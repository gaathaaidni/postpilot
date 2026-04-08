import os
import random
import sqlite3
import time
import facebook_api
import insta

DB_PATH = os.path.join(os.path.dirname(__file__), "posts.db")

def load_posts(post_type):
    """Safely load posts from SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        posts = conn.execute(
            "SELECT id, message, image_filename, last_posted_at FROM posts WHERE post_type = ? ORDER BY last_posted_at ASC, id ASC",
            (post_type,)).fetchall()
        conn.close()
        return [dict(p) for p in posts]
    except Exception as e:
        print(f"❌ Error loading posts for {post_type}: {e}")
        return []

def update_last_posted_timestamp(post_id):
    """Updates the last_posted_at timestamp for a specific post in the SQLite database."""
    try:
        # Use a context manager for the connection to ensure it closes properly
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE posts SET last_posted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (post_id,)
            )
            conn.commit()
    except Exception as e:
        print(f"❌ Error updating last_posted_at for post {post_id}: {e}")

def post_on_facebook(message, image_filename, page_id, access_token, image_folder="images"):
    """Shared logic for posting an image to a Facebook page and cross-posting to Instagram."""
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

def run_posting_loop(stop_event, status_callback, get_interval_func, callback_key, posts_file, page_id, access_token):
    """Standardized background loop for Nexora modules."""
    post_count = 0
    while not stop_event.is_set():
        posts = load_posts(posts_file)
        if not posts:
            if status_callback:
                status_callback(callback_key, False, "Idle (No posts found)", None)
            time.sleep(60)
            continue

        for post in posts:
            if stop_event.is_set(): break
            post_count += 1
            msg = post.get('message', '')
            summary = f"{msg[:50]}..." if len(msg) > 50 else (msg or 'No message')
            
            if status_callback:
                status_callback(callback_key, True, f"Posting... (Post #{post_count})", summary)
            
            success = post_on_facebook(msg, post.get("image_filename", ""), page_id, access_token)
            
            if success:
                # Record the successful post timestamp
                update_last_posted_timestamp(post.get('id'))

            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback(callback_key, True, status, None)
            
            # Responsive sleep logic
            wait_until = time.time() + get_interval_func()
            while time.time() < wait_until and not stop_event.is_set():
                time.sleep(1)