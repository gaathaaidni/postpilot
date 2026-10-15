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
        default_interval: int,
        token_env_keys: tuple = (),
        insta_id_env_keys: tuple = (),
        default_insta_id: str = ""
    ):
        self.key = key
        self.display_name = display_name
        self.post_type = post_type
        self.page_id_env_keys = page_id_env_keys
        self.default_page_id = default_page_id
        self.default_interval = default_interval
        self.token_env_keys = token_env_keys
        self.insta_id_env_keys = insta_id_env_keys
        self.default_insta_id = default_insta_id
        
        self.stop_event = threading.Event()
        self.status_callback: Optional[Callable] = None
        self.current_interval = default_interval

    def get_page_id(self) -> str:
        """
        Resolves the Facebook Page ID from environment variables or configuration defaults.
        Validates that the resolved Page ID consists of valid numeric digits.
        Raises ValueError if missing, empty, or non-numeric.
        """
        for env_key in self.page_id_env_keys:
            val = os.getenv(env_key)
            if val and val.strip():
                resolved = val.strip()
                if not resolved.isdigit():
                    raise ValueError(
                        f"Invalid Facebook Page ID for channel '{self.key}' from {env_key}: '{resolved}'. "
                        f"Page IDs must consist of numeric digits."
                    )
                return resolved

        if self.default_page_id and str(self.default_page_id).strip():
            resolved = str(self.default_page_id).strip()
            if not resolved.isdigit():
                raise ValueError(
                    f"Invalid default Facebook Page ID for channel '{self.key}': '{resolved}'. "
                    f"Page IDs must consist of numeric digits."
                )
            return resolved

        raise ValueError(
            f"Missing Facebook Page ID configuration for channel '{self.key}'. "
            f"Set one of {self.page_id_env_keys} in .env or environment."
        )

    def get_access_token(self) -> Optional[str]:
        """
        Resolves the access token for this specific channel.
        Priority:
        1. Channel-specific environment token keys
        2. Direct Page ID token key (FB_PAGE_TOKEN_{page_id})
        3. Global FB_ACCESS_TOKEN or FB_TOKEN
        """
        for env_key in self.token_env_keys:
            val = os.getenv(env_key)
            if val and val.strip():
                return val.strip()

        try:
            pid = self.get_page_id()
            pid_val = os.getenv(f"FB_PAGE_TOKEN_{pid}")
            if pid_val and pid_val.strip():
                return pid_val.strip()
        except Exception:
            pass

        return facebook_api.get_access_token(channel_key=self.key)

    def get_insta_id(self) -> Optional[str]:
        """Resolves the linked Instagram Business Account ID for this channel, if configured."""
        for env_key in self.insta_id_env_keys:
            val = os.getenv(env_key)
            if val and val.strip():
                return val.strip()
        if self.default_insta_id and str(self.default_insta_id).strip():
            return str(self.default_insta_id).strip()
        return None

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
        token = self.get_access_token()
        page_id = self.get_page_id()
        ig_id = self.get_insta_id()
        return posting_utils.post_on_facebook(
            message, image_filename, page_id, token, ig_user_id=ig_id, channel_key=self.key
        )

    def run(self):
        """Executes the standard posting loop for this channel with pre-flight configuration validation."""
        try:
            token = self.get_access_token()
            if not token:
                msg = f"Configuration Error: Missing access token for channel '{self.key}'"
                logger.warning(f"Cannot start channel runner loop '{self.key}': {msg}")
                if self.status_callback:
                    self.status_callback(self.key, False, msg, None)
                else:
                    import database
                    database.set_task_state(self.key, is_running=False, status=msg)
                return

            page_id = self.get_page_id()
        except Exception as e:
            msg = f"Configuration Error: {e}"
            logger.error(f"Cannot start channel runner loop '{self.key}': {msg}")
            if self.status_callback:
                self.status_callback(self.key, False, msg, None)
            else:
                import database
                database.set_task_state(self.key, is_running=False, status=msg)
            return

        logger.info(f"Starting channel runner loop: {self.display_name} (key={self.key}, page_id={page_id})")
        ig_id = self.get_insta_id()
        posting_utils.run_posting_loop(
            stop_event=self.stop_event,
            status_callback=self.status_callback,
            get_interval_func=lambda: self.current_interval,
            callback_key=self.key,
            post_type=self.post_type,
            page_id=page_id,
            access_token=token,
            ig_user_id=ig_id,
            channel_key=self.key
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
        page_id_env_keys=('FB_PAGE_ID_SUITE', 'FB_PAGE_ID_NEXORA_SUITE', 'TOUR_PAGE_ID'),
        default_page_id=config.FB_PAGE_ID_SUITE,
        default_interval=config.TOUR_INTERVAL,
        token_env_keys=('FB_PAGE_TOKEN_TOUR', 'FB_PAGE_TOKEN_SUITE', 'FB_ACCESS_TOKEN_TOUR', 'FB_ACCESS_TOKEN_SUITE', 'FB_PAGE_TOKEN_NEXORA_SUITE'),
        insta_id_env_keys=('INSTA_ID_SUITE',),
        default_insta_id=config.INSTA_ID_SUITE
    ),
    'nz': Channel(
        key='nz',
        display_name='Nexora Phoenix (Visa)',
        post_type='nz',
        page_id_env_keys=('FB_PAGE_ID_PHOENIX', 'FB_PAGE_ID_NEXORA_BY_PHOENIX', 'VISA_PAGE_ID'),
        default_page_id=config.FB_PAGE_ID_PHOENIX,
        default_interval=config.VISA_INTERVAL,
        token_env_keys=('FB_PAGE_TOKEN_NZ', 'FB_PAGE_TOKEN_PHOENIX', 'FB_ACCESS_TOKEN_NZ', 'FB_ACCESS_TOKEN_PHOENIX', 'FB_PAGE_TOKEN_NEXORA_BY_PHOENIX'),
        insta_id_env_keys=('INSTA_ID_PHOENIX',),
        default_insta_id=config.INSTA_ID_PHOENIX
    ),
    'gaatha': Channel(
        key='gaatha',
        display_name='Gaatha AI',
        post_type='gaatha',
        page_id_env_keys=('FB_PAGE_ID_GAATHA_AI', 'FB_PAGE_ID_GAATHA'),
        default_page_id=config.FB_PAGE_ID_GAATHA_AI,
        default_interval=config.GAATHA_INTERVAL,
        token_env_keys=('FB_PAGE_TOKEN_GAATHA', 'FB_PAGE_TOKEN_GAATHA_AI', 'FB_ACCESS_TOKEN_GAATHA', 'FB_ACCESS_TOKEN_GAATHA_AI'),
        insta_id_env_keys=('INSTA_ID_GAATHA',),
        default_insta_id=""
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

def validate_channel_routing() -> Dict[str, str]:
    """
    Validates routing across all configured channels.
    Ensures:
    1. Every channel resolves to a valid numeric Page ID.
    2. No two channels resolve to the same Page ID (cross-channel collision prevention).
    Returns mapping of channel key to resolved Page ID.
    """
    resolved_mapping = {}
    seen_ids = {}
    for key, ch in CHANNELS.items():
        pid = ch.get_page_id()
        if not pid or not pid.isdigit():
            raise ValueError(f"Channel '{key}' resolved to invalid Page ID: '{pid}'")
        if pid in seen_ids:
            conflicting_key = seen_ids[pid]
            raise ValueError(
                f"Cross-channel routing conflict: Channels '{key}' and '{conflicting_key}' "
                f"both resolve to the same Facebook Page ID '{pid}'."
            )
        seen_ids[pid] = key
        resolved_mapping[key] = pid
    return resolved_mapping
