import os
import time
import facebook_api
import insta
import database
import config

def load_posts(post_type):
    """Safely load posts from database layer."""
    try:
        return database.load_posts_by_type(post_type)
    except Exception as e:
        print(f"❌ Error loading posts for {post_type}: {e}")
        return []

def update_last_posted_timestamp(post_id):
    """Updates the last_posted_at timestamp in the database."""
    try:
        database.update_last_posted_timestamp(post_id)
    except Exception as e:
        print(f"❌ Error updating last_posted_at for post {post_id}: {e}")

def post_on_facebook(message, image_filename, page_id, access_token, image_folder=None):
    """Shared logic for posting an image to a Facebook page and cross-posting to Instagram."""
    if not image_folder:
        image_folder = str(config.UPLOAD_FOLDER)
        
    path = os.path.join(image_folder, image_filename)
    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    try:
        page_token = facebook_api.get_page_token(access_token, page_id)
        if not page_token:
            print(f"❌ Failed: Could not get page token for {page_id}")
            return False

        api_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        with open(path, 'rb') as img:
            files = {'source': (image_filename, img, 'image/jpeg')}
            data = {"caption": message, "access_token": page_token}
            res = facebook_api._request_with_retry("POST", api_url, files=files, data=data)

        if 'error' in res:
            error_msg = res['error'].get('message', 'Unknown error')
            print(f"❌ Facebook API error: {error_msg}")
            return False

        photo_id = res.get('id')
        image_url = None
        if photo_id:
            info = facebook_api._request_with_retry("GET", f"https://graph.facebook.com/v19.0/{photo_id}?fields=images&access_token={page_token}")
            images = info.get('images') or []
            if images:
                image_url = images[0].get('source')

        print(f"✅ Posted to FB ({page_id}): {photo_id}")

        if image_url:
            try:
                insta.post_to_instagram(image_url, message)
            except Exception as e:
                print(f"⚠️ Instagram cross-post failed: {e}")

        return {"photo_id": photo_id, "image_url": image_url, "response": res}
    except Exception as e:
        print(f"❌ Exception in post_on_facebook: {str(e)}")
        return False

def run_posting_loop(stop_event, status_callback, get_interval_func, callback_key, post_type, page_id, access_token):
    """Standardized background loop for posting modules."""
    post_count = 0
    while not stop_event.is_set():
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

            success = post_on_facebook(msg, post.get("image_filename", ""), page_id, access_token)
            
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
            if stop_event.wait(timeout=get_interval_func()):
                break

    if status_callback:
        status_callback(callback_key, False, "Stopped", None)
    else:
        database.set_task_state(callback_key, is_running=False, status="Stopped")