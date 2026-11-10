import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Isolate test runtime data cleanly BEFORE importing config/database
_TEST_TMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_TEST_TMP.name) / 'posts.db'}"
os.environ['POSTPILOT_DATA_DIR'] = _TEST_TMP.name
os.environ['POSTPILOT_UPLOAD_FOLDER'] = str(Path(_TEST_TMP.name) / 'uploads')
os.environ['POSTPILOT_PUBLISHING_ENABLED'] = '0'
os.environ['POSTPILOT_ALLOWED_PLATFORMS'] = ''
os.environ['POSTPILOT_FACEBOOK_PUBLISHING_ENABLED'] = ''
os.environ['POSTPILOT_INSTAGRAM_PUBLISHING_ENABLED'] = ''
os.environ['POSTPILOT_LINKEDIN_PUBLISHING_ENABLED'] = ''
os.environ['WHATSAPP_PUBLISHING_ENABLED'] = '0'

import config
import database
import worker
import facebook_api
import linkedin_api
from platform_adapters import PlatformRegistry
from platform_adapters.facebook import FacebookAdapter
from platform_adapters.instagram import InstagramAdapter
from platform_adapters.linkedin import LinkedInAdapter
from platform_adapters.whatsapp import WhatsAppCloudAdapter
import app as flask_app


class TestProductionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert _TEST_TMP.name in str(config.DATABASE_URL) and _TEST_TMP.name in str(config.DATA_DIR), (
            f"Unsafe DB path in test: {config.DATABASE_URL} / {config.DATA_DIR}"
        )
        database.init_db()

    def setUp(self):
        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM post_audit_logs")
            conn.execute("DELETE FROM scheduled_posts")
            conn.commit()

    def test_01_per_platform_isolation_blocks_whatsapp_and_instagram(self):
        env_patch = {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_FACEBOOK_PUBLISHING_ENABLED': '1',
            'POSTPILOT_INSTAGRAM_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'WHATSAPP_PUBLISHING_ENABLED': '0',
        }
        with patch.dict(os.environ, env_patch):
            self.assertTrue(config.is_platform_publishing_enabled('facebook'))
            self.assertFalse(config.is_platform_publishing_enabled('instagram'))
            self.assertFalse(config.is_platform_publishing_enabled('linkedin'))
            self.assertFalse(config.is_platform_publishing_enabled('whatsapp'))
            self.assertEqual(config.get_enabled_publishing_platforms(), ['facebook'])

            with patch('requests.post') as any_post:
                wa_res = WhatsAppCloudAdapter().send_template('+919825728291', 'hello_world')
                self.assertTrue(wa_res.get('simulated'))

                ig_res = InstagramAdapter().create_container('17841449080283492', 'https://postpilot.gaatha.tech/x.jpg', 'hi')
                self.assertTrue(ig_res.get('simulated'))

                li_res = linkedin_api.create_organization_post('145240694', 'hi')
                self.assertTrue(li_res.get('simulated'))

                any_post.assert_not_called()

    def test_02_whatsapp_never_activates_from_global_flag_alone(self):
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': '',
            'WHATSAPP_PUBLISHING_ENABLED': '',
        }):
            self.assertTrue(config.is_platform_publishing_enabled('facebook'))
            self.assertFalse(config.is_platform_publishing_enabled('whatsapp'))

    def test_03_worker_claims_only_enabled_platforms_and_rejects_simulated(self):
        database.create_scheduled_post(
            'facebook', '2026-11-10 10:00:00', message='FB due', brand_id=1,
            timezone_name='Asia/Kolkata', allow_past=True
        )
        database.create_scheduled_post(
            'whatsapp', '2026-11-10 10:00:00', message='WA due', brand_id=1,
            timezone_name='Asia/Kolkata', allow_past=True
        )
        database.create_scheduled_post(
            'instagram', '2026-11-10 10:00:00', message='IG due', brand_id=1,
            image_filename='test.jpg', timezone_name='Asia/Kolkata', allow_past=True
        )

        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_FACEBOOK_PUBLISHING_ENABLED': '1',
            'POSTPILOT_INSTAGRAM_PUBLISHING_ENABLED': '0',
            'WHATSAPP_PUBLISHING_ENABLED': '0',
        }):
            with patch.object(PlatformRegistry, 'dispatch', return_value={
                'success': True,
                'external_post_id': 'fb_post_sim_1',
                'simulated': True,
                'message': 'Simulated only'
            }):
                worker.process_due_scheduled_posts('test-worker', allow_simulation=False)

        rows = database.get_scheduled_posts(organization_id=1)
        by_plat = {r['post_type']: r for r in rows}
        self.assertEqual(by_plat['whatsapp']['status'], 'scheduled')
        self.assertEqual(by_plat['instagram']['status'], 'scheduled')
        self.assertNotEqual(by_plat['facebook']['status'], 'published')
        self.assertIn('Simulated', by_plat['facebook']['error_message'] or '')

    def test_04_linkedin_adapter_uses_linkedin_org_id_and_upload_folder(self):
        upload_dir = Path(config.UPLOAD_FOLDER)
        upload_dir.mkdir(parents=True, exist_ok=True)
        img_file = upload_dir / 'sample_li.png'
        img_file.write_bytes(b'PNGDATA')

        with patch('linkedin_api.initialize_image_upload', return_value={
            'success': True, 'upload_url': 'https://upload.example/put', 'image_urn': 'urn:li:image:123'
        }) as mock_init, patch('linkedin_api.upload_image_file', return_value=True) as mock_up, \
             patch('linkedin_api.create_organization_post', return_value={'success': True, 'id': 'urn:li:share:999'}) as mock_post:
            res = LinkedInAdapter().publish({
                'organization_id': 1,
                'linkedin_org_id': '145240694',
                'app_key': 'aidni_global',
                'message': 'Test LI',
                'image_filename': 'sample_li.png'
            })
            self.assertTrue(res['success'])
            self.assertEqual(res['organization_id'], '145240694')
            mock_init.assert_called_once()
            self.assertEqual(mock_init.call_args[0][0], '145240694')
            mock_up.assert_called_once_with('https://upload.example/put', str(img_file))
            mock_post.assert_called_once()

    def test_05_immediate_publication_idempotency_and_history(self):
        r1 = database.record_immediate_publication(
            post_type='facebook',
            message='Beta Launch',
            external_post_id='967550829768297_111111',
            brand_id=1,
            organization_id=1,
            created_by=1,
            idempotency_key='beta-launch-suite-test',
            permalink_url='https://www.facebook.com/967550829768297/posts/111111'
        )
        r2 = database.record_immediate_publication(
            post_type='facebook',
            message='Beta Launch',
            external_post_id='967550829768297_222222',
            brand_id=1,
            organization_id=1,
            created_by=1,
            idempotency_key='beta-launch-suite-test',
            permalink_url='https://www.facebook.com/967550829768297/posts/222222'
        )
        self.assertEqual(r1['id'], r2['id'])
        self.assertEqual(r2['external_post_id'], '967550829768297_111111')
        hist = database.get_post_audit_history(r1['id'], organization_id=1)
        self.assertTrue(any('permalink_url' in (h.get('metadata') or '') for h in hist))

    def test_06_meta_sync_connected_pages_maps_all_pages_to_env(self):
        tmp_env = Path(_TEST_TMP.name) / '.env.test'
        tmp_env.write_text('SECRET_KEY=preserve_me\nPOSTPILOT_PUBLISHING_ENABLED=0\n', encoding='utf-8')
        mock_payload = {
            'data': [
                {'id': '967550829768297', 'name': 'Gaatha Suite', 'instagram_business_account': {'id': '17841449080283492'}},
                {'id': '954901604381882', 'name': 'Pheonix by Aidni Global LLP', 'instagram_business_account': {'id': '17841471822022390'}},
                {'id': '1028368893692590', 'name': 'Gaatha AI '},
                {'id': '178168346255851', 'name': 'Gaatha'},
                {'id': '374211199112915', 'name': 'Grahak Chetna', 'instagram_business_account': {'id': '17841467723671727'}},
            ]
        }
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = mock_payload
        with patch.dict(os.environ, {'FB_ACCESS_TOKEN': 'test_tok_val'}):
            with patch('facebook_api.requests.get', return_value=mock_resp):
                res = facebook_api.sync_connected_pages_to_env(env_path=tmp_env)
            pages = FacebookAdapter().get_configured_pages()
            self.assertIn('gaatha', pages)
            self.assertIn('grahak_chetna', pages)
        self.assertTrue(res['success'])
        self.assertEqual(res['pages_count'], 5)
        written = tmp_env.read_text(encoding='utf-8')
        self.assertIn('SECRET_KEY=preserve_me', written)
        self.assertIn('FB_PAGE_ID_GAATHA=178168346255851', written)
        self.assertIn('FB_PAGE_ID_GRAHAK_CHETNA=374211199112915', written)
        self.assertIn('INSTA_ID_GRAHAK_CHETNA=17841467723671727', written)

    def test_07_api_publish_guardrail_and_status(self):
        client = flask_app.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['organization_id'] = 1
            sess['role'] = 'admin'
            sess['csrf_token'] = 'tok123'

        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_FACEBOOK_PUBLISHING_ENABLED': '1',
            'POSTPILOT_INSTAGRAM_PUBLISHING_ENABLED': '0',
            'WHATSAPP_PUBLISHING_ENABLED': '0',
        }):
            st = client.get('/api/status').get_json()
            self.assertEqual(st['enabled_publishing_platforms'], ['facebook'])
            self.assertFalse(st['publishing_platforms']['whatsapp'])

            wa_resp = client.post(
                '/api/publish',
                json={'post_type': 'whatsapp', 'message': 'Blocked test'},
                headers={'X-CSRFToken': 'tok123'}
            )
            self.assertEqual(wa_resp.status_code, 403)
            self.assertTrue(wa_resp.get_json()['blocked_by_guardrail'])

    def test_08_orphan_cleanup_protects_scheduled_posts_media(self):
        upload_dir = Path(config.UPLOAD_FOLDER)
        upload_dir.mkdir(parents=True, exist_ok=True)
        fname = 'protected_sched_video.mp4'
        fpath = upload_dir / fname
        fpath.write_bytes(b'VIDEO')
        database.create_scheduled_post(
            'facebook', '2026-11-12 10:00:00', message='With video',
            image_filename=fname, brand_id=1, timezone_name='Asia/Kolkata'
        )
        flask_app._cleanup_single_image(fname)
        self.assertTrue(fpath.exists())

    def test_09_asia_kolkata_scheduling_and_non_dispatching_cycle(self):
        rec = database.create_scheduled_post(
            'facebook', '2026-11-10 18:00:00', message='IST non-dispatch verify',
            brand_id=1, timezone_name='Asia/Kolkata', allow_past=True
        )
        self.assertEqual(rec['scheduled_for'], '2026-11-10 12:30:00')
        with patch('requests.post') as any_post:
            worker.process_due_scheduled_posts('test-sim-worker', allow_simulation=True)
            any_post.assert_not_called()
        updated = database.get_scheduled_post_by_id(rec['id'], organization_id=1)
        self.assertEqual(updated['status'], 'published')
        self.assertIn('_sim_', updated['external_post_id'] or '')


if __name__ == '__main__':
    unittest.main()
