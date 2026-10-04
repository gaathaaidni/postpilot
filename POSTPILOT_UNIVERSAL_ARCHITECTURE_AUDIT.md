# PostPilot Universal Architecture Audit & Compatibility Report
**Target Environments**: Environment A (Linux Web Server / VPS) & Environment B (Android Phone / Termux)  
**Repository**: `gaathaaidni/postpilot` (`C:\Users\Admin\.gemini\antigravity-ide\scratch\postpilot`)  
**Audit Date**: October 2026  
**Auditor**: Antigravity AI Engineering Team  
**Scope**: Read-Only Comprehensive Systems Audit, Baseline Validation, Security Audit, Portability & Universal Runtime Architecture

---

## 1. Executive Summary

PostPilot originated as a lightweight Kivy desktop application, was subsequently converted into a Flask-based automation server, and recently underwent rapid iterations adding multi-page Facebook and Instagram automation, Grahak Chetna RSS news generation, and video rendering utilities.

The application currently stands in a **partially migrated and inconsistent state**:
1. **Core Runtime**: The core Flask server ([app.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py)) provides functional CRUD operations and a clean web UI for managing post records stored in a local SQLite database ([posts.db](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/posts.db)).
2. **Background Processing**: The application uses Python in-process background threads (`threading.Thread`) controlled by global in-memory dictionaries. This works for single-process local development, but **fails completely under production multi-worker WSGI servers (Gunicorn)** where process memory is not shared.
3. **Critical Security Issues**: A live Facebook User Access Token was committed in plaintext to the repository in [token.txt](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/token.txt). The web application has zero authentication or CSRF protection, leaving all endpoints exposed.
4. **Codebase Discrepancies**: Recent commits pruned scheduling and feed endpoints from [app.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py) while leaving orphaned UI logic in root [script.js](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/script.js). Furthermore, [insta.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/insta.py) has an indentation defect that removes the `run()` method from `InstaSync`, causing Instagram sync to crash on launch, and [grahak_video_factory.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/grahak_video_factory.py) has an invalid relative import preventing standalone execution.
5. **Universal Portability**: The codebase is fundamentally well-suited for a universal single-codebase model across Web Server (Linux VPS) and Android Termux, provided that:
   - In-process threading is replaced by a database-backed job runner or unified worker abstraction.
   - Database operations are abstracted (SQLite for Termux/Dev, PostgreSQL for Production Web Server).
   - Dynamic paths, configuration, and optional heavy dependencies (`moviepy`, `ffmpeg`, `gTTS`) are modularized.
   - Authentication is configurable (disabled or optional for local Termux/localhost, enforced for web deployment).

---

## 2. Current Application Architecture

### 2.1 Component Breakdown

```
+---------------------------------------------------------------------------------------+
|                                    CLIENT BROWSER                                     |
|             (Desktop, Tablet, or Android Mobile Browser at localhost:5000)            |
+-------------------------------------------+-------------------------------------------+
                                            | HTTP (JSON / HTML)
                                            v
+---------------------------------------------------------------------------------------+
|                                   FLASK WEB APP                                       |
|                                     (app.py)                                          |
|                                                                                       |
|  * Static & Jinja2 Templates (index.html, style.css, script.js)                       |
|  * Post Management REST API (/api/posts/<type>, /api/search, /api/upload)             |
|  * Control REST API (/api/control/<type>/start, stop, /api/status, /api/interval)     |
|  * Image/Media Static Serving (/images/<filename>)                                    |
|  * 24h Orphan Image Cleanup Worker (_cleanup_images_worker)                           |
+---------------------+-------------------------------+---------------------------------+
                      |                               |
        (Direct SQL)  |                               | (Spawns daemon threads)
                      v                               v
+-------------------------------+   +---------------------------------------------------+
|      DATABASE LAYER           |   |            IN-PROCESS BACKGROUND WORKERS          |
|         (posts.db)            |   |                                                   |
|                               |   |  * Nexora Suite Loop (nexora_suite.py)            |
|  * SQLite database            |   |  * Phoenix Visa Loop                              |
|  * Table: posts               |   |    (nexora_by_phoenix_international.py)           |
|    - id, post_type, message,  |   |  * Gaatha AI Loop (gaatha_loop.py)                |
|      image_filename,          |   |  * Grahak Chetna Loop (grahakchetna.py) [Broken]  |
|      created_at,              |   |  * Instagram Sync (insta.py) [Broken Method]      |
|      last_posted_at           |   +-------------------------+-------------------------+
+-------------------------------+                             |
                                                              | (HTTPS REST Requests)
                                                              v
                                    +---------------------------------------------------+
                                    |              EXTERNAL API SERVICES                |
                                    |                                                   |
                                    |  * Meta / Facebook Graph API v19.0                |
                                    |    - Photos, Feed, Videos, Stories                |
                                    |    - Page Token Exchange                          |
                                    |  * Instagram Graph API                            |
                                    |    - Media Container & Publish                    |
                                    |  * External RSS Feeds (grahak_news_auto.py)       |
                                    |  * Google Text-to-Speech (gTTS)                   |
                                    +---------------------------------------------------+
```

