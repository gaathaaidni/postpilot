import json
import threading
import os
import time
import sqlite3
from flask import Flask, render_template, jsonify, request, send_from_directory
import logging
from pathlib import Path
from datetime import datetime
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
# modules for posting logic
import nexora_suite as tour
import nexora_by_phoenix_international as visa
import gaatha_loop as gaatha
import insta
import grahakchetna as grahak

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app initialization - specify template and static folders relative to APP_ROOT
app = Flask(__name__, template_folder='templates', static_folder='static')

# Use absolute paths for robustness
APP_ROOT = Path(__file__).parent
UPLOAD_FOLDER = APP_ROOT / 'images'
DB_PATH = APP_ROOT / "posts.db"

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv'}
ALLOWED_MIMETYPES = {
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska', 'video/avi'
}

def validate_file(file):
    """Validates file extension, MIME type, and image integrity."""
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIMETYPES:
        return False, 'Unsupported file format or type'
    
    if extension in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
        try:
            with Image.open(file) as img:
                img.verify()
            file.seek(0)  # Reset stream position after verification
        except Exception:
            return False, 'Invalid image file content'
    return True, None

# Global state for running tasks
posting_state = {
    'tour_running': False,
    'nz_running': False,
    'gaatha_running': False,
    'insta_suite_running': False,
    'insta_phoenix_running': False,
    'grahak_running': False,
    # Threads store
    'threads': {},
    'tour_status': '',
    'nz_status': '',
    'insta_status': '',
    'grahak_status': '',
    'tour_current_post': None,
    'nz_current_post': None,
    'insta_current_post': None,
    'grahak_current_post': None,
    'gaatha_status': '',
    'gaatha_current_post': None,
    # Intervals
    'tour_interval': 30 * 60,  # 30 minutes in seconds
    'nz_interval': 30 * 60,
    'gaatha_interval': 30 * 60,
    'grahak_interval': 30 * 60,
    'insta_interval': 3 * 60
}

posting_state_lock = threading.Lock() # Lock for thread-safe access to posting_state

def _cleanup_images_worker():
    """Background worker to remove images not referenced in the database or active tasks"""
    while True:
        try:
            logger.info("🧹 Starting orphaned image cleanup...")
            
            # 1. Get filenames from SQLite database
            db_images = set()
            try:
                with get_db_connection() as conn:
                    rows = conn.execute("SELECT DISTINCT image_filename FROM posts WHERE image_filename IS NOT NULL AND image_filename != ''").fetchall()
                    db_images = {row['image_filename'] for row in rows}
            except Exception as e:
                logger.error(f"Error querying DB for images: {e}")

            # 2. Scan the upload folder and remove orphans
            upload_dir = app.config['UPLOAD_FOLDER']
            if os.path.exists(upload_dir):
                files_on_disk = os.listdir(upload_dir)
                deleted_count = 0
                for filename in files_on_disk:
                    if not os.path.isfile(os.path.join(upload_dir, filename)) or filename.startswith('.'):
                        continue
                    if filename not in db_images:
                        os.remove(os.path.join(upload_dir, filename))
                        deleted_count += 1
                logger.info(f"✅ Image cleanup finished. Deleted {deleted_count} orphaned files.")
        except Exception as e:
            logger.error(f"Error in image cleanup worker: {e}")
        time.sleep(86400)  # Run once every 24 hours

def _cleanup_single_image(filename):
    """Checks if an image is still needed and deletes it if not."""
    if not filename:
        return

    try:
        with get_db_connection() as conn:
            # Check if any other post uses this image
            row = conn.execute(
                "SELECT COUNT(*) as count FROM posts WHERE image_filename = ?", 
                (filename,)
            ).fetchone()
            if row and row['count'] > 0:
                return # Still referenced in database
    except Exception as e:
        logger.error(f"Error checking DB for single image cleanup: {e}")
        return

    # Delete from disk
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info(f"🗑️ Automatically cleaned up unused image: {filename}")
        except Exception as e:
            logger.error(f"Failed to delete orphaned image {filename}: {e}")

