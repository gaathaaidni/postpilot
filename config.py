"""
PostPilot Configuration Architecture
Supports universal execution across:
- Environment A: Web Server (Linux VPS / Cloud)
- Environment B: Android Phone (Termux)
- Local Development PC
"""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env file if present
load_dotenv(dotenv_path=BASE_DIR / ".env")

def _detect_runtime():
    """Detect whether running inside Termux, VPS/Production, or Local Dev."""
    env = os.getenv('APP_ENV', '').lower()
    if env in ('production', 'prod'):
        return 'production'
    if env == 'termux' or 'TERMUX_VERSION' in os.environ or '/com.termux/' in os.getenv('PREFIX', ''):
        return 'termux'
    if env in ('development', 'dev'):
        return 'development'
    # Default to development
    return 'development'

APP_ENV = _detect_runtime()

# Base directories
DATA_DIR = Path(os.getenv('POSTPILOT_DATA_DIR', BASE_DIR / 'data'))
UPLOAD_FOLDER = Path(os.getenv('POSTPILOT_UPLOAD_FOLDER', DATA_DIR / 'images'))

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# Database URI (SQLite for local/Termux, PostgreSQL for Web Server)
DEFAULT_SQLITE_PATH = DATA_DIR / "posts.db"
DATABASE_URL = os.getenv('POSTPILOT_DATABASE_URL') or os.getenv('DATABASE_URL', f"sqlite:///{DEFAULT_SQLITE_PATH}")

# Flask Core Settings
SECRET_KEY = os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY')
if not SECRET_KEY:
    if APP_ENV == 'production':
        raise RuntimeError(
            "Production security configuration violation: SECRET_KEY must be explicitly configured in the environment. "
            "Silently generating transient secrets in production breaks multi-worker session persistence and CSRF validation."
        )
    SECRET_KEY = 'postpilot-dev-secret-key-change-in-production'

DEBUG = os.getenv('FLASK_DEBUG', '1' if APP_ENV == 'development' else '0') == '1'

# Network binding
# When running inside Termux, strictly enforce 127.0.0.1 (loopback) to prevent accidental
# exposure on mobile hotspot, LAN, or cellular interfaces. Custom HOST overrides are rejected.
# In development, HOST can be overridden (e.g. for LAN testing), defaulting to 127.0.0.1.
# In production, HOST defaults to 0.0.0.0 or configured host behind reverse proxy.
if APP_ENV == 'termux':
    HOST = '127.0.0.1'
else:
    HOST = os.getenv('HOST', '127.0.0.1' if APP_ENV == 'development' else '0.0.0.0')
PORT = int(os.getenv('PORT', 5000))

# Security & Session Settings
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', '1' if APP_ENV == 'production' else '0') == '1'
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))  # 16 MB

# Local mode allows automatic login strictly for requests from 127.0.0.1 / ::1
# Non-localhost connections ALWAYS require explicit authentication.
# In production, LOCAL_MODE is strictly disabled regardless of local settings.
LOCAL_MODE = (os.getenv('LOCAL_MODE', '1') == '1') if APP_ENV in ('development', 'termux') else False

# Admin credentials for authentication
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123' if APP_ENV in ('development', 'termux') else '')

# Social API Credentials & Verified Meta Assets (Business Portfolio: 560075574375818)
META_BUSINESS_PORTFOLIO_ID = os.getenv('META_BUSINESS_PORTFOLIO_ID', '560075574375818')
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
FB_PAGE_ID_SUITE = os.getenv('FB_PAGE_ID_SUITE', os.getenv('TOUR_PAGE_ID', '967550829768297'))
FB_PAGE_ID_PHOENIX = os.getenv('FB_PAGE_ID_PHOENIX', os.getenv('VISA_PAGE_ID', '954901604381882'))
FB_PAGE_ID_GAATHA_AI = os.getenv('FB_PAGE_ID_GAATHA_AI', '1028368893692590')
FB_PAGE_ID_GRAHAK_CHETNA = os.getenv('FB_PAGE_ID_GRAHAK_CHETNA', '374211199112915')
FB_PAGE_ID_GAATHA = os.getenv('FB_PAGE_ID_GAATHA', '178168346255851')

INSTA_ID_SUITE = os.getenv('INSTA_ID_SUITE', '17841449080283492')
INSTA_ID_PHOENIX = os.getenv('INSTA_ID_PHOENIX', '17841471822022390')
INSTA_ID_GRAHAK_CHETNA = os.getenv('INSTA_ID_GRAHAK_CHETNA', '17841467723671727')

