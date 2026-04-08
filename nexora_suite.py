import os
from threading import Event
import posting_utils
import facebook_api

stop_event = Event()
status_callback = None
current_interval = 30 * 60  # Default to 30 minutes

ACCESS_TOKEN = facebook_api.get_access_token()
PAGE_ID = os.getenv('FB_PAGE_ID_NEXORA_SUITE', '967550829768297')  # Nexora Suite page
POST_TYPE = "tour"

def load_posts():
    return posting_utils.load_posts(POST_TYPE)

def set_status_callback(callback):
    """Set callback for status updates"""
    global status_callback
    status_callback = callback

def set_interval(interval):
    """Set posting interval in seconds"""
    global current_interval
    current_interval = interval

def post_on_facebook(message, image_filename):
    return posting_utils.post_on_facebook(message, image_filename, PAGE_ID, ACCESS_TOKEN)

def run_nexora_suite():
    """Run Nexora Suite posting"""
    posting_utils.run_posting_loop(
        stop_event=stop_event,
        status_callback=status_callback,
        get_interval_func=lambda: current_interval,
        callback_key='nexora_suite',
        posts_file=POST_TYPE,
        page_id=PAGE_ID,
        access_token=ACCESS_TOKEN
    )

def stop_nexora_suite():
    """Stop Nexora Suite posting"""
    stop_event.set()
