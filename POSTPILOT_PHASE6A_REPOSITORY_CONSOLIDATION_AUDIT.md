# PostPilot Phase 6A — Repository Consolidation & Legacy Code Audit

**Repository**: `gaathaaidni/postpilot`  
**Execution Context**: Universal Single-Codebase Architecture (Windows Development, Android/Termux, Linux Production VPS)  
**Date**: October 3, 2026  
**Status**: Completed (Read-Only Audit — Zero Files Deleted, Zero Commits, Zero VPS Modifications)  

---

## 1. Executive Summary

Phase 6A provides a thorough, non-destructive audit of the entire PostPilot repository to map its actual working architecture, trace legacy code paths, identify unused utilities, assess worker concurrency patterns, and prepare a prioritized roadmap for repository consolidation.

### Key Audit Highlights:
1. **Architecture Status**: The application is successfully consolidated around a single authoritative database abstraction (`database.py`) and a single authoritative Meta API client (`facebook_api.py`).
2. **Grahak Chetna Complete Absence**: Verified **0 active lines, imports, routes, templates, or scripts** referencing Grahak Chetna.
3. **Legacy Code Identification**:
   - `nexora_suite.py`, `nexora_by_phoenix_international.py`, and `gaatha_loop.py` are thin wrapper modules around `posting_utils.py` that currently serve active post types (`tour`, `nz`, `gaatha`).
   - `migrate_to_sqlite.py` and `posts/*.json` are obsolete historical artifacts.
   - `Connected pages` is an unreferenced text dump from a previous developer diagnostic run.
   - `feedparser` in `requirements.txt` is an orphaned dependency from the removed Grahak Chetna RSS feed reader.
4. **Safety Compliance**: **Zero files deleted, zero git commits, zero git pushes, zero production VPS changes, and zero access tokens injected or logged.**

---

## 2. Current PostPilot Architecture Map

The actual running architecture of PostPilot across its three supported runtimes is mapped below:

```
                            POSTPILOT RUNTIMES
  ┌─────────────────────────┬─────────────────────────┬─────────────────────────┐
  │  Windows Development    │     Android / Termux    │   Linux Server / VPS    │
  │  Flask Dev Server       │   Flask Local Mode      │  Gunicorn (app:app)     │
  │  127.0.0.1:5000         │   127.0.0.1:5000        │  127.0.0.1:5000 (Nginx) │
  │  SQLite (WAL Mode)      │   SQLite (WAL Mode)     │  PostgreSQL / SQLite    │
  └────────────┬────────────┴────────────┬────────────┴────────────┬────────────┘
               │                         │                         │
               ▼                         ▼                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                           PRESENTATION LAYER                                │
  │  Templates: templates/index.html (Dashboard), templates/login.html (Auth)   │
  │  Static: static/script.js (SPA UI + authFetch), static/style.css (Dark CSS) │
  └──────────────────────────────────────┬──────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                           APPLICATION CORE (app.py)                         │
  │  - Middleware: login_required (auto-auth on 127.0.0.1 if dev), csrf_protect │
  │  - Primary-Key REST API: /api/posts/<type>, /api/control/<type>, /api/status│
  │  - Media Service: /api/upload (PIL integrity verify), /images/<filename>    │
  └──────────────────────┬───────────────────────────────┬──────────────────────┘
                         │                               │
                         ▼                               ▼
  ┌───────────────────────────────┐     ┌───────────────────────────────────────┐
  │       DATABASE LAYER          │     │          WORKER & TASK LAYER          │
  │         (database.py)         │     │     posting_utils.py / worker.py      │
  │  - Unified DBConnectionWrapper│     │  - Threading loops (Dev / Termux)     │
  │  - Dialect Translation (?->%s)│     │  - Standalone daemon (Production)     │
  │  - Primary Keys & Timestamps  │     │  - Task State in DB (task_state)      │
  │  - Passwords: PBKDF2/SHA-256  │     │  - Modules: tour, nz, gaatha, insta   │
  │  - Portable Backup: backup.py │     │  - Responsive stop: stop_event.wait() │
  └───────────────────────────────┘     └───────────────────┬───────────────────┘
                                                            │
                                                            ▼
                                        ┌───────────────────────────────────────┐
                                        │          META INTEGRATION LAYER       │
                                        │            (facebook_api.py)          │
                                        │  - Graph API v19.0 Client             │
                                        │  - Exponential backoff & retry        │
                                        │  - Token exchange: User -> Page token │
                                        │  - Instagram container publishing     │
                                        │  - Environment secret: FB_ACCESS_TOKEN│
                                        └───────────────────────────────────────┘
```

