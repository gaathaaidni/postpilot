import requests, time, random, os, json
from threading import Event
import insta

stop_event = Event()
status_callback = None
current_interval = 30 * 60  # Default to 30 minutes

def get_access_token():
    """Read access token from token.txt file"""
    try:
        with open('token.txt', 'r') as f:
            return f.read().strip()
    except:
        return None

ACCESS_TOKEN = get_access_token()
PAGE_ID = "967550829768297"  # Nexora Suite page
IMAGE_FOLDER = "images"
FB_API_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTS_FILE = "posts/tour_posts.json"

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

    try:
        # Upload the image file directly to Facebook (multipart upload)
        page_token = get_page_token()
        if not page_token:
            print("❌ Failed: Could not get page token")
            return False

        with open(path, 'rb') as img:
            files = {'source': (image_filename, img, 'image/jpeg')}
            data = {"caption": message, "access_token": page_token}
            res = requests.post(FB_API_URL, files=files, data=data).json()

        if 'error' in res:
            error_msg = res['error'].get('message', 'Unknown error')
            print(f"❌ Failed: {error_msg}")
            return False

        photo_id = res.get('id')
        image_url = None
        if photo_id:
            info = requests.get(f"https://graph.facebook.com/v19.0/{photo_id}?fields=images&access_token={page_token}").json()
            images = info.get('images') or []
            if images:
                image_url = images[0].get('source')

        print("✅ Posted:", res)

        # Cross-post to Instagram using the Facebook image URL if available
        if image_url:
            try:
                insta.post_to_instagram(image_url, message)
            except Exception:
                pass

        return {"photo_id": photo_id, "image_url": image_url, "response": res}
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def run_nexora_suite():
    """Run Nexora Suite posting"""
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
                # use a descriptive key for callbacks
                status_callback('nexora_suite', True, f"Posting... (Post #{post_count})", current_post_summary)
            success = post_on_facebook(post["message"], post["image_filename"])
            if status_callback:
                status = "Posted" if success else "Failed"
                status_callback('nexora_suite', True, status, None)
            time.sleep(current_interval)

def stop_nexora_suite():
    """Stop Nexora Suite posting"""
    stop_event.set()
