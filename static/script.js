const API_ROOT = '/api';
let currentTab = 'dashboard';
let currentPosts = [];

// --- Navigation ---
document.addEventListener('DOMContentLoaded', () => {
    // Navigation Buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all buttons and sections
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
            
            // Activate clicked button
            btn.classList.add('active');
            currentTab = btn.dataset.tab;
            
            // Sync Mobile Dropdown if exists
            const mobSelect = document.querySelector('.mobile-nav-select');
            if(mobSelect) mobSelect.value = currentTab;

            // Switch View
            if (['tour', 'nz', 'gaatha'].includes(currentTab)) {
                // These tabs use the generic Post Manager view
                document.getElementById('post-manager').classList.add('active');
                loadPostManager(currentTab);
            } else {
                // These tabs have specific views (dashboard, grahak, insta)
                const section = document.getElementById(currentTab);
                if (section) section.classList.add('active');
                if (currentTab === 'grahak') {
                    fetchGrahakStatus();
                    injectGrahakControls();
                }
            }
        });
    });
    
    // Initial status fetch
    updateStatus();
    setInterval(updateStatus, 3000);
    
    // Create Mobile Dropdown (injected for corporate view)
    createMobileDropdown();

    // Agent Toggle Listener (in Manager View)
    const agentToggle = document.getElementById('agent-toggle');
    if (agentToggle) {
        agentToggle.addEventListener('change', (e) => {
            if (['tour', 'nz', 'gaatha'].includes(currentTab)) {
                controlAgent(currentTab, e.target.checked ? 'start' : 'stop');
            }
        });
    }
});

function createMobileDropdown() {
    const sidebar = document.querySelector('.sidebar');
    const navButtons = document.querySelectorAll('.nav-btn');
    if (!sidebar || navButtons.length === 0) return;

    const container = document.createElement('div');
    container.className = 'mobile-nav-container';

    const select = document.createElement('select');
    select.className = 'mobile-nav-select';

    navButtons.forEach(btn => {
        const option = document.createElement('option');
        option.value = btn.dataset.tab;
        option.textContent = btn.innerText.trim();
        if (btn.classList.contains('active')) option.selected = true;
        select.appendChild(option);
    });

    select.addEventListener('change', (e) => {
        const tab = e.target.value;
        const targetBtn = document.querySelector(`.nav-btn[data-tab="${tab}"]`);
        if (targetBtn) targetBtn.click();
    });

    container.appendChild(select);
    // Append container after brand if possible
    const brand = sidebar.querySelector('.brand');
    if (brand) brand.after(container);
    else sidebar.prepend(container);
}

// --- Dashboard & Global Status ---
async function updateStatus() {
    try {
        const res = await fetch(`${API_ROOT}/status`);
        const data = await res.json();
        
        // Update Dashboard Cards
        updateStatCard('stat-tour', data.tour_running, data.tour_status);
        updateStatCard('stat-nz', data.nz_running, data.nz_status);
        updateStatCard('stat-gaatha', data.gaatha_running, data.gaatha_status);
        updateStatCard('stat-insta', data.insta_running, data.insta_status);
        
        // Dynamically Update Grahak Card (injected if missing)
        updateGrahakCard();

        // Update Insta View Status (Specific to the Insta tab)
        const instaStatusLarge = document.getElementById('insta-large-status');
        if(instaStatusLarge) {
             const statusText = instaStatusLarge.querySelector('span');
             if(data.insta_running) {
                 statusText.textContent = "ACTIVE";
                 statusText.style.color = "var(--success)";
             } else {
                 statusText.textContent = "IDLE";
                 statusText.style.color = "var(--danger)";
             }
        }

        // Update Agent Toggle if we are in a manager view
        if (['tour', 'nz', 'gaatha'].includes(currentTab)) {
            const key = `${currentTab}_running`;
            const isRunning = data[key];
            const toggle = document.getElementById('agent-toggle');
            const statusText = document.getElementById('agent-status-text');
            
            if (toggle && statusText) {
                toggle.checked = isRunning;
                statusText.textContent = isRunning ? "ONLINE" : "OFFLINE";
                statusText.style.color = isRunning ? "var(--success)" : "var(--text-muted)";
            }
        }
    } catch (e) { console.error('Status fetch error', e); }
}

function updateStatCard(id, running, text) {
    const card = document.getElementById(id);
    if (!card) return;
    const indicator = card.querySelector('.status-indicator');
    const activity = card.querySelector('.current-activity');
    
    if (running) {
        indicator.className = 'status-indicator running';
        indicator.querySelector('.text').textContent = 'ACTIVE';
        activity.textContent = text || 'Processing...';
        activity.style.color = 'var(--primary)';
    } else {
        indicator.className = 'status-indicator stopped';
        indicator.querySelector('.text').textContent = 'IDLE';
        activity.textContent = 'Standby';
        activity.style.color = 'var(--text-muted)';
    }
}

