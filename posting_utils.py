import os
import json
import random
import time
import facebook_api
import insta

def load_posts(filepath):
    """Safely load posts from a JSON file."""
    if not os.path.exists(filepath):
        print(f"⚠️ Posts file not found: {filepath}")
        return []
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"❌ Error loading posts from {filepath}: {e}")
        return []

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
    posts = load_posts(posts_file)
    if not posts:
        if status_callback:
            status_callback(callback_key, False, "Idle (No posts found)", None)
        return

    random.shuffle(posts)
    post_count = 0
    while not stop_event.is_set():
        for post in posts:
            if stop_event.is_set(): break
            post_count += 1
            msg = post.get('message', '')
            summary = f"{msg[:50]}..." if len(msg) > 50 else (msg or 'No message')
            
            if status_callback:
                status_callback(callback_key, True, f"Posting... (Post #{post_count})", summary)
            
            success = post_on_facebook(msg, post.get("image_filename", ""), page_id, access_token)
            
            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback(callback_key, True, status, None)
            
            # Responsive sleep logic
            wait_until = time.time() + get_interval_func()
            while time.time() < wait_until and not stop_event.is_set():
                time.sleep(1)