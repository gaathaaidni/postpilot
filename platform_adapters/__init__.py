"""
PostPilot Platform Adapters Package
Standardized adapters for Facebook, Instagram, LinkedIn, and WhatsApp Business.
"""
from platform_adapters.base import BasePlatformAdapter, BaseMessagingAdapter
from platform_adapters.facebook import FacebookAdapter
from platform_adapters.instagram import InstagramAdapter
from platform_adapters.linkedin import LinkedInAdapter
from platform_adapters.whatsapp import WhatsAppCloudAdapter
from platform_adapters.registry import PlatformRegistry, CANONICAL_PLATFORMS, LEGACY_CHANNELS, ALL_PLATFORMS

__all__ = [
    'BasePlatformAdapter',
    'BaseMessagingAdapter',
    'FacebookAdapter',
    'InstagramAdapter',
    'LinkedInAdapter',
    'WhatsAppCloudAdapter',
    'PlatformRegistry',
    'CANONICAL_PLATFORMS',
    'LEGACY_CHANNELS',
    'ALL_PLATFORMS'
]
