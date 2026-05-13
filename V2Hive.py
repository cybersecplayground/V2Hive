#!/usr/bin/env python3
"""
V2Hive - Local Config Fetcher & Rebrander with GeoIP2 (ULTRA-FAST)
Uses concurrent processing for 10-50x speed improvement
"""

import os
import re
import base64
import json
import socket
import sys
import hashlib
from urllib.request import Request, urlopen
from urllib.error import URLError
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Try to import tqdm for progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("[INFO] Install tqdm for progress bar: pip install tqdm")

# Fix Windows console encoding issues
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# ============ CONFIGURATION ============

# List of GitHub raw URLs to fetch from
SOURCE_URLS = [
    "https://openproxylist.com/v2ray/rawlist/text",
    "https://raw.githubusercontent.com/Danialsamadi/v2go/refs/heads/main/Splitted-By-Protocol/ss.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/iboxz/free-v2ray-collector/main/main/mix.txt",
    "https://raw.githubusercontent.com/M-Mashreghi/Free-V2ray-Collector/refs/heads/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/vless_configs.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/vmess_configs.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/refs/heads/main/ss_configs.txt",
]

# Output folder
OUTPUT_DIR = "v2hive"

# Branding
BRAND_TAG = "@LetsGetVPN @CyberSecPlayground"
BRAND_EMOJI = "🚀"
COUNTRY_EMOJI = "🌍"

# Path to GeoLite2-Country.mmdb file
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"
FALLBACK_TO_KEYWORD = True

# Performance settings
MAX_WORKERS = 50  # Number of concurrent threads (increase for faster processing)
DNS_TIMEOUT = 3   # DNS timeout in seconds

# ============ CACHING WITH THREAD SAFETY ============

dns_cache = {}
geoip_cache = {}
config_hash_cache = {}
cache_lock = Lock()

def get_from_cache(cache, key):
    """Thread-safe cache get"""
    with cache_lock:
        return cache.get(key)

def set_to_cache(cache, key, value):
    """Thread-safe cache set"""
    with cache_lock:
        cache[key] = value

# ============ COUNTRY TO EMOJI MAPPING ============

COUNTRY_EMOJIS = {
    "US": "🇺🇸", "JP": "🇯🇵", "DE": "🇩🇪", "SG": "🇸🇬", "NL": "🇳🇱",
    "GB": "🇬🇧", "FR": "🇫🇷", "CA": "🇨🇦", "AU": "🇦🇺", "KR": "🇰🇷",
    "BR": "🇧🇷", "IN": "🇮🇳", "CN": "🇨🇳", "RU": "🇷🇺", "IT": "🇮🇹",
    "ES": "🇪🇸", "MX": "🇲🇽", "ID": "🇮🇩", "TR": "🇹🇷", "SA": "🇸🇦",
    "AE": "🇦🇪", "CH": "🇨🇭", "SE": "🇸🇪", "NO": "🇳🇴", "DK": "🇩🇰",
    "FI": "🇫🇮", "BE": "🇧🇪", "AT": "🇦🇹", "PL": "🇵🇱", "CZ": "🇨🇿",
}

def get_country_emoji(country_code):
    return COUNTRY_EMOJIS.get(country_code, "🌍")

# ============ GEOIP2 SETUP ============

geoip_reader = None

def init_geoip():
    """Initialize GeoIP2 database reader"""
    global geoip_reader
    try:
        import geoip2.database
        if os.path.exists(GEOIP_DB_PATH):
            geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
            print(f"[OK] GeoIP2 database loaded: {GEOIP_DB_PATH}")
            return True
        else:
            print(f"[WARN] GeoIP2 database not found at {GEOIP_DB_PATH}")
            print("       Download from: https://github.com/P3TERX/GeoLite2.mmdb/raw/master/GeoLite2-Country.mmdb")
            return False
    except ImportError:
        print("[WARN] geoip2 library not installed. Run: pip install geoip2")
        return False
    except Exception as e:
        print(f"[WARN] GeoIP2 initialization failed: {e}")
        return False

