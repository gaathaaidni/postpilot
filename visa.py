# nz_thread.py
import requests, time, random, os, json
from threading import Event

stop_event = Event()
status_callback = None
current_interval = 30 * 60  # Default to 30 minutes

ACCESS_TOKEN = "EAAT3Q4oZCLo0BQrLKpgjZBdzs7u6ZBPB6YbGuHpQtcLCBCxarH7YOaphe4mQFkTvklDiQFzKppMwmfIZB3Kj61OLwLquw19eZAAatKoXSdT8WpXedmqrgo3kApwLIhd3varkTFyVR2V3SdYnEvFeKKZAZC9tMdWjlbJZBnnimryyclki49nZBhkTldTK4iIOklAZDZD"
PAGE_ID = "954901604381882"  # Nexora by Phoenix International page
IMAGE_FOLDER = "images"
FB_API_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTS_FILE = "posts/visa_posts.json"

def load_posts():
    with open(POSTS_FILE, 'r') as f:
        return json.load(f)

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
        return

    with open(path, 'rb') as img:
        files = {'source': (image_filename, img, 'image/jpeg')}
        data = {"message": message, "access_token": ACCESS_TOKEN}
        res = requests.post(FB_API_URL, files=files, data=data).json()
        success = "id" in res
        status = "✅ Posted" if success else "❌ Failed"
        print(status + ":", res)
        return success

def run_nz():
    """Run Nexora Investments posting"""
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
                status_callback('nz', True, f"Posting... (Post #{post_count})", current_post_summary)
            success = post_on_facebook(post["message"], post["image_filename"])
            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback('nz', True, status, None)
            time.sleep(current_interval)

def stop_nz():
    """Stop Nexora Investments posting"""
    stop_event.set()
