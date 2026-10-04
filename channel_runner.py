"""
PostPilot Channel Runner Architecture
Centralized, configuration-driven orchestration for social publishing channels.

Eliminates duplicate wrapper code across posting loops while delegating all:
- Meta API communication to facebook_api.py
- Posting workflows and duplicate checks to posting_utils.py
- Task persistence and state tracking to database.py
"""
import os
import threading
import logging
from typing import Dict, Optional, Callable, List

import config
import facebook_api
import posting_utils

logger = logging.getLogger(__name__)

class Channel:
    """Represents a discrete posting channel (e.g., Facebook Page + cross-posting target)."""
    
    def __init__(
        self,
        key: str,
        display_name: str,
        post_type: str,
        page_id_env_keys: tuple,
        default_page_id: str,
        default_interval: int
    ):
        self.key = key
        self.display_name = display_name
        self.post_type = post_type
        self.page_id_env_keys = page_id_env_keys
        self.default_page_id = default_page_id
        self.default_interval = default_interval
        
        self.stop_event = threading.Event()
        self.status_callback: Optional[Callable] = None
        self.current_interval = default_interval

    def get_page_id(self) -> str:
        """Resolves the Facebook Page ID from environment variables or configuration defaults."""
        for env_key in self.page_id_env_keys:
            val = os.getenv(env_key)
            if val:
                return val.strip()
        return self.default_page_id

    def load_posts(self) -> list:
        """Fetches pending/available posts from the database for this channel's post type."""
        return posting_utils.load_posts(self.post_type)

    def set_status_callback(self, callback: Optional[Callable]):
        """Sets callback for task status updates."""
        self.status_callback = callback

    def set_interval(self, interval: int):
        """Sets posting interval in seconds."""
        if interval and interval > 0:
            self.current_interval = int(interval)

    def post_on_facebook(self, message: str, image_filename: str):
        """Dispatches an immediate single-post execution for this channel."""
        token = facebook_api.get_access_token()
        page_id = self.get_page_id()
        return posting_utils.post_on_facebook(message, image_filename, page_id, token)

    def run(self):
        """Executes the standard posting loop for this channel."""
        token = facebook_api.get_access_token()
        page_id = self.get_page_id()
        logger.info(f"Starting channel runner loop: {self.display_name} (key={self.key}, page_id={page_id})")
        posting_utils.run_posting_loop(
            stop_event=self.stop_event,
            status_callback=self.status_callback,
            get_interval_func=lambda: self.current_interval,
            callback_key=self.key,
            post_type=self.post_type,
            page_id=page_id,
            access_token=token
        )

    def stop(self):
        """Signals the channel's running loop to halt gracefully."""
        logger.info(f"Stopping channel runner loop: {self.display_name} (key={self.key})")
        self.stop_event.set()

# --- Canonical Channel Definitions ---
CHANNELS: Dict[str, Channel] = {
    'tour': Channel(
        key='tour',
        display_name='Nexora Suite (Tour)',
        post_type='tour',
        page_id_env_keys=('FB_PAGE_ID_SUITE', 'FB_PAGE_ID_NEXORA_SUITE'),
        default_page_id=config.FB_PAGE_ID_SUITE,
        default_interval=config.TOUR_INTERVAL
    ),
    'nz': Channel(
        key='nz',
        display_name='Nexora Phoenix (Visa)',
        post_type='nz',
        page_id_env_keys=('FB_PAGE_ID_PHOENIX', 'FB_PAGE_ID_NEXORA_BY_PHOENIX'),
        default_page_id=config.FB_PAGE_ID_PHOENIX,
        default_interval=config.VISA_INTERVAL
    ),
    'gaatha': Channel(
        key='gaatha',
        display_name='Gaatha AI',
        post_type='gaatha',
        page_id_env_keys=('FB_PAGE_ID_GAATHA_AI', 'FB_PAGE_ID_GAATHA'),
        default_page_id=config.FB_PAGE_ID_GAATHA_AI,
        default_interval=config.GAATHA_INTERVAL
    ),
}

def get_channel(key: str) -> Channel:
    """Retrieves a registered channel by its unique key."""
    if key not in CHANNELS:
        raise KeyError(f"Unknown channel key: '{key}'. Available: {list(CHANNELS.keys())}")
    return CHANNELS[key]

def list_channels() -> List[Dict[str, str]]:
    """Returns metadata for all configured channels."""
    return [
        {
            'key': ch.key,
            'name': ch.display_name,
            'post_type': ch.post_type,
            'page_id': ch.get_page_id(),
            'default_interval': ch.default_interval,
        }
        for ch in CHANNELS.values()
    ]
