# insta.py
import time
import os
import threading
import facebook_api
import database

status_callback = None

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

def is_post_already_synced(post_id):
    """Checks database if a post ID has already been synced to Instagram."""
    return database.is_post_synced(str(post_id), 'instagram')

def mark_post_as_synced(post_id):
    """Records post ID in database as synced to Instagram."""
    database.mark_post_synced(str(post_id), 'instagram')

def post_to_instagram(image_url, caption, ig_user_id=None, access_token=None):
    """Top-level function for Instagram posting, used by modules."""
    if not ig_user_id:
        ig_user_id = os.getenv('INSTA_ID_SUITE') or os.getenv('INSTA_ID_PHOENIX')
    if not access_token:
        access_token = facebook_api.get_access_token()
        
    if not ig_user_id or not access_token:
        return False

    create_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
    publish_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"

    payload = {'image_url': image_url, 'caption': caption, 'access_token': access_token}
    res = facebook_api._request_with_retry("POST", create_url, data=payload)
    if not res or 'id' not in res:
        return False

    time.sleep(5)  # Brief wait for Instagram container processing
    pub_res = facebook_api._request_with_retry("POST", publish_url, data={'creation_id': res['id'], 'access_token': access_token})
    return 'id' in pub_res

class InstaSync:
    """Synchronizes Facebook posts to an Instagram business account."""
    def __init__(self, page_id, ig_user_id, name="Insta", *args, **kwargs):
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
            'access_token': self.access_token or facebook_api.get_access_token()
        }
        res = facebook_api._request_with_retry("GET", url, params=params)
        return res.get('data', [])

    def run(self):
        """Background loop to fetch new Facebook posts and cross-post to Instagram."""
        post_count = 0
        while not self.stop_event.is_set():
            try:
                posts = self.get_recent_facebook_posts()

                for post in posts:
                    if self.stop_event.is_set():
                        break
                    post_id = post.get('id')
                    if not post_id or is_post_already_synced(post_id):
                        continue

                    attachments = post.get('attachments', {}).get('data', [{}])[0]
                    media = attachments.get('media', {})
                    if attachments.get('type') != 'photo':
                        continue

                    image_url = media.get('image', {}).get('src')
                    if image_url and post_to_instagram(image_url, post.get('message', ''), self.ig_user_id, self.access_token):
                        post_count += 1
                        summary = f"{post.get('message', '')[:30]}..."
                        if status_callback:
                            status_callback(self.name, True, f"Synced #{post_count}", summary)
                        mark_post_as_synced(post_id)

                if self.stop_event.is_set():
                    break

                if status_callback:
                    status_callback(self.name, True, 'Checking...', None)

                # Responsive wait using stop_event
                if self.stop_event.wait(timeout=self.interval):
                    break
            except Exception as e:
                if status_callback:
                    status_callback(self.name, False, f"Error: {e}", None)
                if self.stop_event.wait(timeout=10):
                    break
