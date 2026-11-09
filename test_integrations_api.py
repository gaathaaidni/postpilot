import unittest
import json
from unittest.mock import patch, MagicMock
from app import app
import database

class TestIntegrationsAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        database.init_db()

    def tearDown(self):
        self.app_context.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['organization_id'] = 1
            sess['csrf_token'] = 'test_csrf_token'

    def test_01_get_integrations_status(self):
        """Tests that GET /api/integrations/status returns comprehensive status structure."""
        self._login()
        res = self.client.get('/api/integrations/status')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'))
        self.assertIn('meta', data)
        self.assertIn('linkedin', data)
        self.assertIn('whatsapp', data)
        self.assertIn('apps', data['linkedin'])
        self.assertEqual(len(data['linkedin']['apps']), 2)

    def test_02_map_and_unmap_social_property(self):
        """Tests mapping an account to Brand 1 and unmapping."""
        self._login()
        csrf_headers = {'X-CSRFToken': 'test_csrf_token'}

        # Map Gaatha AI FB page to Brand 6
        map_payload = {
            'platform': 'facebook',
            'account_identifier': '1028368893692590',
            'account_name': 'Gaatha AI',
            'brand_id': 6,
            'permissions_scope': 'pages_manage_posts,pages_read_engagement'
        }
        res = self.client.post('/api/integrations/map', json=map_payload, headers=csrf_headers)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('brand_name'), 'GAATHA AI')

        # Verify it shows in database
        acct = database.get_social_account_for_brand(1, 6, 'facebook')
        self.assertIsNotNone(acct)
        self.assertEqual(acct['account_identifier'], '1028368893692590')
        account_id = acct['id']

        # Unmap
        del_res = self.client.delete(f'/api/integrations/map/{account_id}', headers=csrf_headers)
        self.assertEqual(del_res.status_code, 200)
        acct_after = database.get_social_account_for_brand(1, 6, 'facebook')
        self.assertIsNone(acct_after)

    def test_03_brand_isolation_on_mapping(self):
        """Ensures an organization cannot map accounts to brands outside its organization."""
        self._login()
        csrf_headers = {'X-CSRFToken': 'test_csrf_token'}

        # Brand 7 belongs to Org 2, not Org 1
        map_payload = {
            'platform': 'facebook',
            'account_identifier': '999999999',
            'account_name': 'Hacked Brand',
            'brand_id': 7
        }
        res = self.client.post('/api/integrations/map', json=map_payload, headers=csrf_headers)
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn('not found', data.get('error', '').lower())

if __name__ == '__main__':
    unittest.main()
