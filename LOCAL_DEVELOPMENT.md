# PostPilot — Windows & Local Development Guide

This document describes how to set up, run, test, and develop PostPilot in a local development environment (Windows, macOS, or Linux workstation).

---

## 1. Prerequisites

- **Python**: Version 3.10, 3.11, or 3.12 (64-bit recommended)
- **Git**: Version 2.x+
- **Shell**: PowerShell or Command Prompt (Windows), Bash/Zsh (macOS/Linux)
- **No Docker Required**: PostPilot runs natively with zero external dependencies.

---

## 2. Quick Setup Sequence

### Step 1: Clone the Repository
```powershell
git clone https://github.com/gaathaaidni/postpilot.git
cd postpilot
```

### Step 2: Create Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(On Command Prompt, use `.\.venv\Scripts\activate.bat`. On macOS/Linux, use `source .venv/bin/activate`)*

### Step 3: Install Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Default development settings in `.env`:
- `APP_ENV=development`
- `LOCAL_MODE=1` (grants automatic access strictly for `127.0.0.1`)
- `HOST=127.0.0.1`
- `PORT=5000`
- `DATABASE_URL=sqlite:///data/posts.db`
- `ADMIN_USERNAME=admin`
- `ADMIN_PASSWORD=admin123`

### Step 5: Initialize the Database
```powershell
python -c "import database; database.init_db(); print('Database initialized!')"
```

### Step 6: Start the Application
```powershell
python app.py
```

Open your browser at:
```text
http://127.0.0.1:5000
```

---

## 3. Development Commands Reference

### Run the Background Worker Daemon
In server environments or when simulating decoupled task execution:
```powershell
python worker.py
```

### Run Comprehensive Runtime Validation Suite
Executes the automated 10-phase verification test (DB init, auth, CSRF, local vs LAN boundary, CRUD, media validation, task state, persistence, export/import):
```powershell
python test_runtime_validation.py
```

### Run Multi-Worker Concurrency Test
Verifies cross-process task visibility and SQLite WAL mode without shared memory:
```powershell
python test_multi_worker.py
```

### Database Live Backup (SQLite WAL-Safe)
Creates a transactionally consistent online backup of the SQLite database:
```powershell
python -c "import database; print('Backup at:', database.backup_sqlite_db())"
```

### Export Portable PostPilot Archive
Creates a self-contained `.zip` archive containing all posts, safe settings, and media files:
```powershell
python backup.py export
```

### Import Portable PostPilot Archive
Restores posts and media from a portable `.zip` backup:
```powershell
python backup.py import --input data/backups/postpilot_backup_YYYYMMDD_HHMMSS.zip
```

---

## 4. Key Architectural Patterns for Local Dev

1. **No Hardcoded Absolute Paths**: All paths are resolved relative to `config.BASE_DIR` or loaded from environment variables (`POSTPILOT_DATA_DIR`, `POSTPILOT_UPLOAD_FOLDER`).
2. **Stable Primary-Key CRUD**: Posts are queried, updated, and deleted by integer `id` (`/api/posts/<post_type>/<id>`), not fragile array indices.
3. **Multi-Worker Database Coordination**: Background task state is stored in the `task_state` table in `posts.db`. In-process memory is never required for state persistence.
4. **Security Enforcement**: State-altering endpoints (`POST`, `PUT`, `DELETE`) require a valid session CSRF token. Remote LAN requests are blocked unless authenticated.
