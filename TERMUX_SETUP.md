# PostPilot — Android / Termux Complete Operations Guide

This guide provides verified, production-grade instructions for running PostPilot natively on Android devices using **Termux**.

PostPilot utilizes **one unified codebase** across Windows development, Linux cloud hosting, and Android Termux.

---

## 1. Prerequisites & Environment Architecture

### A. Termux App Source
> [!IMPORTANT]
> Install Termux exclusively from **[F-Droid](https://f-droid.org/en/packages/com.termux/)** or the official **[Termux GitHub Releases](https://github.com/termux/termux-app/releases)**.  
> **DO NOT** install Termux from Google Play Store; the Play Store version is deprecated and cannot receive package updates.

### B. Device Storage Requirements
- Android 7.0+ (Android 10+ recommended).
- 350 MB free internal flash storage.
- **CRITICAL STORAGE REQUIREMENT:** Termux and PostPilot must reside on **internal device storage** (`/data/data/com.termux/files/home/`), **NEVER** on an external FAT32/exFAT micro-SD card. SQLite's high-concurrency Write-Ahead Logging (WAL) mode requires POSIX `flock()` advisory file locking, which is not supported by external SD card filesystems.

---

## 2. Automated One-Command Installation (Recommended)

Open Termux on your phone and run:

```bash
pkg update && pkg install -y git
git clone https://github.com/gaathaaidni/postpilot.git ~/postpilot
cd ~/postpilot
bash setup-termux.sh
```

The `setup-termux.sh` script is fully idempotent (safe to run repeatedly) and will:
1. Update system package repositories.
2. Install Python, Git, and pre-compiled ARM64 native media libraries (`python-pillow`, `libjpeg-turbo`, `libpng`, `freetype`, `libwebp`).
3. Create an isolated virtual environment (`.venv`) linked to system site-packages (or reuse existing).
4. Install Python dependencies from `requirements.txt`.
5. Ensure directories `data/images`, `data/media`, `data/backups`, and `logs` exist without altering existing content.
6. Check for an existing `.env`:
   - If `.env` exists: preserves existing user settings.
   - If `.env` does not exist: copies `.env.example` to `.env` with Termux defaults (`APP_ENV=termux`, `HOST=127.0.0.1`, `PORT=5000`, `LOCAL_MODE=1`, and `AI_PROVIDER=mock`).
7. Verify and apply non-destructive SQLite database schema migrations (preserving all existing campaigns, drafts, and posts).

---

## 3. Manual Step-by-Step Installation

If you prefer installing manually step-by-step:

### Step 1: Update Termux Packages
```bash
pkg update && pkg upgrade -y
```

### Step 2: Install Core & Build Packages
```bash
pkg install -y python git python-pillow libjpeg-turbo libpng freetype libwebp termux-tools
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

### Step 5: Configure Environment Template
```bash
cp .env.example .env
```
Edit `.env` using nano if you wish to customize ports or credentials:
```bash
nano .env
```
The default template `.env.example` provides safe defaults for Termux:
```ini
APP_ENV=termux
LOCAL_MODE=1
HOST=127.0.0.1
PORT=5000
DATABASE_URL=sqlite:///data/posts.db
AI_PROVIDER=mock
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
SECRET_KEY=postpilot-dev-secret-key-change-in-production
```
Press `Ctrl + O` then `Enter` to save, and `Ctrl + X` to exit nano.

### Step 6: Create Directories and Initialize Database
```bash
mkdir -p data/images data/media data/backups logs
python -c "import database; database.init_db(); print('Database schema initialized!')"
```

---

## 4. Environment Variables Reference

PostPilot's runtime configuration is managed centrally by `config.py`. The actual variables consumed from `.env` are:

| Variable | Default (Termux / Dev) | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `termux` | Runtime profile (`development`, `termux`, or `production`). Detected from environment or `.env`. |
| `HOST` | `127.0.0.1` | Network interface to bind. Binds strictly to `127.0.0.1` (loopback) in Termux for local security. |
| `PORT` | `5000` | HTTP port for the web dashboard. |
| `LOCAL_MODE` | `1` | Enables automatic admin session creation strictly for requests originating from loopback (`127.0.0.1` / `::1`). Disabled in production. |
| `DATABASE_URL` | `sqlite:///data/posts.db` | Database connection URI. In Termux, uses local SQLite in WAL mode. |
| `SECRET_KEY` | `postpilot-dev-secret-key...` | Flask session secret key. In production, must be explicitly set to a high-entropy secret. |
| `ADMIN_USERNAME` | `admin` | Username for dashboard login when accessing from non-loopback or when `LOCAL_MODE=0`. |
| `ADMIN_PASSWORD` | `admin123` | Password for dashboard login. In production, must be set in `.env`. |
| `MAX_CONTENT_LENGTH`| `16777216` (16 MB) | Maximum upload file size for images and videos. |
| `AI_PROVIDER` | `mock` | Configured AI provider: `mock` (built-in, 100% offline), `groq`, `openai`, or `openai_compatible`. |
| `AI_TIMEOUT_SECONDS`| `30` | Network timeout for external AI requests. |
| `AI_MAX_PROMPT_CHARS`| `8000` | Maximum prompt characters for AI generation requests. |
| `AI_MAX_OUTPUT_TOKENS`| `1500` | Maximum completion tokens generated by the AI provider. |
| `FB_ACCESS_TOKEN` | *empty* | Optional Meta User Access Token. When omitted, social posting is safely simulated/skipped. |

> [!NOTE]
> PostPilot defaults to `AI_PROVIDER=mock`. The mock provider requires zero API keys, consumes zero data, makes zero external network requests, and generates deterministic brand-tailored copy, 14-section strategies, and weekly/monthly content calendars completely offline on your device.

---

## 5. Startup, Shutdown, and Worker Management

### A. Quick Start
Run the startup script:
```bash
./start-termux.sh
```

### B. Role of the Background Worker (`worker.py`)
PostPilot consists of two components:
1. **Web Dashboard (`app.py`):** Serves the UI, handles HTTP requests, manages brand workspaces, AI generation, drafts, and immediate manual publishing.
2. **Background Scheduler Worker (`worker.py`):** Runs the background task daemon that checks for scheduled calendar posts (`process_due_scheduled_posts()`) and executes automated channel intervals (`sync_tasks_with_db()`).

> [!IMPORTANT]
> **Is `worker.py` required?**
> - **Yes**, if you schedule posts on the content calendar to publish at future times automatically in the background. Without `worker.py`, scheduled posts will remain queued and will not publish on schedule.
> - **No**, if you only use PostPilot interactively for AI campaign drafting, brand strategy generation, content planning, and instant manual publishing.

By default, `./start-termux.sh` starts **both** `worker.py` (background daemon with PID tracking in `data/worker.pid` and logs in `logs/worker.log`) and `app.py` (web server with PID tracking in `data/app.pid`). It verifies whether an instance is already running before starting to prevent duplicate processes.

To start *only* the web server without the background worker:
```bash
START_WORKER=0 ./start-termux.sh
```

### C. Clean Shutdown
To stop PostPilot safely:
```bash
./stop-termux.sh
```
`stop-termux.sh` inspects `data/app.pid` and `data/worker.pid` and terminates only PostPilot's specific processes. It will **never** kill unrelated Python applications on your device. It then releases the Android WakeLock.

*Alternatively, if running in the foreground, press `Ctrl + C` in the terminal session.* The cleanup trap will automatically terminate both processes, clean up PID files, and release the WakeLock.

---

## 6. Android Background Execution & Power Management

Android actively conserves battery by suspending background applications and reclaiming RAM. Understanding how Android manages background processes is critical for running background scheduling reliably:

### A. WakeLock (`termux-wake-lock`)
`start-termux.sh` automatically calls `termux-wake-lock` on startup to acquire a CPU wake lock via Android's `PowerManager`. This prevents the phone's CPU from entering deep sleep when the screen turns off.

### B. What WakeLock Can and CANNOT Guarantee
> [!WARNING]
> While `termux-wake-lock` protects against sleep suspension, **it cannot guarantee Android will never terminate the application**:
> 1. **Low Memory Killer (LMK):** If the device runs low on RAM (e.g. running heavy games or opening multiple camera apps), Android's LMK daemon will forcefully kill background processes regardless of wake locks.
> 2. **OEM Aggressive Battery Optimization:** Manufacturers (Samsung One UI, Xiaomi MIUI/HyperOS, OnePlus OxygenOS, Huawei EMUI) employ aggressive proprietary background-killing engines.
> 3. **Notification Dismissal:** If the persistent Termux notification is dismissed or Termux is swiped away from recent apps, Android immediately shuts down the Termux cgroup.

### C. Mandatory Android Settings for 24/7 Scheduling:
To ensure the scheduler runs reliably:
1. **Disable Battery Optimization:**
   - Go to Android **Settings** → **Apps** → **Termux** → **Battery**.
   - Select **Unrestricted** (or **Don't optimize**).
2. **Allow Background Activity:**
   - Enable **Allow background activity** and **Allow background data usage**.
3. **Lock App in Recent Tasks (OEMs):**
   - Open Android Recent Apps view, locate Termux, and tap the lock icon (if available on your device) to prevent accidental swipe-dismissal.

---

## 7. Accessing PostPilot on Mobile Browser

Open Google Chrome, Firefox, or any mobile browser on your Android device and visit:

```text
http://127.0.0.1:5000
```

- **Single-User Local Mode:** When visiting from `127.0.0.1` under `LOCAL_MODE=1`, PostPilot recognizes loopback origin and grants immediate administrative access to the Command Dashboard.
- **Network Isolation:** PostPilot binds exclusively to `127.0.0.1` by default. It is not exposed to Wi-Fi, LAN, or cellular networks. Non-loopback requests are rejected with 401/403.
- **Default Local Credentials:** If accessing with `LOCAL_MODE=0` or via explicit login, the default credentials are `admin` / `admin123`.

---

## 8. Safe Backup and Restore Workflow

PostPilot includes a self-contained, portable backup and restore engine that packages your posts, safe configuration, and media assets into a standard `.zip` file without leaking API tokens or user passwords.

### Exporting Backup
```bash
python backup.py export
```
Output archive is saved in `data/backups/postpilot_backup_YYYYMMDD_HHMMSS.zip`.

### Restoring Backup
```bash
python backup.py import data/backups/postpilot_backup_YYYYMMDD_HHMMSS.zip
```
Optionally overwrite existing records:
```bash
python backup.py import data/backups/postpilot_backup_YYYYMMDD_HHMMSS.zip --overwrite
```

---

## 9. Git-Based Safe Update Workflow

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

## 10. Troubleshooting

### Issue 1: `pkg update` fails with HTTP 403 or repository errors
**Cause:** Outdated Termux mirror.  
**Fix:** Run `termux-change-repo`, select **Main repository**, choose the **Mirrors by Grimler** or **Albatross**, and press OK. Then re-run `pkg update -y`.

### Issue 2: `Pillow` installation takes forever or fails compilation
**Cause:** Pip is trying to build Pillow C-extensions from source on ARM64 without build tools.  
**Fix:** Install the pre-compiled Termux package:
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
