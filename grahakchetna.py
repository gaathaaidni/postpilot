# nz_thread.py
import time
import requests
import random
import os
import json
from threading import Event
import insta
import grahak_uploader

stop_event = Event()
status_callback = None
current_interval = 30 * 60  # Default to 30 minutes

def get_access_token():
    """Read user access token from env, then token.txt fallback."""
    return os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN') or _read_token_file()


def _read_token_file():
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except:
        return None

ACCESS_TOKEN = get_access_token()
PAGE_ID = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA') or os.getenv('GRAHAK_PAGE_ID') or '374211199112915'  # Grahak Chetna page
IMAGE_FOLDER = "images"
FB_API_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTS_FILE = "posts/grahakchetna_posts.json"  # duplicate of visa posts unless otherwise changed

def get_page_token():
    """Fetch page token from user token"""
    try:
        url = f"https://graph.facebook.com/v19.0/me/accounts?access_token={ACCESS_TOKEN}"
        res = requests.get(url).json()
        if 'data' in res:
            for page in res['data']:
                if page.get('id') == PAGE_ID:
                    return page.get('access_token')
        return None
    except:
        return None

def load_posts():
    with open(POSTS_FILE, 'r') as f:
        return json.load(f)


def get_static_base_url():
    """Base URL where images are served. Override with env STATIC_BASE_URL."""
    return os.environ.get('STATIC_BASE_URL', 'http://localhost:5000').rstrip('/')


def get_image_url(filename):
    return f"{get_static_base_url()}/images/{filename}"

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
    
    # Reuse robust logic from grahak_uploader
    token = get_access_token()
    page_token = grahak_uploader.get_page_token(token)
    
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
    random.shuffle(posts)
    post_count = 0
    while not stop_event.is_set():
        for post in posts:
            if stop_event.is_set():
                break
            post_count += 1
            current_post_summary = f"{post['message'][:50]}..." if len(post.get('message', '')) > 50 else post.get('message', 'No message')
            if status_callback:
                status_callback('grahakchetna', True, f"Posting... (Post #{post_count})", current_post_summary)
            success = post_on_facebook(post["message"], post["image_filename"])
            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback('grahakchetna', True, status, None)
            time.sleep(current_interval)

def stop_grahakchetna():
    """Stop Grahak Chetna posting"""
    stop_event.set()