---

## 3. Comprehensive File Audit & Classification

### A. Currently Modified Working Tree Files

| File | Classification | Referenced By | Purpose | Action |
| :--- | :--- | :--- | :--- | :--- |
| `.env.example` | **CURRENT / REQUIRED** | Documentation, Setup scripts | Environment configuration template with empty placeholders | **KEEP** |
| `Connected pages` | **LEGACY AND UNREFERENCED** | None (terminal output dump) | Plaintext listing of historical page IDs and names; zero runtime code references | **POSSIBLY REMOVE** |
| `ERROR_ANALYSIS.md` | **DOCUMENTATION** | Documentation | Token debugging and root-cause analysis guide | **KEEP** |
| `FLASK_README.md` | **DOCUMENTATION** | Documentation | Legacy Flask instructions | **REVIEW** (Consolidate into README.md) |
| `QUICKSTART.md` | **DOCUMENTATION** | Documentation | Quickstart guide | **REVIEW** (Consolidate into README.md) |
| `README.md` | **DOCUMENTATION** | Repository entry point | Primary project documentation | **KEEP** |
| `app.py` | **CURRENT / REQUIRED** | WSGI, Web UI, Test suites | Main Flask web application, routing, auth, and API controllers | **KEEP** |
| `config.py` | **CURRENT / REQUIRED** | All runtime & test modules | Centralized configuration, path resolution, and env loading | **KEEP** |
| `facebook_api.py` | **CURRENT / REQUIRED** | `posting_utils.py`, `insta.py`, Tests | Authoritative Meta Graph API client (v19.0) with retry and token exchange | **KEEP** |
| `fetch_fb_info.py` | **CURRENT / OPTIONAL** | None (CLI utility) | Standalone CLI script to inspect accessible Facebook pages and IG accounts | **KEEP** |
| `fetch_full_info.py` | **CURRENT / OPTIONAL** | None (CLI utility) | Extended developer CLI inspection tool for Meta Graph API entities | **KEEP** |
| `gaatha_loop.py` | **LEGACY BUT REFERENCED** | `app.py`, `worker.py`, `smoke_test.py` | Wrapper loop for `gaatha` post type calling `posting_utils.py` | **REVIEW** (Migrate to unified engine) |
| `insta.py` | **LEGACY BUT REFERENCED** | `app.py`, `worker.py` | Instagram cross-posting loop; still uses flat file `posted.txt` for IDs | **REVIEW** (Migrate tracking to DB) |
| `migrate_to_sqlite.py` | **LEGACY AND UNREFERENCED** | None | One-time script to migrate legacy `posts/*.json` to database | **POSSIBLY REMOVE** |
| `nexora_by_phoenix_international.py` | **LEGACY BUT REFERENCED** | `app.py`, `worker.py`, `smoke_test.py` | Wrapper loop for `nz` post type calling `posting_utils.py` | **REVIEW** (Migrate to unified engine) |
| `nexora_suite.py` | **LEGACY BUT REFERENCED** | `app.py`, `worker.py`, `smoke_test.py` | Wrapper loop for `tour` post type calling `posting_utils.py` | **REVIEW** (Migrate to unified engine) |
| `posting_utils.py` | **CURRENT / REQUIRED** | `nexora_suite.py`, `nexora_by_phoenix...`, `gaatha_loop.py` | Core posting loop, DB update logic, and Facebook dispatch | **KEEP** |
| `requirements.txt` | **CURRENT / REQUIRED** | Setup, Pip, Virtualenv | Declares Python runtime dependencies | **REVIEW** (Remove unused `feedparser`) |
| `run-production.sh` | **CURRENT / REQUIRED** | VPS deployment | Production Gunicorn launcher | **REVIEW** (Bind 127.0.0.1 by default) |
| `run.sh` | **CURRENT / REQUIRED** | Local dev, Termux | Local development startup script | **KEEP** |
| `smoke_test.py` | **TESTING** | Test suite | Non-destructive module-by-module social smoke test | **KEEP** |
| `static/script.js` | **CURRENT / REQUIRED** | `templates/index.html` | Frontend SPA client logic, tab navigation, CSRF handling | **KEEP** |
| `static/style.css` | **CURRENT / REQUIRED** | `templates/index.html` | UI styling, responsive breakpoints, dark theme | **KEEP** |
| `templates/index.html` | **CURRENT / REQUIRED** | `app.py` | Main application dashboard template | **KEEP** |
| `verify_token.py` | **CURRENT / OPTIONAL** | None (CLI utility) | Standalone CLI script to validate `FB_ACCESS_TOKEN` against `/debug_token` | **KEEP** |