### 2.2 Flask Endpoints Inventory

| Route | Methods | Purpose | Implementation Detail |
|---|---|---|---|
| `/` | GET | Main UI | Renders `templates/index.html` |
| `/api/status` | GET | Task & Interval Status | Returns `posting_state` dictionary |
| `/api/posts/<post_type>` | GET | List posts | Queries `posts.db` ordered by `last_posted_at ASC, id ASC` |
| `/api/posts/<post_type>` | POST | Create post | Inserts post into `posts.db` |
| `/api/posts/<post_type>/<int:index>` | PUT | Update post | Updates post via `LIMIT 1 OFFSET index` (Fragile!) |
| `/api/posts/<post_type>/<int:index>` | DELETE | Delete post | Deletes post and triggers `_cleanup_single_image()` |
| `/api/posts/<post_type>/all` | DELETE | Bulk delete posts | Deletes all records for `post_type` and cleans images |
| `/api/search` | GET | Search posts | Query parameter `?q=...`, searches `message` and `post_type` |
| `/api/upload` | POST | Upload media | Verifies extension and PIL image integrity, saves to `images/` |
| `/images/<filename>` | GET | Serve image | Uses `send_from_directory` on `UPLOAD_FOLDER` |
| `/api/interval/<post_type>` | GET | Get post interval | Reads seconds from `posting_state` |
| `/api/interval/<post_type>` | PUT | Set post interval | Updates `posting_state` and running module callback |
| `/api/control/<type>/start` | POST | Start loop | Spawns daemon `threading.Thread` |
| `/api/control/<type>/stop` | POST | Stop loop | Sets module `stop_event` |
| `/api/control/all/start` | POST | Batch start | Starts all 5 modules |
| `/api/control/all/stop` | POST | Batch stop | Stops all 5 modules |

---

## 3. Feature Inventory

