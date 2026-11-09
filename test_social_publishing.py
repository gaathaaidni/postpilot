"""
POSTPILOT — PHASE 2 SOCIAL PUBLISHING & ACCOUNT MANAGEMENT TEST SUITE
======================================================================
Comprehensive automated verification for:
1. Facebook Page selection, brand routing, photo/video payload, and error classification.
2. Instagram 3-phase container lifecycle, public media validation, hashtag limits, and brand routing.
3. LinkedIn dual-app organization routing, REST 3-step image upload, and error classification.
4. Social account management schema, seeding, multi-tenant REST endpoints, and zero secret disclosure.
5. External post ID persistence in scheduled_posts table.
"""

import unittest
import os
import tempfile
import sqlite3
import json
from unittest.mock import patch, MagicMock

# Ensure we test with publishing disabled by default (safety first!)
os.environ['POSTPILOT_PUBLISHING_ENABLED'] = '0'

import database
from platform_adapters.facebook import FacebookAdapter
from platform_adapters.instagram import InstagramAdapter
from platform_adapters.linkedin import LinkedInAdapter
import linkedin_api
import app as flask_app
import config


class TestFacebookPublishing(unittest.TestCase):
    """Verifies Facebook Page selection, media handling, and error handling."""

    def setUp(self):
        self.adapter = FacebookAdapter()

    def test_brand_page_resolution(self):
        """FacebookAdapter resolves correct Page ID for Brand 1, Brand 5, and custom."""
        page_brand1 = self.adapter.resolve_page_id(brand_id=1)
        self.assertEqual(page_brand1, '967550829768297', "Brand 1 must resolve to GAATHA Suite page")

        page_brand5 = self.adapter.resolve_page_id(brand_id=5)
        self.assertEqual(page_brand5, str(config.FB_PAGE_ID_PHOENIX), "Brand 5 must resolve to Phoenix page")

        # Custom explicit page override
        page_custom = self.adapter.resolve_page_id(target_identifier='custom_page_123', brand_id=99)
        self.assertEqual(page_custom, 'custom_page_123')

    def test_facebook_simulation_when_publishing_disabled(self):
        """When POSTPILOT_PUBLISHING_ENABLED=0, Facebook publishing returns simulated result."""
        with patch.object(config, 'is_publishing_enabled', return_value=False):
            res = self.adapter.publish({
                'message': 'Test Facebook announcement for GAATHA Suite',
                'brand_id': 1
            })

            self.assertTrue(res['success'])
            self.assertTrue(res['simulated'])
            self.assertIn('fb_post_sim_', res['external_post_id'])
            self.assertEqual(res['page_id'], '967550829768297')

    @patch('posting_utils.post_on_facebook')
    def test_facebook_real_publish_dispatch(self, mock_post_on_fb):
        """When publishing is enabled, FacebookAdapter delegates to posting_utils with resolved page ID."""
        mock_post_on_fb.return_value = {
            'success': True,
            'id': '967550829768297_987654321',
            'photo_id': 'photo_123'
        }

        with patch.object(config, 'is_publishing_enabled', return_value=True):
            with patch('facebook_api.get_access_token', return_value='fake_token_meta'):
                res = self.adapter.publish({
                    'message': 'Live post dispatch',
                    'image_filename': 'photo.jpg',
                    'brand_id': 1
                })

                self.assertTrue(res['success'])
                self.assertFalse(res['simulated'])
                self.assertEqual(res['external_post_id'], 'photo_123')
                self.assertEqual(res['page_id'], '967550829768297')
                mock_post_on_fb.assert_called_once_with(
                    message='Live post dispatch',
                    image_filename='photo.jpg',
                    page_id='967550829768297',
                    access_token='fake_token_meta'
                )

    def test_facebook_error_classification(self):
        """FacebookAdapter categorizes expired token, permissions, and transient errors."""
        # 1. Token Expired (code 190)
        c1 = self.adapter.classify_error("Error 190: Error validating access token: Session has expired")
        self.assertEqual(c1['error_code'], 'TOKEN_EXPIRED')
        self.assertFalse(c1['retryable'])

        # 2. Permission Denied (code 200)
        c2 = self.adapter.classify_error("OAuthException: (#200) Subject does not have permission")
        self.assertEqual(c2['error_code'], 'PERMISSION_DENIED')
        self.assertFalse(c2['retryable'])

        # 3. Invalid Parameter (code 100)
        c3 = self.adapter.classify_error("Invalid parameter: code 100")
        self.assertEqual(c3['error_code'], 'INVALID_PARAMETER')
        self.assertFalse(c3['retryable'])

        # 4. Transient error (code 2 or timeout)
        c4 = self.adapter.classify_error("Connection timeout error 500 transient")
        self.assertEqual(c4['error_code'], 'TRANSIENT_ERROR')
        self.assertTrue(c4['retryable'])


