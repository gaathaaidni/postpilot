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
                <div class="card-title"><i class="fa-solid fa-filter"></i> Post Quick Browser</div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-size: 0.85rem; color: var(--text-muted);">Filter:</span>
                    <select id="dashboard-filter" class="form-control" style="width: auto; padding: 0.3rem;" onchange="filterDashboardPosts(this.value)">
                        <option value="">All Types (Select...)</option>
                        <option value="tour">Nexora Suite (Tour)</option>
                        <option value="nz">Phoenix Intl (Visa)</option>
                        <option value="gaatha">Gaatha AI</option>
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

function formatDateTime(isoString) {
    if (!isoString) return 'Never';
    // Append 'Z' to treat as UTC if not present, then convert to local time
    const date = new Date(isoString.endsWith('Z') ? isoString : isoString + 'Z');
    return date.toLocaleString();
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
                            <th style="width: 150px">Added</th>
                            <th style="width: 150px">Last Posted</th>
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
                                <td><small class="text-muted">${formatDateTime(post.created_at)}</small></td>
                                <td><small class="text-muted">${formatDateTime(post.last_posted_at)}</small></td>
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
    set('dash-status-insta', mapStatus(data.insta_running));
}

async function deleteAllPosts(type) {
    if (!confirm(`Are you sure you want to delete ALL posts for ${type}? This action cannot be undone.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/posts/${type}/all`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            alert(data.message);
            filterDashboardPosts(type); // Refresh the list
        } else {
            alert('Error deleting posts: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error('Error during delete all:', e);
        alert('Failed to delete posts. Please check console for details.');
    }
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
                            <th style="width: 120px">Last Posted</th>
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
                    <small class="text-muted">${formatDateTime(post.last_posted_at)}</small>
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
            <div class="stat-card">
                <div class="stat-icon bg-purple-soft"><i class="fa-solid fa-clock"></i></div>
                <div class="stat-info">
                    <h4>Scheduled Tasks</h4>
                    <p id="grahak-scheduled-count">0</p>
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
                    <label>Schedule Post (Optional)</label>
                    <input type="datetime-local" id="g-scheduled-at" class="form-control">
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

        <div class="card">
            <div class="card-header">
                <div class="card-title">Task Management</div>
            </div>
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>File / Task</th>
                            <th>Status</th>
                            <th>Progress</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="grahak-tasks-table">
                        <tr><td colspan="4" style="text-align:center;">No active tasks.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    `;
    updateGrahakStatus();
}

async function updateGrahakStatus() {
    // Stop polling if we navigated away from the Grahak tab
    if (currentTab !== 'grahak') {
        if (grahakRefreshTimer) clearTimeout(grahakRefreshTimer);
        grahakRefreshTimer = null;
        return;
    }

    try {
        const res = await fetch('/api/grahak/status');
        const data = await res.json();
        const el = document.getElementById('grahak-news-status');
        if(el) el.textContent = data.news_enabled ? 'Active' : 'Disabled';
        const schedEl = document.getElementById('grahak-scheduled-count');
        if(schedEl) schedEl.textContent = data.scheduled_count || 0;

        // Update Task Table
        const tasksRes = await fetch('/api/grahak/tasks');
        const tasks = await tasksRes.json();
        renderGrahakTasks(tasks);

        // Automatically refresh only if there are active tasks
        const hasActive = Object.values(tasks).some(t => t.status === 'processing' || t.status === 'scheduled');
        if (hasActive) {
            if (grahakRefreshTimer) clearTimeout(grahakRefreshTimer);
            grahakRefreshTimer = setTimeout(updateGrahakStatus, 3000);
        } else {
            grahakRefreshTimer = null;
        }
    } catch(e) {}
}

function renderGrahakTasks(tasks) {
    const tbody = document.getElementById('grahak-tasks-table');
    if (!tbody) return;

    const taskIds = Object.keys(tasks).sort((a, b) => tasks[b].created_at - tasks[a].created_at);
    if (taskIds.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No active tasks.</td></tr>';
        return;
    }

    tbody.innerHTML = taskIds.map(tid => {
        const t = tasks[tid];
        const statusClass = t.status === 'completed' ? 'text-success' : (t.status === 'failed' ? 'text-danger' : 'text-primary');
        const isCancellable = t.status === 'scheduled' || t.status === 'processing';
        
        return `
            <tr>
                <td>
                    <div style="font-weight:500;">${t.filename || tid}</div>
                    <div style="font-size:0.75rem; color:var(--text-muted);">${tid}</div>
                </td>
                <td><span class="${statusClass}">${t.status.toUpperCase()}</span></td>
                <td>
                    <div class="progress-bar-container" style="height:10px; margin-top:0;">
                        <div class="progress-bar" style="width:${t.progress || 0}%; height:10px;"></div>
                    </div>
                </td>
                <td>
                    <div style="display:flex; gap:0.25rem;">
                        <button class="btn btn-sm btn-secondary" title="View Details" onclick="viewTaskDetails('${tid}')">
                            <i class="fa-solid fa-circle-info"></i>
                        </button>
                        ${t.status === 'failed' ? `
                            <button class="btn btn-sm btn-primary" title="Retry" onclick="retryGrahakTask('${tid}')">
                                <i class="fa-solid fa-rotate-right"></i>
                            </button>
                        ` : ''}
                    <button class="btn btn-sm btn-outline-danger" onclick="cancelGrahakTask('${tid}')">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function cancelGrahakTask(taskId) {
    if(!confirm('Remove this task?')) return;
    await fetch(`/api/grahak/task/${taskId}`, { method: 'DELETE' });
    updateGrahakStatus();
}

async function viewTaskDetails(taskId) {
    try {
        const res = await fetch(`/api/grahak/task/${taskId}`);
        const data = await res.json();
        
        const modalHtml = `
            <div id="details-modal" class="modal show" style="display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.6); z-index: 9999; position: fixed; top: 0; left: 0; width: 100%; height: 100%;">
                <div class="card" style="width: 90%; max-width: 600px; max-height: 85vh; overflow-y: auto; box-shadow: 0 10px 25px rgba(0,0,0,0.2);">
                    <div class="card-header" style="position: sticky; top: 0; background: white; z-index: 10;">
                        <div class="card-title">Task Details</div>
                        <button class="btn btn-sm btn-secondary" onclick="document.getElementById('details-modal').remove()">Close</button>
                    </div>
                    <div style="padding: 1.5rem;">
                        <div style="margin-bottom: 1rem;"><strong>Status:</strong> <span class="status-badge ${data.status === 'completed' ? 'status-running' : 'status-stopped'}">${data.status.toUpperCase()}</span></div>
                        <div style="margin-bottom: 1rem;"><strong>Task ID:</strong> <code style="font-size: 0.8rem;">${taskId}</code></div>
                        <div style="margin-bottom: 1rem;"><strong>Created:</strong> ${new Date(data.created_at * 1000).toLocaleString()}</div>
                        
                        ${data.error ? `
                            <div style="margin-bottom: 1rem;">
                                <strong style="color: var(--danger);">Error Message:</strong>
                                <pre style="background: #fff5f5; padding: 12px; border-radius: 6px; border: 1px solid #feb2b2; white-space: pre-wrap; margin-top: 5px; font-size: 0.85rem; color: #c53030;">${data.error}</pre>
                            </div>
                        ` : ''}
                        
                        ${data.results ? `
                            <div style="margin-bottom: 1rem;">
                                <strong>API Response Data:</strong>
                                <pre style="background: #f8fafc; padding: 12px; border-radius: 6px; border: 1px solid var(--border); overflow-x: auto; margin-top: 5px; font-size: 0.8rem;">${JSON.stringify(data.results, null, 2)}</pre>
                            </div>
                        ` : ''}
                        
                        <div style="margin-bottom: 0.5rem;"><strong>Post Content:</strong></div>
                        <p style="font-style: italic; color: var(--text-muted); background: #f9f9f9; padding: 10px; border-radius: 4px; border-left: 4px solid var(--primary);">${data.caption || 'No caption provided'}</p>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    } catch (e) {
        alert("Could not load task details. The task may have been cleaned up.");
    }
}

async function retryGrahakTask(taskId) {
    if (!confirm('This will re-submit the post with the same caption and targets. Proceed?')) return;
    const res = await fetch(`/api/grahak/task/${taskId}/retry`, { method: 'POST' });
    const data = await res.json();
    if (data.task_id) {
        updateGrahakStatus();
    } else {
        alert('Retry failed: ' + (data.error || 'Unknown error'));
    }
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
    formData.append('scheduled_at', document.getElementById('g-scheduled-at').value);
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
