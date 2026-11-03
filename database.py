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
import os
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import config
import timezone_utils

SAFE_MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4'}

def validate_media_reference(filename):
    """
    Validates that a media reference does not contain path traversal sequences
    and uses an allowed media file extension.
    """
    if not filename:
        return None
    if not isinstance(filename, str):
        raise ValueError("Media reference must be a string filename.")
    clean = filename.strip()
    if not clean:
        return None
    if ".." in clean or "/" in clean or "\\" in clean or "\0" in clean:
        raise ValueError("Invalid media reference: path traversal characters are forbidden.")
    base = os.path.basename(clean)
    if base != clean:
        raise ValueError("Invalid media reference: directory paths are forbidden.")
    _, ext = os.path.splitext(base)
    if ext.lower() not in SAFE_MEDIA_EXTENSIONS:
        raise ValueError(f"Unsupported media file extension '{ext}'. Allowed: {', '.join(sorted(SAFE_MEDIA_EXTENSIONS))}")
    return base

class TenantIsolationError(ValueError):
    """Raised when an operation attempts to access or mutate resources of another tenant/organization."""
    pass

def validate_brand_ownership(brand_id, organization_id):
    """
    Validates that brand_id exists and belongs to the given organization.
    """
    if brand_id is None or brand_id == "":
        return True
    try:
        b_id = int(brand_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid brand ID '{brand_id}'. Must be an integer.")
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, organization_id FROM brands WHERE id = ?",
            (b_id,)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Brand ID {b_id} does not exist.")
        if row['organization_id'] != organization_id:
            raise TenantIsolationError(f"Brand ID {b_id} belongs to a different organization and cannot be accessed.")
        return True

def validate_post_ownership(post_id, post_type, organization_id):
    """
    Validates that referenced post_id exists, belongs to the channel, and belongs to the organization.
    """
    if post_id is None or post_id == "":
        return True
    try:
        p_id = int(post_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid post ID '{post_id}'. Must be an integer.")
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, post_type, organization_id FROM posts WHERE id = ?",
            (p_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Referenced post ID {p_id} does not exist.")
        if row['organization_id'] != organization_id:
            raise ValueError(f"Referenced post ID {p_id} belongs to a different organization.")
        if row['post_type'] != post_type:
            raise ValueError(f"Referenced post ID {p_id} belongs to channel '{row['post_type']}', not '{post_type}'.")
        return True

def get_organization_timezone(organization_id=1):
    """Returns the IANA timezone configured for the organization (defaults to UTC)."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT timezone FROM organizations WHERE id = ?", (organization_id,)).fetchone()
        if row and row['timezone']:
            try:
                return timezone_utils.validate_timezone_name(row['timezone'])
            except ValueError:
                return "UTC"
        return "UTC"

def set_organization_timezone(organization_id, tz_name):
    """Sets and validates the organization's default timezone."""
    clean_tz = timezone_utils.validate_timezone_name(tz_name)
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE organizations SET timezone = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (clean_tz, organization_id)
        )
        conn.commit()
    return clean_tz


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
        p = Path(path_str)
        if not p.is_absolute():
            p = config.BASE_DIR / p
        return p
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
            try:
                import facebook_api
                safe_e = facebook_api.sanitize_log_message(str(e))
            except Exception:
                safe_e = str(e)
            logger.error(f"Failed to connect to PostgreSQL: {safe_e}")
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

def _ensure_column_exists(conn, table_name, column_name, column_def):
    """Safely adds a column to an existing table if not already present."""
    if is_postgres():
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_def}")
            conn.commit()
        except Exception as e:
            logger.warning(f"Notice adding column {column_name} to {table_name}: {e}")
    else:
        try:
            cur = conn.execute(f"PRAGMA table_info({table_name})")
            cols = [r[1] for r in cur.fetchall()]
            if column_name not in cols:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
                conn.commit()
        except Exception as e:
            logger.warning(f"Notice adding column {column_name} to {table_name}: {e}")

def _ensure_indexes(conn):
    """Creates performance and integrity indexes safely."""
    indexes = [
        ("idx_posts_org_type", "CREATE INDEX IF NOT EXISTS idx_posts_org_type ON posts(organization_id, post_type, last_posted_at, id)"),
        ("idx_posts_media", "CREATE INDEX IF NOT EXISTS idx_posts_media ON posts(image_filename)"),
        ("idx_sched_due", "CREATE INDEX IF NOT EXISTS idx_sched_due ON scheduled_posts(status, scheduled_for)"),
        ("idx_sched_org", "CREATE INDEX IF NOT EXISTS idx_sched_org ON scheduled_posts(organization_id, post_type, scheduled_for)"),
        ("idx_sched_lock", "CREATE INDEX IF NOT EXISTS idx_sched_lock ON scheduled_posts(locked_by, locked_at)"),
        ("idx_sched_idempotency", "CREATE INDEX IF NOT EXISTS idx_sched_idempotency ON scheduled_posts(idempotency_key)"),
        ("idx_brands_org", "CREATE INDEX IF NOT EXISTS idx_brands_org ON brands(organization_id, slug)"),
        ("idx_users_org", "CREATE INDEX IF NOT EXISTS idx_users_org ON users(organization_id, username)"),
        ("idx_audit_post", "CREATE INDEX IF NOT EXISTS idx_audit_post ON post_audit_logs(scheduled_post_id, created_at)"),
        ("idx_audit_org", "CREATE INDEX IF NOT EXISTS idx_audit_org ON post_audit_logs(organization_id, created_at)"),
        ("idx_bmp_org_brand", "CREATE INDEX IF NOT EXISTS idx_bmp_org_brand ON brand_marketing_profiles(organization_id, brand_id)"),
        ("idx_campaigns_org_brand", "CREATE INDEX IF NOT EXISTS idx_campaigns_org_brand ON campaigns(organization_id, brand_id, status)"),
        ("idx_campaigns_status", "CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(organization_id, status)"),
        ("idx_drafts_org_campaign", "CREATE INDEX IF NOT EXISTS idx_drafts_org_campaign ON content_drafts(organization_id, campaign_id, target_platform)"),
        ("idx_drafts_org_brand", "CREATE INDEX IF NOT EXISTS idx_drafts_org_brand ON content_drafts(organization_id, brand_id, status)"),
    ]
    for name, sql in indexes:
        try:
            conn.execute(sql)
        except Exception as e:
            logger.warning(f"Index creation notice for {name}: {e}")
    conn.commit()

def init_db():
    """Initializes tables and seeds initial administrator and task states."""
    is_pg = is_postgres()
    auto_id = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    with get_db_connection() as conn:
        # 1. Organizations table (Multi-tenancy isolation)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS organizations (
                id {auto_id},
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                plan TEXT DEFAULT 'growth',
                timezone TEXT DEFAULT 'UTC',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. Brands / Workspaces table
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS brands (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                description TEXT,
                logo_url TEXT,
                color_hex TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, slug)
            )
        ''')

        # 3. Posts table
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS posts (
                id {auto_id},
                organization_id INTEGER DEFAULT 1,
                brand_id INTEGER,
                post_type TEXT NOT NULL,
                message TEXT,
                image_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_posted_at TIMESTAMP
            )
        ''')
        
        # 4. Users table for authentication
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS users (
                id {auto_id},
                organization_id INTEGER DEFAULT 1,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'admin',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5. Scheduled posts table (persistent calendar scheduler)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id {auto_id},
                organization_id INTEGER NOT NULL DEFAULT 1,
                brand_id INTEGER,
                post_type TEXT NOT NULL,
                post_id INTEGER,
                message TEXT,
                image_filename TEXT,
                scheduled_for TIMESTAMP NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                status TEXT DEFAULT 'scheduled',
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error_message TEXT,
                locked_by TEXT,
                locked_at TIMESTAMP,
                published_at TIMESTAMP,
                idempotency_key TEXT UNIQUE,
                approved_by INTEGER,
                approved_at TIMESTAMP,
                rejection_reason TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 5b. Post audit logs table (lifecycle history & compliance)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS post_audit_logs (
                id {auto_id},
                organization_id INTEGER NOT NULL DEFAULT 1,
                scheduled_post_id INTEGER NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                changed_by INTEGER,
                reason TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 6. Task state table (decouples task state from in-process memory)
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

        # 7. Worker leases table (ensures single active worker across processes)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS worker_leases (
                lease_name TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 8. Synced posts table (replaces legacy posted.txt for Instagram cross-posting)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS synced_posts (
                post_id TEXT PRIMARY KEY,
                target_platform TEXT DEFAULT 'instagram',
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 9. Brand marketing profiles (positioning, voice & tone, approved facts)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS brand_marketing_profiles (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                positioning TEXT,
                target_audiences TEXT,
                target_markets TEXT,
                languages TEXT,
                voice_and_tone TEXT,
                messaging_guidelines TEXT,
                approved_product_facts TEXT,
                prohibited_claims TEXT,
                preferred_ctas TEXT,
                website_and_social_links TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, brand_id)
            )
        ''')

        # 10. Campaigns table (brand-aware marketing campaigns)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS campaigns (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                objective TEXT NOT NULL,
                campaign_type TEXT DEFAULT 'social',
                target_audience TEXT,
                target_markets TEXT,
                languages TEXT,
                brief TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                status TEXT DEFAULT 'draft',
                budget TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 11. Content drafts table (AI generated and editable content drafts)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS content_drafts (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                target_platform TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                content_format TEXT DEFAULT 'post',
                headline TEXT,
                caption TEXT NOT NULL,
                hashtags TEXT,
                call_to_action TEXT,
                ai_provider TEXT,
                ai_model TEXT,
                metadata TEXT,
                status TEXT DEFAULT 'draft',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()

        # Non-destructive migrations for existing tables
        _ensure_column_exists(conn, 'organizations', 'timezone', "TEXT DEFAULT 'UTC'")
        _ensure_column_exists(conn, 'posts', 'organization_id', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'posts', 'brand_id', 'INTEGER')
        _ensure_column_exists(conn, 'users', 'organization_id', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'users', 'is_active', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'scheduled_posts', 'approved_by', 'INTEGER')
        _ensure_column_exists(conn, 'scheduled_posts', 'approved_at', 'TIMESTAMP')
        _ensure_column_exists(conn, 'scheduled_posts', 'rejection_reason', 'TEXT')

        # Create indexes
        _ensure_indexes(conn)

    # Seed default tasks if empty
    init_default_tasks()

    # Seed default organizations & brands
    init_default_organizations_and_brands()

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
                "INSERT INTO users (username, password_hash, role, organization_id) VALUES (?, ?, 'admin', 1)",
                (username, pw_hash)
            )
            conn.commit()

def init_default_organizations_and_brands():
    """Initializes default GAATHA organization and initial brand workspaces."""
    with get_db_connection() as conn:
        org = conn.execute("SELECT id, timezone FROM organizations WHERE id = 1").fetchone()
        if not org:
            conn.execute(
                "INSERT INTO organizations (id, name, slug, plan, timezone, is_active) VALUES (1, ?, ?, ?, 'Asia/Kolkata', 1)",
                ('GAATHA', 'gaatha', 'enterprise')
            )
            conn.commit()
        elif not org['timezone'] or org['timezone'] == 'UTC':
            conn.execute("UPDATE organizations SET timezone = 'Asia/Kolkata' WHERE id = 1")
            conn.commit()

        initial_brands = [
            ('GAATHA Suite', 'gaatha-suite', 'Core business marketing & customer engagement suite'),
            ('GAATHA POS', 'gaatha-pos', 'Point of sale and retail operations marketing'),
            ('Sentira AI', 'sentira-ai', 'AI-native intelligence and automation systems'),
            ('GAATHA Terra', 'gaatha-terra', 'Sustainability, agriculture, and land systems'),
            ('Phoenix — BY GAATHA', 'phoenix-by-gaatha', 'Flagship international and visa services'),
            ('GAATHA AI', 'gaatha-ai', 'Next-generation AI research and generative applications')
        ]
        for name, slug, desc in initial_brands:
            existing = conn.execute(
                "SELECT id FROM brands WHERE organization_id = 1 AND slug = ?",
                (slug,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO brands (organization_id, name, slug, description, is_active) VALUES (1, ?, ?, ?, 1)",
                    (name, slug, desc)
                )
        conn.commit()

# --- Organization & Brand Multi-Tenancy Management ---
def get_organization_by_id(org_id):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        return dict(row) if row else None

def get_organization_by_slug(slug):
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM organizations WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None

def list_organizations():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM organizations WHERE is_active = 1 ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

def create_organization(name, slug, plan='growth'):
    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO organizations (name, slug, plan, is_active) VALUES (?, ?, ?, 1) RETURNING id",
                (name, slug, plan)
            )
            row = cur.fetchone()
            conn.commit()
            return row['id']
        else:
            cur = conn.execute(
                "INSERT INTO organizations (name, slug, plan, is_active) VALUES (?, ?, ?, 1)",
                (name, slug, plan)
            )
            conn.commit()
            return cur.lastrowid

def get_brands_by_organization(org_id):
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM brands WHERE organization_id = ? AND is_active = 1 ORDER BY id ASC",
            (org_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def create_brand(organization_id, name, slug, description=''):
    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO brands (organization_id, name, slug, description, is_active) VALUES (?, ?, ?, ?, 1) RETURNING id",
                (organization_id, name, slug, description)
            )
            row = cur.fetchone()
            conn.commit()
            return row['id']
        else:
            cur = conn.execute(
                "INSERT INTO brands (organization_id, name, slug, description, is_active) VALUES (?, ?, ?, ?, 1)",
                (organization_id, name, slug, description)
            )
            conn.commit()
            return cur.lastrowid

def get_brand_by_id(brand_id, organization_id=None):
    """Retrieves a single brand by ID, optionally scoped to organization."""
    try:
        b_id = int(brand_id)
    except (ValueError, TypeError):
        return None
    with get_db_connection() as conn:
        if organization_id is not None:
            row = conn.execute(
                "SELECT * FROM brands WHERE id = ? AND organization_id = ? AND is_active = 1",
                (b_id, organization_id)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM brands WHERE id = ? AND is_active = 1", (b_id,)).fetchone()
        return dict(row) if row else None

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

# --- Posts CRUD (Channel-Scoped & Organization-Scoped) ---
def load_posts_by_type(post_type, organization_id=None):
    with get_db_connection() as conn:
        if organization_id is not None:
            posts = conn.execute(
                "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id "
                "FROM posts WHERE post_type = ? AND organization_id = ? ORDER BY last_posted_at ASC, id ASC",
                (post_type, organization_id)
            ).fetchall()
        else:
            posts = conn.execute(
                "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id "
                "FROM posts WHERE post_type = ? ORDER BY last_posted_at ASC, id ASC",
                (post_type,)
            ).fetchall()
        return [dict(p) for p in posts]

def load_all_posts(organization_id=None):
    """Retrieves all posts across all types ordered by id."""
    with get_db_connection() as conn:
        if organization_id is not None:
            posts = conn.execute(
                "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id "
                "FROM posts WHERE organization_id = ? ORDER BY post_type, id ASC",
                (organization_id,)
            ).fetchall()
        else:
            posts = conn.execute(
                "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id "
                "FROM posts ORDER BY post_type, id ASC"
            ).fetchall()
        return [dict(p) for p in posts]

def get_post_by_id(post_id, post_type=None, organization_id=None):
    with get_db_connection() as conn:
        query = "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id FROM posts WHERE id = ?"
        params = [post_id]
        if post_type is not None:
            query += " AND post_type = ?"
            params.append(post_type)
        if organization_id is not None:
            query += " AND organization_id = ?"
            params.append(organization_id)
        row = conn.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

def add_post(post_type, message, image_filename, organization_id=1, brand_id=None):
    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO posts (post_type, message, image_filename, organization_id, brand_id) VALUES (?, ?, ?, ?, ?) RETURNING id",
                (post_type, message, image_filename, organization_id, brand_id)
            )
            row = cur.fetchone()
            conn.commit()
            return row['id']
        else:
            cur = conn.execute(
                "INSERT INTO posts (post_type, message, image_filename, organization_id, brand_id) VALUES (?, ?, ?, ?, ?)",
                (post_type, message, image_filename, organization_id, brand_id)
            )
            conn.commit()
            return cur.lastrowid

def update_post_by_id(post_id, message=None, image_filename=None, post_type=None, organization_id=None):
    """
    Updates post with strict database-level enforcement of channel and organization boundaries.
    Prevents cross-channel or cross-tenant record tampering.
    """
    with get_db_connection() as conn:
        query = "UPDATE posts SET message = COALESCE(?, message), image_filename = COALESCE(?, image_filename) WHERE id = ?"
        params = [message, image_filename, post_id]
        if post_type is not None:
            query += " AND post_type = ?"
            params.append(post_type)
        if organization_id is not None:
            query += " AND organization_id = ?"
            params.append(organization_id)
        res = conn.execute(query, tuple(params))
        conn.commit()
        return res.rowcount > 0

def delete_post_by_id(post_id, post_type=None, organization_id=None):
    """
    Deletes a post ensuring channel and organization isolation at the database level.
    Returns the image filename for cleanup and a boolean indicating success.
    """
    with get_db_connection() as conn:
        select_query = "SELECT image_filename FROM posts WHERE id = ?"
        params = [post_id]
        if post_type is not None:
            select_query += " AND post_type = ?"
            params.append(post_type)
        if organization_id is not None:
            select_query += " AND organization_id = ?"
            params.append(organization_id)
            
        row = conn.execute(select_query, tuple(params)).fetchone()
        if not row:
            return None, False
        image_filename = row['image_filename']

        del_query = "DELETE FROM posts WHERE id = ?"
        del_params = [post_id]
        if post_type is not None:
            del_query += " AND post_type = ?"
            del_params.append(post_type)
        if organization_id is not None:
            del_query += " AND organization_id = ?"
            del_params.append(organization_id)
            
        conn.execute(del_query, tuple(del_params))
        conn.commit()
        return image_filename, True

def delete_all_posts_by_type(post_type, organization_id=None):
    """Deletes all posts for a type scoped to organization and returns distinct image filenames."""
    with get_db_connection() as conn:
        select_query = "SELECT DISTINCT image_filename FROM posts WHERE post_type = ? AND image_filename IS NOT NULL AND image_filename != ''"
        params = [post_type]
        if organization_id is not None:
            select_query += " AND organization_id = ?"
            params.append(organization_id)
            
        rows = conn.execute(select_query, tuple(params)).fetchall()
        images = [r['image_filename'] for r in rows]

        del_query = "DELETE FROM posts WHERE post_type = ?"
        del_params = [post_type]
        if organization_id is not None:
            del_query += " AND organization_id = ?"
            del_params.append(organization_id)

        conn.execute(del_query, tuple(del_params))
        conn.commit()
        return images

def search_posts(query, organization_id=None):
    """Searches posts across message and post_type scoped to organization."""
    with get_db_connection() as conn:
        pattern = f"%{query}%"
        sql = (
            "SELECT id, post_type, message, image_filename, created_at, last_posted_at, organization_id, brand_id "
            "FROM posts WHERE (message LIKE ? OR post_type LIKE ?)"
        )
        params = [pattern, pattern]
        if organization_id is not None:
            sql += " AND organization_id = ?"
            params.append(organization_id)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
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
            try:
                import facebook_api
                safe_status = facebook_api.sanitize_log_message(str(status))
            except Exception:
                safe_status = str(status)
            params.append(safe_status)
        if current_post_summary is not None:
            updates.append("current_post_summary = ?")
            try:
                import facebook_api
                safe_summary = facebook_api.sanitize_log_message(str(current_post_summary))
            except Exception:
                safe_summary = str(current_post_summary)
            params.append(safe_summary)
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
    Automatically handles stale / crashed lease recovery without race conditions.
    """
    now = _utcnow()
    new_expires = now + timedelta(seconds=ttl_seconds)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        # 1. Ensure lease row exists safely without primary key race condition
        conn.execute(
            "INSERT INTO worker_leases (lease_name, worker_id, acquired_at, expires_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(lease_name) DO NOTHING",
            (lease_name, worker_id, now_str, expires_str, now_str)
        )

        # 2. Atomically acquire or renew if unheld, expired, or currently held by this worker
        cur = conn.execute(
            "UPDATE worker_leases SET worker_id = ?, expires_at = ?, updated_at = ? "
            "WHERE lease_name = ? AND (worker_id = ? OR expires_at <= ?)",
            (worker_id, expires_str, now_str, lease_name, worker_id, now_str)
        )
        conn.commit()
        return cur.rowcount > 0

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

# --- Persistent Calendar Scheduler Engine ---
ALLOWED_INITIAL_STATUSES = frozenset({'draft', 'pending_approval', 'scheduled'})

def create_scheduled_post(post_type, scheduled_for, message="", image_filename=None, post_id=None,
                          organization_id=1, brand_id=None, idempotency_key=None, created_by=None,
                          timezone_name=None, initial_status='scheduled', allow_past=True, **kwargs):
    """
    Creates a persistent scheduled post with strict validation, timezone normalization to UTC,
    channel/brand ownership check, and idempotency protection.
    """
    import secrets
    import time

    if not initial_status or initial_status not in ALLOWED_INITIAL_STATUSES:
        raise ValueError(
            f"Invalid initial post status: '{initial_status}'. Must be one of: {', '.join(sorted(ALLOWED_INITIAL_STATUSES))}."
        )

    if post_type not in ('tour', 'nz', 'gaatha', 'insta'):
        raise ValueError(f"Invalid post_type: '{post_type}'. Must be one of tour, nz, gaatha, insta.")

    # Validate organization exists and is active
    with get_db_connection() as conn:
        org = conn.execute("SELECT id FROM organizations WHERE id = ? AND is_active = 1", (organization_id,)).fetchone()
        if not org:
            raise ValueError(f"Organization #{organization_id} does not exist or is inactive.")

    # Validate brand ownership
    if brand_id:
        validate_brand_ownership(brand_id, organization_id)

    # Validate referenced post ownership and channel match
    if post_id:
        validate_post_ownership(post_id, post_type, organization_id)

    # Validate media path
    safe_image = validate_media_reference(image_filename) if image_filename else None

    # Resolve organization timezone
    org_tz = get_organization_timezone(organization_id)
    target_tz = timezone_name or kwargs.get('timezone_str') or org_tz

    # Parse and convert to UTC
    utc_dt, resolved_tz, scheduled_utc_str = timezone_utils.parse_and_convert_to_utc(
        str(scheduled_for),
        tz_name=target_tz,
        org_default_tz=org_tz,
        allow_past=allow_past
    )

    if not idempotency_key:
        idempotency_key = f"sched-{organization_id}-{post_type}-{int(time.time())}-{secrets.token_hex(4)}"

    with get_db_connection() as conn:
        # Idempotency check: if already exists, return existing record
        existing = conn.execute(
            "SELECT * FROM scheduled_posts WHERE idempotency_key = ?",
            (idempotency_key,)
        ).fetchone()
        if existing:
            if existing['organization_id'] != organization_id:
                raise ValueError("Idempotency key collision across organizations.")
            if existing['post_type'] != post_type:
                raise ValueError(f"Idempotency key collision across channels: post belongs to '{existing['post_type']}'.")
            return get_scheduled_post_by_id(existing['id'], organization_id=organization_id)

        msg_val = message if message is not None else ""
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO scheduled_posts (organization_id, brand_id, post_type, post_id, message, image_filename, "
                "scheduled_for, timezone, status, idempotency_key, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (organization_id, brand_id, post_type, post_id, msg_val, safe_image,
                 scheduled_utc_str, resolved_tz, initial_status, idempotency_key, created_by)
            )
            row = cur.fetchone()
            conn.commit()
            new_id = row['id']
        else:
            cur = conn.execute(
                "INSERT INTO scheduled_posts (organization_id, brand_id, post_type, post_id, message, image_filename, "
                "scheduled_for, timezone, status, idempotency_key, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (organization_id, brand_id, post_type, post_id, msg_val, safe_image,
                 scheduled_utc_str, resolved_tz, initial_status, idempotency_key, created_by)
            )
            conn.commit()
            new_id = cur.lastrowid

        created_rec = get_scheduled_post_by_id(new_id, post_type=post_type, organization_id=organization_id)
        if created_rec:
            log_post_transition(
                scheduled_post_id=created_rec['id'],
                from_status=None,
                to_status=initial_status,
                changed_by=created_by,
                reason="Initial post creation",
                organization_id=organization_id
            )
        return created_rec

def get_scheduled_posts(organization_id=1, post_type=None, status=None, brand_id=None,
                        start_date=None, end_date=None, limit=100, offset=0, target_timezone=None):
    """
    Retrieves scheduled posts for an organization with optional filtering by channel,
    brand, status, and date range. Automatically augments each post with localized times.
    Enforces strict pagination bounds and date range ordering.
    """
    if limit is not None:
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            raise ValueError(f"Limit must be an integer between 1 and 500. Got: '{limit}'.")
        if limit < 1 or limit > 500:
            raise ValueError(f"Limit must be between 1 and 500. Got: {limit}.")
    else:
        limit = 100

    if offset is not None:
        try:
            offset = int(offset)
        except (ValueError, TypeError):
            raise ValueError(f"Offset must be a non-negative integer. Got: '{offset}'.")
        if offset < 0:
            raise ValueError(f"Offset cannot be negative. Got: {offset}.")
    else:
        offset = 0

    if post_type:
        if post_type not in ('tour', 'nz', 'gaatha', 'insta'):
            raise ValueError(f"Invalid post_type: '{post_type}'. Must be one of tour, nz, gaatha, insta.")

    if status:
        if status not in VALID_POST_STATUSES:
            raise ValueError(f"Invalid status filter: '{status}'.")

    if brand_id:
        validate_brand_ownership(brand_id, organization_id)

    org_tz = target_timezone or get_organization_timezone(organization_id)
    if target_timezone:
        org_tz = timezone_utils.validate_timezone_name(target_timezone)

    start_utc = None
    if start_date:
        _, _, start_utc = timezone_utils.parse_and_convert_to_utc(str(start_date), tz_name=org_tz, allow_past=True)

    end_utc = None
    if end_date:
        _, _, end_utc = timezone_utils.parse_and_convert_to_utc(str(end_date), tz_name=org_tz, allow_past=True)

    if start_utc and end_utc and start_utc > end_utc:
        raise ValueError(
            f"Invalid date range: start_date ('{start_date}') must be earlier than or equal to end_date ('{end_date}')."
        )

    with get_db_connection() as conn:
        query = "SELECT * FROM scheduled_posts WHERE organization_id = ?"
        params = [organization_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if brand_id:
            query += " AND brand_id = ?"
            params.append(int(brand_id))
        if start_utc:
            query += " AND scheduled_for >= ?"
            params.append(start_utc)
        if end_utc:
            query += " AND scheduled_for <= ?"
            params.append(end_utc)

        query += " ORDER BY scheduled_for ASC, id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, tuple(params)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                loc = timezone_utils.convert_utc_to_local(d['scheduled_for'], tz_name=org_tz)
                d['local_scheduled_for'] = loc['local_iso']
                d['local_display'] = loc['local_display']
                d['display_timezone'] = loc['timezone']
            except Exception:
                d['local_scheduled_for'] = str(d['scheduled_for'])
                d['local_display'] = str(d['scheduled_for'])
                d['display_timezone'] = 'UTC'
            results.append(d)
        return results

def get_scheduled_post_by_id(schedule_id, post_type=None, organization_id=None, target_timezone=None):
    """Retrieves a single scheduled post with localized date fields."""
    with get_db_connection() as conn:
        query = "SELECT * FROM scheduled_posts WHERE id = ?"
        params = [schedule_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)
        if organization_id:
            query += " AND organization_id = ?"
            params.append(organization_id)
        row = conn.execute(query, tuple(params)).fetchone()
        if not row:
            return None
        d = dict(row)
        org_tz = target_timezone or get_organization_timezone(d.get('organization_id', 1))
        try:
            loc = timezone_utils.convert_utc_to_local(d['scheduled_for'], tz_name=org_tz)
            d['local_scheduled_for'] = loc['local_iso']
            d['local_display'] = loc['local_display']
            d['display_timezone'] = loc['timezone']
        except Exception:
            d['local_scheduled_for'] = str(d['scheduled_for'])
            d['local_display'] = str(d['scheduled_for'])
            d['display_timezone'] = 'UTC'
        return d

def update_scheduled_post(schedule_id, message=None, image_filename=None, scheduled_for=None,
                          timezone_name=None, brand_id=None, post_type=None, organization_id=None,
                          allow_past=False):
    """Updates an existing scheduled post with validation and timezone normalization."""
    existing = get_scheduled_post_by_id(schedule_id, post_type=post_type, organization_id=organization_id)
    if not existing:
        return False

    if existing['status'] in ('publishing', 'published', 'cancelled'):
        raise ValueError(f"Cannot update scheduled post #{schedule_id} with status '{existing['status']}'.")

    updates = []
    params = []
    if message is not None:
        updates.append("message = ?")
        params.append(message)
    if image_filename is not None:
        safe_media = validate_media_reference(image_filename) if image_filename else ""
        updates.append("image_filename = ?")
        params.append(safe_media)
    if brand_id is not None:
        if brand_id != 0 and brand_id != "":
            target_org = organization_id or existing['organization_id']
            validate_brand_ownership(brand_id, target_org)
            updates.append("brand_id = ?")
            params.append(int(brand_id))
        else:
            updates.append("brand_id = NULL")
    if scheduled_for is not None:
        target_org = organization_id or existing['organization_id']
        org_tz = get_organization_timezone(target_org)
        target_tz = timezone_name or existing.get('timezone') or org_tz
        utc_dt, resolved_tz, utc_str = timezone_utils.parse_and_convert_to_utc(
            str(scheduled_for),
            tz_name=target_tz,
            org_default_tz=org_tz,
            allow_past=allow_past
        )
        updates.append("scheduled_for = ?")
        params.append(utc_str)
        updates.append("timezone = ?")
        params.append(resolved_tz)

    if not updates:
        return True

    updates.append("updated_at = CURRENT_TIMESTAMP")
    query = f"UPDATE scheduled_posts SET {', '.join(updates)} WHERE id = ?"
    params.append(schedule_id)
    if organization_id:
        query += " AND organization_id = ?"
        params.append(organization_id)

    with get_db_connection() as conn:
        res = conn.execute(query, tuple(params))
        conn.commit()
        return res.rowcount > 0

def cancel_scheduled_post(schedule_id, post_type=None, organization_id=None, user_id=None, reason=None):
    """Cancels a scheduled post if not already published or cancelled."""
    existing = get_scheduled_post_by_id(schedule_id, post_type=post_type, organization_id=organization_id)
    if not existing:
        return False
    if existing['status'] in ('publishing', 'published', 'cancelled'):
        raise ValueError(f"Cannot cancel scheduled post #{schedule_id} with status '{existing['status']}'.")

    with get_db_connection() as conn:
        query = "UPDATE scheduled_posts SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        params = [schedule_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)
        if organization_id:
            query += " AND organization_id = ?"
            params.append(organization_id)
        res = conn.execute(query, tuple(params))
        conn.commit()
        if res.rowcount > 0:
            log_post_transition(
                scheduled_post_id=schedule_id,
                from_status=existing['status'],
                to_status='cancelled',
                changed_by=user_id,
                reason=reason or 'Post cancelled by user',
                organization_id=existing['organization_id'],
                conn=conn
            )
            conn.commit()
            return True
        return False

def delete_scheduled_post(schedule_id, post_type=None, organization_id=None):
    with get_db_connection() as conn:
        query = "DELETE FROM scheduled_posts WHERE id = ?"
        params = [schedule_id]
        if post_type:
            query += " AND post_type = ?"
            params.append(post_type)
        if organization_id:
            query += " AND organization_id = ?"
            params.append(organization_id)
        res = conn.execute(query, tuple(params))
        conn.commit()
        return res.rowcount > 0

def claim_due_scheduled_posts(worker_id, limit=5, lock_timeout_seconds=300):
    """
    Atomically claims due scheduled posts across processes without race conditions.
    Also handles stale-lock recovery if a worker crashed while publishing.
    Only claims posts in 'scheduled' status (drafts, pending_approval, rejected, cancelled are NEVER claimed).
    """
    now = _utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    stale_str = (now - timedelta(seconds=lock_timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT id FROM scheduled_posts "
            "WHERE (status = 'scheduled' AND scheduled_for <= ?) "
            "   OR (status = 'publishing' AND locked_at <= ? AND retry_count < max_retries) "
            "ORDER BY scheduled_for ASC LIMIT ?",
            (now_str, stale_str, limit)
        )
        candidate_ids = [r['id'] for r in cur.fetchall()]
        claimed = []
        for cid in candidate_ids:
            res = conn.execute(
                "UPDATE scheduled_posts SET status = 'publishing', locked_by = ?, locked_at = ?, updated_at = ? "
                "WHERE id = ? AND ("
                "  (status = 'scheduled' AND scheduled_for <= ?) OR "
                "  (status = 'publishing' AND (locked_by = ? OR locked_at <= ?))"
                ")",
                (worker_id, now_str, now_str, cid, now_str, worker_id, stale_str)
            )
            if res.rowcount > 0:
                row = conn.execute("SELECT * FROM scheduled_posts WHERE id = ?", (cid,)).fetchone()
                if row:
                    row_dict = dict(row)
                    claimed.append(row_dict)
                    log_post_transition(
                        scheduled_post_id=cid,
                        from_status='scheduled',
                        to_status='publishing',
                        reason=f"Claimed by worker {worker_id}",
                        organization_id=row_dict.get('organization_id', 1),
                        conn=conn
                    )
        conn.commit()
        return claimed

def complete_scheduled_post(schedule_id, worker_id, success=True, error_message=None):
    """
    Marks a claimed scheduled post as published or failed/retried.
    Enforces worker claim ownership, tenant & channel isolation,
    and sanitizes any error message before storage.
    """
    now = _utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    safe_err = None
    if error_message:
        try:
            import facebook_api
            safe_err = facebook_api.sanitize_log_message(str(error_message))
        except Exception:
            clean = str(error_message)
            for s in ('token=', 'access_token=', 'password=', 'secret=', 'bearer '):
                if s in clean.lower():
                    clean = re.sub(r'(?i)(' + s + r')[^\s&"\']+', r'\1[REDACTED]', clean)
            safe_err = clean

    with get_db_connection() as conn:
        post = conn.execute(
            "SELECT * FROM scheduled_posts WHERE id = ? AND locked_by = ? AND status = 'publishing'",
            (schedule_id, worker_id)
        ).fetchone()
        if not post:
            logger.warning(
                f"Worker '{worker_id}' rejected completion on scheduled post #{schedule_id}: "
                f"no active claim held in 'publishing' status."
            )
            return False

        if success:
            res = conn.execute(
                "UPDATE scheduled_posts SET status = 'published', published_at = ?, locked_by = NULL, locked_at = NULL, "
                "updated_at = ? WHERE id = ? AND locked_by = ? AND status = 'publishing'",
                (now_str, now_str, schedule_id, worker_id)
            )
            if res.rowcount == 0:
                return False

            # Strictly scoped to channel and organization
            if post['post_id']:
                conn.execute(
                    "UPDATE posts SET last_posted_at = CURRENT_TIMESTAMP "
                    "WHERE id = ? AND post_type = ? AND organization_id = ?",
                    (post['post_id'], post['post_type'], post['organization_id'])
                )
            log_post_transition(
                scheduled_post_id=schedule_id,
                from_status='publishing',
                to_status='published',
                reason='Published successfully to Meta channel',
                organization_id=post['organization_id'],
                conn=conn
            )
        else:
            new_retries = (post['retry_count'] or 0) + 1
            max_r = post['max_retries'] or 3
            new_status = 'failed' if new_retries >= max_r else 'scheduled'
            res = conn.execute(
                "UPDATE scheduled_posts SET status = ?, retry_count = ?, error_message = ?, "
                "locked_by = NULL, locked_at = NULL, updated_at = ? "
                "WHERE id = ? AND locked_by = ? AND status = 'publishing'",
                (new_status, new_retries, safe_err, now_str, schedule_id, worker_id)
            )
            if res.rowcount == 0:
                return False

            log_post_transition(
                scheduled_post_id=schedule_id,
                from_status='publishing',
                to_status=new_status,
                reason=f"Publishing failed (retry {new_retries}/{max_r}): {safe_err}",
                organization_id=post['organization_id'],
                conn=conn
            )
        conn.commit()
        return True

# --- Controlled Post Lifecycle & Approvals Engine ---

VALID_POST_STATUSES = {
    'draft',
    'pending_approval',
    'approved',
    'scheduled',
    'publishing',
    'published',
    'rejected',
    'failed',
    'cancelled'
}

VALID_TRANSITIONS = {
    'draft': {'pending_approval', 'scheduled', 'cancelled'},
    'pending_approval': {'approved', 'rejected', 'draft', 'cancelled', 'scheduled'},
    'approved': {'scheduled', 'cancelled', 'draft'},
    'scheduled': {'publishing', 'cancelled', 'draft'},
    'publishing': {'published', 'scheduled', 'failed'},
    'rejected': {'draft', 'pending_approval', 'cancelled'},
    'failed': {'scheduled', 'draft', 'cancelled'},
    'cancelled': {'draft'}
}

def log_post_transition(scheduled_post_id, from_status, to_status, changed_by=None,
                        reason=None, metadata=None, organization_id=1, conn=None):
    """Records an immutable lifecycle audit event."""
    clean_reason = None
    if reason:
        try:
            import facebook_api
            clean_reason = facebook_api.sanitize_log_message(str(reason))
        except Exception:
            clean_reason = str(reason)

    clean_meta = None
    if metadata:
        clean_meta = json.dumps(metadata) if isinstance(metadata, (dict, list)) else str(metadata)

    if conn is not None:
        conn.execute(
            "INSERT INTO post_audit_logs (organization_id, scheduled_post_id, from_status, to_status, "
            "changed_by, reason, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (organization_id, scheduled_post_id, from_status, to_status, changed_by, clean_reason, clean_meta)
        )
    else:
        with get_db_connection() as c:
            c.execute(
                "INSERT INTO post_audit_logs (organization_id, scheduled_post_id, from_status, to_status, "
                "changed_by, reason, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (organization_id, scheduled_post_id, from_status, to_status, changed_by, clean_reason, clean_meta)
            )
            c.commit()

def get_post_audit_history(scheduled_post_id, organization_id=1):
    """Retrieves chronological lifecycle audit events for a scheduled post."""
    post = get_scheduled_post_by_id(scheduled_post_id, organization_id=organization_id)
    if not post:
        return None

    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT pal.*, u.username as changed_by_username "
            "FROM post_audit_logs pal "
            "LEFT JOIN users u ON pal.changed_by = u.id "
            "WHERE pal.scheduled_post_id = ? AND pal.organization_id = ? "
            "ORDER BY pal.created_at ASC, pal.id ASC",
            (scheduled_post_id, organization_id)
        ).fetchall()
        return [dict(r) for r in rows]

def transition_post_status(schedule_id, to_status, user_id=None, reason=None, metadata=None,
                           organization_id=1, expected_from_status=None):
    """
    Safely and atomically transitions a post's lifecycle state according to business rules.
    Enforces optimistic locking conditional updates, records approvals/rejections,
    and logs audit events in the SAME database transaction.
    """
    if to_status not in VALID_POST_STATUSES:
        raise ValueError(f"Invalid target status: '{to_status}'.")

    with get_db_connection() as conn:
        post = conn.execute(
            "SELECT * FROM scheduled_posts WHERE id = ? AND organization_id = ?",
            (schedule_id, organization_id)
        ).fetchone()
        if not post:
            raise ValueError(f"Scheduled post #{schedule_id} does not exist or does not belong to active organization.")

        current_status = post['status'] or 'draft'
        if expected_from_status and current_status != expected_from_status:
            raise ValueError(
                f"Conflict: post #{schedule_id} is currently in status '{current_status}', "
                f"expected '{expected_from_status}'."
            )

        if current_status == to_status:
            return dict(post)

        allowed = VALID_TRANSITIONS.get(current_status, set())
        if to_status not in allowed:
            raise ValueError(f"Illegal lifecycle transition: cannot move post #{schedule_id} from '{current_status}' to '{to_status}'.")

        if to_status == 'rejected' and (not reason or not str(reason).strip()):
            raise ValueError("A specific rejection reason is mandatory when rejecting content.")

        now_str = _utcnow().strftime("%Y-%m-%d %H:%M:%S")
        updates = ["status = ?", "updated_at = ?"]
        params = [to_status, now_str]

        if to_status in ('approved', 'scheduled'):
            if current_status == 'pending_approval' or not post['approved_by']:
                updates.append("approved_by = ?")
                params.append(user_id)
                updates.append("approved_at = ?")
                params.append(now_str)
            updates.append("rejection_reason = NULL")
        elif to_status == 'rejected':
            updates.append("rejection_reason = ?")
            params.append(reason.strip())
        elif to_status == 'draft':
            updates.append("rejection_reason = NULL")

        query = f"UPDATE scheduled_posts SET {', '.join(updates)} WHERE id = ? AND organization_id = ? AND status = ?"
        params.extend([schedule_id, organization_id, current_status])

        res = conn.execute(query, tuple(params))
        if res.rowcount == 0:
            raise ValueError(
                f"Conflict: Concurrent modification detected on post #{schedule_id}. "
                f"Post status changed from '{current_status}' during transition."
            )

        log_post_transition(
            scheduled_post_id=schedule_id,
            from_status=current_status,
            to_status=to_status,
            changed_by=user_id,
            reason=reason,
            metadata=metadata,
            organization_id=organization_id,
            conn=conn
        )
        conn.commit()

    return get_scheduled_post_by_id(schedule_id, organization_id=organization_id)

def retry_failed_post(schedule_id, user_id=None, organization_id=1):
    """Resets a failed post back into the 'scheduled' queue."""
    post = get_scheduled_post_by_id(schedule_id, organization_id=organization_id)
    if not post:
        raise ValueError(f"Scheduled post #{schedule_id} not found.")
    if post['status'] != 'failed':
        raise ValueError(f"Only posts in 'failed' status can be retried. Current status is '{post['status']}'.")

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET status = 'scheduled', retry_count = 0, error_message = NULL, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND organization_id = ?",
            (schedule_id, organization_id)
        )
        log_post_transition(
            scheduled_post_id=schedule_id,
            from_status='failed',
            to_status='scheduled',
            changed_by=user_id,
            reason='Manual retry requested by user',
            organization_id=organization_id,
            conn=conn
        )
        conn.commit()

    return get_scheduled_post_by_id(schedule_id, organization_id=organization_id)

# --- AI Marketing Studio: Brand Marketing Profiles, Campaigns & Content Drafts ---

def get_brand_marketing_profile(brand_id, organization_id=1):
    """Retrieves the marketing profile for a brand, ensuring tenant isolation."""
    validate_brand_ownership(brand_id, organization_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM brand_marketing_profiles WHERE organization_id = ? AND brand_id = ?",
            (organization_id, int(brand_id))
        ).fetchone()
        return dict(row) if row else None

def upsert_brand_marketing_profile(brand_id, organization_id=1, positioning=None,
                                   target_audiences=None, target_markets=None, languages=None,
                                   voice_and_tone=None, messaging_guidelines=None,
                                   approved_product_facts=None, prohibited_claims=None,
                                   preferred_ctas=None, website_and_social_links=None):
    """Creates or updates a brand marketing profile within the organization."""
    validate_brand_ownership(brand_id, organization_id)
    b_id = int(brand_id)

    def _to_str(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val).strip()

    pos = _to_str(positioning)
    aud = _to_str(target_audiences)
    mkt = _to_str(target_markets)
    lng = _to_str(languages)
    vnt = _to_str(voice_and_tone)
    msg = _to_str(messaging_guidelines)
    facts = _to_str(approved_product_facts)
    prohib = _to_str(prohibited_claims)
    ctas = _to_str(preferred_ctas)
    links = _to_str(website_and_social_links)

    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM brand_marketing_profiles WHERE organization_id = ? AND brand_id = ?",
            (organization_id, b_id)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE brand_marketing_profiles SET "
                "positioning = COALESCE(?, positioning), "
                "target_audiences = COALESCE(?, target_audiences), "
                "target_markets = COALESCE(?, target_markets), "
                "languages = COALESCE(?, languages), "
                "voice_and_tone = COALESCE(?, voice_and_tone), "
                "messaging_guidelines = COALESCE(?, messaging_guidelines), "
                "approved_product_facts = COALESCE(?, approved_product_facts), "
                "prohibited_claims = COALESCE(?, prohibited_claims), "
                "preferred_ctas = COALESCE(?, preferred_ctas), "
                "website_and_social_links = COALESCE(?, website_and_social_links), "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE organization_id = ? AND brand_id = ?",
                (pos, aud, mkt, lng, vnt, msg, facts, prohib, ctas, links, organization_id, b_id)
            )
            profile_id = existing['id']
        else:
            if is_postgres():
                cur = conn.execute(
                    "INSERT INTO brand_marketing_profiles (organization_id, brand_id, positioning, "
                    "target_audiences, target_markets, languages, voice_and_tone, messaging_guidelines, "
                    "approved_product_facts, prohibited_claims, preferred_ctas, website_and_social_links) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                    (organization_id, b_id, pos or '', aud or '', mkt or '', lng or 'en',
                     vnt or '', msg or '', facts or '', prohib or '', ctas or '', links or '')
                )
                profile_id = cur.fetchone()['id']
            else:
                cur = conn.execute(
                    "INSERT INTO brand_marketing_profiles (organization_id, brand_id, positioning, "
                    "target_audiences, target_markets, languages, voice_and_tone, messaging_guidelines, "
                    "approved_product_facts, prohibited_claims, preferred_ctas, website_and_social_links) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (organization_id, b_id, pos or '', aud or '', mkt or '', lng or 'en',
                     vnt or '', msg or '', facts or '', prohib or '', ctas or '', links or '')
                )
                profile_id = cur.lastrowid
        conn.commit()

        row = conn.execute(
            "SELECT * FROM brand_marketing_profiles WHERE id = ? AND organization_id = ?",
            (profile_id, organization_id)
        ).fetchone()
        return dict(row) if row else None

def validate_campaign_ownership(campaign_id, organization_id=1):
    """Validates that campaign exists and belongs to the given organization."""
    try:
        c_id = int(campaign_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid campaign ID '{campaign_id}'. Must be an integer.")
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE id = ?",
            (c_id,)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Campaign #{c_id} does not exist.")
        if row['organization_id'] != organization_id:
            raise TenantIsolationError(f"Campaign #{c_id} belongs to a different organization and cannot be accessed.")
        return dict(row)

def create_campaign(organization_id, brand_id, name, objective, brief,
                    campaign_type='social', target_audience=None, target_markets=None,
                    languages=None, start_date=None, end_date=None, status='draft',
                    budget=None, created_by=None):
    """Creates a new marketing campaign strictly scoped to organization and brand."""
    validate_brand_ownership(brand_id, organization_id)
    if not name or not str(name).strip():
        raise ValueError("Campaign name is required and cannot be empty.")
    if not objective or not str(objective).strip():
        raise ValueError("Campaign objective is required and cannot be empty.")
    if not brief or not str(brief).strip():
        raise ValueError("Campaign brief is required and cannot be empty.")

    clean_name = str(name).strip()
    clean_obj = str(objective).strip()
    clean_brief = str(brief).strip()
    b_id = int(brand_id)

    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO campaigns (organization_id, brand_id, name, objective, campaign_type, "
                "target_audience, target_markets, languages, brief, start_date, end_date, "
                "status, budget, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (organization_id, b_id, clean_name, clean_obj, campaign_type or 'social',
                 target_audience or '', target_markets or '', languages or '', clean_brief,
                 start_date, end_date, status or 'draft', budget, created_by)
            )
            cid = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO campaigns (organization_id, brand_id, name, objective, campaign_type, "
                "target_audience, target_markets, languages, brief, start_date, end_date, "
                "status, budget, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (organization_id, b_id, clean_name, clean_obj, campaign_type or 'social',
                 target_audience or '', target_markets or '', languages or '', clean_brief,
                 start_date, end_date, status or 'draft', budget, created_by)
            )
            cid = cur.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
        return dict(row) if row else None

def get_campaign_by_id(campaign_id, organization_id=1):
    """Retrieves a campaign by ID scoped to organization."""
    try:
        c_id = int(campaign_id)
    except (ValueError, TypeError):
        return None
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT c.*, b.name as brand_name, b.slug as brand_slug "
            "FROM campaigns c "
            "LEFT JOIN brands b ON c.brand_id = b.id "
            "WHERE c.id = ? AND c.organization_id = ?",
            (c_id, organization_id)
        ).fetchone()
        return dict(row) if row else None

def list_campaigns(organization_id=1, brand_id=None, status=None, limit=100, offset=0):
    """Lists campaigns for an organization with optional brand and status filtering."""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))

    with get_db_connection() as conn:
        query = (
            "SELECT c.*, b.name as brand_name, b.slug as brand_slug "
            "FROM campaigns c "
            "LEFT JOIN brands b ON c.brand_id = b.id "
            "WHERE c.organization_id = ?"
        )
        params = [organization_id]
        if brand_id:
            query += " AND c.brand_id = ?"
            params.append(int(brand_id))
        if status:
            query += " AND c.status = ?"
            params.append(str(status).strip())

        query += " ORDER BY c.updated_at DESC, c.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

def update_campaign(campaign_id, organization_id=1, name=None, objective=None,
                    brief=None, campaign_type=None, target_audience=None,
                    target_markets=None, languages=None, start_date=None,
                    end_date=None, status=None, budget=None):
    """Updates an existing campaign ensuring tenant isolation."""
    validate_campaign_ownership(campaign_id, organization_id)
    c_id = int(campaign_id)

    updates = []
    params = []
    if name is not None:
        if not str(name).strip():
            raise ValueError("Campaign name cannot be empty.")
        updates.append("name = ?")
        params.append(str(name).strip())
    if objective is not None:
        if not str(objective).strip():
            raise ValueError("Campaign objective cannot be empty.")
        updates.append("objective = ?")
        params.append(str(objective).strip())
    if brief is not None:
        if not str(brief).strip():
            raise ValueError("Campaign brief cannot be empty.")
        updates.append("brief = ?")
        params.append(str(brief).strip())
    if campaign_type is not None:
        updates.append("campaign_type = ?")
        params.append(str(campaign_type).strip())
    if target_audience is not None:
        updates.append("target_audience = ?")
        params.append(str(target_audience).strip())
    if target_markets is not None:
        updates.append("target_markets = ?")
        params.append(str(target_markets).strip())
    if languages is not None:
        updates.append("languages = ?")
        params.append(str(languages).strip())
    if start_date is not None:
        updates.append("start_date = ?")
        params.append(str(start_date).strip() if start_date else None)
    if end_date is not None:
        updates.append("end_date = ?")
        params.append(str(end_date).strip() if end_date else None)
    if status is not None:
        updates.append("status = ?")
        params.append(str(status).strip())
    if budget is not None:
        updates.append("budget = ?")
        params.append(str(budget).strip() if budget else None)

    if not updates:
        return get_campaign_by_id(c_id, organization_id=organization_id)

    updates.append("updated_at = CURRENT_TIMESTAMP")
    sql = f"UPDATE campaigns SET {', '.join(updates)} WHERE id = ? AND organization_id = ?"
    params.extend([c_id, organization_id])

    with get_db_connection() as conn:
        conn.execute(sql, tuple(params))
        conn.commit()

    return get_campaign_by_id(c_id, organization_id=organization_id)

def delete_campaign(campaign_id, organization_id=1):
    """Deletes a campaign and its associated content drafts within the organization."""
    validate_campaign_ownership(campaign_id, organization_id)
    c_id = int(campaign_id)
    with get_db_connection() as conn:
        conn.execute("DELETE FROM content_drafts WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        res = conn.execute("DELETE FROM campaigns WHERE id = ? AND organization_id = ?", (c_id, organization_id))
        conn.commit()
        return res.rowcount > 0

VALID_DRAFT_PLATFORMS = frozenset({'facebook', 'instagram', 'linkedin', 'x', 'whatsapp'})

def create_content_draft(organization_id, brand_id, campaign_id, target_platform,
                         caption, headline=None, hashtags=None, call_to_action=None,
                         language='en', content_format='post', ai_provider=None,
                         ai_model=None, metadata=None, status='draft', created_by=None):
    """Creates a new content draft under an active campaign."""
    camp = validate_campaign_ownership(campaign_id, organization_id)
    if camp['brand_id'] != int(brand_id):
        raise ValueError(f"Brand #{brand_id} does not match campaign #{campaign_id}'s assigned brand #{camp['brand_id']}.")

    clean_platform = str(target_platform).strip().lower()
    if clean_platform not in VALID_DRAFT_PLATFORMS:
        raise ValueError(f"Invalid target_platform: '{target_platform}'. Must be one of: {', '.join(sorted(VALID_DRAFT_PLATFORMS))}.")

    if not caption or not str(caption).strip():
        raise ValueError("Draft caption/body is required and cannot be empty.")

    clean_caption = str(caption).strip()
    meta_str = json.dumps(metadata) if isinstance(metadata, (dict, list)) else (str(metadata) if metadata else None)

    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO content_drafts (organization_id, brand_id, campaign_id, target_platform, "
                "language, content_format, headline, caption, hashtags, call_to_action, "
                "ai_provider, ai_model, metadata, status, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (organization_id, int(brand_id), int(campaign_id), clean_platform,
                 language or 'en', content_format or 'post', headline, clean_caption,
                 hashtags, call_to_action, ai_provider, ai_model, meta_str, status or 'draft', created_by)
            )
            did = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO content_drafts (organization_id, brand_id, campaign_id, target_platform, "
                "language, content_format, headline, caption, hashtags, call_to_action, "
                "ai_provider, ai_model, metadata, status, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (organization_id, int(brand_id), int(campaign_id), clean_platform,
                 language or 'en', content_format or 'post', headline, clean_caption,
                 hashtags, call_to_action, ai_provider, ai_model, meta_str, status or 'draft', created_by)
            )
            did = cur.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (did,)).fetchone()
        return dict(row) if row else None

def get_content_draft_by_id(draft_id, organization_id=1):
    """Retrieves a content draft by ID scoped to organization."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        return None
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT cd.*, c.name as campaign_name, b.name as brand_name "
            "FROM content_drafts cd "
            "LEFT JOIN campaigns c ON cd.campaign_id = c.id "
            "LEFT JOIN brands b ON cd.brand_id = b.id "
            "WHERE cd.id = ? AND cd.organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        return dict(row) if row else None

def list_content_drafts(organization_id=1, campaign_id=None, brand_id=None,
                        target_platform=None, status=None, limit=100, offset=0):
    """Lists content drafts with tenant isolation and optional filters."""
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))

    with get_db_connection() as conn:
        query = (
            "SELECT cd.*, c.name as campaign_name, b.name as brand_name "
            "FROM content_drafts cd "
            "LEFT JOIN campaigns c ON cd.campaign_id = c.id "
            "LEFT JOIN brands b ON cd.brand_id = b.id "
            "WHERE cd.organization_id = ?"
        )
        params = [organization_id]
        if campaign_id:
            query += " AND cd.campaign_id = ?"
            params.append(int(campaign_id))
        if brand_id:
            query += " AND cd.brand_id = ?"
            params.append(int(brand_id))
        if target_platform:
            query += " AND cd.target_platform = ?"
            params.append(str(target_platform).strip().lower())
        if status:
            query += " AND cd.status = ?"
            params.append(str(status).strip())

        query += " ORDER BY cd.updated_at DESC, cd.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

def update_content_draft(draft_id, organization_id=1, caption=None, headline=None,
                         hashtags=None, call_to_action=None, status=None,
                         content_format=None, metadata=None):
    """Updates a content draft ensuring organization ownership."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid draft ID '{draft_id}'.")

    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not existing:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

        updates = []
        params = []
        if caption is not None:
            if not str(caption).strip():
                raise ValueError("Caption cannot be empty.")
            updates.append("caption = ?")
            params.append(str(caption).strip())
        if headline is not None:
            updates.append("headline = ?")
            params.append(str(headline).strip() if headline else None)
        if hashtags is not None:
            updates.append("hashtags = ?")
            params.append(str(hashtags).strip() if hashtags else None)
        if call_to_action is not None:
            updates.append("call_to_action = ?")
            params.append(str(call_to_action).strip() if call_to_action else None)
        if status is not None:
            updates.append("status = ?")
            params.append(str(status).strip())
        if content_format is not None:
            updates.append("content_format = ?")
            params.append(str(content_format).strip())
        if metadata is not None:
            meta_str = json.dumps(metadata) if isinstance(metadata, (dict, list)) else str(metadata)
            updates.append("metadata = ?")
            params.append(meta_str)

        if not updates:
            return dict(existing)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"UPDATE content_drafts SET {', '.join(updates)} WHERE id = ? AND organization_id = ?"
        params.extend([d_id, organization_id])

        conn.execute(sql, tuple(params))
        conn.commit()

        row = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (d_id,)).fetchone()
        return dict(row) if row else None

def delete_content_draft(draft_id, organization_id=1):
    """Deletes a content draft strictly scoped to organization."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        return False
    with get_db_connection() as conn:
        res = conn.execute("DELETE FROM content_drafts WHERE id = ? AND organization_id = ?", (d_id, organization_id))
        conn.commit()
        return res.rowcount > 0


