import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_TMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_TMP.name) / 'posts.db'}"
os.environ['POSTPILOT_DATA_DIR'] = _TMP.name
os.environ['POSTPILOT_UPLOAD_FOLDER'] = str(Path(_TMP.name) / 'uploads')

import config
import database
import facebook_api
import integrations_service
from app import app
from platform_adapters.facebook import FacebookAdapter
from platform_adapters.instagram import InstagramAdapter
from platform_adapters.whatsapp import WhatsAppCloudAdapter


class TestMetaAssetConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()

    def setUp(self):
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test_csrf'

    def tearDown(self):
        self.ctx.pop()

    def test_01_all_five_facebook_pages_configured(self):
        expected = {
            '1028368893692590',
            '954901604381882',
            '967550829768297',
            '374211199112915',
            '178168346255851',
        }
        pages = FacebookAdapter().get_configured_pages()
        actual_ids = {p['page_id'] for p in pages.values()}
        self.assertTrue(expected.issubset(actual_ids), f"Missing FB Pages: {expected - actual_ids}")
        self.assertEqual(set(config.VERIFIED_META_PAGES.keys()), expected)

    def test_02_all_three_instagram_accounts_and_page_mappings(self):
        expected_ig = {
            '17841471822022390': '954901604381882',  # @phoenixbygaatha -> Pheonix
            '17841449080283492': '967550829768297',  # @gaathasuite -> Gaatha Suite
            '17841467723671727': '374211199112915',  # @grahak.chetna -> Grahak Chetna
        }
        ig_adapter = InstagramAdapter()
        accounts = ig_adapter.get_configured_accounts()
        by_ig_id = {a['ig_user_id']: a for a in accounts.values()}
        for ig_id, page_id in expected_ig.items():
            self.assertIn(ig_id, by_ig_id)
            self.assertEqual(by_ig_id[ig_id]['linked_page_id'], page_id)
            self.assertEqual(ig_adapter.get_linked_facebook_page_id(ig_id), page_id)
            matched = ig_adapter.get_account_for_facebook_page(page_id)
            self.assertIsNotNone(matched)
            self.assertEqual(matched['ig_user_id'], ig_id)

        # Config must never hold old wrong INSTA_ID_PHOENIX default 17841472248438802
        self.assertNotEqual(config.INSTA_ID_PHOENIX, '17841472248438802')

    def test_03_duplicate_account_prevention_and_brand_mapping(self):
        database.reconcile_verified_meta_accounts(organization_id=1)
        first_cnt = len(database.get_social_accounts(organization_id=1))
        database.reconcile_verified_meta_accounts(organization_id=1)
        second_cnt = len(database.get_social_accounts(organization_id=1))
        self.assertEqual(first_cnt, second_cnt, "Reconciliation must not create duplicate social_accounts rows")

        # Verify exact 6 default brands preserved
        with database.get_db_connection() as conn:
            brands_cnt = conn.execute("SELECT COUNT(*) FROM brands WHERE organization_id = 1").fetchone()[0]
        self.assertEqual(brands_cnt, 6)

        # Check Brand 1 (Suite), Brand 5 (Phoenix), Brand 6 (Gaatha AI), and Brands 2/3/4 isolation
        self.assertEqual(database.get_social_account_for_brand(1, 1, 'facebook')['account_identifier'], '967550829768297')
        ig_b1 = database.get_social_account_for_brand(1, 1, 'instagram')
        self.assertEqual(ig_b1['account_identifier'], '17841449080283492')
        self.assertEqual(ig_b1['account_name'], '@gaathasuite')

        self.assertEqual(database.get_social_account_for_brand(1, 5, 'facebook')['account_identifier'], '954901604381882')
        self.assertEqual(database.get_social_account_for_brand(1, 5, 'instagram')['account_identifier'], '17841471822022390')
        self.assertEqual(database.get_social_account_for_brand(1, 6, 'facebook')['account_identifier'], '1028368893692590')

        for iso_brand in (2, 3, 4):
            self.assertIsNone(database.get_social_account_for_brand(1, iso_brand, 'facebook'))
            self.assertIsNone(database.get_social_account_for_brand(1, iso_brand, 'instagram'))

        # Neither WhatsApp number auto-assigned to any brand
        for acct in database.get_social_accounts(organization_id=1, platform='whatsapp'):
            self.assertNotIn(acct['account_identifier'], ('1298748379987770', '1171737406016871'))

    def test_04_token_validation_expiry_missing_and_secret_redaction(self):
        fake_secret = 'EAASECRETTOKEN9999999999999999999'

        # Missing token
        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': ''}), \
             patch.object(integrations_service.config, 'FB_ACCESS_TOKEN', None):
            res_missing = integrations_service.discover_meta_properties(organization_id=1)
        self.assertFalse(res_missing['success'])
        self.assertTrue(res_missing['authentication_failure'])
        self.assertEqual(res_missing['status_label'], integrations_service.STATUS_CREDENTIALS_MISSING)

        # Expired / invalid token & secret redaction in error string
        def _expired_get(url, **kwargs):
            m = MagicMock()
            if '/debug_token' in url:
                m.json.return_value = {'data': {'is_valid': False, 'app_id': '1397769361108621', 'expires_at': 100, 'error': {'message': f'Session expired for {fake_secret}'}}}
            else:
                m.json.return_value = {'error': {'code': 190, 'type': 'OAuthException', 'message': f'Invalid OAuth token {fake_secret}'}}
            return m

        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': fake_secret}), \
             patch.object(integrations_service.config, 'FB_ACCESS_TOKEN', fake_secret), \
             patch('requests.get', side_effect=_expired_get):
            res_exp = integrations_service.discover_meta_properties(organization_id=1)

        self.assertFalse(res_exp['success'])
        self.assertTrue(res_exp['authentication_failure'])
        self.assertEqual(res_exp['status_label'], integrations_service.STATUS_AUTHENTICATION_REQUIRED)
        self.assertNotIn(fake_secret, json.dumps(res_exp))

    def test_05_account_states_publishing_guardrails_and_whatsapp_isolation(self):
        # Simulate production flags: FB=1, IG=0, LI=0, WA=0
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_FACEBOOK_PUBLISHING_ENABLED': '1',
            'POSTPILOT_INSTAGRAM_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'WHATSAPP_PUBLISHING_ENABLED': '0',
            'FB_ACCESS_TOKEN': 'tok_valid',
        }), patch.object(integrations_service.config, 'FB_ACCESS_TOKEN', 'tok_valid'):
            self.assertTrue(config.is_platform_publishing_enabled('facebook'))
            self.assertFalse(config.is_platform_publishing_enabled('instagram'))
            self.assertFalse(config.is_platform_publishing_enabled('whatsapp'))

            database.reconcile_verified_meta_accounts(organization_id=1)

            def _live_meta_get(url, **kwargs):
                m = MagicMock()
                if '/debug_token' in url:
                    m.json.return_value = {'data': {'is_valid': True, 'type': 'USER', 'app_id': '1397769361108621', 'expires_at': 0, 'scopes': ['pages_manage_posts', 'instagram_content_publish']}}
                elif '/me/accounts' in url:
                    m.json.return_value = {'data': [
                        {'id': '954901604381882', 'name': 'Pheonix by Aidni Global LLP', 'tasks': ['MANAGE', 'CREATE_CONTENT'], 'connected_instagram_account': {'id': '17841471822022390', 'username': 'phoenixbygaatha', 'media_count': 0}},
                        {'id': '967550829768297', 'name': 'Gaatha Suite', 'tasks': ['MANAGE', 'CREATE_CONTENT'], 'connected_instagram_account': {'id': '17841449080283492', 'username': 'gaathasuite', 'media_count': 16}},
                    ]}
                else:
                    m.json.return_value = {'data': []}
                return m

            with patch('requests.get', side_effect=_live_meta_get):
                meta = integrations_service.discover_meta_properties(organization_id=1)

            self.assertTrue(meta['success'])
            self.assertFalse(meta['authentication_failure'])
            fb_phoenix = meta['pages'][0]
            self.assertEqual(fb_phoenix['account_state'], 'publishing_ready')
            self.assertTrue(fb_phoenix['connected'])
            self.assertTrue(fb_phoenix['read_access_verified'])
            self.assertTrue(fb_phoenix['publishing_ready'])
            self.assertFalse(fb_phoenix['publishing_disabled'])

            ig_phoenix = meta['instagram_accounts'][0]
            self.assertEqual(ig_phoenix['account_state'], 'publishing_disabled')
            self.assertTrue(ig_phoenix['connected'])
            self.assertTrue(ig_phoenix['read_access_verified'])
            self.assertFalse(ig_phoenix['publishing_ready'])
            self.assertTrue(ig_phoenix['publishing_disabled'])
            self.assertEqual(ig_phoenix['media_count'], 0)

        # WhatsApp preferred sender vs secondary rejection
        wa = WhatsAppCloudAdapter()
        ok_p, pid, _ = wa.validate_sender('1298748379987770')
        self.assertTrue(ok_p)
        self.assertEqual(pid, '1298748379987770')
        ok_s, _, err_s = wa.validate_sender('1171737406016871')
        self.assertFalse(ok_s)
        self.assertIn('not offered', err_s.lower())


if __name__ == '__main__':
    unittest.main()

