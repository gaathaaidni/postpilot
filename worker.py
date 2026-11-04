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
import channel_runner
import insta
import facebook_api
import posting_utils

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (Worker) %(message)s")
logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{os.getpid()}-{secrets.token_hex(4)}"
running_threads = {}
threads_lock = threading.Lock()
shutdown_event = threading.Event()

insta_suite = insta.InstaSync(config.FB_PAGE_ID_SUITE, config.INSTA_ID_SUITE, 'insta_suite')
insta_phoenix = insta.InstaSync(config.FB_PAGE_ID_PHOENIX, config.INSTA_ID_PHOENIX, 'insta_phoenix')

def _status_callback(task_name, is_running, message='', current_post=None):
    """Saves task status updates directly to the database."""
    try:
        database.set_task_state(
            task_name,
            is_running=is_running,
            status=facebook_api.sanitize_log_message(message) if message else '',
            current_post_summary=facebook_api.sanitize_log_message(current_post) if current_post else None
        )
    except Exception as e:
        logger.error(f"Error persisting task status for {task_name}: {facebook_api.sanitize_log_message(str(e))}")

# Register callbacks across all configured channels
for ch in channel_runner.CHANNELS.values():
    ch.set_status_callback(_status_callback)
insta.set_status_callback(_status_callback)

def start_module_thread(task_name, target_func):
    with threads_lock:
        if task_name in running_threads and running_threads[task_name].is_alive():
            return
        thread = threading.Thread(target=target_func, daemon=True, name=f"Worker-{task_name}")
        thread.start()
        running_threads[task_name] = thread
        logger.info(f"Started worker thread for {task_name}")

def stop_module_thread(task_name, stop_func):
    with threads_lock:
        stop_func()
        th = running_threads.pop(task_name, None)
        if th and th.is_alive():
            th.join(timeout=1.0)
        logger.info(f"Stopped worker thread for {task_name}")

def _stop_all_running_threads():
    """Halts and joins all active posting threads."""
    for ch in channel_runner.CHANNELS.values():
        ch.stop()
    insta_suite.stop()
    insta_phoenix.stop()
    with threads_lock:
        for th in list(running_threads.values()):
            if th and th.is_alive():
                th.join(timeout=1.0)
        running_threads.clear()

def sync_tasks_with_db():
    """Polls database task_state and starts/stops worker threads to match desired state."""
    states = database.get_all_task_states()
    
    # 1. Standard Configured Channels (tour, nz, gaatha)
    for key, ch in channel_runner.CHANNELS.items():
        ch_state = states.get(key, {})
        if ch_state.get('is_running'):
            ch.set_interval(ch_state.get('interval', ch.default_interval))
            ch.stop_event.clear()
            start_module_thread(key, ch.run)
        else:
            if key in running_threads:
                stop_module_thread(key, ch.stop)

    # 4. Instagram Sync
    insta_state = states.get('insta', {})
    if insta_state.get('is_running'):
        interval = insta_state.get('interval', config.INSTA_INTERVAL)
        insta_suite.set_interval(interval)
        insta_phoenix.set_interval(interval)
        insta_suite.stop_event.clear()
        insta_phoenix.stop_event.clear()
        start_module_thread('insta_suite', insta_suite.run)
        start_module_thread('insta_phoenix', insta_phoenix.run)
    else:
        if 'insta_suite' in running_threads or 'insta_phoenix' in running_threads:
            insta_suite.stop()
            insta_phoenix.stop()
            with threads_lock:
                th1 = running_threads.pop('insta_suite', None)
                th2 = running_threads.pop('insta_phoenix', None)
                if th1 and th1.is_alive(): th1.join(timeout=1.0)
                if th2 and th2.is_alive(): th2.join(timeout=1.0)

def process_due_scheduled_posts(worker_id):
    """Claims and executes due scheduled posts using atomic distributed locks."""
    if not config.is_publishing_enabled():
        logger.info("🛡️ [SAFETY] Scheduled post claiming paused: POSTPILOT_PUBLISHING_ENABLED=0.")
        return []
    try:
        due_posts = database.claim_due_scheduled_posts(worker_id, limit=5)
        for sp in due_posts:
            p_type = sp['post_type']
            msg = sp.get('message') or ''
            img = sp.get('image_filename') or ''
            ch = channel_runner.CHANNELS.get(p_type)
            if not ch:
                logger.error(f"Cannot publish scheduled post {sp['id']}: channel '{p_type}' is not configured.")
                database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message=f"Channel {p_type} not configured")
                continue

            logger.info(f"Executing scheduled post #{sp['id']} on channel '{p_type}'...")
            try:
                page_id = ch.get_page_id()
                token = facebook_api.get_access_token(channel_key=p_type)

                if not token:
                    logger.warning(f"Publishing simulated/skipped for scheduled post #{sp['id']}: Meta token not configured.")
                    database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message="Meta Access Token not configured")
                    continue

                res = posting_utils.post_on_facebook(
                    message=msg,
                    image_filename=img,
                    page_id=page_id,
                    access_token=token,
                    ig_user_id=ch.ig_user_id,
                    channel_key=p_type
                )
                success = bool(res)
                if success:
                    database.complete_scheduled_post(sp['id'], worker_id, success=True)
                    logger.info(f"Successfully published scheduled post #{sp['id']} on channel '{p_type}'.")
                else:
                    database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message="Facebook publishing returned failure")
                    logger.warning(f"Failed to publish scheduled post #{sp['id']} on channel '{p_type}'.")
            except Exception as e:
                safe_e = facebook_api.sanitize_log_message(str(e))
                logger.error(f"Exception publishing scheduled post #{sp['id']}: {safe_e}")
                database.complete_scheduled_post(sp['id'], worker_id, success=False, error_message=safe_e)
    except Exception as e:
        logger.error(f"Error processing due scheduled posts: {facebook_api.sanitize_log_message(str(e))}")

def run_worker_loop():
    logger.info(f"PostPilot worker daemon initializing (ID: {WORKER_ID})...")
    database.init_db()
    
    while not shutdown_event.is_set():
        try:
            # Enforce single active worker via database lease (15-second TTL)
            has_lease = database.acquire_worker_lease(WORKER_ID, lease_name='scheduler', ttl_seconds=15)
            if has_lease:
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
