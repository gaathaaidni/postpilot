"""
Phase 2.1 Test Suite: Property-Aware Content Calendar, Schema Migration & Brand Backfill
(test_calendar_property_filter.py)

Covers:
- Additive schema migration (20261114_002_link_posts_to_properties)
- scheduled_posts foreign key to growth_properties(id) and index creation
- Idempotency of migration execution
- Unambiguous brand-to-property backfill across all 7 GAATHA ecosystem properties
- Explicit backfill verification for Brand 2 (POS) and Brand 3 (Sentira AI)
- Preservation of legacy unassigned/NULL posts
- Preservation of total scheduled_posts record counts
- Multi-tenant isolation during backfill and calendar retrieval
- Unauthenticated access control (HTTP 401 fail-closed)
- Authenticated calendar retrieval (HTTP 200)
- Calendar event filtering by property_id and property_id='all'
- Invalid property ID rejection (HTTP 400)
- Cross-tenant property access rejection (HTTP 404 TenantIsolationError)
- Backward compatibility of calendar API response contract
- Growth property metadata injection into calendar events
- Disposable database rollback verification
- Strict publishing safeguards preservation
- UI contract validation (HTML, JS, and CSS tokens)
"""
import os
import tempfile
import sqlite3
from pathlib import Path
import unittest
import json
import shutil

# Capture original environment and config to prevent bleed into subsequent test modules
_orig_env_db_url = os.environ.get('DATABASE_URL')
_orig_env_data_dir = os.environ.get('POSTPILOT_DATA_DIR')
_orig_env_testing = os.environ.get('TESTING')

_tmp_dir = tempfile.TemporaryDirectory()
_db_file = Path(_tmp_dir.name) / 'phase2_calendar_test.db'

os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-phase2-calendar-filter-32b'
os.environ['DATABASE_URL'] = f"sqlite:///{_db_file}"

import config
_orig_cfg_db_url = getattr(config, 'DATABASE_URL', None)
_orig_cfg_local_mode = getattr(config, 'LOCAL_MODE', None)

config.DATABASE_URL = f"sqlite:///{_db_file}"
config.LOCAL_MODE = False
config.POSTPILOT_PUBLISHING_ENABLED = 0
config.WHATSAPP_PUBLISHING_ENABLED = 0

import database
import app as postpilot_app


class TestCalendarPropertyFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.DATABASE_URL = f"sqlite:///{_db_file}"
        os.environ['DATABASE_URL'] = f"sqlite:///{_db_file}"
        database.init_db()
        database.init_growth_properties()

    @classmethod
    def tearDownClass(cls):
        # Restore config and env to guarantee zero side-effects on subsequent suites
        if _orig_cfg_db_url is not None:
            config.DATABASE_URL = _orig_cfg_db_url
        if _orig_cfg_local_mode is not None:
            config.LOCAL_MODE = _orig_cfg_local_mode
        if _orig_env_db_url is not None:
            os.environ['DATABASE_URL'] = _orig_env_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        if _orig_env_data_dir is not None:
            os.environ['POSTPILOT_DATA_DIR'] = _orig_env_data_dir
        else:
            os.environ.pop('POSTPILOT_DATA_DIR', None)
        if _orig_env_testing is not None:
            os.environ['TESTING'] = _orig_env_testing
        else:
            os.environ.pop('TESTING', None)

    def setUp(self):
        config.DATABASE_URL = f"sqlite:///{_db_file}"
        config.LOCAL_MODE = False
        self.app = postpilot_app.app
        self.client = self.app.test_client()

        # Ensure baseline organizations and growth properties exist
        with database.get_db_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (1, 'GAATHA Flagship', 'gaatha')")
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (2, 'Other Tenant Org', 'other-org')")

            # Ensure brands for Org 1 exist
            brand_seeds = [
                (1, 1, 'GAATHA Suite', 'suite'),
                (2, 1, 'GAATHA POS', 'pos'),
                (3, 1, 'Sentira AI', 'sentira'),
                (4, 1, 'GAATHA Terra', 'terra'),
                (5, 1, 'Phoenix', 'phoenix'),
                (6, 1, 'GAATHA AI', 'ai'),
                (101, 1, 'GAATHA Corporate', 'corporate')
            ]
            for bid, oid, bname, bslug in brand_seeds:
                conn.execute(
                    "INSERT OR IGNORE INTO brands (id, organization_id, name, slug) VALUES (?, ?, ?, ?)",
                    (bid, oid, bname, bslug)
                )

            # Ensure Org 2 brand and property exist for tenant isolation test
            conn.execute("INSERT OR IGNORE INTO brands (id, organization_id, name, slug) VALUES (201, 2, 'Tenant 2 Brand', 't2b')")
            conn.execute("""
                INSERT OR IGNORE INTO growth_properties (id, organization_id, brand_id, property_key, slug, display_name, canonical_url, is_active)
                VALUES (201, 2, 201, 'org2_prop', 'org2-prop', 'Org 2 Property', 'https://org2.gaatha.tech', 1)
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # 1. Migration & Schema Tests
    # -------------------------------------------------------------------------

    def test_01_migration_registered_in_schema_migrations(self):
        """Verifies migration 20261114_002_link_posts_to_properties is registered."""
        with database.get_db_connection() as conn:
            row = conn.execute(
                "SELECT version, description FROM schema_migrations WHERE version = ?",
                ('20261114_002_link_posts_to_properties',)
            ).fetchone()
            self.assertIsNotNone(row, "Phase 2.1 migration must be present in schema_migrations")
            self.assertIn("scheduled_posts", row['description'])

    def test_02_scheduled_posts_has_growth_property_id_and_index(self):
        """PRAGMA table_info confirms growth_property_id column and index idx_sched_growth_property."""
        with database.get_db_connection() as conn:
            cur = conn.execute("PRAGMA table_info(scheduled_posts)")
            cols = [r['name'] for r in cur.fetchall()]
            self.assertIn('growth_property_id', cols, "scheduled_posts must contain growth_property_id column")

            idx_cur = conn.execute("PRAGMA index_list(scheduled_posts)")
            idx_names = [r['name'] for r in idx_cur.fetchall()]
            self.assertIn('idx_sched_growth_property', idx_names, "Index idx_sched_growth_property must exist")

    def test_03_migration_idempotent(self):
        """Re-running migration multiple times must not raise errors or duplicate columns."""
        with database.get_db_connection() as conn:
            # Calling directly multiple times
            database.migrate_phase2_1_property_calendar(conn)
            database.migrate_phase2_1_property_calendar(conn)
            database.init_growth_properties(conn)

            # Check column count
            cur = conn.execute("PRAGMA table_info(scheduled_posts)")
            col_instances = [r['name'] for r in cur.fetchall() if r['name'] == 'growth_property_id']
            self.assertEqual(len(col_instances), 1, "Column growth_property_id must appear exactly once")

    # -------------------------------------------------------------------------
    # 2. Backfill & Data Preservation Tests
    # -------------------------------------------------------------------------

    def test_04_brand_to_property_backfill_all_seven_brands(self):
        """Tests that all 7 ecosystem brands map correctly to their growth property IDs."""
        brand_to_key = {
            1: ('gaatha_suite', 'GAATHA Suite'),
            2: ('gaatha_pos', 'GAATHA POS'),
            3: ('sentira_ai', 'Sentira AI'),
            4: ('gaatha_terra', 'GAATHA Terra'),
            5: ('phoenix', 'Phoenix'),
            6: ('gaatha_ai', 'GAATHA AI'),
            101: ('gaatha_corporate', 'GAATHA Corporate')
        }

        with database.get_db_connection() as conn:
            # Clean up prior test posts
            conn.execute("DELETE FROM scheduled_posts WHERE message LIKE 'TEST_BACKFILL_%'")

            for bid, (pkey, pname) in brand_to_key.items():
                conn.execute("""
                    INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status)
                    VALUES (1, ?, 'facebook', ?, '2026-11-20 12:00:00', 'scheduled')
                """, (bid, f"TEST_BACKFILL_{bid}"))

            conn.commit()

            # Execute backfill
            database.migrate_phase2_1_property_calendar(conn)

            # Check mapping for each
            for bid, (pkey, pname) in brand_to_key.items():
                row = conn.execute("""
                    SELECT sp.id, sp.growth_property_id, gp.property_key, gp.display_name
                    FROM scheduled_posts sp
                    JOIN growth_properties gp ON sp.growth_property_id = gp.id
                    WHERE sp.organization_id = 1 AND sp.message = ?
                """, (f"TEST_BACKFILL_{bid}",)).fetchone()
                self.assertIsNotNone(row, f"Post for brand {bid} must be linked to a growth property")
                self.assertEqual(row['property_key'], pkey, f"Brand {bid} must map to property key {pkey}")
                self.assertEqual(row['display_name'], pname, f"Brand {bid} must map to {pname}")

    def test_05_explicit_brand_2_and_brand_3_backfill(self):
        """Explicitly asserts that Brand 2 maps to POS and Brand 3 maps to Sentira AI."""
        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM scheduled_posts WHERE message IN ('TEST_B2_EXPLICIT', 'TEST_B3_EXPLICIT')")

            conn.execute("""
                INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status)
                VALUES (1, 2, 'instagram', 'TEST_B2_EXPLICIT', '2026-11-21 14:00:00', 'scheduled')
            """)
            conn.execute("""
                INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status)
                VALUES (1, 3, 'linkedin', 'TEST_B3_EXPLICIT', '2026-11-21 15:00:00', 'scheduled')
            """)
            conn.commit()

            database.migrate_phase2_1_property_calendar(conn)

            # Verify Brand 2
            b2_post = conn.execute("""
                SELECT sp.growth_property_id, gp.property_key, gp.display_name
                FROM scheduled_posts sp
                JOIN growth_properties gp ON sp.growth_property_id = gp.id
                WHERE sp.message = 'TEST_B2_EXPLICIT'
            """).fetchone()
            self.assertIsNotNone(b2_post)
            self.assertEqual(b2_post['property_key'], 'gaatha_pos')
            self.assertEqual(b2_post['display_name'], 'GAATHA POS')

            # Verify Brand 3
            b3_post = conn.execute("""
                SELECT sp.growth_property_id, gp.property_key, gp.display_name
                FROM scheduled_posts sp
                JOIN growth_properties gp ON sp.growth_property_id = gp.id
                WHERE sp.message = 'TEST_B3_EXPLICIT'
            """).fetchone()
            self.assertIsNotNone(b3_post)
            self.assertEqual(b3_post['property_key'], 'sentira_ai')
            self.assertEqual(b3_post['display_name'], 'Sentira AI')

    def test_06_unassigned_and_legacy_posts_remain_null(self):
        """Legacy posts with brand_id IS NULL must have growth_property_id remain NULL."""
        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM scheduled_posts WHERE message = 'TEST_LEGACY_NULL'")
            conn.execute("""
                INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status)
                VALUES (1, NULL, 'facebook', 'TEST_LEGACY_NULL', '2026-11-22 10:00:00', 'scheduled')
            """)
            conn.commit()

            database.migrate_phase2_1_property_calendar(conn)

            post = conn.execute("SELECT growth_property_id FROM scheduled_posts WHERE message = 'TEST_LEGACY_NULL'").fetchone()
            self.assertIsNotNone(post)
            self.assertIsNone(post['growth_property_id'], "Unassigned post growth_property_id must remain NULL")

    def test_07_record_count_strictly_preserved(self):
        """Ensures that the total count of scheduled posts is identical before and after migration."""
        with database.get_db_connection() as conn:
            before_count = conn.execute("SELECT COUNT(*) FROM scheduled_posts").fetchone()[0]

            # Re-run migration and backfill
            database.migrate_phase2_1_property_calendar(conn)

            after_count = conn.execute("SELECT COUNT(*) FROM scheduled_posts").fetchone()[0]
            self.assertEqual(before_count, after_count, "Total record count must never change during backfill")

    def test_08_tenant_isolation_in_backfill(self):
        """Backfill must not link Organization 2 posts to Organization 1 growth properties."""
        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM scheduled_posts WHERE message = 'TEST_ORG2_POST'")
            conn.execute("""
                INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status)
                VALUES (2, 201, 'facebook', 'TEST_ORG2_POST', '2026-11-23 10:00:00', 'scheduled')
            """)
            conn.commit()

            database.migrate_phase2_1_property_calendar(conn)

            post = conn.execute("""
                SELECT sp.growth_property_id, gp.organization_id as prop_org
                FROM scheduled_posts sp
                LEFT JOIN growth_properties gp ON sp.growth_property_id = gp.id
                WHERE sp.message = 'TEST_ORG2_POST'
            """).fetchone()
            self.assertIsNotNone(post)
            self.assertEqual(post['prop_org'], 2, "Org 2 post must link to Org 2 property, not Org 1")

    # -------------------------------------------------------------------------
    # 3. Calendar Events API Tests
    # -------------------------------------------------------------------------

    def test_09_api_calendar_events_unauthenticated_returns_401(self):
        """GET /api/calendar/events without session returns HTTP 401."""
        res = self.client.get('/api/calendar/events', environ_base={'REMOTE_ADDR': '198.51.100.1'})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertTrue(data.get('auth_required'))

    def test_10_api_calendar_events_authenticated_returns_200(self):
        """GET /api/calendar/events with active session returns HTTP 200 and list."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events')
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.get_json(), list)

    def test_11_api_calendar_events_default_returns_all_including_unassigned(self):
        """Without property_id filter, returns all events including unassigned legacy items."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events')
        self.assertEqual(res.status_code, 200)
        events = res.get_json()

        # Check for presence of unassigned post
        null_prop_events = [e for e in events if e.get('growth_property_id') is None]
        self.assertGreaterEqual(len(null_prop_events), 1, "Default calendar query must include unassigned posts")

    def test_12_api_calendar_events_filter_by_property_id(self):
        """GET /api/calendar/events?property_id=<id> filters results to that specific property."""
        with database.get_db_connection() as conn:
            suite_prop = conn.execute("SELECT id FROM growth_properties WHERE property_key = 'gaatha_suite' AND organization_id = 1").fetchone()
            self.assertIsNotNone(suite_prop)
            suite_id = suite_prop['id']

        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get(f'/api/calendar/events?property_id={suite_id}')
        self.assertEqual(res.status_code, 200)
        events = res.get_json()
        self.assertGreater(len(events), 0)

        for ev in events:
            self.assertEqual(ev.get('growth_property_id'), suite_id)
            self.assertEqual(ev.get('property_key'), 'gaatha_suite')
            self.assertEqual(ev.get('property_name'), 'GAATHA Suite')

    def test_13_api_calendar_events_filter_all_keyword(self):
        """GET /api/calendar/events?property_id=all returns all events without error."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events?property_id=all')
        self.assertEqual(res.status_code, 200)
        events = res.get_json()
        self.assertIsInstance(events, list)

    def test_14_api_calendar_events_invalid_property_id_returns_400(self):
        """GET /api/calendar/events?property_id=99999 returns HTTP 400."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events?property_id=99999')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'VALIDATION_ERROR')
        self.assertIn("does not exist", data.get('error', ''))

    def test_15_api_calendar_events_cross_tenant_property_returns_404(self):
        """GET /api/calendar/events?property_id=201 (Org 2) from Org 1 returns HTTP 404 (TenantIsolationError)."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events?property_id=201')
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'VALIDATION_ERROR')
        self.assertIn("different organization", data.get('error', ''))

    def test_16_api_calendar_events_response_contract_backward_compatibility(self):
        """Checks backward compatibility of response fields and presence of property fields."""
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True
            sess['user_id'] = 1
            sess['organization_id'] = 1

        res = self.client.get('/api/calendar/events')
        self.assertEqual(res.status_code, 200)
        events = res.get_json()
        self.assertGreater(len(events), 0)

        ev = events[0]
        # Standard legacy calendar fields
        self.assertIn('id', ev)
        self.assertIn('post_type', ev)
        self.assertIn('scheduled_for', ev)
        self.assertIn('status', ev)
        self.assertIn('brand_id', ev)

        # Injected Phase 2.1 property fields
        self.assertIn('growth_property_id', ev)
        self.assertIn('property_id', ev)
        self.assertIn('property_key', ev)
        self.assertIn('property_name', ev)
        self.assertIn('property_canonical_url', ev)

    # -------------------------------------------------------------------------
    # 4. Disposable Rollback & Safeguards Tests
    # -------------------------------------------------------------------------

    def test_17_disposable_database_rollback_simulation(self):
        """Simulates pre-migration backup and verifies pristine rollback capability."""
        disposable_db = Path(_tmp_dir.name) / 'disposable_rollback.db'
        backup_db = Path(_tmp_dir.name) / 'disposable_rollback.bak'

        # Create isolated database with pre-Phase 2 schema (has growth_properties from Phase 1)
        with sqlite3.connect(str(disposable_db)) as conn:
            conn.execute("""
                CREATE TABLE scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    brand_id INTEGER,
                    post_type TEXT,
                    message TEXT,
                    scheduled_for TEXT,
                    status TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE growth_properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    brand_id INTEGER,
                    property_key TEXT,
                    display_name TEXT
                )
            """)
            conn.execute("INSERT INTO growth_properties (id, organization_id, brand_id, property_key, display_name) VALUES (1, 1, 1, 'gaatha_suite', 'GAATHA Suite')")
            conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, description TEXT, applied_at TIMESTAMP)")
            conn.execute("INSERT INTO scheduled_posts (organization_id, brand_id, post_type, message, scheduled_for, status) VALUES (1, 1, 'facebook', 'Pre-rollback post', '2026-11-20', 'scheduled')")
            conn.commit()

        # Step 1: Backup
        shutil.copy2(disposable_db, backup_db)

        # Step 2: Apply migration
        with sqlite3.connect(str(disposable_db)) as conn:
            conn.row_factory = sqlite3.Row
            database.migrate_phase2_1_property_calendar(conn)

            # Confirm column exists
            cols = [r[1] for r in conn.execute("PRAGMA table_info(scheduled_posts)").fetchall()]
            self.assertIn('growth_property_id', cols)

        # Step 3: Rollback by restoring backup
        shutil.copy2(backup_db, disposable_db)

        # Step 4: Verify pre-migration state is restored
        with sqlite3.connect(str(disposable_db)) as conn:
            cols_after = [r[1] for r in conn.execute("PRAGMA table_info(scheduled_posts)").fetchall()]
            self.assertNotIn('growth_property_id', cols_after, "Column must not exist after rollback")
            count = conn.execute("SELECT COUNT(*) FROM scheduled_posts").fetchone()[0]
            self.assertEqual(count, 1, "Original post must be intact")

    def test_18_publishing_safeguards_strictly_disabled(self):
        """Verifies all social media publishing flags remain fail-closed at 0."""
        self.assertEqual(config.POSTPILOT_PUBLISHING_ENABLED, 0)
        self.assertEqual(config.WHATSAPP_PUBLISHING_ENABLED, 0)

    # -------------------------------------------------------------------------
    # 5. UI Contract Verification Tests
    # -------------------------------------------------------------------------

    def test_19_ui_script_and_style_contract(self):
        """Verifies frontend assets include required elements, property dropdown, and color tokens."""
        repo_root = Path(r"D:\postpilot")

        # Check static/script.js
        with open(repo_root / 'static' / 'script.js', 'r', encoding='utf-8') as f:
            js_content = f.read()
            self.assertIn('cal-filter-property', js_content)
            self.assertIn('calendar-property-legend', js_content)
            self.assertIn('renderCalendarPropertyLegend', js_content)
            self.assertIn('cal-prop-badge', js_content)
            self.assertIn('details-property-name', js_content)

        # Check static/style.css
        with open(repo_root / 'static' / 'style.css', 'r', encoding='utf-8') as f:
            css_content = f.read()
            self.assertIn('.cal-prop-badge', css_content)
            self.assertIn('.calendar-property-legend', css_content)
            self.assertIn('.prop-gaatha_corporate', css_content)
            self.assertIn('.prop-gaatha_terra', css_content)
            self.assertIn('.prop-gaatha_suite', css_content)
            self.assertIn('.prop-sentira_ai', css_content)
            self.assertIn('.prop-gaatha_pos', css_content)
            self.assertIn('.prop-gaatha_ai', css_content)
            self.assertIn('.prop-phoenix', css_content)

        # Check templates/index.html
        with open(repo_root / 'templates' / 'index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
            self.assertIn('details-property-name', html_content)


if __name__ == '__main__':
    unittest.main()