def get_country_from_ip(ip):
    """Get country code from IP using GeoIP2"""
    # Check cache first
    cached = get_from_cache(geoip_cache, ip)
    if cached is not None:
        return cached
    
    if not geoip_reader:
        return None
    
    try:
        response = geoip_reader.country(ip)
        country = response.country.iso_code
        set_to_cache(geoip_cache, ip, country)
        return country
    except Exception:
        set_to_cache(geoip_cache, ip, None)
        return None

# ============ IP EXTRACTION FROM CONFIGS ============

def extract_ip_from_vmess(config):
    """Extract IP/domain from vmess:// config"""
    try:
        encoded = config.replace("vmess://", "")
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding
        decoded = base64.b64decode(encoded).decode('utf-8')
        data = json.loads(decoded)
        return data.get("add", "")
    except:
        return None

def extract_ip_from_simple(config):
    """Extract IP/domain from vless://, trojan://, ss:// configs"""
    match = re.search(r'://(?:[^@]+@)?([^:/?#]+)', config)
    return match.group(1) if match else None

def resolve_domain_to_ip(domain):
    """Resolve domain to IP with caching and timeout"""
    # Check cache first
    cached = get_from_cache(dns_cache, domain)
    if cached is not None:
        return cached
    
    if not domain or domain.replace('.', '').replace(':', '').isalpha():
        set_to_cache(dns_cache, domain, None)
        return None
    
    try:
        # Set timeout for DNS resolution
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(DNS_TIMEOUT)
        ip = socket.gethostbyname(domain)
        socket.setdefaulttimeout(original_timeout)
        set_to_cache(dns_cache, domain, ip)
        return ip
    except:
        set_to_cache(dns_cache, domain, None)
        return None

# ============ PROCESSING FUNCTIONS ============

def detect_protocol(config):
    if config.startswith("vmess://"):
        return "vmess"
    elif config.startswith("vless://"):
        return "vless"
    elif config.startswith("trojan://"):
        return "trojan"
    elif config.startswith("ss://"):
        return "shadowsocks"
    return None

def keyword_country_fallback(config):
    common_codes = ['US', 'JP', 'DE', 'SG', 'NL', 'GB', 'FR', 'CA', 'AU', 'KR', 'BR', 'IN']
    for code in common_codes:
        if code.lower() in config.lower():
            return code
    return "US"

def get_country_from_config(config):
    """Extract country using GeoIP2"""
    # Extract server address
    server = None
    if config.startswith("vmess://"):
        server = extract_ip_from_vmess(config)
    elif config.startswith(("vless://", "trojan://", "ss://")):
        server = extract_ip_from_simple(config)
    
    if not server:
        return keyword_country_fallback(config)
    
    # Resolve domain to IP if needed
    ip = server
    if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', server):
        ip = resolve_domain_to_ip(server)
        if not ip:
            return keyword_country_fallback(config)
    
    # Query GeoIP2
    if geoip_reader and ip:
        country = get_country_from_ip(ip)
        if country:
            return country
    
    return keyword_country_fallback(config)

def rebrand_vmess(config, country_code):
    try:
        country_emoji = get_country_emoji(country_code)
        new_remark = f"{BRAND_EMOJI} {BRAND_TAG} | {COUNTRY_EMOJI} {country_emoji} {country_code}"
        
        encoded = config.replace("vmess://", "")
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += "=" * padding
        decoded = base64.b64decode(encoded).decode('utf-8')
        data = json.loads(decoded)
        data['ps'] = new_remark
        new_encoded = base64.b64encode(json.dumps(data).encode()).decode()
        return f"vmess://{new_encoded}"
    except:
        return config