# Initialize Insta Sync Objects
SUITE_PAGE_ID = os.getenv('FB_PAGE_ID_SUITE', '967550829768297')
SUITE_IG_ID = os.getenv('INSTA_ID_SUITE', '17841449080283492')
insta_suite = insta.InstaSync(SUITE_PAGE_ID, SUITE_IG_ID, 'insta_suite')

PHOENIX_PAGE_ID = os.getenv('FB_PAGE_ID_PHOENIX', '954901604381882')
PHOENIX_IG_ID = os.getenv('INSTA_ID_PHOENIX', '17841472248438802')
insta_phoenix = insta.InstaSync(PHOENIX_PAGE_ID, PHOENIX_IG_ID, 'insta_phoenix')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn: # Ensure this is called from the correct APP_ROOT
        conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_type TEXT NOT NULL,
                message TEXT,
                image_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_posted_at TIMESTAMP
            )
        ''')

def load_posts_by_type(post_type):
    with get_db_connection() as conn:
        posts = conn.execute(
            "SELECT id, message, image_filename, created_at, last_posted_at FROM posts WHERE post_type = ? ORDER BY last_posted_at ASC, id ASC",
            (post_type,)
        ).fetchall()
        return [dict(p) for p in posts]

@app.route('/api/search', methods=['GET'])
def search_posts():
    """Search posts by keyword in message or post_type."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    try:
        with get_db_connection() as conn:
            search_pattern = f"%{query}%"
            results = conn.execute(
                "SELECT id, post_type, message, image_filename, created_at, last_posted_at FROM posts WHERE message LIKE ? OR post_type LIKE ? ORDER BY created_at DESC",
                (search_pattern, search_pattern)
            ).fetchall()
            return jsonify([dict(row) for row in results])
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': 'Search failed'}), 500

def update_posting_status(post_type, is_running, message='', current_post=None):
    """Update posting status for a specific post type"""
    with posting_state_lock:
        if post_type == 'tour':
            posting_state['tour_running'] = is_running
            posting_state['tour_status'] = message
            posting_state['tour_current_post'] = current_post
        elif post_type == 'nz':
            posting_state['nz_running'] = is_running
            posting_state['nz_status'] = message
            posting_state['nz_current_post'] = current_post
        elif post_type == 'insta':
            posting_state['insta_running'] = is_running
            posting_state['insta_status'] = message
            posting_state['insta_current_post'] = current_post
        elif post_type == 'gaatha':
            posting_state['gaatha_running'] = is_running
            posting_state['gaatha_status'] = message
            posting_state['gaatha_current_post'] = current_post

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

# Posts API endpoints
@app.route('/api/posts/<post_type>', methods=['GET'])
def get_posts(post_type):
    """Get posts for a specific type"""
    if post_type not in ['tour', 'nz', 'insta', 'gaatha', 'grahak']:
        return jsonify({'error': 'Invalid post type'}), 400
    posts = load_posts_by_type(post_type)
    return jsonify(posts)

@app.route('/api/posts/<post_type>', methods=['POST'])
def add_post(post_type):
    """Add a new post"""
    if post_type not in ['tour', 'nz', 'insta', 'gaatha', 'grahak']:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json()
    message = data.get('message', '')
    image_filename = data.get('image_filename', '')
    with get_db_connection() as conn:
        conn.execute("INSERT INTO posts (post_type, message, image_filename) VALUES (?, ?, ?)",
                    (post_type, message, image_filename))
    return jsonify({'message': message, 'image_filename': image_filename}), 201

@app.route('/api/posts/<post_type>/<int:index>', methods=['PUT'])
def update_post(post_type, index):
    """Update a post"""
    if post_type not in ['tour', 'nz', 'insta', 'gaatha', 'grahak']:
        return jsonify({'error': 'Invalid post type'}), 400
    data = request.get_json()
    message = data.get('message')
    image_filename = data.get('image_filename')
    with get_db_connection() as conn:
        res = conn.execute(
            """UPDATE posts SET message = COALESCE(?, message), image_filename = COALESCE(?, image_filename) 
               WHERE id = (SELECT id FROM posts WHERE post_type = ? ORDER BY id ASC LIMIT 1 OFFSET ?)""",
            (message, image_filename, post_type, index))
        if res.rowcount == 0: return jsonify({'error': 'Post not found'}), 404
    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/<int:index>', methods=['DELETE'])
def delete_post(post_type, index):
    """Delete a post and its associated image if unused"""
    if post_type not in ['tour', 'nz', 'insta', 'gaatha', 'grahak']:
        return jsonify({'error': 'Invalid post type'}), 400
        
    filename_to_cleanup = None
    with get_db_connection() as conn:
        # Find the specific post and its image filename first
        row = conn.execute(
            "SELECT id, image_filename FROM posts WHERE post_type = ? ORDER BY id ASC LIMIT 1 OFFSET ?",
            (post_type, index)).fetchone()
        
        if not row:
            return jsonify({'error': 'Post not found'}), 404
            
        filename_to_cleanup = row['image_filename']
        
        # Delete the specific post record
        conn.execute("DELETE FROM posts WHERE id = ?", (row['id'],))
        conn.commit()

    if filename_to_cleanup:
        _cleanup_single_image(filename_to_cleanup)

    return jsonify({'success': True})

@app.route('/api/posts/<post_type>/all', methods=['DELETE'])
def delete_all_posts(post_type):
    """Delete all posts for a specific type and clean up orphaned images"""
    if post_type not in ['tour', 'nz', 'insta', 'gaatha', 'grahak']:
        return jsonify({'error': 'Invalid post type'}), 400

    filenames_to_check = []
    with get_db_connection() as conn:
        # 1. Collect all distinct filenames that might become orphans
        rows = conn.execute(
            "SELECT DISTINCT image_filename FROM posts WHERE post_type = ? AND image_filename IS NOT NULL AND image_filename != ''",
            (post_type,)
        ).fetchall()
        filenames_to_check = [row['image_filename'] for row in rows]

        # 2. Perform bulk deletion
        conn.execute("DELETE FROM posts WHERE post_type = ?", (post_type,))
        conn.commit()

    # 3. Trigger individual cleanup for each potential orphan
    for filename in filenames_to_check:
        _cleanup_single_image(filename)

    return jsonify({'success': True, 'message': f'All {post_type} posts and associated orphaned images deleted'}), 200

# Image upload endpoint
@app.route('/api/upload', methods=['POST'])
def upload_image():
    """Upload an image file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    is_valid, error_msg = validate_file(file)
    if not is_valid:
        return jsonify({'error': error_msg}), 400

    extension = os.path.splitext(file.filename)[1].lower()
    filename = f"post_{int(time.time())}_{os.urandom(4).hex()}{extension}"
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return jsonify({'filename': filename}), 201

# Control endpoints
@app.route('/api/control/tour/start', methods=['POST'])
def start_tour():
    """Start tour posting"""
    if not posting_state['tour_running']:
        tour.set_status_callback(update_posting_status)
        tour.set_interval(posting_state['tour_interval'])
        tour.stop_event.clear()
        # module renamed; use updated function name
        thread = threading.Thread(target=tour.run_nexora_suite, daemon=True)
        thread.start()
        posting_state['threads']['tour'] = thread
        posting_state['tour_running'] = True
        update_posting_status('tour', True, 'Starting...', None)
        return jsonify({'status': 'Tour posting started'}), 200
    return jsonify({'status': 'Tour already running'}), 200

@app.route('/api/control/tour/stop', methods=['POST'])
def stop_tour():
    """Stop tour posting"""
    if posting_state['tour_running']:
        tour.stop_nexora_suite()
        posting_state['tour_running'] = False
        update_posting_status('tour', False, '', None)
        return jsonify({'status': 'Tour posting stopped'}), 200
    return jsonify({'status': 'Tour not running'}), 200

@app.route('/api/control/nz/start', methods=['POST'])
def start_nz():
    """Start NZ visa posting"""
    if not posting_state['nz_running']:
        visa.set_status_callback(update_posting_status)
        visa.set_interval(posting_state['nz_interval'])
        visa.stop_event.clear()
        # module renamed; use updated function name
        thread = threading.Thread(target=visa.run_nexora_by_phoenix, daemon=True)
        thread.start()
        posting_state['threads']['nz'] = thread
        posting_state['nz_running'] = True
        update_posting_status('nz', True, 'Starting...', None)
        return jsonify({'status': 'NZ posting started'}), 200
    return jsonify({'status': 'NZ already running'}), 200

@app.route('/api/control/nz/stop', methods=['POST'])
def stop_nz():
    """Stop NZ visa posting"""
    if posting_state['nz_running']:
        visa.stop_nexora_by_phoenix()
        posting_state['nz_running'] = False
        update_posting_status('nz', False, '', None)
        return jsonify({'status': 'NZ posting stopped'}), 200
    return jsonify({'status': 'NZ not running'}), 200

# --- GAATHA ENDPOINTS ---
@app.route('/api/control/gaatha/start', methods=['POST'])
def start_gaatha():
    """Start Gaatha AI posting"""
    if not posting_state['gaatha_running']:
        gaatha.set_status_callback(update_posting_status)
        gaatha.set_interval(posting_state['gaatha_interval'])
        gaatha.stop_event.clear()
        thread = threading.Thread(target=gaatha.run_gaatha_loop, daemon=True)
        thread.start()
        posting_state['threads']['gaatha'] = thread
        posting_state['gaatha_running'] = True
        update_posting_status('gaatha', True, 'Starting...', None)
        return jsonify({'status': 'Gaatha posting started'}), 200
    return jsonify({'status': 'Gaatha already running'}), 200

@app.route('/api/control/gaatha/stop', methods=['POST'])
def stop_gaatha():
    """Stop Gaatha AI posting"""
    if posting_state['gaatha_running']:
        gaatha.stop_gaatha_loop()
        posting_state['gaatha_running'] = False
        update_posting_status('gaatha', False, '', None)
        return jsonify({'status': 'Gaatha posting stopped'}), 200
    return jsonify({'status': 'Gaatha not running'}), 200

# --- GRAHAK ENDPOINTS ---
@app.route('/api/control/grahak/start', methods=['POST'])
def start_grahak():
    """Start Grahak Chetna posting"""
    if not posting_state['grahak_running']:
        grahak.set_status_callback(update_posting_status)
        grahak.set_interval(posting_state['grahak_interval'])
        grahak.stop_event.clear()
        thread = threading.Thread(target=grahak.run_grahakchetna, daemon=True)
        thread.start()
        posting_state['threads']['grahak'] = thread
        posting_state['grahak_running'] = True
        update_posting_status('grahak', True, 'Starting...', None)
        return jsonify({'status': 'Grahak posting started'}), 200
    return jsonify({'status': 'Grahak already running'}), 200

@app.route('/api/control/grahak/stop', methods=['POST'])
def stop_grahak():
    """Stop Grahak Chetna posting"""
    if posting_state['grahak_running']:
        grahak.stop_grahakchetna()
        posting_state['grahak_running'] = False
        update_posting_status('grahak', False, '', None)
        return jsonify({'status': 'Grahak posting stopped'}), 200
    return jsonify({'status': 'Grahak not running'}), 200


# --- INSTA SYNC ENDPOINTS (Split) ---

@app.route('/api/control/insta/start', methods=['POST'])
def start_insta():
    """Start Both Instagram syncs"""
    msg = []
    insta.set_status_callback(update_posting_status)
    
    if not posting_state['insta_suite_running']:
        insta_suite.stop_event.clear()
        thread = threading.Thread(target=insta_suite.run, daemon=True)
        thread.start()
        posting_state['threads']['insta_suite'] = thread
        posting_state['insta_suite_running'] = True
        msg.append("Suite Started")

    if not posting_state['insta_phoenix_running']:
        insta_phoenix.stop_event.clear()
        thread2 = threading.Thread(target=insta_phoenix.run, daemon=True)
        thread2.start()
        posting_state['threads']['insta_phoenix'] = thread2
        posting_state['insta_phoenix_running'] = True
        msg.append("Phoenix Started")
        
    return jsonify({'status': ', '.join(msg) or 'Already running'}), 200

@app.route('/api/control/insta/stop', methods=['POST'])
def stop_insta():
    """Stop Instagram sync"""
    if posting_state['insta_suite_running']:
        insta_suite.stop()
        posting_state['insta_suite_running'] = False
    
    if posting_state['insta_phoenix_running']:
        insta_phoenix.stop()
        posting_state['insta_phoenix_running'] = False
        
    return jsonify({'status': 'Instagram syncs stopped'}), 200

@app.route('/api/control/all/start', methods=['POST'])
def start_all():
    """Start all posting tasks"""
    start_tour()
    start_nz()
    start_gaatha()
    start_grahak()
    start_insta()
    return jsonify({'status': 'All tasks started'}), 200

@app.route('/api/control/all/stop', methods=['POST'])
def stop_all():
    """Stop all posting tasks"""
    stop_tour()
    stop_nz()
    stop_gaatha()
    stop_grahak()
    stop_insta()
    return jsonify({'status': 'All tasks stopped'}), 200

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current status of all posting tasks"""
    return jsonify({
        'tour_running': posting_state['tour_running'],
        'nz_running': posting_state['nz_running'],
        'gaatha_running': posting_state['gaatha_running'],
        'grahak_running': posting_state['grahak_running'],
        'insta_running': posting_state['insta_suite_running'] or posting_state['insta_phoenix_running'],
        'tour_status': posting_state['tour_status'],
        'nz_status': posting_state['nz_status'],
        'gaatha_status': posting_state['gaatha_status'],
        'grahak_status': posting_state['grahak_status'],
        'insta_status': posting_state['insta_status'],
        'tour_current_post': posting_state['tour_current_post'],
        'nz_current_post': posting_state['nz_current_post'],
        'gaatha_current_post': posting_state['gaatha_current_post'],
        'grahak_current_post': posting_state['grahak_current_post'],
        'insta_current_post': posting_state['insta_current_post'],
        'tour_interval': posting_state['tour_interval'],
        'nz_interval': posting_state['nz_interval'],
        'gaatha_interval': posting_state['gaatha_interval'],
        'grahak_interval': posting_state['grahak_interval'],
        'insta_interval': posting_state['insta_interval']
    })
# Interval management endpoints
@app.route('/api/interval/<post_type>', methods=['GET']) # This path needs to be updated to APP_ROOT / 'config'
def get_interval(post_type):
    """Get posting interval for a specific post type"""
    interval_key = f'{post_type}_interval'
    if interval_key not in posting_state:
        return jsonify({'error': 'Invalid post type'}), 400
    return jsonify({'interval': posting_state[interval_key]})

@app.route('/api/interval/<post_type>', methods=['PUT'])
def set_interval(post_type):
    """Set posting interval for a specific post type"""
    interval_key = f'{post_type}_interval'
    if interval_key not in posting_state:
        return jsonify({'error': 'Invalid post type'}), 400
    
    data = request.get_json()
    interval = data.get('interval')
    
    if not interval or interval <= 0:
        return jsonify({'error': 'Invalid interval value'}), 400
    
    posting_state[interval_key] = interval
    
    # Update the module if it's running
    if post_type == 'tour':
        tour.set_interval(interval)
    elif post_type == 'nz':
        visa.set_interval(interval)
    elif post_type == 'gaatha':
        gaatha.set_interval(interval)
    elif post_type == 'grahak':
        grahak.set_interval(interval)
    elif post_type == 'insta':
        # Update both
        insta_suite.set_interval(interval)
        insta_phoenix.set_interval(interval)
    
    return jsonify({'success': True, 'interval': interval})

# Serve images
@app.route('/images/<filename>')
def serve_image(filename):
    """Serve image files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=_cleanup_images_worker, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=5000)