---

### B. Untracked Files

| File | Classification | Purpose | Action |
| :--- | :--- | :--- | :--- |
| `.gitignore` | **CURRENT / REQUIRED** | Ignores `.env`, `data/`, `backups/`, `*.pyc`, `images/` | **KEEP** |
| `DATA_EXPORT_IMPORT.md` | **DOCUMENTATION** | Documentation for cross-runtime export/import | **KEEP** |
| `LOCAL_DEVELOPMENT.md` | **DOCUMENTATION** | Guide for local Windows/macOS development | **KEEP** |
| `POSTPILOT_PHASE2_SECURITY_CLEANUP_REPORT.md` | **DOCUMENTATION** | Phase 2 historical security report | **KEEP** |
| `POSTPILOT_PHASE3_UNIVERSAL_RUNTIME_REPORT.md` | **DOCUMENTATION** | Phase 3 historical runtime report | **KEEP** |
| `POSTPILOT_PHASE4_LIVE_RUNTIME_REPORT.md` | **DOCUMENTATION** | Phase 4 historical runtime report | **KEEP** |
| `POSTPILOT_PHASE5_LIVE_INTEGRATION_REPORT.md` | **DOCUMENTATION** | Phase 5 historical integration report | **KEEP** |
| `POSTPILOT_UNIVERSAL_ARCHITECTURE_AUDIT.md` | **DOCUMENTATION** | Phase 1 baseline audit report | **KEEP** |
| `SERVER_DEPLOYMENT.md` | **DOCUMENTATION** | Guide for Linux VPS / Gunicorn deployment | **KEEP** |
| `TERMUX_SETUP.md` | **DOCUMENTATION** | Guide for Android / Termux local setup | **KEEP** |
| `backup.py` | **CURRENT / REQUIRED** | Portable backup and export/import utility | **KEEP** |
| `database.py` | **CURRENT / REQUIRED** | Core unified database abstraction (SQLite & PostgreSQL) | **KEEP** |
| `templates/login.html` | **CURRENT / REQUIRED** | User authentication login page template | **KEEP** |
| `test_clean_install.py` | **TESTING** | Clean installation & isolated venv test suite | **KEEP** |
| `test_meta_api.py` | **TESTING** | Meta Graph API test suite | **KEEP** |
| `test_multi_worker.py` | **TESTING** | Multi-process OS subprocess concurrency test suite | **KEEP** |
| `test_postgres_compatibility.py` | **TESTING** | PostgreSQL dialect, rollback & live check suite | **KEEP** |
| `test_production_config.py` | **TESTING** | Production configuration & security boundary suite | **KEEP** |
| `test_runtime_validation.py` | **TESTING** | 10-phase comprehensive application test suite | **KEEP** |
| `worker.py` | **CURRENT / REQUIRED** | Standalone production background worker daemon | **KEEP** |
| `worker_sim.py` | **TESTING** | Subprocess test worker for `test_multi_worker.py` | **KEEP** |

---

## 4. Legacy Code Findings (Nexora, Phoenix, Gaatha, Instagram)

### 1. Module Name Proliferation
* PostPilot currently maintains 3 nearly identical modules:
  * `nexora_suite.py` (47 lines): Defines `PAGE_ID` (FB_PAGE_ID_SUITE), `POST_TYPE="tour"`, sets interval, and calls `posting_utils.run_posting_loop(...)`.
  * `nexora_by_phoenix_international.py` (47 lines): Defines `PAGE_ID` (FB_PAGE_ID_PHOENIX), `POST_TYPE="nz"`, sets interval, and calls `posting_utils.run_posting_loop(...)`.
  * `gaatha_loop.py` (43 lines): Defines `PAGE_ID` (FB_PAGE_ID_GAATHA_AI), `POST_TYPE="gaatha"`, sets interval, and calls `posting_utils.run_posting_loop(...)`.
* **Finding**: These files are functional but represent duplicate boilerplate code. They can be unified in a subsequent phase into a single parameterized channel runner `channel_runner.py` or configured via `task_channels.py`.

