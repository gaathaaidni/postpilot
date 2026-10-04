"""
gaatha_loop.py - Compatibility Wrapper
Delegates to the unified channel_runner module for 'gaatha' channel orchestration.
Maintains 100% backward compatibility for existing imports and tests.
"""
import channel_runner

_channel = channel_runner.get_channel('gaatha')

# Expose backward-compatible module attributes
stop_event = _channel.stop_event
PAGE_ID = _channel.get_page_id()
POST_TYPE = _channel.post_type

@property
def current_interval():
    return _channel.current_interval

def load_posts():
    return _channel.load_posts()

def set_status_callback(callback):
    _channel.set_status_callback(callback)

def set_interval(interval):
    _channel.set_interval(interval)

def post_to_facebook(message, image_filename):
    return _channel.post_on_facebook(message, image_filename)

def post_on_facebook(message, image_filename):
    return _channel.post_on_facebook(message, image_filename)

def run_gaatha_loop():
    _channel.run()

def stop_gaatha_loop():
    _channel.stop()