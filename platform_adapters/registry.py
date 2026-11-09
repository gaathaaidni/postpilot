"""
PostPilot Unified Platform Adapter Registry
Central registry and dispatcher for all canonical publishing and messaging platforms.

Canonical Platforms:
- facebook: Meta Graph API (Page feeds, photo/video publishing)
- instagram: Meta Graph API for Instagram Business (Containers, single/carousel media)
- linkedin: Modern LinkedIn REST Posts API (Dual-app multi-organization publishing)
- whatsapp: Meta Cloud API v19.0 (Business messaging, pre-approved templates)

Legacy channel keys ('tour', 'nz', 'gaatha') are mapped gracefully for backward compatibility.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from platform_adapters.base import BasePlatformAdapter, BaseMessagingAdapter
from platform_adapters.facebook import FacebookAdapter
from platform_adapters.instagram import InstagramAdapter
from platform_adapters.linkedin import LinkedInAdapter
from platform_adapters.whatsapp import WhatsAppCloudAdapter

logger = logging.getLogger(__name__)

CANONICAL_PLATFORMS = {'facebook', 'instagram', 'linkedin', 'whatsapp'}
RETIRED_LEGACY_CHANNELS = {'tour', 'nz', 'gaatha', 'insta'}
LEGACY_CHANNELS = RETIRED_LEGACY_CHANNELS
ALL_PLATFORMS = CANONICAL_PLATFORMS | RETIRED_LEGACY_CHANNELS


class PlatformRegistry:
    """Registry maintaining active platform adapter singletons and dispatch logic."""

    _adapters: Dict[str, BasePlatformAdapter] = {}
    _initialized: bool = False

    @classmethod
    def _initialize(cls):
        if cls._initialized:
            return
        cls._adapters = {
            'facebook': FacebookAdapter(),
            'instagram': InstagramAdapter(),
            'linkedin': LinkedInAdapter(),
            'whatsapp': WhatsAppCloudAdapter()
        }
        cls._initialized = True

    @classmethod
    def get_adapter(cls, platform_key: str) -> Optional[BasePlatformAdapter]:
        """
        Retrieves the platform adapter for a canonical platform key.
        Legacy channels ('tour', 'nz', 'gaatha', 'insta') return None because they are retired.
        """
        cls._initialize()
        if not platform_key:
            return None
        
        normalized = str(platform_key).strip().lower()
        if normalized == 'twitter':
            normalized = 'x'

        # Direct canonical match
        if normalized in cls._adapters:
            return cls._adapters[normalized]

        # Retired legacy channels have no active adapter
        return None

    @classmethod
    def is_canonical_platform(cls, platform_key: str) -> bool:
        """Returns True if platform_key is one of the 4 canonical platforms."""
        if not platform_key:
            return False
        return str(platform_key).strip().lower() in CANONICAL_PLATFORMS

    @classmethod
    def is_legacy_channel(cls, channel_key: str) -> bool:
        """Returns True if channel_key is a retired legacy channel."""
        if not channel_key:
            return False
        return str(channel_key).strip().lower() in RETIRED_LEGACY_CHANNELS

    @classmethod
    def list_supported_platforms(cls) -> List[Dict[str, Any]]:
        """Returns structured metadata for all supported canonical platforms."""
        cls._initialize()
        platforms_info = [
            {
                'key': 'facebook',
                'name': 'Facebook Pages',
                'type': 'social',
                'media_supported': ['image', 'video'],
                'text_only_allowed': True,
                'char_limit': 63206,
                'status': cls._adapters['facebook'].get_status()
            },
            {
                'key': 'instagram',
                'name': 'Instagram Business',
                'type': 'social',
                'media_supported': ['image', 'video'],
                'text_only_allowed': False,
                'char_limit': 2200,
                'max_hashtags': 30,
                'status': cls._adapters['instagram'].get_status()
            },
            {
                'key': 'linkedin',
                'name': 'LinkedIn Pages',
                'type': 'social',
                'media_supported': ['image'],
                'text_only_allowed': True,
                'char_limit': 3000,
                'status': cls._adapters['linkedin'].get_status()
            },
            {
                'key': 'whatsapp',
                'name': 'WhatsApp Business Cloud',
                'type': 'messaging',
                'media_supported': ['image', 'document', 'video'],
                'text_only_allowed': False,  # Broadcasts require approved templates
                'requires_opt_in': True,
                'status': cls._adapters['whatsapp'].get_status()
            }
        ]
        return platforms_info

    @classmethod
    def validate_content(cls, platform_key: str, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates message content and media against target platform rules."""
        adapter = cls.get_adapter(platform_key)
        if not adapter:
            return False, f"Unsupported platform: '{platform_key}'"
        return adapter.validate_content(content)

    @classmethod
    def dispatch(cls, scheduled_post: Dict[str, Any], worker_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Dispatches a scheduled post record through its designated platform adapter.
        Legacy channels are blocked from dispatch.
        Enforces content validation and returns a standardized dispatch result.
        """
        p_type = scheduled_post.get('post_type', '')
        if cls.is_legacy_channel(p_type):
            err = f"Legacy channel '{p_type}' is permanently retired and cannot be dispatched."
            logger.warning(err)
            return {
                'success': False,
                'platform': p_type,
                'error': err,
                'simulated': False,
                'is_retired_legacy': True
            }

        adapter = cls.get_adapter(p_type)
        if not adapter:
            err = f"No adapter registered for platform '{p_type}'"
            logger.error(err)
            return {
                'success': False,
                'platform': p_type,
                'error': err,
                'simulated': False
            }

        payload = {
            'message': scheduled_post.get('message', ''),
            'image_filename': scheduled_post.get('image_filename') or scheduled_post.get('media_path'),
            'brand_id': scheduled_post.get('brand_id'),
            'organization_id': scheduled_post.get('organization_id'),
            'scheduled_post_id': scheduled_post.get('id'),
            'recipient_phone': scheduled_post.get('recipient_phone') or scheduled_post.get('phone'),
            'template_name': scheduled_post.get('template_name')
        }

        # Content validation before execution
        valid, val_err = adapter.validate_content(payload)
        if not valid:
            logger.warning(f"Content validation failed for post #{scheduled_post.get('id')} on '{p_type}': {val_err}")
            return {
                'success': False,
                'platform': p_type,
                'error': f"Validation failed: {val_err}",
                'simulated': False
            }

        return adapter.publish(payload)
