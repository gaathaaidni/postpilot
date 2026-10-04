# PostPilot — Generic Linux Web Server Deployment Guide

This guide describes how to deploy PostPilot to a standard, isolated Linux server (Ubuntu 22.04/24.04 LTS or Debian 12) behind an Nginx reverse proxy with Gunicorn WSGI and Systemd supervision.

> [!CAUTION]
> **ABSOLUTE PRODUCTION SAFETY**:
> Do NOT deploy this to the existing Gaatha production VPS. PostPilot is decoupled and independent. Deploy ONLY to dedicated, isolated staging or production servers.

---

## 1. Architecture Overview

```text
               INTERNET (HTTPS :443)
                         │
                         ▼
                ┌─────────────────┐
                │   Nginx Proxy   │ (Reverse Proxy, SSL Termination)
                └────────┬────────┘
                         │ (HTTP 127.0.0.1:5000)
                         ▼
        ┌────────────────────────────────┐
        │        Gunicorn WSGI           │
        │           (app.py)             │
        └────────────────┬───────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │   channel_runner│
                └────────┬────────┘
                         │
                         ▼
                 posting_utils.py
                         │
                         ▼
                 facebook_api.py
                         │
                         ▼
                PostgreSQL / SQLite
                         ▲
                         │ (Single Worker Lease)
                ┌────────┴────────┐
                │    worker.py    │
                │ (Systemd Daemon)│
                └─────────────────┘
```

---

## 2. Server Prerequisites

Install system dependencies and build libraries:

```bash
sudo apt update && sudo apt install -y \
    python3 python3-venv python3-pip \
    libjpeg-turbo8-dev zlib1g-dev libpng-dev \
    nginx git certbot python3-certbot-nginx
```

*(Optional: If deploying with PostgreSQL)*
```bash
sudo apt install -y postgresql postgresql-contrib libpq-dev
```

---

## 3. Dedicated System User & Directory Setup

Create an isolated system user with no root privileges:

```bash
sudo useradd --system --shell /bin/bash --home-dir /opt/postpilot postpilot
sudo mkdir -p /opt/postpilot /opt/postpilot/data /opt/postpilot/data/images /var/log/postpilot
sudo chown -R postpilot:postpilot /opt/postpilot /var/log/postpilot
```

---

## 4. Deploy Application Code & Dependencies

Switch to the `postpilot` user and install dependencies:

```bash
sudo -u postpilot -i
cd /opt/postpilot

git clone https://github.com/gaathaaidni/postpilot.git .

# Create clean virtual environment
python3 -m venv venv
source venv/bin/activate

# Install required dependencies
pip install --upgrade pip wheel
pip install -r requirements.txt
# If using PostgreSQL:
pip install psycopg2-binary
```

---

## 5. PostgreSQL vs. SQLite Configuration

### Option A: SQLite (Default, Zero-Config)
SQLite with WAL mode is enabled automatically. No database server configuration is required.
```bash
DATABASE_URL=sqlite:////opt/postpilot/data/posts.db
```

### Option B: PostgreSQL (High-Concurrency Server Mode)
Create an isolated PostgreSQL database and user:
```bash
sudo -u postgres psql
```
```sql
CREATE DATABASE postpilot_db;
CREATE USER postpilot_user WITH ENCRYPTED PASSWORD 'StrongRandomPasswordHere';
GRANT ALL PRIVILEGES ON DATABASE postpilot_db TO postpilot_user;
\c postpilot_db
GRANT ALL ON SCHEMA public TO postpilot_user;
\q
```
Then configure in `.env`:
```bash
DATABASE_URL=postgresql://postpilot_user:StrongRandomPasswordHere@127.0.0.1:5432/postpilot_db
```

---

## 6. Production Environment Variables (`.env`)

Create `/opt/postpilot/.env` owned exclusively by the `postpilot` user:

```bash
cat << 'EOF' > /opt/postpilot/.env
# --- Runtime Profile ---
APP_ENV=production
LOCAL_MODE=0
HOST=127.0.0.1
PORT=5000
FLASK_DEBUG=0

# --- Core Security ---
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=replace-with-a-cryptographically-secure-random-token
SESSION_COOKIE_SECURE=1
MAX_CONTENT_LENGTH=16777216

# --- Authentication ---
ADMIN_USERNAME=admin
ADMIN_PASSWORD=SetAStrongRandomPasswordHere!

# --- Database ---
DATABASE_URL=sqlite:////opt/postpilot/data/posts.db

# --- Storage Directories ---
POSTPILOT_DATA_DIR=/opt/postpilot/data
POSTPILOT_UPLOAD_FOLDER=/opt/postpilot/data/images

# --- Meta / Facebook Graph API ---
# IMPORTANT: NEVER PASTE META TOKENS INTO SOURCE CODE OR CHAT!
FB_ACCESS_TOKEN=your_secure_page_or_user_access_token_here

# Facebook Page IDs
FB_PAGE_ID_SUITE=967550829768297
FB_PAGE_ID_PHOENIX=954901604381882
FB_PAGE_ID_GAATHA_AI=1028368893692590

# Instagram Business Account IDs
INSTA_ID_SUITE=17841449080283492
INSTA_ID_PHOENIX=17841472248438802

# --- Posting Intervals (Seconds) ---
TOUR_INTERVAL=1800
VISA_INTERVAL=1800
GAATHA_INTERVAL=1800
INSTA_CHECK_INTERVAL=180
EOF

chmod 600 /opt/postpilot/.env
```

