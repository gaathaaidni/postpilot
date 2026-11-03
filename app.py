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
from flask import Flask, render_template, jsonify, request, session, send_from_directory, redirect, url_for

import config
import database
import timezone_utils
import channel_runner
import ai_service
import nexora_suite as tour
import nexora_by_phoenix_international as visa
import gaatha_loop as gaatha
import insta

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

VALID_POST_TYPES = {'tour', 'nz', 'gaatha', 'insta'}

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
        if request.method in ('POST', 'PUT', 'DELETE'):
            # Allow login without CSRF token since session is not established yet
            if request.path == '/api/auth/login':
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
            row = conn.execute("SELECT COUNT(*) as count FROM posts WHERE image_filename = ?", (filename,)).fetchone()
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
                rows = conn.execute("SELECT DISTINCT image_filename FROM posts WHERE image_filename IS NOT NULL AND image_filename != ''").fetchall()
                db_images = {r['image_filename'] for r in rows}

            upload_dir = Path(config.UPLOAD_FOLDER)
            if upload_dir.exists():
                for file_path in upload_dir.iterdir():
                    if file_path.is_file() and not file_path.name.startswith('.'):
                        if file_path.name not in db_images:
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

for ch in channel_runner.CHANNELS.values():
    ch.set_status_callback(_local_status_callback)
insta.set_status_callback(_local_status_callback)

insta_suite = insta.InstaSync(config.FB_PAGE_ID_SUITE, config.INSTA_ID_SUITE, 'insta_suite')
insta_phoenix = insta.InstaSync(config.FB_PAGE_ID_PHOENIX, config.INSTA_ID_PHOENIX, 'insta_phoenix')

def _start_local_task(task_name):
    """Spawns an in-process daemon thread for local/Termux mode if lease is available."""
    # Under production, app.py never runs in-process workers. Standalone worker.py handles execution.
    if config.APP_ENV == 'production':
        return

    # Check if a standalone worker daemon is already holding the lease
    app_worker_id = f"app-{os.getpid()}"
    active_lease = database.get_active_worker_lease('scheduler')
    if active_lease and active_lease.get('worker_id') != app_worker_id:
        logger.info(f"Standalone worker ({active_lease.get('worker_id')}) is active; skipping in-process thread for {task_name}")
        return

    # Acquire/renew lease for in-process application worker
    database.acquire_worker_lease(app_worker_id, 'scheduler', ttl_seconds=3600)

    with local_threads_lock:
        if task_name in channel_runner.CHANNELS:
            if task_name in local_worker_threads and local_worker_threads[task_name].is_alive():
                logger.info(f"Task thread '{task_name}' already running; ignoring duplicate start.")
                return
            ch = channel_runner.get_channel(task_name)
            state = database.get_task_state(task_name)
            ch.set_interval(state.get('interval', ch.default_interval))
            ch.stop_event.clear()
            th = threading.Thread(target=ch.run, daemon=True, name=f"Local-{task_name}")
            th.start()
            local_worker_threads[task_name] = th
        elif task_name == 'insta':
            th1 = local_worker_threads.get('insta_suite')
            th2 = local_worker_threads.get('insta_phoenix')
            if (th1 and th1.is_alive()) or (th2 and th2.is_alive()):
                logger.info("Instagram sync threads already running; ignoring duplicate start.")
                return
            state = database.get_task_state('insta')
            interval = state.get('interval', config.INSTA_INTERVAL)
            insta_suite.set_interval(interval)
            insta_phoenix.set_interval(interval)
            insta_suite.stop_event.clear()
            insta_phoenix.stop_event.clear()
            th1 = threading.Thread(target=insta_suite.run, daemon=True, name="Local-insta-suite")
            th2 = threading.Thread(target=insta_phoenix.run, daemon=True, name="Local-insta-phoenix")
            th1.start()
            th2.start()
            local_worker_threads['insta_suite'] = th1
            local_worker_threads['insta_phoenix'] = th2

