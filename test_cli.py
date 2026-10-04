"""
test_cli.py - Validation for PostPilot Unified CLI (postpilot_cli.py)
Verifies:
1. Argument parsing and command dispatch
2. Safe token masking (never printing complete credentials)
3. Graceful missing-token handling across all commands
4. Mocked Graph API token verification and permission inspection
5. Mocked Graph API page and connected asset discovery
6. Non-destructive health check execution
7. Backward compatibility wrappers (verify_token, fetch_full_info, fetch_fb_info)
"""
import os
import sys
import io
import unittest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import postpilot_cli
import verify_token
import fetch_full_info
import fetch_fb_info

class TestPostPilotCLI(unittest.TestCase):

    def test_token_masking(self):
        """Verifies token masking logic prevents credential leaks."""
        self.assertEqual(postpilot_cli.mask_token(None), "[NOT SET]")
        self.assertEqual(postpilot_cli.mask_token(""), "[NOT SET]")
        self.assertEqual(postpilot_cli.mask_token("12345"), "****")
        
        long_tok = "EAAGm0PX4ZCpsBA" + "X" * 100 + "9988"
        masked = postpilot_cli.mask_token(long_tok)
        self.assertTrue(masked.startswith("EAAG...9988"))
        self.assertNotIn("X" * 20, masked)
        self.assertIn("length 119", masked)

    @patch('postpilot_cli.get_auth_token')
    def test_missing_token_safe_handling(self, mock_tok):
        """Commands must handle unconfigured tokens safely without exceptions."""
        mock_tok.return_value = None

        # 1. verify-token
        ret = postpilot_cli.cmd_verify_token()
        self.assertEqual(ret, 0)

        # 2. list-pages
        ret = postpilot_cli.cmd_list_pages()
        self.assertEqual(ret, 0)

        # 3. inspect-account
        ret = postpilot_cli.cmd_inspect_account()
        self.assertEqual(ret, 0)

    def test_health_command(self):
        """Health command runs non-destructively and returns status code 0."""
        ret = postpilot_cli.cmd_health()
        self.assertEqual(ret, 0)

    @patch('postpilot_cli.get_auth_token')
    @patch('requests.get')
    def test_verify_token_mock_valid(self, mock_get, mock_tok):
        """Validates token verification with mocked valid Graph API debug response."""
        mock_tok.return_value = "MOCK_TOKEN_123456789"

        # Mock debug_token and /me responses
        debug_resp = MagicMock()
        debug_resp.json.return_value = {
            'data': {
                'is_valid': True,
                'app_id': '999888777',
                'user_id': '111222333',
                'expires_at': 0,
                'scopes': ['pages_show_list', 'pages_read_engagement', 'pages_manage_posts']
            }
        }
        
        me_resp = MagicMock()
        me_resp.headers = {'x-app-usage': '{"call_count": 5, "total_cputime": 2, "total_time": 1}'}

        mock_get.side_effect = [debug_resp, me_resp]

        ret = postpilot_cli.cmd_verify_token()
        self.assertEqual(ret, 0)

    @patch('postpilot_cli.get_auth_token')
    @patch('requests.get')
    def test_list_pages_mock(self, mock_get, mock_tok):
        """Validates page asset discovery with mocked accounts response."""
        mock_tok.return_value = "MOCK_TOKEN_123456789"

        me_resp = MagicMock()
        me_resp.json.return_value = {'name': 'Mock Admin', 'id': '101'}

        accounts_resp = MagicMock()
        accounts_resp.json.return_value = {
            'data': [
                {
                    'name': 'Nexora Suite',
                    'id': '967550829768297',
                    'instagram_business_account': {'id': '17841449080283492', 'username': 'nexora_suite'},
                    'whatsapp_number': '+1234567890'
                }
            ]
        }

        mock_get.side_effect = [me_resp, accounts_resp]

        ret = postpilot_cli.cmd_list_pages(update_env=False)
        self.assertEqual(ret, 0)

    def test_cli_backward_compatibility_wrappers(self):
        """Verifies verify_token, fetch_full_info, and fetch_fb_info wrappers execute safely."""
        with patch('postpilot_cli.get_auth_token', return_value=None):
            self.assertEqual(verify_token.main(), 0)
            self.assertEqual(fetch_full_info.main(), 0)
            self.assertEqual(fetch_fb_info.main(), 0)

if __name__ == "__main__":
    unittest.main()
