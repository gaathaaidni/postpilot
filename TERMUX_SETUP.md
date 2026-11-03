# PostPilot — Android / Termux Complete Operations Guide

This guide provides verified, production-grade instructions for running PostPilot natively on Android devices using **Termux**.

PostPilot utilizes **one unified codebase** across Windows development, Linux cloud hosting, and Android Termux.

---

## 1. Prerequisites & Environment Architecture

### A. Termux App Source
> [!IMPORTANT]
> Install Termux exclusively from **[F-Droid](https://f-droid.org/en/packages/com.termux/)** or the official **GitHub Releases**.
> **DO NOT** install Termux from Google Play Store; the Play Store version is deprecated and cannot receive package updates.

### B. Device Storage Requirements
- Android 7.0+ (Android 10+ recommended).
- 350 MB free internal flash storage.
- **CRITICAL STORAGE NOTE:** Termux and PostPilot must reside on **internal device storage** (`/data/data/com.termux/files/home/`), **NEVER** on an external FAT32/exFAT micro-SD card. SQLite's high-concurrency Write-Ahead Logging (WAL) mode requires POSIX `flock()` advisory file locking, which is not supported by external SD card filesystems.

---

## 2. Automated One-Command Installation (Recommended)

Open Termux and execute:

```bash
pkg update && pkg install -y git
git clone https://github.com/gaathaaidni/postpilot.git ~/postpilot
cd ~/postpilot
bash setup-termux.sh
```

The script will automatically:
1. Update system package mirrors.
2. Install Python, Git, and pre-compiled ARM64 native media libraries (`python-pillow`, `libjpeg-turbo`, `libpng`, `freetype`, `libwebp`).
3. Create an isolated virtual environment (`.venv`) linked to system site-packages.
4. Install all Python dependencies from `requirements.txt`.
5. Create `.env` pre-configured for Termux local mode (`APP_ENV=termux`, `LOCAL_MODE=1`).
6. Initialize the SQLite database schema with WAL mode and seed the default administrator.

---

## 3. Manual Step-by-Step Installation

If you prefer installing manually step-by-step:

### Step 1: Update Termux Packages
```bash
pkg update && pkg upgrade -y
```

### Step 2: Install Core & Build Packages
```bash
pkg install -y python git python-pillow libjpeg-turbo libpng freetype libwebp
```

### Step 3: Clone Repository
```bash
cd ~
git clone https://github.com/gaathaaidni/postpilot.git
cd postpilot
```

### Step 4: Virtual Environment Setup
```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

### Step 5: Configure Environment
```bash
cp .env.example .env
```
Edit `.env` using nano:
```bash
nano .env
```
Verify the following Termux defaults are set:
```dotenv
APP_ENV=termux
LOCAL_MODE=1
HOST=127.0.0.1
PORT=5000
DATABASE_URL=sqlite:///data/posts.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password_here
```
Press `Ctrl + O` then `Enter` to save, and `Ctrl + X` to exit.

### Step 6: Initialize Database
```bash
python -c "import database; database.init_db(); print('Database schema initialized!')"
```

---

## 4. Startup and Shutdown Commands

### A. Quick Start
Run the startup script:
```bash
./start-termux.sh
```
*Or manually:*
```bash
source .venv/bin/activate
termux-wake-lock
python app.py
```

### B. Clean Shutdown
To stop PostPilot safely:
```bash
./stop-termux.sh
```
*Or press `Ctrl + C` in the running terminal session, then release the lock:*
```bash
termux-wake-unlock
```

---

## 5. Android Background Execution (Preventing Process Killing)

Android's aggressive battery management can terminate long-running background tasks when the phone screen turns off.

Follow these two essential steps:

1. **Acquire Termux WakeLock:**
   `start-termux.sh` automatically calls `termux-wake-lock`. You will see a persistent notification:  
   `Termux - Acquiring wake lock`.
2. **Disable Android Battery Optimization for Termux:**
   - Go to Android **Settings** → **Apps** → **Termux**.
   - Tap **Battery** → Select **Unrestricted** (or **Don't optimize**).
   - Enable **Allow background activity**.

---

## 6. Accessing PostPilot on Mobile Browser

Open Google Chrome or any browser on your Android device and navigate to:

```text
http://127.0.0.1:5000
```

- When accessing from `127.0.0.1` under `LOCAL_MODE=1`, PostPilot automatically logs you into the Command Dashboard.
- External connections across LAN or Wi-Fi require explicit authentication with `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

---

## 7. Safe Backup and Restore Workflow

PostPilot includes a self-contained, portable backup and restore engine that packages your posts, safe configuration, and media assets into a standard `.zip` file without leaking API tokens or user passwords.

### Exporting Backup
```bash
python backup.py export
```
Output archive is saved in `data/backups/postpilot_backup_YYYYMMDD_HHMMSS.zip`.

### Restoring Backup
```bash
python backup.py import data/backups/postpilot_backup_20261103_051218.zip
```
Optionally overwrite existing records:
```bash
python backup.py import data/backups/postpilot_backup_20261103_051218.zip --overwrite
```

---

## 8. Git-Based Update Workflow

To update your running PostPilot installation to the latest code on GitHub without losing data:

```bash
./update-termux.sh
```

This automated update script:
1. Generates an automated safety backup in `data/backups/`.
2. Executes `git pull origin main` to fetch tested updates.
3. Upgrades Python dependencies via `pip install -r requirements.txt`.
4. Runs `database.init_db()` to apply non-destructive database migrations.

---

## 9. Android Capability Matrix & Platform Distinctions

| Feature / Module | Android Termux Status | Notes |
| :--- | :--- | :--- |
| **Command Dashboard** | ✅ **Full Support** | Mobile-responsive touch layout on Chrome / Firefox |
| **Multi-Brand Workspaces** | ✅ **Full Support** | Dynamic GAATHA workspaces and custom brands |
| **Calendar Scheduling** | ✅ **Full Support** | Persistent SQLite task scheduling with WakeLock |
| **Meta Graph API Publishing** | ✅ **Full Support** | Facebook Pages and Instagram via official HTTPS APIs |
| **Media Uploads & Storage** | ✅ **Full Support** | Images/videos stored safely in `data/images` |
| **Portable Backup / Restore** | ✅ **Full Support** | Zip package transfer between phone, PC, and VPS |
| **WhatsApp Cloud API** | ✅ **Full Support** | Official WhatsApp Business Cloud API messages |
| **PostgreSQL Database** | ⚠️ **Client Only** | Connects to remote PostgreSQL via URL; local DB uses SQLite |
| **WhatsApp Web/Status Scraping** | ❌ **Unsupported** | Unofficial Chromium scraping is not supported on Android |
| **Reverse Proxy (Nginx/SSL)** | ℹ️ **Optional** | Termux connects directly to `127.0.0.1:5000`; Nginx is for VPS |

---

## 10. Troubleshooting

### Issue 1: `pkg update` fails with HTTP 403 or repository errors
**Cause:** Outdated Termux mirror.  
**Fix:** Run `termux-change-repo`, select **Main repository**, choose the **Mirrors by Albatross** or **Grimler**, and press OK. Then re-run `pkg update -y`.

### Issue 2: `Pillow` installation takes forever or fails compilation
**Cause:** Pip is trying to build Pillow C-extensions from source on ARM64 without build tools.  
**Fix:** Install the official pre-compiled Termux package:
```bash
pkg install -y python-pillow
```
Ensure your virtual environment was created with `--system-site-packages`:
```bash
python -m venv --system-site-packages .venv
```

### Issue 3: Process terminated when screen turns off
**Cause:** Android Battery Saver terminated the background terminal.  
**Fix:**
```bash
termux-wake-lock
```
Check Android Settings → Apps → Termux → Battery → Set to **Unrestricted**.

### Issue 4: `sqlite3.OperationalError: database is locked`
**Cause:** Attempting to store database files on an external MicroSD card (`/sdcard` or `/storage/emulated/0`), which lacks POSIX locking.  
**Fix:** Ensure PostPilot is installed strictly in Termux internal storage:
```bash
cd /data/data/com.termux/files/home/postpilot
```

### Issue 5: Port 5000 already in use
**Cause:** A previous Python process is still bound to port 5000.  
**Fix:**
```bash
./stop-termux.sh
```
Or kill manually:
```bash
fuser -k 5000/tcp
```
