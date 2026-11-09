"""
PostPilot Unified Platform Adapter Architecture
Defines the base abstraction for social publishing and messaging platform adapters.
Canonical Platforms:
1. facebook
2. instagram
3. linkedin
4. whatsapp (Messaging Adapter)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class BasePlatformAdapter(ABC):
    """Abstract base class for all social publishing platform adapters."""

    def __init__(self, platform_key: str, display_name: str):
        self.platform_key = platform_key
        self.display_name = display_name

    @abstractmethod
    def validate_connection(self, **kwargs) -> Dict[str, Any]:
        """Validates credentials, permissions, and connectivity without publishing."""
        pass

    @abstractmethod
    def validate_content(self, content: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates content against platform-specific constraints:
        character limits, media format requirements, hashtags, and aspect ratios.
        """
        pass

    @abstractmethod
    def publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publishes content to the target social network.
        Must respect POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
        Returns standardized result:
        {
            'success': bool,
            'platform': str,
            'external_post_id': Optional[str],
            'simulated': bool,
            'error': Optional[str],
            'response': Optional[dict]
        }
        """
        pass

    @abstractmethod
    def upload_media(self, file_path: str, media_type: str = 'image', **kwargs) -> Dict[str, Any]:
        """Uploads or registers media assets on the platform prior to publishing."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns structured account health, connection status, and token expiration."""
        pass

    def handle_error(self, error: Any) -> Dict[str, Any]:
        """Classifies platform-specific error responses into standardized error codes."""
        err_str = str(error)
        return {
            'success': False,
            'platform': self.platform_key,
            'error_message': err_str,
            'error_code': 'PLATFORM_ERROR'
        }


class BaseMessagingAdapter(BasePlatformAdapter):
    """
    Dedicated base adapter for commercial messaging gateways (e.g. WhatsApp Business).
    Decoupled from social feed post logic to support recipient lists, template approvals,
    consent rules, and delivery reporting.
    """

    @abstractmethod
    def get_templates(self) -> List[Dict[str, Any]]:
        """Fetches approved message templates from the official provider API."""
        pass

    @abstractmethod
    def send_template(
        self,
        recipient_phone: str,
        template_name: str,
        language_code: str = 'en',
        components: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Dispatches a pre-approved template message to a single recipient.
        Must respect POSTPILOT_PUBLISHING_ENABLED=0 safety guardrail.
        """
        pass

    @abstractmethod
    def validate_phone_number(self, phone_number: str) -> Tuple[bool, str]:
        """Validates E.164 international phone number format."""
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload_bytes: bytes, signature_header: str) -> bool:
        """Verifies cryptographic signature on incoming delivery status webhooks."""
        pass