### 2. Instagram Sync (`insta.py`) Flat-File Dependency
* `insta.py` implements `InstaSync` for cross-posting Facebook photos to Instagram.
* **Finding**: `insta.py` still reads and appends to a disk file named `posted.txt` (`get_posted_ids`, `save_posted_id`) to track which Facebook posts have already been synced. This is a legacy pattern that bypasses the database. In a subsequent phase, this tracking should be stored in a database table (e.g. `synced_posts` or `posts.last_posted_at`) so it survives cross-runtime backup and export.

### 3. Abandoned JSON Storage & One-Time Migration Script
* The directory `posts/` contains 4 files: `tour_posts.json`, `visa_posts.json`, `gaatha_posts.json`, `insta_posts.json` (all 2 bytes: `[]`).
* `migrate_to_sqlite.py` is a one-time migration utility that reads from `posts/` and inserts into the database.
* **Finding**: No active runtime code reads or writes to `posts/*.json`. All active posts are stored in SQLite (`data/posts.db`) or PostgreSQL. The directory `posts/` and `migrate_to_sqlite.py` are legacy and can be safely archived.

---

## 5. Meta & Instagram Architecture Audit

### Authoritative Implementation
- **Authoritative Client**: [facebook_api.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/facebook_api.py).
- **Graph API Version**: `v19.0` (declared in `FB_API_VERSION = "v19.0"`).
- **Base URL**: `https://graph.facebook.com/v19.0`.
- **Core Functions**:
  1. `get_access_token()`: Reads `FB_ACCESS_TOKEN` from `os.getenv` or parses local `.env`.
  2. `get_page_token(user_token, page_id)`: Calls `/me/accounts` to exchange a user token for a Page token.
  3. `get_token_info(token)`: Calls `/debug_token`.
  4. `_request_with_retry()`: Implements exponential backoff (retries 5 times for codes 4, 17, 32, 613, 429).
- **Posting Flow**:
  - `posting_utils.post_on_facebook()`:
    1. Obtains Page token via `facebook_api.get_page_token(access_token, page_id)`.
    2. Uploads image via `POST /{page_id}/photos` with `caption` and `access_token`.
    3. If photo upload succeeds, queries image metadata via `GET /{photo_id}?fields=images`.
- **Instagram Flow**:
  - `insta.post_to_instagram()`:
    1. Creates media container via `POST /{ig_user_id}/media`.
    2. Waits 5 seconds for media processing.
    3. Publishes container via `POST /{ig_user_id}/media_publish`.
- **Dead / Conflicting Code**:
  - `fetch_fb_info.py` and `fetch_full_info.py` duplicate queries to `/me` and `/me/accounts`. They do not conflict with the application because they are standalone CLI utilities, but they should eventually be consolidated into `verify_token.py` or `facebook_api.py`.

---

## 6. Database Architecture Audit

### Authoritative Implementation
- **Authoritative Layer**: [database.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/database.py).
- **Connection Wrapper**: `DBConnectionWrapper` wraps raw SQLite and `psycopg2` connections, providing uniform `execute()`, `commit()`, `rollback()`, and context manager semantics.
- **Dialect Abstraction**:
  - Parameter placeholders: SQLite `?` placeholders are dynamically rewritten to `%s` when connected to PostgreSQL.
  - Primary keys: Dynamically uses `INTEGER PRIMARY KEY AUTOINCREMENT` (SQLite) or `SERIAL PRIMARY KEY` (PostgreSQL).
  - Conflict handling: Uses `ON CONFLICT (task_name) DO NOTHING`.
- **Tables**:
  1. `users`: Stores admin credentials (`id`, `username`, `password_hash`, `role`, `created_at`).
  2. `posts`: Stores post records (`id`, `post_type`, `message`, `image_filename`, `created_at`, `last_posted_at`).
  3. `task_state`: Stores multi-worker automation states (`task_name`, `is_running`, `status`, `current_post_summary`, `interval_seconds`, `last_run_at`, `updated_at`).
- **Storage Bypass Check**:
  - `sqlite3.connect`: **0 occurrences** outside `database.py`.
  - `psycopg2.connect`: **0 occurrences** outside `database.py`.
  - `json.load` / `json.dump`: **0 occurrences** in active runtime database operations (used strictly in `backup.py` for archive packaging).

---

## 7. Worker & Task Architecture Audit

### Execution Models:
1. **Development & Termux Mode (`APP_ENV != 'production'`)**:
   - `app.py` manages background loops using in-process daemon threads (`_start_local_task`, `_stop_local_task`).
   - Threads are joined on stop with `th.join(timeout=1.0)` to eliminate race conditions.
