@echo off
echo =========================================
echo 🐝 V2Hive - Complete Pipeline
echo =========================================
echo.

REM Step 1: Pull latest from GitHub
echo 📥 Pulling latest from GitHub...
git pull origin main

REM Step 2: Run V2Hive collector
echo.
echo 🔄 Running V2Hive collector...
python V2Hive.py

REM Step 3: Sync to GitHub
echo.
echo 📤 Syncing to GitHub...
python github_sync.py

echo.
echo ✅ Complete pipeline finished!
pause