class TestInstagramPublishing(unittest.TestCase):
    """Verifies Instagram 3-phase container lifecycle, media validation, and limits."""

    def setUp(self):
        self.adapter = InstagramAdapter()

    def test_brand_ig_user_resolution(self):
        """InstagramAdapter resolves correct IG user ID for Brand 1 and Brand 5."""
        user_brand1 = self.adapter.resolve_ig_user_id(brand_id=1)
        self.assertEqual(user_brand1, '17841449080283492', "Brand 1 must resolve to @nexora_suite")

        user_brand5 = self.adapter.resolve_ig_user_id(brand_id=5)
        self.assertEqual(user_brand5, '17841471822022390', "Brand 5 must resolve to @phoenixbygaatha")

    def test_public_media_url_validation(self):
        """Instagram requires publicly routable HTTP/HTTPS media URLs."""
        # Valid URLs
        valid, _ = self.adapter.verify_public_media_url('https://cdn.example.com/photo.jpg')
        self.assertTrue(valid)
        valid, _ = self.adapter.verify_public_media_url('http://gaatha.com/media/banner.png')
        self.assertTrue(valid)

        # Invalid URLs
        invalid_cases = [
            '',
            'ftp://example.com/pic.jpg',
            'file:///D:/images/pic.jpg',
            'http://localhost:5000/media.jpg',
            'http://127.0.0.1:8000/photo.png',
            'http://192.168.1.50/pic.jpg',
            'http://10.0.0.1/pic.jpg'
        ]
        for url in invalid_cases:
            val, err = self.adapter.verify_public_media_url(url)
            self.assertFalse(val, f"URL '{url}' should be rejected as non-public")

    def test_hashtag_and_caption_validation(self):
        """Instagram enforces <= 30 hashtags and <= 2200 caption characters."""
        # Too many hashtags
        excessive_tags = ' '.join([f'#tag{i}' for i in range(35)])
        val, err = self.adapter.validate_content({'image_url': 'https://cdn.example.com/p.jpg', 'caption': excessive_tags})
        self.assertFalse(val)
        self.assertIn('30 hashtags', err)

        # Excessive caption
        long_caption = 'A' * 2205
        val, err = self.adapter.validate_content({'image_url': 'https://cdn.example.com/p.jpg', 'caption': long_caption})
        self.assertFalse(val)
        self.assertIn('2,200 character limit', err)

        # Missing media
        val, err = self.adapter.validate_content({'caption': 'Only text'})
        self.assertFalse(val)
        self.assertIn('requires an image or video attachment', err)

    def test_instagram_simulation_when_publishing_disabled(self):
        """When POSTPILOT_PUBLISHING_ENABLED=0, Instagram returns simulated container and media IDs."""
        with patch.object(config, 'is_publishing_enabled', return_value=False):
            res = self.adapter.publish({
                'caption': 'Sunset in Auckland #travel',
                'image_url': 'https://cdn.example.com/travel/sunset.jpg',
                'brand_id': 5
            })

            self.assertTrue(res['success'])
            self.assertTrue(res['simulated'])
            self.assertIn('ig_media_sim_', res['external_post_id'])
            self.assertIn('ig_container_sim_', res['container_id'])
            self.assertEqual(res['ig_user_id'], '17841471822022390')

    @patch('platform_adapters.instagram.requests.get')
    @patch('platform_adapters.instagram.requests.post')
    def test_instagram_3_phase_lifecycle_success(self, mock_post, mock_get):
        """Simulate successful 3-phase container: create -> poll FINISHED -> publish."""
        # 1. Container creation
        mock_create_resp = MagicMock()
        mock_create_resp.status_code = 200
        mock_create_resp.json.return_value = {'id': 'container_1784999'}

        # 3. Publish container
        mock_publish_resp = MagicMock()
        mock_publish_resp.status_code = 200
        mock_publish_resp.json.return_value = {'id': 'ig_media_published_555'}

        mock_post.side_effect = [mock_create_resp, mock_publish_resp]

        # 2. Container status poll
        mock_status_resp = MagicMock()
        mock_status_resp.status_code = 200
        mock_status_resp.json.return_value = {'status_code': 'FINISHED', 'id': 'container_1784999'}
        mock_get.return_value = mock_status_resp

        with patch.object(config, 'is_publishing_enabled', return_value=True):
            with patch('facebook_api.get_access_token', return_value='fake_fb_token'):
                res = self.adapter.publish({
                    'caption': 'Sunset in Auckland #travel #nz',
                    'image_url': 'https://cdn.example.com/travel/sunset.jpg',
                    'brand_id': 5
                })

                self.assertTrue(res['success'])
                self.assertEqual(res['external_post_id'], 'ig_media_published_555')
                self.assertEqual(res['container_id'], 'container_1784999')
                self.assertEqual(mock_post.call_count, 2)
                self.assertEqual(mock_get.call_count, 1)

    def test_instagram_error_classification(self):
        """InstagramAdapter classifies container and session errors."""
        c1 = self.adapter.classify_error("Error 190: Error validating access token")
        self.assertEqual(c1['error_code'], 'TOKEN_EXPIRED')

        c2 = self.adapter.classify_error("Container processing failed with status: ERROR")
        self.assertEqual(c2['error_code'], 'CONTAINER_FAILED')

        c3 = self.adapter.classify_error("Rate limit reached for instagram user: 32")
        self.assertEqual(c3['error_code'], 'RATE_LIMITED')
        self.assertTrue(c3['retryable'])


