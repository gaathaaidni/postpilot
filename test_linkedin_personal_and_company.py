import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import database
import integrations_service
import linkedin_api
import worker
from app import app
from platform_adapters import PlatformRegistry


ROOT = Path(__file__).resolve().parent


class TestLinkedInPersonalAndCompany(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="postpilot_li_test_", suffix=".db")
        os.close(fd)
        self.orig_db_url = config.DATABASE_URL
        config.DATABASE_URL = f"sqlite:///{self.db_path}"
        database.init_db()
        self.client = app.test_client()
        self.app_ctx = app.app_context()
        self.app_ctx.push()

    def tearDown(self):
        self.app_ctx.pop()
        config.DATABASE_URL = self.orig_db_url
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except OSError:
            pass

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'li_test_csrf'

    # 1. Personal text post + centralized API version
    @patch('requests.post')
    @patch('requests.get')
    def test_01_personal_text_post_with_verified_identity(self, mock_get, mock_post):
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {'sub': 'CQ9O2PPp8V', 'name': 'Hardik Gajjar', 'email': 'nexora.aidni@gmail.com'}
        mock_get.return_value = userinfo_resp

        introspect_resp = MagicMock(status_code=200)
        introspect_resp.json.return_value = {'active': True, 'scope': 'email,openid,profile,w_member_social'}
        post_resp = MagicMock(status_code=201, headers={'x-restli-id': 'urn:li:share:personal_101'})
        post_resp.json.return_value = {'id': 'urn:li:share:personal_101'}
        mock_post.side_effect = [introspect_resp, post_resp]

        td = {'access_token': 'AIDNI_PERSONAL_TOK', 'expires_at': time.time() + 3600, 'scope': 'email,openid,profile,w_member_social'}
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0',
            'LINKEDIN_API_VERSION': '202610',
        }), \
             patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'cid_aidni'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'sec_aidni'), \
             patch('linkedin_api.get_token_data', return_value=td), \
             patch('linkedin_api.get_active_token', return_value='AIDNI_PERSONAL_TOK'):
            adapter = PlatformRegistry.get_adapter('linkedin')
            res = adapter.publish({'destination': 'personal', 'app_key': 'aidni_global', 'message': 'Verified personal share'})

        self.assertTrue(res['success'])
        self.assertEqual(res['destination'], 'personal')
        self.assertEqual(res['author_urn'], 'urn:li:person:CQ9O2PPp8V')
        self.assertEqual(res['external_post_id'], 'urn:li:share:personal_101')
        post_call = mock_post.call_args_list[-1]
        self.assertEqual(post_call[0][0], linkedin_api.REST_POSTS_URL)
        self.assertEqual(post_call[1]['headers']['LinkedIn-Version'], '202610')
        self.assertEqual(post_call[1]['json']['author'], 'urn:li:person:CQ9O2PPp8V')

    # 2. Personal image upload + post and unsupported format rejection
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_02_personal_media_upload_and_unsupported_rejection(self, mock_get, mock_post, mock_put):
        with tempfile.TemporaryDirectory() as tmpdir:
            jpg_path = os.path.join(tmpdir, 'sample.jpg')
            with open(jpg_path, 'wb') as f:
                f.write(b'\xff\xd8\xff\xe0MOCKJPEG')
            mp4_path = os.path.join(tmpdir, 'clip.mp4')
            with open(mp4_path, 'wb') as f:
                f.write(b'MOCKMP4')

            userinfo_resp = MagicMock(status_code=200)
            userinfo_resp.json.return_value = {'sub': 'CQ9O2PPp8V', 'name': 'Hardik Gajjar'}
            mock_get.return_value = userinfo_resp

            init_resp = MagicMock(status_code=200)
            init_resp.json.return_value = {'value': {'uploadUrl': 'https://api.linkedin.com/upload/img1', 'image': 'urn:li:image:img1'}}
            post_resp = MagicMock(status_code=201, headers={'x-restli-id': 'urn:li:share:img_202'})
            mock_post.side_effect = [init_resp, post_resp]
            mock_put.return_value = MagicMock(status_code=201)

            td = {'access_token': 'AIDNI_TOK', 'expires_at': time.time() + 3600, 'scope': 'openid,profile,w_member_social'}
            with patch.dict(os.environ, {
                'POSTPILOT_PUBLISHING_ENABLED': '1',
                'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            }), \
                 patch.object(config, 'UPLOAD_FOLDER', tmpdir), \
                 patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['openid', 'profile', 'w_member_social']}), \
                 patch('linkedin_api.get_token_data', return_value=td), \
                 patch('linkedin_api.get_active_token', return_value='AIDNI_TOK'):
                adapter = PlatformRegistry.get_adapter('linkedin')
                bad_res = adapter.publish({'destination': 'personal', 'app_key': 'aidni_global', 'message': 'Video test', 'image_filename': 'clip.mp4'})
                self.assertFalse(bad_res['success'])
                self.assertIn('Unsupported LinkedIn media format', bad_res['error'])

                good_res = adapter.publish({'destination': 'personal', 'app_key': 'aidni_global', 'message': 'Image test', 'image_filename': 'sample.jpg'})
                self.assertTrue(good_res['success'])
                self.assertEqual(good_res['image_urn'], 'urn:li:image:img1')
                init_payload = mock_post.call_args_list[0][1]['json']
                self.assertEqual(init_payload['initializeUploadRequest']['owner'], 'urn:li:person:CQ9O2PPp8V')
                post_payload = mock_post.call_args_list[1][1]['json']
                self.assertEqual(post_payload['content']['media']['id'], 'urn:li:image:img1')

    # 3. Missing OpenID identity or missing w_member_social fails closed
    @patch('requests.post')
    def test_03_personal_blocks_without_identity_or_member_scope(self, mock_post):
        gaatha_td = {'access_token': 'GAATHA_ONLY_SHARE', 'expires_at': time.time() + 3600, 'scope': 'w_member_social'}
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
        }), \
             patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['w_member_social']}), \
             patch('linkedin_api.get_token_data', return_value=gaatha_td), \
             patch('linkedin_api.get_active_token', return_value='GAATHA_ONLY_SHARE'), \
             patch('linkedin_api.get_authenticated_member', return_value={'success': False, 'status_code': 403, 'error': 'ACCESS_DENIED'}):
            adapter = PlatformRegistry.get_adapter('linkedin')
            res = adapter.publish({'destination': 'personal', 'app_key': 'gaatha_ventures', 'message': 'Must fail closed'})
        self.assertFalse(res['success'])
        self.assertEqual(res['error_code'], 'IDENTITY_SCOPE_REQUIRED')
        mock_post.assert_not_called()

        no_write_td = {'access_token': 'READ_ONLY', 'expires_at': time.time() + 3600, 'scope': 'openid,profile'}
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
        }), \
             patch('linkedin_api.get_token_data', return_value=no_write_td), \
             patch('linkedin_api.get_active_token', return_value='READ_ONLY'):
            ident = linkedin_api.resolve_member_author('aidni_global', verify_live=False)
        self.assertFalse(ident['success'])
        self.assertEqual(ident['error_code'], 'MISSING_W_MEMBER_SOCIAL')

    # 4. Company-page blocked without Community Management API or admin ACL (no silent fallback)
    @patch('requests.post')
    @patch('requests.get')
    def test_04_company_blocked_without_cm_api_and_acl_then_succeeds_when_authorized(self, mock_get, mock_post):
        no_org_td = {'access_token': 'AIDNI_TOK', 'expires_at': time.time() + 3600, 'scope': 'email,openid,profile,w_member_social'}
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1', 'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '1', 'POSTPILOT_ALLOWED_PLATFORMS': 'facebook,linkedin'}), \
             patch('linkedin_api.get_token_data', return_value=no_org_td), \
             patch('linkedin_api.get_active_token', return_value='AIDNI_TOK'):
            adapter = PlatformRegistry.get_adapter('linkedin')
            res = adapter.publish({'destination': 'organization', 'linkedin_org_id': '145240694', 'message': 'Org attempt'})
        self.assertFalse(res['success'])
        self.assertEqual(res['destination'], 'organization')
        self.assertEqual(res['error_code'], 'COMMUNITY_MANAGEMENT_API_REQUIRED')
        mock_post.assert_not_called()

        # With w_organization_social but non-admin ACL -> must block
        org_td = {'access_token': 'ORG_TOK', 'expires_at': time.time() + 3600, 'scope': 'w_member_social,w_organization_social'}
        no_admin_acl = MagicMock(status_code=200)
        no_admin_acl.json.return_value = {'elements': [{'organization': 'urn:li:organization:145240694', 'role': 'FOLLOWER', 'state': 'APPROVED'}]}
        mock_get.return_value = no_admin_acl
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1', 'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '1', 'POSTPILOT_ALLOWED_PLATFORMS': 'facebook,linkedin'}), \
             patch('linkedin_api.get_token_data', return_value=org_td), \
             patch('linkedin_api.get_active_token', return_value='ORG_TOK'):
            res_acl = PlatformRegistry.get_adapter('linkedin').publish({'destination': 'organization', 'linkedin_org_id': '145240694', 'message': 'Non admin'})
        self.assertFalse(res_acl['success'])
        self.assertEqual(res_acl['error_code'], 'NOT_ORGANIZATION_ADMIN')
        mock_post.assert_not_called()

        # With w_organization_social + APPROVED ADMINISTRATOR ACL -> succeeds
        admin_acl = MagicMock(status_code=200)
        admin_acl.json.return_value = {'elements': [{'organization': 'urn:li:organization:145250613', 'role': 'ADMINISTRATOR', 'state': 'APPROVED'}]}
        mock_get.return_value = admin_acl
        mock_post.return_value = MagicMock(status_code=201, headers={'x-restli-id': 'urn:li:share:org_ok'})
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1', 'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '1', 'POSTPILOT_ALLOWED_PLATFORMS': 'facebook,linkedin'}), \
             patch('linkedin_api.get_token_data', return_value=org_td), \
             patch('linkedin_api.get_active_token', return_value='ORG_TOK'):
            res_ok = PlatformRegistry.get_adapter('linkedin').publish({'destination': 'organization', 'linkedin_org_id': '145250613', 'message': 'Authorized org'})
        self.assertTrue(res_ok['success'])
        self.assertEqual(res_ok['destination'], 'organization')
        self.assertEqual(res_ok['organization_id'], '145250613')

        # Even with w_organization_social + APPROVED ADMINISTRATOR ACL:
        # If POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED=0, it MUST REMAIN BLOCKED!
        mock_post.reset_mock()
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1', 'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0', 'POSTPILOT_ALLOWED_PLATFORMS': 'facebook,linkedin'}), \
             patch('linkedin_api.get_token_data', return_value=org_td), \
             patch('linkedin_api.get_active_token', return_value='ORG_TOK'):
            res_disabled = PlatformRegistry.get_adapter('linkedin').publish({'destination': 'organization', 'linkedin_org_id': '145250613', 'message': 'Flag disabled'})
        self.assertFalse(res_disabled['success'])
        self.assertEqual(res_disabled['error_code'], 'COMPANY_PUBLISHING_DISABLED')
        mock_post.assert_not_called()

    # 5. Refresh token preservation & log redaction
    @patch('requests.post')
    def test_05_refresh_token_preservation_and_redaction(self, mock_post):
        sanitized = linkedin_api.sanitize_log_message("err access_token=SECRET1 refresh_token=SECRET_REF client_secret=SEC code=CODE1")
        self.assertNotIn('SECRET1', sanitized)
        self.assertNotIn('SECRET_REF', sanitized)
        self.assertNotIn('SEC', sanitized)
        self.assertNotIn('CODE1', sanitized)

        existing = {'aidni_global': {'access_token': 'KEEP_ME_ACTIVE', 'expires_at': time.time() + 3600, 'scope': 'w_member_social'}}
        with patch('linkedin_api.get_token_data', return_value=existing['aidni_global']):
            res_missing = linkedin_api.refresh_access_token('aidni_global')
        self.assertFalse(res_missing['success'])
        self.assertFalse(res_missing['refresh_supported'])
        self.assertTrue(res_missing['reauth_required'])

        mock_post.return_value = MagicMock(status_code=200, headers={'content-type': 'application/json'}, json=lambda: {'access_token': 'REFRESHED_NEW', 'expires_in': 5184000, 'refresh_token': 'NEW_REF_TOK'})
        saved = {}
        with patch.object(config, 'LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP', 'cid'), \
             patch.object(config, 'LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP', 'sec'), \
             patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['w_member_social']}), \
             patch('linkedin_api.get_token_data', return_value={'access_token': 'OLD', 'refresh_token': 'OLD_REF', 'scope': 'w_member_social'}), \
             patch('linkedin_api.save_token_data', side_effect=lambda k, t: saved.update({k: t})):
            res_ok = linkedin_api.refresh_access_token('aidni_global')
        self.assertTrue(res_ok['success'])
        self.assertEqual(saved['aidni_global']['access_token'], 'REFRESHED_NEW')

    # 6. Independent 3-destination status & zero secret disclosure
    def test_06_three_independent_destinations_status_and_no_secret_leak(self):
        aidni_tok = {'access_token': 'SECRET_AIDNI_RAW_TOKEN', 'expires_at': time.time() + 86400, 'scope': 'email,openid,profile,w_member_social'}
        gaatha_tok = {'access_token': 'SECRET_GAATHA_RAW_TOKEN', 'expires_at': time.time() + 86400, 'scope': 'w_member_social'}
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0',
        }), \
             patch('linkedin_api.get_token_data', side_effect=lambda k: aidni_tok if k == 'aidni_global' else gaatha_tok), \
             patch('linkedin_api.get_active_token', side_effect=lambda k: aidni_tok['access_token'] if k == 'aidni_global' else gaatha_tok['access_token']), \
             patch('linkedin_api.get_authenticated_member', return_value={'success': True, 'sub': 'CQ9O2PPp8V', 'name': 'Hardik Gajjar', 'author_urn': 'urn:li:person:CQ9O2PPp8V'}), \
             patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['w_member_social']}):
            self._login()
            resp = self.client.get('/api/linkedin/status')
        self.assertEqual(resp.status_code, 200)
        body_text = resp.get_data(as_text=True)
        self.assertNotIn('SECRET_AIDNI_RAW_TOKEN', body_text)
        self.assertNotIn('SECRET_GAATHA_RAW_TOKEN', body_text)

        st = integrations_service.get_linkedin_integration_status() if False else resp.get_json()
        self.assertIn('apps', st)
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0',
        }), \
             patch('linkedin_api.get_token_data', side_effect=lambda k: aidni_tok if k == 'aidni_global' else gaatha_tok), \
             patch('linkedin_api.get_active_token', side_effect=lambda k: aidni_tok['access_token'] if k == 'aidni_global' else gaatha_tok['access_token']), \
             patch('linkedin_api.get_authenticated_member', return_value={'success': True, 'sub': 'CQ9O2PPp8V', 'name': 'Hardik Gajjar', 'author_urn': 'urn:li:person:CQ9O2PPp8V'}), \
             patch('linkedin_api.introspect_token', return_value={'checked': True, 'active': True, 'scopes': ['w_member_social']}):
            int_li = integrations_service.get_linkedin_integration_status()
        dests = {d['key']: d for d in int_li['destinations']}
        self.assertTrue(dests['personal:aidni_global']['personal_publishing_ready'])
        self.assertEqual(dests['personal:aidni_global']['status_label'], 'Personal Publishing Ready')
        self.assertFalse(dests['organization:145240694']['organization_publishing_ready'])
        self.assertEqual(dests['organization:145240694']['status_label'], 'Approval Pending')
        self.assertFalse(dests['organization:145250613']['organization_publishing_ready'])
        self.assertEqual(dests['organization:145250613']['status_label'], 'Approval Pending')

    # 7. Duplicate protection, worker timeout reclaim safety, queued LinkedIn non-dispatch, history recording
    def test_07_duplicate_protection_and_worker_never_claims_queued_linkedin(self):
        li_post = database.create_scheduled_post(
            'linkedin', '2026-11-10 10:00:00', message='Queued LI Org post', brand_id=1,
            timezone_name='Asia/Kolkata', allow_past=True
        )
        li_post_id = li_post['id'] if isinstance(li_post, dict) else li_post
        # Production flags: facebook worker live, linkedin worker disabled, personal explicit enabled
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_FACEBOOK_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0',
        }), patch('platform_adapters.PlatformRegistry.dispatch') as mock_dispatch:
            worker.process_due_scheduled_posts('test-worker')
            mock_dispatch.assert_not_called()
            rec = database.get_scheduled_post_by_id(li_post_id)
            self.assertEqual(rec['status'], 'scheduled')

        # Timed-out row that ALREADY got an external_post_id must NEVER be reclaimed
        fb_post = database.create_scheduled_post(
            'facebook', '2026-11-10 10:00:00', message='Timed out already posted', brand_id=1,
            timezone_name='Asia/Kolkata', allow_past=True
        )
        fb_post_id = fb_post['id'] if isinstance(fb_post, dict) else fb_post
        with database.get_db_connection() as conn:
            conn.execute(
                "UPDATE scheduled_posts SET status = 'publishing', locked_at = datetime('now', '-600 seconds'), external_post_id = 'urn:li:share:already_done' WHERE id = ?",
                (fb_post_id,)
            )
            conn.commit()
        reclaimed = database.claim_due_scheduled_posts('test-worker', limit=10, allowed_platforms=['facebook'])
        self.assertEqual(reclaimed, [])

        # Immediate publication history & idempotency dedup via /api/publish
        self._login()
        fake_adapter = MagicMock()
        fake_adapter.validate_content.return_value = (True, None)
        fake_adapter.publish.return_value = {
            'success': True,
            'platform': 'linkedin',
            'destination': 'personal',
            'external_post_id': 'urn:li:share:immediate_777',
            'author_urn': 'urn:li:person:CQ9O2PPp8V',
            'app_key': 'aidni_global',
            'simulated': False,
        }
        with patch.dict(os.environ, {
            'POSTPILOT_PUBLISHING_ENABLED': '1',
            'POSTPILOT_ALLOWED_PLATFORMS': 'facebook',
            'POSTPILOT_LINKEDIN_PUBLISHING_ENABLED': '0',
            'POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED': '1',
            'POSTPILOT_LINKEDIN_COMPANY_PUBLISHING_ENABLED': '0',
        }), patch('platform_adapters.PlatformRegistry.get_adapter', return_value=fake_adapter):
            p1 = self.client.post(
                '/api/publish',
                headers={'X-CSRF-Token': 'li_test_csrf'},
                json={'platform': 'linkedin', 'destination': 'personal', 'app_key': 'aidni_global', 'message': 'Explicit live post', 'idempotency_key': 'idem_li_01'}
            )
            self.assertEqual(p1.status_code, 200)
            p2 = self.client.post(
                '/api/publish',
                headers={'X-CSRF-Token': 'li_test_csrf'},
                json={'platform': 'linkedin', 'destination': 'personal', 'app_key': 'aidni_global', 'message': 'Explicit live post', 'idempotency_key': 'idem_li_01'}
            )
            self.assertEqual(p2.status_code, 200)
            self.assertTrue(p2.get_json()['deduplicated'])
            fake_adapter.publish.assert_called_once()

            # Company page immediate publish must be rejected 403
            comp = self.client.post(
                '/api/publish',
                headers={'X-CSRF-Token': 'li_test_csrf'},
                json={'platform': 'linkedin', 'destination': 'organization', 'linkedin_org_id': '145240694', 'message': 'Org blocked'}
            )
            self.assertEqual(comp.status_code, 403)
            self.assertTrue(comp.get_json()['blocked_by_guardrail'])

    # 8. UI markers check
    def test_08_ui_contains_three_destinations_and_explicit_publish_confirmation(self):
        html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        js = (ROOT / 'static/script.js').read_text(encoding='utf-8')
        self.assertIn('id="post-linkedin-destination"', html)
        self.assertIn('personal:aidni_global', html)
        self.assertIn('organization:145240694', html)
        self.assertIn('organization:145250613', html)
        self.assertIn('id="publish-now-post-btn"', html)
        self.assertIn('publishComposerPostNow', js)
        self.assertIn('window.confirm(', js)


if __name__ == '__main__':
    unittest.main()
