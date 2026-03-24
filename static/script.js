let currentTab = 'dashboard';
let statusInterval = null;
let currentModulePosts = [];

document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    createMobileDropdown();
    loadTab('dashboard');
    startStatusPolling();
});

function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadTab(btn.dataset.tab);
            
            // Sync mobile dropdown
            const sel = document.querySelector('.mobile-nav-select');
            if(sel) sel.value = btn.dataset.tab;
        });
    });
}

function createMobileDropdown() {
    const sidebar = document.querySelector('.sidebar');
    const navButtons = document.querySelectorAll('.nav-item');
    if (!sidebar || navButtons.length === 0) return;

    const container = document.createElement('div');
    container.className = 'mobile-nav-container';
    container.style.marginTop = '1rem';

    const select = document.createElement('select');
    select.className = 'mobile-nav-select';
    select.style.width = '100%';
    select.style.padding = '0.5rem';
    select.style.borderRadius = '6px';
    select.style.border = '1px solid var(--border)';

    navButtons.forEach(btn => {
        const option = document.createElement('option');
        option.value = btn.dataset.tab;
        option.textContent = btn.textContent.trim();
        if (btn.classList.contains('active')) option.selected = true;
        select.appendChild(option);
    });

    select.addEventListener('change', (e) => {
        const tab = e.target.value;
        const targetBtn = document.querySelector(`.nav-item[data-tab="${tab}"]`);
        if (targetBtn) targetBtn.click();
    });

    container.appendChild(select);
    sidebar.appendChild(container);
}

function loadTab(tab) {
    currentTab = tab;
    const content = document.getElementById('content-area');
    const title = document.getElementById('page-title');
    
    // Update Title
    const titles = {
        'dashboard': 'System Overview',
        'tour': 'Nexora Suite Management',
        'nz': 'Phoenix International Management',
        'gaatha': 'Gaatha AI Automation',
        'insta': 'Instagram Synchronization',
        'grahak': 'Grahak Chetna Automation'
    };
    title.textContent = titles[tab] || 'Dashboard';

    if (tab === 'dashboard') {
        renderDashboard(content);
    } else if (tab === 'grahak') {
        renderGrahak(content);
    } else {
        renderModule(content, tab);
    }
}

async function startStatusPolling() {
    updateStatus();
    statusInterval = setInterval(updateStatus, 3000);
}

async function updateStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        // Update Dashboard indicators if on dashboard
        if (currentTab === 'dashboard') {
            updateDashboardStatus(data);
        }
        
        // Update Module specific indicators
        if (['tour', 'nz', 'gaatha', 'insta'].includes(currentTab)) {
            updateModuleStatus(currentTab, data);
        }
    } catch (e) {
        console.error("Status poll failed", e);
    }
}

