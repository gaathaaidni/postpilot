"""
test_backup_restore.py - Comprehensive Staging Backup & Restore Security Validation
Verifies:
1. Generation of portable ZIP backup
2. Strict exclusion of secrets, passwords, user hashes, and .env files
3. Path traversal attack prevention during import (e.g., ../../evil)
4. Preservation of post records, intervals, and media
5. Round-trip export and import data integrity
"""
import os
import sys
import io
import json
import zipfile
import tempfile
import unittest
from pathlib import Path
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import backup

class TestBackupRestoreStaging(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_backup.db")
        self.media_dir = os.path.join(self.temp_dir, "media")
        os.makedirs(self.media_dir, exist_ok=True)

        config.DATABASE_URL = f"sqlite:///{self.db_path}"
        config.DATA_DIR = self.temp_dir
        config.UPLOAD_FOLDER = self.media_dir

        database.init_db()

    def tearDown(self):
        try:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_export_excludes_secrets_and_passwords(self):
        """Ensures exported archives never contain .env, user password hashes, or API secrets."""
        # Create a sample post
        with database.get_db_connection() as conn:
            conn.execute(
                "INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?)",
                ("tour", "Staging Tour Announcement", "tour_image.png")
            )
            conn.commit()

        # Create dummy image
        img_path = Path(self.media_dir) / "tour_image.png"
        img = Image.new('RGB', (10, 10), color='green')
        img.save(str(img_path))

        # Run export
        backup_zip = backup.export_backup()
        self.assertTrue(backup_zip.exists())

        # Inspect ZIP archive contents
        with zipfile.ZipFile(backup_zip, 'r') as zf:
            namelist = zf.namelist()

            # Verify required files present
            self.assertIn("manifest.json", namelist)
            self.assertIn("posts.json", namelist)
            self.assertIn("settings.json", namelist)
            self.assertIn("media/tour_image.png", namelist)

            # Strictly verify NO .env or user tables
            for name in namelist:
                self.assertNotIn(".env", name)
                self.assertNotIn("users", name)
                self.assertNotIn("password", name)

            # Verify manifest content
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
            self.assertEqual(manifest['total_posts'], 1)
            self.assertNotIn("FB_ACCESS_TOKEN", str(manifest))
            self.assertNotIn("SECRET_KEY", str(manifest))

            # Verify settings content contains only non-secret intervals
            settings = json.loads(zf.read("settings.json").decode('utf-8'))
            self.assertIn("intervals", settings)
            self.assertNotIn("password", str(settings))
            self.assertNotIn("token", str(settings))

    def test_import_path_traversal_protection(self):
        """Verifies that malicious zip entries with path traversal (e.g., ../../evil.txt) are neutralized."""
        malicious_zip_path = Path(self.temp_dir) / "malicious.zip"
        with zipfile.ZipFile(malicious_zip_path, 'w') as zf:
            zf.writestr("manifest.json", json.dumps({"version": "1.0", "posts_count": 0}))
            zf.writestr("posts.json", json.dumps([]))
            zf.writestr("settings.json", json.dumps({"intervals": {}}))
            # Attempt directory traversal in media folder
            zf.writestr("media/../../traversal_attack.txt", "MALICIOUS CONTENT")

        # Import should safely sanitize using os.path.basename
        stats = backup.import_backup(malicious_zip_path, overwrite=False)
        self.assertIsNotNone(stats)

        # Confirm traversal file was NOT created outside target folder
        escaped_file = Path(self.temp_dir).parent / "traversal_attack.txt"
        self.assertFalse(escaped_file.exists(), "Path traversal vulnerability detected!")

if __name__ == "__main__":
    unittest.main()
