// Global state
let currentPostType = null;
let currentPostIndex = null;
let existingImages = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeTabs();
    initializeButtons();
    loadExistingImages();
    loadAllPosts();
    loadIntervals();
    updateStatus();
    setInterval(updateStatus, 3000);
});

// Tab functionality
function initializeTabs() {
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', function() {
            switchTab(this.dataset.tab);
        });
    });
}

function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active from all buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Mark button as active
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
}

// Button initialization
function initializeButtons() {
    // Tour controls
    document.getElementById('startTourBtn').addEventListener('click', () => startPosting('tour'));
    document.getElementById('stopTourBtn').addEventListener('click', () => stopPosting('tour'));
    
    // NZ controls
    document.getElementById('startNZBtn').addEventListener('click', () => startPosting('nz'));
    document.getElementById('stopNZBtn').addEventListener('click', () => stopPosting('nz'));
    
    // Insta controls
    document.getElementById('startInstaBtn').addEventListener('click', () => startPosting('insta'));
    document.getElementById('stopInstaBtn').addEventListener('click', () => stopPosting('insta'));
    
    // Global controls
    document.getElementById('runAllBtn').addEventListener('click', startAllPosting);
    document.getElementById('stopAllBtn').addEventListener('click', stopAllPosting);
    
    // Post form
    document.getElementById('postForm').addEventListener('submit', submitPost);
    document.getElementById('postImage').addEventListener('change', previewImage);
    document.getElementById('existingImage').addEventListener('change', selectExistingImage);
}

// Load existing images
function loadExistingImages() {
    const imageFiles = ['us.png', 'canada.png', 'uk.png', 'uae.jpeg', 'europe.png', 'nz.jpeg', 'nz1.jpeg', 'nz2.jpeg', 'nz3.jpeg', 'nz4.jpeg', 'nz5.jpeg', 'nz6.jpeg', 'australia.jpeg', 'au1.jpeg', 'au2.jpeg', 'asia.jpeg'];
    const select = document.getElementById('existingImage');
    
    imageFiles.forEach(file => {
        const option = document.createElement('option');
        option.value = file;
        option.textContent = file;
        select.appendChild(option);
    });
}

// Post management
function loadAllPosts() {
    loadPosts('tour');
    loadPosts('nz');
    loadPosts('insta');
}

function loadPosts(postType) {
    fetch(`/api/posts/${postType}`)
        .then(response => response.json())
        .then(posts => {
            const container = document.getElementById(`${postType}PostsList`);
            container.innerHTML = '';
            
            if (posts.length === 0) {
                container.innerHTML = '<p class="loading">No posts yet. Add one to get started!</p>';
                return;
            }
            
            posts.forEach((post, index) => {
                const card = createPostCard(postType, post, index);
                container.appendChild(card);
            });
        })
        .catch(error => {
            console.error('Error loading posts:', error);
            document.getElementById(`${postType}PostsList`).innerHTML = '<p class="error">Error loading posts</p>';
        });
}

function createPostCard(postType, post, index) {
    const card = document.createElement('div');
    card.className = 'post-card';
    
    const imageElem = post.image_filename ? 
        `<img src="/images/${post.image_filename}" alt="Post" class="post-image" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22200%22%3E%3Crect fill=%22%23ddd%22 width=%22300%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 fill=%22%23999%22%3ENo Image%3C/text%3E%3C/svg%3E'"></img>` :
        `<div class="post-image" style="display: flex; align-items: center; justify-content: center; background: #ddd;">No Image</div>`;
    
    card.innerHTML = `
        ${imageElem}
        <div class="post-message">${escapeHtml(post.message)}</div>
        ${post.image_filename ? `<div class="post-image-name">📁 ${escapeHtml(post.image_filename)}</div>` : ''}
        <div class="post-actions">
            <button class="btn btn-info btn-small" onclick="editPost('${postType}', ${index})">✏️ Edit</button>
            <button class="btn btn-danger btn-small" onclick="deletePost('${postType}', ${index})">❌ Delete</button>
        </div>
    `;
    
    return card;
}

