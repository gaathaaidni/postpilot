# PostPilot — Start Here (User Guide)

Welcome to **PostPilot**. This guide provides practical, step-by-step instructions to get up and running immediately.

---

### 1. How do I install it?

Ensure Python 3.10+ is installed on your system.

```bash
# 1. Clone repository
git clone https://github.com/gaathaaidni/postpilot.git
cd postpilot

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux / macOS / Termux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

---

### 2. How do I configure `.env`?

Copy the provided example template to create your `.env` file:

```bash
cp .env.example .env
```

Open `.env` in any text editor and adjust basic settings:
```ini
APP_ENV=development
SECRET_KEY=replace-with-a-random-secret-string
DATABASE_URL=sqlite:///data/posts.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
LOCAL_MODE=1
```
*Never commit or share your `.env` file!*

---

### 3. How do I start it?

To run the local web server:

```bash
python app.py
```
By default, PostPilot listens on `http://127.0.0.1:5000`.

---

### 4. How do I log in?

1. Open your browser and navigate to `http://localhost:5000`.
2. If `LOCAL_MODE=1` is set in development, requests from `127.0.0.1` are automatically granted local administrator access.
3. Otherwise, enter your credentials:
   - **Username**: `admin` (or the value set in `.env`)
   - **Password**: `admin123` (or the value set in `.env`)
4. Click **Sign In**.

---

### 5. How do I connect Meta?

1. Generate a User Access Token in your [Meta for Developers](https://developers.facebook.com/) portal with `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `instagram_basic`, and `instagram_content_publish` permissions.
2. In your private `.env` file, supply your token:
   ```ini
   FB_ACCESS_TOKEN=your_token_here
   ```
3. Test your token safely via CLI:
   ```bash
   python postpilot_cli.py token
   ```
*If you do not have a Meta token yet, PostPilot will function completely in safe offline mode.*

---

### 6. How do I create a post?

1. In the Web UI, select a channel module from the sidebar or mobile menu (e.g., **Nexora Suite**, **Phoenix Intl**, or **Gaatha AI**).
2. Click **Create New Post** or **Add Post**.
3. Type your message or caption.
4. Optional: Click **Upload Image** to attach a photo (PNG, JPG, or WEBP under 16MB).
5. Click **Save Post**.

---

### 7. How do I schedule a post?

1. Posts in each channel are published automatically according to that channel's configured interval.
2. To change the interval, locate the **Post Interval** setting on the channel tab.
3. Enter the interval in seconds (for example, `1800` for 30 minutes, `3600` for 1 hour).
4. Click **Update Interval**. The scheduler worker will automatically pick up the new interval.

---

### 8. How do I run the worker?

PostPilot uses a separate background worker daemon so scheduled publishing does not slow down the web server:

```bash
python worker.py
```
- The worker claims a distributed database lease.
- If multiple workers are started, secondary workers automatically stay in standby mode.
- Press `Ctrl+C` to gracefully shut down the worker and release the lease.

---

### 9. How do I back up data?

To export all your posts and uploaded media into a portable ZIP archive:

```bash
python backup.py export
```
The backup archive will be saved in `data/backups/postpilot_backup_[timestamp].zip`.  
*Note: Backups strictly exclude passwords and API tokens for security.*

---

### 10. How do I restore data?

To import a backup archive into PostPilot:

```bash
python backup.py import data/backups/postpilot_backup_XXXXXXXX.zip
```
All posts and media will be extracted and verified into your current database.

---

### 11. How do I use it from my phone?

PostPilot provides a fully responsive mobile interface:
1. **Via Termux**: Run PostPilot natively inside Termux on your phone and open `http://localhost:5000` in Chrome/Firefox for Android.
2. **Via Local Network / Web Server**: If hosted on a server behind HTTPS, access the web URL directly from your mobile browser. The UI automatically activates mobile navigation, single-column metrics, and touch-optimized buttons.

---

### 12. What is still environment-dependent?

The core application, UI, database, scheduling, and backup are fully validated and ready to use. However, the following external integrations require your specific environment setup:
- **Live Meta Publishing**: Requires your own valid Meta Developer access token.
- **Physical Android Handset**: Architecture is ready for Termux, pending installation on your physical device.
- **Linux Server Deployment**: Production systemd and Nginx templates in `deploy/` must be configured with your server's domain name.
- **PostgreSQL Database**: SQLite is the default; switching to PostgreSQL requires a running PostgreSQL server specified in `DATABASE_URL`.