def rebrand_simple(config, country_code):
    country_emoji = get_country_emoji(country_code)
    new_tag = f"{BRAND_EMOJI} {BRAND_TAG} | {COUNTRY_EMOJI} {country_emoji} {country_code}"
    
    if '#' in config:
        return re.sub(r'#.*$', f'#{new_tag}', config)
    else:
        return f"{config}#{new_tag}"

def process_single_config(config):
    """Process a single config - designed for threading"""
    try:
        # Handle raw base64 configs
        if not config.startswith(("vmess://", "vless://", "trojan://", "ss://")):
            try:
                padding = 4 - (len(config) % 4)
                if padding != 4:
                    config += '=' * padding
                decoded = base64.b64decode(config).decode('utf-8')
                if decoded.startswith(("vmess://", "vless://", "trojan://", "ss://")):
                    config = decoded
                else:
                    return None, None, None
            except:
                return None, None, None
        
        # Get country and rebrand
        country = get_country_from_config(config)
        
        protocol = detect_protocol(config)
        if not protocol:
            return None, None, None
        
        if protocol == "vmess":
            rebranded = rebrand_vmess(config, country)
        else:
            rebranded = rebrand_simple(config, country)
        
        if not rebranded:
            return None, None, None
        
        return rebranded, protocol, country
    except:
        return None, None, None

def get_config_hash_fast(config):
    """Generate unique hash for deduplication"""
    # Check cache
    cached = get_from_cache(config_hash_cache, config)
    if cached is not None:
        return cached
    
    try:
        protocol = detect_protocol(config)
        if not protocol:
            return None
        
        if protocol == "vmess":
            encoded = config.replace("vmess://", "")
            padding = 4 - (len(encoded) % 4)
            if padding != 4:
                encoded += "=" * padding
            decoded = base64.b64decode(encoded).decode('utf-8')
            data = json.loads(decoded)
            unique_str = f"{data.get('add', '')}:{data.get('port', '')}"
            result = hashlib.md5(unique_str.encode()).hexdigest()
        else:
            match = re.search(r'://(?:[^@]+@)?([^:/?#]+):?(\d*)', config)
            if match:
                server = match.group(1)
                port = match.group(2) if match.group(2) else "443"
                unique_str = f"{server}:{port}"
                result = hashlib.md5(unique_str.encode()).hexdigest()
            else:
                result = hashlib.md5(config.encode()).hexdigest()
    except:
        result = hashlib.md5(config.encode()).hexdigest()
    
    set_to_cache(config_hash_cache, config, result)
    return result

def remove_duplicates_fast(configs):
    """Remove duplicates using threading for hash generation"""
    seen_hashes = set()
    unique_configs = []
    duplicates_found = 0
    
    # Use threads to generate hashes in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(get_config_hash_fast, config): config for config in configs}
        
        for future in tqdm(as_completed(futures), total=len(configs), desc="Deduplicating", unit="config") if HAS_TQDM else as_completed(futures):
            config = futures[future]
            config_hash = future.result()
            if config_hash and config_hash not in seen_hashes:
                seen_hashes.add(config_hash)
                unique_configs.append(config)
            else:
                duplicates_found += 1
    
    if duplicates_found > 0:
        print(f"  [INFO] Removed {duplicates_found} duplicate configs")
    
    return unique_configs

def fetch_url(url):
    """Fetch content from a URL"""
    try:
        req = Request(url, headers={'User-Agent': 'V2Hive/1.0'})
        with urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8')
            lines = [line.strip() for line in content.splitlines() 
                    if line.strip() and not line.startswith('#')]
            print(f"  [OK] Fetched {len(lines)} configs from {url}")
            return lines
    except Exception as e:
        print(f"  [FAIL] {url} - {e}")
        return []