def _stop_local_task(task_name):
    """Halts an in-process thread for local/Termux mode."""
    with local_threads_lock:
        if task_name in channel_runner.CHANNELS:
            ch = channel_runner.get_channel(task_name)
            ch.stop()
            th = local_worker_threads.pop(task_name, None)
            if th and th.is_alive():
                th.join(timeout=1.0)
        elif task_name == 'insta':
            insta_suite.stop()
            insta_phoenix.stop()
            th1 = local_worker_threads.pop('insta_suite', None)
            th2 = local_worker_threads.pop('insta_phoenix', None)
            if th1 and th1.is_alive():
                th1.join(timeout=1.0)
            if th2 and th2.is_alive():
                th2.join(timeout=1.0)

        # If no active local threads remain, release worker lease
        if not local_worker_threads:
            try:
                database.release_worker_lease(f"app-{os.getpid()}", 'scheduler')
            except Exception:
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

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """Terminates the user session."""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# --- Posts Management Endpoints ---

@app.route('/api/posts/<post_type>', methods=['GET'])
@login_required
def get_posts(post_type):
    """Retrieves all posts for a specific type scoped to the active organization."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    org_id = session.get('organization_id', 1)
    posts = database.load_posts_by_type(post_type, organization_id=org_id)
    return jsonify(posts)

@app.route('/api/posts/<post_type>', methods=['POST'])
@login_required
@csrf_protect
def add_post(post_type):
    """Creates a new post record scoped to the active organization."""
    if post_type not in VALID_POST_TYPES:
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
    if post_type not in VALID_POST_TYPES:
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
    if post_type not in VALID_POST_TYPES:
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
    if post_type not in VALID_POST_TYPES:
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
    file.save(str(save_path))
    return jsonify({'filename': filename}), 201

@app.route('/images/<filename>')
def serve_image(filename):
    """Serves uploaded images safely from UPLOAD_FOLDER with path traversal protection."""
    safe_filename = os.path.basename(filename)
    return send_from_directory(config.UPLOAD_FOLDER, safe_filename)

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
    return jsonify(response)

@app.route('/api/interval/<post_type>', methods=['GET'])
@login_required
def get_interval(post_type):
    """Retrieves posting interval for a task type."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    state = database.get_task_state(post_type) or {}
    return jsonify({'interval': state.get('interval', 1800)})

@app.route('/api/interval/<post_type>', methods=['PUT'])
@login_required
@csrf_protect
def set_interval(post_type):
    """Sets posting interval for a task type in seconds."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    interval = data.get('interval')
    if not interval or interval <= 0:
        return jsonify({'error': 'Invalid interval value'}), 400

    database.set_task_state(post_type, interval_seconds=interval)

    # Update in-memory module if running locally
    if post_type == 'tour': tour.set_interval(interval)
    elif post_type == 'nz': visa.set_interval(interval)
    elif post_type == 'gaatha': gaatha.set_interval(interval)
    elif post_type == 'insta':
        insta_suite.set_interval(interval)
        insta_phoenix.set_interval(interval)

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
    if not post_type or post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type', 'code': 'INVALID_POST_TYPE'}), 400

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
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    
    brand_id = data.get('brand_id')
    name = data.get('name')
    objective = data.get('objective')
    brief = data.get('brief')

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
    org_id = session.get('organization_id', 1)
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}

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
            change_summary=data.get('change_summary')
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
    org_id = session.get('organization_id', 1)
    try:
        deleted = database.delete_content_draft(draft_id, organization_id=org_id)
        if not deleted:
            return jsonify({'error': 'Draft not found'}), 404
        return jsonify({'status': 'deleted', 'draft_id': draft_id})
    except (database.TenantIsolationError, ValueError) as e:
        return jsonify({'error': str(e)}), 404

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

    try:
        events = database.get_calendar_events(
            organization_id=org_id,
            start_date=start_date,
            end_date=end_date,
            brand_id=brand_id,
            campaign_id=campaign_id,
            platform=platform,
            status=status,
            target_timezone=tz
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
