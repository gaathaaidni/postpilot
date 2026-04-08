let currentTab = 'dashboard';
let statusInterval = null;
let currentModulePosts = [];
let grahakRefreshTimer = null;

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
        if (['tour', 'nz', 'gaatha', 'grahak', 'insta'].includes(currentTab)) {
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
                    <small id="dash-tour-interval" class="text-muted">Interval: --</small>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-green-soft"><i class="fa-solid fa-passport"></i></div>
                <div class="stat-info">
                    <h4>Phoenix Intl</h4>
                    <p id="dash-status-nz">Checking...</p>
                    <small id="dash-nz-interval" class="text-muted">Interval: --</small>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-purple-soft"><i class="fa-solid fa-scroll"></i></div>
                <div class="stat-info">
                    <h4>Gaatha AI</h4>
                    <p id="dash-status-gaatha">Checking...</p>
                    <small id="dash-gaatha-interval" class="text-muted">Interval: --</small>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-red-soft"><i class="fa-solid fa-bullhorn"></i></div>
                <div class="stat-info">
                    <h4>Grahak Chetna</h4>
                    <p id="dash-status-grahak">Checking...</p>
                    <small id="dash-grahak-interval" class="text-muted">Interval: --</small>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-orange-soft"><i class="fa-brands fa-instagram"></i></div>
                <div class="stat-info">
                    <h4>Instagram</h4>
                    <p id="dash-status-insta">Checking...</p>
                    <small id="dash-insta-interval" class="text-muted">Interval: --</small>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title"><i class="fa-solid fa-sliders"></i> Feature Control Panel</div>
            </div>
            <div style="display:grid; gap:1rem; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); padding:1rem 0;">
                ${['tour','nz','gaatha','grahak','insta'].map(type => {
                    const labels = {
                        tour: 'Nexora Suite',
                        nz: 'Phoenix Intl',
                        gaatha: 'Gaatha AI',
                        grahak: 'Grahak Chetna',
                        insta: 'Instagram Sync'
                    };
                    const icons = {
                        tour: 'fa-earth-americas',
                        nz: 'fa-passport',
                        gaatha: 'fa-scroll',
                        grahak: 'fa-bullhorn',
                        insta: 'fa-instagram'
                    };
                    return `
                        <div class="control-tile" style="border:1px solid var(--border); border-radius: 12px; padding:1rem; background: var(--surface);">
                            <div style="display:flex; align-items:center; justify-content:space-between; gap:0.75rem;">
                                <div>
                                    <div style="font-weight:600; display:flex; align-items:center; gap:0.5rem;"><i class="fa-solid ${icons[type]}"></i> ${labels[type]}</div>
                                    <div style="font-size:0.9rem; color: var(--text-muted);" id="dash-${type}-summary">Status unknown</div>
                                </div>
                                <div style="text-align:right; font-size:0.85rem; color: var(--text-muted);" id="dash-${type}-interval-short">Interval: --</div>
                            </div>
                            <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-top:1rem;">
                                <button class="btn btn-sm btn-primary" onclick="controlModule('${type}', 'start')"><i class="fa-solid fa-play"></i> Start</button>
                                <button class="btn btn-sm btn-danger" onclick="controlModule('${type}', 'stop')"><i class="fa-solid fa-stop"></i> Stop</button>
                                <button class="btn btn-sm btn-outline-danger" onclick="deleteAllPosts('${type}')"><i class="fa-solid fa-trash-can"></i> Clear Posts</button>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
            <div style="display:flex; gap:0.75rem; flex-wrap:wrap; justify-content:flex-end; padding-top:0.5rem;">
                <button class="btn btn-danger" onclick="controlAll('stop')"><i class="fa-solid fa-stop"></i> Stop All</button>
                <button class="btn btn-primary" onclick="controlAll('start')"><i class="fa-solid fa-play"></i> Run All</button>
                <button class="btn btn-secondary" onclick="refreshDashboard()"><i class="fa-solid fa-sync-alt"></i> Refresh Status</button>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title"><i class="fa-solid fa-filter"></i> Post Quick Browser</div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-size: 0.85rem; color: var(--text-muted);">Filter:</span>
                    <select id="dashboard-filter" class="form-control" style="width: auto; padding: 0.3rem;" onchange="filterDashboardPosts(this.value)">
                        <option value="">All Types (Select...)</option>
                        <option value="tour">Nexora Suite (Tour)</option>
                        <option value="nz">Phoenix Intl (Visa)</option>
                        <option value="gaatha">Gaatha AI</option>
                        <option value="grahak">Grahak Chetna</option>
                        <option value="insta">Instagram Sync</option>
                    </select>
                </div>
            </div>
            <div id="dashboard-posts-list" style="margin-top: 1rem; border-top: 1px solid var(--border);">
                <div style="color: var(--text-muted); font-size: 0.9rem; padding: 2rem; text-align: center;">
                    <i class="fa-solid fa-arrow-up"></i> Select a post type above to browse current content
                </div>
            </div>
        </div>
    `;
    updateStatus(); // Immediate refresh
}

async function filterDashboardPosts(type) {
    const list = document.getElementById('dashboard-posts-list');
    if (!type) {
        list.innerHTML = `<div style="color: var(--text-muted); font-size: 0.9rem; padding: 2rem; text-align: center;"><i class="fa-solid fa-arrow-up"></i> Select a post type to browse content</div>`;
        return;
    }
    
    list.innerHTML = `<div style="text-align:center; padding: 3rem;"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading ${type} posts...</div>`;
    
    try {
        const res = await fetch(`/api/posts/${type}`);
        const posts = await res.json();
        
        if (posts.length === 0) {
            list.innerHTML = `<div style="text-align:center; padding: 3rem; color: var(--text-muted);">No posts found for <strong>${type}</strong>.</div>`;
            return;
        }

        list.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; padding: 0.5rem 1rem; border-bottom: 1px solid var(--border);">
                <h5 style="margin:0;">${type.charAt(0).toUpperCase() + type.slice(1)} Posts</h5>
                <button class="btn btn-sm btn-danger" onclick="deleteAllPosts('${type}')">
                    <i class="fa-solid fa-trash-can"></i> Delete All ${type.charAt(0).toUpperCase() + type.slice(1)} Posts
                </button>
            </div>
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 100px">Image</th>
                            <th>Message</th>
                            <th style="width: 150px">Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${posts.map(post => `
                            <tr>
                                <td>
                                    ${post.image_filename ? 
                                        `<img src="/images/${post.image_filename}" class="post-img-preview" alt="Post">` : 
                                        `<div class="post-img-preview" style="background:#f1f5f9; display:flex; align-items:center; justify-content:center;"><i class="fa-solid fa-image" style="color:#cbd5e1"></i></div>`
                                    }
                                </td>
                                <td><div style="max-height: 60px; overflow-y: auto; font-size: 0.9rem;">${post.message || '<em class="text-muted">No message</em>'}</div></td>
                                <td><small class="text-muted">${post.created_at ? new Date(post.created_at + 'Z').toLocaleString() : 'N/A'}</small></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        list.innerHTML = `<div style="text-align:center; padding: 3rem; color: var(--danger);">Failed to load posts for ${type}.</div>`;
    }
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
    set('dash-status-grahak', mapStatus(data.grahak_running));
    set('dash-status-insta', mapStatus(data.insta_running));

    set('dash-tour-interval', `Interval: ${data.tour_interval || 0} sec`);
    set('dash-nz-interval', `Interval: ${data.nz_interval || 0} sec`);
    set('dash-gaatha-interval', `Interval: ${data.gaatha_interval || 0} sec`);
    set('dash-grahak-interval', `Interval: ${data.grahak_interval || 0} sec`);
    set('dash-insta-interval', `Interval: ${data.insta_interval || 0} sec`);

    set('dash-tour-summary', `${data.tour_running ? 'Running' : 'Stopped'} · ${data.tour_status || 'No activity yet'}`);
    set('dash-nz-summary', `${data.nz_running ? 'Running' : 'Stopped'} · ${data.nz_status || 'No activity yet'}`);
    set('dash-gaatha-summary', `${data.gaatha_running ? 'Running' : 'Stopped'} · ${data.gaatha_status || 'No activity yet'}`);
    set('dash-grahak-summary', `${data.grahak_running ? 'Running' : 'Stopped'} · ${data.grahak_status || 'No activity yet'}`);
    set('dash-insta-summary', `${data.insta_running ? 'Running' : 'Stopped'} · ${data.insta_status || 'No activity yet'}`);
}

function refreshDashboard() {
    updateStatus();
    const filter = document.getElementById('dashboard-filter');
    if (filter && filter.value) filterDashboardPosts(filter.value);
}

async function deleteAllPosts(type) {
    const msg = `Are you sure you want to delete ALL posts for <strong>${type.toUpperCase()}</strong>? This action cannot be undone.`;
    
    showConfirm(msg, async () => {
        try {
            const res = await fetch(`/api/posts/${type}/all`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                filterDashboardPosts(type); // Refresh the list
            } else {
                alert('Error deleting posts: ' + (data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error('Error during delete all:', e);
        }
    });
}

function showConfirm(htmlMessage, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    const msgEl = document.getElementById('confirm-msg');
    const yesBtn = document.getElementById('confirm-yes-btn');

    msgEl.innerHTML = htmlMessage;
    modal.classList.add('show');

    // Replace button to clear old event listeners
    const newBtn = yesBtn.cloneNode(true);
    yesBtn.parentNode.replaceChild(newBtn, yesBtn);

    newBtn.onclick = () => {
        onConfirm();
        closeConfirmModal();
    };
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.remove('show');
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
                    </tbo                </table>
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
    showToast('Interval updated successfully!', 'success');
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

/**
 * Elegant Toast Notification
 * @param {string} message 
 * @param {string} type - 'success', 'error', 'warning'
 */
function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation';
    
    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.4s ease';
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}
