"""
PostPilot Database Layer
Provides universal database abstraction supporting:
- Local Mode & Termux: SQLite (zero-config, WAL mode for multi-process concurrency)
- Server Mode: PostgreSQL or SQLite via standard DATABASE_URL

Features:
- Dual-engine support: SQLite and PostgreSQL (psycopg2)
- Unified Dict-like Row access across SQLite and PostgreSQL
- Unified parameter translation (? to %s for PostgreSQL)
- Posts CRUD (using stable primary key IDs)
- Users authentication storage with bcrypt/scrypt hashes
- Database-backed task state (safe for multi-worker WSGI servers)
- Safe live database backup mechanism
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import config

logger = logging.getLogger(__name__)

def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def is_postgres():
    """Detects whether DATABASE_URL specifies PostgreSQL."""
    db_url = config.DATABASE_URL.lower()
    return db_url.startswith(("postgresql://", "postgres://"))

def _get_sqlite_path():
    db_url = config.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        path_str = db_url.replace("sqlite:///", "")
        return Path(path_str)
    return config.DEFAULT_SQLITE_PATH

class DBConnectionWrapper:
    """
    Uniform database connection wrapper providing identical interface
    for both SQLite and PostgreSQL.
    """
    def __init__(self, raw_conn, is_pg=False):
        self._conn = raw_conn
        self._is_pg = is_pg

    def execute(self, sql, params=None):
        params = params or ()
        if self._is_pg:
            # Convert ? placeholders to %s for PostgreSQL psycopg2
            pg_sql = sql.replace('?', '%s')
            cur = self._conn.cursor()
            cur.execute(pg_sql, params)
            return cur
        else:
            return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            self.close()

def get_db_connection():
    """
    Returns a unified database connection with dict-like row access.
    Supports SQLite (with WAL mode) or PostgreSQL (via psycopg2).
    """
    if is_postgres():
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(config.DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
            return DBConnectionWrapper(conn, is_pg=True)
        except ImportError:
            raise RuntimeError("PostgreSQL configured but psycopg2 is not installed. Install psycopg2-binary.")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    else:
        sqlite_path = _get_sqlite_path()
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(sqlite_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent multi-process reads/writes in SQLite
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        return DBConnectionWrapper(conn, is_pg=False)

def init_db():
    """Initializes tables and seeds initial administrator and task states."""
    is_pg = is_postgres()
    auto_id = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    with get_db_connection() as conn:
        # 1. Posts table
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS posts (
                id {auto_id},
                post_type TEXT NOT NULL,
                message TEXT,
                image_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_posted_at TIMESTAMP
            )
        ''')
        
        # 2. Users table for authentication
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id {auto_id},
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. Task state table (decouples task state from in-process memory)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS task_state (
                task_name TEXT PRIMARY KEY,
                is_running INTEGER DEFAULT 0,
                status TEXT DEFAULT '',
                current_post_summary TEXT,
                interval_seconds INTEGER DEFAULT 1800,
                last_run_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 4. Worker leases table (ensures single active worker across processes)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS worker_leases (
                lease_name TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Synced posts table (replaces legacy posted.txt for Instagram cross-posting)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS synced_posts (
                post_id TEXT PRIMARY KEY,
                target_platform TEXT DEFAULT 'instagram',
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()

    # Seed default tasks if empty
    init_default_tasks()

    # Seed default admin user if none exists
    init_default_admin()

def init_default_tasks():
    """Ensures records exist in task_state for all active modules."""
    default_tasks = [
        ('tour', config.TOUR_INTERVAL),
        ('nz', config.VISA_INTERVAL),
        ('gaatha', config.GAATHA_INTERVAL),
        ('insta', config.INSTA_INTERVAL),
    ]
    with get_db_connection() as conn:
        for name, interval in default_tasks:
            conn.execute('''
                INSERT INTO task_state (task_name, is_running, status, interval_seconds)
                VALUES (?, 0, 'Stopped', ?)
                ON CONFLICT(task_name) DO NOTHING
            ''', (name, interval))
        conn.commit()

def init_default_admin():
    """Ensures at least one administrator user exists."""
    with get_db_connection() as conn:
        user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
        if not user:
            username = config.ADMIN_USERNAME
            password = config.ADMIN_PASSWORD
            if not password:
                import secrets
                password = secrets.token_urlsafe(12)
                logger.warning(f"==================================================")
                logger.warning(f"INITIAL ADMIN USER CREATED:")
                logger.warning(f"Username: {username}")
                logger.warning(f"Password: {password}")
                logger.warning(f"Please log in and update your credentials.")
                logger.warning(f"==================================================")
            else:
                logger.info(f"Initialized default user '{username}'")

            pw_hash = generate_password_hash(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                (username, pw_hash)
            )
            conn.commit()

# --- User Management ---
def get_user_by_username(username):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def verify_user_password(username, password):
    user = get_user_by_username(username)
    if not user:
        return None
    if check_password_hash(user['password_hash'], password):
        return user
    return None

# --- Posts CRUD ---
def load_posts_by_type(post_type):
    with get_db_connection() as conn:
        posts = conn.execute(
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at "
            "FROM posts WHERE post_type = ? ORDER BY last_posted_at ASC, id ASC",
            (post_type,)
        ).fetchall()
        return [dict(p) for p in posts]

def load_all_posts():
    """Retrieves all posts across all types ordered by id."""
    with get_db_connection() as conn:
        posts = conn.execute(
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at "
            "FROM posts ORDER BY post_type, id ASC"
        ).fetchall()
        return [dict(p) for p in posts]

def get_post_by_id(post_id):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at "
            "FROM posts WHERE id = ?",
            (post_id,)
        ).fetchone()
        return dict(row) if row else None

def add_post(post_type, message, image_filename):
    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?) RETURNING id",
                (post_type, message, image_filename)
            )
            row = cur.fetchone()
            conn.commit()
            return row['id']
        else:
            cur = conn.execute(
                "INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?)",
                (post_type, message, image_filename)
            )
            conn.commit()
            return cur.lastrowid

def update_post_by_id(post_id, message=None, image_filename=None):
    with get_db_connection() as conn:
        res = conn.execute(
            "UPDATE posts SET message = COALESCE(?, message), image_filename = COALESCE(?, image_filename) "
            "WHERE id = ?",
            (message, image_filename, post_id)
        )
        conn.commit()
        return res.rowcount > 0

def delete_post_by_id(post_id):
    """Deletes a post by its stable ID and returns the image filename for cleanup."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT image_filename FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            return None, False
        image_filename = row['image_filename']
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        return image_filename, True