Initialize database tables:
```bash
python3 -c "import database; database.init_db(); print('Production database initialized successfully!')"
exit # Exit postpilot shell
```

---

## 7. Systemd Service Installation

Templates are provided in `deploy/systemd/`:

1. Copy service units:
   ```bash
   sudo cp /opt/postpilot/deploy/systemd/postpilot-web.service.example /etc/systemd/system/postpilot-web.service
   sudo cp /opt/postpilot/deploy/systemd/postpilot-worker.service.example /etc/systemd/system/postpilot-worker.service
   ```
2. Reload systemd and enable services:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable postpilot-web
   sudo systemctl enable postpilot-worker
   sudo systemctl start postpilot-web
   sudo systemctl start postpilot-worker
   ```
3. Check status:
   ```bash
   sudo systemctl status postpilot-web
   sudo systemctl status postpilot-worker
   ```

---

## 8. Nginx Reverse Proxy Configuration

A template is provided in `deploy/nginx/postpilot.conf.example`:

1. Copy configuration to Nginx:
   ```bash
   sudo cp /opt/postpilot/deploy/nginx/postpilot.conf.example /etc/nginx/sites-available/postpilot.conf
   ```
2. Edit `/etc/nginx/sites-available/postpilot.conf` and update `postpilot.example.com` to your domain.
3. Enable site and reload Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/postpilot.conf /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
4. Obtain SSL certificates:
   ```bash
   sudo certbot --nginx -d postpilot.example.com
   ```

---

## 9. Health & Operational Checks

Run the built-in non-destructive health diagnostics:

```bash
sudo -u postpilot /opt/postpilot/venv/bin/python /opt/postpilot/postpilot_cli.py health
```

Verify token validity safely without displaying secrets:
```bash
sudo -u postpilot /opt/postpilot/venv/bin/python /opt/postpilot/postpilot_cli.py verify-token
```

Check HTTP responsiveness:
```bash
curl -I http://127.0.0.1:5000/login
```

---

## 10. Log Locations & Monitoring

- **Gunicorn Access Log**: `/var/log/postpilot/web_access.log`
- **Gunicorn Error Log**: `/var/log/postpilot/web_error.log`
- **Systemd Journal (Web)**: `journalctl -u postpilot-web -f`
- **Systemd Journal (Worker)**: `journalctl -u postpilot-worker -f`
- **Nginx Logs**: `/var/log/nginx/postpilot_access.log` and `/var/log/nginx/postpilot_error.log`

---

## 11. Automated Backups & Restoration

### Backup
Export database posts, intervals, and media non-destructively:
```bash
sudo -u postpilot /opt/postpilot/venv/bin/python /opt/postpilot/backup.py export
```

Add daily backup cron job for user `postpilot`:
```cron
# Daily backup at 03:00 AM UTC
0 3 * * * cd /opt/postpilot && venv/bin/python backup.py export >> data/backup.log 2>&1
```

### Restoration
Restore from an existing backup archive:
```bash
sudo -u postpilot /opt/postpilot/venv/bin/python /opt/postpilot/backup.py import /path/to/backup.zip
```

---

## 12. Rollback Procedure

If an update requires rollback:
1. Stop services:
   ```bash
   sudo systemctl stop postpilot-worker postpilot-web
   ```
2. Revert code via Git or restore previous release:
   ```bash
   cd /opt/postpilot && git checkout <previous_commit_hash>
   ```
3. Restore database snapshot if schema was altered:
   ```bash
   # For SQLite:
   cp /opt/postpilot/data/backups/posts.db.pre-update /opt/postpilot/data/posts.db
   # For PostgreSQL:
   psql -U postpilot_user -d postpilot_db < /opt/postpilot/data/backups/dump_pre_update.sql
   ```
4. Restart services and verify:
   ```bash
   sudo systemctl start postpilot-web postpilot-worker
   sudo systemctl status postpilot-web postpilot-worker
   ```

---

## 13. Security Best Practices & Meta Credential Handling

- **NEVER PASTE META TOKENS INTO SOURCE CODE, PROMPTS, OR CHAT.**
- **Private Injection**: Add tokens directly into `/opt/postpilot/.env` via file edit or secrets manager.
- **File Permissions**: Ensure `.env` is strictly `chmod 600` and owned by `postpilot:postpilot`.
- **Localhost Binding**: Gunicorn must only bind to `127.0.0.1:5000`, never `0.0.0.0`.
- **Worker Lease**: Only one worker process can hold the lease. Standalone `worker.py` takes precedence over `app.py`.
