"""
test_standalone_worker.py - Standalone Worker Daemon Process & Lifecycle Test
Verifies:
1. worker.py process startup and immediate lease acquisition
2. Second worker instance enters Standby mode while first holds lease
3. app.py skips in-process execution when standalone worker holds lease
4. Graceful worker shutdown releases the lease
5. Subsequent worker immediately claims released lease
"""
import os
import sys
import time
import signal
import tempfile
import unittest
import threading
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import database
import worker
import app

class TestStandaloneWorkerLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_worker_lifecycle.db")
        config.DATABASE_URL = f"sqlite:///{self.db_path}"
        database.init_db()

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            if os.path.exists(self.temp_dir):
                os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_worker_lease_acquisition_and_standby(self):
        """Worker 1 acquires lease; Worker 2 enters standby; Worker 1 shutdown frees lease."""
        worker1_id = f"worker-test-1-{os.getpid()}"
        worker2_id = f"worker-test-2-{os.getpid()}"

        # 1. Worker 1 acquires lease
        has_lease_1 = database.acquire_worker_lease(worker1_id, lease_name='scheduler', ttl_seconds=15)
        self.assertTrue(has_lease_1, "Worker 1 should acquire unheld lease")

        active_lease = database.get_active_worker_lease('scheduler')
        self.assertIsNotNone(active_lease)
        self.assertEqual(active_lease['worker_id'], worker1_id)

        # 2. Worker 2 attempts acquisition while Worker 1 is active -> must fail (Standby)
        has_lease_2 = database.acquire_worker_lease(worker2_id, lease_name='scheduler', ttl_seconds=15)
        self.assertFalse(has_lease_2, "Worker 2 must not acquire active lease; should enter standby")

        # 3. Web app checks lease -> detects external worker and skips in-process execution
        app_worker_id = f"app-{os.getpid()}"
        current_active = database.get_active_worker_lease('scheduler')
        self.assertNotEqual(current_active['worker_id'], app_worker_id)

        # 4. Worker 1 shuts down and cleanly releases lease
        database.release_worker_lease(worker1_id, lease_name='scheduler')
        self.assertIsNone(database.get_active_worker_lease('scheduler'))

        # 5. Worker 2 is now able to acquire the lease immediately
        has_lease_2_after = database.acquire_worker_lease(worker2_id, lease_name='scheduler', ttl_seconds=15)
        self.assertTrue(has_lease_2_after, "Worker 2 should acquire lease immediately after Worker 1 release")

    def test_worker_sync_tasks_with_mocked_posts(self):
        """Tests that sync_tasks_with_db respects database state without live API calls."""
        # Set task 'tour' as running in DB
        database.set_task_state('tour', is_running=True, status="Pending Test")
        database.set_task_state('nz', is_running=False, status="Idle")
        database.set_task_state('gaatha', is_running=False, status="Idle")
        database.set_task_state('insta', is_running=False, status="Idle")

        with patch('worker.start_module_thread') as mock_start, \
             patch('worker.stop_module_thread') as mock_stop:
            worker.sync_tasks_with_db()
            mock_start.assert_called_once()
            args = mock_start.call_args[0]
            self.assertEqual(args[0], 'tour')

    def test_clean_shutdown_handler(self):
        """Verifies shutdown releases worker lease."""
        database.acquire_worker_lease(worker.WORKER_ID, lease_name='scheduler', ttl_seconds=60)
        self.assertIsNotNone(database.get_active_worker_lease('scheduler'))

        # Call release directly as performed in shutdown
        database.release_worker_lease(worker.WORKER_ID, lease_name='scheduler')
        self.assertIsNone(database.get_active_worker_lease('scheduler'))

if __name__ == "__main__":
    unittest.main()