def delete_all_posts_by_type(post_type):
    """Deletes all posts for a type and returns distinct image filenames."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT image_filename FROM posts WHERE post_type = ? AND image_filename IS NOT NULL AND image_filename != ''",
            (post_type,)
        ).fetchall()
        images = [r['image_filename'] for r in rows]
        conn.execute("DELETE FROM posts WHERE post_type = ?", (post_type,))
        conn.commit()
        return images

def search_posts(query):
    with get_db_connection() as conn:
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at "
            "FROM posts WHERE message LIKE ? OR post_type LIKE ? ORDER BY created_at DESC",
            (pattern, pattern)
        ).fetchall()
        return [dict(r) for r in rows]

def update_last_posted_timestamp(post_id):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE posts SET last_posted_at = CURRENT_TIMESTAMP WHERE id = ?",
            (post_id,)
        )
        conn.commit()

# --- Task State Management (Multi-Worker Safe) ---
def get_all_task_states():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM task_state").fetchall()
        states = {}
        for r in rows:
            states[r['task_name']] = {
                'is_running': bool(r['is_running']),
                'status': r['status'] or '',
                'current_post_summary': r['current_post_summary'],
                'interval': r['interval_seconds'] or 1800,
                'last_run_at': r['last_run_at'],
                'updated_at': r['updated_at']
            }
        return states

def get_task_state(task_name):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM task_state WHERE task_name = ?", (task_name,)).fetchone()
        if not row:
            return None
        return {
            'is_running': bool(row['is_running']),
            'status': row['status'] or '',
            'current_post_summary': row['current_post_summary'],
            'interval': row['interval_seconds'] or 1800,
            'last_run_at': row['last_run_at'],
            'updated_at': row['updated_at']
        }

def set_task_state(task_name, is_running=None, status=None, current_post_summary=None, interval_seconds=None):
    with get_db_connection() as conn:
        updates = []
        params = []
        if is_running is not None:
            updates.append("is_running = ?")
            params.append(1 if is_running else 0)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if current_post_summary is not None:
            updates.append("current_post_summary = ?")
            params.append(current_post_summary)
        if interval_seconds is not None:
            updates.append("interval_seconds = ?")
            params.append(int(interval_seconds))
            
        updates.append("updated_at = CURRENT_TIMESTAMP")
        if is_running:
            updates.append("last_run_at = CURRENT_TIMESTAMP")
            
        params.append(task_name)
        sql = f"UPDATE task_state SET {', '.join(updates)} WHERE task_name = ?"
        conn.execute(sql, params)
        conn.commit()

# --- Safe Online SQLite Backup ---
def backup_sqlite_db(target_path=None):
    """
    Creates a transactionally consistent, live online backup of the SQLite database
    using SQLite's built-in backup API. Safe against concurrent writes and WAL mode.
    """
    if is_postgres():
        raise NotImplementedError("Direct file backup is for SQLite. Use pg_dump or backup.py for PostgreSQL.")

    src_path = _get_sqlite_path()
    if not src_path.exists():
        raise FileNotFoundError(f"Source database file not found: {src_path}")

    if not target_path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path(config.DATA_DIR) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        target_path = backup_dir / f"posts_backup_{timestamp}.db"
    else:
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(src_path))
    dst_conn = sqlite3.connect(str(target_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
        logger.info(f"SQLite online backup completed successfully: {target_path}")
        return target_path
    finally:
        dst_conn.close()
        src_conn.close()

# --- Distributed Worker Lease Management ---
def acquire_worker_lease(worker_id, lease_name='scheduler', ttl_seconds=30):
    """
    Attempts to acquire or renew a worker lease atomically.
    Returns True if lease acquired or renewed by worker_id, False if held by another active worker.
    Automatically handles stale / crashed lease recovery.
    """
    now = _utcnow()
    new_expires = now + timedelta(seconds=ttl_seconds)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        row = conn.execute("SELECT worker_id, expires_at FROM worker_leases WHERE lease_name = ?", (lease_name,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO worker_leases (lease_name, worker_id, acquired_at, expires_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (lease_name, worker_id, now_str, expires_str, now_str)
            )
            conn.commit()
            return True

        curr_worker = row['worker_id']
        curr_expires_raw = row['expires_at']
        try:
            if isinstance(curr_expires_raw, datetime):
                curr_expires = curr_expires_raw
            else:
                curr_expires = datetime.fromisoformat(str(curr_expires_raw).replace(' ', 'T')[:19])
        except Exception:
            curr_expires = now - timedelta(seconds=1)

        # If current worker owns it, or previous lease expired (crashed worker recovery)
        if curr_worker == worker_id or curr_expires <= now:
            conn.execute(
                "UPDATE worker_leases SET worker_id = ?, expires_at = ?, updated_at = ? WHERE lease_name = ?",
                (worker_id, expires_str, now_str, lease_name)
            )
            conn.commit()
            return True

        # Lease is held by another active worker
        return False

def renew_worker_lease(worker_id, lease_name='scheduler', ttl_seconds=30):
    """Renews an existing lease if still held by worker_id."""
    now = _utcnow()
    new_expires = now + timedelta(seconds=ttl_seconds)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        res = conn.execute(
            "UPDATE worker_leases SET expires_at = ?, updated_at = ? WHERE lease_name = ? AND worker_id = ?",
            (expires_str, now_str, lease_name, worker_id)
        )
        conn.commit()
        return res.rowcount > 0

def release_worker_lease(worker_id, lease_name='scheduler'):
    """Releases a worker lease upon clean shutdown."""
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM worker_leases WHERE lease_name = ? AND worker_id = ?",
            (lease_name, worker_id)
        )
        conn.commit()

def get_active_worker_lease(lease_name='scheduler'):
    """Returns active lease dict if valid, None if expired or unheld."""
    now = _utcnow()
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM worker_leases WHERE lease_name = ?", (lease_name,)).fetchone()
        if not row:
            return None
        expires_raw = row['expires_at']
        try:
            if isinstance(expires_raw, datetime):
                expires = expires_raw
            else:
                expires = datetime.fromisoformat(str(expires_raw).replace(' ', 'T')[:19])
        except Exception:
            return None

        if expires > now:
            return dict(row)
        return None

# --- Cross-Platform Synced Posts Tracking (replaces posted.txt) ---
def is_post_synced(post_id, target_platform='instagram'):
    """Checks whether a Facebook post ID has already been cross-posted."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM synced_posts WHERE post_id = ? AND target_platform = ?",
            (str(post_id), target_platform)
        ).fetchone()
        return row is not None

def mark_post_synced(post_id, target_platform='instagram'):
    """Records a post ID as cross-posted."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO synced_posts (post_id, target_platform) VALUES (?, ?) "
            "ON CONFLICT(post_id) DO NOTHING",
            (str(post_id), target_platform)
        )
        conn.commit()

def get_all_synced_post_ids(target_platform='instagram'):
    """Retrieves all synced post IDs for a target platform as a set."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT post_id FROM synced_posts WHERE target_platform = ?",
            (target_platform,)
        ).fetchall()
        return {r['post_id'] for r in rows}
