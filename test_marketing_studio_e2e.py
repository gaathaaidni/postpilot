"""
test_marketing_studio_e2e.py - PostPilot Complete Marketing Studio End-to-End Regression Suite

Covers the full enterprise lifecycle across multi-tenancy, AI strategy, content planning,
creative validation, media storage, publishing pipeline, analytics, and commercial SaaS quotas.
"""
import os
import sys
import io
import json
import time
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

TEMP_DIR = tempfile.mkdtemp(prefix="postpilot_e2e_")
DB_PATH = os.path.join(TEMP_DIR, "e2e_posts.db")
UPLOAD_DIR = os.path.join(TEMP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

os.environ['DATABASE_URL'] = f"sqlite:///{DB_PATH}"
os.environ['POSTPILOT_DATA_DIR'] = TEMP_DIR
os.environ['POSTPILOT_UPLOAD_FOLDER'] = UPLOAD_DIR
os.environ['APP_ENV'] = 'development'
os.environ['LOCAL_MODE'] = '0'
os.environ['SECRET_KEY'] = 'postpilot-e2e-suite-secret-key-12345'

import config
import database
import app as application_module
import ai_service
import validation
import worker


class TestMarketingStudioE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        config.UPLOAD_FOLDER = UPLOAD_DIR
        config.LOCAL_MODE = False
        database.init_db()
        cls.app = application_module.app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

    def test_full_commercial_marketing_studio_journey(self):
        """
        Executes the end-to-end user and system journey:
        1. Register new commercial tenant organization
        2. Set up brand profile and positioning
        3. Create campaign
        4. Generate AI strategy blueprint
        5. Generate 7-day content planner
        6. Convert plan to content drafts
        7. Edit draft and verify immutable revision tracking
        8. Upload media asset to library
        9. Validate creative platform rules
        10. Schedule draft to publishing queue
        11. Worker atomic claim & publish simulation
        12. Query aggregated analytics dashboard
        13. Upgrade subscription plan and verify entitlements
        """
        # Step 1: Self-service SaaS registration
        reg_payload = {
            'org_name': 'Acme Global Ventures',
            'username': 'acme_owner',
            'email': 'owner@acmeglobal.com',
            'password': 'Secure_Acme_Pass_2026!'
        }
        reg_res = self.client.post('/api/auth/register-org', json=reg_payload)
        self.assertEqual(reg_res.status_code, 201)
        reg_data = reg_res.get_json()
        org_id = reg_data['organization']['id']
        user_id = reg_data['user']['id']
        self.assertEqual(reg_data['user']['role'], 'owner')

        # Log in as Acme Owner
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['username'] = 'acme_owner'
            sess['organization_id'] = org_id
            sess['role'] = 'owner'
            sess['csrf_token'] = 'acme-csrf-token'

        headers = {'X-CSRFToken': 'acme-csrf-token'}

        # Step 2: Create a brand workspace under new organization
        brand_id = database.create_brand(
            organization_id=org_id,
            name='Acme Robotics',
            slug='acme-robotics',
            description='Autonomous logistics and industrial robotics.'
        )
        self.assertIsNotNone(brand_id)

        # Set up brand marketing profile with factual guardrails
        profile_res = self.client.post(f"/api/brands/{brand_id}/profile", json={
            'positioning': 'World leader in warehouse automation and mobile robotics.',
            'voice_and_tone': 'Authoritative, innovative, enterprise-grade, data-driven',
            'approved_product_facts': '99.98% uptime SLA. Over 500 installations across Europe and NA.',
            'prohibited_claims': 'Do not claim infinite battery life. Do not mention uncertified hardware.',
            'target_audiences': 'Supply Chain Directors, VP of Logistics',
            'target_markets': 'North America, Germany, UK'
        }, headers=headers)
        self.assertEqual(profile_res.status_code, 200)

        # Step 3: Create Marketing Campaign
        camp_res = self.client.post('/api/campaigns', json={
            'brand_id': brand_id,
            'name': 'Q1 2027 Autonomous Fleet Expansion',
            'objective': 'Enterprise Lead Generation',
            'brief': 'Showcase next-generation AMR warehouse robots with 99.98% uptime SLA.',
            'target_audience': 'Warehouse executives',
            'target_markets': 'EMEA & North America',
            'languages': 'en'
        }, headers=headers)
        self.assertEqual(camp_res.status_code, 201)
        camp = camp_res.get_json()
        camp_id = camp['id']

        # Step 4: Generate 14-section strategic blueprint
        strat_res = self.client.post(f"/api/campaigns/{camp_id}/strategy", json={
            'provider': 'mock'
        }, headers=headers)
        self.assertEqual(strat_res.status_code, 200)
        strat = strat_res.get_json().get('strategy', {})
        self.assertIn('Enterprise Lead Generation', strat.get('primary_objective', ''))

        # Step 5: Generate intelligent weekly editorial planner
        plan_res = self.client.post(f"/api/campaigns/{camp_id}/planner", json={
            'period_type': 'weekly',
            'start_date': '2026-11-15',
            'provider': 'mock'
        }, headers=headers)
        self.assertEqual(plan_res.status_code, 201)
        plan_data = plan_res.get_json()
        plan_id = plan_data['content_plan']['id']
        entries = plan_data['entries']
        self.assertGreaterEqual(len(entries), 3)

        # Step 6: Convert plan to content drafts
        convert_res = self.client.post(f"/api/content-plans/{plan_id}/convert-drafts", headers=headers)
        self.assertEqual(convert_res.status_code, 201)
        drafts = convert_res.get_json().get('drafts', [])
        self.assertEqual(len(drafts), len(entries))
        draft = drafts[0]
        draft_id = draft['id']
        self.assertEqual(draft['current_revision'], 1)

        # Step 7: Edit draft and verify immutable revision tracking
        edit_res = self.client.put(f"/api/drafts/{draft_id}", json={
            'headline': 'Warehouse Automation Redefined',
            'caption': 'Discover how our autonomous mobile robots deliver 99.98% uptime for enterprise fulfillment.',
            'hashtags': '#Logistics #Robotics #SupplyChain',
            'call_to_action': 'Schedule an Automation Audit',
            'expected_revision': 1
        }, headers=headers)
        self.assertEqual(edit_res.status_code, 200)
        updated_draft = edit_res.get_json()
        self.assertEqual(updated_draft['current_revision'], 2)

        # Verify revision history list
        revs_res = self.client.get(f"/api/drafts/{draft_id}/revisions")
        self.assertEqual(revs_res.status_code, 200)
        revisions = revs_res.get_json().get('revisions', [])
        self.assertEqual(len(revisions), 2)
        rev_nums = [r['revision_number'] for r in revisions]
        self.assertEqual(rev_nums, [1, 2])

        # Step 8: Upload media asset to organization media library
        from PIL import Image
        img_buf = io.BytesIO()
        valid_img = Image.new('RGB', (100, 100), color='blue')
        valid_img.save(img_buf, format='PNG')
        img_buf.seek(0)

        upload_res = self.client.post('/api/media/upload', data={
            'file': (img_buf, 'robotics_hero.png'),
            'brand_id': str(brand_id),
            'campaign_id': str(camp_id)
        }, headers=headers)
        self.assertEqual(upload_res.status_code, 201)
        media_asset = upload_res.get_json()['asset']
        media_id = media_asset['id']

        # Step 9: Validate creative platform rules
        val_res = self.client.post(f"/api/drafts/{draft_id}/validate-creative", headers=headers)
        self.assertEqual(val_res.status_code, 200)
        val_data = val_res.get_json()
        self.assertTrue(val_data.get('valid'))

        # Step 10: Schedule draft into publishing queue
        future_iso = (datetime.now(timezone.utc) + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S')
        sched_res = self.client.post(f"/api/drafts/{draft_id}/schedule", json={
            'channel': 'tour',
            'scheduled_time': future_iso,
            'media_asset_id': media_id
        }, headers=headers)
        self.assertEqual(sched_res.status_code, 201)
        sched_data = sched_res.get_json()
        self.assertEqual(sched_data['draft']['status'], 'scheduled')
        sched_post_id = sched_data['scheduled_post']['id']

        # Step 11: Worker atomic claim & execution simulation
        # Advance scheduled time to past so worker claims it
        with database.get_db_connection() as conn:
            past_iso = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("UPDATE scheduled_posts SET scheduled_for = ? WHERE id = ?", (past_iso, sched_post_id))
            conn.commit()

        # Worker claims post
        worker_id = "test-worker-alpha"
        claimed_posts = database.claim_due_scheduled_posts(worker_id, limit=5)
        self.assertTrue(any(p['id'] == sched_post_id for p in claimed_posts))

        # Worker completes post successfully
        completed = database.complete_scheduled_post(sched_post_id, worker_id, success=True)
        self.assertTrue(completed)

        # Confirm post is marked published
        completed_post = database.get_scheduled_post_by_id(sched_post_id)
        self.assertEqual(completed_post['status'], 'published')

        # Step 12: Query Marketing Intelligence Dashboard
        dash_res = self.client.get('/api/analytics/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        dash = dash_res.get_json()
        self.assertGreaterEqual(dash['total_campaigns'], 1)
        self.assertGreaterEqual(dash['total_drafts'], 1)
        self.assertGreaterEqual(dash['publishing_success_rate'], 50)

        # Step 13: Upgrade SaaS Subscription and verify limits
        upgrade_res = self.client.post('/api/saas/subscription/upgrade', json={
            'plan_id': 'enterprise',
            'billing_cycle': 'annual'
        }, headers=headers)
        self.assertEqual(upgrade_res.status_code, 200)
        sub_data = upgrade_res.get_json()['subscription']
        self.assertEqual(sub_data.get('plan_code') or sub_data.get('plan_id'), 'enterprise')
        self.assertEqual(sub_data['max_campaigns'], 500)
        self.assertEqual(sub_data['max_monthly_ai_tokens'], 2000000)


if __name__ == '__main__':
    unittest.main()
