# PostPilot — Universal Social Media Automation & Scheduling Platform

PostPilot is a universal, secure, and lightweight social publishing and scheduling application built with Python and Flask. It orchestrates automated publishing and cross-posting across Meta platforms (Facebook Pages & Instagram Business) with multi-worker coordination, database persistence, and cross-platform backup/restore.

PostPilot is engineered as a **single unified codebase** capable of running on both local desktop/Termux environments and production Linux web servers.

---

> ⚠️ **CRITICAL PRODUCTION WARNING**:  
> PostPilot is an independent application that is maintained completely separate from the Gaatha production VPS (`/root/gaathacore`), production databases, and production web services. PostPilot must NEVER be deployed to or run against Gaatha production infrastructure.

---

## Current Implemented Capabilities

- 🔐 **Authentication & Access Control**: Secure session-based authentication (`HttpOnly`, `SameSite=Lax`, configurable `Secure`), bcrypt password hashing, and local admin auto-login strictly restricted to `127.0.0.1` in development/Termux mode.
- 🛡️ **CSRF & Upload Protection**: Enforced session CSRF token validation on all mutating endpoints; file upload validation with MIME checking, size limits, and filename sanitization against path traversal.
- 📺 **Channel Orchestration**: Centralized channel runner ([channel_runner.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/channel_runner.py)) managing three publishing channels:
  - 🌍 **Nexora Suite (`tour`)**: Facebook photo & caption broadcasting for tour updates.
  - 🛂 **Phoenix International (`nz`)**: Facebook photo & caption broadcasting for visa/immigration updates.
  - 📜 **Gaatha AI (`gaatha`)**: Facebook photo & caption publishing for cultural AI content.
- 📸 **Instagram Synchronization (`insta`)**: Automated sync monitoring Facebook posts and broadcasting them to linked Instagram Business accounts.
- 🔄 **Duplicate Prevention**: Database-backed `synced_posts` tracking table preventing repeated public cross-posting across channels.
- ⏱️ **Distributed Worker Lease**: Standalone background scheduler daemon ([worker.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/worker.py)) utilizing database-backed atomic lease acquisition, periodic heartbeat renewal, clean signal shutdown, and stale lease recovery.
- 💾 **Universal Database Support**: Built-in SQLite with Write-Ahead Logging (WAL) for multi-process safety on local/Termux runtimes, and a fully compatible PostgreSQL abstraction layer for cloud web servers.
- 📦 **Portable Backup & Restore**: Full ZIP export and restore utility ([backup.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/backup.py)) archiving post records and media while strictly excluding credentials, tokens, and `.env` files.
- 💻 **Modern Web UI**: Responsive desktop and mobile browser interface ([templates/index.html](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/templates/index.html), [static/style.css](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/static/style.css)) featuring mobile navigation, touch-accessible buttons, and live task monitoring.
- 🛠️ **Unified CLI Tool**: Powerful command-line utility ([postpilot_cli.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/postpilot_cli.py)) for headless status, health diagnostics, channel execution, and token debugging.

---

## Quick Start (Windows / Local PC)

### 1. Installation

```powershell
# Clone or navigate to the repository directory
cd postpilot

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to create your private `.env` file:

```powershell
cp .env.example .env
```

Edit `.env` to configure your runtime parameters:
```ini
APP_ENV=development
SECRET_KEY=generate-a-secure-random-secret-key
DATABASE_URL=sqlite:///data/posts.db
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
LOCAL_MODE=1
```

> **Security Note**: Never commit `.env` or access tokens to version control. `.env` is ignored by Git by default.

### 3. Starting PostPilot

To start the local web application:
```powershell
python app.py
```
Open [http://localhost:5000](http://localhost:5000) in your web browser.

To run the background scheduler worker in a separate terminal:
```powershell
python worker.py
```

To run diagnostics or manage tasks via CLI:
```powershell
python postpilot_cli.py health
python postpilot_cli.py status
python postpilot_cli.py list tour
```

---

## Meta / Facebook Graph API Configuration

To enable live publishing to Facebook Pages and Instagram:
1. Generate a User Access Token in the [Meta for Developers Portal](https://developers.facebook.com/) with `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `instagram_basic`, and `instagram_content_publish` permissions.
2. In your private `.env` file, supply your token:
   ```ini
   FB_ACCESS_TOKEN=your_private_token_here
   ```
