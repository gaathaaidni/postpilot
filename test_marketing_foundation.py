"""
PostPilot Phase 3.1 Unit A Test Suite
Tests for Tenant-Scoped Campaign and Brand Marketing Profile Foundation.
"""
import os
import json
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Isolated temporary environment for tests
os.environ['ENV'] = 'testing'
os.environ['TESTING'] = 'true'
os.environ['SECRET_KEY'] = 'test-secret-key-phase3-unit-a-marketing-32b'
_tmp_dir = tempfile.TemporaryDirectory()
os.environ['POSTPILOT_DATA_DIR'] = _tmp_dir.name
os.environ['DATABASE_URL'] = f"sqlite:///{Path(_tmp_dir.name) / 'marketing_foundation_test.db'}"

import database

class TestMarketingFoundation(unittest.TestCase):
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
        # Ensure default GAATHA org (ID 1) and a secondary org (ID 2) exist
        with database.get_db_connection() as conn:
            conn.execute(
                "INSERT INTO organizations (id, name, slug, plan, timezone, is_active) "
                "VALUES (2, 'SaaS Client Corp', 'saas-client', 'growth', 'America/New_York', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            # Ensure secondary org brand exists
            conn.execute(
                "INSERT INTO brands (id, organization_id, name, slug, description, is_active) "
                "VALUES (201, 2, 'Client Brand X', 'client-brand-x', 'External Client Brand', 1) "
                "ON CONFLICT(id) DO NOTHING"
            )
            conn.commit()

    def test_01_seeded_gaatha_brands_preserved_and_not_duplicated(self):
        """Verifies default GAATHA organization has its 6 initial brand workspaces intact without duplicates."""
        brands_org1 = database.get_brands_by_organization(1)
        slugs = [b['slug'] for b in brands_org1]
        self.assertIn('gaatha-suite', slugs)
        self.assertIn('gaatha-pos', slugs)
        self.assertIn('sentira-ai', slugs)
        self.assertIn('gaatha-terra', slugs)
        self.assertIn('phoenix-by-gaatha', slugs)
        self.assertIn('gaatha-ai', slugs)
        self.assertEqual(len(slugs), 6)

        # Run init_db() again to verify idempotent non-duplication
        database.init_db()
        brands_after = database.get_brands_by_organization(1)
        self.assertEqual(len(brands_after), 6)

    def test_02_brand_marketing_profile_upsert_and_isolation(self):
        """Verifies brand marketing profiles can be created, updated, and enforce tenant isolation."""
        # Find GAATHA AI brand
        brands = database.get_brands_by_organization(1)
        gaatha_ai = next(b for b in brands if b['slug'] == 'gaatha-ai')

        # Create profile for GAATHA AI in Org 1
        prof = database.upsert_brand_marketing_profile(
            brand_id=gaatha_ai['id'],
            organization_id=1,
            positioning="Next-generation AI research and generative applications for creators and enterprises",
            target_audiences=["AI Researchers", "Product Builders", "Creative Agencies"],
            target_markets=["Global", "India", "North America"],
            languages=["English", "Hindi"],
            voice_and_tone="Visionary, technical yet accessible, authoritative",
            approved_product_facts="GAATHA AI builds multi-agent workflows and high-performance generative studios.",
            prohibited_claims="Do not claim AGI or sentient machine intelligence."
        )
        self.assertIsNotNone(prof)
        self.assertEqual(prof['organization_id'], 1)
        self.assertEqual(prof['brand_id'], gaatha_ai['id'])
        self.assertIn("Next-generation AI research", prof['positioning'])

        # Retrieve profile
        fetched = database.get_brand_marketing_profile(gaatha_ai['id'], organization_id=1)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['id'], prof['id'])

        # Cross-tenant access attempt: Org 2 attempts to fetch Org 1's profile -> REJECTED
        with self.assertRaises(ValueError):
            database.get_brand_marketing_profile(gaatha_ai['id'], organization_id=2)

        # Cross-tenant upsert attempt: Org 2 attempts to create profile for Org 1's brand -> REJECTED
        with self.assertRaises(ValueError):
            database.upsert_brand_marketing_profile(
                brand_id=gaatha_ai['id'],
                organization_id=2,
                positioning="Malicious cross-tenant override attempt"
            )

        # Update profile for same brand in Org 1 updates existing record rather than creating a duplicate
        updated = database.upsert_brand_marketing_profile(
            brand_id=gaatha_ai['id'],
            organization_id=1,
            positioning="Updated Visionary AI research platform",
            preferred_ctas=["Explore Models", "Start Building Today"]
        )
        self.assertEqual(updated['id'], prof['id'])
        self.assertEqual(updated['positioning'], "Updated Visionary AI research platform")
        self.assertIn("Explore Models", updated['preferred_ctas'])

    def test_03_campaign_crud_and_tenant_scoping(self):
        """Verifies campaigns can be created, listed, updated, and deleted with strict tenant isolation."""
        brands = database.get_brands_by_organization(1)
        sentira = next(b for b in brands if b['slug'] == 'sentira-ai')

        # 1. Create campaign in Org 1
        camp = database.create_campaign(
            organization_id=1,
            brand_id=sentira['id'],
            name="Q4 Enterprise AI Launch",
            objective="Drive enterprise trial signups for Sentira AI orchestration",
            brief="Highlight reliable agentic orchestration, data security, and sub-second response times.",
            campaign_type="product_launch",
            target_audience="CTOs and VP Engineering",
            target_markets="Global SaaS, FinTech, E-commerce",
            languages="en",
            budget="$5,000"
        )
        self.assertIsNotNone(camp)
        self.assertEqual(camp['organization_id'], 1)
        self.assertEqual(camp['brand_id'], sentira['id'])
        self.assertEqual(camp['name'], "Q4 Enterprise AI Launch")
        camp_id = camp['id']

        # 2. Retrieve campaign
        retrieved = database.get_campaign_by_id(camp_id, organization_id=1)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['name'], "Q4 Enterprise AI Launch")
        self.assertEqual(retrieved['brand_slug'], 'sentira-ai')

        # 3. Cross-tenant retrieval by Org 2 -> Returns None
        cross_get = database.get_campaign_by_id(camp_id, organization_id=2)
        self.assertIsNone(cross_get)

        # 4. Cross-tenant update by Org 2 -> Raises ValueError
        with self.assertRaises(ValueError):
            database.update_campaign(
                campaign_id=camp_id,
                organization_id=2,
                name="Hacked Campaign"
            )

        # 5. List campaigns for Org 1 vs Org 2
        c_list_1 = database.list_campaigns(organization_id=1, brand_id=sentira['id'])
        self.assertIn(camp_id, [c['id'] for c in c_list_1])

        c_list_2 = database.list_campaigns(organization_id=2)
        self.assertNotIn(camp_id, [c['id'] for c in c_list_2])

        # 6. Update campaign in Org 1
        upd = database.update_campaign(
            campaign_id=camp_id,
            organization_id=1,
            status="active",
            name="Q4 Enterprise AI Launch - Worldwide"
        )
        self.assertEqual(upd['status'], "active")
        self.assertEqual(upd['name'], "Q4 Enterprise AI Launch - Worldwide")

    def test_04_cross_organization_brand_campaign_association_rejected(self):
        """Verifies an organization cannot attach a campaign to another organization's brand."""
        # Brand 201 belongs to Org 2
        # Org 1 attempts to create campaign for Brand 201
        with self.assertRaises(ValueError) as ctx:
            database.create_campaign(
                organization_id=1,
                brand_id=201,
                name="Illegal Cross-Org Campaign",
                objective="Objective",
                brief="Brief"
            )
        self.assertIn("different organization", str(ctx.exception).lower())

    def test_05_content_draft_crud_and_version_preservation(self):
        """Verifies content drafts can be created, retrieved, updated, and listed under campaigns."""
        brands = database.get_brands_by_organization(1)
        phoenix = next(b for b in brands if b['slug'] == 'phoenix-by-gaatha')

        # Create campaign
        camp = database.create_campaign(
            organization_id=1,
            brand_id=phoenix['id'],
            name="Global Visa & Mobility Campaign",
            objective="Increase consultations for international residency and visa pathways",
            brief="Promote hassle-free business and investor migration with transparent legal advisory."
        )
        camp_id = camp['id']

        # 1. Create drafts for multiple target platforms
        platforms = ['facebook', 'instagram', 'linkedin', 'x', 'whatsapp']
        draft_ids = []
        for plat in platforms:
            d = database.create_content_draft(
                organization_id=1,
                brand_id=phoenix['id'],
                campaign_id=camp_id,
                target_platform=plat,
                headline=f"Pathway to Global Mobility with Phoenix ({plat.capitalize()})",
                caption=f"Expand your horizons with tailored international residency solutions. ({plat})",
                hashtags="#GlobalMobility #Immigration #PhoenixByGaatha",
                call_to_action="Book a 1-on-1 Consultation Today",
                language="en",
                ai_provider="mock",
                ai_model="mock-v1"
            )
            self.assertIsNotNone(d)
            self.assertEqual(d['target_platform'], plat)
            draft_ids.append(d['id'])

        self.assertEqual(len(draft_ids), 5)

        # 2. List drafts by campaign
        drafts = database.list_content_drafts(organization_id=1, campaign_id=camp_id)
        self.assertEqual(len(drafts), 5)

        # 3. Tenant isolation: Org 2 cannot list or read Org 1 drafts
        d_org2 = database.list_content_drafts(organization_id=2, campaign_id=camp_id)
        self.assertEqual(len(d_org2), 0)

        d_single_org2 = database.get_content_draft_by_id(draft_ids[0], organization_id=2)
        self.assertIsNone(d_single_org2)

        # 4. Draft version preservation / regeneration simulation:
        # Creating a second draft for the same platform does NOT overwrite or delete the first draft
        first_x_draft = next(d for d in drafts if d['target_platform'] == 'x')
        second_x_draft = database.create_content_draft(
            organization_id=1,
            brand_id=phoenix['id'],
            campaign_id=camp_id,
            target_platform='x',
            headline="New Version: Global Mobility Pathways",
            caption="Quick update: new international pathways open this month. #Phoenix",
            ai_provider="mock",
            ai_model="mock-v2",
            metadata={'version': 2, 'regenerated_from': first_x_draft['id']}
        )
        self.assertNotEqual(first_x_draft['id'], second_x_draft['id'])

        # Both drafts exist in the campaign
        all_x_drafts = database.list_content_drafts(organization_id=1, campaign_id=camp_id, target_platform='x')
        self.assertEqual(len(all_x_drafts), 2)

        # 5. Edit draft manually
        edited = database.update_content_draft(
            draft_id=first_x_draft['id'],
            organization_id=1,
            caption="Manually polished caption for X platform."
        )
        self.assertEqual(edited['caption'], "Manually polished caption for X platform.")

        # 6. Delete single draft
        del_ok = database.delete_content_draft(second_x_draft['id'], organization_id=1)
        self.assertTrue(del_ok)
        self.assertIsNone(database.get_content_draft_by_id(second_x_draft['id'], organization_id=1))
        # First draft remains intact
        self.assertIsNotNone(database.get_content_draft_by_id(first_x_draft['id'], organization_id=1))

    def test_06_dynamic_additional_organizations_and_brands(self):
        """Verifies that arbitrary new organizations and brands can create campaigns and profiles without code changes."""
        # Create Org 3 dynamically
        org3_id = database.create_organization("Brand Co Global", "brand-co-global", "enterprise")
        self.assertGreater(org3_id, 2)

        # Create 2 custom brands dynamically
        b1_id = database.create_brand(org3_id, "Apex Dynamics", "apex-dynamics", "Industrial IoT")
        b2_id = database.create_brand(org3_id, "Nova Health", "nova-health", "Digital Telehealth")

        # Create profiles and campaigns for Org 3
        prof_b1 = database.upsert_brand_marketing_profile(
            brand_id=b1_id,
            organization_id=org3_id,
            positioning="Industrial automation and predictive telemetry",
            target_markets=["Germany", "Japan", "United States"],
            languages=["de", "ja", "en"]
        )
        self.assertEqual(prof_b1['organization_id'], org3_id)

        camp_b1 = database.create_campaign(
            organization_id=org3_id,
            brand_id=b1_id,
            name="Hannover Messe 2027 Promotion",
            objective="Generate booth traffic and distribution partnerships",
            brief="Highlight sub-millisecond edge telemetry and predictive maintenance ROI."
        )
        self.assertEqual(camp_b1['organization_id'], org3_id)
        self.assertEqual(camp_b1['brand_id'], b1_id)

        # Ensure Org 1 cannot see Org 3's campaigns or profiles
        self.assertIsNone(database.get_campaign_by_id(camp_b1['id'], organization_id=1))
        with self.assertRaises(ValueError):
            database.get_brand_marketing_profile(b1_id, organization_id=1)

if __name__ == '__main__':
    unittest.main()
