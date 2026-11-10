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
import re
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

class ConcurrencyConflictError(ValueError):
    """Raised when an operation encounters an optimistic concurrency conflict."""
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
        ("idx_cdr_draft_rev", "CREATE INDEX IF NOT EXISTS idx_cdr_draft_rev ON content_draft_revisions(organization_id, draft_id, revision_number)"),
        ("idx_cdr_campaign", "CREATE INDEX IF NOT EXISTS idx_cdr_campaign ON content_draft_revisions(organization_id, campaign_id)"),
        ("idx_campaign_strategies_camp", "CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_strategies_camp ON campaign_strategies(organization_id, campaign_id)"),
        ("idx_ai_usage_org_created", "CREATE INDEX IF NOT EXISTS idx_ai_usage_org_created ON ai_usage_logs(organization_id, created_at)"),
        ("idx_content_plans_org_camp", "CREATE INDEX IF NOT EXISTS idx_content_plans_org_camp ON content_plans(organization_id, campaign_id)"),
        ("idx_plan_entries_plan", "CREATE INDEX IF NOT EXISTS idx_plan_entries_plan ON content_plan_entries(organization_id, plan_id, suggested_date)"),
        ("idx_media_assets_org_brand", "CREATE INDEX IF NOT EXISTS idx_media_assets_org_brand ON media_assets(organization_id, brand_id)"),
        ("idx_media_assets_org_created", "CREATE INDEX IF NOT EXISTS idx_media_assets_org_created ON media_assets(organization_id, created_at)"),
        ("idx_sub_plans_code", "CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_plans_code ON subscription_plans(code)"),
        ("idx_org_subs_org", "CREATE UNIQUE INDEX IF NOT EXISTS idx_org_subs_org ON organization_subscriptions(organization_id)"),
        ("idx_social_accounts_org_brand", "CREATE INDEX IF NOT EXISTS idx_social_accounts_org_brand ON social_accounts(organization_id, brand_id, platform)"),
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
                current_revision INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 12. Content draft revisions table (immutable versioned audit history)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS content_draft_revisions (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                draft_id INTEGER NOT NULL,
                revision_number INTEGER NOT NULL,
                headline TEXT,
                caption TEXT NOT NULL,
                hashtags TEXT,
                call_to_action TEXT,
                content_format TEXT DEFAULT 'post',
                ai_provider TEXT,
                ai_model TEXT,
                metadata TEXT,
                change_source TEXT DEFAULT 'manual_edit',
                change_summary TEXT,
                edited_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 13. Campaign strategies table (brand-aware comprehensive strategy)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS campaign_strategies (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                positioning TEXT,
                primary_objective TEXT,
                target_segments TEXT,
                pain_points TEXT,
                value_proposition TEXT,
                core_message TEXT,
                supporting_messages TEXT,
                content_themes TEXT,
                recommended_channels TEXT,
                calls_to_action TEXT,
                suggested_phases TEXT,
                posting_frequency TEXT,
                success_metrics TEXT,
                risks_and_verification TEXT,
                raw_response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 14. AI usage logs table (usage quotas, token tracking, and billing)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS ai_usage_logs (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER,
                campaign_id INTEGER,
                provider TEXT NOT NULL,
                model TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_estimate REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 15. Content plans table (weekly and monthly editorial plans)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS content_plans (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                period_type TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                posting_frequency TEXT,
                status TEXT DEFAULT 'draft',
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 16. Content plan entries table (individual calendar entries in a plan)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS content_plan_entries (
                id {auto_id},
                plan_id INTEGER NOT NULL,
                organization_id INTEGER NOT NULL,
                brand_id INTEGER NOT NULL,
                campaign_id INTEGER NOT NULL,
                suggested_date TEXT NOT NULL,
                platform TEXT NOT NULL,
                theme TEXT,
                content_format TEXT DEFAULT 'post',
                topic TEXT NOT NULL,
                headline TEXT,
                call_to_action TEXT,
                status TEXT DEFAULT 'planned',
                converted_draft_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')


        # 17. Media assets table (central organization and brand media library)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS media_assets (
                id {auto_id},
                organization_id INTEGER NOT NULL,
                brand_id INTEGER,
                campaign_id INTEGER,
                filename TEXT NOT NULL,
                original_name TEXT,
                file_type TEXT DEFAULT 'image',
                file_size INTEGER DEFAULT 0,
                mime_type TEXT,
                tags TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')


        # 18. Subscription plans table
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id {auto_id},
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                max_brands INTEGER DEFAULT 5,
                max_campaigns INTEGER DEFAULT 10,
                max_monthly_posts INTEGER DEFAULT 500,
                max_monthly_ai_tokens INTEGER DEFAULT 100000,
                price_cents INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 19. Organization subscriptions table
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS organization_subscriptions (
                id {auto_id},
                organization_id INTEGER UNIQUE NOT NULL,
                plan_code TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                current_period_start TIMESTAMP,
                current_period_end TIMESTAMP,
                cancel_at_period_end INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 20. Connected social accounts table (Multi-brand & platform credentials)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS social_accounts (
                id {auto_id},
                organization_id INTEGER NOT NULL DEFAULT 1,
                brand_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                account_name TEXT NOT NULL,
                account_identifier TEXT NOT NULL,
                access_token_encrypted TEXT,
                refresh_token_encrypted TEXT,
                token_expires_at TIMESTAMP,
                status TEXT DEFAULT 'connected',
                permissions_scope TEXT,
                last_verified_at TIMESTAMP,
                app_identifier TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, brand_id, platform, account_identifier)
            )
        ''')

        conn.commit()

        # Non-destructive migrations for existing tables
        _ensure_column_exists(conn, 'organizations', 'timezone', "TEXT DEFAULT 'UTC'")
        _ensure_column_exists(conn, 'posts', 'organization_id', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'posts', 'brand_id', 'INTEGER')
        _ensure_column_exists(conn, 'users', 'organization_id', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'users', 'is_active', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'users', 'email', 'TEXT')
        _ensure_column_exists(conn, 'scheduled_posts', 'external_post_id', 'TEXT')

        # Seed default commercial subscription plans
        default_plans = [
            ('starter', 'Starter Tier', 3, 5, 200, 50000, 2900),
            ('growth', 'Growth Tier', 10, 25, 1000, 250000, 7900),
            ('enterprise', 'Enterprise Tier', 100, 500, 10000, 2000000, 29900)
        ]
        for p_code, p_name, p_brands, p_camps, p_posts, p_tokens, p_price in default_plans:
            try:
                if is_postgres():
                    conn.execute(
                        "INSERT INTO subscription_plans (code, name, max_brands, max_campaigns, "
                        "max_monthly_posts, max_monthly_ai_tokens, price_cents) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (code) DO NOTHING",
                        (p_code, p_name, p_brands, p_camps, p_posts, p_tokens, p_price)
                    )
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO subscription_plans (code, name, max_brands, max_campaigns, "
                        "max_monthly_posts, max_monthly_ai_tokens, price_cents) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (p_code, p_name, p_brands, p_camps, p_posts, p_tokens, p_price)
                    )
            except Exception as e:
                logger.warning(f"Notice seeding plan {p_code}: {e}")
        conn.commit()

        _ensure_column_exists(conn, 'scheduled_posts', 'approved_by', 'INTEGER')
        _ensure_column_exists(conn, 'scheduled_posts', 'approved_at', 'TIMESTAMP')
        _ensure_column_exists(conn, 'scheduled_posts', 'rejection_reason', 'TEXT')
        _ensure_column_exists(conn, 'scheduled_posts', 'campaign_id', 'INTEGER')
        _ensure_column_exists(conn, 'scheduled_posts', 'draft_id', 'INTEGER')
        _ensure_column_exists(conn, 'content_drafts', 'media_asset_id', 'INTEGER')
        _ensure_column_exists(conn, 'content_draft_revisions', 'media_asset_id', 'INTEGER')
        _ensure_column_exists(conn, 'content_drafts', 'current_revision', 'INTEGER DEFAULT 1')
        _ensure_column_exists(conn, 'content_draft_revisions', 'ai_provider', 'TEXT')
        _ensure_column_exists(conn, 'content_draft_revisions', 'ai_model', 'TEXT')
        _ensure_column_exists(conn, 'content_draft_revisions', 'metadata', 'TEXT')

        # Non-destructive backfill of revision 1 for legacy drafts lacking revisions
        conn.execute('''
            INSERT INTO content_draft_revisions (
                organization_id, brand_id, campaign_id, draft_id,
                revision_number, headline, caption, hashtags, call_to_action,
                content_format, ai_provider, ai_model, metadata,
                change_source, change_summary, edited_by, created_at
            )
            SELECT
                cd.organization_id, cd.brand_id, cd.campaign_id, cd.id,
                COALESCE(cd.current_revision, 1), cd.headline, cd.caption, cd.hashtags, cd.call_to_action,
                COALESCE(cd.content_format, 'post'),
                cd.ai_provider, cd.ai_model, cd.metadata,
                CASE WHEN cd.ai_provider IS NOT NULL THEN 'ai_generated' ELSE 'manual_creation' END,
                'Initial draft creation',
                cd.created_by,
                cd.created_at
            FROM content_drafts cd
            WHERE NOT EXISTS (
                SELECT 1 FROM content_draft_revisions cdr
                WHERE cdr.draft_id = cd.id
            )
        ''')

        # Create indexes
        _ensure_indexes(conn)

    # Seed default tasks if empty
    init_default_tasks()

    # Seed default organizations & brands
    init_default_organizations_and_brands()

    # Seed default connected social accounts
    init_default_social_accounts()

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

def init_default_social_accounts():
    """Initializes connected social accounts mapped to brand workspaces."""
    with get_db_connection() as conn:
        b1 = conn.execute("SELECT id FROM brands WHERE organization_id = 1 AND id = 1").fetchone()
        b5 = conn.execute("SELECT id FROM brands WHERE organization_id = 1 AND (slug = 'phoenix-by-gaatha' OR id = 5)").fetchone()
        b1_id = b1['id'] if b1 else 1
        b5_id = b5['id'] if b5 else b1_id

        default_accounts = [
            (1, b1_id, 'facebook', 'GAATHA Suite', str(config.FB_PAGE_ID_SUITE or '967550829768297'), 'connected', 'pages_manage_posts,pages_read_engagement', None),
            (1, b1_id, 'instagram', '@nexora_suite', str(config.INSTA_ID_SUITE or '17841471822022390'), 'connected', 'instagram_basic,instagram_content_publish', None),
            (1, b1_id, 'linkedin', 'Aidni Global LLP', '145240694', 'connected', 'w_member_social,w_organization_social', 'aidni_global'),
            (1, b1_id, 'linkedin', 'Gaatha Ventures Sh.p.k.', '145250613', 'connected', 'w_member_social,w_organization_social', 'gaatha_ventures'),
            (1, b1_id, 'whatsapp', 'GAATHA WhatsApp Business', str(getattr(config, 'WHATSAPP_PHONE_NUMBER_ID', None) or '103290292839210'), 'connected', 'whatsapp_business_messaging', None),
            (1, b5_id, 'facebook', 'Phoenix International', str(config.FB_PAGE_ID_PHOENIX or '100089146197321'), 'connected', 'pages_manage_posts,pages_read_engagement', None),
            (1, b5_id, 'instagram', '@phoenixbygaatha', str(config.INSTA_ID_PHOENIX or '17841405309211880'), 'connected', 'instagram_basic,instagram_content_publish', None),
        ]

        for org_id, brand_id, platform, acct_name, acct_id, status, scope, app_id in default_accounts:
            try:
                if is_postgres():
                    conn.execute('''
                        INSERT INTO social_accounts (
                            organization_id, brand_id, platform, account_name,
                            account_identifier, status, permissions_scope, app_identifier
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (organization_id, brand_id, platform, account_identifier) DO UPDATE SET
                            account_name = EXCLUDED.account_name,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP
                    ''', (org_id, brand_id, platform, acct_name, acct_id, status, scope, app_id))
                else:
                    conn.execute('''
                        INSERT INTO social_accounts (
                            organization_id, brand_id, platform, account_name,
                            account_identifier, status, permissions_scope, app_identifier
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(organization_id, brand_id, platform, account_identifier) DO UPDATE SET
                            account_name = excluded.account_name,
                            status = excluded.status,
                            updated_at = CURRENT_TIMESTAMP
                    ''', (org_id, brand_id, platform, acct_name, acct_id, status, scope, app_id))
            except Exception as e:
                logger.warning(f"Notice seeding social account {platform}:{acct_id}: {e}")
        conn.commit()

def get_social_accounts(organization_id=1, brand_id=None, platform=None):
    """
    Retrieves connected social accounts scoped to organization and optional brand.
    Strictly redacts/excludes credentials and secret tokens.
    """
    query = '''
        SELECT sa.id, sa.organization_id, sa.brand_id, b.name as brand_name,
               sa.platform, sa.account_name, sa.account_identifier,
               sa.token_expires_at, sa.status, sa.permissions_scope,
               sa.last_verified_at, sa.app_identifier, sa.created_at, sa.updated_at
        FROM social_accounts sa
        LEFT JOIN brands b ON sa.brand_id = b.id
        WHERE sa.organization_id = ?
    '''
    params = [organization_id]
    if brand_id is not None:
        query += " AND sa.brand_id = ?"
        params.append(brand_id)
    if platform:
        query += " AND sa.platform = ?"
        params.append(platform.lower())
    query += " ORDER BY sa.brand_id, sa.platform, sa.id"

    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

def get_social_account_for_brand(organization_id, brand_id, platform, account_identifier=None):
    """Retrieves specific connected account for backend execution."""
    query = '''
        SELECT * FROM social_accounts
        WHERE organization_id = ? AND brand_id = ? AND platform = ?
    '''
    params = [organization_id, brand_id, platform.lower()]
    if account_identifier:
        query += " AND account_identifier = ?"
        params.append(str(account_identifier))
    query += " LIMIT 1"

    with get_db_connection() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

def upsert_social_account(organization_id, brand_id, platform, account_name, account_identifier,
                          status='connected', permissions_scope=None, app_identifier=None,
                          token_expires_at=None, access_token=None):
    """Inserts or updates a connected social account."""
    with get_db_connection() as conn:
        if is_postgres():
            conn.execute('''
                INSERT INTO social_accounts (
                    organization_id, brand_id, platform, account_name,
                    account_identifier, status, permissions_scope, app_identifier,
                    token_expires_at, access_token_encrypted, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, brand_id, platform, account_identifier) DO UPDATE SET
                    account_name = EXCLUDED.account_name,
                    status = EXCLUDED.status,
                    permissions_scope = COALESCE(EXCLUDED.permissions_scope, social_accounts.permissions_scope),
                    token_expires_at = COALESCE(EXCLUDED.token_expires_at, social_accounts.token_expires_at),
                    access_token_encrypted = COALESCE(EXCLUDED.access_token_encrypted, social_accounts.access_token_encrypted),
                    updated_at = CURRENT_TIMESTAMP
            ''', (organization_id, brand_id, platform.lower(), account_name, str(account_identifier),
                  status, permissions_scope, app_identifier, token_expires_at, access_token))
        else:
            conn.execute('''
                INSERT INTO social_accounts (
                    organization_id, brand_id, platform, account_name,
                    account_identifier, status, permissions_scope, app_identifier,
                    token_expires_at, access_token_encrypted, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(organization_id, brand_id, platform, account_identifier) DO UPDATE SET
                    account_name = excluded.account_name,
                    status = excluded.status,
                    permissions_scope = COALESCE(excluded.permissions_scope, social_accounts.permissions_scope),
                    token_expires_at = COALESCE(excluded.token_expires_at, social_accounts.token_expires_at),
                    access_token_encrypted = COALESCE(excluded.access_token_encrypted, social_accounts.access_token_encrypted),
                    updated_at = CURRENT_TIMESTAMP
            ''', (organization_id, brand_id, platform.lower(), account_name, str(account_identifier),
                  status, permissions_scope, app_identifier, token_expires_at, access_token))
        conn.commit()
        return True

def delete_social_account(account_id, organization_id=1):
    """Disconnects and removes a social account respecting tenant boundaries."""
    with get_db_connection() as conn:
        res = conn.execute(
            "DELETE FROM social_accounts WHERE id = ? AND organization_id = ?",
            (account_id, organization_id)
        )
        conn.commit()
        return res.rowcount > 0

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

def update_user_password(username, new_password):
    """
    Securely updates an existing user's password hash using the project's secure hashing.
    Enforces that the user account must exist in the database.
    Never prints or logs the plain password or the hash.
    """
    clean_user = str(username).strip()
    user = get_user_by_username(clean_user)
    if not user:
        raise ValueError(f"User '{clean_user}' does not exist.")

    pw_hash = generate_password_hash(new_password)
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user['id']))
        conn.commit()
    return True

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

RETIRED_LEGACY_CHANNELS = {'tour', 'nz', 'gaatha', 'insta'}
CANONICAL_CREATION_PLATFORMS = {'facebook', 'instagram', 'linkedin', 'whatsapp', 'x'}
HISTORICAL_QUERY_PLATFORMS = CANONICAL_CREATION_PLATFORMS | RETIRED_LEGACY_CHANNELS

def add_post(post_type, message, image_filename, organization_id=1, brand_id=None):
    clean_type = str(post_type).strip().lower()
    if clean_type in RETIRED_LEGACY_CHANNELS:
        raise ValueError(f"Legacy channel '{clean_type}' is permanently retired and cannot be created.")
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

    clean_post_type = str(post_type).strip().lower()
    if clean_post_type == 'twitter':
        clean_post_type = 'x'
    if clean_post_type in RETIRED_LEGACY_CHANNELS:
        raise ValueError(
            f"Legacy channel '{clean_post_type}' is permanently retired and cannot be scheduled. "
            f"Please use a canonical platform ({', '.join(sorted(CANONICAL_CREATION_PLATFORMS))})."
        )
    if clean_post_type not in CANONICAL_CREATION_PLATFORMS:
        raise ValueError(f"Invalid post_type: '{post_type}'. Must be one of: {', '.join(sorted(CANONICAL_CREATION_PLATFORMS))}.")
    post_type = clean_post_type
    camp_id_val = kwargs.get('campaign_id')
    draft_id_val = kwargs.get('draft_id')

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
                "scheduled_for, timezone, status, idempotency_key, created_by, campaign_id, draft_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (organization_id, brand_id, post_type, post_id, msg_val, safe_image,
                 scheduled_utc_str, resolved_tz, initial_status, idempotency_key, created_by, camp_id_val, draft_id_val)
            )
            row = cur.fetchone()
            conn.commit()
            new_id = row['id']
        else:
            cur = conn.execute(
                "INSERT INTO scheduled_posts (organization_id, brand_id, post_type, post_id, message, image_filename, "
                "scheduled_for, timezone, status, idempotency_key, created_by, campaign_id, draft_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (organization_id, brand_id, post_type, post_id, msg_val, safe_image,
                 scheduled_utc_str, resolved_tz, initial_status, idempotency_key, created_by, camp_id_val, draft_id_val)
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

def record_immediate_publication(post_type, message, external_post_id, brand_id=None,
                                 organization_id=1, created_by=1, image_filename=None,
                                 idempotency_key=None, permalink_url=None,
                                 provider_response=None, reason=None):
    """
    Idempotently records an immediate live publication in scheduled_posts and post_audit_logs
    so it appears in PostPilot publishing history, audit trails, and dashboard KPIs.
    """
    if post_type not in HISTORICAL_QUERY_PLATFORMS:
        raise ValueError(f"Unsupported post_type: '{post_type}'.")
    if brand_id is not None:
        validate_brand_ownership(brand_id, organization_id)
    safe_image = validate_media_reference(image_filename) if image_filename else None

    now_utc = _utcnow().strftime('%Y-%m-%d %H:%M:%S')
    if not idempotency_key:
        idempotency_key = f"imm-{organization_id}-{post_type}-{brand_id or 'org'}-{int(time.time())}-{secrets.token_hex(4)}"

    meta = {'mode': 'immediate', 'external_post_id': external_post_id}
    if permalink_url:
        meta['permalink_url'] = permalink_url
    if provider_response is not None:
        meta['provider_response'] = provider_response

    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM scheduled_posts WHERE idempotency_key = ?",
            (idempotency_key,)
        ).fetchone()
        if existing:
            if existing['organization_id'] != organization_id:
                raise ValueError("Idempotency key collision across organizations.")
            return get_scheduled_post_by_id(existing['id'], organization_id=organization_id)

        msg_val = message if message is not None else ""
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, image_filename, "
                "scheduled_for, timezone, status, published_at, external_post_id, idempotency_key, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, 'UTC', 'published', ?, ?, ?, ?) RETURNING id",
                (organization_id, brand_id, post_type, msg_val, safe_image,
                 now_utc, now_utc, external_post_id, idempotency_key, created_by)
            )
            new_id = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, image_filename, "
                "scheduled_for, timezone, status, published_at, external_post_id, idempotency_key, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, 'UTC', 'published', ?, ?, ?, ?)",
                (organization_id, brand_id, post_type, msg_val, safe_image,
                 now_utc, now_utc, external_post_id, idempotency_key, created_by)
            )
            new_id = cur.lastrowid

        log_post_transition(
            scheduled_post_id=new_id,
            from_status=None,
            to_status='published',
            changed_by=created_by,
            reason=reason or 'Immediate live publication via platform adapter',
            metadata=meta,
            organization_id=organization_id,
            conn=conn
        )
        conn.commit()
        return get_scheduled_post_by_id(new_id, post_type=post_type, organization_id=organization_id)

VALID_SCHEDULED_POST_TYPES = HISTORICAL_QUERY_PLATFORMS

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
        clean_post_type = str(post_type).strip().lower()
        if clean_post_type == 'twitter':
            clean_post_type = 'x'
        if clean_post_type not in VALID_SCHEDULED_POST_TYPES:
            raise ValueError(f"Invalid post_type: '{post_type}'. Must be one of: {', '.join(sorted(VALID_SCHEDULED_POST_TYPES))}.")
        post_type = clean_post_type

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

def claim_due_scheduled_posts(worker_id, limit=5, lock_timeout_seconds=300, allowed_platforms=None):
    """
    Atomically claims due scheduled posts across processes without race conditions.
    Also handles stale-lock recovery if a worker crashed while publishing.
    Only claims posts in 'scheduled' status (drafts, pending_approval, rejected, cancelled are NEVER claimed).
    When allowed_platforms is supplied, restricts claiming strictly to those post_types.
    """
    now = _utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    stale_str = (now - timedelta(seconds=lock_timeout_seconds)).strftime("%Y-%m-%d %H:%M:%S")

    platform_filter_sql = ""
    platform_params = []
    if allowed_platforms is not None:
        normalized = [str(p).strip().lower() for p in allowed_platforms if p and str(p).strip()]
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        platform_filter_sql = f" AND post_type IN ({placeholders})"
        platform_params = normalized

    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT id FROM scheduled_posts "
            "WHERE ((status = 'scheduled' AND scheduled_for <= ?) "
            "   OR (status = 'publishing' AND locked_at <= ? AND retry_count < max_retries))"
            f"{platform_filter_sql} "
            "ORDER BY scheduled_for ASC LIMIT ?",
            tuple([now_str, stale_str] + platform_params + [limit])
        )
        candidate_ids = [r['id'] for r in cur.fetchall()]
        claimed = []
        for cid in candidate_ids:
            post_before = conn.execute("SELECT status, organization_id FROM scheduled_posts WHERE id = ?", (cid,)).fetchone()
            res = conn.execute(
                "UPDATE scheduled_posts SET status = 'publishing', locked_by = ?, locked_at = ?, updated_at = ? "
                "WHERE id = ? AND ("
                "  (status = 'scheduled' AND scheduled_for <= ?) OR "
                "  (status = 'publishing' AND (locked_by = ? OR locked_at <= ?))"
                ")"
                f"{platform_filter_sql}",
                tuple([worker_id, now_str, now_str, cid, now_str, worker_id, stale_str] + platform_params)
            )
            if res.rowcount > 0:
                row = conn.execute("SELECT * FROM scheduled_posts WHERE id = ?", (cid,)).fetchone()
                if row:
                    row_dict = dict(row)
                    claimed.append(row_dict)
                    log_post_transition(
                        scheduled_post_id=cid,
                        from_status=post_before['status'] if post_before else 'scheduled',
                        to_status='publishing',
                        reason=f"Claimed by worker {worker_id}",
                        organization_id=row_dict.get('organization_id', 1),
                        conn=conn
                    )
        conn.commit()
        return claimed

def complete_scheduled_post(schedule_id, worker_id, success=True, error_message=None, external_post_id=None):
    """
    Marks a claimed scheduled post as published or failed/retried.
    Enforces worker claim ownership, tenant & channel isolation,
    stores external post IDs upon success,
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
                "UPDATE scheduled_posts SET status = 'published', published_at = ?, external_post_id = COALESCE(?, external_post_id), "
                "locked_by = NULL, locked_at = NULL, updated_at = ? WHERE id = ? AND locked_by = ? AND status = 'publishing'",
                (now_str, external_post_id, now_str, schedule_id, worker_id)
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
                reason='Published successfully',
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

VALID_CAMPAIGN_STATUSES = frozenset({'draft', 'active', 'paused', 'completed', 'archived'})
INITIAL_CAMPAIGN_STATUSES = frozenset({'draft', 'active'})
LEGAL_CAMPAIGN_TRANSITIONS = {
    'draft': frozenset({'active', 'archived'}),
    'active': frozenset({'paused', 'completed', 'archived'}),
    'paused': frozenset({'active', 'completed', 'archived'}),
    'completed': frozenset({'active', 'archived'}),
    'archived': frozenset({'draft', 'active'})
}

VALID_DRAFT_STATUSES = frozenset({
    'draft', 'pending_approval', 'approved', 'scheduled',
    'published', 'rejected', 'failed', 'archived'
})
INITIAL_DRAFT_STATUSES = frozenset({'draft', 'pending_approval'})
PRIVILEGED_DRAFT_STATUSES = frozenset({'approved', 'scheduled', 'published', 'failed'})
LEGAL_DRAFT_TRANSITIONS = {
    'draft': frozenset({'pending_approval', 'archived'}),
    'pending_approval': frozenset({'approved', 'rejected', 'draft', 'archived'}),
    'approved': frozenset({'scheduled', 'draft', 'archived'}),
    'scheduled': frozenset({'published', 'failed', 'draft', 'archived'}),
    'published': frozenset({'archived'}),
    'rejected': frozenset({'draft', 'pending_approval', 'archived'}),
    'failed': frozenset({'draft', 'scheduled', 'archived'}),
    'archived': frozenset({'draft'})
}

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

def validate_campaign_dates(start_date, end_date):
    """
    Validates that start_date and end_date (if provided) are valid date strings
    and that end_date is not earlier than start_date.
    """
    def parse_dt(d_str):
        if not d_str or not str(d_str).strip():
            return None
        clean = str(d_str).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(clean[:19], fmt[:len(clean[:19])])
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(clean)
        except Exception:
            raise ValueError(f"Invalid date format: '{d_str}'. Must be a valid date string (e.g. YYYY-MM-DD).")

    parsed_start = parse_dt(start_date)
    parsed_end = parse_dt(end_date)
    if parsed_start and parsed_end:
        if parsed_end < parsed_start:
            raise ValueError(f"Campaign end_date ({end_date}) cannot be earlier than start_date ({start_date}).")
    return (str(start_date).strip() if start_date else None,
            str(end_date).strip() if end_date else None)

def validate_campaign_budget(budget):
    """
    Validates that budget (if provided) is non-negative and properly formatted.
    """
    if budget is None or str(budget).strip() == "":
        return None
    clean = str(budget).strip()
    num_part = re.sub(r'^[$\€\£\₹\s]+', '', clean).replace(',', '').strip()
    try:
        val = float(num_part)
        if val < 0:
            raise ValueError(f"Campaign budget cannot be negative: '{budget}'.")
        return clean
    except ValueError as e:
        if "cannot be negative" in str(e):
            raise
        raise ValueError(f"Invalid budget format: '{budget}'. Must be a non-negative number or currency string.")

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

    clean_start, clean_end = validate_campaign_dates(start_date, end_date)
    clean_budget = validate_campaign_budget(budget)

    clean_name = str(name).strip()
    clean_obj = str(objective).strip()
    clean_brief = str(brief).strip()
    b_id = int(brand_id)

    clean_status = str(status or 'draft').strip().lower()
    if clean_status not in INITIAL_CAMPAIGN_STATUSES:
        raise ValueError(
            f"Invalid initial campaign status: '{status}'. Allowed initial statuses: {', '.join(sorted(INITIAL_CAMPAIGN_STATUSES))}."
        )

    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO campaigns (organization_id, brand_id, name, objective, campaign_type, "
                "target_audience, target_markets, languages, brief, start_date, end_date, "
                "status, budget, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
                (organization_id, b_id, clean_name, clean_obj, campaign_type or 'social',
                 target_audience or '', target_markets or '', languages or '', clean_brief,
                 clean_start, clean_end, clean_status, clean_budget, created_by)
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
                 clean_start, clean_end, clean_status, clean_budget, created_by)
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
                    end_date=None, status=None, budget=None, brand_id=None):
    """Updates an existing campaign ensuring tenant isolation and lifecycle validity."""
    existing = validate_campaign_ownership(campaign_id, organization_id)
    c_id = int(campaign_id)
    current_status = (existing.get('status') or 'draft').lower()

    updates = []
    params = []
    if brand_id is not None:
        validate_brand_ownership(brand_id, organization_id)
        updates.append("brand_id = ?")
        params.append(int(brand_id))
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
    if start_date is not None or end_date is not None:
        eval_start = start_date if start_date is not None else existing.get('start_date')
        eval_end = end_date if end_date is not None else existing.get('end_date')
        clean_start, clean_end = validate_campaign_dates(eval_start, eval_end)
        if start_date is not None:
            updates.append("start_date = ?")
            params.append(clean_start)
        if end_date is not None:
            updates.append("end_date = ?")
            params.append(clean_end)
    if status is not None:
        clean_status = str(status).strip().lower()
        if clean_status not in VALID_CAMPAIGN_STATUSES:
            raise ValueError(
                f"Invalid campaign status: '{status}'. Allowed statuses: {', '.join(sorted(VALID_CAMPAIGN_STATUSES))}."
            )
        if clean_status != current_status and clean_status not in LEGAL_CAMPAIGN_TRANSITIONS.get(current_status, frozenset()):
            raise ValueError(
                f"Illegal campaign lifecycle transition from '{current_status}' to '{clean_status}'."
            )
        updates.append("status = ?")
        params.append(clean_status)
    if budget is not None:
        clean_budget = validate_campaign_budget(budget)
        updates.append("budget = ?")
        params.append(clean_budget)

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
        conn.execute("DELETE FROM content_plan_entries WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        conn.execute("DELETE FROM content_plans WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        conn.execute("DELETE FROM campaign_strategies WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        conn.execute("DELETE FROM content_draft_revisions WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        conn.execute("DELETE FROM content_drafts WHERE campaign_id = ? AND organization_id = ?", (c_id, organization_id))
        res = conn.execute("DELETE FROM campaigns WHERE id = ? AND organization_id = ?", (c_id, organization_id))
        conn.commit()
        return res.rowcount > 0

STRATEGY_FIELDS = [
    'positioning', 'primary_objective', 'target_segments', 'pain_points',
    'value_proposition', 'core_message', 'supporting_messages', 'content_themes',
    'recommended_channels', 'calls_to_action', 'suggested_phases',
    'posting_frequency', 'success_metrics', 'risks_and_verification', 'raw_response'
]

def save_campaign_strategy(organization_id, brand_id, campaign_id, strategy_data):
    """
    Saves or updates a campaign strategy within the active organization.
    strategy_data is a dict containing the strategy sections.
    """
    validate_campaign_ownership(campaign_id, organization_id)
    c_id = int(campaign_id)
    b_id = int(brand_id)
    org_id = int(organization_id)

    vals = {}
    for f in STRATEGY_FIELDS:
        v = strategy_data.get(f)
        if isinstance(v, (dict, list)):
            vals[f] = json.dumps(v)
        elif v is not None:
            vals[f] = str(v).strip()
        else:
            vals[f] = None

    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM campaign_strategies WHERE campaign_id = ? AND organization_id = ?",
            (c_id, org_id)
        ).fetchone()

        if existing:
            set_clauses = [f"{f} = ?" for f in STRATEGY_FIELDS]
            set_clauses.append("brand_id = ?")
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE campaign_strategies SET {', '.join(set_clauses)} WHERE id = ? AND organization_id = ?"
            params = [vals[f] for f in STRATEGY_FIELDS] + [b_id, existing['id'], org_id]
            conn.execute(sql, tuple(params))
            strat_id = existing['id']
        else:
            col_names = ['organization_id', 'brand_id', 'campaign_id'] + STRATEGY_FIELDS
            placeholders = ', '.join(['?'] * len(col_names))
            sql = f"INSERT INTO campaign_strategies ({', '.join(col_names)}) VALUES ({placeholders})"
            params = [org_id, b_id, c_id] + [vals[f] for f in STRATEGY_FIELDS]
            cur = conn.execute(sql, tuple(params))
            strat_id = cur.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM campaign_strategies WHERE id = ?", (strat_id,)).fetchone()
        return dict(row) if row else None

def get_campaign_strategy(campaign_id, organization_id=1):
    """Retrieves a campaign strategy scoped to organization."""
    validate_campaign_ownership(campaign_id, organization_id)
    c_id = int(campaign_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM campaign_strategies WHERE campaign_id = ? AND organization_id = ?",
            (c_id, int(organization_id))
        ).fetchone()
        return dict(row) if row else None

VALID_DRAFT_PLATFORMS = frozenset({'facebook', 'instagram', 'linkedin', 'x', 'whatsapp'})

def create_content_draft(organization_id, brand_id, campaign_id, target_platform,
                         caption, headline=None, hashtags=None, call_to_action=None,
                         language='en', content_format='post', ai_provider=None,
                         ai_model=None, metadata=None, status='draft', created_by=None,
                         media_asset_id=None):
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
    clean_status = str(status or 'draft').strip().lower()
    if clean_status not in INITIAL_DRAFT_STATUSES:
        raise ValueError(
            f"Invalid initial content draft status: '{status}'. Allowed initial statuses: {', '.join(sorted(INITIAL_DRAFT_STATUSES))}."
        )

    meta_str = json.dumps(metadata) if isinstance(metadata, (dict, list)) else (str(metadata) if metadata else None)

    m_id = None
    if media_asset_id is not None and str(media_asset_id).strip() != '':
        try:
            m_id = int(media_asset_id)
            asset = get_media_asset_by_id(m_id, organization_id)
            if not asset:
                raise TenantIsolationError(f"Media asset #{m_id} does not exist or does not belong to active organization.")
        except (ValueError, TypeError):
            m_id = None

    with get_db_connection() as conn:
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO content_drafts (organization_id, brand_id, campaign_id, target_platform, "
                "language, content_format, headline, caption, hashtags, call_to_action, "
                "ai_provider, ai_model, metadata, status, current_revision, created_by, media_asset_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) RETURNING id",
                (organization_id, int(brand_id), int(campaign_id), clean_platform,
                 language or 'en', content_format or 'post', headline, clean_caption,
                 hashtags, call_to_action, ai_provider, ai_model, meta_str, clean_status, created_by, m_id)
            )
            did = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO content_drafts (organization_id, brand_id, campaign_id, target_platform, "
                "language, content_format, headline, caption, hashtags, call_to_action, "
                "ai_provider, ai_model, metadata, status, current_revision, created_by, media_asset_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (organization_id, int(brand_id), int(campaign_id), clean_platform,
                 language or 'en', content_format or 'post', headline, clean_caption,
                 hashtags, call_to_action, ai_provider, ai_model, meta_str, clean_status, created_by, m_id)
            )
            did = cur.lastrowid

        # Insert initial immutable revision 1
        initial_source = 'ai_generated' if ai_provider else 'manual_creation'
        conn.execute(
            "INSERT INTO content_draft_revisions (organization_id, brand_id, campaign_id, draft_id, "
            "revision_number, headline, caption, hashtags, call_to_action, content_format, "
            "ai_provider, ai_model, metadata, change_source, change_summary, edited_by, media_asset_id) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (organization_id, int(brand_id), int(campaign_id), did,
             headline, clean_caption, hashtags, call_to_action, content_format or 'post',
             ai_provider, ai_model, meta_str,
             initial_source, 'Initial draft creation', created_by, m_id)
        )
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
            "SELECT cd.*, c.name as campaign_name, b.name as brand_name, "
            "m.filename as media_filename, m.original_name as media_original_name, m.file_type as media_file_type "
            "FROM content_drafts cd "
            "LEFT JOIN campaigns c ON cd.campaign_id = c.id "
            "LEFT JOIN brands b ON cd.brand_id = b.id "
            "LEFT JOIN media_assets m ON cd.media_asset_id = m.id "
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
                         content_format=None, metadata=None, ai_provider=None,
                         ai_model=None, allow_privileged_status=False,
                         expected_revision=None, edited_by=None, change_source='manual_edit',
                         change_summary=None, media_asset_id=None):
    """Updates a content draft ensuring organization ownership, optimistic concurrency, and lifecycle validity."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid draft ID '{draft_id}'.")

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")
        existing = dict(row)

        curr_rev = existing['current_revision'] if existing['current_revision'] is not None else 1
        if expected_revision is not None:
            try:
                exp_int = int(expected_revision)
            except (ValueError, TypeError):
                raise ValueError(f"expected_revision must be an integer, got '{expected_revision}'.")
            if exp_int != curr_rev:
                raise ConcurrencyConflictError(
                    f"Conflict: Draft #{d_id} was modified by another request. Expected revision {exp_int}, but current revision is {curr_rev}."
                )

        current_status = (existing['status'] or 'draft').lower()
        updates = []
        params = []

        new_caption = str(caption).strip() if caption is not None else existing['caption']
        new_headline = str(headline).strip() if (headline is not None and str(headline).strip() != '') else (None if headline == '' else existing['headline'])
        new_hashtags = str(hashtags).strip() if (hashtags is not None and str(hashtags).strip() != '') else (None if hashtags == '' else existing['hashtags'])
        new_cta = str(call_to_action).strip() if (call_to_action is not None and str(call_to_action).strip() != '') else (None if call_to_action == '' else existing['call_to_action'])
        new_format = str(content_format).strip() if content_format is not None else (existing['content_format'] or 'post')
        new_provider = ai_provider if ai_provider is not None else existing.get('ai_provider')
        new_model = ai_model if ai_model is not None else existing.get('ai_model')

        content_changed = False
        if caption is not None:
            if not str(caption).strip():
                raise ValueError("Caption cannot be empty.")
            if new_caption != existing['caption']:
                content_changed = True
            updates.append("caption = ?")
            params.append(new_caption)

        if headline is not None:
            if new_headline != existing['headline']:
                content_changed = True
            updates.append("headline = ?")
            params.append(new_headline)

        if hashtags is not None:
            if new_hashtags != existing['hashtags']:
                content_changed = True
            updates.append("hashtags = ?")
            params.append(new_hashtags)

        if call_to_action is not None:
            if new_cta != existing['call_to_action']:
                content_changed = True
            updates.append("call_to_action = ?")
            params.append(new_cta)

        if content_format is not None:
            if new_format != (existing['content_format'] or 'post'):
                content_changed = True
            updates.append("content_format = ?")
            params.append(new_format)

        if ai_provider is not None:
            updates.append("ai_provider = ?")
            params.append(ai_provider)

        if ai_model is not None:
            updates.append("ai_model = ?")
            params.append(ai_model)

        if status is not None:
            clean_status = str(status).strip().lower()
            if clean_status not in VALID_DRAFT_STATUSES:
                raise ValueError(
                    f"Invalid draft status: '{status}'. Allowed: {', '.join(sorted(VALID_DRAFT_STATUSES))}."
                )
            if not allow_privileged_status and clean_status in PRIVILEGED_DRAFT_STATUSES:
                raise ValueError(
                    f"Cannot directly mark content draft as '{clean_status}' via draft edit. Use dedicated approval or scheduling workflow."
                )
            if clean_status != current_status and clean_status not in LEGAL_DRAFT_TRANSITIONS.get(current_status, frozenset()):
                raise ValueError(
                    f"Illegal draft lifecycle transition from '{current_status}' to '{clean_status}'."
                )
            updates.append("status = ?")
            params.append(clean_status)

        meta_str = None
        if metadata is not None:
            meta_str = json.dumps(metadata) if isinstance(metadata, (dict, list)) else str(metadata)
            updates.append("metadata = ?")
            params.append(meta_str)

        new_media_id = existing.get('media_asset_id')
        if media_asset_id is not None:
            if media_asset_id in (0, '', False, 'null', 'None'):
                updates.append("media_asset_id = NULL")
                if existing.get('media_asset_id') is not None:
                    content_changed = True
                new_media_id = None
            else:
                m_val = int(media_asset_id)
                asset = get_media_asset_by_id(m_val, organization_id)
                if not asset:
                    raise TenantIsolationError(f"Media asset #{m_val} does not exist or does not belong to active organization.")
                updates.append("media_asset_id = ?")
                params.append(m_val)
                if existing.get('media_asset_id') != m_val:
                    content_changed = True
                new_media_id = m_val

        # Append revision if content changed or if explicit regenerated/restored_revision source
        if content_changed or change_source in ('regenerated', 'restored_revision'):
            next_rev = curr_rev + 1
            updates.append("current_revision = ?")
            params.append(next_rev)
            summary = change_summary or ("Updated draft content" if change_source == 'manual_edit' else f"Updated content ({change_source})")
            rev_meta = meta_str if metadata is not None else existing.get('metadata')
            conn.execute(
                "INSERT INTO content_draft_revisions (organization_id, brand_id, campaign_id, draft_id, "
                "revision_number, headline, caption, hashtags, call_to_action, content_format, "
                "ai_provider, ai_model, metadata, change_source, change_summary, edited_by, media_asset_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (organization_id, existing['brand_id'], existing['campaign_id'], d_id,
                 next_rev, new_headline, new_caption, new_hashtags, new_cta, new_format,
                 new_provider, new_model, rev_meta,
                 change_source, summary, edited_by, new_media_id)
            )

        if not updates:
            return dict(existing)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        sql = f"UPDATE content_drafts SET {', '.join(updates)} WHERE id = ? AND organization_id = ?"
        params.extend([d_id, organization_id])

        conn.execute(sql, tuple(params))
        conn.commit()

        row = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (d_id,)).fetchone()
        return dict(row) if row else None

def transition_content_draft_status(draft_id, to_status, user_id=None, reason=None,
                                    organization_id=1, user_role=None):
    """
    Safely transitions a content draft's lifecycle state according to business rules.
    Restricts approval/rejection to authorized users (admin/manager).
    Direct transitions to 'published' without the publishing worker are forbidden.
    """
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid draft ID '{draft_id}'.")

    clean_target = str(to_status).strip().lower()
    if clean_target not in VALID_DRAFT_STATUSES:
        raise ValueError(
            f"Invalid target draft status: '{to_status}'. Allowed: {', '.join(sorted(VALID_DRAFT_STATUSES))}."
        )

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

        current_status = (row['status'] or 'draft').lower()
        if current_status == clean_target:
            return dict(row)

        if clean_target == 'published':
            raise ValueError(
                "Direct transition to 'published' is forbidden; publishing must be executed by the social publishing worker."
            )

        if clean_target not in LEGAL_DRAFT_TRANSITIONS.get(current_status, frozenset()):
            raise ValueError(
                f"Illegal draft lifecycle transition from '{current_status}' to '{clean_target}'."
            )

        # Authorization checks
        if clean_target in ('approved', 'rejected'):
            role = str(user_role or '').strip().lower()
            if role not in ('admin', 'manager'):
                raise ValueError(
                    f"Unauthorized: Only administrators or managers can mark content drafts as '{clean_target}'."
                )

        conn.execute(
            "UPDATE content_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND organization_id = ?",
            (clean_target, d_id, organization_id)
        )
        conn.commit()

        updated = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (d_id,)).fetchone()
        return dict(updated) if updated else None

def delete_content_draft(draft_id, organization_id=1):
    """Deletes a content draft and its revision history strictly scoped to organization."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        return False
    with get_db_connection() as conn:
        conn.execute("DELETE FROM content_draft_revisions WHERE draft_id = ? AND organization_id = ?", (d_id, organization_id))
        res = conn.execute("DELETE FROM content_drafts WHERE id = ? AND organization_id = ?", (d_id, organization_id))
        conn.commit()
        return res.rowcount > 0

def list_draft_revisions(draft_id, organization_id=1):
    """Returns chronological list of revisions for a draft within an organization."""
    try:
        d_id = int(draft_id)
    except (ValueError, TypeError):
        return []

    with get_db_connection() as conn:
        draft = conn.execute(
            "SELECT id FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not draft:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

        rows = conn.execute(
            "SELECT * FROM content_draft_revisions "
            "WHERE draft_id = ? AND organization_id = ? "
            "ORDER BY revision_number ASC",
            (d_id, organization_id)
        ).fetchall()
        return [dict(r) for r in rows]

def get_draft_revision(draft_id, revision_number, organization_id=1):
    """Retrieves a single specific revision for a content draft."""
    try:
        d_id = int(draft_id)
        r_num = int(revision_number)
    except (ValueError, TypeError):
        return None

    with get_db_connection() as conn:
        draft = conn.execute(
            "SELECT id FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not draft:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

        row = conn.execute(
            "SELECT * FROM content_draft_revisions "
            "WHERE draft_id = ? AND revision_number = ? AND organization_id = ?",
            (d_id, r_num, organization_id)
        ).fetchone()
        return dict(row) if row else None

def restore_draft_revision(draft_id, revision_number, organization_id=1, restored_by=None):
    """
    Restores the content of an earlier revision as the newest revision.
    Never mutates or truncates historical revisions; appends a new revision with change_source='restored_revision'.
    """
    try:
        d_id = int(draft_id)
        r_num = int(revision_number)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid draft ID '{draft_id}' or revision number '{revision_number}'.")

    with get_db_connection() as conn:
        draft = conn.execute(
            "SELECT * FROM content_drafts WHERE id = ? AND organization_id = ?",
            (d_id, organization_id)
        ).fetchone()
        if not draft:
            raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

        target_row = conn.execute(
            "SELECT * FROM content_draft_revisions "
            "WHERE draft_id = ? AND revision_number = ? AND organization_id = ?",
            (d_id, r_num, organization_id)
        ).fetchone()
        if not target_row:
            raise ValueError(f"Revision #{r_num} does not exist for draft #{d_id}.")
        target_rev = dict(target_row)

        current_rev = draft['current_revision'] if draft['current_revision'] is not None else 1
        next_rev = current_rev + 1

        # Update draft with restored content
        conn.execute(
            "UPDATE content_drafts SET headline = ?, caption = ?, hashtags = ?, call_to_action = ?, "
            "content_format = ?, ai_provider = ?, ai_model = ?, metadata = ?, media_asset_id = ?, current_revision = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND organization_id = ?",
            (target_rev['headline'], target_rev['caption'], target_rev['hashtags'],
             target_rev['call_to_action'], target_rev.get('content_format', 'post'),
             target_rev.get('ai_provider'), target_rev.get('ai_model'), target_rev.get('metadata'),
             target_rev.get('media_asset_id'),
             next_rev, d_id, organization_id)
        )

        # Append new revision record
        conn.execute(
            "INSERT INTO content_draft_revisions (organization_id, brand_id, campaign_id, draft_id, "
            "revision_number, headline, caption, hashtags, call_to_action, content_format, "
            "ai_provider, ai_model, metadata, change_source, change_summary, edited_by, media_asset_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'restored_revision', ?, ?, ?)",
            (organization_id, draft['brand_id'], draft['campaign_id'], d_id,
             next_rev, target_rev['headline'], target_rev['caption'], target_rev['hashtags'],
             target_rev['call_to_action'], target_rev.get('content_format', 'post'),
             target_rev.get('ai_provider'), target_rev.get('ai_model'), target_rev.get('metadata'),
             f"Restored from revision #{r_num}", restored_by, target_rev.get('media_asset_id'))
        )
        conn.commit()

        updated = conn.execute("SELECT * FROM content_drafts WHERE id = ?", (d_id,)).fetchone()
        return dict(updated) if updated else None

def get_organization_ai_generation_count(organization_id, window_seconds=3600):
    """
    Returns count of AI generation operations executed by the organization within the time window.
    Used for cost-control and rate-limiting.
    """
    try:
        org_id = int(organization_id)
        secs = int(window_seconds)
    except (ValueError, TypeError):
        return 0

    with get_db_connection() as conn:
        if is_postgres():
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM content_draft_revisions "
                "WHERE organization_id = ? AND change_source IN ('ai_generated', 'regenerated') "
                "AND created_at >= NOW() - make_interval(secs => ?)",
                (org_id, secs)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM content_draft_revisions "
                "WHERE organization_id = ? AND change_source IN ('ai_generated', 'regenerated') "
                "AND created_at >= datetime('now', '-' || ? || ' seconds')",
                (org_id, secs)
            ).fetchone()
        return row['cnt'] if row else 0

def log_ai_usage(organization_id, provider, model=None, prompt_tokens=0,
                 completion_tokens=0, total_tokens=0, brand_id=None,
                 campaign_id=None, cost_estimate=0.0, success=True,
                 error_message=None):
    """Logs an AI generation request with token metrics and cost estimates for billing and quota controls."""
    org_id = int(organization_id)
    b_id = int(brand_id) if brand_id is not None else None
    c_id = int(campaign_id) if campaign_id is not None else None
    p_tokens = int(prompt_tokens or 0)
    c_tokens = int(completion_tokens or 0)
    t_tokens = int(total_tokens or (p_tokens + c_tokens))
    cost = float(cost_estimate or 0.0)
    is_success = 1 if success else 0
    clean_err = str(error_message)[:500] if error_message else None

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO ai_usage_logs (organization_id, brand_id, campaign_id, "
            "provider, model, prompt_tokens, completion_tokens, total_tokens, "
            "cost_estimate, success, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, b_id, c_id, str(provider), str(model or ''),
             p_tokens, c_tokens, t_tokens, cost, is_success, clean_err)
        )
        conn.commit()

def get_ai_usage_summary(organization_id, days=30):
    """
    Returns aggregated AI usage metrics and recent request logs for the active organization.
    """
    org_id = int(organization_id)
    d = max(1, min(int(days), 365))

    with get_db_connection() as conn:
        if is_postgres():
            time_filter = "created_at >= NOW() - make_interval(days => ?)"
        else:
            time_filter = "created_at >= datetime('now', '-' || ? || ' days')"

        agg = conn.execute(
            f"SELECT COUNT(*) as total_requests, "
            f"COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) as successful_requests, "
            f"COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0) as failed_requests, "
            f"COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens, "
            f"COALESCE(SUM(completion_tokens), 0) as total_completion_tokens, "
            f"COALESCE(SUM(total_tokens), 0) as total_tokens, "
            f"COALESCE(SUM(cost_estimate), 0.0) as estimated_cost "
            f"FROM ai_usage_logs WHERE organization_id = ? AND {time_filter}",
            (org_id, d)
        ).fetchone()

        by_provider = conn.execute(
            f"SELECT provider, COUNT(*) as request_count, "
            f"COALESCE(SUM(total_tokens), 0) as total_tokens, "
            f"COALESCE(SUM(cost_estimate), 0.0) as estimated_cost "
            f"FROM ai_usage_logs WHERE organization_id = ? AND {time_filter} "
            f"GROUP BY provider ORDER BY request_count DESC",
            (org_id, d)
        ).fetchall()

        recent = conn.execute(
            "SELECT * FROM ai_usage_logs WHERE organization_id = ? "
            "ORDER BY created_at DESC LIMIT 50",
            (org_id,)
        ).fetchall()

        return {
            'period_days': d,
            'summary': dict(agg) if agg else {},
            'by_provider': [dict(r) for r in by_provider],
            'recent_logs': [dict(r) for r in recent]
        }

def get_calendar_events(organization_id=1, start_date=None, end_date=None,
                        brand_id=None, campaign_id=None, platform=None, status=None,
                        target_timezone=None):
    """
    Retrieves unified calendar events across scheduled posts and content drafts
    scoped to active organization with date bounds, localized timestamps, and filters.
    """
    org_id = int(organization_id)
    org_tz = target_timezone or get_organization_timezone(org_id)
    if target_timezone:
        org_tz = timezone_utils.validate_timezone_name(target_timezone)

    if brand_id and str(brand_id) != 'all':
        validate_brand_ownership(int(brand_id), org_id)

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

    events = []

    with get_db_connection() as conn:
        # 1. Query scheduled_posts
        sp_query = (
            "SELECT sp.id, sp.organization_id, sp.post_type, sp.message, "
            "sp.image_filename, sp.scheduled_for, sp.timezone, sp.status, "
            "sp.created_at, sp.brand_id, sp.campaign_id, "
            "b.name as brand_name, c.name as campaign_name "
            "FROM scheduled_posts sp "
            "LEFT JOIN brands b ON sp.brand_id = b.id "
            "LEFT JOIN campaigns c ON sp.campaign_id = c.id "
            "WHERE sp.organization_id = ?"
        )
        sp_params = [org_id]

        if start_utc:
            sp_query += " AND sp.scheduled_for >= ?"
            sp_params.append(start_utc)
        if end_utc:
            sp_query += " AND sp.scheduled_for <= ?"
            sp_params.append(end_utc)
        if brand_id and str(brand_id) != 'all':
            sp_query += " AND sp.brand_id = ?"
            sp_params.append(int(brand_id))
        if campaign_id and str(campaign_id) != 'all':
            sp_query += " AND sp.campaign_id = ?"
            sp_params.append(int(campaign_id))
        if platform and str(platform) != 'all':
            sp_query += " AND sp.post_type = ?"
            sp_params.append(str(platform))
        if status and str(status) != 'all':
            sp_query += " AND sp.status = ?"
            sp_params.append(str(status))

        sp_query += " ORDER BY sp.scheduled_for ASC, sp.id ASC"
        sp_rows = conn.execute(sp_query, tuple(sp_params)).fetchall()

        for r in sp_rows:
            d = dict(r)
            try:
                loc = timezone_utils.convert_utc_to_local(d['scheduled_for'], tz_name=d.get('timezone') or org_tz)
                loc_str = loc['local_iso']
                offset_str = loc.get('offset', '+00:00')
            except Exception:
                loc_str = str(d['scheduled_for'])
                offset_str = '+00:00'
            events.append({
                'id': f"post_{d['id']}",
                'raw_id': d['id'],
                'type': 'scheduled_post',
                'title': (d.get('message') or 'Untitled Post')[:60],
                'message': d.get('message', ''),
                'scheduled_for': d.get('scheduled_for'),
                'local_scheduled_for': loc_str,
                'timezone': d.get('timezone') or org_tz,
                'display_timezone': org_tz,
                'offset': offset_str,
                'post_type': d.get('post_type'),
                'platform': d.get('post_type'),
                'status': d.get('status') or 'scheduled',
                'brand_id': d.get('brand_id'),
                'brand_name': d.get('brand_name'),
                'campaign_id': d.get('campaign_id'),
                'campaign_name': d.get('campaign_name'),
                'image_filename': d.get('image_filename')
            })

        # 2. Query content_drafts
        cd_query = (
            "SELECT cd.id, cd.organization_id, cd.target_platform, cd.headline, "
            "cd.caption, cd.status, cd.created_at, cd.brand_id, cd.campaign_id, "
            "b.name as brand_name, c.name as campaign_name "
            "FROM content_drafts cd "
            "LEFT JOIN brands b ON cd.brand_id = b.id "
            "LEFT JOIN campaigns c ON cd.campaign_id = c.id "
            "WHERE cd.organization_id = ?"
        )
        cd_params = [org_id]

        if start_utc:
            cd_query += " AND cd.created_at >= ?"
            cd_params.append(start_utc)
        if end_utc:
            cd_query += " AND cd.created_at <= ?"
            cd_params.append(end_utc)
        if brand_id and str(brand_id) != 'all':
            cd_query += " AND cd.brand_id = ?"
            cd_params.append(int(brand_id))
        if campaign_id and str(campaign_id) != 'all':
            cd_query += " AND cd.campaign_id = ?"
            cd_params.append(int(campaign_id))
        if platform and str(platform) != 'all':
            cd_query += " AND cd.target_platform = ?"
            cd_params.append(str(platform))
        if status and str(status) != 'all':
            cd_query += " AND cd.status = ?"
            cd_params.append(str(status))

        cd_query += " ORDER BY cd.created_at ASC, cd.id ASC"
        cd_rows = conn.execute(cd_query, tuple(cd_params)).fetchall()

        for r in cd_rows:
            d = dict(r)
            events.append({
                'id': f"draft_{d['id']}",
                'raw_id': d['id'],
                'type': 'content_draft',
                'title': (d.get('headline') or d.get('caption') or 'Untitled Draft')[:60],
                'message': d.get('caption', ''),
                'scheduled_for': d.get('created_at'),
                'local_scheduled_for': d.get('created_at'),
                'timezone': org_tz,
                'display_timezone': org_tz,
                'post_type': d.get('target_platform'),
                'platform': d.get('target_platform'),
                'status': d.get('status') or 'draft',
                'brand_id': d.get('brand_id'),
                'brand_name': d.get('brand_name'),
                'campaign_id': d.get('campaign_id'),
                'campaign_name': d.get('campaign_name'),
                'headline': d.get('headline')
            })

    return events

def create_content_plan(organization_id, brand_id, campaign_id, period_type,
                        start_date, end_date, entries, posting_frequency=None,
                        created_by=None):
    """
    Creates an editorial content plan and its scheduled entries.
    entries is a list of dicts: [{suggested_date, platform, theme, content_format, topic, headline, call_to_action}]
    """
    validate_campaign_ownership(campaign_id, organization_id)
    org_id = int(organization_id)
    b_id = int(brand_id)
    c_id = int(campaign_id)
    clean_period = str(period_type).strip().lower()
    if clean_period not in ('weekly', 'monthly'):
        clean_period = 'weekly'

    with get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO content_plans (organization_id, brand_id, campaign_id, "
            "period_type, start_date, end_date, posting_frequency, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, b_id, c_id, clean_period, str(start_date), str(end_date),
             str(posting_frequency or ''), created_by)
        )
        plan_id = cur.lastrowid

        created_entries = []
        for ent in entries:
            s_date = str(ent.get('suggested_date') or start_date)
            plat = str(ent.get('platform') or 'facebook').lower()
            theme = str(ent.get('theme') or 'General')
            fmt = str(ent.get('content_format') or 'post')
            topic = str(ent.get('topic') or ent.get('headline') or 'Campaign Highlight')
            headline = str(ent.get('headline') or topic)
            cta = str(ent.get('call_to_action') or 'Learn More')

            ecur = conn.execute(
                "INSERT INTO content_plan_entries (plan_id, organization_id, brand_id, "
                "campaign_id, suggested_date, platform, theme, content_format, "
                "topic, headline, call_to_action) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, org_id, b_id, c_id, s_date, plat, theme, fmt, topic, headline, cta)
            )
            created_entries.append({
                'id': ecur.lastrowid,
                'plan_id': plan_id,
                'suggested_date': s_date,
                'platform': plat,
                'theme': theme,
                'content_format': fmt,
                'topic': topic,
                'headline': headline,
                'call_to_action': cta,
                'status': 'planned'
            })
        conn.commit()

        row = conn.execute("SELECT * FROM content_plans WHERE id = ?", (plan_id,)).fetchone()
        plan_dict = dict(row) if row else {}
        plan_dict['entries'] = created_entries
        return plan_dict

def get_content_plans(organization_id, campaign_id=None, brand_id=None):
    """Retrieves content plans scoped to organization with optional campaign filter."""
    org_id = int(organization_id)
    query = (
        "SELECT cp.*, b.name as brand_name, c.name as campaign_name, "
        "(SELECT COUNT(*) FROM content_plan_entries cpe WHERE cpe.plan_id = cp.id) as entry_count "
        "FROM content_plans cp "
        "LEFT JOIN brands b ON cp.brand_id = b.id "
        "LEFT JOIN campaigns c ON cp.campaign_id = c.id "
        "WHERE cp.organization_id = ?"
    )
    params = [org_id]
    if campaign_id:
        query += " AND cp.campaign_id = ?"
        params.append(int(campaign_id))
    if brand_id:
        query += " AND cp.brand_id = ?"
        params.append(int(brand_id))

    query += " ORDER BY cp.created_at DESC"
    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

def get_content_plan_by_id(plan_id, organization_id=1):
    """Retrieves a content plan and its entries scoped to organization."""
    org_id = int(organization_id)
    p_id = int(plan_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT cp.*, b.name as brand_name, c.name as campaign_name "
            "FROM content_plans cp "
            "LEFT JOIN brands b ON cp.brand_id = b.id "
            "LEFT JOIN campaigns c ON cp.campaign_id = c.id "
            "WHERE cp.id = ? AND cp.organization_id = ?",
            (p_id, org_id)
        ).fetchone()
        if not row:
            return None
        plan_dict = dict(row)

        entries = conn.execute(
            "SELECT * FROM content_plan_entries "
            "WHERE plan_id = ? AND organization_id = ? "
            "ORDER BY suggested_date ASC, id ASC",
            (p_id, org_id)
        ).fetchall()
        plan_dict['entries'] = [dict(e) for e in entries]
        return plan_dict

def convert_plan_entry_to_draft(entry_id, organization_id=1, user_id=None):
    """
    Converts a planned calendar entry into an editable content draft in content_drafts.
    Creates immutable revision 1 and updates the entry status.
    """
    org_id = int(organization_id)
    e_id = int(entry_id)

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM content_plan_entries WHERE id = ? AND organization_id = ?",
            (e_id, org_id)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Plan entry #{e_id} does not exist or does not belong to active organization.")
        entry = dict(row)

        if entry.get('converted_draft_id'):
            existing_draft = conn.execute(
                "SELECT * FROM content_drafts WHERE id = ? AND organization_id = ?",
                (entry['converted_draft_id'], org_id)
            ).fetchone()
            if existing_draft:
                return dict(existing_draft)

    draft = create_content_draft(
        organization_id=org_id,
        brand_id=entry['brand_id'],
        campaign_id=entry['campaign_id'],
        target_platform=entry['platform'],
        caption=entry['topic'],
        headline=entry.get('headline'),
        call_to_action=entry.get('call_to_action'),
        content_format=entry.get('content_format', 'post'),
        status='draft',
        created_by=user_id
    )

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE content_plan_entries SET status = 'converted_to_draft', "
            "converted_draft_id = ? WHERE id = ? AND organization_id = ?",
            (draft['id'], e_id, org_id)
        )
        conn.commit()

    return draft

def convert_all_plan_entries_to_drafts(plan_id, organization_id=1, user_id=None):
    """
    Converts all entries in a content plan into editable content drafts.
    Guarantees organization ownership check and immutable revision 1 creation.
    """
    org_id = int(organization_id)
    p_id = int(plan_id)
    plan = get_content_plan_by_id(p_id, organization_id=org_id)
    if not plan:
        raise TenantIsolationError(f"Content plan #{p_id} does not exist or does not belong to active organization.")

    drafts = []
    for entry in plan.get('entries', []):
        draft = convert_plan_entry_to_draft(entry['id'], organization_id=org_id, user_id=user_id)
        drafts.append(draft)
    return drafts





def save_media_asset(organization_id, filename, original_name=None, brand_id=None,
                     campaign_id=None, file_type='image', file_size=0,
                     mime_type=None, tags=None, created_by=None):
    """
    Saves a media asset record scoped to an organization, optionally bound to a brand and campaign.
    """
    org_id = int(organization_id)
    b_id = int(brand_id) if brand_id is not None else None
    c_id = int(campaign_id) if campaign_id is not None else None
    
    if b_id is not None:
        validate_brand_ownership(b_id, org_id)
    if c_id is not None:
        validate_campaign_ownership(c_id, org_id)

    f_name = str(filename).strip()
    if not f_name:
        raise ValueError("Filename is required.")

    clean_file_type = str(file_type or 'image').strip().lower()
    if clean_file_type not in ('image', 'video', 'document'):
        clean_file_type = 'image'

    with get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO media_assets (organization_id, brand_id, campaign_id, "
            "filename, original_name, file_type, file_size, mime_type, tags, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (org_id, b_id, c_id, f_name, str(original_name or f_name),
             clean_file_type, int(file_size or 0), str(mime_type or ''),
             str(tags or ''), created_by)
        )
        asset_id = cur.lastrowid
        conn.commit()

        row = conn.execute("SELECT * FROM media_assets WHERE id = ?", (asset_id,)).fetchone()
        return dict(row) if row else {'id': asset_id, 'filename': f_name}

def get_media_assets(organization_id, brand_id=None, campaign_id=None, file_type=None, search=None):
    """
    Retrieves media assets scoped to organization with optional brand, campaign, type, and search filters.
    """
    org_id = int(organization_id)
    query = (
        "SELECT m.*, b.name as brand_name, c.name as campaign_name "
        "FROM media_assets m "
        "LEFT JOIN brands b ON m.brand_id = b.id "
        "LEFT JOIN campaigns c ON m.campaign_id = c.id "
        "WHERE m.organization_id = ?"
    )
    params = [org_id]

    if brand_id is not None:
        query += " AND m.brand_id = ?"
        params.append(int(brand_id))
    if campaign_id is not None:
        query += " AND m.campaign_id = ?"
        params.append(int(campaign_id))
    if file_type:
        query += " AND m.file_type = ?"
        params.append(str(file_type).strip().lower())
    if search:
        search_pattern = f"%{str(search).strip()}%"
        query += " AND (m.filename LIKE ? OR m.original_name LIKE ? OR m.tags LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern])

    query += " ORDER BY m.created_at DESC, m.id DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

def get_media_asset_by_id(asset_id, organization_id=1):
    """Retrieves a single media asset scoped to organization."""
    org_id = int(organization_id)
    a_id = int(asset_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT m.*, b.name as brand_name, c.name as campaign_name "
            "FROM media_assets m "
            "LEFT JOIN brands b ON m.brand_id = b.id "
            "LEFT JOIN campaigns c ON m.campaign_id = c.id "
            "WHERE m.id = ? AND m.organization_id = ?",
            (a_id, org_id)
        ).fetchone()
        return dict(row) if row else None

def delete_media_asset(asset_id, organization_id=1):
    """Deletes a media asset record scoped to organization. Returns the deleted record dictionary."""
    org_id = int(organization_id)
    a_id = int(asset_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM media_assets WHERE id = ? AND organization_id = ?",
            (a_id, org_id)
        ).fetchone()
        if not row:
            raise TenantIsolationError(f"Media asset #{a_id} does not exist or does not belong to active organization.")
        asset = dict(row)
        conn.execute("DELETE FROM media_assets WHERE id = ? AND organization_id = ?", (a_id, org_id))
        conn.commit()
        return asset


def schedule_content_draft(draft_id, scheduled_for, timezone_name=None, organization_id=1, user_id=None, user_role='admin'):
    """
    Schedules an approved content draft for publication.
    If the draft is in 'draft' or 'pending_approval' and the caller has approval authority (admin, manager, owner),
    it transitions the draft directly to 'scheduled'.
    Creates a corresponding scheduled_post linked via draft_id and campaign_id.
    """
    org_id = int(organization_id)
    d_id = int(draft_id)

    draft = get_content_draft_by_id(d_id, organization_id=org_id)
    if not draft:
        raise TenantIsolationError(f"Content draft #{d_id} does not exist or does not belong to active organization.")

    curr_status = (draft['status'] or 'draft').lower()
    is_approver = (user_role in ('admin', 'manager', 'owner'))
    if curr_status not in ('approved', 'scheduled'):
        if not is_approver:
            raise ValueError(f"Cannot schedule draft in '{curr_status}' status. Draft must be approved first.")

    # Time validation: disallow past scheduled times
    org_tz = get_organization_timezone(org_id)
    target_tz = timezone_name or org_tz
    utc_dt, resolved_tz, scheduled_utc_str = timezone_utils.parse_and_convert_to_utc(
        str(scheduled_for),
        tz_name=target_tz,
        org_default_tz=org_tz,
        allow_past=False
    )

    image_filename = draft.get('media_filename')
    clean_platform = str(draft['target_platform']).strip().lower()

    # Create scheduled post linked to draft
    scheduled_post = create_scheduled_post(
        post_type=clean_platform,
        scheduled_for=scheduled_utc_str,
        message=draft['caption'],
        image_filename=image_filename,
        organization_id=org_id,
        brand_id=draft['brand_id'],
        timezone_name=resolved_tz,
        initial_status='scheduled',
        allow_past=False,
        created_by=user_id,
        campaign_id=draft['campaign_id'],
        draft_id=d_id
    )

    # Update draft status to scheduled
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE content_drafts SET status = 'scheduled', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND organization_id = ?",
            (d_id, org_id)
        )
        conn.commit()

    return {
        'draft_id': d_id,
        'scheduled_post': scheduled_post,
        'scheduled_for': scheduled_utc_str,
        'timezone': resolved_tz,
        'status': 'scheduled'
    }


def get_marketing_dashboard_analytics(organization_id=1, brand_id=None, campaign_id=None):
    """
    Computes aggregated marketing performance analytics scoped to an organization:
    - Campaigns summary (total, active, completed, archived)
    - Drafts lifecycle distribution (draft, pending_approval, approved, scheduled, published, rejected)
    - Publishing throughput and health (scheduled, publishing, published, failed, success rate)
    - Platform distribution
    - AI consumption summary
    """
    org_id = int(organization_id)
    b_id = int(brand_id) if brand_id is not None else None
    c_id = int(campaign_id) if campaign_id is not None else None

    with get_db_connection() as conn:
        # 1. Campaigns summary
        c_query = "SELECT status, COUNT(*) as cnt FROM campaigns WHERE organization_id = ?"
        c_params = [org_id]
        if b_id is not None:
            c_query += " AND brand_id = ?"
            c_params.append(b_id)
        if c_id is not None:
            c_query += " AND id = ?"
            c_params.append(c_id)
        c_query += " GROUP BY status"
        c_rows = conn.execute(c_query, tuple(c_params)).fetchall()

        campaigns_by_status = {r['status']: r['cnt'] for r in c_rows}
        total_campaigns = sum(campaigns_by_status.values())

        # 2. Content Drafts breakdown
        d_query = "SELECT status, target_platform, COUNT(*) as cnt FROM content_drafts WHERE organization_id = ?"
        d_params = [org_id]
        if b_id is not None:
            d_query += " AND brand_id = ?"
            d_params.append(b_id)
        if c_id is not None:
            d_query += " AND campaign_id = ?"
            d_params.append(c_id)
        d_query += " GROUP BY status, target_platform"
        d_rows = conn.execute(d_query, tuple(d_params)).fetchall()

        drafts_by_status = {}
        drafts_by_platform = {}
        total_drafts = 0
        for r in d_rows:
            st = r['status']
            plat = r['target_platform']
            cnt = r['cnt']
            total_drafts += cnt
            drafts_by_status[st] = drafts_by_status.get(st, 0) + cnt
            drafts_by_platform[plat] = drafts_by_platform.get(plat, 0) + cnt

        # 3. Scheduled posts throughput & health
        sp_query = "SELECT status, post_type, COUNT(*) as cnt FROM scheduled_posts WHERE organization_id = ?"
        sp_params = [org_id]
        if b_id is not None:
            sp_query += " AND brand_id = ?"
            sp_params.append(b_id)
        if c_id is not None:
            sp_query += " AND campaign_id = ?"
            sp_params.append(c_id)
        sp_query += " GROUP BY status, post_type"
        sp_rows = conn.execute(sp_query, tuple(sp_params)).fetchall()

        posts_by_status = {}
        posts_by_platform = {}
        total_posts = 0
        for r in sp_rows:
            st = r['status']
            ptype = r['post_type']
            cnt = r['cnt']
            total_posts += cnt
            posts_by_status[st] = posts_by_status.get(st, 0) + cnt
            posts_by_platform[ptype] = posts_by_platform.get(ptype, 0) + cnt

        published_count = posts_by_status.get('published', 0)
        failed_count = posts_by_status.get('failed', 0)
        completed_or_failed = published_count + failed_count
        success_rate = round((published_count / completed_or_failed * 100.0), 1) if completed_or_failed > 0 else 100.0

        # 4. AI usage metrics
        ai_summary = get_ai_usage_summary(organization_id=org_id, days=30)

        # 5. Combined platform metrics
        platforms = set(drafts_by_platform.keys()) | set(posts_by_platform.keys())
        platform_distribution = {}
        for p in platforms:
            platform_distribution[p] = {
                'drafts_count': drafts_by_platform.get(p, 0),
                'scheduled_posts_count': posts_by_platform.get(p, 0)
            }

        return {
            'organization_id': org_id,
            'campaigns': {
                'total': total_campaigns,
                'active': campaigns_by_status.get('active', 0),
                'draft': campaigns_by_status.get('draft', 0),
                'completed': campaigns_by_status.get('completed', 0),
                'archived': campaigns_by_status.get('archived', 0),
                'by_status': campaigns_by_status
            },
            'drafts': {
                'total': total_drafts,
                'draft': drafts_by_status.get('draft', 0),
                'pending_approval': drafts_by_status.get('pending_approval', 0),
                'approved': drafts_by_status.get('approved', 0),
                'scheduled': drafts_by_status.get('scheduled', 0),
                'published': drafts_by_status.get('published', 0),
                'rejected': drafts_by_status.get('rejected', 0),
                'by_status': drafts_by_status
            },
            'publishing': {
                'total_scheduled': total_posts,
                'published': published_count,
                'pending': posts_by_status.get('scheduled', 0) + posts_by_status.get('publishing', 0),
                'failed': failed_count,
                'success_rate_percentage': success_rate,
                'by_status': posts_by_status
            },
            'platforms': platform_distribution,
            'ai_usage': {
                'total_requests': ai_summary['summary'].get('total_requests', 0),
                'successful_requests': ai_summary['summary'].get('successful_requests', 0),
                'total_tokens': ai_summary['summary'].get('total_tokens', 0),
                'estimated_cost_usd': ai_summary['summary'].get('estimated_cost_usd', 0.0)
            },
            'social_engagement': {
                'status': 'not_configured' if not getattr(config, 'FB_ACCESS_TOKEN', None) else 'active',
                'message': 'Meta social credentials not configured; live social engagement metrics unavailable.' if not getattr(config, 'FB_ACCESS_TOKEN', None) else 'Live engagement connected.'
            }
        }


def register_organization_with_owner(org_name, org_slug=None, owner_username="",
                                     owner_password="", owner_email=None,
                                     timezone_name="UTC", plan="starter"):
    """
    Self-service registration for a new multi-tenant organization.
    Atomically creates the organization, its initial owner account, and default brand workspace.
    """
    clean_org_name = str(org_name or "").strip()
    if not clean_org_name:
        raise ValueError("Organization name is required.")

    if not org_slug or not str(org_slug).strip():
        base_slug = re.sub(r'[^a-z0-9]+', '-', clean_org_name.lower()).strip('-')
        clean_slug = base_slug or f"org-{int(time.time())}"
    else:
        clean_slug = re.sub(r'[^a-z0-9]+', '-', str(org_slug).lower()).strip('-')

    clean_username = str(owner_username or "").strip()
    if not clean_username:
        raise ValueError("Owner username is required.")

    if not owner_password or len(str(owner_password)) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    valid_tz = timezone_utils.validate_timezone_name(timezone_name or 'UTC')

    with get_db_connection() as conn:
        # Check slug uniqueness
        existing_org = conn.execute("SELECT id FROM organizations WHERE slug = ?", (clean_slug,)).fetchone()
        if existing_org:
            raise ValueError(f"Organization slug '{clean_slug}' is already taken.")

        # Check username uniqueness
        existing_user = conn.execute("SELECT id FROM users WHERE username = ?", (clean_username,)).fetchone()
        if existing_user:
            raise ValueError(f"Username '{clean_username}' is already taken.")

        # Create organization
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO organizations (name, slug, plan, timezone, is_active) "
                "VALUES (?, ?, ?, ?, 1) RETURNING id",
                (clean_org_name, clean_slug, plan, valid_tz)
            )
            org_id = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO organizations (name, slug, plan, timezone, is_active) "
                "VALUES (?, ?, ?, ?, 1)",
                (clean_org_name, clean_slug, plan, valid_tz)
            )
            org_id = cur.lastrowid

        # Hash owner password and insert owner user
        pw_hash = generate_password_hash(owner_password)
        clean_email = str(owner_email).strip().lower() if owner_email else None

        if is_postgres():
            ucur = conn.execute(
                "INSERT INTO users (organization_id, username, password_hash, role, email, is_active) "
                "VALUES (?, ?, ?, 'owner', ?, 1) RETURNING id",
                (org_id, clean_username, pw_hash, clean_email)
            )
            user_id = ucur.fetchone()['id']
        else:
            ucur = conn.execute(
                "INSERT INTO users (organization_id, username, password_hash, role, email, is_active) "
                "VALUES (?, ?, ?, 'owner', ?, 1)",
                (org_id, clean_username, pw_hash, clean_email)
            )
            user_id = ucur.lastrowid

        # Create initial default brand workspace
        conn.execute(
            "INSERT INTO brands (organization_id, name, slug, description, is_active) "
            "VALUES (?, ?, 'default', 'Default brand workspace', 1)",
            (org_id, f"{clean_org_name} Workspace")
        )

        conn.commit()

        org_row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        user_row = conn.execute("SELECT id, organization_id, username, role, email, is_active, created_at FROM users WHERE id = ?", (user_id,)).fetchone()

        return {
            'organization': dict(org_row),
            'user': dict(user_row)
        }

def get_organization_settings(organization_id):
    """Retrieves organization details, brand counts, and current tier."""
    org_id = int(organization_id)
    with get_db_connection() as conn:
        org_row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not org_row:
            return None
        org_dict = dict(org_row)

        brand_count = conn.execute("SELECT COUNT(*) as cnt FROM brands WHERE organization_id = ? AND is_active = 1", (org_id,)).fetchone()['cnt']
        member_count = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE organization_id = ? AND is_active = 1", (org_id,)).fetchone()['cnt']
        campaign_count = conn.execute("SELECT COUNT(*) as cnt FROM campaigns WHERE organization_id = ?", (org_id,)).fetchone()['cnt']

        org_dict['brand_count'] = brand_count
        org_dict['member_count'] = member_count
        org_dict['campaign_count'] = campaign_count
        return org_dict

def update_organization_settings(organization_id, name=None, timezone_name=None):
    """Updates organization name and timezone."""
    org_id = int(organization_id)
    updates = []
    params = []

    if name is not None:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Organization name cannot be empty.")
        updates.append("name = ?")
        params.append(clean_name)

    if timezone_name is not None:
        valid_tz = timezone_utils.validate_timezone_name(timezone_name)
        updates.append("timezone = ?")
        params.append(valid_tz)

    if not updates:
        return get_organization_settings(org_id)

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(org_id)

    with get_db_connection() as conn:
        conn.execute(f"UPDATE organizations SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()

    return get_organization_settings(org_id)

def get_organization_members(organization_id):
    """Lists team members belonging to the organization."""
    org_id = int(organization_id)
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, organization_id, username, role, email, is_active, created_at "
            "FROM users WHERE organization_id = ? ORDER BY id ASC",
            (org_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def add_organization_member(organization_id, username, password, role="contributor", email=None):
    """Adds a new team member to an organization."""
    org_id = int(organization_id)
    clean_username = str(username or "").strip()
    if not clean_username:
        raise ValueError("Username is required.")

    if not password or len(str(password)) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    clean_role = str(role or "contributor").strip().lower()
    if clean_role not in ('admin', 'manager', 'contributor'):
        raise ValueError(f"Invalid member role '{role}'. Allowed roles: admin, manager, contributor.")

    clean_email = str(email).strip().lower() if email else None

    with get_db_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (clean_username,)).fetchone()
        if existing:
            raise ValueError(f"Username '{clean_username}' is already taken.")

        pw_hash = generate_password_hash(password)
        if is_postgres():
            cur = conn.execute(
                "INSERT INTO users (organization_id, username, password_hash, role, email, is_active) "
                "VALUES (?, ?, ?, ?, ?, 1) RETURNING id",
                (org_id, clean_username, pw_hash, clean_role, clean_email)
            )
            uid = cur.fetchone()['id']
        else:
            cur = conn.execute(
                "INSERT INTO users (organization_id, username, password_hash, role, email, is_active) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (org_id, clean_username, pw_hash, clean_role, clean_email)
            )
            uid = cur.lastrowid
        conn.commit()

        row = conn.execute(
            "SELECT id, organization_id, username, role, email, is_active, created_at "
            "FROM users WHERE id = ?", (uid,)
        ).fetchone()
        return dict(row)

def update_organization_member(organization_id, user_id, role=None, is_active=None):
    """Updates a team member's role or active status within an organization."""
    org_id = int(organization_id)
    u_id = int(user_id)

    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ? AND organization_id = ?",
            (u_id, org_id)
        ).fetchone()
        if not user:
            raise TenantIsolationError(f"User #{u_id} does not exist or does not belong to active organization.")

        curr_role = user['role']
        updates = []
        params = []

        if role is not None:
            clean_role = str(role).strip().lower()
            if clean_role not in ('owner', 'admin', 'manager', 'contributor'):
                raise ValueError(f"Invalid role '{role}'.")
            if curr_role == 'owner' and clean_role != 'owner':
                # Check that another active owner exists
                owners = conn.execute(
                    "SELECT COUNT(*) as cnt FROM users WHERE organization_id = ? AND role = 'owner' AND is_active = 1 AND id != ?",
                    (org_id, u_id)
                ).fetchone()['cnt']
                if owners == 0:
                    raise ValueError("Cannot demote the only active owner in the organization.")
            updates.append("role = ?")
            params.append(clean_role)

        if is_active is not None:
            act_int = 1 if is_active else 0
            if curr_role == 'owner' and act_int == 0:
                owners = conn.execute(
                    "SELECT COUNT(*) as cnt FROM users WHERE organization_id = ? AND role = 'owner' AND is_active = 1 AND id != ?",
                    (org_id, u_id)
                ).fetchone()['cnt']
                if owners == 0:
                    raise ValueError("Cannot deactivate the only active owner in the organization.")
            updates.append("is_active = ?")
            params.append(act_int)

        if updates:
            params.append(u_id)
            params.append(org_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ? AND organization_id = ?", tuple(params))
            conn.commit()

        row = conn.execute(
            "SELECT id, organization_id, username, role, email, is_active, created_at "
            "FROM users WHERE id = ?", (u_id,)
        ).fetchone()
        return dict(row)


def get_subscription_plans():
    """Lists available commercial subscription tiers and entitlements."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, code, name, max_brands, max_campaigns, max_monthly_posts, "
            "max_monthly_ai_tokens, price_cents, is_active "
            "FROM subscription_plans WHERE is_active = 1 ORDER BY price_cents ASC"
        ).fetchall()
        return [dict(r) for r in rows]

def get_organization_subscription(organization_id):
    """Retrieves an organization's active subscription tier and quota limits."""
    org_id = int(organization_id)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT os.*, sp.name as plan_name, sp.max_brands, sp.max_campaigns, "
            "sp.max_monthly_posts, sp.max_monthly_ai_tokens, sp.price_cents "
            "FROM organization_subscriptions os "
            "JOIN subscription_plans sp ON os.plan_code = sp.code "
            "WHERE os.organization_id = ?",
            (org_id,)
        ).fetchone()

        if row:
            return dict(row)

        # Fallback: check organization table plan or default to growth/starter
        org = conn.execute("SELECT plan FROM organizations WHERE id = ?", (org_id,)).fetchone()
        plan_code = (org['plan'] if org and org['plan'] else 'growth').lower()

        sp_row = conn.execute("SELECT * FROM subscription_plans WHERE code = ?", (plan_code,)).fetchone()
        if not sp_row:
            sp_row = conn.execute("SELECT * FROM subscription_plans WHERE code = 'growth'").fetchone()

        if sp_row:
            sp = dict(sp_row)
            return {
                'organization_id': org_id,
                'plan_code': sp['code'],
                'plan_name': sp['name'],
                'status': 'active',
                'max_brands': sp['max_brands'],
                'max_campaigns': sp['max_campaigns'],
                'max_monthly_posts': sp['max_monthly_posts'],
                'max_monthly_ai_tokens': sp['max_monthly_ai_tokens'],
                'price_cents': sp['price_cents']
            }

        return {
            'organization_id': org_id,
            'plan_code': 'growth',
            'plan_name': 'Growth Tier',
            'status': 'active',
            'max_brands': 10,
            'max_campaigns': 25,
            'max_monthly_posts': 1000,
            'max_monthly_ai_tokens': 250000,
            'price_cents': 7900
        }

def set_organization_subscription(organization_id, plan_code, status='active'):
    """Updates an organization's subscription tier."""
    org_id = int(organization_id)
    clean_code = str(plan_code).strip().lower()

    with get_db_connection() as conn:
        plan = conn.execute("SELECT * FROM subscription_plans WHERE code = ?", (clean_code,)).fetchone()
        if not plan:
            raise ValueError(f"Unknown subscription plan code: '{plan_code}'.")

        # Upsert subscription
        existing = conn.execute("SELECT id FROM organization_subscriptions WHERE organization_id = ?", (org_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE organization_subscriptions SET plan_code = ?, status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE organization_id = ?",
                (clean_code, status, org_id)
            )
        else:
            conn.execute(
                "INSERT INTO organization_subscriptions (organization_id, plan_code, status) "
                "VALUES (?, ?, ?)",
                (org_id, clean_code, status)
            )

        # Update organization plan column
        conn.execute("UPDATE organizations SET plan = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (clean_code, org_id))
        conn.commit()

    return get_organization_subscription(org_id)

def check_organization_quota(organization_id, resource_type):
    """
    Evaluates whether the organization has remaining quota for a given resource.
    resource_type: 'brand', 'campaign', 'post', or 'ai_token'
    Returns (is_allowed: bool, current_usage: int, limit: int, message: str)
    """
    org_id = int(organization_id)
    sub = get_organization_subscription(org_id)
    clean_type = str(resource_type).strip().lower()

    with get_db_connection() as conn:
        if clean_type == 'brand':
            limit = sub.get('max_brands', 10)
            usage = conn.execute(
                "SELECT COUNT(*) as cnt FROM brands WHERE organization_id = ? AND is_active = 1",
                (org_id,)
            ).fetchone()['cnt']
        elif clean_type == 'campaign':
            limit = sub.get('max_campaigns', 25)
            usage = conn.execute(
                "SELECT COUNT(*) as cnt FROM campaigns WHERE organization_id = ? AND status != 'archived'",
                (org_id,)
            ).fetchone()['cnt']
        elif clean_type == 'post':
            limit = sub.get('max_monthly_posts', 1000)
            if is_postgres():
                post_query = "SELECT COUNT(*) as cnt FROM scheduled_posts WHERE organization_id = ? AND created_at >= NOW() - make_interval(days => 30)"
            else:
                post_query = "SELECT COUNT(*) as cnt FROM scheduled_posts WHERE organization_id = ? AND created_at >= datetime('now', '-30 days')"
            usage = conn.execute(post_query, (org_id,)).fetchone()['cnt']
        elif clean_type == 'ai_token':
            limit = sub.get('max_monthly_ai_tokens', 250000)
            if is_postgres():
                token_query = "SELECT COALESCE(SUM(total_tokens), 0) as cnt FROM ai_usage_logs WHERE organization_id = ? AND created_at >= NOW() - make_interval(days => 30)"
            else:
                token_query = "SELECT COALESCE(SUM(total_tokens), 0) as cnt FROM ai_usage_logs WHERE organization_id = ? AND created_at >= datetime('now', '-30 days')"
            usage = conn.execute(token_query, (org_id,)).fetchone()['cnt']
        else:
            return (True, 0, 999999, "Unconstrained resource.")

        if usage >= limit:
            msg = f"Subscription quota reached for {clean_type}s ({usage}/{limit}). Please upgrade your plan."
            return (False, usage, limit, msg)
        return (True, usage, limit, "Within subscription quota.")
