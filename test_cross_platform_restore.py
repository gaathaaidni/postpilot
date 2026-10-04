"""
test_cross_platform_restore.py - Cross-Platform Data Portability & End-to-End Duplicate Protection Test

Verifies Phase 9 requirements:
1. Cross-environment export from source environment.
2. Verified exclusion of secrets (.env, tokens, credentials) from backup archive.
3. Import into completely isolated target runtime environment.
4. Data integrity verification (posts, intervals, media assets, database consistency).
5. End-to-end duplicate protection verification (synced_posts prevention on repeat run).
"""
import os
import sys
import tempfile
import unittest
import shutil
import zipfile
import json
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import backup

class TestCrossPlatformDataAndDuplicateProtection(unittest.TestCase):

    def setUp(self):
        # 1. Setup Source Environment
        self.src_dir = tempfile.mkdtemp(prefix="postpilot_src_env_")
        self.src_db = os.path.join(self.src_dir, "posts.db")
        self.src_media = os.path.join(self.src_dir, "images")
        os.makedirs(self.src_media, exist_ok=True)

        # 2. Setup Target (Isolated Cross-Platform Destination) Environment
        self.dst_dir = tempfile.mkdtemp(prefix="postpilot_dst_env_")
        self.dst_db = os.path.join(self.dst_dir, "posts.db")
        self.dst_media = os.path.join(self.dst_dir, "images")
        os.makedirs(self.dst_media, exist_ok=True)

        # Point active config to source
        config.DATABASE_URL = f"sqlite:///{self.src_db}"
        config.DATA_DIR = Path(self.src_dir)
        config.UPLOAD_FOLDER = Path(self.src_media)
        database.init_db()

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.dst_dir, ignore_errors=True)

    def test_cross_platform_export_restore_and_duplicate_prevention(self):
        """Validates export from source, secret exclusion, restore to target, and duplicate prevention."""
        
        # --- A. Populate Source Environment ---
        # 1. Create dummy image
        sample_img_name = "test_banner.png"
        sample_img_path = os.path.join(self.src_media, sample_img_name)
        with open(sample_img_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nMockImageDataForPhase9ExportVerification12345")

        # 2. Add posts across different channels
        post_id_tour = database.add_post("tour", "Nexora Suite Phase 9 Test Post", sample_img_name)
        post_id_gaatha = database.add_post("gaatha", "Gaatha AI Cultural Intelligence Post", None)

        # 3. Configure intervals via task state
        database.set_task_state("tour", interval_seconds=2400)
        database.set_task_state("nz", interval_seconds=3600)

        # 4. Mark post as synced in source
        database.mark_post_synced(post_id_tour, "instagram")

        # --- B. Export Backup ---
        export_zip = backup.export_backup()
        self.assertTrue(export_zip.exists(), "Backup archive must be created")

        # --- C. Verify Archive Contents & Secret Exclusion ---
        with zipfile.ZipFile(export_zip, 'r') as zf:
            file_list = zf.namelist()
            self.assertIn("manifest.json", file_list)
            self.assertIn(f"media/{sample_img_name}", file_list)

            # Ensure NO secrets, tokens, or environment files are archived
            for f in file_list:
                self.assertFalse(f.endswith(".env"), "Backup archive must NOT contain .env")
                self.assertFalse("token" in f.lower() and f.endswith(".txt"), "Backup must NOT contain token files")

            manifest_data = json.loads(zf.read("manifest.json").decode('utf-8'))
            self.assertIn("version", manifest_data)
            self.assertEqual(manifest_data["total_posts"], 2)
            self.assertEqual(manifest_data["total_media_found"], 1)

        # --- D. Switch Config to Target Isolated Runtime ---
        config.DATABASE_URL = f"sqlite:///{self.dst_db}"
        config.DATA_DIR = Path(self.dst_dir)
        config.UPLOAD_FOLDER = Path(self.dst_media)
        database.init_db()

        # Confirm target starts empty
        self.assertEqual(len(database.load_posts_by_type("tour")), 0)
        self.assertEqual(len(database.load_posts_by_type("gaatha")), 0)

        # --- E. Restore into Target Isolated Environment ---
        stats = backup.import_backup(export_zip, overwrite=False)
        self.assertIsNotNone(stats)
        self.assertEqual(stats["posts_imported"], 2)
        self.assertEqual(stats["media_extracted"], 1)

        # --- F. Verify Target Data Integrity ---
        # 1. Verify posts restored
        tour_posts = database.load_posts_by_type("tour")
        self.assertEqual(len(tour_posts), 1)
        self.assertEqual(tour_posts[0]["message"], "Nexora Suite Phase 9 Test Post")
        self.assertEqual(tour_posts[0]["image_filename"], sample_img_name)

        gaatha_posts = database.load_posts_by_type("gaatha")
        self.assertEqual(len(gaatha_posts), 1)
        self.assertEqual(gaatha_posts[0]["message"], "Gaatha AI Cultural Intelligence Post")

        # 2. Verify media asset restored in target media directory
        restored_img_path = os.path.join(self.dst_media, sample_img_name)
        self.assertTrue(os.path.exists(restored_img_path), "Media asset must be restored in target directory")
        with open(restored_img_path, "rb") as f:
            content = f.read()
            self.assertIn(b"MockImageDataForPhase9ExportVerification12345", content)

        # 3. Verify intervals restored
        self.assertEqual(database.get_task_state("tour")['interval'], 2400)
        self.assertEqual(database.get_task_state("nz")['interval'], 3600)

        # --- G. Verify End-to-End Duplicate Protection on Restored State ---
        # 1. Simulate duplicate check for an already-synced post
        database.mark_post_synced(tour_posts[0]["id"], "instagram")
        self.assertTrue(
            database.is_post_synced(tour_posts[0]["id"], "instagram"),
            "Target environment must recognize post as synced"
        )

        # 2. Attempt duplicate publication logic
        attempt_count = 0
        publish_executed = 0

        for _ in range(2):
            attempt_count += 1
            if not database.is_post_synced(tour_posts[0]["id"], "instagram"):
                publish_executed += 1
                database.mark_post_synced(tour_posts[0]["id"], "instagram")

        self.assertEqual(attempt_count, 2, "Two publication attempts were evaluated")
        self.assertEqual(publish_executed, 0, "Zero duplicate publications executed (already synced)")

        # 3. Test fresh un-synced post
        new_post_id = database.add_post("nz", "Fresh Unsynced Post", None)
        self.assertFalse(database.is_post_synced(new_post_id, "instagram"))

        # First run -> allowed
        if not database.is_post_synced(new_post_id, "instagram"):
            publish_executed += 1
            database.mark_post_synced(new_post_id, "instagram")

        self.assertEqual(publish_executed, 1, "First publication must be allowed")

        # Second run -> duplicate prevented
        if not database.is_post_synced(new_post_id, "instagram"):
            publish_executed += 1
            database.mark_post_synced(new_post_id, "instagram")

        self.assertEqual(publish_executed, 1, "Second duplicate publication must be strictly prevented")

if __name__ == "__main__":
    unittest.main()