3. Test your token safely without exposing it:
   ```powershell
   python postpilot_cli.py token
   ```
4. If no Meta token is supplied, PostPilot operates safely in offline mode with full UI and database functionality enabled.

> **CRITICAL CREDENTIAL SAFETY RULES**:  
> - Never hardcode Meta tokens in source files or scripts.  
> - Never paste Meta tokens in chat, GitHub issues, or commit logs.  
> - If an access token is ever exposed, revoke and regenerate it immediately in the Meta Developer Portal.

---

## Linux Server Deployment

Production deployment templates are provided in the `deploy/` directory:
- [deploy/gunicorn.conf.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/deploy/gunicorn.conf.py): Optimized multi-worker WSGI server configuration.
- [deploy/postpilot-web.service](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/deploy/postpilot-web.service): Systemd service unit for the web process.
- [deploy/postpilot-worker.service](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/deploy/postpilot-worker.service): Systemd service unit for the scheduler worker daemon.
- [deploy/nginx/postpilot.conf.example](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/deploy/nginx/postpilot.conf.example): Reverse proxy template with TLS, security headers, and static file caching.
- [deploy/staging_setup.sh](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/deploy/staging_setup.sh): Automated installation script for isolated Ubuntu/Debian staging hosts.

*Note: Deployment files are templates and must be adapted to your isolated server's domain and directories.*

---

## Android / Termux Usage

PostPilot is designed to run locally on Android devices using Termux:
- Follow the setup guide in [TERMUX_SETUP.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/TERMUX_SETUP.md).
- Binds to `127.0.0.1:5000` for safe single-user access via phone browser.
- *Note: While architectural portability is verified, physical device execution remains classified as pending actual hardware testing.*

---

## PostgreSQL Database Configuration

PostPilot supports PostgreSQL out of the box. To switch from SQLite to PostgreSQL:
```ini
DATABASE_URL=postgresql://postpilot_user:strong_password@localhost:5432/postpilot_db
```
The database layer automatically detects PostgreSQL and uses compatible SQL syntax (`SERIAL`, `CURRENT_TIMESTAMP`, and `ON CONFLICT DO NOTHING`).  
*Note: SQL dialect compatibility is verified; live certification is pending an isolated running PostgreSQL instance.*

---

## Portable Data Backup & Restore

PostPilot separates content data from secrets:
- **Export Backup**:
  ```powershell
  python backup.py export
  ```
  Generates a ZIP archive in `data/backups/` containing all post records and media. Credentials, user passwords, and `.env` are strictly excluded.
- **Import Backup**:
  ```powershell
  python backup.py import data/backups/postpilot_backup_XXXXXX.zip
  ```

---

## User Handover Guides

For step-by-step usage instructions, consult:
- 📖 [POSTPILOT_START_HERE.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/POSTPILOT_START_HERE.md) — Simple practical guide for new users.
- 📋 [POSTPILOT_FINAL_READY_TO_USE_CERTIFICATION.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/POSTPILOT_FINAL_READY_TO_USE_CERTIFICATION.md) — Comprehensive readiness and validation certification report.
- ⚙️ [LOCAL_DEVELOPMENT.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/LOCAL_DEVELOPMENT.md) — Local developer setup and testing.
- 🚀 [SERVER_DEPLOYMENT.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/SERVER_DEPLOYMENT.md) — Server deployment details.
- 📱 [TERMUX_SETUP.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/TERMUX_SETUP.md) — Phone Termux setup instructions.
- 💾 [DATA_EXPORT_IMPORT.md](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/DATA_EXPORT_IMPORT.md) — Data migration manual.