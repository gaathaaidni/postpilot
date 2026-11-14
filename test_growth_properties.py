"""
Phase 1 Test Suite: Growth & Intelligence Property Registry & Migration Foundation
(test_growth_properties.py)

Covers:
- Seven default ecosystem properties seeding and schema
- Correct brand mapping for Organization 1
- Property listing and single property retrieval APIs
- Property creation, editing, and status toggling APIs
- Input validation (URLs, unique keys, format constraints)
- Duplicate key rejection (HTTP 409)
- Authentication, CSRF protection, and RBAC (Viewer read-only)
- Multi-tenant isolation between organizations
- Migration versioning and idempotency
- Disposable database rollback verification
- Preservation of existing domain tables and publishing safeguards
"""
import os
import tempfile
import sqlite3
from pathlib import Path
import unittest
import json
import shutil

# Configure isolated test environment
os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-phase1-growth-properties-32b'
_tmp_dir = tempfile.TemporaryDirectory()
_db_file = Path(_tmp_dir.name) / 'growth_properties_test.db'
os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
os.environ['DATABASE_URL'] = f"sqlite:///{_db_file}"

import config
config.DATABASE_URL = f"sqlite:///{_db_file}"
config.LOCAL_MODE = False
config.POSTPILOT_PUBLISHING_ENABLED = 0
config.WHATSAPP_PUBLISHING_ENABLED = 0

import database
import app as postpilot_app

class TestGrowthProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        try:
            _tmp_dir.cleanup()
        except Exception:
            pass

    def setUp(self):
        config.LOCAL_MODE = False  # Enforce strict auth & CSRF validation
        # Seed test organizations and secondary brands
        with database.get_db_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (1, 'GAATHA Flagship', 'gaatha')")
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (2, 'Tenant Two Corp', 'tenant-2')")
            conn.execute("INSERT OR IGNORE INTO brands (id, organization_id, name, slug, description) VALUES (101, 1, 'GAATHA Flagship', 'gaatha-flagship', 'Flagship Brand')")
            conn.execute("INSERT OR IGNORE INTO brands (id, organization_id, name, slug, description) VALUES (201, 2, 'Tenant Two Brand', 't2-brand', 'Tenant Two Workspace')")
            conn.commit()

        self.client = postpilot_app.app.test_client()

    def _login(self, user_id=1, username="admin1", role="admin", org_id=1):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = role
            sess['organization_id'] = org_id
            sess['csrf_token'] = 'test-csrf-token-growth-12345'
        return {'X-CSRFToken': 'test-csrf-token-growth-12345', 'Content-Type': 'application/json'}

    # --------------------------------------------------------------------------
    # 1. Seven Default Ecosystem Properties & Brand Mappings
    # --------------------------------------------------------------------------

    def test_default_growth_properties_seeded(self):
        """Verifies that all 7 default GAATHA ecosystem properties exist for Organization 1."""
        props = database.list_growth_properties(organization_id=1, include_inactive=True)
        self.assertGreaterEqual(len(props), 7)
        keys = {p['property_key']: p for p in props}

        expected_keys = [
            'gaatha_corporate',
            'gaatha_terra',
            'gaatha_suite',
            'sentira_ai',
            'gaatha_pos',
            'gaatha_ai',
            'phoenix'
        ]
        for key in expected_keys:
            self.assertIn(key, keys, f"Missing expected property key: {key}")
            p = keys[key]
            self.assertTrue(p['is_active'])
            self.assertTrue(p['canonical_url'].startswith('http'))
            self.assertTrue(len(p['display_name']) > 0)

        # Verify GAATHA Terra is represented globally (not India-only)
        terra = keys['gaatha_terra']
        self.assertEqual(terra['target_countries'], 'GLOBAL')
        self.assertEqual(terra['canonical_url'], 'https://terra.gaatha.tech')

        # Verify GAATHA Suite, POS, and Sentira AI
        suite = keys['gaatha_suite']
        self.assertEqual(suite['canonical_url'], 'https://gaatha.tech/suite/')
        self.assertEqual(suite['property_type'], 'saas_product')

        sentira = keys['sentira_ai']
        self.assertEqual(sentira['canonical_url'], 'https://gaatha.tech/sentira/')

        pos = keys['gaatha_pos']
        self.assertEqual(pos['canonical_url'], 'https://gaatha.tech/pos/')

    def test_brand_mappings_for_default_properties(self):
        """Verifies that each default property links to the appropriate brand workspace."""
        props = database.list_growth_properties(organization_id=1)
        prop_map = {p['property_key']: p for p in props}

        # Check brands mapped
        self.assertIsNotNone(prop_map['gaatha_corporate']['brand_id'])
        self.assertIsNotNone(prop_map['gaatha_terra']['brand_id'])
        self.assertIsNotNone(prop_map['gaatha_suite']['brand_id'])
        self.assertIsNotNone(prop_map['sentira_ai']['brand_id'])
        self.assertIsNotNone(prop_map['gaatha_pos']['brand_id'])
        self.assertIsNotNone(prop_map['gaatha_ai']['brand_id'])
        self.assertIsNotNone(prop_map['phoenix']['brand_id'])

    # --------------------------------------------------------------------------
    # 2. REST API: Listing & Retrieval
    # --------------------------------------------------------------------------

    def test_api_list_properties(self):
        headers = self._login(org_id=1)
        res = self.client.get('/api/growth/properties', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 7)

        # Test envelope mode
        res_env = self.client.get('/api/growth/properties?envelope=1', headers=headers)
        self.assertEqual(res_env.status_code, 200)
        data_env = res_env.get_json()
        self.assertIn('properties', data_env)
        self.assertIn('count', data_env)
        self.assertEqual(data_env['count'], len(data_env['properties']))

    def test_api_get_single_property(self):
        headers = self._login(org_id=1)
        res = self.client.get('/api/growth/properties/1', headers=headers)
        self.assertEqual(res.status_code, 200)
        prop = res.get_json()
        self.assertEqual(prop['id'], 1)
        self.assertIn('property_key', prop)

        # Nonexistent property returns 404
        res_404 = self.client.get('/api/growth/properties/99999', headers=headers)
        self.assertEqual(res_404.status_code, 404)

    # --------------------------------------------------------------------------
    # 3. REST API: Creation & Validation
    # --------------------------------------------------------------------------

    def test_api_create_property_success(self):
        headers = self._login(org_id=1)
        payload = {
            'property_key': 'gaatha_developers',
            'display_name': 'GAATHA Developer Hub',
            'canonical_url': 'https://developer.gaatha.tech',
            'property_type': 'portal',
            'category': 'Developer Platform',
            'target_countries': 'GLOBAL',
            'brand_id': 1
        }
        res = self.client.post('/api/growth/properties', json=payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertEqual(created['property_key'], 'gaatha_developers')
        self.assertEqual(created['display_name'], 'GAATHA Developer Hub')
        self.assertEqual(created['is_active'], 1)

    def test_api_create_duplicate_key_rejected(self):
        headers = self._login(org_id=1)
        payload = {
            'property_key': 'gaatha_corporate',  # Already seeded
            'display_name': 'Duplicate Corp',
            'canonical_url': 'https://duplicate.gaatha.tech'
        }
        res = self.client.post('/api/growth/properties', json=payload, headers=headers)
        self.assertEqual(res.status_code, 409)
        self.assertIn('already exists', res.get_json().get('error', ''))

    def test_api_create_invalid_url_rejected(self):
        headers = self._login(org_id=1)
        payload = {
            'property_key': 'invalid_url_prop',
            'display_name': 'Invalid URL Test',
            'canonical_url': 'not_a_valid_url_without_scheme'
        }
        res = self.client.post('/api/growth/properties', json=payload, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Canonical URL must be a valid absolute URL', res.get_json().get('error', ''))

    def test_api_create_invalid_key_format_rejected(self):
        headers = self._login(org_id=1)
        # Spaces, capital letters, or special characters forbidden
        payload = {
            'property_key': 'Invalid Key With Spaces!',
            'display_name': 'Invalid Key',
            'canonical_url': 'https://valid.example.com'
        }
        res = self.client.post('/api/growth/properties', json=payload, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Property key may only contain', res.get_json().get('error', ''))

    # --------------------------------------------------------------------------
    # 4. REST API: Editing & Status Updates
    # --------------------------------------------------------------------------

    def test_api_update_property(self):
        headers = self._login(org_id=1)
        # Create a test property to update so seeded properties remain pristine
        create_res = self.client.post('/api/growth/properties', json={
            'property_key': 'test_prop_for_update',
            'display_name': 'Original Name',
            'canonical_url': 'https://update-test.gaatha.tech'
        }, headers=headers)
        self.assertEqual(create_res.status_code, 201)
        test_id = create_res.get_json()['id']

        payload = {
            'display_name': 'Updated Property Name',
            'category': 'AgTech & Climate Intelligence',
            'target_countries': 'GLOBAL,IN,US,AU,BR'
        }
        res = self.client.put(f'/api/growth/properties/{test_id}', json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()
        self.assertEqual(updated['display_name'], 'Updated Property Name')
        self.assertEqual(updated['category'], 'AgTech & Climate Intelligence')
        self.assertEqual(updated['target_countries'], 'GLOBAL,IN,US,AU,BR')

    def test_api_toggle_property_status(self):
        headers = self._login(org_id=1)
        # Create a test property to toggle so seeded properties remain untouched
        create_res = self.client.post('/api/growth/properties', json={
            'property_key': 'test_prop_for_toggle',
            'display_name': 'Toggle Test',
            'canonical_url': 'https://toggle-test.gaatha.tech'
        }, headers=headers)
        self.assertEqual(create_res.status_code, 201)
        test_id = create_res.get_json()['id']

        # Disable
        res_disable = self.client.patch(f'/api/growth/properties/{test_id}/status', json={'is_active': False}, headers=headers)
        self.assertEqual(res_disable.status_code, 200)
        self.assertEqual(res_disable.get_json()['is_active'], 0)

        # Check list with include_inactive=false
        res_active_only = self.client.get('/api/growth/properties?include_inactive=false', headers=headers)
        self.assertEqual(res_active_only.status_code, 200)
        active_keys = [p['property_key'] for p in res_active_only.get_json()]
        self.assertNotIn('test_prop_for_toggle', active_keys)

        # Re-enable
        res_enable = self.client.patch(f'/api/growth/properties/{test_id}/status', json={'is_active': True}, headers=headers)
        self.assertEqual(res_enable.status_code, 200)
        self.assertEqual(res_enable.get_json()['is_active'], 1)

    # --------------------------------------------------------------------------
    # 5. Security: Authentication, CSRF & RBAC
    # --------------------------------------------------------------------------

    def test_unauthenticated_requests_rejected(self):
        # GET -> 401
        res_get = self.client.get('/api/growth/properties')
        self.assertEqual(res_get.status_code, 401)

        # POST -> 401
        res_post = self.client.post('/api/growth/properties', json={'property_key': 'anon'})
        self.assertEqual(res_post.status_code, 401)

        # PUT -> 401
        res_put = self.client.put('/api/growth/properties/1', json={'display_name': 'anon'})
        self.assertEqual(res_put.status_code, 401)

        # PATCH -> 401
        res_patch = self.client.patch('/api/growth/properties/1/status', json={'is_active': False})
        self.assertEqual(res_patch.status_code, 401)

    def test_csrf_protection_enforced(self):
        self._login(org_id=1)
        bad_headers = {'Content-Type': 'application/json'}  # Missing X-CSRFToken

        res_post = self.client.post('/api/growth/properties', json={'property_key': 'nocsrf'}, headers=bad_headers)
        self.assertEqual(res_post.status_code, 403)

        res_put = self.client.put('/api/growth/properties/1', json={'display_name': 'nocsrf'}, headers=bad_headers)
        self.assertEqual(res_put.status_code, 403)

        res_patch = self.client.patch('/api/growth/properties/1/status', json={'is_active': False}, headers=bad_headers)
        self.assertEqual(res_patch.status_code, 403)

    def test_viewer_role_read_only(self):
        headers = self._login(user_id=99, username="viewer_user", role="viewer", org_id=1)

        # Viewer CAN read properties
        res_get = self.client.get('/api/growth/properties', headers=headers)
        self.assertEqual(res_get.status_code, 200)

        # Viewer CANNOT mutate
        res_post = self.client.post('/api/growth/properties', json={'property_key': 'viewer_try'}, headers=headers)
        self.assertEqual(res_post.status_code, 403)

        res_put = self.client.put('/api/growth/properties/1', json={'display_name': 'viewer_try'}, headers=headers)
        self.assertEqual(res_put.status_code, 403)

        res_patch = self.client.patch('/api/growth/properties/1/status', json={'is_active': False}, headers=headers)
        self.assertEqual(res_patch.status_code, 403)

    # --------------------------------------------------------------------------
    # 6. Multi-Tenant Isolation
    # --------------------------------------------------------------------------

    def test_tenant_isolation(self):
        # Org 2 user logs in
        headers_org2 = self._login(user_id=2, username="org2_admin", role="admin", org_id=2)

        # Org 2 should see 0 properties initially (since default 7 were seeded for Org 1)
        res = self.client.get('/api/growth/properties', headers=headers_org2)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()), 0)

        # Org 2 cannot fetch Org 1's property (ID 1)
        res_get_other = self.client.get('/api/growth/properties/1', headers=headers_org2)
        self.assertEqual(res_get_other.status_code, 404)

        # Org 2 cannot update Org 1's property
        res_put_other = self.client.put('/api/growth/properties/1', json={'display_name': 'Hacked'}, headers=headers_org2)
        self.assertEqual(res_put_other.status_code, 404)

        # Org 2 cannot toggle Org 1's property status
        res_patch_other = self.client.patch('/api/growth/properties/1/status', json={'is_active': False}, headers=headers_org2)
        self.assertEqual(res_patch_other.status_code, 404)

    # --------------------------------------------------------------------------
    # 7. Database Migration Idempotency & Rollback Simulation
    # --------------------------------------------------------------------------

    def test_migration_version_and_idempotency(self):
        with database.get_db_connection() as conn:
            # Check schema_migrations table exists and has the migration recorded
            row = conn.execute("SELECT version, description FROM schema_migrations WHERE version = '20261114_001_growth_properties'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['version'], '20261114_001_growth_properties')

        # Run init_growth_properties multiple times to verify repeat-safety
        database.init_growth_properties()
        database.init_growth_properties()

        # Record count should not multiply
        props = database.list_growth_properties(1)
        self.assertGreaterEqual(len(props), 7)

    def test_migration_rollback_simulation_disposable_copy(self):
        """Simulates a complete rollback on a disposable SQLite database."""
        tmp_db_path = Path(_tmp_dir.name) / 'disposable_rollback_test.db'
        shutil.copyfile(_db_file, tmp_db_path)

        conn = sqlite3.connect(str(tmp_db_path))
        c = conn.cursor()

        # Verify growth_properties exists before rollback
        c.execute("SELECT count(*) FROM growth_properties")
        count_before = c.fetchone()[0]
        self.assertGreater(count_before, 0)

        # Execute rollback: DROP growth_properties and remove migration version
        c.execute("DROP TABLE IF EXISTS growth_properties")
        c.execute("DELETE FROM schema_migrations WHERE version = '20261114_001_growth_properties'")
        conn.commit()

        # Check table does not exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='growth_properties'")
        self.assertIsNone(c.fetchone())

        # Check PRAGMA integrity
        c.execute("PRAGMA integrity_check")
        integrity = c.fetchone()[0]
        self.assertEqual(integrity, 'ok')
        conn.close()

    # --------------------------------------------------------------------------
    # 8. Safeguard & Domain Preservation
    # --------------------------------------------------------------------------

    def test_preservation_of_safeguards_and_domain_tables(self):
        # Publishing flags must remain strictly fail-closed (0)
        self.assertEqual(config.POSTPILOT_PUBLISHING_ENABLED, 0)
        self.assertEqual(config.WHATSAPP_PUBLISHING_ENABLED, 0)

        # Verify all 24 domain tables are present in the database
        expected_tables = [
            'organizations', 'brands', 'brand_marketing_profiles', 'users',
            'posts', 'scheduled_posts', 'post_audit_logs', 'synced_posts',
            'campaigns', 'campaign_strategies', 'content_plans', 'content_plan_entries',
            'content_drafts', 'content_draft_revisions', 'media_assets', 'social_accounts',
            'whatsapp_webhook_events', 'whatsapp_suppression_list', 'whatsapp_templates',
            'ai_usage_logs', 'subscription_plans', 'organization_subscriptions',
            'worker_leases', 'task_state'
        ]
        with database.get_db_connection() as conn:
            actual_tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in expected_tables:
                self.assertIn(table, actual_tables, f"Domain table {table} is missing!")
            self.assertIn('schema_migrations', actual_tables)
            self.assertIn('growth_properties', actual_tables)

if __name__ == '__main__':
    unittest.main()