function renderDashboard(container) {
    container.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon bg-blue-soft"><i class="fa-solid fa-earth-americas"></i></div>
                <div class="stat-info">
                    <h4>Nexora Suite</h4>
                    <p id="dash-status-tour">Checking...</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-green-soft"><i class="fa-solid fa-passport"></i></div>
                <div class="stat-info">
                    <h4>Phoenix Intl</h4>
                    <p id="dash-status-nz">Checking...</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-purple-soft"><i class="fa-solid fa-scroll"></i></div>
                <div class="stat-info">
                    <h4>Gaatha AI</h4>
                    <p id="dash-status-gaatha">Checking...</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-orange-soft"><i class="fa-brands fa-instagram"></i></div>
                <div class="stat-info">
                    <h4>Instagram</h4>
                    <p id="dash-status-insta">Checking...</p>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <div class="card-title">Recent System Logs</div>
            </div>
            <div style="color: var(--text-muted); font-size: 0.9rem;">
                System operating normally. Select a module from the sidebar to manage posts.
            </div>
        </div>
    `;
    updateStatus(); // Immediate refresh
}

function updateDashboardStatus(data) {
    const mapStatus = (running) => running ? 
        `<span style="color:var(--success)">Active</span>` : 
        `<span style="color:var(--text-muted)">Stopped</span>`;
    
    const set = (id, val) => {
        const el = document.getElementById(id);
        if(el) el.innerHTML = val;
    };

    set('dash-status-tour', mapStatus(data.tour_running));
    set('dash-status-nz', mapStatus(data.nz_running));
    set('dash-status-gaatha', mapStatus(data.gaatha_running));
    set('dash-status-insta', mapStatus(data.insta_running));
}

async function renderModule(container, type) {
    // Basic Layout
    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <div style="display:flex; align-items:center; gap:1rem;">
                    <span id="module-status-badge" class="status-badge status-stopped">Stopped</span>
                    <span id="module-status-text" style="font-size:0.9rem; color:var(--text-muted)"></span>
                </div>
                <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
                    <div style="display:flex; align-items:center; margin-right:1rem;">
                        <span style="font-size:0.85rem; color:var(--text-muted); margin-right:0.5rem;">Interval (sec):</span>
                        <input type="number" id="interval-input" class="form-control" style="width:80px; padding:0.4rem;" value="1800">
                        <button class="btn btn-sm btn-secondary" onclick="saveInterval('${type}')" style="margin-left:0.5rem;">Set</button>
                    </div>
                    <button class="btn btn-danger btn-sm" onclick="controlModule('${type}', 'stop')"><i class="fa-solid fa-stop"></i> Stop</button>
                    <button class="btn btn-primary btn-sm" onclick="controlModule('${type}', 'start')"><i class="fa-solid fa-play"></i> Start</button>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title">Post Queue</div>
                <button class="btn btn-primary btn-sm" onclick="openModal('add', null, '${type}')"><i class="fa-solid fa-plus"></i> Add Post</button>
            </div>
            <div class="table-responsive" style="overflow-x:auto;">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 80px">Image</th>
                            <th>Message</th>
                            <th style="width: 120px">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="posts-table-body">
                        <tr><td colspan="3" style="text-align:center;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;

    // Load Data
    loadPosts(type);
    loadInterval(type);
    updateStatus();
}

async function loadPosts(type) {
    try {
        const res = await fetch(`/api/posts/${type}`);
        const posts = await res.json();
        currentModulePosts = posts;
        const tbody = document.getElementById('posts-table-body');
        
        if (!tbody) return;

        if (posts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding: 2rem; color: var(--text-muted);">No posts configured.</td></tr>`;
            return;
        }

        tbody.innerHTML = posts.map((post, index) => `
            <tr>
                <td>
                    ${post.image_filename ? 
                        `<img src="/images/${post.image_filename}" class="post-img-preview" alt="Post">` : 
                        `<div class="post-img-preview" style="background:#f1f5f9; display:flex; align-items:center; justify-content:center;"><i class="fa-solid fa-image" style="color:#cbd5e1"></i></div>`
                    }
                </td>
                <td>
                    <div class="text-truncate">${post.message || 'No caption'}</div>
                </td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick='openModal("edit", ${index}, "${type}")'><i class="fa-solid fa-pen"></i></button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deletePost('${type}', ${index})"><i class="fa-solid fa-trash"></i></button>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error("Load posts failed", e);
    }
}

async function loadInterval(type) {
    try {
        const res = await fetch(`/api/interval/${type}`);
        const data = await res.json();
        const input = document.getElementById('interval-input');
        if(input && data.interval) input.value = data.interval;
    } catch(e) {}
}

async function saveInterval(type) {
    const val = document.getElementById('interval-input').value;
    await fetch(`/api/interval/${type}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({interval: parseInt(val)})
    });
    alert('Interval updated');
}

async function controlModule(type, action) {
    await fetch(`/api/control/${type}/${action}`, { method: 'POST' });
    updateStatus();
}

async function controlAll(action) {
    await fetch(`/api/control/all/${action}`, { method: 'POST' });
    updateStatus();
}

function updateModuleStatus(type, data) {
    const badge = document.getElementById('module-status-badge');
    const text = document.getElementById('module-status-text');
    
    if (!badge) return;

    let isRunning = data[`${type}_running`];
    let statusMsg = data[`${type}_status`] || '';

    // Adjust key for insta
    if (type === 'insta') isRunning = data.insta_running;

    if (isRunning) {
        badge.className = 'status-badge status-running';
        badge.textContent = 'Running';
    } else {
        badge.className = 'status-badge status-stopped';
        badge.textContent = 'Stopped';
    }
    
    text.textContent = statusMsg;
}

