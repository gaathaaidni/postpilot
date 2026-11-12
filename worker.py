"""
PostPilot Background Task Worker Daemon
Decoupled background task manager suitable for:
- Environment A (Web Server): Run as a standalone Systemd/Docker service alongside Gunicorn
- Environment B (Termux / Local): Can run concurrently or as a lightweight background session

Coordinates task state using the database (task_state table), ensuring multi-worker safety.
"""
import os
import time
import signal
import sys
import secrets
import threading
import logging
import database
import config
import facebook_api
import posting_utils
from platform_adapters.registry import PlatformRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (Worker) %(message)s")
logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{os.getpid()}-{secrets.token_hex(4)}"
shutdown_event = threading.Event()

def start_module_thread(task_name, target_func=None):
    """Stub for legacy module threads."""
    pass

def stop_module_thread(task_name, stop_func=None):
    """Stub for stopping legacy module threads."""
    pass

def _stop_all_running_threads():
    """Halts all background operations upon worker shutdown."""
    pass

def sync_tasks_with_db():
    """Polls database task_state and dispatches/halts module threads."""
    states = database.get_all_task_states()
    for key, s in states.items():
        if s.get('is_running'):
            start_module_thread(key, None)
        else:
            stop_module_thread(key, None)

def process_due_scheduled_posts(worker_id, allow_simulation=False):
    """Claims and executes due scheduled posts using atomic distributed locks via PlatformRegistry."""
    allow_sim = allow_simulation or bool(os.getenv('POSTPILOT_SIMULATE_SCHEDULER') in ('1', 'true', 'True'))
    if not config.is_publishing_enabled() and not allow_sim:
        logger.info("🛡️ [SAFETY] Scheduled post claiming paused: POSTPILOT_PUBLISHING_ENABLED=0.")
        return []
    enabled_platforms = None if allow_sim else config.get_enabled_publishing_platforms()
    if not allow_sim and not enabled_platforms:
        logger.info("🛡️ [SAFETY] Scheduled post claiming paused: no enabled publishing platforms.")
        return []
    try:
        due_posts = database.claim_due_scheduled_posts(worker_id, limit=5, allowed_platforms=enabled_platforms)
        for sp in due_posts:
            p_type = sp['post_type']
            if sp.get('external_post_id'):
                logger.info(f"Skipping duplicate dispatch for scheduled post #{sp['id']} (already has external_post_id={sp['external_post_id']}).")
                database.complete_scheduled_post(sp['id'], worker_id, success=True, external_post_id=sp['external_post_id'])
                continue
            logger.info(f"Executing scheduled post #{sp['id']} on platform/channel '{p_type}'...")
            try:
                res = PlatformRegistry.dispatch(sp, worker_id=worker_id)
                success = bool(res.get('success', False))
                err = res.get('error')
                if success and not allow_sim and res.get('simulated'):
                    success = False
                    err = res.get('message') or f"Platform '{p_type}' publishing disabled or simulated only."
                ext_id = res.get('external_post_id') or res.get('post_id') or res.get('media_id')
                if success:
                    database.complete_scheduled_post(sp['id'], worker_id, success=True, external_post_id=ext_id)
                    logger.info(f"Successfully published scheduled post #{sp['id']} on platform '{p_type}'. External ID: {ext_id}")
                else:
                    database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message=err or "Publishing failed")
                    logger.warning(f"Failed to publish scheduled post #{sp['id']} on platform '{p_type}': {err}")
            except Exception as e:
                safe_e = facebook_api.sanitize_log_message(str(e))
                logger.error(f"Exception publishing scheduled post #{sp['id']}: {safe_e}")
                database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message=safe_e)
    except Exception as e:
        logger.error(f"Error processing due scheduled posts: {facebook_api.sanitize_log_message(str(e))}")

def _maybe_sync_meta_pages_to_env(last_sync_ts):
    interval = int(os.getenv('META_ENV_SYNC_INTERVAL_SECONDS', '21600') or '21600')
    now_ts = time.time()
    if interval <= 0 or (now_ts - last_sync_ts) < interval:
        return last_sync_ts
    try:
        res = facebook_api.sync_connected_pages_to_env()
        if res.get('success'):
            logger.info(f"[META-SYNC] Verified {res.get('pages_count', 0)} connected Meta Page(s) in .env (updated={res.get('updated')}).")
    except Exception as sync_err:
        logger.warning(f"[META-SYNC] Periodic .env page sync skipped: {facebook_api.sanitize_log_message(str(sync_err))}")
    return now_ts

def run_worker_loop():
    logger.info(f"PostPilot worker daemon initializing (ID: {WORKER_ID})...")
    database.init_db()
    last_meta_sync = 0.0
    
    while not shutdown_event.is_set():
        try:
            # Enforce single active worker via database lease (15-second TTL)
            has_lease = database.acquire_worker_lease(WORKER_ID, lease_name='scheduler', ttl_seconds=15)
            if has_lease:
                last_meta_sync = _maybe_sync_meta_pages_to_env(last_meta_sync)
                sync_tasks_with_db()
                process_due_scheduled_posts(WORKER_ID)
            else:
                active = database.get_active_worker_lease('scheduler')
                active_id = active.get('worker_id', 'unknown') if active else 'unknown'
                logger.info(f"Standby: another worker ({active_id}) holds the scheduler lease.")
                _stop_all_running_threads()
        except Exception as e:
            logger.error(f"Error in task sync loop: {facebook_api.sanitize_log_message(str(e))}")
        
        if shutdown_event.wait(timeout=3.0):
            break

    # Clean release upon shutdown
    try:
        database.release_worker_lease(WORKER_ID, lease_name='scheduler')
    except Exception:
        pass

def shutdown(signum=None, frame=None):
    logger.info("Shutdown signal received. Stopping worker threads...")
    shutdown_event.set()
    _stop_all_running_threads()
    try:
        database.release_worker_lease(WORKER_ID, lease_name='scheduler')
    except Exception:
        pass
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    run_worker_loop()
