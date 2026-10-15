import os
import time
import logging
import facebook_api
import insta
import database
import config

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv'}

def load_posts(post_type):
    """Safely load posts from database layer."""
    try:
        return database.load_posts_by_type(post_type)
    except Exception as e:
        logger.error(f"❌ Error loading posts for {post_type}: {e}")
        return []

def update_last_posted_timestamp(post_id):
    """Updates the last_posted_at timestamp in the database."""
    try:
        database.update_last_posted_timestamp(post_id)
    except Exception as e:
        logger.error(f"❌ Error updating last_posted_at for post {post_id}: {e}")

def post_on_facebook(message, image_filename, page_id, access_token, image_folder=None, ig_user_id=None, channel_key=None):
    """
    Robust publishing logic supporting:
    - Text-only posts (to /{page_id}/feed)
    - Photo posts (to /{page_id}/photos)
    - Video posts (to /{page_id}/videos)
    - Channel-isolated Instagram cross-posting (strictly when ig_user_id is configured)
    """
    if not page_id:
        logger.error("❌ post_on_facebook called without a valid page_id.")
        return False

    has_media = bool(image_filename and str(image_filename).strip())

    # Pre-flight payload validation: text-only posts require non-empty message
    if not has_media and (not message or not str(message).strip()):
        logger.error("❌ Cannot publish text post: message content is empty.")
        return False

    try:
        page_token = facebook_api.get_page_token(access_token, page_id, channel_key=channel_key)
        if not page_token:
            logger.error(f"❌ Failed: Could not get page token for page {page_id}")
            return False

        if not image_folder:
            image_folder = str(config.UPLOAD_FOLDER)

        image_url = None
        photo_id = None
        res = None

        if has_media:
            clean_filename = str(image_filename).strip()
            path = os.path.join(image_folder, clean_filename)
            if not os.path.isfile(path):
                logger.error(f"❌ Media file not found or is a directory: {path}")
                return False

            ext = os.path.splitext(clean_filename)[1].lower()

            if ext in VIDEO_EXTENSIONS:
                # Video upload payload with appropriate MIME type
                mime_map = {
                    '.mp4': 'video/mp4',
                    '.mov': 'video/quicktime',
                    '.avi': 'video/x-msvideo',
                    '.mkv': 'video/x-matroska'
                }
                video_mime = mime_map.get(ext, 'video/mp4')
                api_url = f"{facebook_api.BASE_URL}/{page_id}/videos"
                with open(path, 'rb') as video_file:
                    files = {'source': (clean_filename, video_file, video_mime)}
                    data = {"description": message or '', "access_token": page_token}
                    res = facebook_api._request_with_retry("POST", api_url, files=files, data=data)
            else:
                # Photo upload payload
                api_url = f"{facebook_api.BASE_URL}/{page_id}/photos"
                photo_mime_map = {
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg'
                }
                mime = photo_mime_map.get(ext, 'image/jpeg')
                with open(path, 'rb') as img:
                    files = {'source': (clean_filename, img, mime)}
                    data = {"caption": message or '', "access_token": page_token}
                    res = facebook_api._request_with_retry("POST", api_url, files=files, data=data)
        else:
            # Text-only feed post payload
            api_url = f"{facebook_api.BASE_URL}/{page_id}/feed"
            data = {"message": message or '', "access_token": page_token}
            res = facebook_api._request_with_retry("POST", api_url, data=data)

        if not res or 'error' in res:
            err_msg = res.get('error', {}).get('message', 'Unknown error') if isinstance(res.get('error'), dict) else str(res.get('error'))
            logger.error(f"❌ Facebook API error for page {page_id}: {err_msg}")
            return False

        photo_id = res.get('id')
        logger.info(f"✅ Successfully published to Facebook page {page_id}: {photo_id}")

        # Resolve image URL if this was a photo post and Instagram cross-posting is enabled
        if has_media and photo_id and ig_user_id:
            ext = os.path.splitext(clean_filename)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                try:
                    info = facebook_api._request_with_retry(
                        "GET",
                        f"{facebook_api.BASE_URL}/{photo_id}?fields=images&access_token={page_token}"
                    )
                    images = info.get('images') or []
                    if images:
                        image_url = images[0].get('source')
                    if image_url:
                        insta.post_to_instagram(image_url, message, ig_user_id=ig_user_id, access_token=access_token)
                except Exception as e:
                    logger.warning(f"⚠️ Channel-specific Instagram cross-post warning: {e}")

        return {"photo_id": photo_id, "id": photo_id, "image_url": image_url, "response": res}
    except Exception as e:
        logger.error(f"❌ Exception in post_on_facebook: {e}")
        return False

def run_posting_loop(stop_event, status_callback, get_interval_func, callback_key, post_type, page_id, access_token, ig_user_id=None, channel_key=None):
    """Standardized background loop for posting modules with exception resilience."""
    post_count = 0
    resolved_channel = channel_key or callback_key
    while not stop_event.is_set():
        try:
            posts = load_posts(post_type)
            if not posts:
                if stop_event.is_set():
                    break
                if status_callback:
                    status_callback(callback_key, True, "Idle (No posts found)", None)
                else:
                    database.set_task_state(callback_key, is_running=True, status="Idle (No posts found)")
                if stop_event.wait(timeout=1.0):
                    break
                continue

            for post in posts:
                if stop_event.is_set():
                    break
                post_count += 1
                msg = post.get('message', '')
                summary = f"{msg[:50]}..." if len(msg) > 50 else (msg or 'No message')
                
                if status_callback:
                    status_callback(callback_key, True, f"Posting... (Post #{post_count})", summary)
                else:
                    database.set_task_state(callback_key, is_running=True, status=f"Posting... (Post #{post_count})", current_post_summary=summary)

                try:
                    result = post_on_facebook(
                        message=msg,
                        image_filename=post.get("image_filename", ""),
                        page_id=page_id,
                        access_token=access_token,
                        ig_user_id=ig_user_id,
                        channel_key=resolved_channel
                    )
                    success = bool(result)
                except Exception as post_err:
                    logger.error(f"Error publishing post {post.get('id')} on channel {callback_key}: {post_err}")
                    success = False
                
                if success:
                    update_last_posted_timestamp(post.get('id'))

                status = "Posted" if success else "Failed"
                if stop_event.is_set():
                    break
                if status_callback:
                    status_callback(callback_key, True, status, None)
                else:
                    database.set_task_state(callback_key, is_running=True, status=status)

                # Responsive wait using stop_event
                interval_val = get_interval_func()
                if not interval_val or interval_val <= 0:
                    interval_val = 1800
                if stop_event.wait(timeout=interval_val):
                    break

        except Exception as loop_err:
            logger.error(f"Unexpected error in posting loop for {callback_key}: {loop_err}")
            if status_callback:
                status_callback(callback_key, True, f"Error: {loop_err}", None)
            else:
                database.set_task_state(callback_key, is_running=True, status=f"Error: {loop_err}")
            # Prevent fast spin on persistent errors
            if stop_event.wait(timeout=5.0):
                break

    if status_callback:
        status_callback(callback_key, False, "Stopped", None)
    else:
        database.set_task_state(callback_key, is_running=False, status="Stopped")