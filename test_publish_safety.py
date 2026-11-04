"""
test_publish_safety.py - PostPilot External Publishing Safety Test Suite

Validates that external publishing to Meta (Facebook & Instagram) is strictly
guarded and disabled by default:
1. Publishing disabled by default (POSTPILOT_PUBLISHING_ENABLED=0)
2. Direct Facebook publishing guarded
3. Direct Instagram publishing guarded
4. Facebook background posting loop guarded (queued posts not consumed)
5. Instagram background sync loop guarded
6. Scheduled post claiming guarded (posts not claimed or executed)
7. Meta publishing POST endpoints guarded (non-publishing ops preserved)
8. Publishing enabled only when explicitly set to '1'
"""
import os
import sys
import threading
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import facebook_api
import insta
import posting_utils
import worker
import database


class TestPublishSafety(unittest.TestCase):

    def setUp(self):
        # Ensure clean environment for each test
        self.original_env = os.environ.get('POSTPILOT_PUBLISHING_ENABLED')

    def tearDown(self):
        if self.original_env is not None:
            os.environ['POSTPILOT_PUBLISHING_ENABLED'] = self.original_env
        else:
            os.environ.pop('POSTPILOT_PUBLISHING_ENABLED', None)

    def test_01_publishing_disabled_by_default(self):
        """Verifies publishing is strictly disabled by default when unset or set to 0."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': ''}, clear=False):
            os.environ.pop('POSTPILOT_PUBLISHING_ENABLED', None)
            os.environ.pop('PUBLISHING_ENABLED', None)
            self.assertFalse(config.is_publishing_enabled(), "Must be disabled when unset")

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled(), "Must be disabled when '0'")

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': 'false'}):
            self.assertFalse(config.is_publishing_enabled(), "Must be disabled when 'false'")

    @patch('requests.request')
    def test_02_facebook_direct_publishing_guarded(self, mock_request):
        """Verifies direct Facebook publishing is blocked without network calls when disabled."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())
            result = posting_utils.post_on_facebook(
                message="Test message",
                image_filename="",
                page_id="123456789",
                access_token="TEST_TOKEN"
            )
            self.assertFalse(result, "Direct Facebook publishing must return False when disabled")
            mock_request.assert_not_called()

    @patch('requests.request')
    def test_03_instagram_direct_publishing_guarded(self, mock_request):
        """Verifies direct Instagram publishing is blocked without network calls when disabled."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())
            result = insta.post_to_instagram(
                image_url="https://example.com/image.jpg",
                caption="Test caption",
                ig_user_id="987654321",
                access_token="TEST_TOKEN"
            )
            self.assertFalse(result, "Direct Instagram publishing must return False when disabled")
            mock_request.assert_not_called()

    @patch('posting_utils.post_on_facebook')
    @patch('posting_utils.load_posts')
    def test_04_facebook_background_posting_guarded(self, mock_load, mock_post):
        """Verifies background posting loop pauses without consuming queued posts when disabled."""
        stop_event = threading.Event()
        status_updates = []

        def mock_status(task_name, is_running, message, current_post):
            status_updates.append((is_running, message))
            # Stop immediately after status update to exit loop
            stop_event.set()

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())
            posting_utils.run_posting_loop(
                stop_event=stop_event,
                status_callback=mock_status,
                get_interval_func=lambda: 1,
                callback_key="test_ch",
                post_type="tour",
                page_id="12345",
                access_token="TEST_TOKEN"
            )

        # Queued posts must never be loaded or posted
        mock_load.assert_not_called()
        mock_post.assert_not_called()
        self.assertTrue(any("Paused (Publishing disabled)" in s[1] for s in status_updates))

    @patch('insta.post_to_instagram')
    def test_05_instagram_background_sync_guarded(self, mock_insta_post):
        """Verifies Instagram background sync loop pauses without attempting sync when disabled."""
        sync = insta.InstaSync(page_id="12345", ig_user_id="67890", name="test_insta")
        status_updates = []

        def mock_status(task_name, is_running, message, current_post):
            status_updates.append((is_running, message))
            sync.stop()

        insta.set_status_callback(mock_status)

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())
            sync.run()

        mock_insta_post.assert_not_called()
        self.assertTrue(any("Paused (Publishing disabled)" in s[1] for s in status_updates))

    @patch('database.claim_due_scheduled_posts')
    def test_06_scheduled_post_claiming_guarded(self, mock_claim):
        """Verifies scheduled posts are never claimed or executed while publishing is disabled."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())
            result = worker.process_due_scheduled_posts("worker-test-1")
            self.assertEqual(result, [], "Must return empty list without claiming posts")
            mock_claim.assert_not_called()

    @patch('requests.request')
    def test_07_meta_publishing_endpoints_guarded(self, mock_request):
        """Verifies Meta POST publishing endpoints are intercepted; non-publishing ops preserved."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '0'}):
            self.assertFalse(config.is_publishing_enabled())

            # 1. Publishing POST endpoints must be intercepted without calling requests.request
            endpoints = [
                f"{facebook_api.BASE_URL}/12345/feed",
                f"{facebook_api.BASE_URL}/12345/photos",
                f"{facebook_api.BASE_URL}/12345/videos",
                f"{facebook_api.BASE_URL}/12345/media",
                f"{facebook_api.BASE_URL}/12345/media_publish"
            ]
            for ep in endpoints:
                res = facebook_api._request_with_retry("POST", ep, data={'message': 'test'})
                self.assertIsInstance(res, dict)
                self.assertTrue(res.get('simulated'), f"Endpoint {ep} should return simulated response")
            mock_request.assert_not_called()

            # 2. Non-publishing operations (e.g. GET) are not intercepted by the publishing guard
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'id': '12345', 'name': 'Test Page'}
            mock_request.return_value = mock_response

            get_res = facebook_api._request_with_retry("GET", f"{facebook_api.BASE_URL}/me")
            self.assertEqual(get_res.get('name'), 'Test Page')
            self.assertEqual(mock_request.call_count, 1)

    def test_08_publishing_enabled_when_explicit(self):
        """Verifies publishing is permitted when POSTPILOT_PUBLISHING_ENABLED is explicitly 1."""
        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': '1'}):
            self.assertTrue(config.is_publishing_enabled(), "Must be True when '1'")

        with patch.dict(os.environ, {'POSTPILOT_PUBLISHING_ENABLED': 'true'}):
            self.assertTrue(config.is_publishing_enabled(), "Must be True when 'true'")