class TestLinkedInPublishing(unittest.TestCase):
    """Verifies LinkedIn REST Posts API 202401, dual-app selection, and 3-step image upload."""

    def setUp(self):
        self.adapter = LinkedInAdapter()

    def test_dual_app_selection(self):
        """LinkedInAdapter resolves correct company and app key."""
        app_aidni = self.adapter.resolve_app_key(organization_id='145240694')
        self.assertEqual(app_aidni, 'aidni_global')

        app_gaatha = self.adapter.resolve_app_key(organization_id='145250613')
        self.assertEqual(app_gaatha, 'gaatha_ventures')

    @patch('linkedin_api.create_organization_post')
    def test_linkedin_text_post_success(self, mock_create_post):
        """Simulate successful text post to LinkedIn Organization."""
        mock_create_post.return_value = {
            'success': True,
            'share_urn': 'urn:li:share:7123456789012345678',
            'id': 'urn:li:share:7123456789012345678',
            'app_key': 'aidni_global',
            'organization_id': '145240694',
            'simulated': False
        }

        res = self.adapter.publish({
            'text': 'Exciting developments at Aidni Global!',
            'app_name': 'aidni_global',
            'organization_id': '145240694'
        })

        self.assertTrue(res['success'])
        self.assertEqual(res['external_post_id'], 'urn:li:share:7123456789012345678')
        self.assertEqual(res['organization_id'], '145240694')

    @patch('linkedin_api.requests.put')
    @patch('linkedin_api.requests.post')
    def test_linkedin_3_step_image_upload(self, mock_post, mock_put):
        """Simulate LinkedIn 3-step image upload (initializeUpload -> PUT binary -> create post)."""
        # Step 1: initializeUpload
        mock_init_resp = MagicMock()
        mock_init_resp.status_code = 200
        mock_init_resp.json.return_value = {
            'value': {
                'uploadUrl': 'https://api.linkedin.com/mediaUpload/12345',
                'image': 'urn:li:image:D5405AQG_abcdef'
            }
        }

        # Step 3: create post
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.headers = {'x-restli-id': 'urn:li:share:7999888777'}
        mock_post_resp.json.return_value = {'id': 'urn:li:share:7999888777'}

        mock_post.side_effect = [mock_init_resp, mock_post_resp]

        # Step 2: PUT binary image bytes
        mock_put_resp = MagicMock()
        mock_put_resp.status_code = 201
        mock_put.return_value = mock_put_resp

        # Create a temporary image file to upload
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
            tf.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF' + b'\x00' * 50)
            tf_path = tf.name

        try:
            with patch.object(config, 'is_publishing_enabled', return_value=True):
                with patch('linkedin_api.get_active_token', return_value='fake_token_123'):
                    # Call initializeUpload
                    init_res = linkedin_api.initialize_image_upload('145250613', app_key='gaatha_ventures')
                    self.assertTrue(init_res['success'])
                    self.assertEqual(init_res['image_urn'], 'urn:li:image:D5405AQG_abcdef')

                    # Call upload binary
                    up_ok = linkedin_api.upload_image_file(init_res['upload_url'], tf_path)
                    self.assertTrue(up_ok)

                    # Call create post referencing image_urn
                    post_res = linkedin_api.create_organization_post(
                        organization_id='145250613',
                        text='Showcasing our new venture!',
                        app_key='gaatha_ventures',
                        image_urn=init_res['image_urn']
                    )

                    self.assertTrue(post_res['success'])
                    self.assertEqual(post_res['id'], 'urn:li:share:7999888777')
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_linkedin_error_classification(self):
        """LinkedInAdapter classifies CM API requirements and token expiry."""
        c1 = self.adapter.classify_error("HTTP 401 Unauthorized token expired")
        self.assertEqual(c1['error_code'], 'TOKEN_EXPIRED')

        c2 = self.adapter.classify_error("HTTP 403 Forbidden: w_organization_social scope missing")
        self.assertEqual(c2['error_code'], 'CM_API_REQUIRED')