def save_configs(protocol_data, country_data):
    """Save configs to flat folder structure"""
    os.makedirs(f"{OUTPUT_DIR}/by-protocol", exist_ok=True)
    os.makedirs(f"{OUTPUT_DIR}/by-country", exist_ok=True)
    
    protocol_files = {
        "vmess": "all_vmess.txt",
        "vless": "all_vless.txt",
        "trojan": "all_trojan.txt",
        "shadowsocks": "all_ss.txt"
    }
    
    for protocol, filename in protocol_files.items():
        if protocol in protocol_data and protocol_data[protocol]:
            filepath = f"{OUTPUT_DIR}/by-protocol/{filename}"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(protocol_data[protocol]))
            print(f"  [OK] Saved {len(protocol_data[protocol])} configs to {filepath}")
    
    for country, configs in country_data.items():
        if configs:
            filepath = f"{OUTPUT_DIR}/by-country/{country}.txt"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(configs))
            print(f"  [OK] Saved {len(configs)} configs to {filepath}")

# ============ MAIN ============

def main():
    start_time = datetime.now()
    
    print("=" * 50)
    print("🐝 V2Hive - ULTRA-FAST Config Collector")
    print(f"🐝 Using {MAX_WORKERS} concurrent workers")
    print("=" * 50)
    print(f"\n[INFO] Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Initialize GeoIP2
    geoip_available = init_geoip()
    if not geoip_available and FALLBACK_TO_KEYWORD:
        print("[INFO] Using keyword fallback for country detection\n")
    
    # Fetch all configs
    print(f"[INFO] Fetching from {len(SOURCE_URLS)} sources...\n")
    all_configs = []
    for url in SOURCE_URLS:
        configs = fetch_url(url)
        all_configs.extend(configs)
    
    print(f"\n[INFO] Total configs collected: {len(all_configs)}")
    
    # Remove duplicates
    print("[INFO] Removing duplicate configs...")
    dedup_start = datetime.now()
    all_configs = remove_duplicates_fast(all_configs)
    dedup_time = (datetime.now() - dedup_start).total_seconds()
    print(f"[INFO] Unique configs: {len(all_configs)} (took {dedup_time:.1f}s)")
    
    # Process configs concurrently
    print(f"\n[INFO] Processing {len(all_configs)} configs with {MAX_WORKERS} threads...\n")
    
    protocol_data = {"vmess": [], "vless": [], "trojan": [], "shadowsocks": []}
    country_data = {}
    processed = 0
    failed = 0
    
    process_start = datetime.now()
    
    # Use ThreadPoolExecutor for concurrent processing
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_config, config): config for config in all_configs}
        
        # Process results with progress bar
        iterator = tqdm(as_completed(futures), total=len(futures), desc="Processing", unit="config") if HAS_TQDM else as_completed(futures)
        
        for future in iterator:
            rebranded, protocol, country = future.result()
            
            if rebranded and protocol and country:
                if protocol in protocol_data:
                    protocol_data[protocol].append(rebranded)
                    processed += 1
                
                if country not in country_data:
                    country_data[country] = []
                country_data[country].append(rebranded)
            else:
                failed += 1
    
    process_time = (datetime.now() - process_start).total_seconds()
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    print(f"\n[INFO] Successfully processed: {processed} configs")
    print(f"[INFO] Failed: {failed} configs")
    print(f"[INFO] Countries detected: {len(country_data)}")
    print(f"[INFO] Processing speed: {processed / process_time:.1f} configs/second")
    print(f"[INFO] Cache stats: DNS: {len(dns_cache)}, GeoIP: {len(geoip_cache)}")
    print(f"[INFO] Total time: {total_time:.1f} seconds")
    
    # Save to disk
    print("\n[INFO] Saving to local folder...")
    save_start = datetime.now()
    save_configs(protocol_data, country_data)
    save_time = (datetime.now() - save_start).total_seconds()
    print(f"[INFO] Save time: {save_time:.1f} seconds")
    
    print(f"\n[OK] Done! Files saved to: {OUTPUT_DIR}/")
    print(f"\n[INFO] End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()