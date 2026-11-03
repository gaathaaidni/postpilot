"""
Integration and regression tests for PostPilot AI Marketing Studio APIs (test_campaign_api.py).
Tests campaign lifecycle, brand profile management, multi-platform AI copy generation,
draft version preservation, CSRF/auth protection, and multi-tenant isolation.
"""
import os
import tempfile
from pathlib import Path
import unittest
import json
import shutil

# Configure isolated test environment
os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-phase3-campaign-api-32bytes'
_tmp_dir = tempfile.TemporaryDirectory()
_db_file = Path(_tmp_dir.name) / 'campaign_api_test.db'
os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
os.environ['DATABASE_URL'] = f"sqlite:///{_db_file}"

import config
config.DATABASE_URL = f"sqlite:///{_db_file}"
config.LOCAL_MODE = False

import database
import app as postpilot_app

class TestCampaignAPI(unittest.TestCase):
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
        # Seed test organizations and brands
        with database.get_db_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (1, 'Org One', 'org-1')")
            conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (2, 'Org Two', 'org-2')")
            conn.execute("INSERT OR IGNORE INTO brands (id, organization_id, name, slug, description) VALUES (10, 1, 'Brand Alpha', 'alpha', 'Brand Alpha consultancy')")
            conn.execute("INSERT OR IGNORE INTO brands (id, organization_id, name, slug, description) VALUES (20, 2, 'Brand Beta', 'beta', 'Brand Beta products')")
            conn.commit()

        self.client = postpilot_app.app.test_client()

    def _login(self, user_id=1, username="admin1", role="admin", org_id=1):
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = username
            sess['role'] = role
            sess['organization_id'] = org_id
            sess['csrf_token'] = 'test-csrf-token-12345'
        return {'X-CSRFToken': 'test-csrf-token-12345', 'Content-Type': 'application/json'}

    def test_unauthenticated_requests_rejected(self):
        # GET /api/campaigns without session -> 401
        res = self.client.get('/api/campaigns')
        self.assertEqual(res.status_code, 401)

        # POST /api/campaigns without session -> 401
        res = self.client.post('/api/campaigns', json={'name': 'Test'})
        self.assertEqual(res.status_code, 401)

    def test_csrf_protection_on_campaign_endpoints(self):
        headers = self._login(org_id=1)
        # Attempt POST without CSRF header -> 403
        bad_headers = {'Content-Type': 'application/json'}
        res = self.client.post('/api/campaigns', json={'name': 'Test'}, headers=bad_headers)
        self.assertEqual(res.status_code, 403)

    def test_brand_profile_get_and_upsert(self):
        headers = self._login(org_id=1)

        # Initially profile is empty
        res = self.client.get('/api/brands/10/profile', headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['brand_id'], 10)

        # Upsert marketing profile
        profile_payload = {
            'positioning': 'Market leader in strategic visa planning',
            'voice_and_tone': 'Authoritative, calm, consultative',
            'messaging_guidelines': 'Always emphasize verified credentials',
            'approved_product_facts': '15+ years experience, 10k visas processed',
            'prohibited_claims': 'Never promise guaranteed approval',
            'preferred_ctas': 'Schedule your consultation now'
        }
        res = self.client.post('/api/brands/10/profile', json=profile_payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        saved = res.get_json()['profile']
        self.assertEqual(saved['positioning'], profile_payload['positioning'])
        self.assertEqual(saved['voice_and_tone'], profile_payload['voice_and_tone'])

        # Verify GET returns the updated profile
        res = self.client.get('/api/brands/10/profile', headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['profile']['approved_product_facts'], profile_payload['approved_product_facts'])

    def test_campaign_crud_lifecycle(self):
        headers = self._login(org_id=1)

        # Create Campaign
        create_payload = {
            'brand_id': 10,
            'name': 'Q3 Global Expansion',
            'objective': 'Brand Awareness',
            'brief': 'Highlight international branch launches and success stories.',
            'campaign_type': 'social',
            'target_audience': 'Entrepreneurs and investors',
            'target_markets': 'UK, Canada, Australia',
            'languages': 'en'
        }
        res = self.client.post('/api/campaigns', json=create_payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        camp = res.get_json()
        self.assertEqual(camp['name'], 'Q3 Global Expansion')
        camp_id = camp['id']

        # Get Single Campaign
        res = self.client.get(f'/api/campaigns/{camp_id}', headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['objective'], 'Brand Awareness')

        # List Campaigns
        res = self.client.get('/api/campaigns?brand_id=10', headers=headers)
        self.assertEqual(res.status_code, 200)
        camps = res.get_json()
        self.assertTrue(len(camps) >= 1)
        self.assertEqual(camps[0]['id'], camp_id)

        # Update Campaign
        update_payload = {'objective': 'High Intent Lead Gen', 'status': 'active'}
        res = self.client.put(f'/api/campaigns/{camp_id}', json=update_payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()
        self.assertEqual(updated['objective'], 'High Intent Lead Gen')
        self.assertEqual(updated['status'], 'active')

        # Delete Campaign
        res = self.client.delete(f'/api/campaigns/{camp_id}', headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'deleted')

        # Verify not found after deletion
        res = self.client.get(f'/api/campaigns/{camp_id}', headers=headers)
        self.assertEqual(res.status_code, 404)

    def test_campaign_content_generation_and_draft_versioning(self):
        headers = self._login(org_id=1)

        # 1. Create Brand Profile
        self.client.post('/api/brands/10/profile', json={
            'positioning': 'Elite tech staffing',
            'approved_product_facts': '98% retention rate over 3 years.',
            'prohibited_claims': 'Zero turnover guarantee.'
        }, headers=headers)

        # 2. Create Campaign
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10,
            'name': 'Tech Talent Blitz',
            'objective': 'Client Acquisition',
            'brief': 'Attract CTOs looking for senior AI engineers.',
            'target_audience': 'Tech Leaders and HR Directors'
        }, headers=headers)
        self.assertEqual(res.status_code, 201)
        camp_id = res.get_json()['id']

        # 3. Generate Content across all platforms using Mock provider
        gen_payload = {
            'provider': 'mock',
            'platforms': ['facebook', 'instagram', 'linkedin', 'x', 'whatsapp']
        }
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json=gen_payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['drafts']), 5)

        # Verify platforms are covered
        platforms_generated = {d['target_platform'] for d in data['drafts']}
        self.assertEqual(platforms_generated, {'facebook', 'instagram', 'linkedin', 'x', 'whatsapp'})

        # Verify WhatsApp format is conversational message draft
        whatsapp_draft = next(d for d in data['drafts'] if d['target_platform'] == 'whatsapp')
        self.assertIn('Update:', whatsapp_draft['headline'])
        self.assertIn('Hello', whatsapp_draft['caption'])

        # 4. Regenerate content (version preservation check)
        res2 = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'provider': 'mock',
            'platforms': ['linkedin']
        }, headers=headers)
        self.assertEqual(res2.status_code, 201)

        # Total drafts under this campaign should now be 6 (previous drafts NOT overwritten)
        res_drafts = self.client.get(f'/api/campaigns/{camp_id}/drafts', headers=headers)
        self.assertEqual(res_drafts.status_code, 200)
        all_drafts = res_drafts.get_json()
        self.assertEqual(len(all_drafts), 6)

        # 5. Edit a draft
        draft_to_edit = all_drafts[0]
        draft_id = draft_to_edit['id']
        edit_payload = {
            'headline': 'Customized Strategic Perspective',
            'caption': 'Refined manual copy for executive audience.',
            'hashtags': '#Custom #Staffing'
        }
        res_edit = self.client.put(f'/api/drafts/{draft_id}', json=edit_payload, headers=headers)
        self.assertEqual(res_edit.status_code, 200)
        edited_draft = res_edit.get_json()
        self.assertEqual(edited_draft['headline'], 'Customized Strategic Perspective')
        self.assertEqual(edited_draft['caption'], 'Refined manual copy for executive audience.')

        # 6. Delete a draft
        res_del = self.client.delete(f'/api/drafts/{draft_id}', headers=headers)
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.get_json()['status'], 'deleted')

        # Remaining drafts should be 5
        res_after = self.client.get(f'/api/campaigns/{camp_id}/drafts', headers=headers)
        self.assertEqual(len(res_after.get_json()), 5)

    def test_multi_tenant_isolation(self):
        # Org 1 creates a campaign
        headers_org1 = self._login(user_id=1, org_id=1)
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10,
            'name': 'Org1 Exclusive Campaign',
            'objective': 'Secret Launch',
            'brief': 'Top secret campaign details'
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 201)
        org1_camp_id = res.get_json()['id']

        # Org 2 user attempts to access Org 1 campaign -> 404
        headers_org2 = self._login(user_id=2, org_id=2)
        res = self.client.get(f'/api/campaigns/{org1_camp_id}', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # Org 2 user attempts to generate content for Org 1 campaign -> 404
        res = self.client.post(f'/api/campaigns/{org1_camp_id}/generate', json={'provider': 'mock'}, headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # Org 2 user attempts to create campaign for Org 1 brand (Brand #10) -> 404 / rejected
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10,
            'name': 'Unauthorized Org2 Attempt',
            'objective': 'Hack',
            'brief': 'Should fail'
        }, headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # Org 2 user attempts to access Org 1 brand profile -> 404
        res = self.client.get('/api/brands/10/profile', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

    def test_campaign_validation_errors(self):
        headers = self._login(org_id=1)

        # Missing brand_id
        res = self.client.post('/api/campaigns', json={'name': 'A', 'objective': 'B', 'brief': 'C'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('brand_id is required', res.get_json()['error'])

        # Empty name
        res = self.client.post('/api/campaigns', json={'brand_id': 10, 'name': '   ', 'objective': 'B', 'brief': 'C'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Campaign name is required', res.get_json()['error'])

        # Empty objective
        res = self.client.post('/api/campaigns', json={'brand_id': 10, 'name': 'A', 'objective': '', 'brief': 'C'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Campaign objective is required', res.get_json()['error'])

        # Empty brief
        res = self.client.post('/api/campaigns', json={'brand_id': 10, 'name': 'A', 'objective': 'B', 'brief': ' '}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Campaign brief is required', res.get_json()['error'])

    def test_campaign_generate_unsupported_provider(self):
        headers = self._login(org_id=1)
        # Create valid campaign
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Test', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers)
        camp_id = res.get_json()['id']

        # Request generation with unknown provider
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={'provider': 'non_existent_provider_xyz'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Unsupported AI provider', res.get_json()['error'])

    def test_draft_cross_tenant_isolation(self):
        headers_org1 = self._login(user_id=1, org_id=1)
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Camp1', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers_org1)
        camp_id = res.get_json()['id']

        # Generate draft in org 1
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={'provider': 'mock', 'platforms': ['linkedin']}, headers=headers_org1)
        draft = res.get_json()['drafts'][0]
        draft_id = draft['id']

        # Org 2 user attempts to fetch draft -> 404
        headers_org2 = self._login(user_id=2, org_id=2)
        res = self.client.get(f'/api/drafts/{draft_id}', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # Org 2 user attempts to update draft -> 404
        res = self.client.put(f'/api/drafts/{draft_id}', json={'headline': 'Hacked'}, headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # Org 2 user attempts to delete draft -> 404
        res = self.client.delete(f'/api/drafts/{draft_id}', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

    def test_campaign_status_validation_and_lifecycle_transitions(self):
        headers = self._login(org_id=1)

        # 1. Invalid initial status rejected on creation
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Camp Invalid', 'objective': 'Obj', 'brief': 'Brief',
            'status': 'invalid_status_xyz'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid initial campaign status', res.get_json()['error'])

        # 2. Valid creation with default status 'draft'
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Camp Valid', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers)
        self.assertEqual(res.status_code, 201)
        camp_id = res.get_json()['id']
        self.assertEqual(res.get_json()['status'], 'draft')

        # 3. Invalid status string on update rejected
        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'bogus_status'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid campaign status', res.get_json()['error'])

        # 4. Illegal transition rejected (e.g. draft directly to completed)
        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'completed'}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Illegal campaign lifecycle transition', res.get_json()['error'])

        # 5. Legal sequential transitions
        # draft -> active
        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'active'}, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'active')

        # active -> paused
        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'paused'}, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'paused')

        # paused -> completed
        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'completed'}, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'completed')

    def test_draft_status_validation_and_privileged_transitions(self):
        headers_admin = self._login(user_id=1, role='admin', org_id=1)

        # Create campaign and generate a draft
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Draft Lifecycle Camp', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers_admin)
        camp_id = res.get_json()['id']

        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={'provider': 'mock', 'platforms': ['facebook']}, headers=headers_admin)
        draft = res.get_json()['drafts'][0]
        draft_id = draft['id']
        self.assertEqual(draft['status'], 'draft')

        # 1. Arbitrary status string rejected on edit
        res = self.client.put(f'/api/drafts/{draft_id}', json={'status': 'random_nonsense'}, headers=headers_admin)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid draft status', res.get_json()['error'])

        # 2. Direct attempt to mark as 'approved' via PUT /api/drafts/<id> is DENIED
        res = self.client.put(f'/api/drafts/{draft_id}', json={'status': 'approved'}, headers=headers_admin)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Cannot directly mark content draft as', res.get_json()['error'])

        # 3. Direct attempt to mark as 'scheduled' via edit is DENIED
        res = self.client.put(f'/api/drafts/{draft_id}', json={'status': 'scheduled'}, headers=headers_admin)
        self.assertEqual(res.status_code, 400)

        # 4. Direct attempt to mark as 'published' via transition is DENIED
        res = self.client.post(f'/api/drafts/{draft_id}/transition', json={'status': 'published'}, headers=headers_admin)
        self.assertEqual(res.status_code, 400)
        self.assertIn('publishing worker', res.get_json()['error'])

        # 5. Workflow: Transition from draft to pending_approval
        res = self.client.post(f'/api/drafts/{draft_id}/transition', json={'status': 'pending_approval'}, headers=headers_admin)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['draft']['status'], 'pending_approval')

        # 6. Workflow: Non-admin user cannot approve
        headers_user = self._login(user_id=99, role='contributor', org_id=1)
        res = self.client.post(f'/api/drafts/{draft_id}/approve', headers=headers_user)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Unauthorized', res.get_json()['error'])

        # 7. Workflow: Admin approves
        headers_admin = self._login(user_id=1, role='admin', org_id=1)
        res = self.client.post(f'/api/drafts/{draft_id}/approve', headers=headers_admin)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['draft']['status'], 'approved')

        # 8. Rejection workflow on a new draft
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={'provider': 'mock', 'platforms': ['linkedin']}, headers=headers_admin)
        draft2_id = res.get_json()['drafts'][0]['id']
        self.client.post(f'/api/drafts/{draft2_id}/transition', json={'status': 'pending_approval'}, headers=headers_admin)

        # Rejection without reason is rejected
        res = self.client.post(f'/api/drafts/{draft2_id}/reject', json={}, headers=headers_admin)
        self.assertEqual(res.status_code, 400)
        self.assertIn('rejection reason is required', res.get_json()['error'])

        # Rejection with reason succeeds
        res = self.client.post(f'/api/drafts/{draft2_id}/reject', json={'reason': 'Missing price disclaimer'}, headers=headers_admin)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['draft']['status'], 'rejected')

if __name__ == '__main__':
    unittest.main()