// Grahak Special Handling
async function renderGrahak(container) {
    container.innerHTML = `
        <div class="stats-grid">
             <div class="stat-card">
                <div class="stat-icon bg-blue-soft"><i class="fa-solid fa-newspaper"></i></div>
                <div class="stat-info">
                    <h4>News Automation</h4>
                    <p id="grahak-news-status">Disabled</p>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title">Automation Controls</div>
            </div>
             <div style="display:flex; gap:1rem; margin-bottom:1rem; flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="grahakAction('run_news')">Run News Now</button>
                <button class="btn btn-secondary" onclick="grahakAction('start_news')">Enable Auto</button>
                <button class="btn btn-danger" onclick="grahakAction('stop_news')">Disable Auto</button>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title">Manual Upload</div>
            </div>
             <form id="grahak-upload-form">
                <div class="form-group">
                    <label>File (Image/Video)</label>
                    <input type="file" id="grahak-file" class="form-control">
                </div>
                <div class="form-group">
                    <label>Caption</label>
                    <textarea id="grahak-caption" class="form-control" rows="2"></textarea>
                </div>
                <div class="form-group">
                    <label style="display:block; margin-bottom:0.5rem;">Targets</label>
                    <div style="display:flex; gap:1rem; flex-wrap:wrap;">
                        <label><input type="checkbox" id="g-fb-feed" checked> FB Feed</label>
                        <label><input type="checkbox" id="g-fb-story"> FB Story</label>
                        <label><input type="checkbox" id="g-ig-feed"> IG Feed</label>
                        <label><input type="checkbox" id="g-ig-reel"> IG Reel</label>
                    </div>
                </div>
                <button type="button" class="btn btn-primary" onclick="grahakUpload()">Upload & Post</button>
            </form>
        </div>
    `;
    updateGrahakStatus();
}

async function updateGrahakStatus() {
    try {
        const res = await fetch('/api/grahak/status');
        const data = await res.json();
        const el = document.getElementById('grahak-news-status');
        if(el) el.textContent = data.news_enabled ? 'Active' : 'Disabled';
    } catch(e) {}
}

async function grahakAction(action) {
    await fetch(`/api/grahak/${action}`, {method: 'POST'});
    updateGrahakStatus();
}

async function grahakUpload() {
    const file = document.getElementById('grahak-file').files[0];
    if(!file) return alert("Select file");
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('caption', document.getElementById('grahak-caption').value);
    formData.append('fb_feed', document.getElementById('g-fb-feed').checked);
    formData.append('fb_story', document.getElementById('g-fb-story').checked);
    formData.append('ig_feed', document.getElementById('g-ig-feed').checked);
    formData.append('ig_reel', document.getElementById('g-ig-reel').checked);
    
    const btn = document.querySelector('#grahak-upload-form button');
    const oldText = btn.textContent;
    btn.textContent = 'Uploading...';
    btn.disabled = true;
    
    try {
        const res = await fetch('/api/grahak/upload_post', {method: 'POST', body: formData});
        const d = await res.json();
        alert('Upload processed: ' + JSON.stringify(d.results));
    } catch(e) {
        alert('Error uploading');
    }
    
    btn.textContent = oldText;
    btn.disabled = false;
}

// Post Modal Logic
function openModal(mode, data, type) {
    document.getElementById('post-modal').classList.add('show');
    document.getElementById('modal-title').textContent = mode === 'edit' ? 'Edit Post' : 'New Post';
    
    // Set hidden fields
    document.getElementById('post-type').value = type || '';
    
    if (mode === 'edit') {
        const post = currentModulePosts[data];
        document.getElementById('post-index').value = data;
        document.getElementById('post-message').value = post.message || '';
        document.getElementById('current-image-filename').value = post.image_filename || '';
        document.getElementById('file-name').textContent = post.image_filename || 'Change file...';
    } else {
        document.getElementById('post-index').value = '-1';
        document.getElementById('post-message').value = '';
        document.getElementById('current-image-filename').value = '';
        document.getElementById('file-name').textContent = 'Choose file or drag here';
        document.getElementById('post-file').value = '';
    }
}

function closeModal() {
    document.getElementById('post-modal').classList.remove('show');
}

function handleFileSelect(input) {
    if (input.files && input.files[0]) {
        document.getElementById('file-name').textContent = input.files[0].name;
    }
}

async function savePost() {
    const type = document.getElementById('post-type').value;
    const index = parseInt(document.getElementById('post-index').value);
    const message = document.getElementById('post-message').value;
    const fileInput = document.getElementById('post-file');
    let filename = document.getElementById('current-image-filename').value;

    if (fileInput.files.length > 0) {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const uploadRes = await fetch('/api/upload', {method: 'POST', body: formData});
        const uploadData = await uploadRes.json();
        if (uploadData.filename) {
            filename = uploadData.filename;
        }
    }

    const payload = { message, image_filename: filename };
    
    if (index >= 0) {
        await fetch(`/api/posts/${type}/${index}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
    } else {
        await fetch(`/api/posts/${type}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
    }

    closeModal();
    loadPosts(type);
}

async function deletePost(type, index) {
    if(confirm('Are you sure you want to delete this post?')) {
        await fetch(`/api/posts/${type}/${index}`, { method: 'DELETE' });
        loadPosts(type);
    }
}
