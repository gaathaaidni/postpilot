# PostPilot — Android / Termux Setup Guide

This guide provides verified, step-by-step instructions for running PostPilot natively on an Android device using **Termux**.

---

## 1. Prerequisites

### A. Install Termux
> [!IMPORTANT]
> Install Termux exclusively from **[F-Droid](https://f-droid.org/en/packages/com.termux/)** or the official **GitHub Releases**.
> **DO NOT** install Termux from Google Play Store; that version is deprecated and receives no updates.

### B. Device Requirements
- Android 7.0 or higher (Android 10+ recommended)
- Minimum 300MB free internal device storage
- Termux must be installed in internal storage (NOT external SD card, as SQLite WAL mode requires POSIX lock support).

---

## 2. Package Installation

Open Termux and update core packages:

```bash
pkg update && pkg upgrade -y
```

Install Python, Git, and native build dependencies required by Pillow (image processing):

```bash
pkg install -y python git libjpeg-turbo libpng freetype libwebp
```

Verify installed Python version:

```bash
python --version
# Expected: Python 3.11.x or 3.12.x
```

---

## 3. Clone or Copy PostPilot

Clone the repository into your Termux home directory (`~/`):

```bash
cd ~
git clone https://github.com/gaathaaidni/postpilot.git
cd postpilot
```

*Or, if transferring files from your development machine:*
```bash
cd ~
# Copy postpilot folder to ~/postpilot
cd ~/postpilot
```

---

## 4. Virtual Environment & Dependencies

Create and activate an isolated Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Upgrade pip and wheel:

```bash
pip install --upgrade pip wheel setuptools
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

> [!TIP]
> If building `Pillow` from source via pip takes too long on a low-end phone, you can install the pre-compiled Termux Pillow package:
> ```bash
> pkg install -y python-pillow
> ```

---

## 5. Environment Configuration

Copy the example configuration:

```bash
cp .env.example .env
```

Edit `.env` using `nano`:

```bash
nano .env
```

Configure your settings:

```dotenv
# Runtime Environment
APP_ENV=termux
LOCAL_MODE=1
HOST=127.0.0.1
PORT=5000

# Security (Set a strong admin password)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password_here

# Meta Graph API Token (Optional during testing)
FB_ACCESS_TOKEN=your_facebook_access_token_here
```

Press `Ctrl + O` then `Enter` to save, and `Ctrl + X` to exit nano.

---

## 6. Prevent Android from Killing the Process (WakeLock)

Android's battery manager aggressively terminates background processes when the screen turns off. To keep PostPilot active:

```bash
termux-wake-lock
```

You will see an active notification: `Termux - Acquiring wake lock`.

---

## 7. Initialize Database & Start Application

Initialize the SQLite database:

```bash
python -c "import database; database.init_db(); print('Database initialized successfully!')"
```

Start the PostPilot application:

```bash
python app.py
```

Expected output:
```text
2026-10-03 10:00:00 [INFO] (App) Starting PostPilot in termux mode on 127.0.0.1:5000
 * Serving Flask app 'app'
 * Running on http://127.0.0.1:5000
```

---

## 8. Access in Mobile Browser

Open Google Chrome or your default mobile browser on the phone and navigate to:

```text
http://127.0.0.1:5000
```

- In `LOCAL_MODE=1`, localhost access automatically authenticates to the Dashboard.
- All module controls (Nexora Suite, Phoenix Intl, Gaatha AI, Instagram Sync) and Post CRUD are fully functional.

---

## 9. Background Automation Daemon (Optional)

If running in multi-worker server mode on Termux, you can run the background worker daemon in a separate Termux session:

```bash
# In Termux Session 1:
python app.py

# In Termux Session 2:
python worker.py
```

---

## 10. Manual Phone Testing Checklist

| Test Item | Verification Procedure | Expected Outcome |
| :--- | :--- | :--- |
| **App Launch** | Run `python app.py` | Starts without errors on `127.0.0.1:5000` |
| **Local Access** | Open `http://127.0.0.1:5000` | Dashboard loads cleanly |
| **Mobile UI** | Test navigation on mobile screen | Dropdown navigation switches modules cleanly |
| **Post CRUD** | Add a post with image upload | Post created and image saved in `data/images` |
| **Task Control** | Click "Start" on Nexora Suite | Status changes to "Running" in database |
| **WakeLock** | Turn off screen for 10 minutes | Tasks remain active without being killed |
| **Data Export** | Run `python backup.py export` | Creates `.zip` in `data/backups/` |
