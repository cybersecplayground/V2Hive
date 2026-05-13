#!/usr/bin/env python3
"""
V2Hive - GitHub Auto Sync
Pushes updated configs to GitHub repository
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

# ============ CONFIGURATION ============

# Path to your local V2Hive repository
REPO_PATH = os.getcwd()  # Current directory (run script from inside repo)

# GitHub repository info (automatically detected from git config)
# Make sure you've run: git remote set-url origin https://github.com/cybersecplayground/V2Hive.git

# Folders to sync
FOLDERS_TO_SYNC = ["by-protocol", "by-country"]

# Commit message template
COMMIT_MESSAGE = "Auto-update: {timestamp} - {stats}"

# ============ FUNCTIONS ============

def get_changes_stats():
    """Get statistics about what changed"""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    
    lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
    
    added = []
    modified = []
    deleted = []
    
    for line in lines:
        if line.startswith('A'):
            added.append(line[3:])
        elif line.startswith('M'):
            modified.append(line[3:])
        elif line.startswith('D'):
            deleted.append(line[3:])
    
    return {
        'added': added,
        'modified': modified,
        'deleted': deleted,
        'total': len(lines)
    }

def commit_and_push():
    """Commit and push changes to GitHub"""
    
    # Check if there are any changes
    changes = get_changes_stats()
    
    if changes['total'] == 0:
        print("📝 No changes to commit")
        return True
    
    print(f"\n📊 Changes detected:")
    if changes['added']:
        print(f"   ✅ Added: {len(changes['added'])} files")
        for f in changes['added'][:5]:
            print(f"      - {f}")
        if len(changes['added']) > 5:
            print(f"      ... and {len(changes['added']) - 5} more")
    
    if changes['modified']:
        print(f"   📝 Modified: {len(changes['modified'])} files")
    
    if changes['deleted']:
        print(f"   ❌ Deleted: {len(changes['deleted'])} files")
    
    # Add all changes
    print("\n📦 Staging changes...")
    subprocess.run(["git", "add", "."], cwd=REPO_PATH, capture_output=True)
    
    # Create commit message with stats
    stats = f"{changes['total']} files changed"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = COMMIT_MESSAGE.format(timestamp=timestamp, stats=stats)
    
    print(f"💬 Commit message: {commit_msg}")
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_PATH, capture_output=True)
    
    # Push to GitHub
    print("🚀 Pushing to GitHub...")
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Successfully pushed to GitHub!")
        return True
    else:
        print(f"❌ Push failed: {result.stderr}")
        return False

def check_git_config():
    """Check if git is configured correctly"""
    
    # Check if directory is a git repository
    if not os.path.exists(os.path.join(REPO_PATH, ".git")):
        print("❌ Not a git repository! Run: git init")
        return False
    
    # Check remote URL
    result = subprocess.run(
        ["git", "remote", "-v"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    
    if "cybersecplayground/V2Hive" not in result.stdout:
        print("⚠️  Remote URL not set to cybersecplayground/V2Hive")
        print("   Run: git remote add origin https://github.com/cybersecplayground/V2Hive.git")
        return False
    
    # Check user config
    name_result = subprocess.run(
        ["git", "config", "user.name"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    
    email_result = subprocess.run(
        ["git", "config", "user.email"],
        cwd=REPO_PATH,
        capture_output=True,
        text=True
    )
    
    if not name_result.stdout.strip() or not email_result.stdout.strip():
        print("⚠️  Git user not configured!")
        print("   Run:")
        print('   git config --global user.name "cybersecplayground"')
        print('   git config --global user.email "cybersecplaygroundcom@gmail.com"')
        return False
    
    return True

def main():
    print("=" * 50)
    print("🐝 V2Hive - GitHub Auto Sync")
    print("=" * 50)
    print(f"📁 Repository: {REPO_PATH}")
    print(f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Check git configuration
    print("🔍 Checking git configuration...")
    if not check_git_config():
        return
    
    # Show current status
    print("\n📊 Current git status:")
    subprocess.run(["git", "status", "--short"], cwd=REPO_PATH)
    
    # Commit and push
    success = commit_and_push()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ Sync completed successfully!")
        print("=" * 50)
    else:
        print("\n❌ Sync failed. Check errors above.")

if __name__ == "__main__":
    main()