// Global Controls
window.controlAll = async (action) => {
    await fetch(`${API_ROOT}/control/all/${action}`, { method: 'POST' });
    updateStatus();
};

window.controlAgent = async (type, action) => {
    await fetch(`${API_ROOT}/control/${type}/${action}`, { method: 'POST' });
    updateStatus();
};

// --- Post Manager (Tour, NZ, Gaatha) ---
async function loadPostManager(type) {
    const titles = {
        'tour': 'Nexora Suite Manager',
        'nz': 'Nexora Phoenix Manager',
        'gaatha': 'Gaatha AI Manager'
    };
    const titleEl = document.getElementById('manager-title');
    if (titleEl) titleEl.innerText = titles[type];
    
    // Load Interval
    try {
        const intervalRes = await fetch(`${API_ROOT}/interval/${type}`);
        const intervalData = await intervalRes.json();
        const intervalInput = document.getElementById('interval-input');
        if (intervalInput) intervalInput.value = intervalData.interval || 1800;
    } catch (e) {}

    // Load Posts
    try {
        const res = await fetch(`${API_ROOT}/posts/${type}`);
        currentPosts = await res.json();
        renderPosts();
    } catch (e) {}
    
    updateStatus();
}

function renderPosts() {
    const grid = document.getElementById('posts-grid');
    if (!grid) return;
    grid.innerHTML = '';
    
    currentPosts.forEach((post, index) => {
        const card = document.createElement('div');
        card.className = 'post-card glass-panel';
        
        let imgHtml = '';
        if (post.image_filename) {
            imgHtml = `<img src="/images/${post.image_filename}" class="post-img" loading="lazy">`;
        } else {
            imgHtml = `<div class="post-img" style="background:#222;display:flex;align-items:center;justify-content:center;color:#444"><i class="fa-solid fa-image fa-2x"></i></div>`;
        }

        card.innerHTML = `
            ${imgHtml}
            <div class="post-body">
                <div class="post-text">${post.message || 'No message content'}</div>
                <div class="post-actions">
                    <button onclick="editPost(${index})" class="btn btn-sm btn-outline"><i class="fa-solid fa-pen"></i></button>
                    <button onclick="deletePost(${index})" class="btn btn-sm btn-danger"><i class="fa-solid fa-trash"></i></button>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

window.updateInterval = async () => {
    const val = document.getElementById('interval-input').value;
    await fetch(`${API_ROOT}/interval/${currentTab}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ interval: parseInt(val) })
    });
    showNotification('Interval Updated');
};

// --- Modals ---
window.openModal = (isEdit = false, index = null) => {
    const modal = document.getElementById('postModal');
    if (!modal) return;
    modal.style.display = 'block';
    
    const form = document.getElementById('postForm');
    
    if (isEdit && index !== null) {
        const post = currentPosts[index];
        document.getElementById('modalTitle').innerText = 'Edit Transmission';
        document.getElementById('postIndex').value = index;
        document.getElementById('postMessage').value = post.message;
        document.getElementById('postImage').value = post.image_filename;
        updateImagePreview(post.image_filename);
    } else {
        document.getElementById('modalTitle').innerText = 'New Transmission';
        if (form) form.reset();
        document.getElementById('postIndex').value = '';
        document.getElementById('imagePreview').innerHTML = '';
        document.getElementById('postImage').value = '';
    }
};

window.closeModal = () => {
    const modal = document.getElementById('postModal');
    if (modal) modal.style.display = 'none';
};

window.editPost = (index) => openModal(true, index);

window.deletePost = async (index) => {
    if (!confirm('Abort this transmission data?')) return;
    await fetch(`${API_ROOT}/posts/${currentTab}/${index}`, { method: 'DELETE' });
    loadPostManager(currentTab);
};

window.handleFileUpload = async (input) => {
    const file = input.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch(`${API_ROOT}/upload`, { method: 'POST', body: formData });
    const data = await res.json();
    
    if (data.filename) {
        document.getElementById('postImage').value = data.filename;
        updateImagePreview(data.filename);
    }
};

function updateImagePreview(filename) {
    const div = document.getElementById('imagePreview');
    if (filename) {
        div.innerHTML = `<img src="/images/${filename}" style="max-height:100px;border-radius:4px;">`;
    } else {
        div.innerHTML = '';
    }
}

