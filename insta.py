# insta_thread.py
import time, json, os
import threading
import facebook_api

status_callback = None

POSTED_FILE = 'posted.txt'

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

class InstaSync:
    def __init__(self, page_id, ig_user_id, name="Insta"):
        self.page_id = page_id
        self.ig_user_id = ig_user_id
        self.name = name
        self.stop_event = threading.Event()
        self.interval = 3 * 60
        self.access_token = facebook_api.get_access_token()

    def set_interval(self, seconds):
        self.interval = seconds

    def stop(self):
        self.stop_event.set()

    def get_recent_facebook_posts(self):
        url = f"https://graph.facebook.com/v19.0/{self.page_id}/posts"
        params = {
            'fields': 'id,message,attachments{media,type}',
            'access_token': self.access_token
        }
        res = facebook_api._request_with_retry("GET", url, params=params)
        return res.get('data', [])

def get_posted_ids():
    try:
        with open(POSTED_FILE, 'r') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_posted_id(post_id):
    with open(POSTED_FILE, 'a') as f:
        f.write(post_id + '\n')

def post_to_instagram(image_url, caption, ig_user_id=None, access_token=None):
    """Top-level function for Instagram posting, used by other modules."""
    if not ig_user_id:
        ig_user_id = os.getenv('INSTA_ID_GRAHAK_CHETNA')
    if not access_token:
        access_token = facebook_api.get_access_token()
        
    if not ig_user_id or not access_token:
        return False

    create_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
    publish_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"

    payload = {'image_url': image_url, 'caption': caption, 'access_token': access_token}
    res = facebook_api._request_with_retry("POST", create_url, data=payload)
    if 'id' not in res:
        return False

    time.sleep(5) # Brief wait for container processing
    pub_res = facebook_api._request_with_retry("POST", publish_url, data={'creation_id': res['id'], 'access_token': access_token})
    return 'id' in pub_res

    def run(self):
        post_count = 0
        while not self.stop_event.is_set():
            try:
                posts = self.get_recent_facebook_posts()
                posted_ids = get_posted_ids()

                for post in posts:
                    if self.stop_event.is_set(): break
                    post_id = post['id']
                    if post_id in posted_ids: continue

                    attachments = post.get('attachments', {}).get('data', [{}])[0]
                    media = attachments.get('media', {})
                    if attachments.get('type') != 'photo': continue

                    image_url = media.get('image', {}).get('src')
                    if image_url and post_to_instagram(image_url, post.get('message', ''), self.ig_user_id, self.access_token):
                        post_count += 1
                        summary = f"{post.get('message', '')[:30]}..."
                        if status_callback:
                            status_callback(self.name, True, f"Synced #{post_count}", summary)
                        save_posted_id(post_id)

                if status_callback:
                    status_callback(self.name, True, 'Checking...', None)
                time.sleep(self.interval)
            except Exception as e:
                print(f"❌ Error in {self.name} sync: {e}")
                time.sleep(60)