VERIFIED_META_PAGES = {
    '1028368893692590': {'name': 'Gaatha AI', 'env_key': 'FB_PAGE_ID_GAATHA_AI', 'slug': 'gaatha_ai', 'instagram_id': None},
    '954901604381882': {'name': 'Pheonix by Aidni Global LLP', 'env_key': 'FB_PAGE_ID_PHOENIX', 'slug': 'phoenix', 'instagram_id': '17841471822022390'},
    '967550829768297': {'name': 'Gaatha Suite', 'env_key': 'FB_PAGE_ID_SUITE', 'slug': 'suite', 'instagram_id': '17841449080283492'},
    '374211199112915': {'name': 'Grahak Chetna', 'env_key': 'FB_PAGE_ID_GRAHAK_CHETNA', 'slug': 'grahak_chetna', 'instagram_id': '17841467723671727'},
    '178168346255851': {'name': 'Gaatha', 'env_key': 'FB_PAGE_ID_GAATHA', 'slug': 'gaatha', 'instagram_id': None},
}

VERIFIED_META_INSTAGRAM_ACCOUNTS = {
    '17841471822022390': {'username': 'phoenixbygaatha', 'brand': 'Phoenix', 'env_key': 'INSTA_ID_PHOENIX', 'facebook_page_id': '954901604381882'},
    '17841449080283492': {'username': 'gaathasuite', 'brand': 'Gaatha Suite', 'env_key': 'INSTA_ID_SUITE', 'facebook_page_id': '967550829768297'},
    '17841467723671727': {'username': 'grahak.chetna', 'brand': 'Grahak Chetna', 'env_key': 'INSTA_ID_GRAHAK_CHETNA', 'facebook_page_id': '374211199112915'},
}

# LinkedIn Dual-Application OAuth 2.0 & API Configuration
LINKEDIN_REDIRECT_URI = os.getenv('LINKEDIN_REDIRECT_URI', 'https://postpilot.gaatha.tech/api/auth/linkedin/callback')

# Aidni Global LLP
LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP = os.getenv('LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP') or os.getenv('LINKEDIN_CLIENT_ID_AIDNI_GLOBAL')
LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP = os.getenv('LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP') or os.getenv('LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL')
LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL_LLP = os.getenv('LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL_LLP') or os.getenv('LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL')
LINKEDIN_ORG_ID_AIDNI_GLOBAL = os.getenv('LINKEDIN_ORG_ID_AIDNI_GLOBAL', '145240694')

# Gaatha Ventures Sh.p.k.
LINKEDIN_CLIENT_ID_GAATHA_VENTURES = os.getenv('LINKEDIN_CLIENT_ID_GAATHA_VENTURES')
LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES = os.getenv('LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES')
LINKEDIN_ACCESS_TOKEN_GAATHA_VENTURES = os.getenv('LINKEDIN_ACCESS_TOKEN_GAATHA_VENTURES')
LINKEDIN_ORG_ID_GAATHA_VENTURES = os.getenv('LINKEDIN_ORG_ID_GAATHA_VENTURES', '145250613')

# Backward compatibility aliases
LINKEDIN_CLIENT_ID = os.getenv('LINKEDIN_CLIENT_ID') or LINKEDIN_CLIENT_ID_GAATHA_VENTURES or LINKEDIN_CLIENT_ID_AIDNI_GLOBAL_LLP
LINKEDIN_CLIENT_SECRET = os.getenv('LINKEDIN_CLIENT_SECRET') or LINKEDIN_CLIENT_SECRET_GAATHA_VENTURES or LINKEDIN_CLIENT_SECRET_AIDNI_GLOBAL_LLP
LINKEDIN_ACCESS_TOKEN = os.getenv('LINKEDIN_ACCESS_TOKEN') or LINKEDIN_ACCESS_TOKEN_GAATHA_VENTURES or LINKEDIN_ACCESS_TOKEN_AIDNI_GLOBAL_LLP

# Publishing Safety Guardrail
# When 0 (default), all real external network calls to Meta Facebook & Instagram Graph APIs
# are strictly blocked, returning safe simulations. Must be explicitly set to '1' to publish.
POSTPILOT_PUBLISHING_ENABLED = (os.getenv('POSTPILOT_PUBLISHING_ENABLED') or os.getenv('PUBLISHING_ENABLED', '0')).strip().lower() in ('1', 'true', 'yes')

PUBLISHING_CONTROL_PLATFORMS = ('facebook', 'instagram', 'linkedin', 'whatsapp')
_PLATFORM_ALIASES = {
    'fb': 'facebook',
    'facebook': 'facebook',
    'ig': 'instagram',
    'insta': 'instagram',
    'instagram': 'instagram',
    'li': 'linkedin',
    'linkedin': 'linkedin',
    'wa': 'whatsapp',
    'whatsapp': 'whatsapp',
}

