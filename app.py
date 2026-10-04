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
import threading
import logging
from pathlib import Path
from functools import wraps
from PIL import Image
from flask import Flask, render_template, jsonify, request, session, send_from_directory, redirect, url_for

import config
import database
import channel_runner
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
            ch = channel_runner.get_channel(task_name)
            state = database.get_task_state(task_name)
            ch.set_interval(state.get('interval', ch.default_interval))
            ch.stop_event.clear()
            th = threading.Thread(target=ch.run, daemon=True)
            th.start()
            local_worker_threads[task_name] = th
        elif task_name == 'insta':
            state = database.get_task_state('insta')
            interval = state.get('interval', config.INSTA_INTERVAL)
            insta_suite.set_interval(interval)
            insta_phoenix.set_interval(interval)
            insta_suite.stop_event.clear()
            insta_phoenix.stop_event.clear()
            th1 = threading.Thread(target=insta_suite.run, daemon=True)
            th2 = threading.Thread(target=insta_phoenix.run, daemon=True)
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

@app.route('/api/auth/me', methods=['GET'])
def get_auth_status():
    """Returns current user session and authentication status."""
    is_authed = bool(session.get('user_id'))
    is_local = config.LOCAL_MODE and is_localhost_request()
    return jsonify({
        'authenticated': is_authed or is_local,
        'username': session.get('username', 'local_admin' if is_local else None),
        'role': session.get('role', 'admin' if is_local else None),
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
    token = get_or_create_csrf_token()
    return jsonify({
        'success': True,
        'username': user['username'],
        'role': user['role'],
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
    """Retrieves all posts for a specific type."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    posts = database.load_posts_by_type(post_type)
    return jsonify(posts)

@app.route('/api/posts/<post_type>', methods=['POST'])
@login_required
@csrf_protect
def add_post(post_type):
    """Creates a new post record."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    image_filename = data.get('image_filename', '').strip()

    post_id = database.add_post(post_type, message, image_filename)
    return jsonify({'id': post_id, 'message': message, 'image_filename': image_filename}), 201

@app.route('/api/posts/<post_type>/<int:post_id>', methods=['PUT'])
@login_required
@csrf_protect
def update_post(post_type, post_id):
    """Updates an existing post using its primary key ID."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json() or {}
    message = data.get('message')
    image_filename = data.get('image_filename')

    success = database.update_post_by_id(post_id, message, image_filename)
    if not success:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/<int:post_id>', methods=['DELETE'])
@login_required
@csrf_protect
def delete_post(post_type, post_id):
    """Deletes a post by its primary key ID and purges its image if unreferenced."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400
        
    image_filename, success = database.delete_post_by_id(post_id)
    if not success:
        return jsonify({'error': 'Post not found'}), 404

    if image_filename:
        _cleanup_single_image(image_filename)

    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/all', methods=['DELETE'])
@login_required
@csrf_protect
def delete_all_posts(post_type):
    """Deletes all posts for a type and cleans up orphaned media."""
    if post_type not in VALID_POST_TYPES:
        return jsonify({'error': 'Invalid post type'}), 400

    deleted_images = database.delete_all_posts_by_type(post_type)
    for img in deleted_images:
        _cleanup_single_image(img)

    return jsonify({'success': True, 'message': f'All {post_type} posts deleted'}), 200

@app.route('/api/search', methods=['GET'])
@login_required
def search_posts():
    """Searches posts across message and post_type."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    try:
        results = database.search_posts(query)
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
    """Serves uploaded images safely from UPLOAD_FOLDER."""
    return send_from_directory(config.UPLOAD_FOLDER, filename)

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

# --- Main Entry Point ---

def init_application():
    """Initializes database and background workers."""
    database.init_db()
    threading.Thread(target=_cleanup_images_worker, daemon=True, name="ImageCleanupWorker").start()

init_application()

if __name__ == '__main__':
    logger.info(f"Starting PostPilot in {config.APP_ENV} mode on {config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