class TestSocialAccountsManagement(unittest.TestCase):
    """Verifies social_accounts database operations and REST endpoints."""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name
        self.orig_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = self.db_path

        # Initialize clean test db
        database.init_db()

        # Configure Flask test client with test db
        flask_app.app.config['TESTING'] = True
        self.client = flask_app.app.test_client()

    def tearDown(self):
        if self.orig_db_url:
            os.environ['DATABASE_URL'] = self.orig_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_social_accounts_seeding_and_querying(self):
        """Default social accounts are seeded across Brand 1 and Brand 5."""
        accounts = database.get_social_accounts(organization_id=1)

        self.assertGreaterEqual(len(accounts), 6, "At least 6 default accounts should be seeded for org 1")
        platforms = {acc['platform'] for acc in accounts}
        self.assertIn('facebook', platforms)
        self.assertIn('instagram', platforms)
        self.assertIn('linkedin', platforms)
        self.assertIn('whatsapp', platforms)

        # Verify token security: no access_token in get_social_accounts output
        for acc in accounts:
            self.assertNotIn('access_token', acc)
            self.assertNotIn('access_token_encrypted', acc)

    def test_social_accounts_rest_api_get(self):
        """GET /api/accounts returns sanitized account list with zero secrets."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        resp = self.client.get('/api/accounts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))
        accounts = data.get('accounts', [])
        self.assertGreaterEqual(len(accounts), 1)

        # Strict security assertion
        for acc in accounts:
            self.assertNotIn('access_token', acc)
            self.assertNotIn('access_token_encrypted', acc)
            self.assertIn('status', acc)
            self.assertIn('token_status', acc)

    def test_social_accounts_verify_and_delete(self):
        """POST /api/accounts/verify/<id> and DELETE /api/accounts/<id> work within org."""
        accounts = database.get_social_accounts(organization_id=1)
        self.assertTrue(len(accounts) > 0)
        target_id = accounts[0]['id']

        csrf_val = 'test_csrf_token_acc'
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['organization_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['csrf_token'] = csrf_val

        headers = {'X-CSRFToken': csrf_val}

        # 1. Verify account
        v_resp = self.client.post(f'/api/accounts/verify/{target_id}', headers=headers)
        self.assertEqual(v_resp.status_code, 200)
        v_data = v_resp.get_json()
        self.assertTrue(v_data.get('success'))
        self.assertIn('verified_at', v_data)

        # 2. Delete account
        d_resp = self.client.delete(f'/api/accounts/{target_id}', headers=headers)
        self.assertEqual(d_resp.status_code, 200)
        d_data = d_resp.get_json()
        self.assertTrue(d_data.get('success'))

    def test_multi_tenant_isolation(self):
        """Org 2 cannot view or delete Org 1 accounts."""
        csrf_val = 'test_csrf_token_org2'
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['organization_id'] = 2  # Different Org!
            sess['username'] = 'org2_user'
            sess['role'] = 'editor'
            sess['csrf_token'] = csrf_val

        headers = {'X-CSRFToken': csrf_val}

        # Try deleting Org 1's account #2
        d_resp = self.client.delete('/api/accounts/2', headers=headers)
        self.assertEqual(d_resp.status_code, 404)
        d_data = d_resp.get_json()
        self.assertFalse(d_data.get('success'))


class TestExternalPostIdPersistence(unittest.TestCase):
    """Verifies external_post_id persistence in scheduled_posts."""

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name
        self.orig_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = self.db_path

        database.init_db()

    def tearDown(self):
        if self.orig_db_url:
            os.environ['DATABASE_URL'] = self.orig_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_external_post_id_column_and_completion(self):
        """complete_scheduled_post persists external_post_id and updates status to published."""
        # Create scheduled post
        post_res = database.create_scheduled_post(
            post_type='facebook',
            scheduled_for='2026-11-10T12:00:00',
            message='Automated post for GAATHA Suite',
            organization_id=1,
            brand_id=1
        )
        post_id = post_res['id']

        # Simulate worker acquiring lease claim on due post
        with database.get_db_connection() as conn:
            conn.execute(
                "UPDATE scheduled_posts SET status = 'publishing', locked_by = ?, locked_at = datetime('now') WHERE id = ?",
                ('test_worker_1', post_id)
            )
            conn.commit()

        # Complete post with external_post_id
        database.complete_scheduled_post(
            schedule_id=post_id,
            worker_id='test_worker_1',
            success=True,
            external_post_id='fb_967550829768297_99887766'
        )

        # Verify database record
        with database.get_db_connection() as conn:
            row = conn.execute("SELECT status, external_post_id FROM scheduled_posts WHERE id = ?", (post_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['status'], 'published')
            self.assertEqual(row['external_post_id'], 'fb_967550829768297_99887766')


if __name__ == '__main__':
    unittest.main()
