"""
Integration and regression tests for PostPilot AI Marketing Studio APIs (test_campaign_api.py).
Tests campaign lifecycle, brand profile management, multi-platform AI copy generation,
draft version preservation, CSRF/auth protection, and multi-tenant isolation.
"""
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
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
import ai_service
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

    def test_draft_immutable_revision_history_and_optimistic_locking(self):
        headers_org1 = self._login(user_id=1, role='admin', org_id=1)

        # 1. Create campaign and draft
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Revision Test Camp', 'objective': 'Test revisions', 'brief': 'Brief'
        }, headers=headers_org1)
        camp_id = res.get_json()['id']

        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'provider': 'mock', 'platforms': ['facebook']
        }, headers=headers_org1)
        draft = res.get_json()['drafts'][0]
        draft_id = draft['id']
        self.assertEqual(draft['current_revision'], 1)

        # 2. Check initial revision in /revisions
        res = self.client.get(f'/api/drafts/{draft_id}/revisions', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['count'], 1)
        rev1 = data['revisions'][0]
        self.assertEqual(rev1['revision_number'], 1)
        self.assertEqual(rev1['change_source'], 'ai_generated')
        self.assertEqual(rev1['caption'], draft['caption'])
        self.assertEqual(rev1['ai_provider'], 'mock')

        # 3. Update draft caption -> creates revision 2
        res = self.client.put(f'/api/drafts/{draft_id}', json={
            'caption': 'Revised caption for unit testing',
            'expected_revision': 1
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        updated1 = res.get_json()
        self.assertEqual(updated1['current_revision'], 2)
        self.assertEqual(updated1['caption'], 'Revised caption for unit testing')

        # 4. Optimistic locking: Attempt edit with stale expected_revision 1 -> HTTP 409 CONCURRENT_EDIT_CONFLICT
        res = self.client.put(f'/api/drafts/{draft_id}', json={
            'caption': 'Conflict edit attempt',
            'expected_revision': 1
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()['code'], 'CONCURRENT_EDIT_CONFLICT')

        # 5. Successful edit with expected_revision 2 -> creates revision 3
        res = self.client.put(f'/api/drafts/{draft_id}', json={
            'caption': 'Third version of caption',
            'expected_revision': 2
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['current_revision'], 3)

        # 6. Check full revision history
        res = self.client.get(f'/api/drafts/{draft_id}/revisions', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        revs = res.get_json()['revisions']
        self.assertEqual(len(revs), 3)
        self.assertEqual(revs[0]['revision_number'], 1)
        self.assertEqual(revs[1]['revision_number'], 2)
        self.assertEqual(revs[2]['revision_number'], 3)

        # 7. Fetch single revision by number
        res = self.client.get(f'/api/drafts/{draft_id}/revisions/1', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['caption'], draft['caption'])

        # 8. Restore revision 1 -> appends as revision 4 with source 'restored_revision'
        res = self.client.post(f'/api/drafts/{draft_id}/revisions/1/restore', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        restore_data = res.get_json()
        self.assertEqual(restore_data['current_revision'], 4)
        self.assertEqual(restore_data['draft']['caption'], draft['caption'])

        # Prior revisions are intact!
        res = self.client.get(f'/api/drafts/{draft_id}/revisions', headers=headers_org1)
        self.assertEqual(res.get_json()['count'], 4)
        self.assertEqual(res.get_json()['revisions'][3]['change_source'], 'restored_revision')

        # 9. AI regeneration creates revision 5
        res = self.client.post(f'/api/drafts/{draft_id}/regenerate', json={
            'provider': 'mock',
            'expected_revision': 4
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        regen_draft = res.get_json()['draft']
        self.assertEqual(regen_draft['current_revision'], 5)

        # Check rev5 metadata
        res = self.client.get(f'/api/drafts/{draft_id}/revisions/5', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        rev5 = res.get_json()
        self.assertEqual(rev5['revision_number'], 5)
        self.assertEqual(rev5['change_source'], 'regenerated')
        self.assertEqual(rev5['ai_provider'], 'mock')

        # 10. Tenant isolation: Org 2 cannot view or restore Org 1's draft revisions
        headers_org2 = self._login(user_id=2, role='admin', org_id=2)
        res = self.client.get(f'/api/drafts/{draft_id}/revisions', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        res = self.client.post(f'/api/drafts/{draft_id}/revisions/1/restore', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

    def test_ai_generation_cost_and_input_controls(self):
        headers = self._login(user_id=1, role='admin', org_id=1)

        # Create campaign
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Limits Test Camp', 'objective': 'Test cost controls', 'brief': 'Brief text'
        }, headers=headers)
        camp_id = res.get_json()['id']

        # 1. Empty platform list rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={'platforms': []}, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('non-empty list', res.get_json()['error'])

        # 2. Exceeding max platforms (>5) rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook', 'instagram', 'linkedin', 'x', 'whatsapp', 'facebook']
        }, headers=headers)
        self.assertEqual(res.status_code, 400)

        # 3. Duplicate platform in list rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook', 'facebook']
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Duplicate platform', res.get_json()['error'])

        # 4. Malformed / unsupported platform rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['myspace_unsupported']
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Unsupported platform', res.get_json()['error'])

        # 5. Invalid language format rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook'],
            'language': 'very_long_invalid_language_name_exceeding_limits'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid language format', res.get_json()['error'])

        # 6. Invalid content format rejected with 400
        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook'],
            'content_format': 'invalid_format_xyz'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Invalid content format', res.get_json()['error'])

        # 7. Idempotency deduplication check:
        # First call succeeds
        res1 = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook'],
            'provider': 'mock',
            'idempotency_key': 'test-idem-key-12345'
        }, headers=headers)
        self.assertEqual(res1.status_code, 201)
        draft1_id = res1.get_json()['drafts'][0]['id']

        # Rapid second call with same idempotency key returns cached response
        res2 = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook'],
            'provider': 'mock',
            'idempotency_key': 'test-idem-key-12345'
        }, headers=headers)
        self.assertIn(res2.status_code, (200, 201))
        self.assertEqual(res2.get_json()['drafts'][0]['id'], draft1_id)

        # 8. Partial success preservation
        # Mock one platform to fail while another succeeds
        with patch('ai_service.generate_campaign_content') as mock_gen:
            def side_effect(provider, brand_info, campaign_info, target_platform, **kwargs):
                if target_platform == 'instagram':
                    raise ai_service.AIRateLimitError("Instagram rate limit", provider="mock", status_code=429)
                return ai_service.GenerationResult(
                    headline="FB Headline", caption="FB Caption", target_platform="facebook",
                    ai_provider="mock", ai_model="mock-v1"
                )
            mock_gen.side_effect = side_effect

            res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
                'platforms': ['facebook', 'instagram'],
                'provider': 'mock',
                'idempotency_key': 'partial-success-test'
            }, headers=headers)
            self.assertIn(res.status_code, (201, 207))
            data = res.get_json()
            self.assertEqual(data['status'], 'partial_success')
            self.assertEqual(len(data['drafts']), 1)
            self.assertEqual(data['drafts'][0]['target_platform'], 'facebook')
            self.assertEqual(len(data['errors']), 1)
            self.assertEqual(data['errors'][0]['platform'], 'instagram')

        # 9. Organization hourly limit enforcement
        with patch('config.AI_ORG_HOURLY_GENERATION_LIMIT', 2):
            with patch('database.get_organization_ai_generation_count', return_value=5):
                res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
                    'platforms': ['linkedin'],
                    'provider': 'mock'
                }, headers=headers)
                self.assertEqual(res.status_code, 429)
                self.assertIn('hourly AI generation limit', res.get_json()['error'])

    def test_campaign_date_and_budget_integrity(self):
        headers = self._login(user_id=1, role='admin', org_id=1)

        # 1. Invalid date range on creation (end_date < start_date)
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Bad Dates Camp', 'objective': 'Obj', 'brief': 'Brief',
            'start_date': '2026-12-31', 'end_date': '2026-01-01'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be earlier than start_date', res.get_json()['error'])

        # 2. Negative budget on creation
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Negative Budget Camp', 'objective': 'Obj', 'brief': 'Brief',
            'budget': '-500'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be negative', res.get_json()['error'])

        # 3. Valid creation
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Valid Integrity Camp', 'objective': 'Obj', 'brief': 'Brief',
            'start_date': '2026-06-01', 'end_date': '2026-06-30', 'budget': '$2,500.00'
        }, headers=headers)
        self.assertEqual(res.status_code, 201)
        camp_id = res.get_json()['id']

        # 4. Updating with invalid date range
        res = self.client.put(f'/api/campaigns/{camp_id}', json={
            'end_date': '2026-05-01'  # earlier than existing start_date 2026-06-01
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be earlier than start_date', res.get_json()['error'])

        # 5. Updating with negative budget
        res = self.client.put(f'/api/campaigns/{camp_id}', json={
            'budget': '$-100'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn('cannot be negative', res.get_json()['error'])

    def test_mass_assignment_and_protected_field_tampering(self):
        headers = self._login(user_id=1, role='admin', org_id=1)

        # Create campaign and draft
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Security Test Camp', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers)
        camp_id = res.get_json()['id']

        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook'], 'provider': 'mock'
        }, headers=headers)
        draft_id = res.get_json()['drafts'][0]['id']

        # 1. Attempt to tamper with campaign organization_id via PUT
        res = self.client.put(f'/api/campaigns/{camp_id}', json={
            'organization_id': 999,
            'name': 'Tampered Name'
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['code'], 'PROTECTED_FIELD_TAMPERING')

        # 2. Attempt to tamper with campaign created_by
        res = self.client.put(f'/api/campaigns/{camp_id}', json={
            'created_by': 999
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['code'], 'PROTECTED_FIELD_TAMPERING')

        # 3. Attempt to tamper with draft organization_id or brand_id via PUT
        res = self.client.put(f'/api/drafts/{draft_id}', json={
            'organization_id': 999
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['code'], 'PROTECTED_FIELD_TAMPERING')

        res = self.client.put(f'/api/drafts/{draft_id}', json={
            'brand_id': 999
        }, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()['code'], 'PROTECTED_FIELD_TAMPERING')

    def test_campaign_cascade_delete_and_pagination(self):
        headers = self._login(user_id=1, role='admin', org_id=1)

        # Create campaign and drafts
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Cascade Camp', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers)
        camp_id = res.get_json()['id']

        res = self.client.post(f'/api/campaigns/{camp_id}/generate', json={
            'platforms': ['facebook', 'linkedin'], 'provider': 'mock'
        }, headers=headers)
        drafts = res.get_json()['drafts']
        draft_ids = [d['id'] for d in drafts]

        # Verify drafts exist
        res = self.client.get(f'/api/campaigns/{camp_id}/drafts', headers=headers)
        self.assertEqual(len(res.get_json()), 2)

        # Delete campaign
        res = self.client.delete(f'/api/campaigns/{camp_id}', headers=headers)
        self.assertEqual(res.status_code, 200)

        # Drafts are cascaded and cannot be found
        for did in draft_ids:
            res = self.client.get(f'/api/drafts/{did}', headers=headers)
            self.assertEqual(res.status_code, 404)
            res = self.client.get(f'/api/drafts/{did}/revisions', headers=headers)
            self.assertEqual(res.status_code, 404)

    def test_archival_lifecycle_and_legacy_backfill(self):
        headers_admin = self._login(user_id=1, role='admin', org_id=1)
        headers_user = self._login(user_id=88, role='contributor', org_id=1)

        # 1. Campaign transition to archived
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Archival Camp', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers_admin)
        camp_id = res.get_json()['id']

        res = self.client.put(f'/api/campaigns/{camp_id}', json={'status': 'archived'}, headers=headers_admin)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'archived')

        # 2. Draft transition to archived
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10, 'name': 'Archival Draft Camp', 'objective': 'Obj', 'brief': 'Brief'
        }, headers=headers_admin)
        camp2_id = res.get_json()['id']

        res = self.client.post(f'/api/campaigns/{camp2_id}/generate', json={
            'platforms': ['facebook'], 'provider': 'mock'
        }, headers=headers_admin)
        draft_id = res.get_json()['drafts'][0]['id']

        # Transition draft to archived
        res = self.client.post(f'/api/drafts/{draft_id}/transition', json={'status': 'archived'}, headers=headers_admin)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['draft']['status'], 'archived')

        # 3. Non-manager/contributor cannot reject draft
        res = self.client.post(f'/api/campaigns/{camp2_id}/generate', json={
            'platforms': ['instagram'], 'provider': 'mock'
        }, headers=headers_admin)
        draft2_id = res.get_json()['drafts'][0]['id']
        self.client.post(f'/api/drafts/{draft2_id}/transition', json={'status': 'pending_approval'}, headers=headers_admin)

        res = self.client.post(f'/api/drafts/{draft2_id}/reject', json={'reason': 'User rejected'}, headers=headers_user)
        self.assertEqual(res.status_code, 400)
        self.assertIn('Unauthorized', res.get_json()['error'])

        # 4. Legacy database backfill test
        # Directly insert a draft row without any revision record
        with database.get_db_connection() as conn:
            cur = conn.execute(
                "INSERT INTO content_drafts (organization_id, brand_id, campaign_id, target_platform, "
                "caption, status, current_revision, created_by) "
                "VALUES (1, 10, ?, 'whatsapp', 'Legacy draft with no revision record', 'draft', 1, 1)",
                (camp2_id,)
            )
            legacy_id = cur.lastrowid
            conn.commit()

        # Confirm 0 revisions exist for legacy_id
        res = self.client.get(f'/api/drafts/{legacy_id}/revisions', headers=headers_admin)
        self.assertEqual(res.get_json()['count'], 0)

        # Run database.init_db() to trigger backfill
        database.init_db()

        # Confirm revision 1 was backfilled non-destructively
        res = self.client.get(f'/api/drafts/{legacy_id}/revisions', headers=headers_admin)
        self.assertEqual(res.get_json()['count'], 1)
        rev = res.get_json()['revisions'][0]
        self.assertEqual(rev['revision_number'], 1)
        self.assertEqual(rev['caption'], 'Legacy draft with no revision record')
        self.assertEqual(rev['change_source'], 'manual_creation')

    def test_campaign_strategy_lifecycle_and_tenant_isolation(self):
        headers_org1 = self._login(user_id=1, role='admin', org_id=1)

        # 1. Create a campaign in Org 1
        res = self.client.post('/api/campaigns', json={
            'brand_id': 10,
            'name': 'Strategy Test Campaign',
            'objective': 'Expand market share by 30%',
            'brief': 'Launch high-impact brand campaign for enterprise solutions.'
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 201)
        camp_id = res.get_json()['id']

        # 2. GET strategy before generation -> 404
        res = self.client.get(f'/api/campaigns/{camp_id}/strategy', headers=headers_org1)
        self.assertEqual(res.status_code, 404)

        # 3. Generate strategy -> 200
        res = self.client.post(f'/api/campaigns/{camp_id}/strategy', json={
            'provider': 'mock'
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        strat = data['strategy']
        self.assertEqual(strat['campaign_id'], camp_id)
        self.assertEqual(strat['organization_id'], 1)

        # Verify all 14 core sections exist
        required_sections = [
            'positioning', 'primary_objective', 'target_segments', 'pain_points',
            'value_proposition', 'core_message', 'supporting_messages', 'content_themes',
            'recommended_channels', 'calls_to_action', 'suggested_phases',
            'posting_frequency', 'success_metrics', 'risks_and_verification'
        ]
        for sec in required_sections:
            self.assertIn(sec, strat)
            self.assertTrue(len(strat[sec]) > 0)

        # 4. GET strategy returns the generated strategy
        res = self.client.get(f'/api/campaigns/{camp_id}/strategy', headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['core_message'], strat['core_message'])

        # 5. PUT strategy updates section manually
        res = self.client.put(f'/api/campaigns/{camp_id}/strategy', json={
            'core_message': 'Customized core narrative arc',
            'primary_objective': 'Customized KPI target: 50% ARR growth'
        }, headers=headers_org1)
        self.assertEqual(res.status_code, 200)
        updated_strat = res.get_json()['strategy']
        self.assertEqual(updated_strat['core_message'], 'Customized core narrative arc')
        self.assertEqual(updated_strat['primary_objective'], 'Customized KPI target: 50% ARR growth')

        # 6. Tenant isolation: Org 2 cannot GET, POST, or PUT strategy for Org 1's campaign
        headers_org2 = self._login(user_id=2, role='admin', org_id=2)
        res = self.client.get(f'/api/campaigns/{camp_id}/strategy', headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        res = self.client.post(f'/api/campaigns/{camp_id}/strategy', json={'provider': 'mock'}, headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        res = self.client.put(f'/api/campaigns/{camp_id}/strategy', json={'core_message': 'Hacked'}, headers=headers_org2)
        self.assertEqual(res.status_code, 404)

        # 7. Delete campaign cascades and cleans up strategy
        headers_org1 = self._login(user_id=1, role='admin', org_id=1)
        res = self.client.delete(f'/api/campaigns/{camp_id}', headers=headers_org1)
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f'/api/campaigns/{camp_id}/strategy', headers=headers_org1)
        self.assertEqual(res.status_code, 404)

if __name__ == '__main__':
    unittest.main()