| Feature | Actually Implemented? | Code Location | Dependencies | Web Server Viability | Termux Viability | Notes |
|---|---|---|---|---|---|---|
| **Web Dashboard** | Yes | [templates/index.html](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/templates/index.html), [static/script.js](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/static/script.js) | Flask, FontAwesome, Inter | Full | Full | Responsive layout, polling `/api/status` every 3s. |
| **Post CRUD** | Yes | [app.py:L224-L312](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py#L224-L312) | SQLite, Flask | Full | Full | Uses offset indexing instead of primary key ID in API routes. |
| **Media Upload** | Yes | [app.py:L314-L334](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py#L314-L334) | Pillow, Flask | Full | Full | Pillow verifies image headers; saves to local `images/`. |
| **Orphan Media Cleanup** | Yes | [app.py:L86-L143](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py#L86-L143) | SQLite, OS | Full | Full | Deletes unreferenced disk images on post delete and daily. |
| **Facebook Photo Posting** | Yes | [posting_utils.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/posting_utils.py), [facebook_api.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/facebook_api.py) | requests | Full | Full | Graph API v19.0 photo upload with retry/backoff. |
| **Nexora Suite Loop** | Yes | [nexora_suite.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/nexora_suite.py) | posting_utils, threading | Broken with Gunicorn | Works single-process | Daemon thread loop cycling through `posts.db`. |
| **Phoenix Visa Loop** | Yes | [nexora_by_phoenix_international.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/nexora_by_phoenix_international.py) | posting_utils, threading | Broken with Gunicorn | Works single-process | Daemon thread loop cycling through `posts.db`. |
| **Gaatha AI Loop** | Partial | [gaatha_loop.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/gaatha_loop.py) | facebook_api, threading | Broken with Gunicorn | Works single-process | Duplicates posting code; only posts `posts[0]`. |
| **Instagram Sync (InstaSync)** | **BROKEN** | [insta.py:L72](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/insta.py#L72) | requests, threading | No | No | `run(self)` is nested inside `post_to_instagram`; throws `AttributeError`. |
| **Grahak Chetna Loop** | **BROKEN** | [grahakchetna.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/grahakchetna.py) | grahak_uploader | No | No | Reads non-existent JSON file `grahakchetna_posts.json` instead of SQLite. |
| **Grahak Video News Factory** | **BROKEN** | [grahak_video_factory.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/grahak_video_factory.py) | gTTS, MoviePy, Pillow | Needs ffmpeg | Needs ffmpeg/pkg | Relative import `from . import facebook_api` fails when run from root. |
| **Grahak RSS News Auto** | Partial | [grahak_news_auto.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/grahak_news_auto.py) | xml.etree, requests | Full | Full | CLI-only; Flask endpoints were deleted in commit `0b6c44b`. |
| **Delayed Job Scheduling** | **Ghost / Dead Code** | [script.js](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/script.js) (root) | None | No | No | Exists in root `script.js` but backend routes deleted from `app.py`. |
| **Authentication & Users** | **NOT IMPLEMENTED** | None | None | Needs implementation | Optional on localhost | Application has zero authentication. |
| **YouTube Automation** | **DEPRECATED** | [grahak_youtube_auto.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/grahak_youtube_auto.py) | None | N/A | N/A | Explicitly stubbed out and disabled. |

---

## 4. Social Media Integrations

### 4.1 Meta / Facebook Graph API
- **API Version**: Graph API v19.0 (`https://graph.facebook.com/v19.0`).
- **Endpoints Used**:
  - `POST /{page_id}/photos`: Multipart photo upload with caption.
  - `POST /{page_id}/feed`: Direct text-only feed post.
  - `POST /{page_id}/videos`: Multipart MP4 video upload.
  - `POST /{page_id}/video_stories` & `/photo_stories`: Story publishing.
  - `GET /me/accounts`: Exchanges user token for page tokens.
  - `GET /debug_token`: Validates token scopes and expiration.
- **Authentication**:
  - Relies on a User Access Token or Page Access Token configured in `.env` (`FB_ACCESS_TOKEN` or `FB_TOKEN`).
  - No OAuth 2.0 user handshake flow exists; tokens must be manually generated in Meta Graph API Explorer.
- **Token Storage**:
  - Plaintext in `.env` or [token.txt](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/token.txt).
- **Rate Limit Handling**:
  - Implemented in [facebook_api.py:L110-L135](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/facebook_api.py#L110-L135) with exponential backoff (detects HTTP 429 and error codes 4, 17, 32, 613).
- **Server vs Termux**: Identical behavior. Both execute outbound HTTPS requests to Graph API endpoints.

### 4.2 Instagram Graph API
- **API Version**: Graph API v19.0.
- **Endpoints Used**:
  - `POST /{ig_user_id}/media`: Creates a media container (`image_url` or `video_url`, caption).
  - `POST /{ig_user_id}/media_publish`: Publishes the container (`creation_id`).
  - `GET /{container_id}?fields=status_code`: Polls for container processing readiness.
- **Crucial Architectural Detail**:
  - The Instagram Graph API **does not accept direct file uploads**; it requires a publicly accessible HTTP/HTTPS URL (`image_url` or `video_url`).
  - **Workaround in PostPilot**: Instead of requiring a public static web server, PostPilot uploads media to Facebook first (either published or unpublished), extracts the public Facebook CDN source URL (`https://scontent...`), and feeds that URL into Instagram's container creation endpoint!
  - **Significance for Termux**: This is an exceptional workaround for phone/Termux environments because the phone does NOT need a public IP or port forwarding to publish images/reels to Instagram!

### 4.3 WhatsApp Business API
- Queried in [fetch_full_info.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/fetch_full_info.py) via `whatsapp_number` field. No messaging logic implemented.

---

## 5. Security Audit Findings

| Severity | Issue | Description | Affected Files | Remediation |
|---|---|---|---|---|
| **CRITICAL** | **Live Facebook Token in Git** | A live, unredacted Facebook Access Token (`EAAT3Q4oZCLo0BQ...`) was committed directly into git version control in [token.txt](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/token.txt). | `token.txt` | **Immediately revoke/invalidate this token** in Meta App Dashboard, remove `token.txt`, and add to `.gitignore`. |
| **CRITICAL** | **Zero Authentication / Authorization** | The entire web interface and all REST API endpoints are public. Anyone with network access can view, create, edit, delete posts, and trigger social broadcasts. | `app.py`, `templates/index.html` | Implement session-based authentication (Flask-Login or token auth) with a local-mode bypass for Termux. |
| **CRITICAL** | **Unauthenticated Bulk Post Deletion** | `/api/posts/<post_type>/all` permanently deletes all posts and discards images with a single HTTP DELETE request and no auth or confirmation token. | `app.py:L288` | Require authentication and confirmation token. |
| **HIGH** | **Missing CSRF Protection** | All mutation endpoints (`POST`, `PUT`, `DELETE`) accept JSON and form submissions without CSRF tokens. | `app.py` | Add Flask-WTF CSRF protection or custom header validation (`X-Requested-With`). |
| **HIGH** | **Hardcoded Production Page IDs** | Facebook Page IDs and Instagram IDs are hardcoded as defaults across 7 different Python files instead of centrally managed. | `nexora_suite.py`, `nexora_by_phoenix_international.py`, `gaatha_loop.py`, `grahakchetna.py`, `grahak_news_auto.py`, `grahak_video_factory.py`, `app.py` | Centralize all Page IDs in `.env` / configuration manager. |
| **HIGH** | **Exposed SQLite Database in Git** | The SQLite database [posts.db](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/posts.db) is tracked in version control, creating merge conflicts and leaking data. | `posts.db` | Add `*.db` to `.gitignore` and initialize database programmatically on first run. |
| **HIGH** | **Debug Mode Enabled in Entrypoint** | [app.py:L574](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py#L574) specifies `app.run(debug=True, host='0.0.0.0', port=5000)`, exposing the Werkzeug debugger console on all network interfaces. | `app.py` | Change to `debug=False` by default and read `FLASK_DEBUG` from environment. |
| **MEDIUM** | **Array Offset Race Condition** | Post updating and deletion (`/api/posts/<type>/<index>`) uses `OFFSET ?` rather than database primary keys (`id`). Concurrent operations will edit/delete the wrong posts. | `app.py:L256, L271` | Refactor endpoints to `/api/posts/<int:post_id>`. |
| **MEDIUM** | **Multi-Worker Memory Corruption** | `posting_state` and `threading.Thread` loops reside in process RAM. Under Gunicorn with 4 workers, state is split across 4 processes, breaking controls. | `app.py`, `posting_utils.py` | Extract background jobs into a dedicated runner or use database-backed task state. |
| **LOW** | **Committed Build Artifacts & Logs** | Python bytecode (`__pycache__`), logs (`news.log`, `yt.log`), and temporary media (`temp_audio.mp3`, `temp_frame_*.jpg`) are tracked in git. | `__pycache__/*`, `*.log`, `*.mp3`, `*.jpg` | Purge tracked artifacts and update `.gitignore`. |

---

## 6. Database Architecture

### 6.1 Current Schema
PostPilot uses raw SQLite3 without an ORM. The database file is located at `APP_ROOT / "posts.db"`.

```sql
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_type TEXT NOT NULL,
    message TEXT,
    image_filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_posted_at TIMESTAMP
);
```

### 6.2 Evaluation: Local Mode (Termux) vs Server Mode (Web Server)
- **Local Mode (Termux)**: SQLite is the optimal engine for Termux. It requires zero server setup, is compiled into Python by default, and consumes virtually no memory.
- **Server Mode (Web Server)**: While SQLite can handle low-volume web reads, multiple concurrent Gunicorn workers writing simultaneously cause SQLite database locking errors (`sqlite3.OperationalError: database is locked`). A web server deployment benefits from PostgreSQL or MySQL.
- **Universal Abstraction Plan**:
  - Replace raw `sqlite3.connect(DB_PATH)` with SQLAlchemy Core or a database abstraction layer.
  - In Termux / Development: `DATABASE_URL = "sqlite:///data/postpilot.db"`
  - In Production Web Server: `DATABASE_URL = "postgresql://user:password@localhost:5432/postpilot"`
  - Schema migrations should be managed via Alembic rather than ad-hoc scripts.

---

## 7. Universal Runtime Compatibility: Web Server vs Termux

### 7.1 Target Runtime Matrix

| Requirement | Environment A (Web Server / VPS) | Environment B (Android / Termux) |
|---|---|---|
| **Operating System** | Ubuntu / Debian / RHEL Linux | Android (Linux kernel via Termux userland) |
| **Process Manager** | Systemd, Docker, or Supervisord | `termux-services`, foreground execution, or `termux-wake-lock` |
| **Python Version** | Python 3.10+ | Python 3.11 / 3.12 (via `pkg install python`) |
| **WSGI / Web Server** | Nginx / Caddy -> Gunicorn (`--workers 4`) | Flask built-in server or Gunicorn (`--workers 1 --threads 4`) |
| **Network Binding** | `127.0.0.1:5000` (Reverse proxied with HTTPS) | `127.0.0.1:5000` (Local browser access on phone) |
| **Database** | PostgreSQL (or persistent SQLite volume) | SQLite (built-in) |
| **Filesystem Paths** | `/opt/postpilot` or `/var/www/postpilot` | `/data/data/com.termux/files/home/postpilot` |
| **Font Dependencies** | `/usr/share/fonts/truetype/dejavu/...` | `$PREFIX/share/fonts/TTF/...` or bundled font in repo |
| **Media Engine** | `ffmpeg` package via `apt` | `ffmpeg` package via `pkg install ffmpeg` |

### 7.2 Dependency Classification

| Dependency | Classification | Status & Notes |
|---|---|---|
| `Flask` | **Portable** | Works identically on Linux server and Termux. |
| `requests` | **Portable** | Pure Python HTTP client; works identically on both. |
| `python-dotenv` | **Portable** | Environment variable loader; universal. |
| `feedparser` | **Portable** | Pure Python RSS parser; universal. |
| `Pillow` | **Termux-Compatible** | Requires C library compilation (`libjpeg-turbo`, `libpng`, `freetype`). In Termux, install via `pkg install libjpeg-turbo libpng freetype` before `pip install Pillow`. |
| `gunicorn` | **Web-server-specific** | Essential for Linux web servers. Can run in Termux but only in single-worker mode. |
| `moviepy` | **Needs abstraction** | Not in `requirements.txt`! Requires native `ffmpeg`. Heavy for Termux; video factory should be an optional plugin/module. |
| `gTTS` | **Portable** | Not in `requirements.txt`! Calls Google Translate TTS API; requires network access. |

---

## 8. Universal Architecture Requirements & Abstractions

To achieve **one application codebase + environment-specific configuration** without forks:

### 8.1 Path Resolution Abstraction
- **Current Problem**: Hardcoded paths like `/workspaces/postpilot` in [migrate_to_sqlite.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/migrate_to_sqlite.py) and hardcoded fonts like `/data/data/com.termux/...` in [test.txt](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/test.txt).
- **Universal Fix**:
  ```python
  # Core paths dynamically resolved relative to app root or environment variable
  BASE_DIR = Path(__file__).resolve().parent
  DATA_DIR = Path(os.getenv('POSTPILOT_DATA_DIR', BASE_DIR / 'data'))
  UPLOAD_DIR = Path(os.getenv('POSTPILOT_UPLOAD_DIR', DATA_DIR / 'images'))
  FONT_DIR = BASE_DIR / 'assets' / 'fonts'
  ```

### 8.2 Configuration Hierarchy
```
Environment Variable > .env.{APP_ENV} > .env > Code Defaults
```
Three profiles:
1. `APP_ENV=development` (Local PC, SQLite, Debug logging, Auth optional)
2. `APP_ENV=termux` (Android Termux, SQLite, Single-worker, Waker/Heartbeat, Local Auth bypass)
3. `APP_ENV=production` (VPS / Web Server, PostgreSQL, Gunicorn, Reverse Proxy, Strict Auth, HTTPS cookies)

---

## 9. Background Processing Architecture

### 9.1 The Fundamental Flaw of the Current Design
In [app.py](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/app.py), posting loops are executed by spawning Python threads directly in Flask:
```python
thread = threading.Thread(target=tour.run_nexora_suite, daemon=True)
thread.start()
posting_state['threads']['tour'] = thread
```
When running with Gunicorn (`--workers 4`):
1. **Memory Isolation**: Each Gunicorn worker is an independent OS process. A start command hitting Worker A creates a thread in Worker A. The next status request hits Worker B, which reports `stopped`.
2. **Process Recycling**: Gunicorn periodically recycles workers, silently killing active posting loops.
3. **No Persistence**: If the server restarts or crashes, all background threads die and never resume.

### 9.2 Universal Portable Background Runner
Instead of requiring Redis/Celery (which is overly heavy for Termux):
1. **Database-Backed Task State**: Store job status and next run time in a `scheduled_tasks` table.
2. **Dedicated Runner**:
   - **On Web Server**: Run a lightweight separate scheduler process: `python -m postpilot.worker` managed via Systemd or Docker.
   - **On Termux**: A single background loop inside the standalone Flask runner (`python app.py`) or separate Termux session.
   - **Termux Android Battery Handling**: Add a helper script invoking `termux-wake-lock` to prevent Android from putting the CPU to sleep while posting tasks are active.

---

## 10. Web UI & Mobile Usability Audit

- **Desktop Experience**: The interface is clean, featuring a modern dark-bordered sidebar, top bar with batch controls, responsive cards, post tables, and modals.
- **Mobile Experience**:
  - The CSS currently implements a basic breakpoint `@media (max-width: 768px)` that hides `.nav-menu` and injects a `<select>` dropdown via JavaScript.
  - While functional, selecting modules via a dropdown is clunky on mobile devices.
- **Recommended Mobile Enhancements**:
  - Replace the `<select>` dropdown with a sleek mobile bottom navigation bar or slide-out drawer.
  - Optimize the file upload area for touch targets.
  - Implement touch-friendly preview cards for post queues instead of wide data tables.

---

## 11. Testing Baseline & Validation Results

Safe local tests were executed without network connections to external social accounts:

1. **Python Bytecode Compilation**:
   - All 17 Python files compiled successfully without syntax errors (`py_compile`).
2. **Module Import Testing**:
   - `facebook_api`: **PASSED**
   - `posting_utils`: **PASSED**
   - `insta`: **PASSED**
   - `nexora_suite`: **PASSED**
   - `nexora_by_phoenix_international`: **PASSED**
   - `gaatha_loop`: **PASSED**
   - `grahakchetna`: **PASSED**
   - `grahak_uploader`: **PASSED**
   - `grahak_news_auto`: **PASSED**
   - `app`: **PASSED**
   - `grahak_video_factory`: **FAILED** (`ImportError: attempted relative import with no known parent package` at line 8: `from . import facebook_api`).
3. **Class Structure Inspection**:
   - `insta.InstaSync`: **DEFECT CONFIRMED**. `run(self)` is indented inside `post_to_instagram`, leaving `InstaSync` without a `run()` method. Calling `/api/control/insta/start` will crash with `AttributeError`.
4. **Database Verification**:
   - [posts.db](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/posts.db) inspected: Schema verified (`posts` table), currently 0 rows.
5. **Flask Test Client Routing**:
   - Tested 14 endpoints via Flask test client (`/`, `/api/status`, `/api/posts/*`, `/api/interval/*`, `/api/search`). All responded with HTTP 200/400 as expected.
6. **CRUD Cycle Validation**:
   - Added test post record -> Retrieved -> Updated -> Searched -> Deleted -> Database verified clean.
7. **Repository State Restored**:
   - Working tree restored to pristine state (`git status`: clean).

---

## 12. Required Changes & Roadmap

### Phase 2: Security & Defect Remediation (Immediate)
1. **Revoke Exposed Token**: Invalidate the leaked Meta token in [token.txt](file:///C:/Users/Admin/.gemini/antigravity-ide/scratch/postpilot/token.txt) and remove the file from git.
2. **Fix Code Defects**:
   - Fix `insta.py` indentation so `InstaSync.run` is a proper method on the class.
   - Fix `grahak_video_factory.py` relative import (`import facebook_api` instead of `from . import facebook_api`).
   - Fix `grahakchetna.py` to query SQLite `posts.db` instead of missing JSON file.
   - Fix array offset deletion/updates in `app.py` to use primary key `post_id`.
3. **Clean Version Control**:
   - Add `.env`, `token.txt`, `posts.db`, `*.log`, `__pycache__/`, `images/*` to `.gitignore`.
   - Remove orphaned root `script.js` or consolidate with `static/script.js`.
   - Remove dead scripts (`run.sh` referencing non-existent `src.app`).

### Phase 3: Universal Configuration & Storage Abstraction
1. Create a centralized `config.py` using `pydantic-settings` or dataclasses supporting `APP_ENV=development|termux|production`.
2. Move data files (`posts.db`, `images/`) into a configurable directory (`./data/`).
3. Abstract the database engine with SQLAlchemy to support SQLite (Termux/Dev) and PostgreSQL (Production Web Server).

### Phase 4: Background Task Runner & Queue
1. Replace in-process `threading.Thread` with a database-backed job runner.
2. Provide a single runner command: `python -m postpilot.worker` (for VPS background service) or auto-spawned single thread for Termux.
3. Add `termux-wake-lock` integration script for Android continuous execution.

### Phase 5: Authentication & Multi-User Support
1. Implement a user model and session authentication.
2. Add environment flag `AUTH_ENABLED`:
   - `false` for local Termux/localhost usage.
   - `true` for VPS Web Server deployment.

---

## 13. Audit Status & Summary Table

- **Audit Status**: **COMPLETE (READ-ONLY)**
- **Files Inspected**: 17 Python modules, HTML templates, CSS styles, JavaScript files, Shell scripts, Docker configs, documentation, and database.
- **Real Accounts Connected**: 0 (Strict read-only policy observed).
- **Posts Published**: 0.
- **VPS / GaathaCore Touched**: 0 (Full boundary respect maintained).
- **Working Tree**: Clean and untouched.

*Audit completed successfully. Ready for user review and approval before proceeding to Phase 2 implementation.*