def _parse_optional_bool_env(var_name):
    raw = os.getenv(var_name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() in ('1', 'true', 'yes')

def _normalize_platform_key(platform):
    raw = str(platform or '').strip().lower()
    return _PLATFORM_ALIASES.get(raw, raw)

def is_publishing_enabled():
    """Checks whether external social media publishing is currently authorized."""
    return (os.getenv('POSTPILOT_PUBLISHING_ENABLED') or os.getenv('PUBLISHING_ENABLED', '0')).strip().lower() in ('1', 'true', 'yes')

def is_platform_publishing_enabled(platform):
    """
    Fail-closed per-platform publishing guardrail check.
    - Respects global POSTPILOT_PUBLISHING_ENABLED first.
    - Enforces POSTPILOT_ALLOWED_PLATFORMS comma-separated allowlist when set.
    - WhatsApp NEVER activates from the global switch alone; it always requires
      WHATSAPP_PUBLISHING_ENABLED=1 (and allowlist inclusion if allowlist is set).
    - Respects POSTPILOT_<PLATFORM>_PUBLISHING_ENABLED when explicitly configured.
    """
    if not is_publishing_enabled():
        return False

    plat = _normalize_platform_key(platform)
    if not plat:
        return False

    allowed_raw = (os.getenv('POSTPILOT_ALLOWED_PLATFORMS') or '').strip()
    allowed_set = None
    if allowed_raw:
        allowed_set = {_normalize_platform_key(p) for p in allowed_raw.split(',') if p.strip()}
        if plat not in allowed_set:
            return False

    if plat == 'whatsapp':
        return _parse_optional_bool_env('WHATSAPP_PUBLISHING_ENABLED') is True

    plat_flag = _parse_optional_bool_env(f'POSTPILOT_{plat.upper()}_PUBLISHING_ENABLED')
    if plat_flag is not None:
        return plat_flag

    return True

def get_enabled_publishing_platforms():
    """Returns canonical platform keys currently authorized for live dispatch."""
    return [p for p in PUBLISHING_CONTROL_PLATFORMS if is_platform_publishing_enabled(p)]

def get_publishing_controls_summary():
    """Returns non-secret runtime publishing control summary across all supported channels."""
    platforms = {p: is_platform_publishing_enabled(p) for p in PUBLISHING_CONTROL_PLATFORMS}
    return {
        'global_enabled': is_publishing_enabled(),
        'allowed_platforms': [p for p, enabled in platforms.items() if enabled],
        'platforms': platforms,
        'whatsapp_enabled': platforms['whatsapp'],
    }

# Default posting intervals in seconds
TOUR_INTERVAL = int(os.getenv('TOUR_INTERVAL', 1800))
VISA_INTERVAL = int(os.getenv('VISA_INTERVAL', 1800))
GAATHA_INTERVAL = int(os.getenv('GAATHA_INTERVAL', 1800))
INSTA_INTERVAL = int(os.getenv('INSTA_CHECK_INTERVAL', 180))

# AI Marketing Studio Provider Configuration
# Supported providers: 'mock', 'groq', 'openai', 'openai_compatible'
# Defaults to 'mock' for 100% offline functionality without API keys or external network dependencies.
_configured_ai_prov = os.getenv('AI_PROVIDER', '').strip().lower()
if not _configured_ai_prov:
    AI_PROVIDER = 'mock'
else:
    AI_PROVIDER = _configured_ai_prov

# If AI_MOCK is explicitly enabled, enforce mock provider
if os.getenv('AI_MOCK', '').strip().lower() in ('1', 'true', 'yes'):
    AI_PROVIDER = 'mock'
AI_API_KEY = os.getenv('AI_API_KEY')
AI_BASE_URL = os.getenv('AI_BASE_URL')
AI_MODEL = os.getenv('AI_MODEL')
AI_TIMEOUT_SECONDS = int(os.getenv('AI_TIMEOUT_SECONDS', 30))

# AI Cost Controls & Generation Guardrails
AI_MAX_PLATFORMS_PER_REQUEST = int(os.getenv('AI_MAX_PLATFORMS_PER_REQUEST', 5))
AI_MAX_PROMPT_CHARS = int(os.getenv('AI_MAX_PROMPT_CHARS', 8000))
AI_MAX_OUTPUT_TOKENS = int(os.getenv('AI_MAX_OUTPUT_TOKENS', 1500))
AI_ORG_HOURLY_GENERATION_LIMIT = int(os.getenv('AI_ORG_HOURLY_GENERATION_LIMIT', 60))
AI_DEDUPLICATION_WINDOW_SECONDS = int(os.getenv('AI_DEDUPLICATION_WINDOW_SECONDS', 15))

# Groq OpenAI-compatible provider settings
GROQ_API_KEY = os.getenv('GROQ_API_KEY') or AI_API_KEY
GROQ_BASE_URL = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
GROQ_MODEL = os.getenv('GROQ_MODEL', AI_MODEL or 'llama-3.3-70b-versatile')

# OpenAI-compatible provider settings
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or AI_API_KEY
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', AI_MODEL or 'gpt-4o-mini')

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv'}
ALLOWED_MIMETYPES = {
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/avi'
}
