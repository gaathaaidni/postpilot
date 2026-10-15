"""
nexora_by_phoenix_international.py - Compatibility Wrapper
Delegates to the unified channel_runner module for 'nz' (visa) channel orchestration.
Maintains 100% backward compatibility for existing imports and tests.
"""
import channel_runner

_channel = channel_runner.get_channel('nz')

# Expose backward-compatible module attributes
stop_event = _channel.stop_event
POST_TYPE = _channel.post_type

def __getattr__(name):
    if name == 'PAGE_ID':
        return _channel.get_page_id()
    if name == 'current_interval':
        return _channel.current_interval
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def load_posts():
    return _channel.load_posts()

def set_status_callback(callback):
    _channel.set_status_callback(callback)

def set_interval(interval):
    _channel.set_interval(interval)

def post_on_facebook(message, image_filename):
    return _channel.post_on_facebook(message, image_filename)

def run_nexora_by_phoenix():
    _channel.run()

def stop_nexora_by_phoenix():
    _channel.stop()

