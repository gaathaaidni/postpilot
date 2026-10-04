"""
test_worker_lease.py - Validation for PostPilot Worker Lease & State Migration
Verifies:
1. Single worker lease acquisition
2. Mutual exclusion (second worker rejected while lease is active)
3. Lease renewal (heartbeat extension)
4. Active worker lease queries
5. Automatic expiration / stale lease recovery
6. Graceful release on shutdown
7. Database-backed synced_posts tracking (replacing posted.txt)
"""
import os
import sys
import time
import tempfile
import unittest

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database

class TestWorkerLease(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_lease.db")
        config.DATABASE_URL = f"sqlite:///{self.db_path}"
        # Initialize test database
        database.init_db()

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            if os.path.exists(self.temp_dir):
                os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_single_worker_acquisition(self):
        """Worker A acquires an unheld lease."""
        acquired = database.acquire_worker_lease("worker-a", ttl_seconds=5)
        self.assertTrue(acquired, "Worker A should acquire unheld lease")
        
        lease = database.get_active_worker_lease()
        self.assertIsNotNone(lease)
        self.assertEqual(lease["worker_id"], "worker-a")

    def test_mutual_exclusion(self):
        """Worker B cannot acquire lease while Worker A holds active lease."""
        database.acquire_worker_lease("worker-a", ttl_seconds=10)
        
        # Worker B tries to acquire
        acquired_b = database.acquire_worker_lease("worker-b", ttl_seconds=10)
        self.assertFalse(acquired_b, "Worker B should NOT acquire active lease held by Worker A")
        
        # Lease should still belong to Worker A
        lease = database.get_active_worker_lease()
        self.assertEqual(lease["worker_id"], "worker-a")

    def test_lease_renewal(self):
        """Worker A can renew its own lease."""
        database.acquire_worker_lease("worker-a", ttl_seconds=5)
        
        # Re-acquiring with same worker ID acts as renewal
        renewed = database.acquire_worker_lease("worker-a", ttl_seconds=10)
        self.assertTrue(renewed, "Worker A should be able to re-acquire / refresh its own lease")
        
        # Explicit renew function also succeeds
        renew_explicit = database.renew_worker_lease("worker-a", ttl_seconds=15)
        self.assertTrue(renew_explicit, "Worker A explicit renewal should succeed")
        
        # Worker B cannot renew Worker A's lease
        renew_b = database.renew_worker_lease("worker-b", ttl_seconds=15)
        self.assertFalse(renew_b, "Worker B should NOT renew Worker A's lease")

    def test_stale_lease_recovery(self):
        """Expired lease allows Worker B to acquire without manual intervention."""
        # Worker A acquires short TTL lease (1 second)
        database.acquire_worker_lease("worker-a", ttl_seconds=1)
        
        # Sleep until expired
        time.sleep(1.2)
        
        # Active query shows expired
        lease = database.get_active_worker_lease()
        self.assertIsNone(lease, "Expired lease should not be reported as active")
        
        # Worker B should now be able to acquire
        acquired_b = database.acquire_worker_lease("worker-b", ttl_seconds=5)
        self.assertTrue(acquired_b, "Worker B must be able to acquire expired/stale lease")
        
        lease_b = database.get_active_worker_lease()
        self.assertEqual(lease_b["worker_id"], "worker-b")

    def test_graceful_release(self):
        """Worker releases lease on shutdown, allowing immediate handover."""
        database.acquire_worker_lease("worker-a", ttl_seconds=60)
        
        database.release_worker_lease("worker-a")
        
        lease = database.get_active_worker_lease()
        self.assertIsNone(lease, "No active lease should exist after release")
        
        acquired_b = database.acquire_worker_lease("worker-b", ttl_seconds=60)
        self.assertTrue(acquired_b, "Worker B can immediately acquire after release")

    def test_synced_posts_database_storage(self):
        """synced_posts table replaces legacy flat-file posted.txt."""
        self.assertFalse(database.is_post_synced("post-101", "insta_posts"))
        
        database.mark_post_synced("post-101", "insta_posts")
        
        self.assertTrue(database.is_post_synced("post-101", "insta_posts"))
        
        # Duplicate marking should be safe (ON CONFLICT DO NOTHING)
        database.mark_post_synced("post-101", "insta_posts")
        self.assertTrue(database.is_post_synced("post-101", "insta_posts"))
        
        # Different platform / category
        self.assertFalse(database.is_post_synced("post-101", "other_source"))
        
        # All IDs
        all_ids = database.get_all_synced_post_ids("insta_posts")
        self.assertIn("post-101", all_ids)

if __name__ == "__main__":
    unittest.main()
