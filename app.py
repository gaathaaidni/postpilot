"""
PostPilot Web Application
Universal single-codebase application supporting:
- Environment A: Web Server (Linux VPS / Cloud via Gunicorn + Reverse Proxy)
- Environment B: Android Phone (Termux)
- Local Development PC
"""
import os
import time
import secrets
import hashlib
import threading
import logging
from pathlib import Path
from functools import wraps
from PIL import Image
import urllib.parse
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request, session, send_from_directory, redirect, url_for

import config
import database
import timezone_utils
from validation import validate_platform_creative
import ai_service
import linkedin_api
import integrations_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (App) %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = str(config.UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE

RETIRED_LEGACY_CHANNELS = {'tour', 'nz', 'gaatha', 'insta'}
CANONICAL_CREATION_PLATFORMS = {'facebook', 'instagram', 'linkedin', 'whatsapp', 'x'}
HISTORICAL_QUERY_PLATFORMS = CANONICAL_CREATION_PLATFORMS | RETIRED_LEGACY_CHANNELS
VALID_POST_TYPES = HISTORICAL_QUERY_PLATFORMS

def validate_file(file):
    """Validates file extension, MIME type, and image integrity."""
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in config.ALLOWED_EXTENSIONS or file.content_type not in config.ALLOWED_MIMETYPES:
        return False, 'Unsupported file format or type'
    
    if extension in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        try:
            with Image.open(file) as img:
                img.verify()
            file.seek(0)
        except Exception:
            return False, 'Invalid image file content'
    return True, None

# --- Authentication & CSRF Middleware ---

def is_localhost_request():
    """Verifies whether the current HTTP request originates strictly from localhost."""
    remote = request.remote_addr
    return remote in ('127.0.0.1', '::1', 'localhost')

def get_or_create_csrf_token():
    """Retrieves or creates a secure CSRF token in the user's session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(24)
    return session['csrf_token']

def login_required(f):
    """Enforces authentication for sensitive routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check if session already authenticated
        if session.get('user_id'):
            return f(*args, **kwargs)

        # 2. Controlled Local Mode: strictly allow if enabled AND requested from 127.0.0.1
        if config.LOCAL_MODE and is_localhost_request():
            # Auto-authenticate local user
            session['user_id'] = 1
            session['username'] = 'local_admin'
            session['role'] = 'admin'
            session['organization_id'] = 1
            get_or_create_csrf_token()
            return f(*args, **kwargs)

        # 3. Deny unauthenticated access
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Authentication required', 'auth_required': True}), 401
        return redirect(url_for('login_page'))
    return decorated_function

def csrf_protect(f):
    """Enforces CSRF token validation on state-altering requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            # Allow login without CSRF token since session is not established yet
            if request.path in ('/api/auth/login', '/api/auth/register-org', '/api/webhooks/whatsapp'):
                return f(*args, **kwargs)

            # Check header, form, or JSON
            token = (
                request.headers.get('X-CSRFToken') or
                request.form.get('csrf_token') or
                (request.is_json and request.get_json(silent=True) and request.get_json().get('csrf_token'))
            )
            expected = session.get('csrf_token')
            if not expected or not token or not secrets.compare_digest(token, expected):
                # If in controlled local mode on localhost, generate and accept token automatically
                if config.LOCAL_MODE and is_localhost_request():
                    get_or_create_csrf_token()
                else:
                    logger.warning(f"CSRF validation failed for {request.remote_addr} on {request.path}")
                    return jsonify({'error': 'Invalid or missing CSRF token'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def apply_csrf_protection():
    """Ensure session has a CSRF token initialized."""
    get_or_create_csrf_token()

# --- Image Cleanup Worker ---
def _cleanup_single_image(filename):
    """Checks if an image is still needed and deletes it if not."""
    if not filename:
        return
    try:
        with database.get_db_connection() as conn:
            row = conn.execute("""
                SELECT (
                    (SELECT COUNT(*) FROM posts WHERE image_filename = ?) +
                    (SELECT COUNT(*) FROM scheduled_posts WHERE image_filename = ?) +
                    (SELECT COUNT(*) FROM media_assets WHERE filename = ?)
                ) as count
            """, (filename, filename, filename)).fetchone()
            if row and row['count'] > 0:
                return
    except Exception as e:
        logger.error(f"Error checking DB for single image cleanup: {e}")
        return

    filepath = Path(config.UPLOAD_FOLDER) / filename
    if filepath.exists():
        try:
            filepath.unlink()
            logger.info(f"Deleted orphaned image: {filename}")
        except Exception as e:
            logger.error(f"Failed to delete orphaned image {filename}: {e}")

def _cleanup_images_worker():
    """Background worker running daily to purge unreferenced media files."""
    while True:
        try:
            with database.get_db_connection() as conn:
                rows = conn.execute("""
                    SELECT DISTINCT image_filename FROM posts WHERE image_filename IS NOT NULL AND image_filename != ''
                    UNION
                    SELECT DISTINCT image_filename FROM scheduled_posts WHERE image_filename IS NOT NULL AND image_filename != ''
                    UNION
                    SELECT DISTINCT filename as image_filename FROM media_assets WHERE filename IS NOT NULL AND filename != ''
                """).fetchall()
                db_images = {r['image_filename'] for r in rows}

            upload_dir = Path(config.UPLOAD_FOLDER)
            if upload_dir.exists():
                for file_path in upload_dir.iterdir():
                    if file_path.is_file() and not file_path.name.startswith('.'):
                        if file_path.name not in db_images and (time.time() - file_path.stat().st_mtime) > 604800:
                            file_path.unlink()
                            logger.info(f"Purged orphan media: {file_path.name}")
        except Exception as e:
            logger.error(f"Error in image cleanup worker: {e}")
        time.sleep(86400)

# --- Local In-Process Worker for Termux & Dev ---
# In production, tasks are managed by standalone worker.py or background service.
local_worker_threads = {}
local_threads_lock = threading.Lock()

def _local_status_callback(task_name, is_running, message='', current_post=None):
    database.set_task_state(task_name, is_running=is_running, status=message, current_post_summary=current_post)

def _start_local_task(task_name):
    """Legacy automation threads are retired. Scheduled publishing is handled via worker lease."""
    pass

def _stop_local_task(task_name):
    """Legacy automation threads are retired."""
    pass

# --- Page Routes ---

@app.route('/')
@login_required
def index():
    """Renders the main PostPilot dashboard."""
    return render_template(
        'index.html',
        csrf_token=get_or_create_csrf_token(),
        username=session.get('username', 'User'),
        local_mode=config.LOCAL_MODE and is_localhost_request()
    )

@app.route('/login')
def login_page():
    """Renders the login page if accessed directly."""
    if session.get('user_id') or (config.LOCAL_MODE and is_localhost_request()):
        return redirect(url_for('index'))
    return render_template('login.html', csrf_token=get_or_create_csrf_token())

@app.route('/about')
def about_page():
    """Renders the public About Us page."""
    return render_template(
        'about.html',
        csrf_token=get_or_create_csrf_token(),
        is_authenticated=bool(session.get('user_id'))
    )

@app.route('/privacy')
def privacy_page():
    """Renders the public Privacy Policy page."""
    return render_template(
        'privacy.html',
        csrf_token=get_or_create_csrf_token(),
        is_authenticated=bool(session.get('user_id'))
    )

@app.route('/terms')
def terms_page():
    """Renders the public Terms & Conditions page."""
    return render_template(
        'terms.html',
        csrf_token=get_or_create_csrf_token(),
        is_authenticated=bool(session.get('user_id'))
    )

@app.route('/agreement')
@app.route('/user-agreement')
def user_agreement_page():
    """Renders the public User Agreement page."""
    return render_template(
        'user-agreement.html',
        csrf_token=get_or_create_csrf_token(),
        is_authenticated=bool(session.get('user_id'))
    )

# --- Authentication API Endpoints ---

@app.after_request
def set_security_headers(response):
    """Enforces defensive HTTP response headers across all endpoints."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

@app.route('/api/auth/me', methods=['GET'])
def get_auth_status():
    """Returns current user session and authentication status."""
    is_authed = bool(session.get('user_id'))
    is_local = config.LOCAL_MODE and is_localhost_request()
    return jsonify({
        'authenticated': is_authed or is_local,
        'username': session.get('username', 'local_admin' if is_local else None),
        'role': session.get('role', 'admin' if is_local else None),
        'organization_id': session.get('organization_id', 1),
        'local_mode': is_local,
        'csrf_token': get_or_create_csrf_token()
    })

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """Handles username & password login."""
    data = request.get_json(silent=True) or request.form
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    user = database.verify_user_password(username, password)
    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['organization_id'] = user.get('organization_id', 1)
    token = get_or_create_csrf_token()
    return jsonify({
        'success': True,
        'username': user['username'],
        'role': user['role'],
        'organization_id': session['organization_id'],
        'csrf_token': token
    })


@app.route('/api/auth/register-org', methods=['POST'])
def register_organization_route():
    """Administrator-controlled organization registration."""
    # Protect endpoint: Only authenticated administrators or automated test suites can provision new organizations
    is_admin = bool(session.get('user_id') and session.get('role') == 'admin')
    is_test_env = getattr(config, 'APP_ENV', '') == 'testing' or getattr(config, 'TESTING', False) or app.config.get('TESTING', False)
    is_local_admin = bool(getattr(config, 'LOCAL_MODE', False) and is_localhost_request())
    if not (is_admin or is_test_env or is_local_admin):
        return jsonify({'error': 'Public registration is disabled. Contact your administrator.', 'code': 'REGISTRATION_DISABLED'}), 403

    data = request.get_json(silent=True) or request.form or {}
    org_name = data.get('org_name') or data.get('organization_name')
    org_slug = data.get('org_slug')
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    timezone_name = data.get('timezone', 'UTC')

    if not org_name or not username or not password:
        return jsonify({'error': 'org_name, username, and password are required', 'code': 'VALIDATION_ERROR'}), 400

    terms_accepted = data.get('terms_accepted')
    privacy_accepted = data.get('privacy_accepted')
    policy_version = str(data.get('policy_version') or '1.0')

    # If submitted from registration UI, validate consent
    if 'terms_accepted' in data and not (terms_accepted is True or str(terms_accepted).lower() in ('true', '1')):
        return jsonify({'error': 'You must agree to the Terms of Service & User Agreement.', 'code': 'TERMS_NOT_ACCEPTED'}), 400
    if 'privacy_accepted' in data and not (privacy_accepted is True or str(privacy_accepted).lower() in ('true', '1')):
        return jsonify({'error': 'You must acknowledge the Privacy Policy.', 'code': 'PRIVACY_NOT_ACKNOWLEDGED'}), 400

    try:
        res = database.register_organization_with_owner(
            org_name=org_name,
            org_slug=org_slug,
            owner_username=username,
            owner_password=password,
            owner_email=email,
            timezone_name=timezone_name
        )
        user = res['user']
        org = res['organization']

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['organization_id'] = org['id']
        session['csrf_token'] = secrets.token_hex(16)

        if terms_accepted and privacy_accepted:
            logger.info(f"User '{username}' registered org '{org_name}' with Terms & Privacy Policy v{policy_version} acceptance recorded at {datetime.now(timezone.utc).isoformat()}")

        return jsonify({
            'status': 'success',
            'organization': org,
            'user': user,
            'policy_version_accepted': policy_version if (terms_accepted and privacy_accepted) else None,
            'csrf_token': session['csrf_token']
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error registering organization: {e}")
        return jsonify({'error': 'Failed to register organization'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Terminates the user session."""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# --- LinkedIn OAuth & Integration Endpoints ---

@app.route('/api/auth/linkedin/connect', methods=['GET'])
@app.route('/api/auth/linkedin/connect/<app_name>', methods=['GET'])
@login_required
def linkedin_connect(app_name=None):
    """
    Generates a secure LinkedIn OAuth authorization URL with CSRF state token
    for the requested LinkedIn application ('aidni_global' or 'gaatha_ventures').
    """
    app_key = app_name or request.args.get('app') or linkedin_api.APP_GAATHA_VENTURES
    try:
        norm_key = linkedin_api.normalize_app_key(app_key)
        red_uri = getattr(config, 'LINKEDIN_REDIRECT_URI', None) or 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'
        raw_scope = request.args.get('scope')
        requested_scopes = linkedin_api.parse_scopes(raw_scope) if raw_scope else None
        auth_url, state, csrf = linkedin_api.get_authorization_url(
            app_key=norm_key,
            redirect_uri=red_uri,
            scopes=requested_scopes,
        )

        # Save CSRF state per app in session
        if 'linkedin_oauth_states' not in session:
            session['linkedin_oauth_states'] = {}
        session['linkedin_oauth_states'][norm_key] = csrf
        session['linkedin_oauth_state'] = state  # backward compatibility
        session['linkedin_oauth_last_app'] = norm_key
        session.modified = True

        # If browser direct navigation or redirect requested
        if request.args.get('format') != 'json' and 'application/json' not in request.headers.get('Accept', ''):
            return redirect(auth_url)

        return jsonify({
            'success': True,
            'app_key': norm_key,
            'authorization_url': auth_url,
            'state': state
        })
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'CONFIG_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error generating LinkedIn authorization URL for {app_key}: {e}")
        return jsonify({'error': 'Failed to initiate LinkedIn authorization'}), 500


@app.route('/api/auth/linkedin/callback', methods=['GET'])
def linkedin_callback():
    """
    Handles LinkedIn OAuth 2.0 redirect callback.
    Validates CSRF state token and exchanges authorization code for an access token
    for the specific LinkedIn application.
    """
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    error_desc = request.args.get('error_description')

    def _callback_error_response(err_msg, err_code, desc=None, app_hint=None, force_redirect_for_non_json=False):
        accept_hdr = request.headers.get('Accept', '')
        wants_json = 'application/json' in accept_hdr or request.args.get('format') == 'json'
        wants_browser = 'text/html' in accept_hdr or force_redirect_for_non_json
        if not wants_json and wants_browser:
            params = {
                'tab': 'accounts',
                'linkedin_error': str(err_msg),
            }
            if desc:
                params['linkedin_error_description'] = str(desc)
            if app_hint:
                params['linkedin_app'] = str(app_hint)
            return redirect('/?' + urllib.parse.urlencode(params))
        payload = {'error': err_msg, 'code': err_code}
        if desc:
            payload['description'] = desc
        return jsonify(payload), 400

    state_app_hint = state.split(':', 1)[0] if state and ':' in state else None

    if error:
        safe_desc = linkedin_api.sanitize_log_message(str(error_desc or ''))
        logger.warning(f"LinkedIn OAuth authorization denied (app={state_app_hint or 'unknown'}): {error} - {safe_desc}")
        return _callback_error_response(
            err_msg=error,
            err_code='OAUTH_DENIED',
            desc=error_desc,
            app_hint=state_app_hint,
            force_redirect_for_non_json=True,
        )

    if not state:
        return jsonify({'error': 'Missing OAuth state parameter.', 'code': 'INVALID_STATE'}), 400

    # Parse app and csrf from state: '<app_key>:<csrf>' or legacy '<csrf>'
    parts = state.split(':', 1)
    if len(parts) == 2:
        app_key = linkedin_api.normalize_app_key(parts[0])
        csrf = parts[1]
    else:
        app_key = session.get('linkedin_oauth_last_app') or linkedin_api.APP_GAATHA_VENTURES
        csrf = state

    # Validate CSRF against session
    saved_states = session.get('linkedin_oauth_states', {})
    expected_csrf = saved_states.get(app_key) or session.get('linkedin_oauth_state')

    valid_csrf = False
    if expected_csrf:
        if expected_csrf == state or expected_csrf == csrf:
            valid_csrf = True
        elif ":" in str(expected_csrf) and str(expected_csrf).split(":", 1)[1] == csrf:
            valid_csrf = True

    if not valid_csrf:
        logger.warning(f"LinkedIn OAuth callback rejected: CSRF state mismatch for app '{app_key}'.")
        return _callback_error_response(
            err_msg='Invalid OAuth state. Potential CSRF detected or login session expired — please retry connecting from Connected Accounts.',
            err_code='INVALID_STATE',
            app_hint=app_key,
        )

    # Clean state after use
    if 'linkedin_oauth_states' in session and app_key in session['linkedin_oauth_states']:
        session['linkedin_oauth_states'].pop(app_key, None)
    session.pop('linkedin_oauth_state', None)
    session.modified = True

    if not code:
        return _callback_error_response(
            err_msg='Missing authorization code in LinkedIn callback.',
            err_code='MISSING_CODE',
            app_hint=app_key,
        )

    # Exchange code for access token using specific app credentials and exact redirect URI
    red_uri = getattr(config, 'LINKEDIN_REDIRECT_URI', None) or 'https://postpilot.gaatha.tech/api/auth/linkedin/callback'
    token_res = linkedin_api.exchange_code_for_token(code=code, app_key=app_key, redirect_uri=red_uri)
    if not token_res.get('success'):
        return _callback_error_response(
            err_msg=token_res.get('error', 'Token exchange failed'),
            err_code='EXCHANGE_FAILED',
            app_hint=app_key,
        )

    token = token_res['access_token']
    session[f'linkedin_access_token_{app_key}'] = token

    eligibility = linkedin_api.check_organization_publishing_eligibility(app_key, access_token=token)
    granted_scopes = linkedin_api.parse_scopes(token_res.get('scope'))
    if token_res.get('member'):
        member = token_res['member']
    elif 'openid' in granted_scopes and 'profile' in granted_scopes:
        member = linkedin_api.get_authenticated_member(token)
    else:
        member = {'success': False, 'skipped': True, 'name': None}

    # Persist verified token and status to database social_accounts without overwriting existing brand mapping
    try:
        cfg = linkedin_api.get_app_config(app_key)
        target_org = str(cfg.get('org_id'))
        org_scope = session.get('organization_id', 1)
        existing_accounts = database.get_social_accounts(organization_id=org_scope, platform='linkedin')
        matched = next((a for a in existing_accounts if str(a.get('account_identifier')) == target_org), None)
        target_brand_id = matched['brand_id'] if matched else 1

        exp_ts = token_res.get('expires_at')
        exp_str = datetime.fromtimestamp(float(exp_ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if exp_ts else None

        database.upsert_social_account(
            organization_id=org_scope,
            brand_id=target_brand_id,
            platform='linkedin',
            account_name=token_res.get('display_name', cfg['display_name']),
            account_identifier=target_org,
            status='connected',
            permissions_scope=token_res.get('scope'),
            app_identifier=app_key,
            access_token=token,
            token_expires_at=exp_str
        )
    except Exception as e:
        logger.warning(f"Could not persist LinkedIn account to database: {e}")

    if 'application/json' in request.headers.get('Accept', '') or request.args.get('format') == 'json':
        return jsonify({
            'success': True,
            'message': f"LinkedIn authentication successful for {token_res.get('display_name')}.",
            'app_key': app_key,
            'display_name': token_res.get('display_name'),
            'member': member.get('name') if member and member.get('success') else None,
            'eligibility': eligibility
        })

    return redirect(f"/?tab=accounts&linkedin_connected={app_key}")


@app.route('/api/linkedin/status', methods=['GET'])
@login_required
def linkedin_status():
    """Returns LinkedIn integration readiness and target company discovery for both apps."""
    req_app = request.args.get('app')
    audit = linkedin_api.audit_linkedin_status()
    if req_app:
        norm_key = linkedin_api.normalize_app_key(req_app)
        app_data = audit.get('apps', {}).get(norm_key)
        if app_data:
            return jsonify({
                'success': True,
                'app': app_data,
                'publishing_enabled': audit.get('publishing_enabled', False)
            })
    return jsonify(audit)


@app.route('/api/linkedin/organizations', methods=['GET'])
@login_required
def linkedin_organizations():
    """Returns configuration and permission status for both target LinkedIn organizations."""
    audit = linkedin_api.audit_linkedin_status()
    return jsonify({
        'success': True,
        'apps': audit.get('apps', {}),
        'targets': audit.get('targets', {})
    })


@app.route('/api/linkedin/refresh', methods=['POST'])
@login_required
@csrf_protect
def linkedin_refresh_token():
    """Safely attempts LinkedIn refresh-token flow only if authorized, preserving existing tokens on failure."""
    data = request.get_json(silent=True) or {}
    app_key = data.get('app') or data.get('app_key') or linkedin_api.APP_AIDNI_GLOBAL
    res = linkedin_api.refresh_access_token(app_key)
    return jsonify(res), (200 if res.get('success') else 400)


@app.route('/api/linkedin/publish', methods=['POST'])
@login_required
@csrf_protect
def linkedin_publish_post():
    """Publishes or simulates a post to either a verified Personal LinkedIn Profile or a Company Page."""
    org_id_scope = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    destination = str(data.get('destination') or 'organization').strip().lower()
    org_id = data.get('organization_id')
    app_key = data.get('app') or data.get('app_key')
    text = data.get('text') or data.get('message') or data.get('caption')
    image_filename = data.get('image_filename')
    idempotency_key = data.get('idempotency_key')

    if not text or not str(text).strip():
        return jsonify({'error': 'Post text is required', 'code': 'MISSING_TEXT'}), 400

    if idempotency_key:
        with database.get_db_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM scheduled_posts WHERE idempotency_key = ? AND organization_id = ?",
                (idempotency_key, org_id_scope)
            ).fetchone()
            if existing:
                rec = database.get_scheduled_post_by_id(existing['id'], organization_id=org_id_scope)
                return jsonify({
                    'success': rec['status'] == 'published',
                    'deduplicated': True,
                    'external_post_id': rec.get('external_post_id'),
                    'record': rec
                }), 200

    if destination == 'personal':
        resolved_app = linkedin_api.normalize_app_key(app_key or linkedin_api.APP_AIDNI_GLOBAL)
        if not config.is_linkedin_personal_publishing_enabled():
            return jsonify({
                'success': False,
                'destination': 'personal',
                'blocked_by_guardrail': True,
                'error': 'Personal LinkedIn publishing is currently disabled.'
            }), 403
        token = session.get(f'linkedin_access_token_{resolved_app}') or linkedin_api.get_active_token(resolved_app)
        from platform_adapters import PlatformRegistry
        adapter = PlatformRegistry.get_adapter('linkedin')
        res = adapter.publish({
            'destination': 'personal',
            'app_key': resolved_app,
            'message': text,
            'image_filename': image_filename,
            'access_token': token,
        })
        if not res.get('success') or res.get('simulated'):
            return jsonify(res), (403 if res.get('error_code') in ('PERMISSION_DENIED', 'IDENTITY_SCOPE_REQUIRED', 'UNAUTHENTICATED', 'TOKEN_EXPIRED') else 400)

        ext_id = res.get('external_post_id')
        record = database.record_immediate_publication(
            post_type='linkedin',
            message=text,
            external_post_id=ext_id,
            brand_id=data.get('brand_id'),
            organization_id=org_id_scope,
            created_by=user_id,
            image_filename=image_filename,
            idempotency_key=idempotency_key,
            provider_response={'external_post_id': ext_id, 'destination': 'personal', 'author_urn': res.get('author_urn'), 'app_key': resolved_app},
            reason='Immediate publication to Personal LinkedIn Profile via /api/linkedin/publish',
        )
        return jsonify({**res, 'record': record}), 200

    # Organization destination
    if not org_id:
        if app_key:
            try:
                cfg = linkedin_api.get_app_config(app_key)
                org_id = cfg.get('org_id')
            except Exception:
                pass
    if not org_id:
        return jsonify({'error': 'organization_id is required', 'code': 'MISSING_ORG'}), 400

    if not config.is_linkedin_company_publishing_enabled():
        return jsonify({
            'success': False,
            'destination': 'organization',
            'blocked_by_guardrail': True,
            'error': 'Company-page LinkedIn publishing is disabled pending Community Management API (w_organization_social) approval.'
        }), 403

    clean_org = str(org_id).replace("urn:li:organization:", "").strip()
    if app_key:
        resolved_app = linkedin_api.normalize_app_key(app_key)
    elif clean_org == linkedin_api.DEFAULT_ORG_ID_AIDNI_GLOBAL:
        resolved_app = linkedin_api.APP_AIDNI_GLOBAL
    else:
        resolved_app = linkedin_api.APP_GAATHA_VENTURES

    token = (
        session.get(f'linkedin_access_token_{resolved_app}')
        or linkedin_api.get_active_token(resolved_app)
    )

    try:
        elig = linkedin_api.check_organization_publishing_eligibility(resolved_app, access_token=token)
        if not elig.get('company_publishing_authorized'):
            return jsonify({
                'success': False,
                'destination': 'organization',
                'error_code': elig.get('eligibility_code', 'COMMUNITY_MANAGEMENT_API_REQUIRED'),
                'error': elig.get('eligibility_message') or 'Company-page publishing not authorized.'
            }), 403

        result = linkedin_api.create_organization_post(
            organization_id=org_id,
            text=text,
            app_key=resolved_app,
            access_token=token
        )
        return jsonify(result), (200 if result.get('success') else 400)
    except Exception as e:
        logger.error(f"Error publishing LinkedIn post: {linkedin_api.sanitize_log_message(str(e))}")
        return jsonify({'error': linkedin_api.sanitize_log_message(str(e))}), 500

@app.route('/api/publish', methods=['POST'])
@login_required
@csrf_protect
def immediate_publish_post():
    """Immediately publishes a post via PlatformRegistry with per-platform guardrails, idempotency, and audit recording."""
    import requests
    import facebook_api
    from platform_adapters import PlatformRegistry

    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}

    raw_post_type = str(data.get('post_type') or data.get('platform') or '').strip().lower()
    destination = str(data.get('destination') or data.get('linkedin_destination') or '').strip().lower()
    is_li_personal = (raw_post_type == 'linkedin_personal') or (config._normalize_platform_key(raw_post_type) == 'linkedin' and destination == 'personal')
    post_type = 'linkedin' if is_li_personal else config._normalize_platform_key(raw_post_type)

    if post_type not in ('facebook', 'instagram', 'linkedin', 'whatsapp'):
        return jsonify({'error': f"Unsupported platform '{post_type}'"}), 400

    if is_li_personal:
        if not config.is_linkedin_personal_publishing_enabled():
            return jsonify({
                'success': False,
                'platform': 'linkedin',
                'destination': 'personal',
                'blocked_by_guardrail': True,
                'error': "Personal LinkedIn publishing is currently disabled."
            }), 403
    elif post_type == 'linkedin':
        if not config.is_linkedin_company_publishing_enabled():
            return jsonify({
                'success': False,
                'platform': 'linkedin',
                'destination': 'organization',
                'blocked_by_guardrail': True,
                'error': "Company-page LinkedIn publishing is disabled pending Community Management API (w_organization_social) approval."
            }), 403
    elif not config.is_platform_publishing_enabled(post_type):
        return jsonify({
            'success': False,
            'platform': post_type,
            'blocked_by_guardrail': True,
            'error': f"Publishing is currently disabled for platform '{post_type}'."
        }), 403

    brand_id = data.get('brand_id')
    if brand_id is not None and str(brand_id).strip() != '':
        try:
            brand_id = int(brand_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid brand_id'}), 400
    else:
        brand_id = None

    message = data.get('message') or data.get('caption') or data.get('text') or ''
    image_filename = data.get('image_filename')
    idempotency_key = data.get('idempotency_key')

    if idempotency_key:
        with database.get_db_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM scheduled_posts WHERE idempotency_key = ? AND organization_id = ?",
                (idempotency_key, org_id)
            ).fetchone()
            if existing:
                rec = database.get_scheduled_post_by_id(existing['id'], organization_id=org_id)
                return jsonify({
                    'success': rec['status'] == 'published',
                    'deduplicated': True,
                    'external_post_id': rec.get('external_post_id'),
                    'record': rec
                }), 200

    adapter = PlatformRegistry.get_adapter(post_type)
    if not adapter:
        return jsonify({'error': f"No adapter registered for '{post_type}'"}), 400

    payload = {
        'organization_id': org_id,
        'brand_id': brand_id,
        'post_type': 'linkedin_personal' if is_li_personal else post_type,
        'destination': 'personal' if is_li_personal else (destination or None),
        'message': message,
        'image_filename': image_filename,
        'image_url': data.get('image_url'),
        'page_id': data.get('page_id'),
        'ig_user_id': data.get('ig_user_id'),
        'linkedin_org_id': data.get('linkedin_org_id'),
        'app_key': data.get('app_key'),
    }
    valid, val_err = adapter.validate_content(payload)
    if not valid:
        return jsonify({'success': False, 'error': val_err or 'Content validation failed'}), 400

    res = adapter.publish(payload)
    if not res.get('success') or res.get('simulated'):
        return jsonify({
            'success': False,
            'platform': post_type,
            'destination': res.get('destination'),
            'simulated': bool(res.get('simulated')),
            'error_code': res.get('error_code'),
            'error': res.get('error') or res.get('message') or 'Live publishing rejected'
        }), 400

    ext_id = res.get('external_post_id') or res.get('post_id')
    if not ext_id:
        return jsonify({'success': False, 'error': 'Provider did not return a valid post ID'}), 502

    permalink_url = res.get('permalink_url')
    page_id = res.get('page_id')
    if post_type == 'facebook' and not permalink_url and page_id:
        try:
            ptok = facebook_api.get_page_token(facebook_api.get_access_token(), page_id)
            if ptok:
                vresp = requests.get(
                    f"https://graph.facebook.com/v19.0/{ext_id}",
                    params={'fields': 'id,permalink_url,created_time,message', 'access_token': ptok},
                    timeout=15
                )
                if vresp.status_code == 200:
                    permalink_url = vresp.json().get('permalink_url')
        except Exception as ve:
            logger.warning(f"Post verification lookup warning for {ext_id}: {ve}")

    record = database.record_immediate_publication(
        post_type=post_type,
        message=message,
        external_post_id=ext_id,
        brand_id=brand_id,
        organization_id=org_id,
        created_by=user_id,
        image_filename=image_filename,
        idempotency_key=idempotency_key,
        permalink_url=permalink_url,
        provider_response={
            'external_post_id': ext_id,
            'page_id': page_id,
            'permalink_url': permalink_url,
            'destination': res.get('destination'),
            'author_urn': res.get('author_urn'),
            'organization_id': res.get('organization_id'),
            'app_key': res.get('app_key'),
        },
        reason=f"Immediate live publication ({res.get('destination') or post_type}) via /api/publish"
    )
    return jsonify({
        'success': True,
        'platform': post_type,
        'destination': res.get('destination'),
        'page_id': page_id,
        'author_urn': res.get('author_urn'),
        'external_post_id': ext_id,
        'permalink_url': permalink_url,
        'record': record
    }), 200

# --- Social Account Management Endpoints (Phase 2 & Part F) ---

@app.route('/api/accounts', methods=['GET'])
@login_required
def get_accounts():
    """
    Returns verified connected social accounts for the active organization.
    Supports optional brand_id and platform filtering.
    Zero token or secret disclosure.
    """
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id', type=int)
    platform = request.args.get('platform')

    accounts = database.get_social_accounts(
        organization_id=org_id,
        brand_id=brand_id,
        platform=platform
    )

    for a in accounts:
        plat = a['platform']
        if plat == 'linkedin':
            app_k = linkedin_api.normalize_app_key(
                a.get('app_identifier')
                or ('aidni_global' if str(a.get('account_identifier')) == str(getattr(config, 'LINKEDIN_ORG_ID_AIDNI_GLOBAL', '145240694')) else 'gaatha_ventures')
            )
            a['reconnect_url'] = f"/api/auth/linkedin/connect/{app_k}"
            tok_data = linkedin_api.get_token_data(app_k)
            if tok_data and tok_data.get('access_token'):
                real_scopes = linkedin_api.parse_scopes(tok_data.get('scope'))
                if real_scopes:
                    a['permissions_scope'] = ','.join(real_scopes)
                if linkedin_api.is_token_expired(tok_data):
                    a['status'] = 'expired'
                    a['token_status'] = 'expired'
                else:
                    a['status'] = 'connected'
                    a['token_status'] = 'valid'
            else:
                a['status'] = 'authentication_required'
                a['token_status'] = 'missing'
                a['permissions_scope'] = ','.join(linkedin_api.get_default_scopes(app_k))
            continue
        elif plat in ('facebook', 'instagram'):
            a['reconnect_url'] = "/api/auth/meta/connect"
        elif plat == 'whatsapp':
            a['reconnect_url'] = "/api/auth/whatsapp/configure"
        else:
            a['reconnect_url'] = None

        # Determine token status
        if a.get('status') == 'connected':
            a['token_status'] = 'valid'
        elif a.get('status') == 'expired':
            a['token_status'] = 'expired'
        else:
            a['token_status'] = 'unknown'

    return jsonify({
        'success': True,
        'organization_id': org_id,
        'count': len(accounts),
        'accounts': accounts
    })


@app.route('/api/accounts/verify/<int:account_id>', methods=['POST'])
@login_required
@csrf_protect
def verify_account(account_id):
    """
    Verifies connection status for a connected account without leaking credentials.
    Enforces organization boundaries.
    """
    org_id = session.get('organization_id', 1)
    accounts = database.get_social_accounts(organization_id=org_id)
    target = next((a for a in accounts if a['id'] == account_id), None)
    if not target:
        return jsonify({'error': 'Social account not found', 'code': 'NOT_FOUND'}), 404

    plat = target['platform']
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with database.get_db_connection() as conn:
        conn.execute(
            "UPDATE social_accounts SET last_verified_at = ?, status = 'connected' WHERE id = ?",
            (now_str, account_id)
        )
        conn.commit()

    return jsonify({
        'success': True,
        'account_id': account_id,
        'platform': plat,
        'status': 'connected',
        'last_verified_at': now_str,
        'verified_at': now_str
    })


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
@login_required
@csrf_protect
def disconnect_account(account_id):
    """Disconnects and removes a social account respecting organization isolation."""
    org_id = session.get('organization_id', 1)
    success = database.delete_social_account(account_id, organization_id=org_id)
    if not success:
        return jsonify({'error': 'Social account not found or access denied', 'code': 'NOT_FOUND'}), 404
    return jsonify({'success': True, 'message': 'Account disconnected successfully.'})


# --- Unified Social Platform Integration & Discovery Endpoints ---

@app.route('/api/integrations/status', methods=['GET'])
@login_required
def get_integrations_status_route():
    """
    Returns verified live status for all platforms:
    - Meta Facebook Pages & Instagram Accounts
    - LinkedIn Enterprise Applications
    - WhatsApp Business Cloud API & Phone Verification
    """
    org_id = session.get('organization_id', 1)
    meta_data = integrations_service.discover_meta_properties(organization_id=org_id)
    linkedin_data = integrations_service.get_linkedin_integration_status(organization_id=org_id)
    whatsapp_data = integrations_service.get_whatsapp_integration_status(organization_id=org_id)

    controls = config.get_publishing_controls_summary()
    return jsonify({
        'success': True,
        'organization_id': org_id,
        'publishing_enabled': config.is_publishing_enabled(),
        'publishing_controls': controls,
        'publishing_platforms': controls['platforms'],
        'enabled_publishing_platforms': controls['allowed_platforms'],
        'meta': meta_data,
        'linkedin': linkedin_data,
        'whatsapp': whatsapp_data
    })


@app.route('/api/integrations/meta/discover', methods=['GET'])
@login_required
def discover_meta_route():
    """Discovers all accessible Facebook Pages and linked Instagram accounts via Meta Graph API."""
    org_id = session.get('organization_id', 1)
    result = integrations_service.discover_meta_properties(organization_id=org_id)
    return jsonify(result)


@app.route('/api/integrations/whatsapp/status', methods=['GET'])
@login_required
def whatsapp_status_route():
    """Returns actual WhatsApp Business phone verification, platform type, and template status."""
    org_id = session.get('organization_id', 1)
    result = integrations_service.get_whatsapp_integration_status(organization_id=org_id)
    return jsonify(result)


@app.route('/api/whatsapp/templates', methods=['GET'])
@login_required
def whatsapp_templates_route():
    """Returns live Meta-approved templates separately from local sandbox previews."""
    from platform_adapters.whatsapp import WhatsAppCloudAdapter, PRESERVED_WHATSAPP_NUMBERS

    adapter = WhatsAppCloudAdapter()
    creds = adapter.get_credentials()
    waba_ids = []
    for wid in [creds.get('waba_id'), '1370721214882653', '1471882524763501']:
        if wid and wid not in waba_ids:
            waba_ids.append(wid)

    live_by_waba = {}
    all_live_templates = []
    for wid in waba_ids:
        res = adapter.fetch_live_templates(waba_id=wid)
        live_by_waba[wid] = res
        for t in res.get('templates', []):
            t_copy = dict(t)
            t_copy['waba_id'] = wid
            all_live_templates.append(t_copy)

    approved_live = [t for t in all_live_templates if t.get('meta_approved')]
    local_previews = adapter.get_local_template_previews()

    return jsonify({
        'success': True,
        'configured_waba_id': creds.get('waba_id'),
        'preserved_numbers': list(PRESERVED_WHATSAPP_NUMBERS.values()),
        'meta_approved_count': len(approved_live),
        'live_templates': all_live_templates,
        'live_by_waba': live_by_waba,
        'local_previews_count': len(local_previews),
        'local_previews': local_previews,
    })


@app.route('/api/whatsapp/simulate', methods=['POST'])
@login_required
@csrf_protect
def whatsapp_simulate_route():
    """Validates formatting, template variables, E.164 phone, and sender isolation strictly in sandbox simulation."""
    from platform_adapters.whatsapp import WhatsAppCloudAdapter

    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    adapter = WhatsAppCloudAdapter()

    recipient = data.get('recipient_phone') or data.get('phone') or ''
    template_name = data.get('template_name') or 'client_welcome'
    message_text = data.get('message') or data.get('text') or ''
    variables = data.get('variables')
    language_code = data.get('language_code') or 'en'
    brand_id = data.get('brand_id')

    if config.is_platform_publishing_enabled('whatsapp'):
        return jsonify({
            'success': False,
            'error': 'Sandbox simulation endpoint only operates when WHATSAPP_PUBLISHING_ENABLED=0.'
        }), 409

    if brand_id is not None and str(brand_id).strip() != '':
        res = adapter.publish({
            'organization_id': org_id,
            'brand_id': int(brand_id),
            'recipient_phone': recipient,
            'template_name': template_name,
            'message': message_text,
            'variables': variables,
            'language_code': language_code,
            'phone_number_id': data.get('phone_number_id'),
        })
        return jsonify(res), (200 if res.get('success') else 400)

    valid, val_err = adapter.validate_content({
        'recipient_phone': recipient,
        'template_name': template_name,
        'message': message_text,
        'variables': variables,
    })
    if not valid:
        return jsonify({'success': False, 'error': val_err}), 400

    from platform_adapters.whatsapp import PRESERVED_WHATSAPP_NUMBERS, PREFERRED_PHONE_NUMBER_ID, LEGACY_DISCONNECTED_PHONE_NUMBER_ID
    requested_pid = str(data.get('phone_number_id') or PREFERRED_PHONE_NUMBER_ID).strip()
    if requested_pid == LEGACY_DISCONNECTED_PHONE_NUMBER_ID:
        return jsonify({'success': False, 'error': "Secondary number +91 90990 28291 (1171737406016871) is preserved in read-only standby and is not offered for broadcasting."}), 400
    if requested_pid != PREFERRED_PHONE_NUMBER_ID:
        return jsonify({'success': False, 'error': f"Only preferred PostPilot sender {PREFERRED_PHONE_NUMBER_ID} (+91 98257 28291) is permitted."}), 400
    res = adapter.send_template(
        recipient_phone=recipient,
        template_name=template_name,
        language_code=language_code,
        variables=variables,
        phone_number_id=requested_pid,
    )
    if res.get('success'):
        res['selected_account'] = PRESERVED_WHATSAPP_NUMBERS[requested_pid]
    return jsonify(res), (200 if res.get('success') else 400)


@app.route('/api/webhooks/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook_route():
    """Meta WhatsApp Cloud API webhook verification challenge and fail-closed HMAC-SHA256 event receiver."""
    import hmac
    import json as py_json
    from platform_adapters.whatsapp import WhatsAppCloudAdapter

    adapter = WhatsAppCloudAdapter()
    creds = adapter.get_credentials()

    if request.method == 'GET':
        mode = request.args.get('hub.mode', '')
        verify_token = request.args.get('hub.verify_token', '')
        challenge = request.args.get('hub.challenge', '')
        expected = creds.get('verify_token') or ''
        if mode == 'subscribe' and expected and hmac.compare_digest(str(verify_token), str(expected)):
            return challenge, 200
        return jsonify({'error': 'Webhook verification token mismatch'}), 403

    sig = request.headers.get('X-Hub-Signature-256', '')
    raw_bytes = request.get_data()
    if not adapter.verify_webhook_signature(raw_bytes, sig, app_secret=creds.get('app_secret')):
        return jsonify({'error': 'Invalid or missing webhook signature'}), 403

    payload = request.get_json(silent=True) or {}
    recorded = 0
    for entry in payload.get('entry', []):
        waba_id = str(entry.get('id') or '')
        for change in entry.get('changes', []):
            val = change.get('value') or {}
            meta_obj = val.get('metadata') or {}
            phone_id = str(meta_obj.get('phone_number_id') or '')
            for st in val.get('statuses', []):
                database.record_whatsapp_webhook_event(
                    event_type='status',
                    waba_id=waba_id,
                    phone_number_id=phone_id,
                    message_id=st.get('id'),
                    status_value=st.get('status'),
                    recipient_phone=st.get('recipient_id'),
                    payload_json=st,
                )
                recorded += 1
            for msg in val.get('messages', []):
                database.record_whatsapp_webhook_event(
                    event_type='inbound_message',
                    waba_id=waba_id,
                    phone_number_id=phone_id,
                    message_id=msg.get('id'),
                    status_value=msg.get('type'),
                    recipient_phone=msg.get('from'),
                    payload_json=msg,
                )
                recorded += 1

    return jsonify({'status': 'received', 'events_recorded': recorded}), 200


@app.route('/api/integrations/map', methods=['POST'])
@login_required
@csrf_protect
def map_social_property_route():
    """
    Safely assigns an accessible social property (Facebook Page, IG account, etc.) to a brand workspace.
    Guarantees brand isolation.
    """
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    platform = data.get('platform')
    account_identifier = data.get('account_identifier')
    account_name = data.get('account_name')
    brand_id = data.get('brand_id')
    permissions_scope = data.get('permissions_scope')
    app_identifier = data.get('app_identifier')

    if not platform or not account_identifier or not account_name or not brand_id:
        return jsonify({'error': 'Missing required fields: platform, account_identifier, account_name, brand_id', 'code': 'VALIDATION_ERROR'}), 400

    try:
        brand_id_int = int(brand_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'brand_id must be an integer', 'code': 'VALIDATION_ERROR'}), 400

    res = integrations_service.map_property_to_brand(
        organization_id=org_id,
        platform=platform,
        account_identifier=str(account_identifier),
        account_name=str(account_name),
        brand_id=brand_id_int,
        permissions_scope=permissions_scope,
        app_identifier=app_identifier
    )
    if not res.get('success'):
        return jsonify(res), 400
    return jsonify(res), 200


@app.route('/api/integrations/map/<int:account_id>', methods=['DELETE'])
@login_required
@csrf_protect
def unmap_social_property_route(account_id):
    """Disconnects and unmaps a social account from a brand workspace."""
    org_id = session.get('organization_id', 1)
    res = integrations_service.unmap_property(organization_id=org_id, account_id=account_id)
    if not res.get('success'):
        return jsonify(res), 400
    return jsonify(res), 200

# --- Posts Management Endpoints ---

@app.route('/api/posts/<post_type>', methods=['GET'])
@login_required
def get_posts(post_type):
    """Retrieves all posts for a specific type scoped to the active organization."""
    if post_type not in HISTORICAL_QUERY_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    org_id = session.get('organization_id', 1)
    posts = database.load_posts_by_type(post_type, organization_id=org_id)
    return jsonify(posts)

@app.route('/api/posts/<post_type>', methods=['POST'])
@login_required
@csrf_protect
def add_post(post_type):
    """Creates a new post record scoped to the active organization."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy channel '{post_type}' is permanently retired and cannot be created.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    image_filename = data.get('image_filename', '').strip()
    brand_id = data.get('brand_id')
    org_id = session.get('organization_id', 1)

    post_id = database.add_post(post_type, message, image_filename, organization_id=org_id, brand_id=brand_id)
    return jsonify({'id': post_id, 'message': message, 'image_filename': image_filename, 'organization_id': org_id}), 201

@app.route('/api/posts/<post_type>/<int:post_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_post(post_type, post_id):
    """Updates an existing post ensuring channel-scoped and organization-scoped record access."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy channel '{post_type}' is permanently retired and cannot be created.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    message = data.get('message')
    image_filename = data.get('image_filename')
    org_id = session.get('organization_id', 1)

    success = database.update_post_by_id(post_id, message, image_filename, post_type=post_type, organization_id=org_id)
    if not success:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/<int:post_id>', methods=['DELETE'])
@login_required
@csrf_protect
def delete_post(post_type, post_id):
    """Deletes a post ensuring channel-scoped and organization-scoped record access."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy channel '{post_type}' is permanently retired and cannot be created.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    org_id = session.get('organization_id', 1)
        
    image_filename, success = database.delete_post_by_id(post_id, post_type=post_type, organization_id=org_id)
    if not success:
        return jsonify({'error': 'Post not found'}), 404

    if image_filename:
        _cleanup_single_image(image_filename)

    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/all', methods=['DELETE'])
@login_required
@csrf_protect
def delete_all_posts(post_type):
    """Deletes all posts for a type scoped to organization and cleans up orphaned media."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy channel '{post_type}' is permanently retired and cannot be created.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    org_id = session.get('organization_id', 1)

    deleted_images = database.delete_all_posts_by_type(post_type, organization_id=org_id)
    for img in deleted_images:
        _cleanup_single_image(img)

    return jsonify({'success': True, 'message': f'All {post_type} posts deleted'}), 200

@app.route('/api/search', methods=['GET'])
@login_required
def search_posts():
    """Searches posts across message and post_type scoped to organization."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    try:
        org_id = session.get('organization_id', 1)
        results = database.search_posts(query, organization_id=org_id)
        return jsonify(results)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': 'Search failed'}), 500

# --- File Upload & Media Serving ---

@app.route('/api/upload', methods=['POST'])
@login_required
@csrf_protect
def upload_image():
    """Uploads and validates a media file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    is_valid, error_msg = validate_file(file)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    extension = os.path.splitext(file.filename)[1].lower()
    filename = f"post_{int(time.time())}_{secrets.token_hex(4)}{extension}"
    save_path = Path(config.UPLOAD_FOLDER) / filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    file.save(str(save_path))
    return jsonify({'filename': filename}), 201

@app.route('/images/<filename>')
def serve_image(filename):
    """Serves uploaded images safely from UPLOAD_FOLDER with path traversal protection."""
    safe_filename = os.path.basename(filename)
    return send_from_directory(config.UPLOAD_FOLDER, safe_filename)




# --- Commercial SaaS Subscription Endpoints ---

@app.route('/api/saas/plans', methods=['GET'])
def list_saas_plans_route():
    """Lists available commercial subscription plans and quotas."""
    plans = database.get_subscription_plans()
    return jsonify({'status': 'success', 'plans': plans}), 200

@app.route('/api/saas/subscription', methods=['GET'])
@login_required
def get_saas_subscription_route():
    """Retrieves current organization's subscription tier and quota usage."""
    org_id = session.get('organization_id', 1)
    sub = database.get_organization_subscription(org_id)

    _, brand_usage, brand_limit, _ = database.check_organization_quota(org_id, 'brand')
    _, camp_usage, camp_limit, _ = database.check_organization_quota(org_id, 'campaign')
    _, post_usage, post_limit, _ = database.check_organization_quota(org_id, 'post')
    _, token_usage, token_limit, _ = database.check_organization_quota(org_id, 'ai_token')

    usage_metrics = {
        'brands': {'used': brand_usage, 'limit': brand_limit},
        'campaigns': {'used': camp_usage, 'limit': camp_limit},
        'monthly_posts': {'used': post_usage, 'limit': post_limit},
        'monthly_ai_tokens': {'used': token_usage, 'limit': token_limit}
    }
    return jsonify({
        'status': 'success',
        'subscription': sub,
        'quotas': usage_metrics
    }), 200

@app.route('/api/saas/subscription/upgrade', methods=['POST'])
@login_required
@csrf_protect
def upgrade_saas_subscription_route():
    """Changes/upgrades an organization's subscription tier. Restricted to owner or admin."""
    org_id = session.get('organization_id', 1)
    caller_role = session.get('role', 'contributor')
    if caller_role not in ('owner', 'admin'):
        return jsonify({'error': 'Forbidden: only organization owners and admins can manage subscriptions.'}), 403

    data = request.get_json(silent=True) or {}
    plan_code = data.get('plan_code') or data.get('plan_id')
    if not plan_code:
        return jsonify({'error': 'plan_code is required', 'code': 'VALIDATION_ERROR'}), 400

    try:
        updated = database.set_organization_subscription(org_id, plan_code)
        return jsonify({'status': 'success', 'subscription': updated}), 200
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error upgrading subscription for org #{org_id}: {e}")
        return jsonify({'error': 'Failed to upgrade subscription'}), 500

# --- Organization Settings & Team Management Endpoints ---

@app.route('/api/org/settings', methods=['GET'])
@login_required
def get_org_settings_route():
    """Retrieves current organization settings, metrics, and tier."""
    org_id = session.get('organization_id', 1)
    settings = database.get_organization_settings(org_id)
    if not settings:
        return jsonify({'error': 'Organization not found'}), 404
    return jsonify({'status': 'success', 'settings': settings}), 200

@app.route('/api/org/settings', methods=['PUT'])
@login_required
@csrf_protect
def update_org_settings_route():
    """Updates organization name or timezone. Restricted to owner or admin."""
    org_id = session.get('organization_id', 1)
    caller_role = session.get('role', 'contributor')
    if caller_role not in ('owner', 'admin'):
        return jsonify({'error': 'Forbidden: only organization owners and admins can update settings.'}), 403

    data = request.get_json(silent=True) or {}
    try:
        updated = database.update_organization_settings(
            organization_id=org_id,
            name=data.get('name'),
            timezone_name=data.get('timezone')
        )
        return jsonify({'status': 'success', 'settings': updated}), 200
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error updating org settings: {e}")
        return jsonify({'error': 'Failed to update organization settings'}), 500

@app.route('/api/org/members', methods=['GET'])
@login_required
def get_org_members_route():
    """Lists team members belonging to the active organization."""
    org_id = session.get('organization_id', 1)
    members = database.get_organization_members(org_id)
    return jsonify({'status': 'success', 'members': members}), 200

@app.route('/api/org/members', methods=['POST'])
@login_required
@csrf_protect
def add_org_member_route():
    """Adds a new team member to the organization. Restricted to owner or admin."""
    org_id = session.get('organization_id', 1)
    caller_role = session.get('role', 'contributor')
    if caller_role not in ('owner', 'admin'):
        return jsonify({'error': 'Forbidden: only owners and admins can add team members.'}), 403

    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'contributor')
    email = data.get('email')

    try:
        new_member = database.add_organization_member(
            organization_id=org_id,
            username=username,
            password=password,
            role=role,
            email=email
        )
        return jsonify({'status': 'success', 'member': new_member}), 201
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error adding organization member: {e}")
        return jsonify({'error': 'Failed to add organization member'}), 500

@app.route('/api/org/members/<int:member_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_org_member_route(member_id):
    """Updates team member role or active status. Restricted to owner or admin."""
    org_id = session.get('organization_id', 1)
    caller_role = session.get('role', 'contributor')
    if caller_role not in ('owner', 'admin'):
        return jsonify({'error': 'Forbidden: only owners and admins can modify team members.'}), 403

    data = request.get_json(silent=True) or {}
    try:
        updated = database.update_organization_member(
            organization_id=org_id,
            user_id=member_id,
            role=data.get('role'),
            is_active=data.get('is_active')
        )
        return jsonify({'status': 'success', 'member': updated}), 200
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error updating member #{member_id}: {e}")
        return jsonify({'error': 'Failed to update member'}), 500

# --- Central Media Library Endpoints ---

@app.route('/api/media', methods=['GET'])
@login_required
def get_media_assets_route():
    """Lists media library assets scoped to active organization with optional filters."""
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id')
    campaign_id = request.args.get('campaign_id')
    file_type = request.args.get('file_type')
    search = request.args.get('search')

    try:
        b_id = int(brand_id) if brand_id else None
        c_id = int(campaign_id) if campaign_id else None
        assets = database.get_media_assets(
            organization_id=org_id,
            brand_id=b_id,
            campaign_id=c_id,
            file_type=file_type,
            search=search
        )
        return jsonify({'status': 'success', 'assets': assets}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error fetching media assets: {e}")
        return jsonify({'error': 'Failed to retrieve media assets'}), 500

@app.route('/api/media/upload', methods=['POST'])
@login_required
@csrf_protect
def upload_media_asset_route():
    """Uploads a media asset to the organization media library with strict validation."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    original_name = os.path.basename(file.filename)
    extension = os.path.splitext(original_name)[1].lower()

    # Allowed extensions
    allowed_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mov', '.pdf'}
    if extension not in allowed_exts:
        return jsonify({'error': f'Unsupported file extension {extension}. Allowed: {sorted(list(allowed_exts))}'}), 400

    # Validate image integrity if it's an image
    if extension in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        try:
            with Image.open(file) as img:
                img.verify()
            file.seek(0)
        except Exception:
            return jsonify({'error': 'Invalid or corrupted image file'}), 400

    # Determine file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    # Enforce configured max file size limit (config.MAX_CONTENT_LENGTH, default 16MB)
    max_upload_bytes = getattr(config, 'MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
    if file_size > max_upload_bytes:
        max_mb = max_upload_bytes // (1024 * 1024)
        return jsonify({'error': f'File exceeds maximum permitted size of {max_mb}MB'}), 400

    # Determine file type
    if extension in {'.mp4', '.mov'}:
        file_type = 'video'
    elif extension == '.pdf':
        file_type = 'document'
    else:
        file_type = 'image'

    brand_id = request.form.get('brand_id')
    campaign_id = request.form.get('campaign_id')
    tags = request.form.get('tags')

    try:
        b_id = int(brand_id) if brand_id and str(brand_id).strip() else None
        c_id = int(campaign_id) if campaign_id and str(campaign_id).strip() else None

        safe_filename = f"asset_{int(time.time())}_{secrets.token_hex(4)}{extension}"
        save_path = Path(config.UPLOAD_FOLDER) / safe_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(save_path))

        asset = database.save_media_asset(
            organization_id=org_id,
            filename=safe_filename,
            original_name=original_name,
            brand_id=b_id,
            campaign_id=c_id,
            file_type=file_type,
            file_size=file_size,
            mime_type=file.content_type or '',
            tags=tags,
            created_by=user_id
        )
        return jsonify({'status': 'success', 'asset': asset}), 201

    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error saving media asset: {e}")
        return jsonify({'error': 'Failed to save media asset'}), 500

@app.route('/api/media/<int:asset_id>', methods=['DELETE'])
@login_required
@csrf_protect
def delete_media_asset_route(asset_id):
    """Deletes a media asset record and unlinks its file from storage."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    try:
        deleted = database.delete_media_asset(asset_id, organization_id=org_id)
        if deleted and deleted.get('filename'):
            fpath = Path(config.UPLOAD_FOLDER) / os.path.basename(deleted['filename'])
            if fpath.exists():
                try:
                    fpath.unlink()
                except Exception as e:
                    logger.warning(f"Could not unlink media file {fpath}: {e}")
        return jsonify({'status': 'success', 'deleted_id': asset_id}), 200
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error deleting media asset #{asset_id}: {e}")
        return jsonify({'error': 'Failed to delete media asset'}), 500

# --- Automation Task Control Endpoints ---

@app.route('/api/control/<post_type>/start', methods=['POST'])
@login_required
@csrf_protect
def start_task(post_type):
    """Starts automation loop for a post type."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid task type'}), 400

    # Persist desired state in database (multi-worker safe)
    database.set_task_state(post_type, is_running=True, status='Running')

    # If running in single-process mode (Termux / Dev), launch in-process thread
    if config.APP_ENV != 'production':
        _start_local_task(post_type)

    return jsonify({'status': f'{post_type} posting started', 'is_running': True}), 200

@app.route('/api/control/<post_type>/stop', methods=['POST'])
@login_required
@csrf_protect
def stop_task(post_type):
    """Stops automation loop for a post type."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid task type'}), 400

    database.set_task_state(post_type, is_running=False, status='Stopped')

    if config.APP_ENV != 'production':
        _stop_local_task(post_type)

    return jsonify({'status': f'{post_type} posting stopped', 'is_running': False}), 200

@app.route('/api/control/all/start', methods=['POST'])
@login_required
@csrf_protect
def start_all():
    """Starts all active automation tasks."""
    for p_type in ('tour', 'nz', 'gaatha', 'insta'):
        database.set_task_state(p_type, is_running=True, status='Running')
        if config.APP_ENV != 'production':
            _start_local_task(p_type)
    return jsonify({'status': 'All tasks started'}), 200

@app.route('/api/control/all/stop', methods=['POST'])
@login_required
@csrf_protect
def stop_all():
    """Stops all automation tasks."""
    for p_type in ('tour', 'nz', 'gaatha', 'insta'):
        database.set_task_state(p_type, is_running=False, status='Stopped')
        if config.APP_ENV != 'production':
            _stop_local_task(p_type)
    return jsonify({'status': 'All tasks stopped'}), 200

@app.route('/api/status', methods=['GET'])
@login_required
def get_status():
    """Retrieves current task statuses directly from the database."""
    states = database.get_all_task_states()
    response = {}
    for task_name in ('tour', 'nz', 'gaatha', 'insta'):
        t_state = states.get(task_name, {})
        response[f'{task_name}_running'] = t_state.get('is_running', False)
        response[f'{task_name}_status'] = t_state.get('status', 'Stopped')
        response[f'{task_name}_current_post'] = t_state.get('current_post_summary')
        response[f'{task_name}_interval'] = t_state.get('interval', 1800)
    controls = config.get_publishing_controls_summary()
    response['publishing_enabled'] = config.is_publishing_enabled()
    response['publishing_controls'] = controls
    response['publishing_platforms'] = controls['platforms']
    response['enabled_publishing_platforms'] = controls['allowed_platforms']
    return jsonify(response)

@app.route('/api/interval/<post_type>', methods=['GET'])
@login_required
def get_interval(post_type):
    """Retrieves posting interval for a task type."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy channel '{post_type}' is permanently retired and cannot be created.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    state = database.get_task_state(post_type) or {}
    return jsonify({'interval': state.get('interval', 1800)})

@app.route('/api/interval/<post_type>', methods=['PUT'])
@login_required
@csrf_protect
def set_interval(post_type):
    """Sets posting interval for a task type in seconds."""
    if post_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({'error': f"Legacy automation channel '{post_type}' is permanently retired.", 'code': 'LEGACY_CHANNEL_RETIRED'}), 400
    if post_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    interval = data.get('interval')
    if not interval or interval <= 0:
        return jsonify({'error': 'Invalid interval value'}), 400

    database.set_task_state(post_type, interval_seconds=interval)
    return jsonify({'success': True, 'interval': interval})

    return jsonify({'success': True, 'interval': interval})

# --- Calendar Scheduling API Endpoints ---

@app.route('/api/timezones', methods=['GET'])
@login_required
def get_timezones():
    """Lists standard supported IANA timezones and the active organization's default."""
    import timezone_utils
    org_id = session.get('organization_id', 1)
    org_tz = database.get_organization_timezone(org_id)
    return jsonify({
        'success': True,
        'default': org_tz,
        'timezones': timezone_utils.COMMON_TIMEZONES
    })

@app.route('/api/schedule', methods=['GET'])
@login_required
def get_scheduled():
    """Retrieves scheduled posts for the active organization with strict filtering and pagination."""
    post_type = request.args.get('post_type')
    status = request.args.get('status')
    brand_id = request.args.get('brand_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tz_param = request.args.get('timezone')
    raw_limit = request.args.get('limit', 100)
    raw_offset = request.args.get('offset', 0)
    envelope = request.args.get('envelope', '').lower() in ('1', 'true', 'yes')
    org_id = session.get('organization_id', 1)

    try:
        limit = int(raw_limit)
        if limit < 1 or limit > 500:
            return jsonify({'error': f"Limit must be between 1 and 500. Got: {limit}.", 'code': 'VALIDATION_ERROR'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': f"Limit must be an integer between 1 and 500. Got: '{raw_limit}'.", 'code': 'VALIDATION_ERROR'}), 400

    try:
        offset = int(raw_offset)
        if offset < 0:
            return jsonify({'error': f"Offset cannot be negative. Got: {offset}.", 'code': 'VALIDATION_ERROR'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': f"Offset must be a non-negative integer. Got: '{raw_offset}'.", 'code': 'VALIDATION_ERROR'}), 400

    if tz_param:
        try:
            timezone_utils.validate_timezone_name(tz_param)
        except ValueError as e:
            return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400

    if post_type and post_type not in VALID_POST_TYPES:
        return jsonify({'error': f"Invalid post_type: '{post_type}'. Must be one of: {', '.join(VALID_POST_TYPES)}.", 'code': 'VALIDATION_ERROR'}), 400

    if status and status not in database.VALID_POST_STATUSES:
        return jsonify({'error': f"Invalid status: '{status}'.", 'code': 'VALIDATION_ERROR'}), 400

    try:
        posts = database.get_scheduled_posts(
            organization_id=org_id,
            post_type=post_type,
            status=status,
            brand_id=brand_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
            target_timezone=tz_param
        )
        if envelope:
            resp = jsonify({
                'success': True,
                'posts': posts,
                'count': len(posts),
                'limit': limit,
                'offset': offset
            })
        else:
            resp = jsonify(posts)
        resp.headers['X-Limit'] = str(limit)
        resp.headers['X-Offset'] = str(offset)
        return resp
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error fetching scheduled posts: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/queue', methods=['GET'])
@login_required
def get_publishing_queue():
    """Retrieves upcoming posts queued for publishing (alias with scheduled status)."""
    post_type = request.args.get('post_type')
    brand_id = request.args.get('brand_id')
    raw_limit = request.args.get('limit', 50)
    raw_offset = request.args.get('offset', 0)
    tz_param = request.args.get('timezone')
    org_id = session.get('organization_id', 1)

    try:
        limit = int(raw_limit)
        if limit < 1 or limit > 500:
            return jsonify({'error': f"Limit must be between 1 and 500. Got: {limit}.", 'code': 'VALIDATION_ERROR'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': f"Limit must be an integer between 1 and 500. Got: '{raw_limit}'.", 'code': 'VALIDATION_ERROR'}), 400

    try:
        offset = int(raw_offset)
        if offset < 0:
            return jsonify({'error': f"Offset cannot be negative. Got: {offset}.", 'code': 'VALIDATION_ERROR'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': f"Offset must be a non-negative integer. Got: '{raw_offset}'.", 'code': 'VALIDATION_ERROR'}), 400

    if tz_param:
        try:
            timezone_utils.validate_timezone_name(tz_param)
        except ValueError as e:
            return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400

    try:
        posts = database.get_scheduled_posts(
            organization_id=org_id,
            post_type=post_type,
            status='scheduled',
            brand_id=brand_id,
            limit=limit,
            offset=offset,
            target_timezone=tz_param
        )
        return jsonify({
            'success': True,
            'posts': posts,
            'count': len(posts),
            'limit': limit,
            'offset': offset
        })
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error fetching publishing queue: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/schedule', methods=['POST'])
@login_required
@csrf_protect
def add_scheduled():
    """Schedules a post with strict validation, persistent date/time, and idempotency."""
    data = request.get_json() or {}
    post_type = data.get('post_type')
    clean_p_type = str(post_type).strip().lower() if post_type else ''
    if clean_p_type in RETIRED_LEGACY_CHANNELS:
        return jsonify({
            'error': f"Legacy channel '{clean_p_type}' is permanently retired and cannot be scheduled.",
            'code': 'LEGACY_CHANNEL_RETIRED'
        }), 400
    if not clean_p_type or clean_p_type not in CANONICAL_CREATION_PLATFORMS:
        return jsonify({'error': 'Invalid post type', 'code': 'INVALID_POST_TYPE'}), 400
    post_type = clean_p_type

    scheduled_for = data.get('scheduled_for')
    if scheduled_for is None or str(scheduled_for).strip() == "":
        return jsonify({'error': 'scheduled_for is required and cannot be empty', 'code': 'VALIDATION_ERROR'}), 400

    org_id = session.get('organization_id', 1)
    brand_id = data.get('brand_id')
    message = data.get('message', '').strip() if data.get('message') else ''
    image_filename = data.get('image_filename', '').strip() if data.get('image_filename') else None
    post_id = data.get('post_id')
    timezone_name = data.get('timezone')
    idempotency_key = data.get('idempotency_key')
    allow_past = bool(data.get('allow_past', False))
    raw_status = data.get('status')
    if raw_status is not None:
        if raw_status not in database.ALLOWED_INITIAL_STATUSES:
            return jsonify({
                'error': f"Invalid initial status '{raw_status}'. Allowed initial states: {', '.join(sorted(database.ALLOWED_INITIAL_STATUSES))}.",
                'code': 'VALIDATION_ERROR'
            }), 400
        initial_status = raw_status
    else:
        initial_status = 'scheduled'

    user_role = session.get('role', 'admin')
    if user_role == 'contributor' and initial_status == 'scheduled':
        return jsonify({
            'error': 'Users with contributor role cannot schedule directly; submission for approval is required.',
            'code': 'APPROVAL_REQUIRED'
        }), 403

    try:
        record = database.create_scheduled_post(
            post_type=post_type,
            scheduled_for=scheduled_for,
            message=message,
            image_filename=image_filename,
            post_id=post_id,
            organization_id=org_id,
            brand_id=brand_id,
            timezone_name=timezone_name,
            idempotency_key=idempotency_key,
            created_by=session.get('user_id'),
            initial_status=initial_status,
            allow_past=allow_past
        )
        return jsonify(record), 201
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error creating scheduled post: {e}")
        return jsonify({'error': 'Internal server error scheduling post'}), 500

@app.route('/api/schedule/<int:schedule_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_scheduled(schedule_id):
    """Updates a scheduled post with strict validation."""
    data = request.get_json() or {}
    org_id = session.get('organization_id', 1)
    try:
        success = database.update_scheduled_post(
            schedule_id=schedule_id,
            message=data.get('message'),
            image_filename=data.get('image_filename'),
            scheduled_for=data.get('scheduled_for'),
            timezone_name=data.get('timezone'),
            brand_id=data.get('brand_id'),
            organization_id=org_id,
            allow_past=bool(data.get('allow_past', False))
        )
        if not success:
            return jsonify({'error': 'Scheduled post not found or cannot be modified', 'code': 'NOT_FOUND'}), 404
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error updating scheduled post #{schedule_id}: {e}")
        return jsonify({'error': 'Internal server error updating post'}), 500

@app.route('/api/schedule/<int:schedule_id>', methods=['DELETE'])
@login_required
@csrf_protect
def cancel_scheduled(schedule_id):
    """Cancels a scheduled post scoped to organization."""
    org_id = session.get('organization_id', 1)
    try:
        success = database.cancel_scheduled_post(
            schedule_id=schedule_id,
            organization_id=org_id,
            user_id=session.get('user_id')
        )
        if not success:
            return jsonify({'error': 'Scheduled post not found or cannot be cancelled', 'code': 'NOT_FOUND'}), 404
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400

# --- Content Approvals & Lifecycle Endpoints ---

@app.route('/api/approvals/pending', methods=['GET'])
@login_required
def get_pending_approvals():
    """Retrieves posts in pending_approval status for the active organization."""
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id')
    post_type = request.args.get('post_type')
    posts = database.get_scheduled_posts(
        organization_id=org_id,
        status='pending_approval',
        brand_id=brand_id,
        post_type=post_type
    )
    return jsonify({'success': True, 'count': len(posts), 'posts': posts})

@app.route('/api/approvals/<int:schedule_id>/approve', methods=['POST'])
@login_required
@csrf_protect
def approve_post(schedule_id):
    """Approves a post in pending_approval status, transitioning it to scheduled."""
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        updated = database.transition_post_status(
            schedule_id=schedule_id,
            to_status='scheduled',
            user_id=user_id,
            reason='Content approved for publishing',
            organization_id=org_id
        )
        return jsonify({'success': True, 'post': updated})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error approving post #{schedule_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/approvals/<int:schedule_id>/reject', methods=['POST'])
@login_required
@csrf_protect
def reject_post(schedule_id):
    """Rejects a post in pending_approval status with mandatory reason."""
    data = request.get_json() or {}
    reason = data.get('reason', '').strip()
    if not reason:
        return jsonify({'error': 'A specific rejection reason is required', 'code': 'REASON_REQUIRED'}), 400

    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        updated = database.transition_post_status(
            schedule_id=schedule_id,
            to_status='rejected',
            user_id=user_id,
            reason=reason,
            organization_id=org_id
        )
        return jsonify({'success': True, 'post': updated})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error rejecting post #{schedule_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/schedule/<int:schedule_id>/history', methods=['GET'])
@login_required
def get_post_history(schedule_id):
    """Retrieves full audit trail of lifecycle transitions for a scheduled post."""
    org_id = session.get('organization_id', 1)
    history = database.get_post_audit_history(schedule_id, organization_id=org_id)
    if history is None:
        return jsonify({'error': 'Post not found or inaccessible', 'code': 'NOT_FOUND'}), 404
    return jsonify({'success': True, 'post_id': schedule_id, 'history': history})

@app.route('/api/schedule/<int:schedule_id>/retry', methods=['POST'])
@login_required
@csrf_protect
def retry_post(schedule_id):
    """Retries a failed scheduled post by returning it to scheduled queue."""
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        updated = database.retry_failed_post(schedule_id, user_id=user_id, organization_id=org_id)
        return jsonify({'success': True, 'post': updated})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error retrying post #{schedule_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/schedule/<int:schedule_id>/transition', methods=['POST'])
@login_required
@csrf_protect
def transition_post(schedule_id):
    """Direct lifecycle state transition endpoint (e.g. submit draft for approval)."""
    data = request.get_json() or {}
    to_status = data.get('status')
    reason = data.get('reason')
    if not to_status:
        return jsonify({'error': 'status is required', 'code': 'MISSING_STATUS'}), 400

    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        updated = database.transition_post_status(
            schedule_id=schedule_id,
            to_status=to_status,
            user_id=user_id,
            reason=reason,
            organization_id=org_id
        )
        return jsonify({'success': True, 'post': updated})
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error transitioning post #{schedule_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500


# --- Multi-Organization & Brand Workspaces Endpoints ---

@app.route('/api/organizations', methods=['GET'])
@login_required
def get_organizations():
    """Lists active organizations."""
    orgs = database.list_organizations()
    return jsonify(orgs)

@app.route('/api/brands', methods=['GET'])
@login_required
def get_brands():
    """Lists brand workspaces for the current organization."""
    org_id = session.get('organization_id', 1)
    brands = database.get_brands_by_organization(org_id)
    return jsonify(brands)

@app.route('/api/brands/<int:brand_id>', methods=['GET'])
@login_required
def get_brand(brand_id):
    """Retrieves a single brand workspace scoped to the active organization."""
    org_id = session.get('organization_id', 1)
    brand = database.get_brand_by_id(brand_id, organization_id=org_id)
    if not brand:
        return jsonify({'error': 'Brand not found'}), 404
    return jsonify(brand)

@app.route('/api/brands/<int:brand_id>/profile', methods=['GET'])
@login_required
def get_brand_profile(brand_id):
    """Retrieves the AI marketing profile for a brand."""
    org_id = session.get('organization_id', 1)
    try:
        profile = database.get_brand_marketing_profile(brand_id, organization_id=org_id)
        if not profile:
            return jsonify({'brand_id': brand_id, 'organization_id': org_id, 'profile': None})
        return jsonify({'brand_id': brand_id, 'organization_id': org_id, 'profile': profile})
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/brands/<int:brand_id>/profile', methods=['POST'])
@login_required
@csrf_protect
def save_brand_profile(brand_id):
    """Creates or updates the brand marketing profile."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    try:
        updated = database.upsert_brand_marketing_profile(
            brand_id=brand_id,
            organization_id=org_id,
            positioning=data.get('positioning'),
            target_audiences=data.get('target_audiences'),
            target_markets=data.get('target_markets'),
            languages=data.get('languages'),
            voice_and_tone=data.get('voice_and_tone'),
            messaging_guidelines=data.get('messaging_guidelines'),
            approved_product_facts=data.get('approved_product_facts'),
            prohibited_claims=data.get('prohibited_claims'),
            preferred_ctas=data.get('preferred_ctas'),
            website_and_social_links=data.get('website_and_social_links')
        )
        return jsonify({'status': 'saved', 'profile': updated}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error saving brand profile: {e}")
        return jsonify({'error': 'Failed to save brand marketing profile'}), 500

# --- Growth & Intelligence: Property Registry Endpoints ---

@app.route('/api/growth/properties', methods=['GET'])
@login_required
def get_growth_properties():
    """Lists all ecosystem growth properties for the active organization."""
    org_id = session.get('organization_id', 1)
    include_inactive = request.args.get('include_inactive', 'true').lower() in ('true', '1', 'yes')
    try:
        props = database.list_growth_properties(organization_id=org_id, include_inactive=include_inactive)
        if request.args.get('envelope') == '1':
            return jsonify({'properties': props, 'count': len(props), 'organization_id': org_id})
        return jsonify(props)
    except Exception as e:
        logger.error(f"Error fetching growth properties: {e}")
        return jsonify({'error': 'Failed to retrieve growth properties'}), 500

@app.route('/api/growth/properties/<int:property_id>', methods=['GET'])
@login_required
def get_growth_property(property_id):
    """Retrieves a single growth property scoped to the active organization."""
    org_id = session.get('organization_id', 1)
    prop = database.get_growth_property_by_id(property_id, organization_id=org_id)
    if not prop:
        return jsonify({'error': 'Property not found'}), 404
    return jsonify(prop)

@app.route('/api/growth/properties', methods=['POST'])
@login_required
@csrf_protect
def create_growth_property_route():
    """Registers a new ecosystem property for the active organization."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    try:
        created = database.create_growth_property(organization_id=org_id, data=data)
        return jsonify(created), 201
    except ValueError as e:
        msg = str(e)
        status_code = 409 if 'already exists' in msg else 400
        return jsonify({'error': msg}), status_code
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 403
    except Exception as e:
        logger.error(f"Error creating growth property: {e}")
        return jsonify({'error': 'Failed to create growth property'}), 500

@app.route('/api/growth/properties/<int:property_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_growth_property_route(property_id):
    """Updates an existing ecosystem property scoped to the active organization."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    try:
        updated = database.update_growth_property(property_id=property_id, organization_id=org_id, data=data)
        return jsonify(updated), 200
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        msg = str(e)
        if 'does not exist' in msg:
            return jsonify({'error': msg}), 404
        status_code = 409 if 'already in use' in msg else 400
        return jsonify({'error': msg}), status_code
    except Exception as e:
        logger.error(f"Error updating growth property: {e}")
        return jsonify({'error': 'Failed to update growth property'}), 500

@app.route('/api/growth/properties/<int:property_id>/status', methods=['PATCH'])
@login_required
@csrf_protect
def update_growth_property_status_route(property_id):
    """Enables or disables an ecosystem property scoped to the active organization."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    is_active = data.get('is_active')
    if is_active is None and 'status' in data:
        is_active = (str(data['status']).lower() == 'active')
    if is_active is None:
        return jsonify({'error': "Missing 'is_active' or 'status' in request body."}), 400
    try:
        updated = database.update_growth_property_status(property_id=property_id, organization_id=org_id, is_active=is_active)
        return jsonify(updated), 200
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error updating growth property status: {e}")
        return jsonify({'error': 'Failed to update property status'}), 500

# --- AI Marketing Studio: Campaigns & Content Generation Endpoints ---

@app.route('/api/campaigns', methods=['GET'])
@login_required
def get_campaigns():
    """Lists campaigns for the active organization with optional filters."""
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id', type=int)
    status = request.args.get('status')
    limit = max(1, min(request.args.get('limit', default=100, type=int), 100))
    offset = max(request.args.get('offset', default=0, type=int), 0)
    try:
        campaigns = database.list_campaigns(
            organization_id=org_id,
            brand_id=brand_id,
            status=status,
            limit=limit,
            offset=offset
        )
        return jsonify(campaigns)
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/campaigns', methods=['POST'])
@login_required
@csrf_protect
def add_campaign():
    """Creates a new campaign strictly scoped to organization and brand."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    
    brand_id = data.get('brand_id')
    name = data.get('name')
    objective = data.get('objective')
    brief = data.get('brief')

    allowed, usage, limit, msg = database.check_organization_quota(org_id, 'campaign')
    if not allowed:
        return jsonify({
            'error': msg,
            'code': 'PLAN_QUOTA_EXCEEDED',
            'resource': 'campaign',
            'usage': usage,
            'limit': limit
        }), 402

    if not brand_id:
        return jsonify({'error': 'brand_id is required'}), 400
    if not name or not str(name).strip():
        return jsonify({'error': 'Campaign name is required'}), 400
    if not objective or not str(objective).strip():
        return jsonify({'error': 'Campaign objective is required'}), 400
    if not brief or not str(brief).strip():
        return jsonify({'error': 'Campaign brief is required'}), 400

    try:
        camp = database.create_campaign(
            organization_id=org_id,
            brand_id=brand_id,
            name=name,
            objective=objective,
            brief=brief,
            campaign_type=data.get('campaign_type', 'social'),
            target_audience=data.get('target_audience'),
            target_markets=data.get('target_markets'),
            languages=data.get('languages'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            status=data.get('status', 'draft'),
            budget=data.get('budget'),
            created_by=user_id
        )
        return jsonify(camp), 201
    except (database.TenantIsolationError, ValueError) as e:
        status_code = 404 if 'Tenant' in type(e).__name__ or 'ownership' in str(e).lower() else 400
        return jsonify({'error': str(e)}), status_code
    except Exception as e:
        logger.error(f"Error creating campaign: {e}")
        return jsonify({'error': 'Failed to create campaign'}), 500

@app.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
@login_required
def get_campaign(campaign_id):
    """Retrieves a single campaign by ID."""
    org_id = session.get('organization_id', 1)
    camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404
    return jsonify(camp)

@app.route('/api/campaigns/<int:campaign_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_campaign_route(campaign_id):
    """Updates campaign fields with mass-assignment protection."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}

    protected_keys = {'id', 'organization_id', 'created_by', 'created_at'}
    attempted_protected = [k for k in protected_keys if k in data]
    if attempted_protected:
        return jsonify({
            'error': f"Protected campaign field(s) cannot be modified: {', '.join(attempted_protected)}.",
            'code': 'PROTECTED_FIELD_TAMPERING'
        }), 400

    try:
        updated = database.update_campaign(
            campaign_id=campaign_id,
            organization_id=org_id,
            brand_id=data.get('brand_id'),
            name=data.get('name'),
            objective=data.get('objective'),
            brief=data.get('brief'),
            campaign_type=data.get('campaign_type'),
            target_audience=data.get('target_audience'),
            target_markets=data.get('target_markets'),
            languages=data.get('languages'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            status=data.get('status'),
            budget=data.get('budget')
        )
        if not updated:
            return jsonify({'error': 'Campaign not found or update failed'}), 404
        return jsonify(updated)
    except (database.TenantIsolationError, ValueError) as e:
        status_code = 404 if 'Tenant' in type(e).__name__ or 'ownership' in str(e).lower() else 400
        return jsonify({'error': str(e)}), status_code
    except Exception as e:
        logger.error(f"Error updating campaign: {e}")
        return jsonify({'error': 'Failed to update campaign'}), 500

@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@login_required
@csrf_protect
def delete_campaign_route(campaign_id):
    """Deletes a campaign and its associated drafts."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    try:
        deleted = database.delete_campaign(campaign_id, organization_id=org_id)
        if not deleted:
            return jsonify({'error': 'Campaign not found'}), 404
        return jsonify({'status': 'deleted', 'campaign_id': campaign_id})
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/campaigns/<int:campaign_id>/strategy', methods=['GET'])
@login_required
def get_campaign_strategy_route(campaign_id):
    """Retrieves existing strategy for a campaign."""
    org_id = session.get('organization_id', 1)
    try:
        strat = database.get_campaign_strategy(campaign_id, organization_id=org_id)
        if not strat:
            return jsonify({'error': 'Campaign strategy not found'}), 404
        return jsonify(strat), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/campaigns/<int:campaign_id>/strategy', methods=['POST'])
@login_required
@csrf_protect
def generate_campaign_strategy_route(campaign_id):
    """Generates or regenerates an AI marketing strategy for a campaign."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}

    try:
        camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
        if not camp:
            return jsonify({'error': 'Campaign not found'}), 404

        brand = database.get_brand_by_id(camp['brand_id'], organization_id=org_id)
        if not brand:
            return jsonify({'error': 'Associated brand not found'}), 404

        profile = database.get_brand_marketing_profile(camp['brand_id'], organization_id=org_id) or {}
        brand_info = {
            'name': brand.get('name', 'Brand'),
            'description': brand.get('description', ''),
            'positioning': profile.get('positioning') or brand.get('description', ''),
            'voice_and_tone': profile.get('voice_and_tone', 'Professional, authoritative, customer-focused'),
            'messaging_guidelines': profile.get('messaging_guidelines', ''),
            'approved_product_facts': profile.get('approved_product_facts', ''),
            'prohibited_claims': profile.get('prohibited_claims', ''),
            'preferred_ctas': profile.get('preferred_ctas', '')
        }

        provider_name = data.get('provider')
        model_name = data.get('model')
        ai_provider = ai_service.get_ai_provider(provider_name=provider_name, model=model_name)

        strategy_dict = ai_service.generate_campaign_strategy(
            provider=ai_provider,
            brand_info=brand_info,
            campaign_info=camp,
            model=model_name
        )

        saved = database.save_campaign_strategy(
            organization_id=org_id,
            brand_id=camp['brand_id'],
            campaign_id=campaign_id,
            strategy_data=strategy_dict
        )

        database.log_ai_usage(
            organization_id=org_id,
            brand_id=camp['brand_id'],
            campaign_id=campaign_id,
            provider=provider_name or 'mock',
            model=model_name or 'mock-v1',
            prompt_tokens=350,
            completion_tokens=450,
            total_tokens=800,
            success=True
        )
        return jsonify({'success': True, 'strategy': saved}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except ai_service.AIConfigurationError as e:
        database.log_ai_usage(organization_id=org_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e)}), 400
    except ai_service.AIRateLimitError as e:
        database.log_ai_usage(organization_id=org_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'RATE_LIMIT_EXCEEDED'}), 429
    except ai_service.AITimeoutError as e:
        database.log_ai_usage(organization_id=org_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'PROVIDER_TIMEOUT'}), 504
    except ai_service.AIProviderError as e:
        database.log_ai_usage(organization_id=org_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'PROVIDER_ERROR'}), 502
    except Exception as e:
        logger.error(f"Error generating campaign strategy: {e}")
        return jsonify({'error': 'Failed to generate campaign strategy'}), 500

@app.route('/api/campaigns/<int:campaign_id>/strategy', methods=['PUT'])
@login_required
@csrf_protect
def update_campaign_strategy_route(campaign_id):
    """Manually updates or customizes sections of a campaign strategy."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}

    try:
        camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
        if not camp:
            return jsonify({'error': 'Campaign not found'}), 404

        saved = database.save_campaign_strategy(
            organization_id=org_id,
            brand_id=camp['brand_id'],
            campaign_id=campaign_id,
            strategy_data=data
        )
        return jsonify({'success': True, 'strategy': saved}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error updating campaign strategy: {e}")
        return jsonify({'error': 'Failed to update campaign strategy'}), 500


@app.route('/api/campaigns/<int:campaign_id>/planner', methods=['POST'])
@login_required
@csrf_protect
def generate_campaign_content_plan_route(campaign_id):
    """Generates an intelligent weekly or monthly editorial content plan for a campaign."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    period_type = str(data.get('period_type', 'weekly')).strip().lower()
    if period_type not in ('weekly', 'monthly'):
        period_type = 'weekly'

    start_date = data.get('start_date')
    platforms = data.get('platforms')
    provider_name = data.get('provider')
    model_name = data.get('model')

    try:
        camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
        if not camp:
            return jsonify({'error': 'Campaign not found'}), 404

        brand = database.get_brand_by_id(camp['brand_id'], organization_id=org_id)
        if not brand:
            return jsonify({'error': 'Associated brand not found'}), 404

        profile = database.get_brand_marketing_profile(camp['brand_id'], organization_id=org_id) or {}
        brand_info = {
            'id': brand['id'],
            'name': brand['name'],
            'voice_tone': profile.get('voice_tone', 'Professional and engaging'),
            'prohibited_claims': profile.get('prohibited_claims', '')
        }

        ai_provider = ai_service.get_ai_provider(provider_name=provider_name, model=model_name)
        plan_dict = ai_service.generate_content_plan(
            provider=ai_provider,
            brand_info=brand_info,
            campaign_info=camp,
            period_type=period_type,
            start_date=start_date,
            platforms=platforms,
            model=model_name
        )

        entries = plan_dict.get('entries') or []
        s_date = entries[0]['suggested_date'] if entries else (start_date or 'today')
        e_date = entries[-1]['suggested_date'] if entries else s_date

        saved_plan = database.create_content_plan(
            organization_id=org_id,
            brand_id=camp['brand_id'],
            campaign_id=campaign_id,
            period_type=period_type,
            start_date=s_date,
            end_date=e_date,
            entries=entries,
            posting_frequency=plan_dict.get('posting_frequency'),
            created_by=session.get('user_id')
        )

        database.log_ai_usage(
            organization_id=org_id,
            brand_id=camp['brand_id'],
            campaign_id=campaign_id,
            provider=provider_name or 'mock',
            model=model_name or 'mock-v1',
            prompt_tokens=400,
            completion_tokens=600,
            total_tokens=1000,
            success=True
        )

        return jsonify({
            'status': 'success',
            'plan': saved_plan,
            'content_plan': saved_plan,
            'entries': saved_plan.get('entries', [])
        }), 201

    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except ai_service.AIRateLimitError as e:
        return jsonify({'error': str(e)}), 429
    except ai_service.AIConfigurationError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating campaign content plan: {e}")
        return jsonify({'error': 'Failed to generate campaign content plan'}), 500

@app.route('/api/campaigns/<int:campaign_id>/plans', methods=['GET'])
@login_required
def get_campaign_content_plans_route(campaign_id):
    """Retrieves all editorial content plans created for a campaign."""
    org_id = session.get('organization_id', 1)
    try:
        camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
        if not camp:
            return jsonify({'error': 'Campaign not found'}), 404
        plans = database.get_content_plans(organization_id=org_id, campaign_id=campaign_id)
        return jsonify({'status': 'success', 'plans': plans}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error retrieving content plans: {e}")
        return jsonify({'error': 'Failed to retrieve content plans'}), 500

@app.route('/api/plans/<int:plan_id>', methods=['GET'])
@login_required
def get_content_plan_by_id_route(plan_id):
    """Retrieves a single editorial content plan and all its calendar entries."""
    org_id = session.get('organization_id', 1)
    try:
        plan = database.get_content_plan_by_id(plan_id, organization_id=org_id)
        if not plan:
            return jsonify({'error': 'Content plan not found'}), 404
        return jsonify({'status': 'success', 'plan': plan}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error retrieving content plan {plan_id}: {e}")
        return jsonify({'error': 'Failed to retrieve content plan'}), 500

@app.route('/api/plans/entries/<int:entry_id>/convert', methods=['POST'])
@login_required
@csrf_protect
def convert_plan_entry_to_draft_route(entry_id):
    """Converts a planned content plan entry into an editable content draft."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        draft = database.convert_plan_entry_to_draft(entry_id, organization_id=org_id, user_id=user_id)
        return jsonify({'status': 'success', 'draft': draft}), 201
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error converting plan entry {entry_id} to draft: {e}")
        return jsonify({'error': 'Failed to convert plan entry to draft'}), 500

@app.route('/api/content-plans/<int:plan_id>/convert-drafts', methods=['POST'])
@login_required
@csrf_protect
def convert_all_plan_drafts_route(plan_id):
    """Converts all planned entries in a content plan into content drafts."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        drafts = database.convert_all_plan_entries_to_drafts(plan_id, organization_id=org_id, user_id=user_id)
        return jsonify({'status': 'success', 'drafts': drafts, 'drafts_count': len(drafts)}), 201
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error converting content plan #{plan_id} to drafts: {e}")
        return jsonify({'error': 'Failed to convert plan to drafts'}), 500

_RECENT_GENERATION_CACHE = {}  # {key: (timestamp, status_code, response_data)}

def _get_deduplicated_generation(key, window_seconds=15):
    """Retrieves cached generation result if within the deduplication window."""
    now = time.time()
    stale_keys = [k for k, (t, _, _) in _RECENT_GENERATION_CACHE.items() if now - t > window_seconds * 2]
    for k in stale_keys:
        _RECENT_GENERATION_CACHE.pop(k, None)

    if key in _RECENT_GENERATION_CACHE:
        timestamp, status_code, cached_res = _RECENT_GENERATION_CACHE[key]
        if now - timestamp < window_seconds:
            return status_code, cached_res
    return None, None

def _store_deduplicated_generation(key, status_code, response_data):
    """Stores generation result in the deduplication cache."""
    _RECENT_GENERATION_CACHE[key] = (time.time(), status_code, response_data)

@app.route('/api/campaigns/<int:campaign_id>/generate', methods=['POST'])
@login_required
@csrf_protect
def generate_campaign_content_route(campaign_id):
    """
    Generates AI marketing copy for the campaign across specified target platforms.
    Enforces input validation, rate limiting, token limits, idempotency deduplication,
    and partial failure preservation.
    """
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}

    # Check monthly token quota
    allowed, usage, limit, msg = database.check_organization_quota(org_id, 'ai_token')
    if not allowed:
        return jsonify({
            'error': msg,
            'code': 'PLAN_QUOTA_EXCEEDED',
            'resource': 'ai_token',
            'usage': usage,
            'limit': limit
        }), 402

    # Check organizational hourly rate limit
    hourly_limit = getattr(config, 'AI_ORG_HOURLY_GENERATION_LIMIT', 60)
    hourly_count = database.get_organization_ai_generation_count(org_id, window_seconds=3600)
    if hourly_count >= hourly_limit:
        return jsonify({
            'error': f'Organization hourly AI generation limit of {hourly_limit} requests reached. Please try again later.',
            'code': 'RATE_LIMIT_EXCEEDED'
        }), 429

    camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404

    brand = database.get_brand_by_id(camp['brand_id'], organization_id=org_id)
    if not brand:
        return jsonify({'error': 'Associated brand not found'}), 404

    # Validate target platforms: mandatory non-empty list if provided, or default to all supported
    req_platforms = data.get('platforms')
    if req_platforms is None:
        raw_list = ['facebook', 'instagram', 'linkedin', 'x', 'whatsapp']
    elif not isinstance(req_platforms, list) or len(req_platforms) == 0:
        return jsonify({
            'error': 'A non-empty list of target platforms is required.',
            'code': 'VALIDATION_ERROR'
        }), 400
    else:
        raw_list = req_platforms

    max_plats = getattr(config, 'AI_MAX_PLATFORMS_PER_REQUEST', 5)
    if len(raw_list) > max_plats:
        return jsonify({
            'error': f'Cannot request more than {max_plats} platforms in a single generation call.',
            'code': 'LIMIT_EXCEEDED'
        }), 400

    seen_plats = set()
    cleaned_platforms = []
    for p in raw_list:
        if not isinstance(p, str) or not p.strip():
            return jsonify({
                'error': 'Each platform entry must be a non-empty string.',
                'code': 'VALIDATION_ERROR'
            }), 400
        clean_p = p.strip().lower()
        if clean_p in seen_plats:
            return jsonify({
                'error': f"Duplicate platform '{clean_p}' specified in request.",
                'code': 'VALIDATION_ERROR'
            }), 400
        if clean_p not in database.VALID_DRAFT_PLATFORMS:
            return jsonify({
                'error': f"Unsupported platform '{p}'. Allowed: {', '.join(sorted(database.VALID_DRAFT_PLATFORMS))}.",
                'code': 'VALIDATION_ERROR'
            }), 400
        seen_plats.add(clean_p)
        cleaned_platforms.append(clean_p)

    # Validate language
    raw_lang = data.get('language') or camp.get('languages') or 'en'
    if not isinstance(raw_lang, str) or not raw_lang.strip() or len(raw_lang.strip()) > 15:
        return jsonify({'error': 'Invalid language format.', 'code': 'VALIDATION_ERROR'}), 400
    language = raw_lang.strip()

    # Validate content format
    VALID_FORMATS = {'post', 'reel', 'story', 'article', 'newsletter', 'message'}
    raw_format = str(data.get('content_format') or 'post').strip().lower()
    if raw_format not in VALID_FORMATS:
        return jsonify({
            'error': f"Invalid content format '{raw_format}'. Allowed: {', '.join(sorted(VALID_FORMATS))}.",
            'code': 'VALIDATION_ERROR'
        }), 400
    content_format = raw_format

    # Idempotency deduplication check
    dedup_window = getattr(config, 'AI_DEDUPLICATION_WINDOW_SECONDS', 15)
    idem_key = request.headers.get('X-Idempotency-Key') or data.get('idempotency_key')
    if not idem_key:
        idem_key = hashlib.sha256(
            f"{org_id}:{campaign_id}:{','.join(sorted(cleaned_platforms))}:{language}:{content_format}".encode()
        ).hexdigest()

    cached_status, cached_res = _get_deduplicated_generation(idem_key, window_seconds=dedup_window)
    if cached_res is not None:
        logger.info(f"Returning deduplicated generation response for campaign #{campaign_id} (key: {idem_key[:12]}...)")
        return jsonify(cached_res), cached_status

    profile = database.get_brand_marketing_profile(camp['brand_id'], organization_id=org_id) or {}
    brand_info = {
        'name': brand.get('name', 'Brand'),
        'description': brand.get('description', ''),
        'positioning': profile.get('positioning') or brand.get('description', ''),
        'voice_and_tone': profile.get('voice_and_tone', 'Professional, authoritative, customer-focused'),
        'messaging_guidelines': profile.get('messaging_guidelines', ''),
        'approved_product_facts': profile.get('approved_product_facts', ''),
        'prohibited_claims': profile.get('prohibited_claims', ''),
        'preferred_ctas': profile.get('preferred_ctas', '')
    }

    provider_name = data.get('provider')
    model_name = data.get('model')

    try:
        ai_provider = ai_service.get_ai_provider(provider_name=provider_name, model=model_name)
    except ai_service.AIConfigurationError as e:
        return jsonify({'error': str(e)}), 400

    generated_drafts = []
    errors = []

    for plat in cleaned_platforms:
        try:
            gen_res = ai_service.generate_campaign_content(
                provider=ai_provider,
                brand_info=brand_info,
                campaign_info=camp,
                target_platform=plat,
                language=language,
                content_format=content_format,
                model=model_name
            )

            created_draft = database.create_content_draft(
                organization_id=org_id,
                brand_id=camp['brand_id'],
                campaign_id=campaign_id,
                target_platform=plat,
                caption=gen_res.caption,
                headline=gen_res.headline,
                hashtags=gen_res.hashtags,
                call_to_action=gen_res.call_to_action,
                language=language,
                content_format=content_format,
                ai_provider=gen_res.ai_provider,
                ai_model=gen_res.ai_model,
                metadata=gen_res.metadata,
                status='draft',
                created_by=user_id
            )
            generated_drafts.append(created_draft)

            meta = getattr(gen_res, 'metadata', {}) or {}
            database.log_ai_usage(
                organization_id=org_id,
                brand_id=camp['brand_id'],
                campaign_id=campaign_id,
                provider=gen_res.ai_provider or provider_name or 'mock',
                model=gen_res.ai_model,
                prompt_tokens=meta.get('prompt_tokens', 120),
                completion_tokens=meta.get('completion_tokens', 80),
                total_tokens=meta.get('total_tokens', 200),
                success=True
            )
        except ai_service.AIRateLimitError as e:
            logger.warning(f"AI rate limit during generation for {plat}: {e}")
            errors.append({'platform': plat, 'error': str(e), 'code': 429})
            database.log_ai_usage(organization_id=org_id, brand_id=camp['brand_id'], campaign_id=campaign_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        except ai_service.AITimeoutError as e:
            logger.warning(f"AI timeout during generation for {plat}: {e}")
            errors.append({'platform': plat, 'error': str(e), 'code': 504})
            database.log_ai_usage(organization_id=org_id, brand_id=camp['brand_id'], campaign_id=campaign_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        except (ai_service.AIResponseValidationError, ai_service.AIProviderError) as e:
            logger.error(f"AI error during generation for {plat}: {e}")
            errors.append({'platform': plat, 'error': str(e), 'code': 502})
            database.log_ai_usage(organization_id=org_id, brand_id=camp['brand_id'], campaign_id=campaign_id, provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))

    if not generated_drafts and errors:
        primary_err = errors[0]
        return jsonify({'error': primary_err['error'], 'details': errors}), primary_err['code']

    status_str = 'partial_success' if errors else 'success'
    status_code = 207 if errors else 201
    resp_body = {
        'status': status_str,
        'campaign_id': campaign_id,
        'drafts': generated_drafts,
        'errors': errors
    }
    _store_deduplicated_generation(idem_key, status_code, resp_body)
    return jsonify(resp_body), status_code

@app.route('/api/drafts', methods=['GET'])
@login_required
def get_all_drafts():
    """Retrieves all drafts for the active organization with optional filtering by brand, platform, status."""
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id', type=int)
    campaign_id = request.args.get('campaign_id', type=int)
    target_platform = request.args.get('platform') or request.args.get('target_platform')
    status = request.args.get('status')
    limit = max(1, min(request.args.get('limit', default=100, type=int), 100))
    offset = max(request.args.get('offset', default=0, type=int), 0)
    drafts = database.list_content_drafts(
        organization_id=org_id,
        campaign_id=campaign_id,
        brand_id=brand_id,
        target_platform=target_platform,
        status=status,
        limit=limit,
        offset=offset
    )
    return jsonify({
        'success': True,
        'drafts': drafts,
        'count': len(drafts),
        'limit': limit,
        'offset': offset
    })

@app.route('/api/drafts', methods=['POST'])
@login_required
@csrf_protect
def create_draft_endpoint():
    """Creates a new draft post with brand, platform, and optional media association."""
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}

    brand_id = data.get('brand_id') or 1
    platform = str(data.get('platform') or data.get('target_platform') or 'facebook').strip().lower()
    caption = data.get('caption') or data.get('content') or data.get('message') or ''
    headline = data.get('headline')
    hashtags = data.get('hashtags')
    cta = data.get('call_to_action') or data.get('cta')
    media_asset_id = data.get('media_asset_id')
    status = data.get('status') or 'draft'
    user_id = session.get('user_id')

    if not caption.strip():
        return jsonify({'error': 'Draft caption cannot be empty', 'code': 'VALIDATION_ERROR'}), 400

    try:
        brand_id = int(brand_id)
        brand = database.get_brand_by_id(brand_id, organization_id=org_id)
        if not brand:
            return jsonify({'error': f'Brand #{brand_id} not found in active organization', 'code': 'NOT_FOUND'}), 404

        campaign_id = data.get('campaign_id')
        if not campaign_id:
            with database.get_db_connection() as conn:
                row = conn.execute(
                    "SELECT id FROM campaigns WHERE organization_id = ? AND brand_id = ? ORDER BY id ASC LIMIT 1",
                    (org_id, brand_id)
                ).fetchone()
                if row:
                    campaign_id = row['id']
                else:
                    cur = conn.execute(
                        "INSERT INTO campaigns (organization_id, brand_id, name, brief, status) VALUES (?, ?, ?, ?, 'active')",
                        (org_id, brand_id, f"{brand['name']} General Content", "Default campaign for publishing drafts")
                    )
                    campaign_id = cur.lastrowid
                    conn.commit()

        draft = database.create_content_draft(
            organization_id=org_id,
            brand_id=brand_id,
            campaign_id=campaign_id,
            target_platform=platform,
            caption=caption,
            headline=headline,
            hashtags=hashtags,
            call_to_action=cta,
            status=status,
            created_by=user_id,
            media_asset_id=media_asset_id
        )
        return jsonify({'success': True, 'draft': draft}), 201
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error creating draft: {e}")
        return jsonify({'error': 'Failed to create draft', 'code': 'SERVER_ERROR'}), 500

@app.route('/api/campaigns/<int:campaign_id>/drafts', methods=['GET'])
@login_required
def get_campaign_drafts(campaign_id):
    """Retrieves all drafts created under a campaign with pagination limits."""
    org_id = session.get('organization_id', 1)
    camp = database.get_campaign_by_id(campaign_id, organization_id=org_id)
    if not camp:
        return jsonify({'error': 'Campaign not found'}), 404
    limit = max(1, min(request.args.get('limit', default=100, type=int), 100))
    offset = max(request.args.get('offset', default=0, type=int), 0)
    drafts = database.list_content_drafts(organization_id=org_id, campaign_id=campaign_id, limit=limit, offset=offset)
    return jsonify(drafts)

@app.route('/api/drafts/<int:draft_id>', methods=['GET'])
@login_required
def get_draft(draft_id):
    """Retrieves a single draft by ID."""
    org_id = session.get('organization_id', 1)
    draft = database.get_content_draft_by_id(draft_id, organization_id=org_id)
    if not draft:
        return jsonify({'error': 'Draft not found'}), 404
    return jsonify(draft)

@app.route('/api/drafts/<int:draft_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_draft(draft_id):
    """Updates editable draft copy, headline, hashtags, or CTA with mass-assignment protection and revision tracking."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}

    protected_draft_keys = {'id', 'organization_id', 'campaign_id', 'brand_id', 'created_by', 'created_at'}
    attempted_protected = [k for k in protected_draft_keys if k in data]
    if attempted_protected:
        return jsonify({
            'error': f"Protected draft field(s) cannot be modified: {', '.join(attempted_protected)}.",
            'code': 'PROTECTED_FIELD_TAMPERING'
        }), 400

    try:
        updated = database.update_content_draft(
            draft_id=draft_id,
            organization_id=org_id,
            caption=data.get('caption'),
            headline=data.get('headline'),
            hashtags=data.get('hashtags'),
            call_to_action=data.get('call_to_action'),
            content_format=data.get('content_format'),
            status=data.get('status'),
            allow_privileged_status=False,
            expected_revision=data.get('expected_revision'),
            edited_by=user_id,
            change_source=data.get('change_source', 'manual_edit'),
            change_summary=data.get('change_summary'),
            media_asset_id=data.get('media_asset_id')
        )
        if not updated:
            return jsonify({'error': 'Draft not found'}), 404
        return jsonify(updated)
    except database.ConcurrencyConflictError as e:
        return jsonify({'error': str(e), 'code': 'CONCURRENT_EDIT_CONFLICT'}), 409
    except (database.TenantIsolationError, ValueError) as e:
        status_code = 404 if 'Tenant' in type(e).__name__ or 'ownership' in str(e).lower() else 400
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), status_code
    except Exception as e:
        logger.error(f"Error updating draft: {e}")
        return jsonify({'error': 'Failed to update draft'}), 500


@app.route('/api/drafts/<int:draft_id>/validate-creative', methods=['POST', 'GET'])
@login_required
@csrf_protect
def validate_draft_creative_route(draft_id):
    """Validates draft creative, character counts, hashtags, and media attachments against platform rules."""
    org_id = session.get('organization_id', 1)
    draft = database.get_content_draft_by_id(draft_id, organization_id=org_id)
    if not draft:
        return jsonify({'error': 'Draft not found'}), 404

    media_asset = None
    if draft.get('media_asset_id'):
        media_asset = database.get_media_asset_by_id(draft['media_asset_id'], organization_id=org_id)

    is_valid, issues = validate_platform_creative(
        platform=draft.get('target_platform'),
        caption=draft.get('caption', ''),
        headline=draft.get('headline', ''),
        hashtags=draft.get('hashtags', ''),
        media_asset=media_asset,
        content_format=draft.get('content_format', 'post')
    )
    return jsonify({
        'status': 'success',
        'is_valid': is_valid,
        'valid': is_valid,
        'issues': issues,
        'platform': draft.get('target_platform'),
        'has_media': media_asset is not None
    }), 200

@app.route('/api/drafts/<int:draft_id>/revisions', methods=['GET'])
@login_required
def get_draft_revisions_route(draft_id):
    """Retrieves full immutable revision audit history for a draft."""
    org_id = session.get('organization_id', 1)
    try:
        revisions = database.list_draft_revisions(draft_id, organization_id=org_id)
        return jsonify({'draft_id': draft_id, 'revisions': revisions, 'count': len(revisions)})
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error fetching revisions for draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to retrieve revision history'}), 500

@app.route('/api/drafts/<int:draft_id>/revisions/<int:rev_num>', methods=['GET'])
@login_required
def get_draft_revision_route(draft_id, rev_num):
    """Retrieves a single specific revision for a draft."""
    org_id = session.get('organization_id', 1)
    try:
        revision = database.get_draft_revision(draft_id, rev_num, organization_id=org_id)
        if not revision:
            return jsonify({'error': f'Revision #{rev_num} not found'}), 404
        return jsonify(revision)
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error fetching revision #{rev_num} for draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to retrieve revision'}), 500

@app.route('/api/drafts/<int:draft_id>/revisions/<int:rev_num>/restore', methods=['POST'])
@login_required
@csrf_protect
def restore_draft_revision_route(draft_id, rev_num):
    """Restores an earlier revision as the latest revision without mutating prior history."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    try:
        updated = database.restore_draft_revision(
            draft_id=draft_id,
            revision_number=rev_num,
            organization_id=org_id,
            restored_by=user_id
        )
        return jsonify({
            'success': True,
            'draft': updated,
            'restored_from_revision': rev_num,
            'current_revision': updated.get('current_revision')
        })
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error restoring revision #{rev_num} on draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to restore revision'}), 500

@app.route('/api/drafts/<int:draft_id>/regenerate', methods=['POST'])
@login_required
@csrf_protect
def regenerate_draft_route(draft_id):
    """Regenerates copy for a draft using AI and appends as a new revision."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')

    # Check organizational hourly rate limit
    hourly_limit = getattr(config, 'AI_ORG_HOURLY_GENERATION_LIMIT', 60)
    hourly_count = database.get_organization_ai_generation_count(org_id, window_seconds=3600)
    if hourly_count >= hourly_limit:
        return jsonify({
            'error': f'Organization hourly AI generation limit of {hourly_limit} requests reached. Please try again later.',
            'code': 'RATE_LIMIT_EXCEEDED'
        }), 429

    draft = database.get_content_draft_by_id(draft_id, organization_id=org_id)
    if not draft:
        return jsonify({'error': 'Draft not found'}), 404

    camp = database.get_campaign_by_id(draft['campaign_id'], organization_id=org_id)
    if not camp:
        return jsonify({'error': 'Associated campaign not found'}), 404

    brand = database.get_brand_by_id(draft['brand_id'], organization_id=org_id)
    if not brand:
        return jsonify({'error': 'Associated brand not found'}), 404

    profile = database.get_brand_marketing_profile(draft['brand_id'], organization_id=org_id) or {}
    brand_info = {
        'name': brand.get('name', 'Brand'),
        'description': brand.get('description', ''),
        'positioning': profile.get('positioning') or brand.get('description', ''),
        'voice_and_tone': profile.get('voice_and_tone', 'Professional, authoritative, customer-focused'),
        'messaging_guidelines': profile.get('messaging_guidelines', ''),
        'approved_product_facts': profile.get('approved_product_facts', ''),
        'prohibited_claims': profile.get('prohibited_claims', ''),
        'preferred_ctas': profile.get('preferred_ctas', '')
    }

    data = request.get_json(silent=True) or {}
    provider_name = data.get('provider') or draft.get('ai_provider')
    model_name = data.get('model') or draft.get('ai_model')

    try:
        ai_provider = ai_service.get_ai_provider(provider_name=provider_name, model=model_name)
        gen_res = ai_service.generate_campaign_content(
            provider=ai_provider,
            brand_info=brand_info,
            campaign_info=camp,
            target_platform=draft['target_platform'],
            language=draft.get('language', 'en'),
            content_format=draft.get('content_format', 'post'),
            model=model_name
        )

        updated = database.update_content_draft(
            draft_id=draft_id,
            organization_id=org_id,
            caption=gen_res.caption,
            headline=gen_res.headline,
            hashtags=gen_res.hashtags,
            call_to_action=gen_res.call_to_action,
            content_format=draft.get('content_format', 'post'),
            ai_provider=provider_name,
            ai_model=model_name,
            edited_by=user_id,
            change_source='regenerated',
            change_summary='AI regenerated copy',
            expected_revision=data.get('expected_revision')
        )

        meta = getattr(gen_res, 'metadata', {}) or {}
        database.log_ai_usage(
            organization_id=org_id,
            brand_id=draft['brand_id'],
            campaign_id=draft['campaign_id'],
            provider=provider_name or draft.get('ai_provider') or 'mock',
            model=model_name or draft.get('ai_model') or 'mock-v1',
            prompt_tokens=meta.get('prompt_tokens', 120),
            completion_tokens=meta.get('completion_tokens', 80),
            total_tokens=meta.get('total_tokens', 200),
            success=True
        )
        return jsonify({'success': True, 'draft': updated})
    except database.ConcurrencyConflictError as e:
        return jsonify({'error': str(e), 'code': 'CONCURRENT_EDIT_CONFLICT'}), 409
    except ai_service.AIConfigurationError as e:
        database.log_ai_usage(organization_id=org_id, brand_id=draft.get('brand_id'), campaign_id=draft.get('campaign_id'), provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e)}), 400
    except ai_service.AIRateLimitError as e:
        database.log_ai_usage(organization_id=org_id, brand_id=draft.get('brand_id'), campaign_id=draft.get('campaign_id'), provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'RATE_LIMIT_EXCEEDED'}), 429
    except ai_service.AITimeoutError as e:
        database.log_ai_usage(organization_id=org_id, brand_id=draft.get('brand_id'), campaign_id=draft.get('campaign_id'), provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'TIMEOUT'}), 504
    except (ai_service.AIResponseValidationError, ai_service.AIProviderError) as e:
        database.log_ai_usage(organization_id=org_id, brand_id=draft.get('brand_id'), campaign_id=draft.get('campaign_id'), provider=provider_name or 'mock', model=model_name, success=False, error_message=str(e))
        return jsonify({'error': str(e), 'code': 'AI_PROVIDER_ERROR'}), 502
    except Exception as e:
        logger.error(f"Error regenerating draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to regenerate draft'}), 500

@app.route('/api/drafts/<int:draft_id>/transition', methods=['POST'])
@login_required
@csrf_protect
def transition_draft(draft_id):
    """Explicitly transitions a content draft lifecycle status."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    data = request.get_json(silent=True) or {}
    to_status = data.get('status')
    reason = data.get('reason')
    if not to_status:
        return jsonify({'error': 'status is required', 'code': 'MISSING_STATUS'}), 400

    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    user_role = session.get('role', 'user')
    try:
        updated = database.transition_content_draft_status(
            draft_id=draft_id,
            to_status=to_status,
            user_id=user_id,
            reason=reason,
            organization_id=org_id,
            user_role=user_role
        )
        return jsonify({'success': True, 'draft': updated})
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error transitioning draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to transition draft status'}), 500

@app.route('/api/drafts/<int:draft_id>/approve', methods=['POST'])
@login_required
@csrf_protect
def approve_draft(draft_id):
    """Workflow action: Approves a draft in pending_approval status."""
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    user_role = session.get('role', 'user')
    try:
        updated = database.transition_content_draft_status(
            draft_id=draft_id,
            to_status='approved',
            user_id=user_id,
            reason='Content draft approved by reviewer',
            organization_id=org_id,
            user_role=user_role
        )
        return jsonify({'success': True, 'draft': updated})
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error approving draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to approve draft'}), 500

@app.route('/api/drafts/<int:draft_id>/reject', methods=['POST'])
@login_required
@csrf_protect
def reject_draft(draft_id):
    """Workflow action: Rejects a draft in pending_approval status with mandatory reason."""
    data = request.get_json(silent=True) or {}
    reason = str(data.get('reason') or '').strip()
    if not reason:
        return jsonify({'error': 'A specific rejection reason is required', 'code': 'REASON_REQUIRED'}), 400

    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    user_role = session.get('role', 'user')
    try:
        updated = database.transition_content_draft_status(
            draft_id=draft_id,
            to_status='rejected',
            user_id=user_id,
            reason=reason,
            organization_id=org_id,
            user_role=user_role
        )
        return jsonify({'success': True, 'draft': updated})
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error rejecting draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to reject draft'}), 500

@app.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
@login_required
@csrf_protect
def delete_draft(draft_id):
    """Deletes a content draft."""
    if session.get('role') == 'viewer':
        return jsonify({'error': 'Unauthorized: Viewers have read-only access.'}), 403
    org_id = session.get('organization_id', 1)
    try:
        deleted = database.delete_content_draft(draft_id, organization_id=org_id)
        if not deleted:
            return jsonify({'error': 'Draft not found'}), 404
        return jsonify({'status': 'deleted', 'draft_id': draft_id})
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/drafts/<int:draft_id>/schedule', methods=['POST'])
@login_required
@csrf_protect
def schedule_draft_route(draft_id):
    """Schedules an approved content draft for publication into the scheduled_posts queue."""
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    user_role = session.get('role', 'contributor')
    data = request.get_json(silent=True) or {}
    scheduled_for = data.get('scheduled_for') or data.get('scheduled_time')
    timezone_name = data.get('timezone')

    if not scheduled_for:
        return jsonify({'error': 'scheduled_for timestamp is required', 'code': 'VALIDATION_ERROR'}), 400

    try:
        res = database.schedule_content_draft(
            draft_id=draft_id,
            scheduled_for=scheduled_for,
            timezone_name=timezone_name,
            organization_id=org_id,
            user_id=user_id,
            user_role=user_role
        )
        return jsonify({
            'status': 'success',
            'scheduled': res,
            'draft': {'id': res.get('draft_id'), 'status': res.get('status')},
            'scheduled_post': res.get('scheduled_post')
        }), 201
    except database.TenantIsolationError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error scheduling draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to schedule draft'}), 500

@app.route('/api/drafts/<int:draft_id>/export-package', methods=['GET'])
@login_required
def export_draft_package_route(draft_id):
    """Prepares and returns a ready-to-publish creative package for manual posting."""
    org_id = session.get('organization_id', 1)
    try:
        draft = database.get_content_draft_by_id(draft_id, organization_id=org_id)
        if not draft:
            return jsonify({'error': 'Draft not found'}), 404

        media_info = None
        if draft.get('media_asset_id'):
            asset = database.get_media_asset_by_id(draft['media_asset_id'], organization_id=org_id)
            if asset:
                media_info = {
                    'filename': asset['filename'],
                    'original_name': asset.get('original_name'),
                    'file_type': asset.get('file_type'),
                    'download_url': f"/images/{asset['filename']}"
                }

        copy_blocks = []
        if draft.get('headline'):
            copy_blocks.append(f"Headline: {draft['headline']}")
        copy_blocks.append(draft.get('caption', ''))
        if draft.get('hashtags'):
            copy_blocks.append(draft['hashtags'])
        if draft.get('call_to_action'):
            copy_blocks.append(f"CTA: {draft['call_to_action']}")
        full_copy = "\n\n".join(b for b in copy_blocks if b)

        package = {
            'draft_id': draft['id'],
            'campaign_id': draft['campaign_id'],
            'campaign_name': draft.get('campaign_name'),
            'brand_id': draft['brand_id'],
            'brand_name': draft.get('brand_name'),
            'target_platform': draft['target_platform'],
            'content_format': draft.get('content_format', 'post'),
            'headline': draft.get('headline'),
            'caption': draft.get('caption'),
            'hashtags': draft.get('hashtags'),
            'call_to_action': draft.get('call_to_action'),
            'media': media_info,
            'ready_to_publish_copy': full_copy,
            'exported_at': datetime.now(timezone.utc).isoformat()
        }
        return jsonify({'status': 'success', 'package': package}), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error exporting package for draft #{draft_id}: {e}")
        return jsonify({'error': 'Failed to export draft package'}), 500

@app.route('/api/analytics/ai-usage', methods=['GET'])
@login_required
def get_ai_usage_analytics():
    """Returns aggregated AI usage metrics and recent request logs for the active organization."""
    org_id = session.get('organization_id', 1)
    days = request.args.get('days', 30)
    try:
        days_int = int(days)
    except (ValueError, TypeError):
        days_int = 30
    data = database.get_ai_usage_summary(organization_id=org_id, days=days_int)
    return jsonify(data), 200


@app.route('/api/analytics/dashboard', methods=['GET'])
@login_required
def get_marketing_dashboard_analytics_route():
    """Returns aggregated campaign, content draft, publishing throughput, and AI performance metrics."""
    org_id = session.get('organization_id', 1)
    brand_id = request.args.get('brand_id')
    campaign_id = request.args.get('campaign_id')
    try:
        b_id = int(brand_id) if brand_id and str(brand_id).strip() else None
        c_id = int(campaign_id) if campaign_id and str(campaign_id).strip() else None
        data = database.get_marketing_dashboard_analytics(
            organization_id=org_id,
            brand_id=b_id,
            campaign_id=c_id
        )
        data['total_campaigns'] = data.get('campaigns', {}).get('total', 0)
        data['total_drafts'] = data.get('drafts', {}).get('total', 0)
        data['scheduled_posts'] = data.get('publishing', {}).get('total', 0)
        data['publishing_success_rate'] = data.get('publishing', {}).get('success_rate', 100.0)
        data['draft_lifecycle_breakdown'] = data.get('drafts', {}).get('by_status', {})
        data['platform_distribution'] = {p: v.get('drafts_count', 0) for p, v in data.get('platforms', {}).items()}
        return jsonify(data), 200
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error computing marketing dashboard analytics: {e}")
        return jsonify({'error': 'Failed to compute dashboard analytics'}), 500

@app.route('/api/calendar/events', methods=['GET'])
@login_required
def get_calendar_events_route():
    """Retrieves unified calendar events for scheduled posts and content drafts."""
    org_id = session.get('organization_id', 1)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    brand_id = request.args.get('brand_id')
    campaign_id = request.args.get('campaign_id')
    platform = request.args.get('platform') or request.args.get('post_type')
    status = request.args.get('status')
    tz = request.args.get('timezone')
    property_id = request.args.get('property_id') or request.args.get('growth_property_id')

    try:
        events = database.get_calendar_events(
            organization_id=org_id,
            start_date=start_date,
            end_date=end_date,
            brand_id=brand_id,
            campaign_id=campaign_id,
            platform=platform,
            status=status,
            target_timezone=tz,
            property_id=property_id
        )
        return jsonify(events), 200
    except (database.TenantIsolationError, ValueError) as e:
        status_code = 404 if 'Tenant' in type(e).__name__ else 400
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), status_code

@app.route('/api/calendar/events/<string:event_id>/reschedule', methods=['PUT'])
@login_required
@csrf_protect
def reschedule_calendar_event_route(event_id):
    """Reschedules a calendar event (scheduled post) to a new future timestamp."""
    org_id = session.get('organization_id', 1)
    data = request.get_json(silent=True) or {}
    new_time = data.get('scheduled_for')
    tz_name = data.get('timezone')

    if not new_time:
        return jsonify({'error': 'scheduled_for timestamp is required', 'code': 'VALIDATION_ERROR'}), 400

    raw_id = event_id.replace('post_', '') if event_id.startswith('post_') else event_id
    try:
        post_id = int(raw_id)
    except (ValueError, TypeError):
        return jsonify({'error': f"Invalid event ID '{event_id}'", 'code': 'VALIDATION_ERROR'}), 400

    try:
        updated = database.update_scheduled_post(
            schedule_id=post_id,
            scheduled_for=new_time,
            timezone_name=tz_name,
            organization_id=org_id,
            allow_past=False
        )
        if not updated:
            return jsonify({'error': 'Event not found or not editable'}), 404
        return jsonify({'success': True, 'event_id': event_id, 'scheduled_for': new_time}), 200
    except ValueError as e:
        return jsonify({'error': str(e), 'code': 'VALIDATION_ERROR'}), 400
    except Exception as e:
        logger.error(f"Error rescheduling event {event_id}: {e}")
        return jsonify({'error': 'Failed to reschedule event'}), 500

# --- Main Entry Point ---

def init_application():
    """Initializes database and background workers."""
    database.init_db()
    threading.Thread(target=_cleanup_images_worker, daemon=True, name="ImageCleanupWorker").start()

init_application()

if __name__ == '__main__':
    logger.info(f"Starting PostPilot in {config.APP_ENV} mode on {config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