2. **Production Server Mode (`APP_ENV == 'production'`)**:
   - `app.py` runs purely as a stateless REST API under Gunicorn.
   - Starting/stopping a task updates the database row `database.set_task_state(post_type, is_running=True)`.
   - A standalone daemon [worker.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/worker.py) polls the database every 3 seconds via `sync_tasks_with_db()`, spawning or terminating worker threads to match desired database state.
3. **Task Concurrency & State Persistence**:
   - Task state survives process restart because it is persisted in the database table `task_state`.
   - Responsive shutdown is achieved via `stop_event.wait(timeout=...)` in `posting_utils.py`.
4. **Architectural Observation**:
   - If both `app.py` (in dev mode) and `worker.py` are started simultaneously against the same database, both will run worker loops.
   - Recommendation: Add a simple worker process heartbeat/lease or guard in `app.py` so that in-process threads cannot run if a standalone `worker.py` daemon is registered.

---

## 8. Security & Secret Handling Audit

1. **Credentials Management**:
   - Meta access tokens are loaded exclusively via `os.getenv('FB_ACCESS_TOKEN')`.
   - Passwords are encrypted using `werkzeug.security.generate_password_hash` (PBKDF2 with SHA-256).
   - Session keys use `secrets.token_hex(32)`.
2. **Network & Session Protection**:
   - Requests from remote IPs strictly require authentication (`login_required`).
   - CSRF protection is enforced on all `POST`, `PUT`, `DELETE` requests using cryptographically secure 24-byte tokens.
   - Localhost auto-authentication is strictly restricted to `127.0.0.1` and disabled when `APP_ENV=production`.
3. **Secret Leakage Audit**:
   - `EAAT` / `EAAB`: 0 active code occurrences.
   - `token.txt`: 0 active code occurrences.
   - Backup archives: Inspected generated export zip; strictly free of `.env`, passwords, hashes, and tokens.

---

## 9. Grahak Chetna Final Audit

A comprehensive case-insensitive scan was performed across all active Python files, HTML templates, CSS files, JavaScript files, and shell scripts:
- `grahak`: **0 active occurrences**
- `grahakchetna`: **0 active occurrences**
- `grahak_chetna`: **0 active occurrences**
- `Grahak Chetna`: **0 active occurrences**
*(Matches are strictly confined to historical documentation reports explaining its removal in Phase 2).*

---

## 10. Static & Template Assets Audit

1. **`templates/index.html`**:
   - Clean, modern layout.
   - Accurately renders the 4 active post modules: Nexora Suite (`tour`), Phoenix Intl (`nz`), Gaatha AI (`gaatha`), Instagram Sync (`insta`).
   - Zero references to removed routes or obsolete products.
2. **`templates/login.html`**:
   - Standalone login interface.
   - Sends credentials via JSON `POST /api/auth/login`.
   - CSRF token embedded in meta tag and headers.
3. **`static/script.js`**:
   - All state modifications use `authFetch()` which automatically injects `X-CSRFToken`.
   - Handles session expiration by redirecting to `/login`.
   - Zero references to removed endpoints or legacy JSON endpoints.
4. **`static/style.css`**:
   - Modern dark-mode responsive styling with CSS variables.
   - Breakpoints at `< 768px` for mobile viewports.

---

## 11. Test Coverage Audit

| Test File | Type | Scope | Safety | Environment Requirements |
| :--- | :--- | :--- | :--- | :--- |
| `test_runtime_validation.py` | System / E2E | 10-Phase runtime validation (Auth, CSRF, CRUD, WAL, Persistence, Export/Import) | Non-destructive (Temp directory) | Windows, Linux, Termux |
| `test_multi_worker.py` | Integration | Multi-process OS concurrency (3 independent PIDs, WAL) | Non-destructive (Temp database) | Windows, Linux, Termux |
| `test_postgres_compatibility.py` | Unit / Integration | Dual-engine dialect translation, rollback, controlled failure, live check | Non-destructive (Temp database) | Windows, Linux, Termux (Live check pending server) |
| `test_meta_api.py` | Integration | Meta Graph API (/debug_token, /me, /me/accounts, scopes) | Non-destructive (Read-only metadata) | Windows, Linux, Termux (Live calls pending .env token) |
| `test_production_config.py` | Security / Config | Production security boundary (DEBUG=False, remote rejection, CSRF) | Non-destructive (Temp directory) | Windows, Linux, Termux |
| `test_clean_install.py` | Packaging | Clean install & dependency isolation in a fresh sandbox venv | Non-destructive (Temp sandbox) | Windows, Linux, Termux |
| `smoke_test.py` | Smoke | Module-by-module social smoke test | Non-destructive (Skipped if token unset) | Windows, Linux, Termux |

