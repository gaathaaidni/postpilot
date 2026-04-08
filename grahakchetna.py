# grahakchetna.py
import time
import requests
import random
import os
import json
from threading import Event
import facebook_api
import grahak_uploader # Still used for higher-level upload functions

stop_event = Event()
status_callback = None
current_interval = 30 * 60  # Default to 30 minutes

ACCESS_TOKEN = facebook_api.get_access_token()
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or os.getenv('GRAHAK_PAGE_ID') or '374211199112915'  # Grahak Chetna page
IMAGE_FOLDER = "images"
FB_API_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTS_FILE = "posts/grahakchetna_posts.json"  # duplicate of visa posts unless otherwise changed

def load_posts():
    if not os.path.exists(POSTS_FILE):
        print(f"⚠️ Posts file not found: {POSTS_FILE}")
        return []
    try:
        with open(POSTS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Error decoding JSON from {POSTS_FILE}")
        return []

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

def set_interval(interval):
    """Set posting interval in seconds"""
    global current_interval
    current_interval = interval

def post_on_facebook(message, image_filename):
    path = os.path.join(IMAGE_FOLDER, image_filename)
    if not os.path.exists(path):
        print(f"Image not found: {path}")
        return False

    # Determine media type
    is_video = image_filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
    
    # Get specific page token for this module's PAGE_ID
    page_token = facebook_api.get_page_token(ACCESS_TOKEN, PAGE_ID)
    
    if not page_token:
        print("❌ FB Post Failed: Could not acquire Page Token")
        return False
    
    if is_video:
        res = grahak_uploader.upload_fb_video(path, message, True, page_token)
    else:
        res = grahak_uploader.upload_fb_photo(path, message, True, page_token)
        
    if 'id' not in res:
        print(f"❌ FB Post Failed: {res}")
        return False
        
    fb_id = res['id']
    print(f"✅ Posted to FB: {fb_id}")
    
    # Sync to Instagram
    media_url = grahak_uploader.get_public_url(fb_id, is_video, page_token)
    if media_url:
        # Post as Reel if video, Feed if image
        grahak_uploader.publish_instagram(media_url, message, is_video, is_video, page_token)
        
    return {"photo_id": fb_id, "response": res}

def run_grahakchetna():
    """Run Grahak Chetna posting"""
    posts = load_posts()
    if not posts:
        if status_callback:
            status_callback('grahak', False, "Idle (No posts found)", None)
        return

    random.shuffle(posts)
    post_count = 0
    while not stop_event.is_set():
        for post in posts:
            if stop_event.is_set():
                break
            post_count += 1
            current_post_summary = f"{post['message'][:50]}..." if len(post.get('message', '')) > 50 else post.get('message', 'No message')
            if status_callback:
                status_callback('grahak', True, f"Posting... (Post #{post_count})", current_post_summary)
            success = post_on_facebook(post["message"], post["image_filename"])
            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback('grahak', True, status, None)
            time.sleep(current_interval)

def stop_grahakchetna():
    """Stop Grahak Chetna posting"""
    stop_event.set()