function editPost(postType, index) {
    const posts = document.getElementById(`${postType}PostsList`);
    // Fetch fresh data to get the actual post
    fetch(`/api/posts/${postType}`)
        .then(response => response.json())
        .then(allPosts => {
            if (index < allPosts.length) {
                const post = allPosts[index];
                currentPostType = postType;
                currentPostIndex = index;
                document.getElementById('postMessage').value = post.message;
                document.getElementById('existingImage').value = post.image_filename || '';
                
                if (post.image_filename) {
                    const preview = document.getElementById('imagePreview');
                    preview.src = `/images/${post.image_filename}`;
                    preview.style.display = 'block';
                } else {
                    document.getElementById('imagePreview').style.display = 'none';
                }
                
                document.getElementById('postImage').value = '';
                openAddPostModal(postType);
            }
        });
}

function deletePost(postType, index) {
    if (confirm('Are you sure you want to delete this post?')) {
        fetch(`/api/posts/${postType}/${index}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            loadPosts(postType);
            showSuccess('Post deleted successfully!');
        })
        .catch(error => {
            console.error('Error deleting post:', error);
            showError('Error deleting post');
        });
    }
}

// Modal functions
function openAddPostModal(postType) {
    currentPostType = postType;
    currentPostIndex = null;
    document.getElementById('postMessage').value = '';
    document.getElementById('existingImage').value = '';
    document.getElementById('postImage').value = '';
    document.getElementById('imagePreview').style.display = 'none';
    document.getElementById('postModal').classList.add('active');
}

function closeAddPostModal() {
    document.getElementById('postModal').classList.remove('active');
    currentPostType = null;
    currentPostIndex = null;
}

// Form submission
function submitPost(e) {
    e.preventDefault();
    
    const message = document.getElementById('postMessage').value.trim();
    const fileInput = document.getElementById('postImage');
    const existingImageSelect = document.getElementById('existingImage');
    
    if (!message) {
        showError('Please enter a message');
        return;
    }
    
    let imageFilename = existingImageSelect.value;
    
    if (fileInput.files.length > 0) {
        // Upload new image
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        
        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            imageFilename = data.filename;
            savePost(message, imageFilename);
        })
        .catch(error => {
            console.error('Error uploading image:', error);
            showError('Error uploading image');
        });
    } else {
        savePost(message, imageFilename);
    }
}

function savePost(message, imageFilename) {
    const postData = {
        message: message,
        image_filename: imageFilename
    };
    
    const method = currentPostIndex !== null ? 'PUT' : 'POST';
    const url = currentPostIndex !== null ? 
        `/api/posts/${currentPostType}/${currentPostIndex}` :
        `/api/posts/${currentPostType}`;
    
    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(postData)
    })
    .then(response => response.json())
    .then(data => {
        closeAddPostModal();
        loadPosts(currentPostType);
        showSuccess(`Post ${currentPostIndex !== null ? 'updated' : 'added'} successfully!`);
    })
    .catch(error => {
        console.error('Error saving post:', error);
        showError('Error saving post');
    });
}

// Image preview
function previewImage(e) {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('imagePreview');
            preview.src = e.target.result;
            preview.style.display = 'block';
            document.getElementById('existingImage').value = '';
        };
        reader.readAsDataURL(file);
    }
}

function selectExistingImage(e) {
    const filename = e.target.value;
    if (filename) {
        const preview = document.getElementById('imagePreview');
        preview.src = `/images/${filename}`;
        preview.style.display = 'block';
        document.getElementById('postImage').value = '';
    } else {
        document.getElementById('imagePreview').style.display = 'none';
    }
}

// Control functions
function startPosting(postType) {
    fetch(`/api/control/${postType}/start`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        showSuccess(`${postType.toUpperCase()} posting started!`);
        updateStatus();
    })
    .catch(error => {
        console.error('Error starting posting:', error);
        showError('Error starting posting');
    });
}

function stopPosting(postType) {
    fetch(`/api/control/${postType}/stop`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        showSuccess(`${postType.toUpperCase()} posting stopped!`);
        updateStatus();
    })
    .catch(error => {
        console.error('Error stopping posting:', error);
        showError('Error stopping posting');
    });
}

function startAllPosting() {
    fetch('/api/control/all/start', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        showSuccess('All posting tasks started!');
        updateStatus();
    })
    .catch(error => {
        console.error('Error starting all posting:', error);
        showError('Error starting posting tasks');
    });
}

function stopAllPosting() {
    fetch('/api/control/all/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        showSuccess('All posting tasks stopped!');
        updateStatus();
    })
    .catch(error => {
        console.error('Error stopping all posting:', error);
        showError('Error stopping posting tasks');
    });
}

// Status updates
function updateStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(status => {
            updateButtonState('Tour', status.tour_running);
            updateButtonState('NZ', status.nz_running);
            updateButtonState('Insta', status.insta_running);
            
            // Build status messages
            let statusMessages = [];
            if (status.tour_running) {
                statusMessages.push(`📍 Tour: ${status.tour_status || 'Running'} ${status.tour_current_post ? ' - ' + status.tour_current_post : ''}`);
            }
            if (status.nz_running) {
                statusMessages.push(`📍 NZ: ${status.nz_status || 'Running'} ${status.nz_current_post ? ' - ' + status.nz_current_post : ''}`);
            }
            if (status.insta_running) {
                statusMessages.push(`📍 Insta: ${status.insta_status || 'Running'} ${status.insta_current_post ? ' - ' + status.insta_current_post : ''}`);
            }
            
            const globalElement = document.getElementById('globalStatus');
            if (statusMessages.length > 0) {
                globalElement.innerHTML = `🟢 ${statusMessages.join(' | ')}`;
            } else {
                globalElement.textContent = '🔴 All Stopped';
            }
        })
        .catch(error => console.error('Error updating status:', error));
}

// Load and display current intervals
function loadIntervals() {
    fetch('/api/status')
        .then(response => response.json())
        .then(status => {
            document.getElementById('tourInterval').value = Math.round(status.tour_interval / 60);
            document.getElementById('nzInterval').value = Math.round(status.nz_interval / 60);
            document.getElementById('instaInterval').value = Math.round(status.insta_interval / 60);
        })
        .catch(error => console.error('Error loading intervals:', error));
}

// Update interval for a posting type
function updateInterval(postType) {
    const inputId = postType === 'tour' ? 'tourInterval' : 
                    postType === 'nz' ? 'nzInterval' : 'instaInterval';
    const minutes = parseInt(document.getElementById(inputId).value);
    
    if (!minutes || minutes <= 0) {
        showError('Please enter a valid interval');
        return;
    }
    
    const seconds = minutes * 60;
    
    fetch(`/api/interval/${postType}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ interval: seconds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccess(`${postType.toUpperCase()} interval updated to ${minutes} minutes`);
        } else {
            showError('Failed to update interval');
        }
    })
    .catch(error => {
        console.error('Error updating interval:', error);
        showError('Error updating interval');
    });
}

function updateButtonState(type, isRunning) {
    const prefix = type === 'Tour' ? 'Tour' : type === 'NZ' ? 'NZ' : 'Insta';
    const startBtn = document.getElementById(`start${prefix}Btn`);
    const stopBtn = document.getElementById(`stop${prefix}Btn`);
    
    if (isRunning) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        startBtn.style.opacity = '0.5';
        stopBtn.style.opacity = '1';
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        startBtn.style.opacity = '1';
        stopBtn.style.opacity = '0.5';
    }
}

// Utility functions
function showSuccess(message) {
    const controls = document.querySelector('.controls-section');
    const alert = document.createElement('div');
    alert.className = 'success';
    alert.textContent = message;
    controls.insertBefore(alert, controls.firstChild);
    setTimeout(() => alert.remove(), 3000);
}

function showError(message) {
    const controls = document.querySelector('.controls-section');
    const alert = document.createElement('div');
    alert.className = 'error';
    alert.textContent = '❌ ' + message;
    controls.insertBefore(alert, controls.firstChild);
    setTimeout(() => alert.remove(), 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Close modal on outside click
window.addEventListener('click', function(event) {
    const modal = document.getElementById('postModal');
    if (event.target === modal) {
        closeAddPostModal();
    }
});