---

## 12. Dependency Audit (`requirements.txt`)

```text
Flask>=2.3.2                            # REQUIRED RUNTIME: Web application framework
requests>=2.31.0                        # REQUIRED RUNTIME: Meta Graph API HTTP client
Werkzeug>=2.3.6                         # REQUIRED RUNTIME: Password hashing & security
python-dotenv>=1.0.0                    # REQUIRED RUNTIME: Environment variable loader
feedparser>=6.0.11                      # OBSOLETE / UNREFERENCED: Orphan from Grahak Chetna RSS
Pillow>=10.0.0                          # REQUIRED RUNTIME: Image validation & handling
gunicorn>=21.2.0; sys_platform != 'win32' # PLATFORM-SPECIFIC: Production WSGI server (Linux)
```

- **Obsolete Dependency**: `feedparser` is not imported anywhere in active code. It was previously used by `grahak_news_auto.py` (deleted in Phase 2).
- **PostgreSQL Dependency**: When deploying to PostgreSQL, `psycopg2-binary>=2.9.9` is required. It should be documented or added as an optional extra.

---

## 13. Shell Scripts Audit

1. **`run.sh`**:
   - Sets `APP_ENV=development`.
   - Starts `python app.py` (which binds to `127.0.0.1:5000` by default).
   - Safe for local development and Termux.
2. **`run-production.sh`**:
   - Sets `APP_ENV=production`.
   - Invokes `gunicorn --workers 4 --bind 0.0.0.0:5000 app:app`.
   - **Security Observation**: Binds to `0.0.0.0:5000`. In a production setup behind Nginx, it is strongly recommended to bind to `127.0.0.1:5000` so that external visitors cannot bypass Nginx.

---

## 14. Audit of "Connected pages"

- **File Name**: `Connected pages` (space in filename, no extension).
- **File Type**: Plaintext diagnostic text file.
- **Contents**: A terminal output listing 5 connected Facebook pages and Instagram usernames (`Gaatha AI`, `Nexora by Phoenix International`, `Nexora Suite`, `sizzlecraft`, `Gaatha`).
- **Why Git Sees It Modified**: In Phase 2, entry `[5] Grahak Chetna` was purged from this file.
- **Reference Analysis**: It is **not imported, not read, and not referenced** by any Python code, HTML, CSS, JavaScript, or shell script in the repository.
- **Conclusion**: It is a legacy developer diagnostic dump. It should not remain tracked as active application code.

---

## 15. Prioritized Recommended Cleanup (For Future Phases)

> [!IMPORTANT]
> This phase is **AUDIT ONLY**. No files have been deleted, moved, or modified. The recommendations below are queued for user approval prior to execution in Phase 6B.

### HIGH PRIORITY:
1. **Remove Unused `feedparser`**: Remove `feedparser>=6.0.11` from `requirements.txt` to eliminate an unused dependency.
2. **Untrack `Connected pages`**: Remove `Connected pages` from git tracking and add to `.gitignore`.
3. **Hardened Production Binding**: Update `run-production.sh` to bind to `127.0.0.1:${PORT:-5000}` by default to prevent exposing Gunicorn directly to the public internet without Nginx.

### MEDIUM PRIORITY:
4. **Archive `posts/` Directory and `migrate_to_sqlite.py`**: Remove the abandoned `posts/*.json` directory and the one-time `migrate_to_sqlite.py` utility since SQLite/PostgreSQL is now the sole source of truth.
5. **Migrate Instagram Sync ID Tracking**: Update `insta.py` to record synced Facebook post IDs in the database instead of the flat file `posted.txt`.
6. **Consolidate Documentation**: Consolidate `FLASK_README.md` and `QUICKSTART.md` into the primary `README.md`.

### LOW PRIORITY:
7. **Consolidate Channel Boilerplate**: Refactor `nexora_suite.py`, `nexora_by_phoenix_international.py`, and `gaatha_loop.py` into a unified `channel_runner.py` to eliminate code duplication.
8. **Consolidate Diagnostic CLI Tools**: Merge `fetch_fb_info.py` and `fetch_full_info.py` into `verify_token.py`.
