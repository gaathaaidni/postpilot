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
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    # If not provided, generate a deterministic fallback for dev, or random for session
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'postpilot-dev-secret-key-change-in-production')
    if APP_ENV == 'production':
        # Generate random key if none specified in production to prevent hardcoded vulnerability
        SECRET_KEY = secrets.token_hex(32)

DEBUG = os.getenv('FLASK_DEBUG', '1' if APP_ENV == 'development' else '0') == '1'

# Network binding
# Termux and dev bind to 127.0.0.1 by default for safety; production binds to 0.0.0.0 or 127.0.0.1 behind Nginx
HOST = os.getenv('HOST', '127.0.0.1' if APP_ENV in ('development', 'termux') else '0.0.0.0')
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

# Social API Credentials & Page IDs
FB_ACCESS_TOKEN = os.getenv('FB_ACCESS_TOKEN') or os.getenv('FB_TOKEN')
FB_PAGE_ID_SUITE = os.getenv('FB_PAGE_ID_SUITE', os.getenv('TOUR_PAGE_ID', '967550829768297'))
FB_PAGE_ID_PHOENIX = os.getenv('FB_PAGE_ID_PHOENIX', os.getenv('VISA_PAGE_ID', '954901604381882'))
FB_PAGE_ID_GAATHA_AI = os.getenv('FB_PAGE_ID_GAATHA_AI', os.getenv('FB_PAGE_ID_GAATHA', '1028368893692590'))

INSTA_ID_SUITE = os.getenv('INSTA_ID_SUITE', '17841449080283492')
INSTA_ID_PHOENIX = os.getenv('INSTA_ID_PHOENIX', '17841472248438802')

# Default posting intervals in seconds
TOUR_INTERVAL = int(os.getenv('TOUR_INTERVAL', 1800))
VISA_INTERVAL = int(os.getenv('VISA_INTERVAL', 1800))
GAATHA_INTERVAL = int(os.getenv('GAATHA_INTERVAL', 1800))
INSTA_INTERVAL = int(os.getenv('INSTA_CHECK_INTERVAL', 180))

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv'}
ALLOWED_MIMETYPES = {
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/avi'
}