window.handleFormSubmit = async (e) => {
    e.preventDefault();
    const idx = document.getElementById('postIndex').value;
    const payload = {
        message: document.getElementById('postMessage').value,
        image_filename: document.getElementById('postImage').value
    };
    
    if (idx !== '') {
        await fetch(`${API_ROOT}/posts/${currentTab}/${idx}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
    } else {
        await fetch(`${API_ROOT}/posts/${currentTab}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
    }
    closeModal();
    loadPostManager(currentTab);
};

// --- Grahak ---
window.triggerGrahak = async (endpoint) => {
    await fetch(`${API_ROOT}/grahak/${endpoint}`, { method: 'POST' });
    showNotification('Task Initiated');
    setTimeout(fetchGrahakStatus, 2000);
};

window.fetchGrahakStatus = async () => {
    try {
        const res = await fetch(`${API_ROOT}/grahak/status`);
        const data = await res.json();
        const newsEl = document.getElementById('grahak-last-news');
        if (newsEl) newsEl.innerText = data.last_news_run ? new Date(data.last_news_run).toLocaleString() : 'Never';
        fetchGrahakLogs();
    } catch(e) {}
};

window.fetchGrahakLogs = async () => {
    try {
        const res = await fetch(`${API_ROOT}/grahak/logs`);
        const data = await res.json();
        const container = document.getElementById('grahak-logs');
        
        let html = '<div style="color:#fff;margin-bottom:10px">--- NEWS LOGS ---</div>';
        html += data.news.map(l => `<div class="log-line">${l}</div>`).join('');
        
        if (container) {
            container.innerHTML = html;
            container.scrollTop = container.scrollHeight;
        }
    } catch(e) {}
};

async function updateGrahakCard() {
    try {
        const res = await fetch(`${API_ROOT}/grahak/status`);
        const data = await res.json();
        
        const grid = document.querySelector('.stats-grid');
        let card = document.getElementById('stat-grahak-chetna');
        
        // Inject card if missing
        if (!card && grid) {
            card = document.createElement('div');
            card.id = 'stat-grahak-chetna';
            card.className = 'stat-card glass-panel';
            card.innerHTML = `
                <h3>Grahak Chetna</h3>
                <div class="status-indicator">
                    <div class="pulse"></div>
                    <span class="text"></span>
                </div>
                <div class="current-activity"></div>
            `;
            grid.appendChild(card);
        }
        
        if (card) {
            const indicator = card.querySelector('.status-indicator');
            const activity = card.querySelector('.current-activity');
            const isRunning = data.news_enabled;
            
            if (isRunning) {
                indicator.className = 'status-indicator running';
                indicator.querySelector('.text').textContent = 'ACTIVE';
                activity.textContent = 'News Automation Running';
                activity.style.color = 'var(--primary)';
            } else {
                indicator.className = 'status-indicator stopped';
                indicator.querySelector('.text').textContent = 'IDLE';
                activity.textContent = 'News Automation Stopped';
                activity.style.color = 'var(--text-muted)';
            }
        }
    } catch(e) {}
}

function injectGrahakControls() {
    const section = document.getElementById('grahak');
    if (!section || document.getElementById('btn-create-video')) return;
    
    let panel = section.querySelector('.control-panel');
    if (!panel) {
        panel = document.createElement('div');
        panel.className = 'control-panel glass-panel';
        panel.style.marginBottom = '20px';
        section.prepend(panel);
    }
    
    const btn = document.createElement('button');
    btn.id = 'btn-create-video';
    btn.className = 'btn btn-primary';
    btn.innerHTML = '<i class="fa-solid fa-video"></i> Create News Video';
    btn.onclick = window.createNewsVideo;
    panel.appendChild(btn);
}

// --- Video News ---
window.createNewsVideo = async () => {
    const title = prompt("Enter News Headline:");
    if(!title) return;
    
    const desc = prompt("Enter News Body/Description:");
    if(!desc) return;
    
    const lang = prompt("Enter Language Code (en, hi, gu):", "en");
    if(!lang) return;
    
    showNotification("Generating Video... This may take time.");
    
    const res = await fetch(`${API_ROOT}/grahak/create_video`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ title: title, description: desc, language: lang })
    });
    
    const data = await res.json();
    if(data.status === 'success') showNotification("Video Posted Successfully!");
    else showNotification("Video Failed: " + (data.message || 'Unknown error'));
};

// --- Notifications ---
function showNotification(msg) {
    const area = document.getElementById('notification-area');
    if (!area) return;
    const note = document.createElement('div');
    note.innerText = msg;
    note.style.cssText = `
        position: fixed; bottom: 20px; right: 20px;
        background: var(--primary); color: #000;
        padding: 1rem 2rem; border-radius: 4px;
        box-shadow: 0 0 20px rgba(0,243,255,0.4);
        animation: fadeIn 0.3s; font-weight: bold;
        z-index: 9999;
    `;
    area.appendChild(note);
    setTimeout(() => note.remove(), 3000);
}

// Close modal on outside click
window.onclick = function(event) {
    const modal = document.getElementById('postModal');
    if (event.target == modal) {
        closeModal();
    }
}
