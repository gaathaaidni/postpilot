import json
import threading
import os
from flask import Flask, render_template, jsonify, request, send_from_directory
from pathlib import Path
import tour
import visa
import insta

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

POSTS_DIR = "posts"
NZ_FILE = os.path.join(POSTS_DIR, "visa_posts.json")
TOUR_FILE = os.path.join(POSTS_DIR, "tour_posts.json")
INSTA_FILE = os.path.join(POSTS_DIR, "insta_posts.json")

# Global state for running tasks
posting_state = {
    'tour_running': False,
    'nz_running': False,
    'insta_running': False,
    'threads': {},
    'tour_status': '',
    'nz_status': '',
    'insta_status': '',
    'tour_current_post': None,
    'nz_current_post': None,
    'insta_current_post': None,
    'tour_interval': 30 * 60,  # 30 minutes in seconds
    'nz_interval': 30 * 60,
    'insta_interval': 3 * 60  # 3 minutes for Instagram sync
}

def load_posts(filepath):
    """Load posts from JSON file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return []

def save_posts(filepath, posts):
    """Save posts to JSON file"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(posts, f, indent=2)

def update_posting_status(post_type, is_running, message='', current_post=None):
    """Update posting status for a specific post type"""
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

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

# Posts API endpoints
@app.route('/api/posts/<post_type>', methods=['GET'])
def get_posts(post_type):
    """Get posts for a specific type"""
    if post_type == 'tour':
        posts = load_posts(TOUR_FILE)
    elif post_type == 'nz':
        posts = load_posts(NZ_FILE)
    elif post_type == 'insta':
        posts = load_posts(INSTA_FILE)
    else:
        return jsonify({'error': 'Invalid post type'}), 400
    
    return jsonify(posts)

@app.route('/api/posts/<post_type>', methods=['POST'])
def add_post(post_type):
    """Add a new post"""
    if post_type == 'tour':
        filepath = TOUR_FILE
    elif post_type == 'nz':
        filepath = NZ_FILE
    elif post_type == 'insta':
        filepath = INSTA_FILE
    else:
        return jsonify({'error': 'Invalid post type'}), 400
    
    data = request.get_json()
    posts = load_posts(filepath)
    
    new_post = {
        'message': data.get('message', ''),
        'image_filename': data.get('image_filename', '')
    }
    posts.append(new_post)
    save_posts(filepath, posts)
    
    return jsonify(new_post), 201

@app.route('/api/posts/<post_type>/<int:index>', methods=['PUT'])
def update_post(post_type, index):
    """Update a post"""
    if post_type == 'tour':
        filepath = TOUR_FILE
    elif post_type == 'nz':
        filepath = NZ_FILE
    elif post_type == 'insta':
        filepath = INSTA_FILE
    else:
        return jsonify({'error': 'Invalid post type'}), 400
    
    posts = load_posts(filepath)
    if index < 0 or index >= len(posts):
        return jsonify({'error': 'Post not found'}), 404
    
    data = request.get_json()
    posts[index]['message'] = data.get('message', posts[index].get('message', ''))
    posts[index]['image_filename'] = data.get('image_filename', posts[index].get('image_filename', ''))
    
    save_posts(filepath, posts)
    return jsonify(posts[index])

@app.route('/api/posts/<post_type>/<int:index>', methods=['DELETE'])
def delete_post(post_type, index):
    """Delete a post"""
    if post_type == 'tour':
        filepath = TOUR_FILE
    elif post_type == 'nz':
        filepath = NZ_FILE
    elif post_type == 'insta':
        filepath = INSTA_FILE
    else:
        return jsonify({'error': 'Invalid post type'}), 400
    
    posts = load_posts(filepath)
    if index < 0 or index >= len(posts):
        return jsonify({'error': 'Post not found'}), 404
    
    posts.pop(index)
    save_posts(filepath, posts)
    
    return jsonify({'success': True})

# Image upload endpoint
@app.route('/api/upload', methods=['POST'])
def upload_image():
    """Upload an image file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        filename = file.filename
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'filename': filename}), 201
    
    return jsonify({'error': 'File upload failed'}), 400

# Control endpoints
@app.route('/api/control/tour/start', methods=['POST'])
def start_tour():
    """Start tour posting"""
    if not posting_state['tour_running']:
        tour.set_status_callback(update_posting_status)
        tour.set_interval(posting_state['tour_interval'])
        tour.stop_event.clear()
        thread = threading.Thread(target=tour.run_tour, daemon=True)
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
        tour.stop_tour()
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
        thread = threading.Thread(target=visa.run_nz, daemon=True)
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
        visa.stop_nz()
        posting_state['nz_running'] = False
        update_posting_status('nz', False, '', None)
        return jsonify({'status': 'NZ posting stopped'}), 200
    return jsonify({'status': 'NZ not running'}), 200

@app.route('/api/control/insta/start', methods=['POST'])
def start_insta():
    """Start Instagram sync"""
    if not posting_state['insta_running']:
        insta.set_status_callback(update_posting_status)
        insta.set_interval(posting_state['insta_interval'])
        insta.stop_event.clear()
        thread = threading.Thread(target=insta.run_insta_sync, daemon=True)
        thread.start()
        posting_state['threads']['insta'] = thread
        posting_state['insta_running'] = True
        update_posting_status('insta', True, 'Starting...', None)
        return jsonify({'status': 'Instagram sync started'}), 200
    return jsonify({'status': 'Instagram already running'}), 200

@app.route('/api/control/insta/stop', methods=['POST'])
def stop_insta():
    """Stop Instagram sync"""
    if posting_state['insta_running']:
        insta.stop_insta_sync()
        posting_state['insta_running'] = False
        update_posting_status('insta', False, '', None)
        return jsonify({'status': 'Instagram sync stopped'}), 200
    return jsonify({'status': 'Instagram not running'}), 200

@app.route('/api/control/all/start', methods=['POST'])
def start_all():
    """Start all posting tasks"""
    start_tour()
    start_nz()
    start_insta()
    return jsonify({'status': 'All tasks started'}), 200

@app.route('/api/control/all/stop', methods=['POST'])
def stop_all():
    """Stop all posting tasks"""
    stop_tour()
    stop_nz()
    stop_insta()
    return jsonify({'status': 'All tasks stopped'}), 200

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current status of all posting tasks"""
    return jsonify({
        'tour_running': posting_state['tour_running'],
        'nz_running': posting_state['nz_running'],
        'insta_running': posting_state['insta_running'],
        'tour_status': posting_state['tour_status'],
        'nz_status': posting_state['nz_status'],
        'insta_status': posting_state['insta_status'],
        'tour_current_post': posting_state['tour_current_post'],
        'nz_current_post': posting_state['nz_current_post'],
        'insta_current_post': posting_state['insta_current_post'],
        'tour_interval': posting_state['tour_interval'],
        'nz_interval': posting_state['nz_interval'],
        'insta_interval': posting_state['insta_interval']
    })

# Interval management endpoints
@app.route('/api/interval/<post_type>', methods=['GET'])
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
    elif post_type == 'insta':
        insta.set_interval(interval)
    
    return jsonify({'success': True, 'interval': interval})

# Serve images
@app.route('/images/<filename>')
def serve_image(filename):
    """Serve image files"""
    return send_from_directory('images', filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
