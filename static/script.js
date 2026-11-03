/**
 * PostPilot Universal Web Application - Main Client Script
 * Ultra-modern, mobile-first SaaS experience with live social mockups,
 * multi-channel automation controls, and responsive UI.
 */

// Application State
let currentTab = 'dashboard';
let statusInterval = null;
let currentModulePosts = [];
let activeChannels = ['tour', 'nz', 'gaatha', 'insta'];
let cachedStatus = {};
let searchTimeout = null;

// Channel Metadata
const CHANNEL_INFO = {
    tour: {
        name: 'Nexora Suite',
        short: 'Tour',
        pageId: '967550829768297',
        instaId: '17841449080283492',
        handle: 'nexora_suite',
        category: 'Travel & Tourism',
        icon: 'fa-earth-americas',
        color: '#38bdf8',
        bg: '#0284c7',
        platforms: ['facebook', 'instagram']
    },
    nz: {
        name: 'Phoenix International',
        short: 'Visa',
        pageId: '954901604381882',
        instaId: '17841472248438802',
        handle: 'phoenix_intl',
        category: 'Global Visa & Immigration',
        icon: 'fa-passport',
        color: '#4ade80',
        bg: '#16a34a',
        platforms: ['facebook', 'instagram']
    },
    gaatha: {
        name: 'Gaatha AI',
        short: 'Storytelling',
        pageId: '1028368893692590',
        handle: 'gaatha_ai',
        category: 'AI Cultural Narratives',
        icon: 'fa-wand-magic-sparkles',
        color: '#c084fc',
        bg: '#9333ea',
        platforms: ['facebook']
    },
    insta: {
        name: 'Instagram Dual Sync',
        short: 'IG Sync',
        handle: 'dual_sync_engine',
        category: 'Bidirectional Meta Sync',
        icon: 'fa-camera-retro',
        color: '#f472b6',
        bg: '#db2777',
        platforms: ['instagram']
    }
};

// CSRF Token Helper
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'DELETE'].includes(method)) {
        if (!options.headers['X-CSRFToken'] && CSRF_TOKEN) {
            options.headers['X-CSRFToken'] = CSRF_TOKEN;
        }
    }
    const res = await fetch(url, options);
    if (res.status === 401) {
        window.location.href = '/login';
    }
    return res;
}

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupMobileDrawer();
    setupGlobalSearch();
    loadTab('dashboard');
    startStatusPolling();
});

// Setup Navigation & Listeners
function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (!tab) return;
            document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            closeMobileDrawer();
            loadTab(tab);
        });
    });
}

// Mobile Drawer Setup
function setupMobileDrawer() {
    const menuBtn = document.getElementById('mobile-menu-btn');
    const closeBtn = document.getElementById('sidebar-close-btn');
    const backdrop = document.getElementById('mobile-backdrop');
    const sidebar = document.getElementById('sidebar');

    if (menuBtn && sidebar) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.add('open');
            if (backdrop) backdrop.classList.add('active');
        });
    }

    if (closeBtn && sidebar) {
        closeBtn.addEventListener('click', closeMobileDrawer);
    }

    if (backdrop) {
        backdrop.addEventListener('click', closeMobileDrawer);
    }
}

function closeMobileDrawer() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('mobile-backdrop');
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
}

// Global Search Setup
function setupGlobalSearch() {
    const searchInput = document.getElementById('global-search-input');
    const clearBtn = document.getElementById('search-clear-btn');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';

        if (searchTimeout) clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            if (query.length >= 2) {
                renderSearch(document.getElementById('content-area'), query);
            } else if (query.length === 0) {
                loadTab(currentTab === 'search' ? 'dashboard' : currentTab);
            }
        }, 300);
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            clearBtn.style.display = 'none';
            loadTab(currentTab === 'search' ? 'dashboard' : currentTab);
        });
    }
}

// Tab Loading Controller
function loadTab(tab) {
    currentTab = tab;
    const content = document.getElementById('content-area');
    const title = document.getElementById('page-title');

    const titles = {
        'dashboard': 'System Overview',
        'brands': 'Brand Workspaces',
        'studio': 'AI Marketing Studio',
        'campaigns': 'Campaigns Management',
        'calendar': 'Content Calendar',
        'media': 'Media Library',
        'composer': 'Post Composer',
        'approvals': 'Approvals Centre',
        'queue': 'Publishing Queue',
        'history': 'Publishing History',
        'analytics': 'Marketing & AI Analytics',
        'accounts': 'Connected Social Accounts',
        'settings': 'Organization & SaaS Settings',
        'tour': 'Nexora Suite Management',
        'nz': 'Phoenix International Management',
        'gaatha': 'Gaatha AI Automation',
        'insta': 'Instagram Synchronization',
        'search': 'Search Posts'
    };
    if (title) title.textContent = titles[tab] || 'Dashboard';

    // Highlight sidebar nav item
    document.querySelectorAll('.nav-item').forEach(b => {
        if (b.dataset.tab === tab) b.classList.add('active');
        else b.classList.remove('active');
    });

    if (tab === 'dashboard') {
        renderDashboard(content);
    } else if (tab === 'brands') {
        renderBrands(content);
    } else if (tab === 'studio') {
        renderAIStudioView(content);
    } else if (tab === 'campaigns') {
        renderCampaigns(content);
    } else if (tab === 'calendar') {
        renderCalendarView(content);
    } else if (tab === 'media') {
        renderMedia(content);
    } else if (tab === 'composer') {
        renderComposerView(content);
    } else if (tab === 'approvals') {
        renderApprovalsView(content);
    } else if (tab === 'queue') {
        renderQueueView(content);
    } else if (tab === 'history') {
        renderHistory(content);
    } else if (tab === 'analytics') {
        renderAnalytics(content);
    } else if (tab === 'accounts') {
        renderAccounts(content);
    } else if (tab === 'settings') {
        renderSettings(content);
    } else if (['tour', 'nz', 'gaatha', 'insta'].includes(tab)) {
        renderModule(content, tab);
    }
}

// Status Polling Engine
async function startStatusPolling() {
    updateStatus();
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = setInterval(updateStatus, 3000);
}

async function updateStatus() {
    try {
        const res = await authFetch('/api/status');
        if (!res.ok) return;
        const data = await res.json();
        cachedStatus = data;

        // Update Nav status pills
        activeChannels.forEach(ch => {
            const isRunning = data[`${ch}_running`];
            const pill = document.getElementById(`nav-${ch}-status`);
            if (pill) {
                pill.textContent = isRunning ? 'Running' : 'Idle';
                pill.className = `nav-badge ${isRunning ? 'running' : ''}`;
            }
        });

        // Global status pulse
        const anyRunning = activeChannels.some(ch => data[`${ch}_running`]);
        const dot = document.getElementById('system-pulsing-dot');
        const indicator = document.getElementById('global-status-indicator');
        if (dot) dot.style.backgroundColor = anyRunning ? 'var(--success)' : '#94a3b8';
        if (indicator) indicator.textContent = anyRunning ? 'Pipelines Active' : 'System Standby';

        // Update active view
        if (currentTab === 'dashboard') {
            updateDashboardMetrics(data);
        } else if (['tour', 'nz', 'gaatha', 'insta'].includes(currentTab)) {
            updateModuleStatus(currentTab, data);
        }

        // Poll pending approvals badge
        updatePendingApprovalsBadge();
    } catch (e) {
        console.warn("Status poll update skipped", e);
    }
}

// Helper: Format seconds to friendly string
function formatInterval(seconds) {
    if (!seconds || seconds <= 0) return 'Disabled';
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.round(seconds / 60);
    if (mins < 60) return `${mins}m (${seconds}s)`;
    const hours = (seconds / 3600).toFixed(1).replace('.0', '');
    return `${hours}h (${seconds}s)`;
}

// ==========================================================================
// VIEW: Dashboard
// ==========================================================================
async function renderDashboard(container) {
    container.innerHTML = `
        <!-- KPI Metrics Grid -->
        <section class="stats-grid" aria-label="Key Performance Indicators">
            <div class="stat-card">
                <div class="stat-icon bg-blue-soft">
                    <i class="fa-solid fa-bolt"></i>
                </div>
                <div class="stat-info">
                    <h4>Active Pipelines</h4>
                    <p id="kpi-active-count">0 / 4</p>
                    <small id="kpi-active-desc">Checking status...</small>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-green-soft">
                    <i class="fa-solid fa-layer-group"></i>
                </div>
                <div class="stat-info">
                    <h4>Total Queued Posts</h4>
                    <p id="kpi-total-posts">--</p>
                    <small>Across all 4 active channels</small>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-pink-soft">
                    <i class="fa-brands fa-instagram"></i>
                </div>
                <div class="stat-info">
                    <h4>Instagram Sync</h4>
                    <p id="kpi-insta-status">Checking...</p>
                    <small id="kpi-insta-interval">Interval: --</small>
                </div>
            </div>

            <div class="stat-card">
                <div class="stat-icon bg-purple-soft">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                </div>
                <div class="stat-info">
                    <h4>Loop Schedule</h4>
                    <p>Automated</p>
                    <small>Continuous periodic publishing</small>
                </div>
            </div>
        </section>

        <!-- Channel Automation Pipeline Cards -->
        <section class="card">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-sliders" style="color: var(--primary);"></i>
                        <span>Automation Pipelines</span>
                    </div>
                    <div class="card-subtitle">Manage automated posting intervals and real-time execution states</div>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn btn-sm btn-outline-danger" onclick="controlAll('stop')">
                        <i class="fa-solid fa-stop"></i> Stop All
                    </button>
                    <button class="btn btn-sm btn-primary" onclick="controlAll('start')">
                        <i class="fa-solid fa-play"></i> Run All
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="refreshDashboard()" title="Refresh Status">
                        <i class="fa-solid fa-rotate"></i>
                    </button>
                </div>
            </div>

            <div class="channel-grid">
                ${activeChannels.map(ch => {
                    const info = CHANNEL_INFO[ch];
                    return `
                        <div class="control-tile" id="tile-${ch}">
                            <div class="tile-header">
                                <div class="tile-brand-group">
                                    <div class="tile-icon-badge" style="background: ${info.bg}15; color: ${info.bg};">
                                        <i class="fa-solid ${info.icon}"></i>
                                    </div>
                                    <div>
                                        <div class="tile-title">${info.name}</div>
                                        <div class="tile-subtitle">${info.category}</div>
                                    </div>
                                </div>
                                <span class="status-badge status-stopped" id="dash-badge-${ch}">Stopped</span>
                            </div>

                            <div style="display: flex; gap: 0.35rem; margin-bottom: 0.5rem;">
                                ${info.platforms.map(p => `
                                    <span class="platform-pill ${p}">
                                        <i class="fa-brands fa-${p}"></i> ${p === 'facebook' ? 'Facebook Page' : 'Instagram'}
                                    </span>
                                `).join('')}
                            </div>

                            <div class="tile-status-bar">
                                <span id="dash-status-msg-${ch}">Idle</span>
                                <span style="font-weight: 600; color: var(--text-primary);" id="dash-interval-text-${ch}">--</span>
                            </div>

                            <div class="tile-actions">
                                <button class="btn btn-sm btn-primary" onclick="controlModule('${ch}', 'start')" title="Start Loop">
                                    <i class="fa-solid fa-play"></i> Start
                                </button>
                                <button class="btn btn-sm btn-secondary" onclick="controlModule('${ch}', 'stop')" title="Stop Loop">
                                    <i class="fa-solid fa-stop"></i> Stop
                                </button>
                                <button class="btn btn-sm btn-secondary" onclick="loadTab('${ch}')" title="Manage Posts">
                                    <i class="fa-solid fa-list-check"></i> Queue
                                </button>
                                <button class="btn btn-sm btn-outline-danger" onclick="deleteAllPosts('${ch}')" title="Delete All Posts">
                                    <i class="fa-solid fa-trash-can"></i>
                                </button>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        </section>

        <!-- Quick Post Browser -->
        <section class="card">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-table-list" style="color: var(--primary);"></i>
                        <span>Content Queue Quick Browser</span>
                    </div>
                    <div class="card-subtitle">Browse, preview, and manage queued content across channels</div>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <label for="dashboard-filter" style="font-size: 0.85rem; color: var(--text-secondary); font-weight: 500;">Filter:</label>
                    <select id="dashboard-filter" class="form-control" style="width: auto; padding: 0.4rem 0.75rem; font-size: 0.85rem;" onchange="filterDashboardPosts(this.value)">
                        <option value="">Choose Channel...</option>
                        <option value="tour">Nexora Suite (Tour)</option>
                        <option value="nz">Phoenix Intl (Visa)</option>
                        <option value="gaatha">Gaatha AI</option>
                        <option value="insta">Instagram Sync</option>
                    </select>
                </div>
            </div>

            <div id="dashboard-posts-list">
                <div class="empty-state">
                    <i class="fa-solid fa-arrow-pointer empty-state-icon"></i>
                    <div class="empty-state-title">Select a Channel Above</div>
                    <p class="empty-state-desc">Choose a channel from the filter dropdown to browse queued posts and preview their media attachments.</p>
                </div>
            </div>
        </section>
    `;

    updateStatus();
    loadDashboardTotalPosts();
}

// Count total posts across all channels
async function loadDashboardTotalPosts() {
    try {
        let total = 0;
        for (const ch of activeChannels) {
            const res = await authFetch(`/api/posts/${ch}`);
            if (res.ok) {
                const posts = await res.json();
                total += posts.length;
            }
        }
        const totalEl = document.getElementById('kpi-total-posts');
        if (totalEl) totalEl.textContent = total;
    } catch (e) {
        console.warn("Could not calculate total queued posts", e);
    }
}

function updateDashboardMetrics(data) {
    let runningCount = 0;
    activeChannels.forEach(ch => {
        const isRunning = data[`${ch}_running`];
        if (isRunning) runningCount++;

        const badge = document.getElementById(`dash-badge-${ch}`);
        if (badge) {
            badge.className = `status-badge ${isRunning ? 'status-running' : 'status-stopped'}`;
            badge.innerHTML = isRunning ? '<i class="fa-solid fa-circle-play"></i> Running' : 'Stopped';
        }

        const msg = document.getElementById(`dash-status-msg-${ch}`);
        if (msg) {
            msg.textContent = data[`${ch}_status`] || (isRunning ? 'Processing loop' : 'Idle');
        }

        const intervalEl = document.getElementById(`dash-interval-text-${ch}`);
        if (intervalEl) {
            intervalEl.textContent = `Interval: ${formatInterval(data[`${ch}_interval`])}`;
        }
    });

    const activeKpi = document.getElementById('kpi-active-count');
    if (activeKpi) activeKpi.textContent = `${runningCount} / 4`;

    const activeDesc = document.getElementById('kpi-active-desc');
    if (activeDesc) {
        activeDesc.textContent = runningCount > 0 ? `${runningCount} pipelines actively posting` : 'All automation pipelines stopped';
    }

    const instaKpi = document.getElementById('kpi-insta-status');
    if (instaKpi) {
        instaKpi.textContent = data.insta_running ? 'Active Sync' : 'Standby';
        instaKpi.style.color = data.insta_running ? 'var(--success)' : 'var(--text-primary)';
    }

    const instaIntervalEl = document.getElementById('kpi-insta-interval');
    if (instaIntervalEl) {
        instaIntervalEl.textContent = `Interval: ${formatInterval(data.insta_interval)}`;
    }
}

async function filterDashboardPosts(type) {
    const list = document.getElementById('dashboard-posts-list');
    if (!type) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-arrow-pointer empty-state-icon"></i>
                <div class="empty-state-title">Select a Channel Above</div>
                <p class="empty-state-desc">Choose a channel from the filter dropdown to browse queued posts and preview their media attachments.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = `
        <div style="text-align:center; padding: 3rem; color: var(--text-muted);">
            <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem;"></i>
            <div>Loading ${CHANNEL_INFO[type]?.name || type} posts...</div>
        </div>
    `;

    try {
        const res = await authFetch(`/api/posts/${type}`);
        const posts = await res.json();

        if (posts.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-inbox empty-state-icon"></i>
                    <div class="empty-state-title">No Posts Found for ${CHANNEL_INFO[type]?.name}</div>
                    <p class="empty-state-desc">This channel queue is currently empty. Add posts to enable automated publishing.</p>
                    <button class="btn btn-primary" onclick="openModal('add', null, '${type}')">
                        <i class="fa-solid fa-plus"></i> Create Post for this Channel
                    </button>
                </div>
            `;
            return;
        }

        list.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; padding: 0.75rem 0.5rem; margin-bottom: 0.5rem; flex-wrap: wrap; gap: 0.5rem;">
                <div style="font-weight: 600; font-size: 0.95rem;">
                    ${CHANNEL_INFO[type]?.name} Queue (${posts.length} ${posts.length === 1 ? 'post' : 'posts'})
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="btn btn-sm btn-primary" onclick="openModal('add', null, '${type}')">
                        <i class="fa-solid fa-plus"></i> Add Post
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteAllPosts('${type}')">
                        <i class="fa-solid fa-trash-can"></i> Clear All
                    </button>
                </div>
            </div>

            <!-- Desktop Table View -->
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 70px;">ID</th>
                            <th style="width: 80px;">Media</th>
                            <th>Message Caption</th>
                            <th style="width: 170px;">Last Published</th>
                            <th style="width: 120px; text-align: right;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${posts.map(post => `
                            <tr>
                                <td><span style="font-weight: 700; color: var(--text-muted); font-size: 0.85rem;">#${post.id}</span></td>
                                <td>
                                    ${post.image_filename ? 
                                        `<img src="/images/${post.image_filename}" class="post-img-preview" alt="Post thumbnail" loading="lazy">` : 
                                        `<div class="post-img-preview" style="display:flex; align-items:center; justify-content:center; color:#94a3b8;"><i class="fa-regular fa-image"></i></div>`
                                    }
                                </td>
                                <td>
                                    <div class="text-truncate" style="max-width: 400px; font-weight: 500;">
                                        ${escapeHtml(post.message) || '<em style="color:var(--text-muted)">No caption provided</em>'}
                                    </div>
                                    <small style="color: var(--text-muted); font-size: 0.75rem;">Created: ${post.created_at || 'N/A'}</small>
                                </td>
                                <td>
                                    ${post.last_posted_at ? 
                                        `<span style="font-size: 0.82rem; font-weight: 500;"><i class="fa-regular fa-clock" style="color: var(--success);"></i> ${post.last_posted_at}</span>` : 
                                        `<span style="font-size: 0.8rem; color: var(--text-muted);"><i class="fa-solid fa-hourglass-start"></i> Pending loop</span>`
                                    }
                                </td>
                                <td style="text-align: right;">
                                    <button class="btn btn-sm btn-secondary btn-icon-only" onclick="openModal('edit', ${post.id}, '${type}')" title="Edit Post">
                                        <i class="fa-solid fa-pen"></i>
                                    </button>
                                    <button class="btn btn-sm btn-outline-danger btn-icon-only" onclick="deletePost('${type}', ${post.id})" title="Delete Post">
                                        <i class="fa-solid fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>

            <!-- Mobile Cards View -->
            <div class="mobile-posts-list">
                ${posts.map(post => `
                    <div class="mobile-post-card">
                        <div class="mobile-post-header">
                            <span style="font-weight: 700; font-size: 0.85rem; color: var(--text-muted);">#${post.id}</span>
                            <span style="font-size: 0.78rem; color: var(--text-muted);">
                                ${post.last_posted_at ? 'Published: ' + post.last_posted_at : 'Pending execution'}
                            </span>
                        </div>
                        <div class="mobile-post-body">
                            ${post.image_filename ? 
                                `<img src="/images/${post.image_filename}" class="mobile-post-img" alt="Post Media" loading="lazy">` : 
                                `<div class="mobile-post-img" style="display:flex; align-items:center; justify-content:center; background:#f1f5f9; color:#94a3b8;"><i class="fa-regular fa-image"></i></div>`
                            }
                            <div class="mobile-post-content">
                                ${escapeHtml(post.message) || '<em style="color:var(--text-muted)">No caption provided</em>'}
                            </div>
                        </div>
                        <div class="mobile-post-actions">
                            <button class="btn btn-sm btn-secondary" onclick="openModal('edit', ${post.id}, '${type}')">
                                <i class="fa-solid fa-pen"></i> Edit
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="deletePost('${type}', ${post.id})">
                                <i class="fa-solid fa-trash"></i> Delete
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (e) {
        list.innerHTML = `
            <div class="empty-state" style="color: var(--danger);">
                <i class="fa-solid fa-triangle-exclamation empty-state-icon" style="color: var(--danger);"></i>
                <div class="empty-state-title">Failed to Load Content</div>
                <p class="empty-state-desc">Could not retrieve posts for ${type}. Please verify connection and retry.</p>
            </div>
        `;
    }
}

function refreshDashboard() {
    updateStatus();
    loadDashboardTotalPosts();
    const filter = document.getElementById('dashboard-filter');
    if (filter && filter.value) {
        filterDashboardPosts(filter.value);
    }
    showToast('Dashboard status refreshed', 'info');
}

// ==========================================================================
// VIEW: Connected Social Accounts
// ==========================================================================
function renderAccounts(container) {
    container.innerHTML = `
        <div class="card" style="margin-bottom: 1.5rem; background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); color: #ffffff; border: none;">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <h2 style="font-size: 1.35rem; font-weight: 700; margin-bottom: 0.35rem;">Meta Social Ecosystem Assets</h2>
                    <p style="color: #94a3b8; font-size: 0.9rem;">Verified Facebook Pages and linked Instagram accounts currently configured in PostPilot</p>
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <span class="platform-pill meta" style="background: rgba(255,255,255,0.12); color: #ffffff; border-color: rgba(255,255,255,0.2);">
                        <i class="fa-brands fa-meta"></i> Graph API v19.0
                    </span>
                    <span class="platform-pill" style="background: rgba(16,185,129,0.2); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.3);">
                        <i class="fa-solid fa-shield-halved"></i> Secrets Protected
                    </span>
                </div>
            </div>
        </div>

        <div class="accounts-grid">
            <!-- Account 1: Nexora Suite -->
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-identity">
                        <div class="account-avatar" style="background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%);">
                            <i class="fa-solid fa-earth-americas"></i>
                        </div>
                        <div class="account-meta">
                            <h3>Nexora Suite</h3>
                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem;">
                                <span class="platform-pill facebook"><i class="fa-brands fa-facebook"></i> Facebook Page</span>
                                <span class="platform-pill instagram"><i class="fa-brands fa-instagram"></i> Instagram</span>
                            </div>
                        </div>
                    </div>
                    <span class="status-badge status-running"><i class="fa-solid fa-check"></i> Linked</span>
                </div>

                <div class="account-details-list">
                    <div class="account-detail-item">
                        <span class="account-detail-label">Facebook Page ID</span>
                        <code class="account-detail-value">967550829768297</code>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Instagram Profile</span>
                        <code class="account-detail-value">@nexora_suite</code>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Focus / Niche</span>
                        <span class="account-detail-value">Tour & Destination Packages</span>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Automation Pipeline</span>
                        <span class="account-detail-value">Channel <code>tour</code></span>
                    </div>
                </div>

                <div style="display: flex; gap: 0.5rem; margin-top: 1.25rem;">
                    <button class="btn btn-sm btn-primary" onclick="loadTab('tour')" style="flex: 1;">
                        <i class="fa-solid fa-list-check"></i> View Post Queue
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="openModal('add', null, 'tour')" title="Compose for Nexora Suite">
                        <i class="fa-solid fa-pen"></i> Compose
                    </button>
                </div>
            </div>

            <!-- Account 2: Phoenix International -->
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-identity">
                        <div class="account-avatar" style="background: linear-gradient(135deg, #16a34a 0%, #4ade80 100%);">
                            <i class="fa-solid fa-passport"></i>
                        </div>
                        <div class="account-meta">
                            <h3>Phoenix International</h3>
                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem;">
                                <span class="platform-pill facebook"><i class="fa-brands fa-facebook"></i> Facebook Page</span>
                                <span class="platform-pill instagram"><i class="fa-brands fa-instagram"></i> Instagram</span>
                            </div>
                        </div>
                    </div>
                    <span class="status-badge status-running"><i class="fa-solid fa-check"></i> Linked</span>
                </div>

                <div class="account-details-list">
                    <div class="account-detail-item">
                        <span class="account-detail-label">Facebook Page ID</span>
                        <code class="account-detail-value">954901604381882</code>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Instagram Profile</span>
                        <code class="account-detail-value">@phoenix_intl</code>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Focus / Niche</span>
                        <span class="account-detail-value">Immigration & Visa Consulting</span>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Automation Pipeline</span>
                        <span class="account-detail-value">Channel <code>nz</code></span>
                    </div>
                </div>

                <div style="display: flex; gap: 0.5rem; margin-top: 1.25rem;">
                    <button class="btn btn-sm btn-primary" onclick="loadTab('nz')" style="flex: 1;">
                        <i class="fa-solid fa-list-check"></i> View Post Queue
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="openModal('add', null, 'nz')" title="Compose for Phoenix">
                        <i class="fa-solid fa-pen"></i> Compose
                    </button>
                </div>
            </div>

            <!-- Account 3: Gaatha AI -->
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-identity">
                        <div class="account-avatar" style="background: linear-gradient(135deg, #9333ea 0%, #c084fc 100%);">
                            <i class="fa-solid fa-wand-magic-sparkles"></i>
                        </div>
                        <div class="account-meta">
                            <h3>Gaatha AI</h3>
                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem;">
                                <span class="platform-pill facebook"><i class="fa-brands fa-facebook"></i> Facebook Page</span>
                            </div>
                        </div>
                    </div>
                    <span class="status-badge status-running"><i class="fa-solid fa-check"></i> Linked</span>
                </div>

                <div class="account-details-list">
                    <div class="account-detail-item">
                        <span class="account-detail-label">Facebook Page ID</span>
                        <code class="account-detail-value">1028368893692590</code>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Focus / Niche</span>
                        <span class="account-detail-value">AI Narratives & Cultural Heritage</span>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Automation Pipeline</span>
                        <span class="account-detail-value">Channel <code>gaatha</code></span>
                    </div>
                </div>

                <div style="display: flex; gap: 0.5rem; margin-top: 1.25rem;">
                    <button class="btn btn-sm btn-primary" onclick="loadTab('gaatha')" style="flex: 1;">
                        <i class="fa-solid fa-list-check"></i> View Post Queue
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="openModal('add', null, 'gaatha')" title="Compose for Gaatha AI">
                        <i class="fa-solid fa-pen"></i> Compose
                    </button>
                </div>
            </div>

            <!-- Account 4: Instagram Dual Sync -->
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-identity">
                        <div class="account-avatar" style="background: var(--ig-gradient);">
                            <i class="fa-brands fa-instagram"></i>
                        </div>
                        <div class="account-meta">
                            <h3>Instagram Sync Hub</h3>
                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem;">
                                <span class="platform-pill instagram"><i class="fa-brands fa-instagram"></i> Graph API Sync</span>
                            </div>
                        </div>
                    </div>
                    <span class="status-badge status-running"><i class="fa-solid fa-sync"></i> Synchronized</span>
                </div>

                <div class="account-details-list">
                    <div class="account-detail-item">
                        <span class="account-detail-label">Accounts Synced</span>
                        <span class="account-detail-value">@nexora_suite &amp; @phoenix_intl</span>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Sync Mechanism</span>
                        <span class="account-detail-value">Bidirectional Graph API Sync</span>
                    </div>
                    <div class="account-detail-item">
                        <span class="account-detail-label">Automation Pipeline</span>
                        <span class="account-detail-value">Channel <code>insta</code></span>
                    </div>
                </div>

                <div style="display: flex; gap: 0.5rem; margin-top: 1.25rem;">
                    <button class="btn btn-sm btn-primary" onclick="loadTab('insta')" style="flex: 1;">
                        <i class="fa-solid fa-list-check"></i> View Sync Queue
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="openModal('add', null, 'insta')" title="Compose for Instagram">
                        <i class="fa-solid fa-pen"></i> Compose
                    </button>
                </div>
            </div>
        </div>

        <div class="card" style="border-left: 4px solid var(--primary); background: #f8fafc;">
            <div style="display: flex; gap: 0.85rem; align-items: flex-start;">
                <i class="fa-solid fa-shield-halved" style="color: var(--primary); font-size: 1.4rem; margin-top: 0.2rem;"></i>
                <div>
                    <h4 style="font-weight: 700; font-size: 0.95rem; margin-bottom: 0.2rem;">Security &amp; Token Architecture</h4>
                    <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45;">
                        Meta access tokens and OAuth secrets are safely isolated in server/Termux environment variables (<code style="background: #e2e8f0; padding: 0.1rem 0.3rem; border-radius: 4px;">.env</code>). They are never exposed to browser memory or client-side JavaScript.
                    </p>
                </div>
            </div>
        </div>
    `;
}

// ==========================================================================
// VIEW: Post Composer (Full Screen Mode)
// ==========================================================================
function renderComposerView(container) {
    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-feather-pointed" style="color: var(--primary);"></i>
                        <span>Social Post Studio</span>
                    </div>
                    <div class="card-subtitle">Draft, schedule, and submit rich social content with instant live mockup validation</div>
                </div>
            </div>

            <div class="composer-grid">
                <!-- Editor Column -->
                <div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                        <div class="form-group">
                            <label for="view-composer-type" class="form-label">Destination Channel</label>
                            <select id="view-composer-type" class="form-control" onchange="handleComposerChannelChange(this.value)">
                                <option value="tour">Nexora Suite (Tour & Travel · Facebook & IG)</option>
                                <option value="nz">Phoenix Intl (Visa & Migration · Facebook & IG)</option>
                                <option value="gaatha">Gaatha AI (Cultural & AI Storytelling · Facebook)</option>
                                <option value="insta">Instagram Sync (Dual Sync Engine)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="view-composer-brand" class="form-label">Brand Workspace</label>
                            <select id="view-composer-brand" class="form-control">
                                <option value="">Default (Core Brand)</option>
                            </select>
                        </div>
                    </div>

                    <div class="form-group">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                            <label for="view-composer-caption" class="form-label" style="margin-bottom: 0;">Caption / Copy</label>
                            <span id="view-char-counter" style="font-size: 0.78rem; color: var(--text-muted);">0 / 2200 characters</span>
                        </div>
                        <textarea 
                            id="view-composer-caption" 
                            rows="4" 
                            class="form-control" 
                            placeholder="Write your post caption..."
                            oninput="handleCaptionInput(this.value)"
                        ></textarea>

                        <div class="hashtag-chips-row">
                            <span class="hashtag-chip" onclick="insertTag('#PostPilot')">#PostPilot</span>
                            <span class="hashtag-chip" onclick="insertTag('#Nexora')">#Nexora</span>
                            <span class="hashtag-chip" onclick="insertTag('#Travel')">#Travel</span>
                            <span class="hashtag-chip" onclick="insertTag('#PhoenixIntl')">#PhoenixIntl</span>
                            <span class="hashtag-chip" onclick="insertTag('#Visa')">#Visa</span>
                            <span class="hashtag-chip" onclick="insertTag('#GaathaAI')">#GaathaAI</span>
                            <span class="hashtag-chip" onclick="insertTag('#Automation')">#Automation</span>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Media Attachment</label>
                        <div class="file-upload-wrapper">
                            <input type="file" id="view-composer-file" accept="image/*,video/*" onchange="handleFileSelect(this)">
                            <div class="file-upload-icon"><i class="fa-solid fa-cloud-arrow-up"></i></div>
                            <div class="file-upload-text" id="view-file-name">Drag & drop image or browse files</div>
                            <div class="file-upload-hint">Supports PNG, JPG, WEBP, MP4 (Max 16 MB)</div>
                        </div>

                        <div id="view-file-preview-card" class="file-preview-card">
                            <img id="view-preview-thumb-img" class="file-preview-thumb" src="" alt="Selected Media">
                            <div style="flex: 1; min-width: 0;">
                                <div id="view-selected-file-label" style="font-weight: 600; font-size: 0.85rem;" class="text-truncate">filename.png</div>
                                <div style="font-size: 0.75rem; color: var(--success);"><i class="fa-solid fa-check"></i> Media ready</div>
                            </div>
                            <button type="button" class="btn btn-sm btn-secondary" onclick="clearSelectedMedia()" title="Remove">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                        </div>
                    </div>

                    <!-- Scheduling Section -->
                    <div style="background: var(--bg-app); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 1rem; margin-top: 1rem;">
                        <div style="font-weight: 700; font-size: 0.88rem; margin-bottom: 0.65rem; display: flex; align-items: center; gap: 0.4rem;">
                            <i class="fa-solid fa-clock" style="color: var(--primary);"></i>
                            <span>Schedule &amp; Timezone Context</span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="view-composer-datetime" class="form-label" style="font-size: 0.8rem;">Date &amp; Time (Local)</label>
                                <input type="datetime-local" id="view-composer-datetime" class="form-control" style="font-size: 0.85rem;">
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="view-composer-timezone" class="form-label" style="font-size: 0.8rem;">Timezone</label>
                                <select id="view-composer-timezone" class="form-control" style="font-size: 0.85rem;">
                                    <option value="UTC">UTC</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    <!-- Action Buttons -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.65rem; margin-top: 1.25rem;">
                        <button type="button" class="btn btn-primary btn-lg" onclick="handleComposerSubmit('scheduled')" style="grid-column: span 2;">
                            <i class="fa-solid fa-calendar-check"></i> Schedule Post
                        </button>
                        <button type="button" class="btn btn-secondary" onclick="handleComposerSubmit('draft')">
                            <i class="fa-solid fa-file-pen"></i> Save as Draft
                        </button>
                        <button type="button" class="btn btn-secondary" onclick="handleComposerSubmit('pending_approval')">
                            <i class="fa-solid fa-paper-plane"></i> Submit for Approval
                        </button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="saveViewComposerPost()" style="grid-column: span 2; font-size: 0.82rem; margin-top: 0.25rem;">
                            <i class="fa-solid fa-bolt"></i> Direct Loop Queue (Continuous Periodic Posting)
                        </button>
                    </div>
                </div>

                <!-- Live Social Media Preview Column -->
                <div>
                    <div class="composer-preview-header">
                        <div style="font-weight: 700; font-size: 0.95rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-eye" style="color: var(--primary);"></i>
                            <span>Live Social Feed Mockup</span>
                        </div>
                        <div class="preview-toggle-group">
                            <button type="button" id="v-tab-btn-fb" class="preview-tab-btn active" onclick="switchPreviewPlatform('fb')">
                                <i class="fa-brands fa-facebook" style="color: var(--fb-blue);"></i> Facebook
                            </button>
                            <button type="button" id="v-tab-btn-ig" class="preview-tab-btn" onclick="switchPreviewPlatform('ig')">
                                <i class="fa-brands fa-instagram" style="color: var(--ig-pink);"></i> Instagram
                            </button>
                        </div>
                    </div>

                    <!-- Facebook Mockup -->
                    <div id="v-mockup-container-fb" class="fb-post-mockup">
                        <div class="fb-mockup-header">
                            <div class="fb-mockup-avatar" id="v-fb-preview-avatar">N</div>
                            <div>
                                <div class="fb-mockup-page-name">
                                    <span id="v-fb-preview-name">Nexora Suite</span>
                                    <i class="fa-solid fa-circle-check"></i>
                                </div>
                                <div class="fb-mockup-time">Just now &middot; <i class="fa-solid fa-earth-americas"></i></div>
                            </div>
                        </div>
                        <div class="fb-mockup-caption" id="v-fb-preview-caption">Your caption will appear here in real-time...</div>
                        <div class="fb-mockup-media-container" id="v-fb-preview-media">
                            <div class="fb-mockup-media-placeholder">
                                <i class="fa-regular fa-image"></i>
                                <div>Attach an image to preview layout</div>
                            </div>
                        </div>
                        <div class="fb-mockup-footer">
                            <div class="fb-footer-action"><i class="fa-regular fa-thumbs-up"></i> Like</div>
                            <div class="fb-footer-action"><i class="fa-regular fa-comment"></i> Comment</div>
                            <div class="fb-footer-action"><i class="fa-solid fa-share"></i> Share</div>
                        </div>
                    </div>

                    <!-- Instagram Mockup -->
                    <div id="v-mockup-container-ig" class="ig-post-mockup" style="display: none;">
                        <div class="ig-mockup-header">
                            <div class="ig-avatar-ring">
                                <div class="ig-avatar-inner" id="v-ig-preview-avatar">N</div>
                            </div>
                            <div>
                                <div class="ig-mockup-user" id="v-ig-preview-username">nexora_suite</div>
                                <div class="ig-mockup-location">Global &middot; Meta Business</div>
                            </div>
                        </div>
                        <div class="ig-mockup-media-container" id="v-ig-preview-media">
                            <div class="fb-mockup-media-placeholder">
                                <i class="fa-brands fa-instagram"></i>
                                <div>Attach an image to preview 1:1 Instagram frame</div>
                            </div>
                        </div>
                        <div class="ig-mockup-actions">
                            <div class="ig-action-left">
                                <i class="fa-regular fa-heart"></i>
                                <i class="fa-regular fa-comment"></i>
                                <i class="fa-regular fa-paper-plane"></i>
                            </div>
                            <i class="fa-regular fa-bookmark"></i>
                        </div>
                        <div class="ig-mockup-caption-wrap">
                            <span class="ig-mockup-username-prefix" id="v-ig-preview-prefix">nexora_suite</span>
                            <span id="v-ig-preview-caption">Your caption will appear here...</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    handleComposerChannelChange('tour');
    initComposerView();
}

// ==========================================================================
// VIEW: Channel Automation / Queue Management
// ==========================================================================
async function renderModule(container, type) {
    const info = CHANNEL_INFO[type] || { name: type, category: 'Channel', icon: 'fa-paper-plane', platforms: [] };

    container.innerHTML = `
        <!-- Hero Header -->
        <div class="card" style="margin-bottom: 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div class="account-avatar" style="background: ${info.bg || 'var(--primary)'};">
                        <i class="fa-solid ${info.icon}"></i>
                    </div>
                    <div>
                        <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0;">${info.name}</h2>
                            <span id="module-status-badge" class="status-badge status-stopped">Stopped</span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.2rem;">
                            ${info.category} &middot; <span id="module-status-text">Status: Idle</span>
                        </div>
                    </div>
                </div>

                <!-- Interval & State Controls -->
                <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 0.4rem; background: var(--bg-app); padding: 0.35rem 0.65rem; border-radius: var(--radius-md); border: 1px solid var(--border);">
                        <label for="interval-preset" style="font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0;">Schedule:</label>
                        <select id="interval-preset" class="form-control" style="width: auto; padding: 0.25rem 0.5rem; font-size: 0.82rem;" onchange="handleIntervalPresetChange('${type}', this.value)">
                            <option value="900">15 Minutes (900s)</option>
                            <option value="1800">30 Minutes (1800s)</option>
                            <option value="3600">1 Hour (3600s)</option>
                            <option value="7200">2 Hours (7200s)</option>
                            <option value="21600">6 Hours (21600s)</option>
                            <option value="custom">Custom Seconds...</option>
                        </select>
                        <input type="number" id="interval-input" class="form-control" style="width: 80px; padding: 0.25rem 0.4rem; font-size: 0.82rem; display: none;" value="1800" min="10">
                        <button class="btn btn-sm btn-secondary" id="interval-save-btn" onclick="saveInterval('${type}')" style="display: none; padding: 0.25rem 0.5rem;">Save</button>
                    </div>

                    <button id="module-toggle-btn" class="btn btn-primary btn-sm" onclick="toggleModule('${type}')">
                        <i class="fa-solid fa-play"></i> Start Automation
                    </button>
                </div>
            </div>
        </div>

        <!-- Post Queue Card -->
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-list-check" style="color: var(--primary);"></i>
                        <span>Content Publishing Queue</span>
                    </div>
                    <div class="card-subtitle">Posts will be published sequentially according to the configured interval</div>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn btn-primary btn-sm" onclick="openModal('add', null, '${type}')">
                        <i class="fa-solid fa-plus"></i> Add Post
                    </button>
                    <button class="btn btn-outline-danger btn-sm" onclick="deleteAllPosts('${type}')">
                        <i class="fa-solid fa-trash-can"></i> Clear All
                    </button>
                </div>
            </div>

            <!-- Desktop Queue Table -->
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 70px;">ID</th>
                            <th style="width: 80px;">Media</th>
                            <th>Message / Caption</th>
                            <th style="width: 170px;">Last Published</th>
                            <th style="width: 120px; text-align: right;">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="posts-table-body">
                        <tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--text-muted);"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading posts...</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Mobile Queue Cards -->
            <div id="posts-mobile-body" class="mobile-posts-list">
                <!-- Dynamically populated -->
            </div>
        </div>
    `;

    loadPosts(type);
    loadInterval(type);
    updateStatus();
}

async function loadPosts(type) {
    try {
        const res = await authFetch(`/api/posts/${type}`);
        const posts = await res.json();
        currentModulePosts = posts;
        const tbody = document.getElementById('posts-table-body');
        const mbody = document.getElementById('posts-mobile-body');

        if (!tbody) return;

        if (posts.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align:center; padding: 3rem 1.5rem; color: var(--text-muted);">
                        <i class="fa-solid fa-inbox" style="font-size: 2rem; color: #cbd5e1; margin-bottom: 0.5rem; display: block;"></i>
                        <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">No Posts in Queue</div>
                        <p style="font-size: 0.85rem; margin-bottom: 1rem;">This channel has no queued content. Add your first post to start publishing.</p>
                        <button class="btn btn-sm btn-primary" onclick="openModal('add', null, '${type}')">
                            <i class="fa-solid fa-plus"></i> Add Post Now
                        </button>
                    </td>
                </tr>
            `;
            if (mbody) {
                mbody.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-inbox empty-state-icon"></i>
                        <div class="empty-state-title">No Posts in Queue</div>
                        <p class="empty-state-desc">Add your first post to start publishing.</p>
                        <button class="btn btn-sm btn-primary" onclick="openModal('add', null, '${type}')">
                            <i class="fa-solid fa-plus"></i> Add Post Now
                        </button>
                    </div>
                `;
            }
            return;
        }

        tbody.innerHTML = posts.map(post => `
            <tr>
                <td><span style="font-weight: 700; color: var(--text-muted); font-size: 0.85rem;">#${post.id}</span></td>
                <td>
                    ${post.image_filename ? 
                        `<img src="/images/${post.image_filename}" class="post-img-preview" alt="Post thumbnail" loading="lazy">` : 
                        `<div class="post-img-preview" style="display:flex; align-items:center; justify-content:center; color:#94a3b8;"><i class="fa-regular fa-image"></i></div>`
                    }
                </td>
                <td>
                    <div class="text-truncate" style="max-width: 420px; font-weight: 500;">
                        ${escapeHtml(post.message) || '<em style="color:var(--text-muted)">No caption</em>'}
                    </div>
                    <small style="color: var(--text-muted); font-size: 0.75rem;">Created: ${post.created_at || 'N/A'}</small>
                </td>
                <td>
                    ${post.last_posted_at ? 
                        `<span style="font-size: 0.82rem; font-weight: 500;"><i class="fa-regular fa-clock" style="color: var(--success);"></i> ${post.last_posted_at}</span>` : 
                        `<span style="font-size: 0.8rem; color: var(--text-muted);"><i class="fa-solid fa-hourglass-start"></i> Pending loop</span>`
                    }
                </td>
                <td style="text-align: right;">
                    <button class="btn btn-sm btn-secondary btn-icon-only" onclick="openModal('edit', ${post.id}, '${type}')" title="Edit Post">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-icon-only" onclick="deletePost('${type}', ${post.id})" title="Delete Post">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        if (mbody) {
            mbody.innerHTML = posts.map(post => `
                <div class="mobile-post-card">
                    <div class="mobile-post-header">
                        <span style="font-weight: 700; font-size: 0.85rem; color: var(--text-muted);">#${post.id}</span>
                        <span style="font-size: 0.78rem; color: var(--text-muted);">
                            ${post.last_posted_at ? 'Published: ' + post.last_posted_at : 'Pending execution'}
                        </span>
                    </div>
                    <div class="mobile-post-body">
                        ${post.image_filename ? 
                            `<img src="/images/${post.image_filename}" class="mobile-post-img" alt="Post Media" loading="lazy">` : 
                            `<div class="mobile-post-img" style="display:flex; align-items:center; justify-content:center; background:#f1f5f9; color:#94a3b8;"><i class="fa-regular fa-image"></i></div>`
                        }
                        <div class="mobile-post-content">
                            ${escapeHtml(post.message) || '<em style="color:var(--text-muted)">No caption provided</em>'}
                        </div>
                    </div>
                    <div class="mobile-post-actions">
                        <button class="btn btn-sm btn-secondary" onclick="openModal('edit', ${post.id}, '${type}')">
                            <i class="fa-solid fa-pen"></i> Edit
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deletePost('${type}', ${post.id})">
                            <i class="fa-solid fa-trash"></i> Delete
                        </button>
                    </div>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error("Load posts failed", e);
    }
}

// Interval Management
async function loadInterval(type) {
    try {
        const res = await authFetch(`/api/interval/${type}`);
        const data = await res.json();
        const input = document.getElementById('interval-input');
        const preset = document.getElementById('interval-preset');
        if (input && data.interval) {
            input.value = data.interval;
            if (preset) {
                const standardValues = ['900', '1800', '3600', '7200', '21600'];
                if (standardValues.includes(String(data.interval))) {
                    preset.value = String(data.interval);
                } else {
                    preset.value = 'custom';
                    input.style.display = 'inline-block';
                    const saveBtn = document.getElementById('interval-save-btn');
                    if (saveBtn) saveBtn.style.display = 'inline-flex';
                }
            }
        }
    } catch (e) {
        console.warn("Could not load interval", e);
    }
}

function handleIntervalPresetChange(type, value) {
    const input = document.getElementById('interval-input');
    const saveBtn = document.getElementById('interval-save-btn');
    if (value === 'custom') {
        if (input) input.style.display = 'inline-block';
        if (saveBtn) saveBtn.style.display = 'inline-flex';
    } else {
        if (input) {
            input.value = value;
            input.style.display = 'none';
        }
        if (saveBtn) saveBtn.style.display = 'none';
        saveInterval(type, parseInt(value));
    }
}

async function saveInterval(type, customVal = null) {
    const inputVal = customVal !== null ? customVal : parseInt(document.getElementById('interval-input').value);
    if (!inputVal || inputVal <= 0) {
        showToast('Please specify a positive interval in seconds', 'error');
        return;
    }

    try {
        const res = await authFetch(`/api/interval/${type}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval: inputVal })
        });
        if (res.ok) {
            showToast(`Loop schedule updated to ${formatInterval(inputVal)}`, 'success');
            updateStatus();
        } else {
            showToast('Failed to update interval', 'error');
        }
    } catch (e) {
        showToast('Network error saving interval', 'error');
    }
}

// Module Automation Control
async function controlModule(type, action) {
    try {
        const res = await authFetch(`/api/control/${type}/${action}`, { method: 'POST' });
        if (res.ok) {
            showToast(`${CHANNEL_INFO[type]?.name || type} posting ${action === 'start' ? 'started' : 'stopped'}`, 'success');
            updateStatus();
        } else {
            showToast(`Action failed for ${type}`, 'error');
        }
    } catch (e) {
        showToast('Error communicating with server', 'error');
    }
}

async function toggleModule(type) {
    const isRunning = cachedStatus[`${type}_running`];
    controlModule(type, isRunning ? 'stop' : 'start');
}

async function controlAll(action) {
    try {
        const res = await authFetch(`/api/control/all/${action}`, { method: 'POST' });
        if (res.ok) {
            showToast(`All automation channels ${action === 'start' ? 'started' : 'stopped'}`, 'success');
            updateStatus();
        }
    } catch (e) {
        showToast('Error sending global command', 'error');
    }
}

function updateModuleStatus(type, data) {
    const badge = document.getElementById('module-status-badge');
    const text = document.getElementById('module-status-text');
    const toggleBtn = document.getElementById('module-toggle-btn');

    if (!badge) return;

    const isRunning = data[`${type}_running`];
    const statusMsg = data[`${type}_status`] || '';

    if (isRunning) {
        badge.className = 'status-badge status-running';
        badge.innerHTML = '<i class="fa-solid fa-circle-play"></i> Running';
    } else {
        badge.className = 'status-badge status-stopped';
        badge.innerHTML = 'Stopped';
    }

    if (text) {
        text.textContent = statusMsg ? `Status: ${statusMsg}` : (isRunning ? 'Loop active' : 'Idle');
    }

    if (toggleBtn) {
        if (isRunning) {
            toggleBtn.className = 'btn btn-danger btn-sm';
            toggleBtn.innerHTML = '<i class="fa-solid fa-stop"></i> Stop Automation';
        } else {
            toggleBtn.className = 'btn btn-primary btn-sm';
            toggleBtn.innerHTML = '<i class="fa-solid fa-play"></i> Start Automation';
        }
    }
}

// ==========================================================================
// VIEW: Global Post Search
// ==========================================================================
async function renderSearch(container, query) {
    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-magnifying-glass" style="color: var(--primary);"></i>
                        <span>Search Results for "${escapeHtml(query)}"</span>
                    </div>
                    <div class="card-subtitle">Searching across all channel queues</div>
                </div>
            </div>
            <div id="search-results-list" style="padding: 1rem 0;">
                <div style="text-align:center; padding: 2rem; color: var(--text-muted);">
                    <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 1.5rem;"></i>
                    <div style="margin-top: 0.5rem;">Searching posts...</div>
                </div>
            </div>
        </div>
    `;

    try {
        const res = await authFetch(`/api/search?q=${encodeURIComponent(query)}`);
        const results = await res.json();
        const listEl = document.getElementById('search-results-list');

        if (!listEl) return;

        if (results.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-filter-circle-xmark empty-state-icon"></i>
                    <div class="empty-state-title">No Matching Posts Found</div>
                    <p class="empty-state-desc">Try another keyword or search phrase.</p>
                </div>
            `;
            return;
        }

        listEl.innerHTML = `
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 70px;">ID</th>
                            <th style="width: 140px;">Channel</th>
                            <th style="width: 80px;">Media</th>
                            <th>Matched Caption</th>
                            <th style="width: 120px; text-align: right;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.map(post => {
                            const pType = post.post_type || 'tour';
                            const info = CHANNEL_INFO[pType] || { name: pType };
                            return `
                                <tr>
                                    <td><span style="font-weight: 700; color: var(--text-muted); font-size: 0.85rem;">#${post.id}</span></td>
                                    <td>
                                        <span class="platform-pill ${pType === 'insta' ? 'instagram' : 'facebook'}">
                                            ${info.name}
                                        </span>
                                    </td>
                                    <td>
                                        ${post.image_filename ? 
                                            `<img src="/images/${post.image_filename}" class="post-img-preview" alt="thumbnail">` : 
                                            `<div class="post-img-preview" style="display:flex; align-items:center; justify-content:center; color:#94a3b8;"><i class="fa-regular fa-image"></i></div>`
                                        }
                                    </td>
                                    <td>
                                        <div style="font-weight: 500; font-size: 0.9rem;">${highlightMatch(escapeHtml(post.message), query)}</div>
                                        <small style="color: var(--text-muted); font-size: 0.75rem;">Created: ${post.created_at || 'N/A'}</small>
                                    </td>
                                    <td style="text-align: right;">
                                        <button class="btn btn-sm btn-secondary btn-icon-only" onclick="openModal('edit', ${post.id}, '${pType}')" title="Edit Post">
                                            <i class="fa-solid fa-pen"></i>
                                        </button>
                                        <button class="btn btn-sm btn-outline-danger btn-icon-only" onclick="deletePost('${pType}', ${post.id})" title="Delete Post">
                                            <i class="fa-solid fa-trash"></i>
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (e) {
        console.error("Search failed", e);
    }
}

// ==========================================================================
// Post Modal & Live Preview Engine
// ==========================================================================
function openModal(mode, postId, type) {
    const modal = document.getElementById('post-modal');
    const modalTitle = document.getElementById('modal-title');
    const typeSelect = document.getElementById('post-type');
    const idInput = document.getElementById('post-id');
    const msgInput = document.getElementById('post-message');
    const curImgInput = document.getElementById('current-image-filename');
    const fileLabel = document.getElementById('file-name');
    const fileInput = document.getElementById('post-file');
    const previewCard = document.getElementById('file-preview-card');
    const previewThumb = document.getElementById('preview-thumb-img');

    if (!modal) return;

    modal.classList.add('show');
    modalTitle.textContent = mode === 'edit' ? 'Edit Social Post' : 'Create New Post';
    typeSelect.value = type || 'tour';

    if (mode === 'edit' && postId) {
        const post = currentModulePosts.find(p => p.id === postId);
        if (post) {
            idInput.value = post.id;
            msgInput.value = post.message || '';
            curImgInput.value = post.image_filename || '';
            fileLabel.textContent = post.image_filename ? `Current: ${post.image_filename}` : 'Choose new file or drag here';
            
            if (post.image_filename) {
                previewThumb.src = `/images/${post.image_filename}`;
                document.getElementById('selected-file-label').textContent = post.image_filename;
                previewCard.style.display = 'flex';
                updateMockupMedia(`/images/${post.image_filename}`);
            } else {
                previewCard.style.display = 'none';
                clearMockupMedia();
            }
            handleCaptionInput(post.message || '');
        }
    } else {
        idInput.value = '';
        msgInput.value = '';
        curImgInput.value = '';
        fileInput.value = '';
        fileLabel.textContent = 'Drag & drop image/video or browse files';
        previewCard.style.display = 'none';
        clearMockupMedia();
        handleCaptionInput('');
    }

    handleComposerChannelChange(typeSelect.value);
}

function closeModal() {
    const modal = document.getElementById('post-modal');
    if (modal) modal.classList.remove('show');
}

// Live Mockup Interaction Handlers
function handleCaptionInput(text) {
    const len = text.length;
    
    // Update char counter
    const counterModal = document.getElementById('char-counter');
    if (counterModal) counterModal.textContent = `${len} / 2200 characters`;
    const counterView = document.getElementById('view-char-counter');
    if (counterView) counterView.textContent = `${len} / 2200 characters`;

    const displayText = text.trim() ? escapeHtml(text) : 'Your caption will appear here in real-time...';

    // Update modal mockup captions
    const fbCapModal = document.getElementById('fb-preview-caption');
    if (fbCapModal) fbCapModal.innerHTML = displayText;
    const igCapModal = document.getElementById('ig-preview-caption');
    if (igCapModal) igCapModal.innerHTML = displayText;

    // Update view mockup captions
    const fbCapView = document.getElementById('v-fb-preview-caption');
    if (fbCapView) fbCapView.innerHTML = displayText;
    const igCapView = document.getElementById('v-ig-preview-caption');
    if (igCapView) igCapView.innerHTML = displayText;
}

function insertTag(tag) {
    const inputModal = document.getElementById('post-message');
    const inputView = document.getElementById('view-composer-caption');
    const target = inputModal && inputModal.offsetParent !== null ? inputModal : inputView;
    if (!target) return;

    const cur = target.value;
    target.value = cur ? `${cur} ${tag}` : tag;
    target.focus();
    handleCaptionInput(target.value);
}

function handleComposerChannelChange(channel) {
    const info = CHANNEL_INFO[channel] || CHANNEL_INFO.tour;

    // Update Modal mockups
    const fbName = document.getElementById('fb-preview-name');
    const fbAvatar = document.getElementById('fb-preview-avatar');
    const igUser = document.getElementById('ig-preview-username');
    const igPrefix = document.getElementById('ig-preview-prefix');
    const igAvatar = document.getElementById('ig-preview-avatar');

    if (fbName) fbName.textContent = info.name;
    if (fbAvatar) fbAvatar.textContent = info.name[0];
    if (igUser) igUser.textContent = info.handle;
    if (igPrefix) igPrefix.textContent = info.handle;
    if (igAvatar) igAvatar.textContent = info.name[0];

    // Update View mockups
    const vFbName = document.getElementById('v-fb-preview-name');
    const vFbAvatar = document.getElementById('v-fb-preview-avatar');
    const vIgUser = document.getElementById('v-ig-preview-username');
    const vIgPrefix = document.getElementById('v-ig-preview-prefix');
    const vIgAvatar = document.getElementById('v-ig-preview-avatar');

    if (vFbName) vFbName.textContent = info.name;
    if (vFbAvatar) vFbAvatar.textContent = info.name[0];
    if (vIgUser) vIgUser.textContent = info.handle;
    if (vIgPrefix) vIgPrefix.textContent = info.handle;
    if (vIgAvatar) vIgAvatar.textContent = info.name[0];
}

function switchPreviewPlatform(platform) {
    const fbBtnModal = document.getElementById('tab-btn-fb');
    const igBtnModal = document.getElementById('tab-btn-ig');
    const fbBoxModal = document.getElementById('mockup-container-fb');
    const igBoxModal = document.getElementById('mockup-container-ig');

    const fbBtnView = document.getElementById('v-tab-btn-fb');
    const igBtnView = document.getElementById('v-tab-btn-ig');
    const fbBoxView = document.getElementById('v-mockup-container-fb');
    const igBoxView = document.getElementById('v-mockup-container-ig');

    if (platform === 'fb') {
        if (fbBtnModal) fbBtnModal.classList.add('active');
        if (igBtnModal) igBtnModal.classList.remove('active');
        if (fbBoxModal) fbBoxModal.style.display = 'block';
        if (igBoxModal) igBoxModal.style.display = 'none';

        if (fbBtnView) fbBtnView.classList.add('active');
        if (igBtnView) igBtnView.classList.remove('active');
        if (fbBoxView) fbBoxView.style.display = 'block';
        if (igBoxView) igBoxView.style.display = 'none';
    } else {
        if (fbBtnModal) fbBtnModal.classList.remove('active');
        if (igBtnModal) igBtnModal.classList.add('active');
        if (fbBoxModal) fbBoxModal.style.display = 'none';
        if (igBoxModal) igBoxModal.style.display = 'block';

        if (fbBtnView) fbBtnView.classList.remove('active');
        if (igBtnView) igBtnView.classList.add('active');
        if (fbBoxView) fbBoxView.style.display = 'none';
        if (igBoxView) igBoxView.style.display = 'block';
    }
}

function handleFileSelect(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];

    // Validate size (16MB)
    if (file.size > 16 * 1024 * 1024) {
        showToast('File size exceeds 16MB limit', 'error');
        input.value = '';
        return;
    }

    const objectUrl = URL.createObjectURL(file);

    // Update Modal
    const fileNameEl = document.getElementById('file-name');
    const previewCard = document.getElementById('file-preview-card');
    const previewThumb = document.getElementById('preview-thumb-img');
    const fileLabel = document.getElementById('selected-file-label');

    if (fileNameEl) fileNameEl.textContent = file.name;
    if (previewThumb) previewThumb.src = objectUrl;
    if (fileLabel) fileLabel.textContent = file.name;
    if (previewCard) previewCard.style.display = 'flex';

    // Update View
    const vFileNameEl = document.getElementById('view-file-name');
    const vPreviewCard = document.getElementById('view-file-preview-card');
    const vPreviewThumb = document.getElementById('view-preview-thumb-img');
    const vFileLabel = document.getElementById('view-selected-file-label');

    if (vFileNameEl) vFileNameEl.textContent = file.name;
    if (vPreviewThumb) vPreviewThumb.src = objectUrl;
    if (vFileLabel) vFileLabel.textContent = file.name;
    if (vPreviewCard) vPreviewCard.style.display = 'flex';

    updateMockupMedia(objectUrl);
}

function clearSelectedMedia() {
    const fileInput = document.getElementById('post-file');
    const curImgInput = document.getElementById('current-image-filename');
    const previewCard = document.getElementById('file-preview-card');
    const fileNameEl = document.getElementById('file-name');

    if (fileInput) fileInput.value = '';
    if (curImgInput) curImgInput.value = '';
    if (previewCard) previewCard.style.display = 'none';
    if (fileNameEl) fileNameEl.textContent = 'Drag & drop image/video or browse files';

    // Also clear view composer
    const vFileInput = document.getElementById('view-composer-file');
    const vPreviewCard = document.getElementById('view-file-preview-card');
    const vFileNameEl = document.getElementById('view-file-name');

    if (vFileInput) vFileInput.value = '';
    if (vPreviewCard) vPreviewCard.style.display = 'none';
    if (vFileNameEl) vFileNameEl.textContent = 'Drag & drop image or browse files';

    clearMockupMedia();
}

function updateMockupMedia(src) {
    const placeholder = '<div class="fb-mockup-media-placeholder"><i class="fa-regular fa-image"></i><div>Attach an image to preview</div></div>';
    const imgHtml = `<img src="${src}" class="fb-mockup-img" alt="Post Mockup Media">`;
    const igImgHtml = `<img src="${src}" class="ig-mockup-img" alt="Post Mockup Media">`;

    const fbMedia = document.getElementById('fb-preview-media');
    const igMedia = document.getElementById('ig-preview-media');
    if (fbMedia) fbMedia.innerHTML = imgHtml;
    if (igMedia) igMedia.innerHTML = igImgHtml;

    const vFbMedia = document.getElementById('v-fb-preview-media');
    const vIgMedia = document.getElementById('v-ig-preview-media');
    if (vFbMedia) vFbMedia.innerHTML = imgHtml;
    if (vIgMedia) vIgMedia.innerHTML = igImgHtml;
}

function clearMockupMedia() {
    const fbPlaceholder = '<div class="fb-mockup-media-placeholder"><i class="fa-regular fa-image"></i><div>Attach an image or video to preview media layout</div></div>';
    const igPlaceholder = '<div class="fb-mockup-media-placeholder"><i class="fa-brands fa-instagram"></i><div>Attach an image to preview 1:1 Instagram frame</div></div>';

    const fbMedia = document.getElementById('fb-preview-media');
    const igMedia = document.getElementById('ig-preview-media');
    if (fbMedia) fbMedia.innerHTML = fbPlaceholder;
    if (igMedia) igMedia.innerHTML = igPlaceholder;

    const vFbMedia = document.getElementById('v-fb-preview-media');
    const vIgMedia = document.getElementById('v-ig-preview-media');
    if (vFbMedia) vFbMedia.innerHTML = fbPlaceholder;
    if (vIgMedia) vIgMedia.innerHTML = igPlaceholder;
}

// Save Post (Modal)
async function savePost() {
    const type = document.getElementById('post-type').value;
    const postId = document.getElementById('post-id').value;
    const message = document.getElementById('post-message').value.trim();
    const fileInput = document.getElementById('post-file');
    let filename = document.getElementById('current-image-filename').value;
    const saveBtn = document.getElementById('save-post-btn');

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';
    }

    // Media upload if a new file was chosen
    if (fileInput.files.length > 0) {
        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            const uploadRes = await authFetch('/api/upload', { method: 'POST', body: formData });
            const uploadData = await uploadRes.json();
            if (uploadData.filename) {
                filename = uploadData.filename;
            } else {
                showToast(uploadData.error || 'Upload failed', 'error');
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
                }
                return;
            }
        } catch (e) {
            showToast('Media upload failed due to network error', 'error');
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
            }
            return;
        }
    }

    const payload = { message, image_filename: filename };

    try {
        if (postId) {
            const res = await authFetch(`/api/posts/${type}/${postId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast('Post updated successfully', 'success');
            } else {
                showToast('Failed to update post', 'error');
            }
        } else {
            const res = await authFetch(`/api/posts/${type}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast(`New post queued for ${CHANNEL_INFO[type]?.name || type}`, 'success');
            } else {
                showToast('Failed to create post', 'error');
            }
        }
    } catch (e) {
        showToast('Error communicating with server', 'error');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
        }
    }

    closeModal();
    if (currentTab === type) loadPosts(type);
    if (currentTab === 'dashboard') {
        loadDashboardTotalPosts();
        const filter = document.getElementById('dashboard-filter');
        if (filter && filter.value === type) filterDashboardPosts(type);
    }
}

// Save Post (Full Screen View Composer)
async function saveViewComposerPost() {
    const type = document.getElementById('view-composer-type').value;
    const message = document.getElementById('view-composer-caption').value.trim();
    const fileInput = document.getElementById('view-composer-file');
    let filename = '';

    if (!message && fileInput.files.length === 0) {
        showToast('Please provide a caption or attach media', 'error');
        return;
    }

    if (fileInput.files.length > 0) {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        const uploadRes = await authFetch('/api/upload', { method: 'POST', body: formData });
        const uploadData = await uploadRes.json();
        if (uploadData.filename) {
            filename = uploadData.filename;
        } else {
            showToast(uploadData.error || 'Upload failed', 'error');
            return;
        }
    }

    const payload = { message, image_filename: filename };
    const res = await authFetch(`/api/posts/${type}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (res.ok) {
        showToast(`Post queued for ${CHANNEL_INFO[type]?.name || type}!`, 'success');
        resetViewComposer();
    } else {
        showToast('Failed to create post', 'error');
    }
}

function resetViewComposer() {
    const caption = document.getElementById('view-composer-caption');
    const fileInput = document.getElementById('view-composer-file');
    if (caption) caption.value = '';
    if (fileInput) fileInput.value = '';
    clearSelectedMedia();
    handleCaptionInput('');
}

// Delete Single Post
async function deletePost(type, postId) {
    showConfirm(`Are you sure you want to delete post #${postId}? This action cannot be undone.`, async () => {
        try {
            const res = await authFetch(`/api/posts/${type}/${postId}`, { method: 'DELETE' });
            if (res.ok) {
                showToast(`Post #${postId} deleted`, 'success');
                if (currentTab === type) loadPosts(type);
                if (currentTab === 'dashboard') {
                    loadDashboardTotalPosts();
                    const filter = document.getElementById('dashboard-filter');
                    if (filter && filter.value === type) filterDashboardPosts(type);
                }
            } else {
                showToast('Failed to delete post', 'error');
            }
        } catch (e) {
            showToast('Error deleting post', 'error');
        }
    });
}

// Bulk Delete All Posts in Channel
async function deleteAllPosts(type) {
    const channelName = CHANNEL_INFO[type]?.name || type.toUpperCase();
    const msg = `Are you sure you want to delete <strong>ALL</strong> posts for <strong>${channelName}</strong>? All media files unreferenced by other posts will be purged.`;

    showConfirm(msg, async () => {
        try {
            const res = await authFetch(`/api/posts/${type}/all`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                showToast(`All ${channelName} posts cleared`, 'success');
                if (currentTab === type) loadPosts(type);
                if (currentTab === 'dashboard') {
                    loadDashboardTotalPosts();
                    const filter = document.getElementById('dashboard-filter');
                    if (filter && filter.value === type) filterDashboardPosts(type);
                }
            } else {
                showToast(data.error || 'Failed to clear posts', 'error');
            }
        } catch (e) {
            showToast('Error clearing channel posts', 'error');
        }
    });
}

// Confirmation Dialog Modal Logic
function showConfirm(htmlMessage, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    const msgEl = document.getElementById('confirm-msg');
    const yesBtn = document.getElementById('confirm-yes-btn');

    if (!modal || !msgEl || !yesBtn) return;

    msgEl.innerHTML = htmlMessage;
    modal.classList.add('show');

    const newBtn = yesBtn.cloneNode(true);
    yesBtn.parentNode.replaceChild(newBtn, yesBtn);

    newBtn.onclick = () => {
        onConfirm();
        closeConfirmModal();
    };
}

function closeConfirmModal() {
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.remove('show');
}

// Authentication
async function handleLogout() {
    try {
        await authFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {}
    window.location.href = '/login';
}

// Toast System
function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? 'fa-circle-check' : (type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-info');

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Utility: Escape HTML
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function highlightMatch(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark style="background:#fef08a; padding:0 2px; border-radius:2px;">$1</mark>');
}

// ==========================================================================
// Phase 2: Composer Advanced Handlers (Brands, Timezones, Multiple Actions)
// ==========================================================================

async function initComposerView() {
    // 1. Set default scheduled datetime to 2 hours from now in local time
    const dtInput = document.getElementById('view-composer-datetime');
    if (dtInput) {
        const d = new Date(Date.now() + 2 * 3600 * 1000);
        const pad = (n) => String(n).padStart(2, '0');
        const formatted = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
        dtInput.value = formatted;
        dtInput.min = `${new Date().getFullYear()}-${pad(new Date().getMonth() + 1)}-${pad(new Date().getDate())}T${pad(new Date().getHours())}:${pad(new Date().getMinutes())}`;
    }

    // 2. Fetch and populate brands
    try {
        const res = await authFetch('/api/brands');
        if (res.ok) {
            const brands = await res.json();
            const brandSelect = document.getElementById('view-composer-brand');
            if (brandSelect && brands.length > 0) {
                brandSelect.innerHTML = brands.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
            }
        }
    } catch (e) {
        console.error('Failed to load brands:', e);
    }

    // 3. Fetch and populate timezones
    try {
        const res = await authFetch('/api/timezones');
        if (res.ok) {
            const tzData = await res.json();
            const tzSelect = document.getElementById('view-composer-timezone');
            if (tzSelect && tzData.timezones) {
                tzSelect.innerHTML = tzData.timezones.map(tz => 
                    `<option value="${tz}" ${tz === tzData.default ? 'selected' : ''}>${tz}</option>`
                ).join('');
            }
        }
    } catch (e) {
        console.error('Failed to load timezones:', e);
    }
}

async function handleComposerSubmit(status) {
    const postType = document.getElementById('view-composer-type')?.value;
    const message = document.getElementById('view-composer-caption')?.value.trim() || '';
    const fileInput = document.getElementById('view-composer-file');
    const brandId = document.getElementById('view-composer-brand')?.value || null;
    const dtVal = document.getElementById('view-composer-datetime')?.value;
    const tzVal = document.getElementById('view-composer-timezone')?.value || 'UTC';

    if (!message && (!fileInput || fileInput.files.length === 0)) {
        showToast('Please provide a post caption or attach media', 'error');
        return;
    }

    if (status === 'scheduled' && !dtVal) {
        showToast('Please select a scheduled date and time', 'error');
        return;
    }

    let imageFilename = null;
    if (fileInput && fileInput.files.length > 0) {
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        try {
            const uploadRes = await authFetch('/api/upload', { method: 'POST', body: formData });
            const uploadData = await uploadRes.json();
            if (uploadData.filename) {
                imageFilename = uploadData.filename;
            } else {
                showToast(uploadData.error || 'Failed to upload media', 'error');
                return;
            }
        } catch (e) {
            showToast('Media upload failed: ' + e.message, 'error');
            return;
        }
    }

    let scheduledFor = dtVal;
    if (!scheduledFor) {
        const d = new Date(Date.now() + 3600 * 1000);
        scheduledFor = d.toISOString();
    }

    const payload = {
        post_type: postType,
        scheduled_for: scheduledFor,
        timezone: tzVal,
        message: message,
        image_filename: imageFilename,
        brand_id: brandId ? parseInt(brandId, 10) : null,
        status: status
    };

    try {
        const res = await authFetch('/api/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            if (status === 'draft') {
                showToast('Draft post saved successfully!', 'success');
                loadTab('queue');
            } else if (status === 'pending_approval') {
                showToast('Post submitted for approval!', 'success');
                loadTab('approvals');
            } else {
                showToast('Post scheduled successfully on calendar!', 'success');
                loadTab('calendar');
            }
            resetViewComposer();
        } else {
            showToast(data.error || 'Failed to save post', 'error');
        }
    } catch (e) {
        showToast('Error scheduling post: ' + e.message, 'error');
    }
}

async function updatePendingApprovalsBadge() {
    try {
        const res = await authFetch('/api/approvals/pending');
        if (res.ok) {
            const data = await res.json();
            const badge = document.getElementById('nav-approvals-count');
            if (badge) {
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }
        }
    } catch (e) {
        // silent
    }
}

// ==========================================================================
// Phase 2: Interactive Content Calendar Engine
// ==========================================================================

let calendarCurrentDate = new Date();
let calendarActiveView = 'month'; // 'month', 'week', 'day', 'list'
let calendarFilterChannel = 'all';
let calendarFilterBrand = 'all';
let calendarFilterStatus = 'all';
let cachedScheduledPosts = [];
let cachedBrandsList = [];

async function renderCalendarView(container) {
    container.innerHTML = `
        <div class="calendar-toolbar">
            <div class="calendar-nav-group">
                <button type="button" class="btn btn-secondary btn-sm" onclick="prevCalendar()" title="Previous">
                    <i class="fa-solid fa-chevron-left"></i>
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="todayCalendar()">Today</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="nextCalendar()" title="Next">
                    <i class="fa-solid fa-chevron-right"></i>
                </button>
                <span id="calendar-title-label" class="calendar-title-display"></span>
            </div>

            <div class="view-btn-group">
                <button type="button" id="cview-btn-month" class="view-btn active" onclick="setCalendarView('month')">Month</button>
                <button type="button" id="cview-btn-week" class="view-btn" onclick="setCalendarView('week')">Week</button>
                <button type="button" id="cview-btn-day" class="view-btn" onclick="setCalendarView('day')">Day</button>
                <button type="button" id="cview-btn-list" class="view-btn" onclick="setCalendarView('list')">Agenda / List</button>
            </div>

            <div class="calendar-filters-group">
                <select id="cal-filter-channel" onchange="handleCalendarFilterChange()">
                    <option value="all">All Channels</option>
                    <option value="tour">Nexora Suite</option>
                    <option value="nz">Phoenix Intl</option>
                    <option value="gaatha">Gaatha AI</option>
                    <option value="insta">Instagram Sync</option>
                </select>
                <select id="cal-filter-brand" onchange="handleCalendarFilterChange()">
                    <option value="all">All Brands</option>
                </select>
                <select id="cal-filter-status" onchange="handleCalendarFilterChange()">
                    <option value="all">All Statuses</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="pending_approval">Pending Approval</option>
                    <option value="draft">Draft</option>
                    <option value="published">Published</option>
                    <option value="failed">Failed</option>
                </select>
                <button type="button" class="btn btn-primary btn-sm" onclick="loadTab('composer')">
                    <i class="fa-solid fa-plus"></i> New Post
                </button>
            </div>
        </div>

        <div id="calendar-content-root">
            <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
                <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
                Loading scheduled content...
            </div>
        </div>
    `;

    await loadCalendarData();
}

async function loadCalendarData() {
    try {
        // Fetch brands if not cached
        if (cachedBrandsList.length === 0) {
            const bRes = await authFetch('/api/brands');
            if (bRes.ok) cachedBrandsList = await bRes.json();
            const brandSel = document.getElementById('cal-filter-brand');
            if (brandSel && cachedBrandsList.length > 0) {
                brandSel.innerHTML = '<option value="all">All Brands</option>' + 
                    cachedBrandsList.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
            }
        }

        let calUrl = `/api/calendar/events?brand_id=${encodeURIComponent(calendarFilterBrand)}&status=${encodeURIComponent(calendarFilterStatus)}&platform=${encodeURIComponent(calendarFilterChannel)}`;
        const res = await authFetch(calUrl);
        if (res.ok) {
            cachedScheduledPosts = await res.json();
        } else {
            const fallbackRes = await authFetch('/api/schedule?limit=500');
            cachedScheduledPosts = fallbackRes.ok ? await fallbackRes.json() : [];
        }
    } catch (e) {
        console.error('Error fetching calendar posts:', e);
        cachedScheduledPosts = [];
    }

    renderCalendarContent();
}

function handleCalendarFilterChange() {
    calendarFilterChannel = document.getElementById('cal-filter-channel')?.value || 'all';
    calendarFilterBrand = document.getElementById('cal-filter-brand')?.value || 'all';
    calendarFilterStatus = document.getElementById('cal-filter-status')?.value || 'all';
    renderCalendarContent();
}

function prevCalendar() {
    if (calendarActiveView === 'month') {
        calendarCurrentDate.setMonth(calendarCurrentDate.getMonth() - 1);
    } else if (calendarActiveView === 'week') {
        calendarCurrentDate.setDate(calendarCurrentDate.getDate() - 7);
    } else if (calendarActiveView === 'day') {
        calendarCurrentDate.setDate(calendarCurrentDate.getDate() - 1);
    }
    renderCalendarContent();
}

function nextCalendar() {
    if (calendarActiveView === 'month') {
        calendarCurrentDate.setMonth(calendarCurrentDate.getMonth() + 1);
    } else if (calendarActiveView === 'week') {
        calendarCurrentDate.setDate(calendarCurrentDate.getDate() + 7);
    } else if (calendarActiveView === 'day') {
        calendarCurrentDate.setDate(calendarCurrentDate.getDate() + 1);
    }
    renderCalendarContent();
}

function todayCalendar() {
    calendarCurrentDate = new Date();
    renderCalendarContent();
}

function setCalendarView(view) {
    calendarActiveView = view;
    document.querySelectorAll('.view-btn').forEach(btn => {
        if (btn.id === `cview-btn-${view}`) btn.classList.add('active');
        else btn.classList.remove('active');
    });
    renderCalendarContent();
}

function getFilteredCalendarPosts() {
    return cachedScheduledPosts.filter(p => {
        if (calendarFilterChannel !== 'all' && p.post_type !== calendarFilterChannel) return false;
        if (calendarFilterBrand !== 'all' && String(p.brand_id) !== String(calendarFilterBrand)) return false;
        if (calendarFilterStatus !== 'all' && p.status !== calendarFilterStatus) return false;
        return true;
    });
}

function renderCalendarContent() {
    const root = document.getElementById('calendar-content-root');
    const titleLabel = document.getElementById('calendar-title-label');
    if (!root) return;

    const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];

    if (titleLabel) {
        if (calendarActiveView === 'month') {
            titleLabel.textContent = `${monthNames[calendarCurrentDate.getMonth()]} ${calendarCurrentDate.getFullYear()}`;
        } else if (calendarActiveView === 'week') {
            titleLabel.textContent = `Week of ${monthNames[calendarCurrentDate.getMonth()]} ${calendarCurrentDate.getDate()}, ${calendarCurrentDate.getFullYear()}`;
        } else if (calendarActiveView === 'day') {
            titleLabel.textContent = `${calendarCurrentDate.toDateString()}`;
        } else {
            titleLabel.textContent = `Scheduled Content (${calendarCurrentDate.getFullYear()})`;
        }
    }

    if (calendarActiveView === 'month') {
        renderCalendarMonthGrid(root);
    } else if (calendarActiveView === 'week') {
        renderCalendarWeekView(root);
    } else if (calendarActiveView === 'day') {
        renderCalendarDayView(root);
    } else {
        renderCalendarListView(root);
    }
}

function renderCalendarMonthGrid(root) {
    const year = calendarCurrentDate.getFullYear();
    const month = calendarCurrentDate.getMonth();
    const firstDayIndex = new Date(year, month, 1).getDay(); // 0 is Sun
    const totalDaysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    // Monday-first indexing: (day + 6) % 7
    const adjustedFirstDay = (firstDayIndex + 6) % 7;

    const today = new Date();
    const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    const filtered = getFilteredCalendarPosts();

    let html = `
        <div class="calendar-grid-wrap">
            <div class="calendar-day-headers-row">
                <div class="calendar-day-header-cell">Mon</div>
                <div class="calendar-day-header-cell">Tue</div>
                <div class="calendar-day-header-cell">Wed</div>
                <div class="calendar-day-header-cell">Thu</div>
                <div class="calendar-day-header-cell">Fri</div>
                <div class="calendar-day-header-cell">Sat</div>
                <div class="calendar-day-header-cell">Sun</div>
            </div>
            <div class="calendar-month-grid">
    `;

    // Trailing days from previous month
    for (let i = adjustedFirstDay - 1; i >= 0; i--) {
        const d = prevMonthDays - i;
        html += `
            <div class="calendar-day-cell other-month">
                <div class="calendar-day-num">${d}</div>
            </div>
        `;
    }

    // Days in current month
    const pad = (n) => String(n).padStart(2, '0');
    for (let day = 1; day <= totalDaysInMonth; day++) {
        const dateStr = `${year}-${pad(month + 1)}-${pad(day)}`;
        const isToday = isCurrentMonth && today.getDate() === day;

        // Find posts on this date
        const dayPosts = filtered.filter(p => {
            const postDate = (p.local_scheduled_for || p.scheduled_for || '').substring(0, 10);
            return postDate === dateStr;
        });

        html += `
            <div class="calendar-day-cell ${isToday ? 'today' : ''}" onclick="handleCalendarDayClick('${dateStr}', event)">
                <div class="calendar-day-num">
                    <span>${day}</span>
                    ${dayPosts.length > 0 ? `<small style="color:var(--text-muted); font-size:0.7rem;">${dayPosts.length} post${dayPosts.length > 1 ? 's' : ''}</small>` : ''}
                </div>
                <div class="calendar-events-wrap">
        `;

        dayPosts.slice(0, 3).forEach(p => {
            const timeStr = (p.local_scheduled_for || p.scheduled_for || '').substring(11, 16);
            html += `
                <div class="calendar-pill pill-${p.post_type}" onclick="openPostDetails(${p.id}, event)" title="${escapeHtml(p.message || '')}">
                    <span style="font-weight: 700; font-size: 0.7rem;">${timeStr}</span>
                    <span class="text-truncate" style="flex:1;">${escapeHtml(p.message || '(Media Attachment)')}</span>
                    <span class="badge badge-${p.status}" style="padding: 1px 4px; font-size: 0.65rem;">${p.status}</span>
                </div>
            `;
        });

        if (dayPosts.length > 3) {
            html += `
                <div style="font-size: 0.72rem; color: var(--primary); font-weight: 700; text-align: center; cursor: pointer;" onclick="setCalendarView('day'); calendarCurrentDate = new Date('${dateStr}'); renderCalendarContent(); event.stopPropagation();">
                    +${dayPosts.length - 3} more
                </div>
            `;
        }

        html += `
                </div>
            </div>
        `;
    }

    // Days into next month to complete the grid (multiples of 7)
    const totalRendered = adjustedFirstDay + totalDaysInMonth;
    const remaining = (7 - (totalRendered % 7)) % 7;
    for (let j = 1; j <= remaining; j++) {
        html += `
            <div class="calendar-day-cell other-month">
                <div class="calendar-day-num">${j}</div>
            </div>
        `;
    }

    html += `
            </div>
        </div>
    `;

    root.innerHTML = html;
}

function renderCalendarWeekView(root) {
    const startOfWeek = new Date(calendarCurrentDate);
    const day = (startOfWeek.getDay() + 6) % 7;
    startOfWeek.setDate(startOfWeek.getDate() - day); // Mon

    const filtered = getFilteredCalendarPosts();
    const pad = (n) => String(n).padStart(2, '0');
    const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    let html = `
        <div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.75rem;">
    `;

    for (let i = 0; i < 7; i++) {
        const d = new Date(startOfWeek);
        d.setDate(startOfWeek.getDate() + i);
        const dateStr = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

        const dayPosts = filtered.filter(p => {
            const postDate = (p.local_scheduled_for || p.scheduled_for || '').substring(0, 10);
            return postDate === dateStr;
        });

        html += `
            <div class="card" style="padding: 0.75rem; min-height: 380px; display: flex; flex-direction: column;">
                <div style="border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 0.75rem; text-align: center;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">${dayNames[i]}</div>
                    <div style="font-size: 1.15rem; font-weight: 800; color: var(--primary);">${d.getDate()}</div>
                </div>
                <div style="flex: 1; display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto;">
        `;

        if (dayPosts.length === 0) {
            html += `<div style="color: var(--text-muted); font-size: 0.75rem; text-align: center; margin-top: 2rem;">No posts</div>`;
        } else {
            dayPosts.forEach(p => {
                const timeStr = (p.local_scheduled_for || p.scheduled_for || '').substring(11, 16);
                html += `
                    <div class="calendar-pill pill-${p.post_type}" onclick="openPostDetails(${p.id}, event)" style="padding: 0.5rem; flex-direction: column; align-items: flex-start; gap: 0.25rem;">
                        <div style="display: flex; justify-content: space-between; width: 100%; font-size: 0.72rem;">
                            <span style="font-weight: 700;">${timeStr}</span>
                            <span class="badge badge-${p.status}">${p.status}</span>
                        </div>
                        <div style="font-size: 0.8rem; line-height: 1.35; max-height: 48px; overflow: hidden;">${escapeHtml(p.message || '(Media Attachment)')}</div>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;
    }

    html += `</div>`;
    root.innerHTML = html;
}

function renderCalendarDayView(root) {
    const pad = (n) => String(n).padStart(2, '0');
    const dateStr = `${calendarCurrentDate.getFullYear()}-${pad(calendarCurrentDate.getMonth() + 1)}-${pad(calendarCurrentDate.getDate())}`;

    const filtered = getFilteredCalendarPosts().filter(p => {
        const postDate = (p.local_scheduled_for || p.scheduled_for || '').substring(0, 10);
        return postDate === dateStr;
    });

    let html = `
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.25rem;">
                <div>
                    <h3 style="margin: 0; font-size: 1.2rem; font-weight: 700;">${calendarCurrentDate.toDateString()}</h3>
                    <small style="color: var(--text-muted);">${filtered.length} scheduled item${filtered.length === 1 ? '' : 's'}</small>
                </div>
                <button type="button" class="btn btn-primary btn-sm" onclick="loadTab('composer')">
                    <i class="fa-solid fa-plus"></i> Schedule for Today
                </button>
            </div>
    `;

    if (filtered.length === 0) {
        html += `
            <div style="text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
                <i class="fa-regular fa-calendar-xmark" style="font-size: 2.5rem; margin-bottom: 0.75rem; display: block; opacity: 0.5;"></i>
                <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.25rem;">No posts scheduled for this date</div>
                <p style="font-size: 0.85rem; max-width: 380px; margin: 0 auto 1.25rem;">Create a new social post or schedule automated campaign content for this slot.</p>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadTab('composer')">Open Composer</button>
            </div>
        `;
    } else {
        html += `<div style="display: flex; flex-direction: column; gap: 0.85rem;">`;
        filtered.forEach(p => {
            const timeStr = (p.local_scheduled_for || p.scheduled_for || '').substring(11, 16);
            html += `
                <div class="calendar-list-card" onclick="openPostDetails(${p.id}, event)" style="cursor: pointer;">
                    <div class="calendar-list-date-badge">
                        <div class="calendar-list-date-day">${timeStr}</div>
                        <div class="calendar-list-date-month">${p.display_timezone || 'UTC'}</div>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; flex-wrap: wrap;">
                            <span class="badge" style="background: var(--bg-app); border: 1px solid var(--border);">${CHANNEL_INFO[p.post_type]?.name || p.post_type}</span>
                            <span class="badge badge-${p.status}">${p.status}</span>
                            ${p.idempotency_key ? `<small style="color: var(--text-muted); font-size: 0.72rem;">#${p.id}</small>` : ''}
                        </div>
                        <div style="font-size: 0.9rem; line-height: 1.45; color: var(--text-primary); margin-bottom: 0.25rem;" class="text-truncate">${escapeHtml(p.message || '(Media Attachment)')}</div>
                        ${p.image_filename ? `<small style="color: var(--success); font-size: 0.75rem;"><i class="fa-solid fa-paperclip"></i> ${escapeHtml(p.image_filename)}</small>` : ''}
                    </div>
                    <div>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id}, event)">Inspect</button>
                    </div>
                </div>
            `;
        });
        html += `</div>`;
    }

    html += `</div>`;
    root.innerHTML = html;
}

function renderCalendarListView(root) {
    const filtered = getFilteredCalendarPosts().sort((a, b) => {
        return (a.scheduled_for || '').localeCompare(b.scheduled_for || '');
    });

    let html = `
        <div class="calendar-list-view">
    `;

    if (filtered.length === 0) {
        html += `
            <div class="card" style="text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
                <i class="fa-solid fa-calendar-check" style="font-size: 2.5rem; margin-bottom: 0.75rem; display: block; opacity: 0.5;"></i>
                <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.25rem;">No scheduled posts match current filters</div>
                <p style="font-size: 0.85rem;">Adjust your channel, brand, or status filters, or compose a new post.</p>
            </div>
        `;
    } else {
        filtered.forEach(p => {
            const rawDt = p.local_scheduled_for || p.scheduled_for || '';
            const datePart = rawDt.substring(0, 10);
            const timePart = rawDt.substring(11, 16);

            html += `
                <div class="calendar-list-card" onclick="openPostDetails(${p.id}, event)" style="cursor: pointer;">
                    <div class="calendar-list-date-badge">
                        <div class="calendar-list-date-day">${datePart.substring(8, 10)}</div>
                        <div class="calendar-list-date-month">${datePart.substring(5, 7)}/${datePart.substring(0, 4)}</div>
                        <small style="font-size: 0.72rem; color: var(--primary); font-weight: 700;">${timePart}</small>
                    </div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; flex-wrap: wrap;">
                            <span class="badge" style="background: var(--bg-app); border: 1px solid var(--border);">${CHANNEL_INFO[p.post_type]?.name || p.post_type}</span>
                            <span class="badge badge-${p.status}">${p.status}</span>
                            ${p.timezone ? `<small style="color: var(--text-muted); font-size: 0.72rem;">Zone: ${p.timezone}</small>` : ''}
                        </div>
                        <div style="font-size: 0.9rem; line-height: 1.45; color: var(--text-primary); margin-bottom: 0.25rem;">${escapeHtml(p.message || '(Media Attachment)')}</div>
                        ${p.image_filename ? `<small style="color: var(--success); font-size: 0.75rem;"><i class="fa-solid fa-paperclip"></i> ${escapeHtml(p.image_filename)}</small>` : ''}
                    </div>
                    <div style="display: flex; gap: 0.5rem;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id}, event)">Details</button>
                    </div>
                </div>
            `;
        });
    }

    html += `</div>`;
    root.innerHTML = html;
}

function handleCalendarDayClick(dateStr, event) {
    if (event.target.closest('.calendar-pill') || event.target.closest('button')) {
        return; // Handled by pill or button
    }
    // Set composer date and open composer
    loadTab('composer');
    setTimeout(() => {
        const dtInput = document.getElementById('view-composer-datetime');
        if (dtInput) {
            dtInput.value = `${dateStr}T10:00`;
        }
    }, 150);
}

// ==========================================================================
// Phase 2: Post Details & Audit Modal Controller
// ==========================================================================

let activeDetailsPost = null;

async function openPostDetails(postId, event) {
    if (event) event.stopPropagation();

    const modal = document.getElementById('post-details-modal');
    if (!modal) return;

    modal.classList.add('show');
    document.getElementById('details-title-display') || null;

    // Reset fields
    document.getElementById('details-caption').textContent = 'Loading...';
    document.getElementById('details-scheduled-time').textContent = '...';
    document.getElementById('details-error-alert').style.display = 'none';
    document.getElementById('details-rejection-alert').style.display = 'none';
    document.getElementById('details-media-container').style.display = 'none';
    document.getElementById('details-action-left').innerHTML = '';
    document.getElementById('details-audit-timeline').innerHTML = '<div style="color: var(--text-muted); font-size:0.82rem;">Fetching history...</div>';

    // Find post in cache or fetch
    let post = cachedScheduledPosts.find(p => p.id === postId);
    if (!post) {
        try {
            const res = await authFetch('/api/schedule');
            if (res.ok) {
                const all = await res.json();
                post = all.find(p => p.id === postId);
            }
        } catch (e) {}
    }

    activeDetailsPost = post;

    if (post) {
        document.getElementById('details-status-badge').className = `badge badge-${post.status}`;
        document.getElementById('details-status-badge').textContent = post.status.toUpperCase();
        document.getElementById('details-channel-name').textContent = CHANNEL_INFO[post.post_type]?.name || post.post_type;
        
        const brandObj = cachedBrandsList.find(b => b.id === post.brand_id);
        document.getElementById('details-brand-name').textContent = brandObj ? brandObj.name : 'Default Workspace';
        
        document.getElementById('details-scheduled-time').textContent = post.local_display || post.scheduled_for;
        document.getElementById('details-caption').textContent = post.message || '(No text caption provided)';

        if (post.image_filename) {
            document.getElementById('details-media-container').style.display = 'block';
            document.getElementById('details-media-img').src = `/static/images/${encodeURIComponent(post.image_filename)}`;
        }

        if (post.status === 'failed' && post.error_message) {
            document.getElementById('details-error-alert').style.display = 'block';
            document.getElementById('details-error-msg').textContent = post.error_message;
        }

        if (post.status === 'rejected' && post.rejection_reason) {
            document.getElementById('details-rejection-alert').style.display = 'block';
            document.getElementById('details-rejection-msg').textContent = post.rejection_reason;
        }

        // Action Buttons based on status
        renderDetailsActionButtons(post);
    }

    // Load audit trail
    try {
        const histRes = await authFetch(`/api/schedule/${postId}/history`);
        if (histRes.ok) {
            const histData = await histRes.json();
            renderAuditTimeline(histData.history || []);
        } else {
            document.getElementById('details-audit-timeline').innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">No audit logs recorded for this item.</div>';
        }
    } catch (e) {
        document.getElementById('details-audit-timeline').innerHTML = '<div style="color: var(--danger); font-size: 0.8rem;">Failed to load audit history.</div>';
    }
}

function renderDetailsActionButtons(post) {
    const actionWrap = document.getElementById('details-action-left');
    if (!actionWrap) return;

    let btns = '';
    if (post.status === 'pending_approval') {
        btns += `
            <button type="button" class="btn btn-success btn-sm" onclick="approvePostFromDetails(${post.id})">
                <i class="fa-solid fa-check"></i> Approve Post
            </button>
            <button type="button" class="btn btn-danger btn-sm" onclick="openRejectModal(${post.id})">
                <i class="fa-solid fa-xmark"></i> Reject Post
            </button>
        `;
    } else if (post.status === 'failed') {
        btns += `
            <button type="button" class="btn btn-primary btn-sm" onclick="retryPostFromDetails(${post.id})">
                <i class="fa-solid fa-rotate-right"></i> Retry Publishing
            </button>
        `;
    }

    if (['scheduled', 'draft', 'pending_approval', 'rejected', 'failed'].includes(post.status)) {
        btns += `
            <button type="button" class="btn btn-secondary btn-sm" onclick="openRescheduleModal(${post.id})">
                <i class="fa-solid fa-clock"></i> Reschedule
            </button>
            <button type="button" class="btn btn-danger btn-sm" onclick="cancelPostFromDetails(${post.id})">
                <i class="fa-solid fa-ban"></i> Cancel Post
            </button>
        `;
    }

    actionWrap.innerHTML = btns;
}

function renderAuditTimeline(events) {
    const timeline = document.getElementById('details-audit-timeline');
    if (!timeline) return;

    if (events.length === 0) {
        timeline.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">Initial creation event only.</div>';
        return;
    }

    timeline.innerHTML = events.map(e => `
        <div class="audit-timeline-item">
            <div class="audit-timeline-dot"></div>
            <div class="audit-timeline-header">
                <span class="audit-timeline-action">
                    ${e.from_status ? `<span class="badge badge-${e.from_status}" style="font-size:0.65rem;">${e.from_status}</span> &rarr; ` : ''}
                    <span class="badge badge-${e.to_status}" style="font-size:0.65rem;">${e.to_status}</span>
                </span>
                <span class="audit-timeline-time">${e.created_at}</span>
                ${e.changed_by_username ? `<span class="badge" style="font-size:0.68rem; background:var(--bg-app);">${escapeHtml(e.changed_by_username)}</span>` : ''}
            </div>
            ${e.reason ? `<div class="audit-timeline-reason">${escapeHtml(e.reason)}</div>` : ''}
        </div>
    `).join('');
}

function closeDetailsModal() {
    const modal = document.getElementById('post-details-modal');
    if (modal) modal.classList.remove('show');
    activeDetailsPost = null;
}

async function approvePostFromDetails(id) {
    try {
        const res = await authFetch(`/api/approvals/${id}/approve`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('Post approved for scheduling!', 'success');
            closeDetailsModal();
            refreshActiveWorkflowView();
        } else {
            showToast(data.error || 'Failed to approve post', 'error');
        }
    } catch (e) {
        showToast('Approval error: ' + e.message, 'error');
    }
}

async function cancelPostFromDetails(id) {
    showConfirm('Are you sure you want to cancel this scheduled post? It will not be published.', async () => {
        try {
            const res = await authFetch(`/api/schedule/${id}`, { method: 'DELETE' });
            if (res.ok) {
                showToast('Post cancelled successfully', 'success');
                closeDetailsModal();
                refreshActiveWorkflowView();
            } else {
                const data = await res.json();
                showToast(data.error || 'Failed to cancel post', 'error');
            }
        } catch (e) {
            showToast('Cancellation error: ' + e.message, 'error');
        }
    });
}

async function retryPostFromDetails(id) {
    try {
        const res = await authFetch(`/api/schedule/${id}/retry`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('Post returned to publishing queue!', 'success');
            closeDetailsModal();
            refreshActiveWorkflowView();
        } else {
            showToast(data.error || 'Failed to retry post', 'error');
        }
    } catch (e) {
        showToast('Retry error: ' + e.message, 'error');
    }
}

// Rejection Modal Handlers
function openRejectModal(postId) {
    const modal = document.getElementById('reject-reason-modal');
    const idInput = document.getElementById('reject-post-id');
    const reasonInput = document.getElementById('reject-reason-input');
    if (modal && idInput) {
        idInput.value = postId;
        if (reasonInput) reasonInput.value = '';
        modal.classList.add('show');
    }
}

function closeRejectModal() {
    const modal = document.getElementById('reject-reason-modal');
    if (modal) modal.classList.remove('show');
}

async function confirmRejectPost() {
    const id = document.getElementById('reject-post-id')?.value;
    const reason = document.getElementById('reject-reason-input')?.value.trim();

    if (!reason) {
        showToast('A specific rejection reason is mandatory', 'error');
        return;
    }

    try {
        const res = await authFetch(`/api/approvals/${id}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Post rejected and returned for revision', 'success');
            closeRejectModal();
            closeDetailsModal();
            refreshActiveWorkflowView();
        } else {
            showToast(data.error || 'Failed to reject post', 'error');
        }
    } catch (e) {
        showToast('Error rejecting post: ' + e.message, 'error');
    }
}

// Reschedule Modal Handlers
async function openRescheduleModal(postId) {
    const modal = document.getElementById('reschedule-modal');
    const idInput = document.getElementById('reschedule-post-id');
    const dtInput = document.getElementById('reschedule-datetime');
    const tzSelect = document.getElementById('reschedule-timezone');

    if (modal && idInput) {
        idInput.value = postId;

        // Set default to current post scheduled time or 2 hours ahead
        const post = cachedScheduledPosts.find(p => p.id === postId);
        if (dtInput) {
            if (post && post.local_scheduled_for) {
                dtInput.value = post.local_scheduled_for.substring(0, 16);
            } else {
                const d = new Date(Date.now() + 2 * 3600 * 1000);
                const pad = (n) => String(n).padStart(2, '0');
                dtInput.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
            }
        }

        // Populate timezones
        try {
            const tzRes = await authFetch('/api/timezones');
            if (tzRes.ok) {
                const tzData = await tzRes.json();
                if (tzSelect && tzData.timezones) {
                    const defaultZone = post?.timezone || tzData.default;
                    tzSelect.innerHTML = tzData.timezones.map(tz => 
                        `<option value="${tz}" ${tz === defaultZone ? 'selected' : ''}>${tz}</option>`
                    ).join('');
                }
            }
        } catch (e) {}

        modal.classList.add('show');
    }
}

function closeRescheduleModal() {
    const modal = document.getElementById('reschedule-modal');
    if (modal) modal.classList.remove('show');
}

async function confirmReschedulePost() {
    const id = document.getElementById('reschedule-post-id')?.value;
    const dtVal = document.getElementById('reschedule-datetime')?.value;
    const tzVal = document.getElementById('reschedule-timezone')?.value;

    if (!dtVal) {
        showToast('Please select a valid date and time', 'error');
        return;
    }

    try {
        const res = await authFetch(`/api/schedule/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scheduled_for: dtVal, timezone: tzVal })
        });
        const data = await res.json();
        if (res.ok) {
            showToast('Post rescheduled successfully!', 'success');
            closeRescheduleModal();
            closeDetailsModal();
            refreshActiveWorkflowView();
        } else {
            showToast(data.error || 'Failed to reschedule post', 'error');
        }
    } catch (e) {
        showToast('Rescheduling error: ' + e.message, 'error');
    }
}

function refreshActiveWorkflowView() {
    updatePendingApprovalsBadge();
    if (currentTab === 'calendar') loadCalendarData();
    else if (currentTab === 'approvals') renderApprovalsView(document.getElementById('content-area'));
    else if (currentTab === 'queue') renderQueueView(document.getElementById('content-area'));
}

// ==========================================================================
// Phase 2: Content Approvals Centre View
// ==========================================================================

async function renderApprovalsView(container) {
    container.innerHTML = `
        <div class="card" style="margin-bottom: 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <h3 style="margin: 0; font-size: 1.2rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-clipboard-check" style="color: #fbbf24;"></i> Approvals Centre
                    </h3>
                    <p style="margin: 0.25rem 0 0; color: var(--text-secondary); font-size: 0.85rem;">
                        Review, approve, or request revisions on pending content before it enters the automated publishing queue.
                    </p>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" onclick="renderApprovalsView(document.getElementById('content-area'))">
                    <i class="fa-solid fa-rotate"></i> Refresh
                </button>
            </div>
        </div>

        <div id="approvals-content-root">
            <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
                <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
                Fetching pending approvals...
            </div>
        </div>
    `;

    try {
        const res = await authFetch('/api/approvals/pending');
        if (!res.ok) throw new Error('Failed to retrieve approvals');
        const data = await res.json();
        const posts = data.posts || [];

        const root = document.getElementById('approvals-content-root');
        if (!root) return;

        if (posts.length === 0) {
            root.innerHTML = `
                <div class="card" style="text-align: center; padding: 4.5rem 1rem;">
                    <i class="fa-solid fa-circle-check" style="font-size: 3rem; color: var(--success); margin-bottom: 1rem; display: block;"></i>
                    <h4 style="font-weight: 700; font-size: 1.15rem; margin-bottom: 0.35rem;">All Caught Up!</h4>
                    <p style="color: var(--text-secondary); font-size: 0.88rem; max-width: 420px; margin: 0 auto 1.5rem;">
                        There are currently no marketing posts awaiting approval in your active organization.
                    </p>
                    <button type="button" class="btn btn-primary btn-sm" onclick="loadTab('composer')">
                        <i class="fa-solid fa-plus"></i> Compose New Post
                    </button>
                </div>
            `;
            return;
        }

        let html = `<div class="approvals-grid">`;
        posts.forEach(p => {
            html += `
                <div class="approval-card">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                            <span class="badge" style="background: var(--bg-app); border: 1px solid var(--border); font-size: 0.75rem;">
                                ${CHANNEL_INFO[p.post_type]?.name || p.post_type}
                            </span>
                            <span class="badge badge-pending_approval">Pending Approval</span>
                        </div>
                        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
                            <i class="fa-regular fa-clock"></i> Scheduled: <strong>${p.local_display || p.scheduled_for}</strong>
                        </div>
                        <div style="font-size: 0.9rem; line-height: 1.45; color: var(--text-primary); margin-bottom: 0.75rem; max-height: 120px; overflow-y: auto;">
                            ${escapeHtml(p.message || '(Media Attachment)')}
                        </div>
                        ${p.image_filename ? `
                            <div style="margin-bottom: 0.75rem; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; max-height: 140px; display: flex; justify-content: center; background: #000;">
                                <img src="/static/images/${encodeURIComponent(p.image_filename)}" alt="Attachment" style="max-height: 140px; object-fit: contain;">
                            </div>
                        ` : ''}
                    </div>
                    <div style="border-top: 1px solid var(--border); padding-top: 0.75rem; margin-top: 0.75rem; display: flex; gap: 0.5rem; justify-content: space-between;">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id})">
                            <i class="fa-solid fa-eye"></i> Details
                        </button>
                        <div style="display: flex; gap: 0.4rem;">
                            <button type="button" class="btn btn-danger btn-sm" onclick="openRejectModal(${p.id})">
                                <i class="fa-solid fa-xmark"></i> Reject
                            </button>
                            <button type="button" class="btn btn-success btn-sm" onclick="approvePost(${p.id})">
                                <i class="fa-solid fa-check"></i> Approve
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
        html += `</div>`;
        root.innerHTML = html;
    } catch (e) {
        const root = document.getElementById('approvals-content-root');
        if (root) {
            root.innerHTML = `<div class="card" style="color: var(--danger); text-align: center; padding: 2rem;">Error: ${escapeHtml(e.message)}</div>`;
        }
    }
}

async function approvePost(id) {
    try {
        const res = await authFetch(`/api/approvals/${id}/approve`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('Post approved successfully!', 'success');
            refreshActiveWorkflowView();
        } else {
            showToast(data.error || 'Failed to approve post', 'error');
        }
    } catch (e) {
        showToast('Approval error: ' + e.message, 'error');
    }
}

// ==========================================================================
// Phase 2: Publishing Queue & History View
// ==========================================================================

let queueFilterStatus = 'all';
let queueFilterChannel = 'all';
let cachedQueuePosts = [];

async function renderQueueView(container) {
    container.innerHTML = `
        <div class="calendar-toolbar">
            <div>
                <h3 style="margin: 0; font-size: 1.15rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-solid fa-list-check" style="color: #34d399;"></i> Publishing Queue &amp; History
                </h3>
                <small style="color: var(--text-secondary);">Filter and audit all queued, published, draft, and failed campaign posts.</small>
            </div>

            <div class="calendar-filters-group">
                <select id="q-filter-status" onchange="handleQueueFilterChange()">
                    <option value="all">All Statuses</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="publishing">Publishing (In Transit)</option>
                    <option value="published">Published</option>
                    <option value="pending_approval">Pending Approval</option>
                    <option value="draft">Draft</option>
                    <option value="failed">Failed</option>
                    <option value="cancelled">Cancelled</option>
                </select>
                <select id="q-filter-channel" onchange="handleQueueFilterChange()">
                    <option value="all">All Channels</option>
                    <option value="tour">Nexora Suite</option>
                    <option value="nz">Phoenix Intl</option>
                    <option value="gaatha">Gaatha AI</option>
                    <option value="insta">Instagram Sync</option>
                </select>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadQueueData()">
                    <i class="fa-solid fa-rotate"></i>
                </button>
            </div>
        </div>

        <div id="queue-content-root">
            <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
                <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>
                Loading queue entries...
            </div>
        </div>
    `;

    await loadQueueData();
}

async function loadQueueData() {
    try {
        const res = await authFetch('/api/schedule?limit=250');
        if (res.ok) {
            cachedQueuePosts = await res.json();
        } else {
            cachedQueuePosts = [];
        }
    } catch (e) {
        cachedQueuePosts = [];
    }
    renderQueueTable();
}

function handleQueueFilterChange() {
    queueFilterStatus = document.getElementById('q-filter-status')?.value || 'all';
    queueFilterChannel = document.getElementById('q-filter-channel')?.value || 'all';
    renderQueueTable();
}

function renderQueueTable() {
    const root = document.getElementById('queue-content-root');
    if (!root) return;

    let filtered = cachedQueuePosts.filter(p => {
        if (queueFilterStatus !== 'all' && p.status !== queueFilterStatus) return false;
        if (queueFilterChannel !== 'all' && p.post_type !== queueFilterChannel) return false;
        return true;
    });

    if (filtered.length === 0) {
        root.innerHTML = `
            <div class="card" style="text-align: center; padding: 3.5rem 1rem; color: var(--text-muted);">
                <i class="fa-solid fa-inbox" style="font-size: 2.5rem; opacity: 0.5; margin-bottom: 0.75rem; display: block;"></i>
                <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.25rem;">No posts match current queue filters</div>
                <p style="font-size: 0.85rem;">Try selecting a different status or channel filter above.</p>
            </div>
        `;
        return;
    }

    let html = `
        <div class="queue-table-wrap">
            <table class="queue-table">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Scheduled (Local)</th>
                        <th>Channel</th>
                        <th>Caption / Content</th>
                        <th>Media</th>
                        <th>Retries</th>
                        <th style="text-align: right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
    `;

    filtered.forEach(p => {
        html += `
            <tr>
                <td><span class="badge badge-${p.status}">${p.status}</span></td>
                <td>
                    <div style="font-weight: 600; font-size: 0.85rem;">${p.local_display || p.scheduled_for}</div>
                    <small style="color: var(--text-muted); font-size: 0.72rem;">UTC: ${p.scheduled_for}</small>
                </td>
                <td>
                    <span class="badge" style="background: var(--bg-app); border: 1px solid var(--border);">
                        ${CHANNEL_INFO[p.post_type]?.name || p.post_type}
                    </span>
                </td>
                <td style="max-width: 280px;">
                    <div class="text-truncate" style="font-size: 0.85rem;" title="${escapeHtml(p.message || '')}">
                        ${escapeHtml(p.message || '(No text caption)')}
                    </div>
                    ${p.status === 'failed' && p.error_message ? `
                        <div style="font-size: 0.75rem; color: #b91c1c; margin-top: 0.2rem; background: #fee2e2; padding: 2px 6px; border-radius: 4px;" class="text-truncate" title="${escapeHtml(p.error_message)}">
                            <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(p.error_message)}
                        </div>
                    ` : ''}
                </td>
                <td>
                    ${p.image_filename ? `
                        <span class="badge" style="background: var(--bg-app); border: 1px solid var(--border); font-size: 0.75rem;" title="${escapeHtml(p.image_filename)}">
                            <i class="fa-solid fa-paperclip"></i> Media
                        </span>
                    ` : '<span style="color: var(--text-muted); font-size: 0.75rem;">None</span>'}
                </td>
                <td>
                    ${p.retry_count > 0 ? `
                        <span class="badge ${p.status === 'failed' ? 'badge-failed' : 'badge-draft'}">${p.retry_count}/${p.max_retries || 3}</span>
                    ` : '<span style="color: var(--text-muted); font-size: 0.78rem;">0</span>'}
                </td>
                <td style="text-align: right; white-space: nowrap;">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id})">
                        <i class="fa-solid fa-eye"></i> Details
                    </button>
                    ${p.status === 'failed' ? `
                        <button type="button" class="btn btn-primary btn-sm" onclick="retryPostFromDetails(${p.id})" title="Retry publishing">
                            <i class="fa-solid fa-rotate-right"></i>
                        </button>
                    ` : ''}
                    ${['scheduled', 'draft'].includes(p.status) ? `
                        <button type="button" class="btn btn-secondary btn-sm" onclick="openRescheduleModal(${p.id})" title="Reschedule">
                            <i class="fa-solid fa-clock"></i>
                        </button>
                        <button type="button" class="btn btn-danger btn-sm" onclick="cancelPostFromDetails(${p.id})" title="Cancel">
                            <i class="fa-solid fa-ban"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    root.innerHTML = html;
}

/* ==========================================================================
   AI MARKETING STUDIO CLIENT ENGINE
   Brand-Aware Campaign Intelligence & Multi-Platform Generation
   ========================================================================== */

let studioBrands = [];
let studioSelectedBrandId = null;
let studioCampaigns = [];
let studioSelectedCampaignId = null;
let studioDrafts = [];
let studioBrandProfile = null;
let isGeneratingCopy = false;

async function renderAIStudioView(container) {
    if (!container) return;

    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading AI Marketing Studio...</p>
        </div>
    `;

    try {
        // 1. Fetch available brands
        const brandsRes = await authFetch('/api/brands');
        if (brandsRes.ok) {
            studioBrands = await brandsRes.json();
        } else {
            studioBrands = [];
        }

        if (studioBrands.length > 0 && !studioSelectedBrandId) {
            studioSelectedBrandId = studioBrands[0].id;
        }

        // 2. Fetch campaigns for active brand
        if (studioSelectedBrandId) {
            const campRes = await authFetch(`/api/campaigns?brand_id=${studioSelectedBrandId}`);
            if (campRes.ok) {
                studioCampaigns = await campRes.json();
            } else {
                studioCampaigns = [];
            }

            // 3. Fetch brand marketing profile
            const profRes = await authFetch(`/api/brands/${studioSelectedBrandId}/profile`);
            if (profRes.ok) {
                const profData = await profRes.json();
                studioBrandProfile = profData.profile || null;
            }
        }

        if (studioCampaigns.length > 0 && !studioSelectedCampaignId) {
            studioSelectedCampaignId = studioCampaigns[0].id;
        }

        // 4. Fetch drafts for active campaign
        if (studioSelectedCampaignId) {
            const draftsRes = await authFetch(`/api/campaigns/${studioSelectedCampaignId}/drafts`);
            if (draftsRes.ok) {
                studioDrafts = await draftsRes.json();
            } else {
                studioDrafts = [];
            }
        } else {
            studioDrafts = [];
        }

        renderAIStudioDOM(container);
    } catch (err) {
        console.error("Failed to render AI Marketing Studio:", err);
        container.innerHTML = `
            <div class="card" style="padding: 2rem; text-align: center;">
                <i class="fa-solid fa-triangle-exclamation fa-2x" style="color: var(--danger);"></i>
                <h3 style="margin-top: 0.5rem;">Could not load AI Marketing Studio</h3>
                <p style="color: var(--text-muted);">${escapeHtml(err.message || String(err))}</p>
                <button class="btn btn-primary" onclick="renderAIStudioView(document.getElementById('content-area'))" style="margin-top: 1rem;">Retry</button>
            </div>
        `;
    }
}

function renderAIStudioDOM(container) {
    const activeBrand = studioBrands.find(b => b.id === Number(studioSelectedBrandId)) || null;
    const activeCampaign = studioCampaigns.find(c => c.id === Number(studioSelectedCampaignId)) || null;

    let html = `
        <div class="studio-container">
            <!-- Studio Top Control Bar -->
            <div class="studio-header-card">
                <div class="studio-brand-selector-wrap">
                    <span style="font-weight: 700; font-size: 0.88rem; color: var(--text-muted); text-transform: uppercase;">Brand:</span>
                    <select id="studio-brand-select" class="form-control" style="min-width: 180px;" onchange="handleStudioBrandChange(this.value)">
                        ${studioBrands.map(b => `<option value="${b.id}" ${b.id === Number(studioSelectedBrandId) ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}
                    </select>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openBrandProfileModal()" title="View &amp; Edit Brand Marketing Profile">
                        <i class="fa-solid fa-id-badge" style="color: var(--primary);"></i> Brand Profile
                    </button>
                </div>

                <div class="studio-campaign-selector-wrap">
                    <span style="font-weight: 700; font-size: 0.88rem; color: var(--text-muted); text-transform: uppercase;">Campaign:</span>
                    <select id="studio-campaign-select" class="form-control" style="min-width: 220px;" onchange="handleStudioCampaignChange(this.value)">
                        ${studioCampaigns.length > 0
                            ? studioCampaigns.map(c => `<option value="${c.id}" ${c.id === Number(studioSelectedCampaignId) ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')
                            : `<option value="">No campaigns yet</option>`
                        }
                    </select>
                    <button type="button" class="btn btn-primary btn-sm" onclick="openNewCampaignModal()" title="Create New Marketing Campaign">
                        <i class="fa-solid fa-plus"></i> New Campaign
                    </button>
                </div>
            </div>
    `;

    // Active Campaign Brief or Empty Prompt
    if (activeCampaign) {
        html += `
            <div class="studio-brief-banner">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.75rem;">
                    <div>
                        <div class="studio-brief-title">
                            <i class="fa-solid fa-bullhorn" style="color: var(--primary);"></i>
                            <span>${escapeHtml(activeCampaign.name)}</span>
                            <span class="badge badge-success" style="font-size: 0.72rem; text-transform: capitalize;">${escapeHtml(activeCampaign.status || 'draft')}</span>
                        </div>
                        <p style="margin: 0; color: var(--text-secondary); font-size: 0.92rem; line-height: 1.5;">${escapeHtml(activeCampaign.brief)}</p>
                    </div>
                </div>

                <div class="studio-meta-chips" style="display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <span class="studio-chip"><i class="fa-solid fa-bullseye" style="color: #6366f1;"></i> Objective: <strong>${escapeHtml(activeCampaign.objective)}</strong></span>
                    ${activeCampaign.target_audience ? `<span class="studio-chip"><i class="fa-solid fa-users" style="color: #06b6d4;"></i> Audience: ${escapeHtml(activeCampaign.target_audience)}</span>` : ''}
                    ${activeCampaign.target_markets ? `<span class="studio-chip"><i class="fa-solid fa-earth-americas" style="color: #10b981;"></i> Markets: ${escapeHtml(activeCampaign.target_markets)}</span>` : ''}
                    <span class="studio-chip"><i class="fa-solid fa-language" style="color: #f59e0b;"></i> Lang: ${escapeHtml(activeCampaign.languages || 'en').toUpperCase()}</span>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openCampaignStrategyModal(${activeCampaign.id})" style="margin-left: auto;" title="View &amp; Generate AI Strategic Blueprint">
                        <i class="fa-solid fa-chess-knight" style="color: #6366f1;"></i> Strategy Blueprint
                    </button>
                    <button type="button" class="btn btn-primary btn-sm" onclick="openContentPlannerModal(${activeCampaign.id})" style="margin-left: 0.5rem;" title="Generate weekly/monthly content plan roadmap">
                        <i class="fa-solid fa-calendar-check"></i> Content Planner
                    </button>
                </div>
            </div>

            <!-- AI Generation Control Bar -->
            <div class="studio-generation-card">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h4 style="margin: 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-wand-magic-sparkles" style="color: #c084fc;"></i>
                            Multi-Platform AI Generation
                        </h4>
                        <p style="margin: 0.25rem 0 0 0; font-size: 0.82rem; color: var(--text-muted);">
                            Generates brand-aware marketing copy customized for each platform adhering to approved facts and tone.
                        </p>
                    </div>

                    <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                        <div style="display: flex; align-items: center; gap: 0.4rem;">
                            <label for="studio-provider-select" style="font-size: 0.82rem; color: var(--text-muted); font-weight: 600;">Provider:</label>
                            <select id="studio-provider-select" class="form-control" style="font-size: 0.85rem; padding: 0.35rem 0.65rem; width: auto;">
                                <option value="mock">Offline Mock (Deterministic / Fast)</option>
                                <option value="groq">Groq (Llama 3.3 70B Versatile)</option>
                                <option value="openai">OpenAI (GPT-4o Mini)</option>
                            </select>
                        </div>

                        <button id="studio-generate-btn" type="button" class="btn btn-primary" onclick="generateStudioCopy()" ${isGeneratingCopy ? 'disabled' : ''}>
                            ${isGeneratingCopy
                                ? `<i class="fa-solid fa-spinner fa-spin"></i> Generating Copy...`
                                : `<i class="fa-solid fa-sparkles"></i> Generate Copy`
                            }
                        </button>
                    </div>
                </div>

                <!-- Platform Selection Checkbox Pills -->
                <div class="studio-platform-selector-row">
                    <label class="platform-pill-toggle active">
                        <input type="checkbox" id="gen-plat-fb" value="facebook" checked>
                        <i class="fa-brands fa-facebook" style="color: #1877f2;"></i> Facebook
                    </label>
                    <label class="platform-pill-toggle active">
                        <input type="checkbox" id="gen-plat-ig" value="instagram" checked>
                        <i class="fa-brands fa-instagram" style="color: #db2777;"></i> Instagram
                    </label>
                    <label class="platform-pill-toggle active">
                        <input type="checkbox" id="gen-plat-li" value="linkedin" checked>
                        <i class="fa-brands fa-linkedin" style="color: #0284c7;"></i> LinkedIn
                    </label>
                    <label class="platform-pill-toggle active">
                        <input type="checkbox" id="gen-plat-x" value="x" checked>
                        <i class="fa-brands fa-x-twitter" style="color: #0f172a;"></i> X (Twitter)
                    </label>
                    <label class="platform-pill-toggle active">
                        <input type="checkbox" id="gen-plat-wa" value="whatsapp" checked>
                        <i class="fa-brands fa-whatsapp" style="color: #059669;"></i> WhatsApp Draft
                    </label>
                </div>
            </div>

            <!-- Drafts Review & In-Place Editor Grid -->
            <div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h3 style="font-size: 1.15rem; margin: 0; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-layer-group" style="color: var(--primary);"></i>
                        Generated Campaign Drafts
                        <span class="badge badge-secondary" style="font-size: 0.78rem;">${studioDrafts.length}</span>
                    </h3>
                </div>

                ${studioDrafts.length === 0 ? `
                    <div class="card" style="padding: 3rem 1rem; text-align: center; border: 2px dashed var(--border);">
                        <i class="fa-solid fa-file-pen fa-2x" style="color: var(--text-muted); margin-bottom: 0.5rem;"></i>
                        <h4 style="margin: 0; color: var(--text-primary);">No copy generated yet for this campaign</h4>
                        <p style="color: var(--text-muted); font-size: 0.88rem; max-width: 480px; margin: 0.5rem auto 1.25rem auto;">
                            Click the <strong>Generate Copy</strong> button above to create customized, brand-aligned marketing drafts for Facebook, Instagram, LinkedIn, X, and WhatsApp.
                        </p>
                        <button type="button" class="btn btn-primary btn-sm" onclick="generateStudioCopy()">
                            <i class="fa-solid fa-sparkles"></i> Generate First Drafts
                        </button>
                    </div>
                ` : `
                    <div class="studio-drafts-grid">
                        ${studioDrafts.map(d => renderStudioDraftCard(d)).join('')}
                    </div>
                `}
            </div>
        `;
    } else {
        html += `
            <div class="card" style="padding: 4rem 1.5rem; text-align: center; border: 2px dashed var(--border);">
                <i class="fa-solid fa-bullhorn fa-3x" style="color: var(--primary); margin-bottom: 1rem; opacity: 0.8;"></i>
                <h3 style="margin-bottom: 0.5rem;">Welcome to AI Marketing Studio</h3>
                <p style="color: var(--text-muted); max-width: 520px; margin: 0 auto 1.5rem auto; line-height: 1.5;">
                    PostPilot's Brand-Aware AI Marketing Studio creates high-converting, platform-specific copy anchored to your verified brand guidelines and product facts.
                </p>
                <button type="button" class="btn btn-primary" onclick="openNewCampaignModal()">
                    <i class="fa-solid fa-plus"></i> Create Your First Campaign
                </button>
            </div>
        `;
    }

    html += `</div>`;
    container.innerHTML = html;
}

function renderStudioDraftCard(draft) {
    const plat = (draft.target_platform || 'facebook').toLowerCase();
    const platIcons = {
        'facebook': 'fa-brands fa-facebook',
        'instagram': 'fa-brands fa-instagram',
        'linkedin': 'fa-brands fa-linkedin',
        'x': 'fa-brands fa-x-twitter',
        'whatsapp': 'fa-brands fa-whatsapp'
    };
    const platLabels = {
        'facebook': 'Facebook Post',
        'instagram': 'Instagram Caption',
        'linkedin': 'LinkedIn Post',
        'x': 'X (Twitter) Post',
        'whatsapp': 'WhatsApp Business Message'
    };

    return `
        <div class="studio-draft-card" id="draft-card-${draft.id}">
            <div class="studio-draft-header">
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                    <span class="platform-badge ${plat}">
                        <i class="${platIcons[plat] || 'fa-solid fa-share-nodes'}"></i>
                        ${platLabels[plat] || plat.toUpperCase()}
                    </span>
                    <span class="badge badge-secondary" style="font-size: 0.7rem; font-weight: 500;" id="draft-rev-badge-${draft.id}">
                        Rev #${draft.current_revision || 1}
                    </span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                    <button type="button" class="btn btn-outline-secondary btn-sm" style="padding: 0.15rem 0.4rem; font-size: 0.72rem;" onclick="viewDraftRevisions(${draft.id})" title="View revision history">
                        <i class="fa-solid fa-clock-rotate-left"></i> History
                    </button>
                    <span style="font-size: 0.72rem; color: var(--text-muted);">
                        ${escapeHtml(draft.ai_provider || 'ai')} · ${draft.created_at ? formatReadableDateTime(draft.created_at) : 'Draft'}
                    </span>
                </div>
            </div>

            ${plat === 'whatsapp' ? `
                <div class="whatsapp-notice-banner">
                    <i class="fa-solid fa-circle-info"></i>
                    <span><strong>Conversational Messaging Draft:</strong> For direct customer chat/broadcast, distinct from social status updates.</span>
                </div>
            ` : ''}

            <!-- Headline Editor -->
            <div>
                <label class="studio-card-field-label">Headline / Hook</label>
                <input type="text" id="draft-headline-${draft.id}" class="form-control" style="font-size: 0.88rem; font-weight: 600;" value="${escapeHtml(draft.headline || '')}">
            </div>

            <!-- Body / Caption Editor -->
            <div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                    <label class="studio-card-field-label" style="margin-bottom: 0;">Caption / Message Body</label>
                    <span id="draft-count-${draft.id}" style="font-size: 0.74rem; color: var(--text-muted);">${(draft.caption || '').length} chars</span>
                </div>
                <textarea 
                    id="draft-caption-${draft.id}" 
                    class="form-control" 
                    rows="5" 
                    style="font-size: 0.85rem; line-height: 1.45;" 
                    oninput="document.getElementById('draft-count-${draft.id}').textContent = this.value.length + ' chars'"
                >${escapeHtml(draft.caption || '')}</textarea>
            </div>

            <!-- Hashtags & CTA -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                <div>
                    <label class="studio-card-field-label">Hashtags</label>
                    <input type="text" id="draft-hashtags-${draft.id}" class="form-control" style="font-size: 0.8rem;" value="${escapeHtml(draft.hashtags || '')}" placeholder="#Tags">
                </div>
                <div>
                    <label class="studio-card-field-label">Call to Action</label>
                    <input type="text" id="draft-cta-${draft.id}" class="form-control" style="font-size: 0.8rem;" value="${escapeHtml(draft.call_to_action || '')}" placeholder="Next step">
                </div>
            </div>

            <!-- Validation Feedback Box -->
            <div id="draft-validation-box-${draft.id}" style="display: none; padding: 0.5rem 0.75rem; border-radius: var(--radius-md); font-size: 0.78rem;"></div>

            <!-- Action Controls -->
            <div class="studio-draft-actions">
                <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="saveStudioDraft(${draft.id})" title="Save manual edits to this draft">
                        <i class="fa-solid fa-floppy-disk"></i> Save
                    </button>
                    <button type="button" class="btn btn-outline-info btn-sm" onclick="validateStudioDraftCreative(${draft.id})" id="btn-val-${draft.id}" title="Run platform creative guidelines check">
                        <i class="fa-solid fa-check-double"></i> Validate
                    </button>
                    <button type="button" class="btn btn-outline-primary btn-sm" onclick="regenerateStudioDraft(${draft.id})" id="btn-regen-${draft.id}" title="Regenerate copy with AI (creates new revision)">
                        <i class="fa-solid fa-arrows-rotate"></i> Regenerate
                    </button>
                    <button type="button" class="btn btn-primary btn-sm" onclick="openScheduleDraftModal(${draft.id})" title="Schedule this verified draft directly">
                        <i class="fa-solid fa-calendar-check"></i> Schedule
                    </button>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteStudioDraft(${draft.id})" title="Delete draft">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        </div>
    `;
}

// Brand & Campaign Switchers
function handleStudioBrandChange(brandId) {
    studioSelectedBrandId = Number(brandId);
    studioSelectedCampaignId = null; // Reset campaign on brand change
    renderAIStudioView(document.getElementById('content-area'));
}

function handleStudioCampaignChange(campaignId) {
    studioSelectedCampaignId = Number(campaignId);
    renderAIStudioView(document.getElementById('content-area'));
}

// Brand Profile Modal Handling
async function openBrandProfileModal() {
    if (!studioSelectedBrandId) {
        showToast("Please select a brand workspace first.", "warning");
        return;
    }

    const modal = document.getElementById('brand-profile-modal');
    document.getElementById('profile-brand-id').value = studioSelectedBrandId;

    // Prefill if cached
    const p = studioBrandProfile || {};
    document.getElementById('profile-positioning').value = p.positioning || '';
    document.getElementById('profile-voice').value = p.voice_and_tone || '';
    document.getElementById('profile-guidelines').value = p.messaging_guidelines || '';
    document.getElementById('profile-approved-facts').value = p.approved_product_facts || '';
    document.getElementById('profile-prohibited-claims').value = p.prohibited_claims || '';
    document.getElementById('profile-ctas').value = p.preferred_ctas || '';
    document.getElementById('profile-audiences').value = p.target_audiences || '';
    document.getElementById('profile-markets').value = p.target_markets || '';

    modal.classList.add('active');
}

function closeBrandProfileModal() {
    const modal = document.getElementById('brand-profile-modal');
    if (modal) modal.classList.remove('active');
}

async function saveBrandProfileFromModal() {
    const brandId = document.getElementById('profile-brand-id').value;
    const payload = {
        positioning: document.getElementById('profile-positioning').value.trim(),
        voice_and_tone: document.getElementById('profile-voice').value.trim(),
        messaging_guidelines: document.getElementById('profile-guidelines').value.trim(),
        approved_product_facts: document.getElementById('profile-approved-facts').value.trim(),
        prohibited_claims: document.getElementById('profile-prohibited-claims').value.trim(),
        preferred_ctas: document.getElementById('profile-ctas').value.trim(),
        target_audiences: document.getElementById('profile-audiences').value.trim(),
        target_markets: document.getElementById('profile-markets').value.trim()
    };

    try {
        const res = await authFetch(`/api/brands/${brandId}/profile`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const data = await res.json();
            studioBrandProfile = data.profile;
            closeBrandProfileModal();
            showToast("Brand Marketing Profile updated successfully!", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to update profile", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// Campaign Modal Handling
function openNewCampaignModal() {
    const modal = document.getElementById('campaign-modal');
    const brandSelect = document.getElementById('modal-campaign-brand-id');
    brandSelect.innerHTML = studioBrands.map(b => `
        <option value="${b.id}" ${b.id === Number(studioSelectedBrandId) ? 'selected' : ''}>${escapeHtml(b.name)}</option>
    `).join('');

    document.getElementById('modal-campaign-id').value = '';
    document.getElementById('modal-campaign-name').value = '';
    document.getElementById('modal-campaign-objective').value = '';
    document.getElementById('modal-campaign-brief').value = '';
    document.getElementById('modal-campaign-audience').value = '';
    document.getElementById('modal-campaign-markets').value = '';

    modal.classList.add('active');
}

function closeCampaignModal() {
    const modal = document.getElementById('campaign-modal');
    if (modal) modal.classList.remove('active');
}

async function saveCampaignFromModal() {
    const brandId = document.getElementById('modal-campaign-brand-id').value;
    const name = document.getElementById('modal-campaign-name').value.trim();
    const objective = document.getElementById('modal-campaign-objective').value.trim();
    const brief = document.getElementById('modal-campaign-brief').value.trim();
    const campaignType = document.getElementById('modal-campaign-type').value;
    const audience = document.getElementById('modal-campaign-audience').value.trim();
    const markets = document.getElementById('modal-campaign-markets').value.trim();
    const languages = document.getElementById('modal-campaign-languages').value.trim();

    if (!name || !objective || !brief) {
        showToast("Please provide Campaign Name, Objective, and Brief.", "warning");
        return;
    }

    const payload = {
        brand_id: Number(brandId),
        name,
        objective,
        brief,
        campaign_type: campaignType,
        target_audience: audience,
        target_markets: markets,
        languages: languages || 'en'
    };

    try {
        const res = await authFetch('/api/campaigns', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const created = await res.json();
            closeCampaignModal();
            showToast("Marketing Campaign created successfully!", "success");
            studioSelectedBrandId = Number(brandId);
            studioSelectedCampaignId = created.id;
            renderAIStudioView(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to create campaign", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// =============================================================================
// Campaign Strategy Blueprint Handlers
// =============================================================================
const STRATEGY_SECTIONS = [
    'positioning', 'primary_objective', 'target_segments', 'pain_points',
    'value_proposition', 'core_message', 'supporting_messages', 'content_themes',
    'recommended_channels', 'calls_to_action', 'suggested_phases',
    'posting_frequency', 'success_metrics', 'risks_and_verification'
];

async function openCampaignStrategyModal(campaignId) {
    const cid = campaignId || studioSelectedCampaignId;
    if (!cid) {
        showToast("Please select a campaign first.", "warning");
        return;
    }
    document.getElementById('strategy-campaign-id').value = cid;
    const modal = document.getElementById('campaign-strategy-modal');
    if (modal) modal.classList.add('show');

    document.getElementById('strategy-loading-state').style.display = 'block';
    document.getElementById('strategy-empty-state').style.display = 'none';
    document.getElementById('strategy-content-state').style.display = 'none';
    document.getElementById('save-strategy-btn').style.display = 'none';

    try {
        const res = await authFetch(`/api/campaigns/${cid}/strategy`);
        document.getElementById('strategy-loading-state').style.display = 'none';
        if (res.ok) {
            const strat = await res.json();
            renderStrategyDataInModal(strat);
        } else if (res.status === 404) {
            document.getElementById('strategy-empty-state').style.display = 'block';
        } else {
            showToast("Failed to fetch strategy", "danger");
            document.getElementById('strategy-empty-state').style.display = 'block';
        }
    } catch (e) {
        document.getElementById('strategy-loading-state').style.display = 'none';
        document.getElementById('strategy-empty-state').style.display = 'block';
        showToast(e.message || "Failed to load strategy", "danger");
    }
}

function closeCampaignStrategyModal() {
    const modal = document.getElementById('campaign-strategy-modal');
    if (modal) modal.classList.remove('show');
}

function renderStrategyDataInModal(strat) {
    document.getElementById('strategy-empty-state').style.display = 'none';
    document.getElementById('strategy-content-state').style.display = 'block';
    document.getElementById('save-strategy-btn').style.display = 'inline-block';

    const lastUpdated = strat.updated_at || strat.created_at;
    if (lastUpdated) {
        document.getElementById('strategy-last-updated').textContent = `Blueprint updated: ${new Date(lastUpdated).toLocaleString()}`;
    }

    STRATEGY_SECTIONS.forEach(field => {
        const el = document.getElementById(`strat-${field}`);
        if (el) {
            el.value = strat[field] || '';
        }
    });
}

async function generateStrategyFromModal() {
    const cid = document.getElementById('strategy-campaign-id').value;
    if (!cid) return;

    document.getElementById('strategy-loading-state').style.display = 'block';
    document.getElementById('strategy-empty-state').style.display = 'none';
    document.getElementById('strategy-content-state').style.display = 'none';
    document.getElementById('save-strategy-btn').style.display = 'none';

    const provider = (document.getElementById('studio-provider-select') || {}).value || 'mock';

    try {
        const res = await authFetch(`/api/campaigns/${cid}/strategy`, {
            method: 'POST',
            body: JSON.stringify({ provider })
        });
        document.getElementById('strategy-loading-state').style.display = 'none';
        if (res.ok) {
            const data = await res.json();
            renderStrategyDataInModal(data.strategy);
            showToast("Strategic blueprint generated successfully!", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Strategy generation failed", "danger");
            document.getElementById('strategy-empty-state').style.display = 'block';
        }
    } catch (e) {
        document.getElementById('strategy-loading-state').style.display = 'none';
        document.getElementById('strategy-empty-state').style.display = 'block';
        showToast(e.message || "Network error", "danger");
    }
}

async function saveStrategyFromModal() {
    const cid = document.getElementById('strategy-campaign-id').value;
    if (!cid) return;

    const payload = {};
    STRATEGY_SECTIONS.forEach(field => {
        const el = document.getElementById(`strat-${field}`);
        if (el) {
            payload[field] = el.value.trim();
        }
    });

    try {
        const res = await authFetch(`/api/campaigns/${cid}/strategy`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const data = await res.json();
            renderStrategyDataInModal(data.strategy);
            showToast("Strategy updated and saved successfully!", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to update strategy", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// Generate Copy via AI Service
async function generateStudioCopy() {
    if (!studioSelectedCampaignId) {
        showToast("Please select or create a campaign first.", "warning");
        return;
    }

    const platforms = [];
    if (document.getElementById('gen-plat-fb')?.checked) platforms.push('facebook');
    if (document.getElementById('gen-plat-ig')?.checked) platforms.push('instagram');
    if (document.getElementById('gen-plat-li')?.checked) platforms.push('linkedin');
    if (document.getElementById('gen-plat-x')?.checked) platforms.push('x');
    if (document.getElementById('gen-plat-wa')?.checked) platforms.push('whatsapp');

    if (platforms.length === 0) {
        showToast("Please select at least one target social platform.", "warning");
        return;
    }

    const provider = document.getElementById('studio-provider-select')?.value || 'mock';

    isGeneratingCopy = true;
    const btn = document.getElementById('studio-generate-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generating Copy...`;
    }

    try {
        const res = await authFetch(`/api/campaigns/${studioSelectedCampaignId}/generate`, {
            method: 'POST',
            body: JSON.stringify({
                platforms,
                provider
            })
        });

        const data = await res.json();
        if (res.ok) {
            showToast(`✨ Generated ${data.drafts.length} brand-aware copy drafts!`, "success");
            // Prepend new drafts to studioDrafts without losing existing versions
            studioDrafts = [...(data.drafts || []), ...studioDrafts];
            renderAIStudioDOM(document.getElementById('content-area'));
        } else {
            showToast(data.error || "Content generation failed", "danger");
        }
    } catch (e) {
        showToast(e.message || "Generation network error", "danger");
    } finally {
        isGeneratingCopy = false;
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-sparkles"></i> Generate Copy`;
        }
    }
}

// Save Edited Draft
async function saveStudioDraft(draftId) {
    const draft = studioDrafts.find(d => d.id === draftId);
    const headline = document.getElementById(`draft-headline-${draftId}`)?.value.trim();
    const caption = document.getElementById(`draft-caption-${draftId}`)?.value.trim();
    const hashtags = document.getElementById(`draft-hashtags-${draftId}`)?.value.trim();
    const cta = document.getElementById(`draft-cta-${draftId}`)?.value.trim();

    if (!caption) {
        showToast("Caption cannot be empty.", "warning");
        return;
    }

    try {
        const res = await authFetch(`/api/drafts/${draftId}`, {
            method: 'PUT',
            body: JSON.stringify({
                headline,
                caption,
                hashtags,
                call_to_action: cta,
                expected_revision: draft ? (draft.current_revision || 1) : 1
            })
        });

        if (res.ok) {
            const updated = await res.json();
            const idx = studioDrafts.findIndex(d => d.id === draftId);
            if (idx !== -1) studioDrafts[idx] = updated;
            const revBadge = document.getElementById(`draft-rev-badge-${draftId}`);
            if (revBadge) revBadge.textContent = `Rev #${updated.current_revision || 1}`;
            showToast("Draft saved successfully!", "success");
        } else if (res.status === 409) {
            showToast("Conflict: Draft was modified by another session. Please refresh to load latest revision.", "warning");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to update draft", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// Regenerate Copy for a Draft (Appends as New Revision)
async function regenerateStudioDraft(draftId) {
    const draft = studioDrafts.find(d => d.id === draftId);
    const btn = document.getElementById(`btn-regen-${draftId}`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
    }

    try {
        const res = await authFetch(`/api/drafts/${draftId}/regenerate`, {
            method: 'POST',
            body: JSON.stringify({
                expected_revision: draft ? (draft.current_revision || 1) : 1
            })
        });

        if (res.ok) {
            const data = await res.json();
            const updated = data.draft;
            const idx = studioDrafts.findIndex(d => d.id === draftId);
            if (idx !== -1) studioDrafts[idx] = updated;

            const headlineEl = document.getElementById(`draft-headline-${draftId}`);
            if (headlineEl) headlineEl.value = updated.headline || '';
            const captionEl = document.getElementById(`draft-caption-${draftId}`);
            if (captionEl) {
                captionEl.value = updated.caption || '';
                const cnt = document.getElementById(`draft-count-${draftId}`);
                if (cnt) cnt.textContent = `${(updated.caption || '').length} chars`;
            }
            const tagsEl = document.getElementById(`draft-hashtags-${draftId}`);
            if (tagsEl) tagsEl.value = updated.hashtags || '';
            const ctaEl = document.getElementById(`draft-cta-${draftId}`);
            if (ctaEl) ctaEl.value = updated.call_to_action || '';
            const revBadge = document.getElementById(`draft-rev-badge-${draftId}`);
            if (revBadge) revBadge.textContent = `Rev #${updated.current_revision || 1}`;

            showToast(`✨ Regenerated copy! Created Rev #${updated.current_revision}.`, "success");
        } else if (res.status === 409) {
            showToast("Conflict: Draft was modified by another session. Please refresh.", "warning");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to regenerate copy", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-arrows-rotate"></i> Regenerate`;
        }
    }
}

// View Revision History
async function viewDraftRevisions(draftId) {
    try {
        const res = await authFetch(`/api/drafts/${draftId}/revisions`);
        if (!res.ok) {
            showToast("Failed to fetch revisions", "danger");
            return;
        }
        const data = await res.json();
        const revisions = data.revisions || [];
        if (revisions.length === 0) {
            showToast("No revisions recorded yet.", "info");
            return;
        }

        const listHtml = revisions.map(r => `
            <div style="border-bottom: 1px solid var(--border-color); padding: 0.6rem 0; display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                <div style="flex: 1; min-width: 0;">
                    <div style="font-weight: 600; font-size: 0.85rem;">Rev #${r.revision_number} <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">(${escapeHtml(r.change_source || 'manual')})</span></div>
                    <div style="font-size: 0.78rem; color: var(--text-secondary); margin: 0.2rem 0;">${escapeHtml(r.change_summary || '')}</div>
                    <div style="font-size: 0.72rem; color: var(--text-muted);">${formatReadableDateTime(r.created_at)}</div>
                    <div style="font-size: 0.8rem; background: var(--bg-tertiary); padding: 0.3rem 0.5rem; border-radius: 4px; margin-top: 0.3rem; max-height: 80px; overflow-y: auto; white-space: pre-wrap;">${escapeHtml(r.caption || '')}</div>
                </div>
                <div>
                    <button type="button" class="btn btn-outline-primary btn-sm" style="font-size: 0.75rem;" onclick="restoreRevision(${draftId}, ${r.revision_number})">
                        Restore
                    </button>
                </div>
            </div>
        `).join('');

        let revModal = document.getElementById('draft-revisions-modal');
        if (!revModal) {
            revModal = document.createElement('div');
            revModal.id = 'draft-revisions-modal';
            revModal.className = 'modal-backdrop';
            document.body.appendChild(revModal);
        }

        revModal.innerHTML = `
            <div class="modal-card" style="max-width: 600px; max-height: 85vh; display: flex; flex-direction: column;">
                <div class="modal-header">
                    <h3>Draft #${draftId} Revision History</h3>
                    <button type="button" class="modal-close" onclick="document.getElementById('draft-revisions-modal').classList.remove('active')">&times;</button>
                </div>
                <div class="modal-body" style="overflow-y: auto; flex: 1;">
                    ${listHtml}
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="document.getElementById('draft-revisions-modal').classList.remove('active')">Close</button>
                </div>
            </div>
        `;
        revModal.classList.add('active');
    } catch (e) {
        showToast(e.message || "Failed to load revisions", "danger");
    }
}

// Restore a Specific Revision
async function restoreRevision(draftId, revNum) {
    if (!confirm(`Restore content from Revision #${revNum}? This creates a new revision with that content.`)) return;

    try {
        const res = await authFetch(`/api/drafts/${draftId}/revisions/${revNum}/restore`, {
            method: 'POST'
        });

        if (res.ok) {
            const data = await res.json();
            const updated = data.draft;
            const idx = studioDrafts.findIndex(d => d.id === draftId);
            if (idx !== -1) studioDrafts[idx] = updated;

            const headlineEl = document.getElementById(`draft-headline-${draftId}`);
            if (headlineEl) headlineEl.value = updated.headline || '';
            const captionEl = document.getElementById(`draft-caption-${draftId}`);
            if (captionEl) {
                captionEl.value = updated.caption || '';
                const cnt = document.getElementById(`draft-count-${draftId}`);
                if (cnt) cnt.textContent = `${(updated.caption || '').length} chars`;
            }
            const tagsEl = document.getElementById(`draft-hashtags-${draftId}`);
            if (tagsEl) tagsEl.value = updated.hashtags || '';
            const ctaEl = document.getElementById(`draft-cta-${draftId}`);
            if (ctaEl) ctaEl.value = updated.call_to_action || '';
            const revBadge = document.getElementById(`draft-rev-badge-${draftId}`);
            if (revBadge) revBadge.textContent = `Rev #${updated.current_revision || 1}`;

            const revModal = document.getElementById('draft-revisions-modal');
            if (revModal) revModal.classList.remove('active');

            showToast(`Restored content from Rev #${revNum} as Rev #${updated.current_revision}!`, "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to restore revision", "danger");
        }
    } catch (e) {
        showToast(e.message || "Restore network error", "danger");
    }
}

// Delete Draft
async function deleteStudioDraft(draftId) {
    if (!confirm("Are you sure you want to delete this draft?")) return;

    try {
        const res = await authFetch(`/api/drafts/${draftId}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            studioDrafts = studioDrafts.filter(d => d.id !== draftId);
            const el = document.getElementById(`draft-card-${draftId}`);
            if (el) el.remove();
            showToast("Draft deleted.", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to delete draft", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// Schedule Draft -> Opens Composer Modal
function scheduleStudioDraft(draftId) {
    const draft = studioDrafts.find(d => d.id === draftId);
    if (!draft) return;

    // Combine caption and hashtags for the composer
    let text = draft.caption || '';
    if (draft.hashtags) {
        text += `\n\n${draft.hashtags}`;
    }

    openModal('add');
    const msgEl = document.getElementById('post-message');
    if (msgEl) {
        msgEl.value = text;
        if (typeof handleCaptionInput === 'function') {
            handleCaptionInput(text);
        }
    }

    showToast("Draft loaded into Composer. Choose media and schedule time!", "info");
}

// ==========================================================================
// VIEW: Brand Workspaces (Unit L)
// ==========================================================================
async function renderBrands(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Brand Workspaces...</p>
        </div>
    `;

    try {
        const res = await authFetch('/api/brands');
        const brands = res.ok ? await res.json() : [];

        let html = `
            <div class="brands-view-container">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                            <i class="fa-solid fa-building-flag" style="color: #6366f1;"></i> Brand Workspaces
                        </h2>
                        <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                            Isolated marketing workspaces with distinct positioning, guardrails, campaigns, and audiences.
                        </p>
                    </div>
                </div>

                <div class="brands-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.25rem;">
        `;

        if (brands.length === 0) {
            html += `
                <div class="card" style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem;">
                    <i class="fa-solid fa-building-circle-exclamation fa-3x" style="color: var(--text-muted); opacity: 0.5;"></i>
                    <h3 style="margin-top: 1rem;">No Brands Found</h3>
                    <p style="color: var(--text-muted);">No brand workspaces configured for your organization.</p>
                </div>
            `;
        } else {
            brands.forEach(b => {
                html += `
                    <div class="card brand-card" style="display: flex; flex-direction: column; justify-content: space-between; gap: 1rem; padding: 1.25rem;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
                                <div style="font-weight: 700; font-size: 1.1rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
                                    <div class="brand-avatar-pill" style="width: 32px; height: 32px; border-radius: 8px; background: #6366f1; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.9rem;">
                                        ${escapeHtml((b.name || 'B')[0].toUpperCase())}
                                    </div>
                                    <span>${escapeHtml(b.name)}</span>
                                </div>
                                <span class="badge badge-secondary" style="font-size: 0.72rem;">${escapeHtml(b.slug || 'brand')}</span>
                            </div>

                            <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45; margin-bottom: 0.75rem;">
                                ${escapeHtml(b.description || 'Global brand marketing workspace under GAATHA / PostPilot.')}
                            </p>

                            <div style="display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.78rem; color: var(--text-muted); background: var(--bg-surface); padding: 0.6rem 0.8rem; border-radius: var(--radius-md); border: 1px solid var(--border);">
                                <div><i class="fa-solid fa-globe" style="width: 16px;"></i> ${escapeHtml(b.website || 'No website set')}</div>
                                <div><i class="fa-solid fa-users" style="width: 16px;"></i> ${escapeHtml(b.target_audience || 'Universal audiences')}</div>
                                <div><i class="fa-solid fa-earth-americas" style="width: 16px;"></i> ${escapeHtml(b.target_markets || 'Global')}</div>
                            </div>
                        </div>

                        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; pt: 0.5rem; border-top: 1px solid var(--border);">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="openBrandProfileModal(${b.id})" title="Edit brand positioning and factual guardrails">
                                <i class="fa-solid fa-id-card" style="color: var(--primary);"></i> Profile
                            </button>
                            <button type="button" class="btn btn-primary btn-sm" onclick="switchToStudioWithBrand(${b.id})" title="Open brand in AI Marketing Studio">
                                <i class="fa-solid fa-wand-magic-sparkles"></i> AI Studio
                            </button>
                            <button type="button" class="btn btn-outline-secondary btn-sm" onclick="switchToCampaignsWithBrand(${b.id})" title="View brand campaigns">
                                <i class="fa-solid fa-bullhorn"></i> Campaigns
                            </button>
                        </div>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load brand workspaces: ${escapeHtml(e.message)}</div>`;
    }
}

function switchToStudioWithBrand(brandId) {
    studioSelectedBrandId = Number(brandId);
    studioSelectedCampaignId = null;
    loadTab('studio');
}

function switchToCampaignsWithBrand(brandId) {
    campaignsFilterBrandId = Number(brandId);
    loadTab('campaigns');
}

function switchToStudioWithCampaign(brandId, campaignId) {
    studioSelectedBrandId = Number(brandId);
    studioSelectedCampaignId = Number(campaignId);
    loadTab('studio');
}

// ==========================================================================
// VIEW: Campaigns Management (Unit L)
// ==========================================================================
let campaignsFilterBrandId = null;
let campaignsFilterStatus = 'all';

async function renderCampaigns(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Marketing Campaigns...</p>
        </div>
    `;

    try {
        const [brandsRes, campsRes] = await Promise.all([
            authFetch('/api/brands'),
            authFetch(campaignsFilterBrandId ? `/api/campaigns?brand_id=${campaignsFilterBrandId}` : '/api/campaigns')
        ]);

        const brands = brandsRes.ok ? await brandsRes.json() : [];
        let campaigns = campsRes.ok ? await campsRes.json() : [];

        if (campaignsFilterStatus !== 'all') {
            campaigns = campaigns.filter(c => (c.status || 'draft') === campaignsFilterStatus);
        }

        let html = `
            <div class="campaigns-view-container">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                            <i class="fa-solid fa-bullhorn" style="color: #f59e0b;"></i> Marketing Campaigns
                        </h2>
                        <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                            Orchestrate multi-brand initiatives, AI strategic blueprints, and publishing cadences.
                        </p>
                    </div>
                    <button type="button" class="btn btn-primary" onclick="openNewCampaignModal()">
                        <i class="fa-solid fa-plus"></i> New Campaign
                    </button>
                </div>

                <!-- Filters Bar -->
                <div class="card" style="padding: 0.85rem 1rem; margin-bottom: 1.25rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                        <div style="display: flex; align-items: center; gap: 0.4rem;">
                            <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Brand:</label>
                            <select class="form-control" style="width: auto; font-size: 0.85rem;" onchange="campaignsFilterBrandId = this.value ? Number(this.value) : null; renderCampaigns(document.getElementById('content-area'))">
                                <option value="">All Brands</option>
                                ${brands.map(b => `<option value="${b.id}" ${b.id === campaignsFilterBrandId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}
                            </select>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.4rem;">
                            <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Status:</label>
                            <select class="form-control" style="width: auto; font-size: 0.85rem;" onchange="campaignsFilterStatus = this.value; renderCampaigns(document.getElementById('content-area'))">
                                <option value="all" ${campaignsFilterStatus === 'all' ? 'selected' : ''}>All Statuses</option>
                                <option value="draft" ${campaignsFilterStatus === 'draft' ? 'selected' : ''}>Draft</option>
                                <option value="active" ${campaignsFilterStatus === 'active' ? 'selected' : ''}>Active</option>
                                <option value="paused" ${campaignsFilterStatus === 'paused' ? 'selected' : ''}>Paused</option>
                                <option value="completed" ${campaignsFilterStatus === 'completed' ? 'selected' : ''}>Completed</option>
                                <option value="archived" ${campaignsFilterStatus === 'archived' ? 'selected' : ''}>Archived</option>
                            </select>
                        </div>
                    </div>
                    <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: 600;">${campaigns.length} Campaigns</span>
                </div>

                <div class="campaigns-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 1.25rem;">
        `;

        if (campaigns.length === 0) {
            html += `
                <div class="card" style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem;">
                    <i class="fa-solid fa-bullhorn fa-3x" style="color: var(--text-muted); opacity: 0.5;"></i>
                    <h3 style="margin-top: 1rem;">No Campaigns Match Criteria</h3>
                    <p style="color: var(--text-muted);">Create your first campaign or adjust brand/status filters above.</p>
                </div>
            `;
        } else {
            campaigns.forEach(c => {
                const brand = brands.find(b => b.id === c.brand_id);
                const brandName = brand ? brand.name : `Brand #${c.brand_id}`;
                const statusBadge = c.status === 'active' ? 'badge-success' : (c.status === 'completed' ? 'badge-info' : 'badge-secondary');

                html += `
                    <div class="card campaign-card" style="display: flex; flex-direction: column; justify-content: space-between; gap: 0.85rem; padding: 1.25rem;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                                <div>
                                    <span class="badge" style="background: rgba(99, 102, 241, 0.1); color: #6366f1; font-size: 0.7rem; font-weight: 700; margin-bottom: 0.25rem; display: inline-block;">
                                        ${escapeHtml(brandName)}
                                    </span>
                                    <h3 style="margin: 0; font-size: 1.05rem; font-weight: 700;">${escapeHtml(c.name)}</h3>
                                </div>
                                <span class="badge ${statusBadge}" style="text-transform: capitalize; font-size: 0.72rem;">${escapeHtml(c.status || 'draft')}</span>
                            </div>

                            <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45; margin-bottom: 0.6rem;">
                                ${escapeHtml(c.brief || 'No campaign brief supplied.')}
                            </p>

                            <div style="display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.76rem; color: var(--text-muted); background: var(--bg-surface); padding: 0.5rem 0.75rem; border-radius: var(--radius-md); border: 1px solid var(--border);">
                                <div><strong>Objective:</strong> ${escapeHtml(c.objective || 'Brand Awareness')}</div>
                                <div><strong>Audience:</strong> ${escapeHtml(c.target_audience || 'Universal')}</div>
                                <div><strong>Markets:</strong> ${escapeHtml(c.target_markets || 'Global')}</div>
                            </div>
                        </div>

                        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; pt: 0.5rem; border-top: 1px solid var(--border);">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="openCampaignStrategyModal(${c.id})" title="View/generate AI strategy roadmap">
                                <i class="fa-solid fa-chess-knight" style="color: #6366f1;"></i> Strategy
                            </button>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="openContentPlannerModal(${c.id})" title="Intelligent weekly/monthly content planner">
                                <i class="fa-solid fa-calendar-check" style="color: #10b981;"></i> Planner
                            </button>
                            <button type="button" class="btn btn-primary btn-sm" onclick="switchToStudioWithCampaign(${c.brand_id}, ${c.id})" title="Open campaign in AI Marketing Studio">
                                <i class="fa-solid fa-wand-magic-sparkles"></i> AI Studio
                            </button>
                        </div>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load campaigns: ${escapeHtml(e.message)}</div>`;
    }
}

// ==========================================================================
// VIEW: Media Library (Unit L)
// ==========================================================================
let mediaFilterBrandId = null;

async function renderMedia(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Media Library Assets...</p>
        </div>
    `;

    try {
        const [brandsRes, mediaRes] = await Promise.all([
            authFetch('/api/brands'),
            authFetch(mediaFilterBrandId ? `/api/media?brand_id=${mediaFilterBrandId}` : '/api/media')
        ]);

        const brands = brandsRes.ok ? await brandsRes.json() : [];
        const mediaAssets = mediaRes.ok ? await mediaRes.json() : [];

        let html = `
            <div class="media-view-container">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                            <i class="fa-solid fa-photo-film" style="color: #ec4899;"></i> Brand Media Library
                        </h2>
                        <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                            Secure multi-tenant asset storage for brand creative graphics, photography, and video.
                        </p>
                    </div>
                </div>

                <!-- Media Upload Dropzone Card -->
                <div class="card" style="padding: 1.25rem; margin-bottom: 1.5rem; background: var(--bg-surface); border: 2px dashed var(--border);">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                        <div style="display: flex; align-items: center; gap: 0.75rem;">
                            <i class="fa-solid fa-cloud-arrow-up fa-2x" style="color: var(--primary);"></i>
                            <div>
                                <h4 style="margin: 0; font-size: 0.95rem;">Upload Creative Media Asset</h4>
                                <small style="color: var(--text-muted);">PNG, JPG, WEBP, GIF, MP4 (Max 16 MB)</small>
                            </div>
                        </div>

                        <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                            <select id="media-upload-brand-select" class="form-control" style="font-size: 0.85rem; width: auto;">
                                <option value="">Global / Org-wide Asset</option>
                                ${brands.map(b => `<option value="${b.id}" ${b.id === mediaFilterBrandId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}
                            </select>
                            <input type="file" id="media-upload-file-input" style="display: none;" accept="image/*,video/*" onchange="handleMediaUpload(this)">
                            <button type="button" class="btn btn-primary" onclick="document.getElementById('media-upload-file-input').click()">
                                <i class="fa-solid fa-upload"></i> Choose File
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Media Filter Bar -->
                <div class="card" style="padding: 0.75rem 1rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Filter by Brand:</label>
                        <select class="form-control" style="font-size: 0.85rem; width: auto;" onchange="mediaFilterBrandId = this.value ? Number(this.value) : null; renderMedia(document.getElementById('content-area'))">
                            <option value="">All Brand Assets</option>
                            ${brands.map(b => `<option value="${b.id}" ${b.id === mediaFilterBrandId ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('')}
                        </select>
                    </div>
                    <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: 600;">${mediaAssets.length} Assets Stored</span>
                </div>

                <!-- Assets Grid -->
                <div class="media-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1.25rem;">
        `;

        if (mediaAssets.length === 0) {
            html += `
                <div class="card" style="grid-column: 1 / -1; text-align: center; padding: 3rem 1rem;">
                    <i class="fa-solid fa-photo-film fa-3x" style="color: var(--text-muted); opacity: 0.5;"></i>
                    <h3 style="margin-top: 1rem;">No Media Assets</h3>
                    <p style="color: var(--text-muted);">Upload graphics, banners, or video to build your brand media library.</p>
                </div>
            `;
        } else {
            mediaAssets.forEach(m => {
                const brand = brands.find(b => b.id === m.brand_id);
                const brandName = brand ? brand.name : 'Global';
                const sizeKb = m.file_size ? (m.file_size / 1024).toFixed(0) + ' KB' : '';

                html += `
                    <div class="card media-asset-card" style="overflow: hidden; padding: 0; display: flex; flex-direction: column;">
                        <div style="height: 150px; background: #0f172a; display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative;">
                            ${m.file_url ? `<img src="${escapeHtml(m.file_url)}" alt="${escapeHtml(m.original_filename)}" style="width: 100%; height: 100%; object-fit: cover;">` : `<i class="fa-regular fa-image fa-2x" style="color: #64748b;"></i>`}
                            <span class="badge" style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: #fff; font-size: 0.65rem;">
                                ${escapeHtml(brandName)}
                            </span>
                        </div>
                        <div style="padding: 0.85rem; flex: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 0.5rem;">
                            <div>
                                <div style="font-weight: 600; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(m.original_filename)}">
                                    ${escapeHtml(m.original_filename)}
                                </div>
                                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">
                                    ${sizeKb} · ${escapeHtml(m.content_type || 'image')}
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; pt: 0.4rem; border-top: 1px solid var(--border);">
                                <small style="font-size: 0.7rem; color: var(--text-muted);">${formatReadableDateTime(m.created_at)}</small>
                                <button type="button" class="btn btn-outline-danger btn-sm" style="padding: 0.15rem 0.4rem; font-size: 0.72rem;" onclick="deleteMediaAsset(${m.id})" title="Delete asset">
                                    <i class="fa-solid fa-trash-can"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load media assets: ${escapeHtml(e.message)}</div>`;
    }
}

async function handleMediaUpload(input) {
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    const brandSelect = document.getElementById('media-upload-brand-select');
    const brandId = brandSelect ? brandSelect.value : null;

    const formData = new FormData();
    formData.append('file', file);
    if (brandId) {
        formData.append('brand_id', brandId);
    }

    showToast("Uploading media asset...", "info");
    try {
        const res = await authFetch('/api/media/upload', {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            showToast("Media asset uploaded successfully!", "success");
            input.value = '';
            renderMedia(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Upload failed", "danger");
        }
    } catch (e) {
        showToast(e.message || "Upload network error", "danger");
    }
}

async function deleteMediaAsset(assetId) {
    if (!confirm("Are you sure you want to permanently delete this media asset?")) return;
    try {
        const res = await authFetch(`/api/media/${assetId}`, { method: 'DELETE' });
        if (res.ok) {
            showToast("Media asset deleted.", "success");
            renderMedia(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to delete asset", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// ==========================================================================
// VIEW: Publishing History (Unit L)
// ==========================================================================
let historyFilterChannel = 'all';

async function renderHistory(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Publishing History...</p>
        </div>
    `;

    try {
        const res = await authFetch('/api/posts');
        const allPosts = res.ok ? await res.json() : [];

        // Completed / Published / Failed posts
        let historyPosts = allPosts.filter(p => ['published', 'failed', 'rejected'].includes(p.status) || p.completed_at);
        if (historyFilterChannel !== 'all') {
            historyPosts = historyPosts.filter(p => p.type === historyFilterChannel);
        }

        let html = `
            <div class="history-view-container">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                            <i class="fa-solid fa-clock-rotate-left" style="color: #94a3b8;"></i> Publishing History &amp; Audit Trail
                        </h2>
                        <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                            Full record of executed dispatches, social live post IDs, and lifecycle diagnostics.
                        </p>
                    </div>
                </div>

                <!-- Filters -->
                <div class="card" style="padding: 0.75rem 1rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Channel:</label>
                        <select class="form-control" style="font-size: 0.85rem; width: auto;" onchange="historyFilterChannel = this.value; renderHistory(document.getElementById('content-area'))">
                            <option value="all" ${historyFilterChannel === 'all' ? 'selected' : ''}>All Channels</option>
                            <option value="tour" ${historyFilterChannel === 'tour' ? 'selected' : ''}>Nexora Suite</option>
                            <option value="nz" ${historyFilterChannel === 'nz' ? 'selected' : ''}>Phoenix Intl</option>
                            <option value="gaatha" ${historyFilterChannel === 'gaatha' ? 'selected' : ''}>Gaatha AI</option>
                            <option value="insta" ${historyFilterChannel === 'insta' ? 'selected' : ''}>Instagram Sync</option>
                        </select>
                    </div>
                    <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: 600;">${historyPosts.length} Records</span>
                </div>

                <div class="card" style="overflow-x: auto; padding: 0;">
                    <table class="data-table" style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: var(--bg-surface); border-bottom: 1px solid var(--border);">
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">ID</th>
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Channel</th>
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Caption Excerpt</th>
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Media</th>
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Status</th>
                                <th style="padding: 0.75rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Execution Time</th>
                                <th style="padding: 0.75rem 1rem; text-align: right; font-size: 0.75rem; text-transform: uppercase;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        if (historyPosts.length === 0) {
            html += `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
                        No publishing history recorded yet.
                    </td>
                </tr>
            `;
        } else {
            historyPosts.forEach(p => {
                const info = CHANNEL_INFO[p.type] || { name: p.type || 'Channel', icon: 'fa-share-nodes' };
                const isPublished = p.status === 'published';
                const statusBadge = isPublished ? 'badge-success' : 'badge-danger';

                html += `
                    <tr style="border-bottom: 1px solid var(--border);">
                        <td style="padding: 0.75rem 1rem; font-weight: 700; font-size: 0.82rem;">#${p.id}</td>
                        <td style="padding: 0.75rem 1rem;">
                            <span style="font-weight: 600; font-size: 0.85rem;"><i class="fa-solid ${info.icon}"></i> ${escapeHtml(info.name)}</span>
                        </td>
                        <td style="padding: 0.75rem 1rem; max-width: 300px;">
                            <div style="font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${escapeHtml(p.message || 'No caption')}
                            </div>
                        </td>
                        <td style="padding: 0.75rem 1rem; font-size: 0.82rem;">
                            ${p.image_filename ? `<i class="fa-regular fa-image" style="color: var(--primary);"></i> Attached` : `<span style="color: var(--text-muted);">Text only</span>`}
                        </td>
                        <td style="padding: 0.75rem 1rem;">
                            <span class="badge ${statusBadge}" style="text-transform: capitalize; font-size: 0.72rem;">${escapeHtml(p.status)}</span>
                        </td>
                        <td style="padding: 0.75rem 1rem; font-size: 0.8rem; color: var(--text-muted);">
                            ${formatReadableDateTime(p.completed_at || p.scheduled_time)}
                        </td>
                        <td style="padding: 0.75rem 1rem; text-align: right;">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="openDetailsModal(${p.id})">
                                <i class="fa-solid fa-eye"></i> Details
                            </button>
                        </td>
                    </tr>
                `;
            });
        }

        html += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load history: ${escapeHtml(e.message)}</div>`;
    }
}

// ==========================================================================
// VIEW: Analytics Dashboard (Unit L)
// ==========================================================================
async function renderAnalytics(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Aggregating Marketing &amp; AI Intelligence Dashboard...</p>
        </div>
    `;

    try {
        const [dashRes, usageRes] = await Promise.all([
            authFetch('/api/analytics/dashboard'),
            authFetch('/api/analytics/ai-usage')
        ]);

        const dash = dashRes.ok ? await dashRes.json() : {};
        const usage = usageRes.ok ? await usageRes.json() : {};

        const totalCampaigns = dash.total_campaigns || 0;
        const totalDrafts = dash.total_drafts || 0;
        const scheduledCount = dash.scheduled_posts || 0;
        const successRate = dash.publishing_success_rate !== undefined ? `${dash.publishing_success_rate}%` : '100%';
        const totalTokens = usage.total_tokens ? usage.total_tokens.toLocaleString() : (dash.tokens_consumed ? dash.tokens_consumed.toLocaleString() : '0');
        const totalCost = usage.total_estimated_cost_usd !== undefined ? `$${Number(usage.total_estimated_cost_usd).toFixed(4)}` : '$0.0000';

        const funnel = dash.draft_lifecycle_breakdown || {};
        const platforms = dash.platform_distribution || {};

        let html = `
            <div class="analytics-view-container">
                <div style="margin-bottom: 1.5rem;">
                    <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                        <i class="fa-solid fa-chart-line" style="color: #10b981;"></i> Marketing &amp; AI Intelligence Dashboard
                    </h2>
                    <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                        Real-time analytics for multi-brand initiatives, AI token consumption, publishing velocity, and platform distribution.
                    </p>
                </div>

                <!-- 6 KPI Metric Cards -->
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(99, 102, 241, 0.1); color: #6366f1;">
                            <i class="fa-solid fa-bullhorn"></i>
                        </div>
                        <div class="stat-info">
                            <h4>Active Campaigns</h4>
                            <p>${totalCampaigns}</p>
                            <small>Orchestrated brands</small>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(192, 132, 252, 0.1); color: #c084fc;">
                            <i class="fa-solid fa-file-lines"></i>
                        </div>
                        <div class="stat-info">
                            <h4>Content Drafts</h4>
                            <p>${totalDrafts}</p>
                            <small>Across all channels</small>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(16, 185, 129, 0.1); color: #10b981;">
                            <i class="fa-solid fa-calendar-check"></i>
                        </div>
                        <div class="stat-info">
                            <h4>Publishing Queue</h4>
                            <p>${scheduledCount}</p>
                            <small>Scheduled dispatches</small>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(56, 189, 248, 0.1); color: #0284c7;">
                            <i class="fa-solid fa-circle-check"></i>
                        </div>
                        <div class="stat-info">
                            <h4>Success Rate</h4>
                            <p>${successRate}</p>
                            <small>Publishing reliability</small>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(245, 158, 11, 0.1); color: #f59e0b;">
                            <i class="fa-solid fa-microchip"></i>
                        </div>
                        <div class="stat-info">
                            <h4>AI Tokens</h4>
                            <p>${totalTokens}</p>
                            <small>Consumed this cycle</small>
                        </div>
                    </div>

                    <div class="stat-card">
                        <div class="stat-icon" style="background: rgba(236, 72, 153, 0.1); color: #ec4899;">
                            <i class="fa-solid fa-receipt"></i>
                        </div>
                        <div class="stat-info">
                            <h4>Compute Cost</h4>
                            <p>${totalCost}</p>
                            <small>Estimated USD</small>
                        </div>
                    </div>
                </div>

                <!-- Intelligence Grids -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 1.25rem;">
                    <!-- Draft Funnel Card -->
                    <div class="card" style="padding: 1.25rem;">
                        <h4 style="margin: 0 0 1rem 0; font-size: 1rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-filter" style="color: var(--primary);"></i> Content Lifecycle Funnel
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Drafting &amp; Generation</span>
                                    <span style="font-weight: 700;">${funnel.draft || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.draft || 0) / Math.max(1, totalDrafts)) * 100)}%; background: #94a3b8; height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Pending Approval</span>
                                    <span style="font-weight: 700;">${funnel.pending_approval || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.pending_approval || 0) / Math.max(1, totalDrafts)) * 100)}%; background: #fbbf24; height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Approved</span>
                                    <span style="font-weight: 700;">${funnel.approved || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.approved || 0) / Math.max(1, totalDrafts)) * 100)}%; background: #34d399; height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Scheduled &amp; Queued</span>
                                    <span style="font-weight: 700;">${funnel.scheduled || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.scheduled || 0) / Math.max(1, totalDrafts)) * 100)}%; background: #60a5fa; height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Published Dispatches</span>
                                    <span style="font-weight: 700;">${funnel.published || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.published || 0) / Math.max(1, totalDrafts)) * 100)}%; background: #10b981; height: 100%;"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Platform Share Card -->
                    <div class="card" style="padding: 1.25rem;">
                        <h4 style="margin: 0 0 1rem 0; font-size: 1rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-share-nodes" style="color: #ec4899;"></i> Platform Distribution
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 0.65rem;">
                            ${Object.keys(platforms).length === 0 ? `<p style="color: var(--text-muted); font-size: 0.85rem;">No platform copies generated yet.</p>` : ''}
                            ${Object.entries(platforms).map(([plat, count]) => `
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.45rem 0.6rem; background: var(--bg-surface); border-radius: var(--radius-md); border: 1px solid var(--border);">
                                    <span style="font-weight: 600; font-size: 0.85rem; text-transform: capitalize;">${escapeHtml(plat)}</span>
                                    <span class="badge badge-secondary">${count} Drafts</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load analytics: ${escapeHtml(e.message)}</div>`;
    }
}

// ==========================================================================
// VIEW: Organization Settings & SaaS Subscriptions (Unit L)
// ==========================================================================
async function renderSettings(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Organization &amp; Subscription Settings...</p>
        </div>
    `;

    try {
        const [orgRes, membersRes, subRes] = await Promise.all([
            authFetch('/api/org/settings'),
            authFetch('/api/org/members'),
            authFetch('/api/saas/subscription')
        ]);

        const org = orgRes.ok ? await orgRes.json() : {};
        const members = membersRes.ok ? (await membersRes.json()).members || [] : [];
        const sub = subRes.ok ? (await subRes.json()).subscription || {} : {};

        const planName = (sub.plan_name || sub.plan_id || 'Enterprise').toUpperCase();
        const tokensLimit = sub.max_ai_tokens_per_month || 2000000;
        const tokensUsed = sub.tokens_used_this_month || 0;
        const tokensPct = Math.min(100, Math.round((tokensUsed / Math.max(1, tokensLimit)) * 100));

        const campsLimit = sub.max_campaigns || 500;
        const campsUsed = sub.campaigns_count || 1;
        const campsPct = Math.min(100, Math.round((campsUsed / Math.max(1, campsLimit)) * 100));

        let html = `
            <div class="settings-view-container">
                <div style="margin-bottom: 1.5rem;">
                    <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800;">
                        <i class="fa-solid fa-gear" style="color: #64748b;"></i> Organization &amp; SaaS Settings
                    </h2>
                    <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                        Workspace identity, team permission roles, and commercial subscription limits.
                    </p>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1.25rem; margin-bottom: 1.5rem;">
                    <!-- Org Profile Card -->
                    <div class="card" style="padding: 1.25rem;">
                        <h4 style="margin: 0 0 1rem 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-building" style="color: var(--primary);"></i> Organization Identity
                        </h4>
                        <form onsubmit="event.preventDefault(); saveOrgSettings();">
                            <div class="form-group">
                                <label for="org-name-input" class="form-label">Organization Name</label>
                                <input type="text" id="org-name-input" class="form-control" value="${escapeHtml(org.name || 'GAATHA')}" required>
                            </div>
                            <div class="form-group">
                                <label for="org-timezone-select" class="form-label">Default Workspace Timezone</label>
                                <select id="org-timezone-select" class="form-control">
                                    <option value="Asia/Kolkata" ${org.default_timezone === 'Asia/Kolkata' ? 'selected' : ''}>Asia/Kolkata (IST · UTC+5:30)</option>
                                    <option value="UTC" ${org.default_timezone === 'UTC' ? 'selected' : ''}>UTC</option>
                                    <option value="America/New_York" ${org.default_timezone === 'America/New_York' ? 'selected' : ''}>America/New_York (EST/EDT)</option>
                                    <option value="Europe/London" ${org.default_timezone === 'Europe/London' ? 'selected' : ''}>Europe/London (GMT/BST)</option>
                                    <option value="Asia/Dubai" ${org.default_timezone === 'Asia/Dubai' ? 'selected' : ''}>Asia/Dubai (GST · UTC+4:00)</option>
                                </select>
                            </div>
                            <button type="submit" class="btn btn-primary btn-sm" style="margin-top: 0.5rem;">
                                <i class="fa-solid fa-floppy-disk"></i> Save Settings
                            </button>
                        </form>
                    </div>

                    <!-- SaaS Entitlements Card -->
                    <div class="card" style="padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between;">
                        <div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                                <h4 style="margin: 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                                    <i class="fa-solid fa-crown" style="color: #f59e0b;"></i> Subscription Plan
                                </h4>
                                <span class="badge badge-success" style="font-weight: 800; font-size: 0.78rem;">${escapeHtml(planName)}</span>
                            </div>

                            <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 1rem;">
                                Commercial SaaS tier with automated quota tracking and provider failover.
                            </p>

                            <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem;">
                                <div>
                                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.25rem;">
                                        <span>AI Monthly Tokens: <strong>${tokensUsed.toLocaleString()} / ${tokensLimit.toLocaleString()}</strong></span>
                                        <span>${tokensPct}%</span>
                                    </div>
                                    <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                        <div style="width: ${tokensPct}%; background: #f59e0b; height: 100%;"></div>
                                    </div>
                                </div>
                                <div>
                                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.25rem;">
                                        <span>Campaigns: <strong>${campsUsed} / ${campsLimit}</strong></span>
                                        <span>${campsPct}%</span>
                                    </div>
                                    <div style="background: var(--bg-surface); height: 8px; border-radius: 4px; overflow: hidden;">
                                        <div style="width: ${campsPct}%; background: #6366f1; height: 100%;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <button type="button" class="btn btn-secondary btn-sm" onclick="openSubscriptionUpgradeModal()">
                            <i class="fa-solid fa-arrow-up-right-dots"></i> Upgrade Plan
                        </button>
                    </div>
                </div>

                <!-- Team Members Card -->
                <div class="card" style="padding: 1.25rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
                        <div>
                            <h4 style="margin: 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                                <i class="fa-solid fa-users" style="color: var(--primary);"></i> Workspace Team Members
                            </h4>
                            <small style="color: var(--text-muted);">Role-based permissions (Owner, Admin, Contributor, Viewer)</small>
                        </div>
                        <button type="button" class="btn btn-primary btn-sm" onclick="openOrgMemberModal()">
                            <i class="fa-solid fa-user-plus"></i> Add Member
                        </button>
                    </div>

                    <div style="overflow-x: auto;">
                        <table class="data-table" style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="background: var(--bg-surface); border-bottom: 1px solid var(--border);">
                                    <th style="padding: 0.65rem 0.85rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">User</th>
                                    <th style="padding: 0.65rem 0.85rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Email</th>
                                    <th style="padding: 0.65rem 0.85rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Role</th>
                                    <th style="padding: 0.65rem 0.85rem; text-align: left; font-size: 0.75rem; text-transform: uppercase;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${members.map(m => `
                                    <tr style="border-bottom: 1px solid var(--border);">
                                        <td style="padding: 0.65rem 0.85rem; font-weight: 600; font-size: 0.85rem;">${escapeHtml(m.username || 'User')}</td>
                                        <td style="padding: 0.65rem 0.85rem; font-size: 0.82rem; color: var(--text-secondary);">${escapeHtml(m.email || '—')}</td>
                                        <td style="padding: 0.65rem 0.85rem;">
                                            <span class="badge ${m.role === 'owner' ? 'badge-primary' : (m.role === 'admin' ? 'badge-info' : 'badge-secondary')}" style="font-size: 0.72rem; text-transform: capitalize;">
                                                ${escapeHtml(m.role || 'contributor')}
                                            </span>
                                        </td>
                                        <td style="padding: 0.65rem 0.85rem; font-size: 0.78rem; color: var(--success);"><i class="fa-solid fa-check"></i> Active</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load settings: ${escapeHtml(e.message)}</div>`;
    }
}

async function saveOrgSettings() {
    const name = document.getElementById('org-name-input')?.value.trim();
    const tz = document.getElementById('org-timezone-select')?.value;
    if (!name) return;

    try {
        const res = await authFetch('/api/org/settings', {
            method: 'POST',
            body: JSON.stringify({ name, default_timezone: tz })
        });
        if (res.ok) {
            showToast("Organization settings saved successfully!", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to update settings", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// ==========================================================================
// MODAL CONTROLLERS & ACTIONS: Creative Validation, Planner, Scheduling, SaaS
// ==========================================================================

// Creative Platform Validation
async function validateStudioDraftCreative(draftId) {
    const box = document.getElementById(`draft-validation-box-${draftId}`);
    const btn = document.getElementById(`btn-val-${draftId}`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
    }

    try {
        const res = await authFetch(`/api/drafts/${draftId}/validate-creative`, {
            method: 'POST'
        });

        if (box) box.style.display = 'block';

        if (res.ok) {
            const data = await res.json();
            const valid = data.valid;
            const issues = data.issues || [];

            if (valid) {
                if (box) {
                    box.style.background = '#ecfdf5';
                    box.style.border = '1px solid #a7f3d0';
                    box.style.color = '#065f46';
                    box.innerHTML = `<i class="fa-solid fa-circle-check"></i> <strong>Platform Guidelines Passed!</strong> Character counts, tags, and formatting satisfy channel limits.`;
                }
                showToast("Creative satisfies platform rules!", "success");
            } else {
                if (box) {
                    box.style.background = '#fffbeb';
                    box.style.border = '1px solid #fde68a';
                    box.style.color = '#92400e';
                    box.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>Creative Notice:</strong><ul style="margin: 0.3rem 0 0 1rem; padding: 0;">${issues.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
                }
                showToast("Review creative notices before scheduling.", "warning");
            }
        } else {
            const err = await res.json();
            showToast(err.error || "Validation failed", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validate`;
        }
    }
}

// Schedule Draft Modal
function openScheduleDraftModal(draftId) {
    const draft = studioDrafts.find(d => d.id === draftId);
    if (!draft) return;

    document.getElementById('sched-draft-id').value = draftId;

    // Default datetime to tomorrow at 10:00 AM
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(10, 0, 0, 0);
    const localIso = tomorrow.toISOString().slice(0, 16);
    const dtEl = document.getElementById('sched-draft-datetime');
    if (dtEl) dtEl.value = localIso;

    // Pre-select mapped channel
    const chanEl = document.getElementById('sched-draft-channel');
    if (chanEl) {
        if (draft.target_platform === 'instagram') chanEl.value = 'insta';
        else if (draft.target_platform === 'facebook') chanEl.value = 'tour';
        else chanEl.value = 'tour';
    }

    // Populate media assets dropdown
    const mediaEl = document.getElementById('sched-draft-media');
    if (mediaEl) {
        authFetch('/api/media').then(r => r.ok ? r.json() : []).then(assets => {
            let opts = `<option value="">No media attached (Text only)</option>`;
            assets.forEach(a => {
                opts += `<option value="${a.id}">${escapeHtml(a.original_filename)}</option>`;
            });
            mediaEl.innerHTML = opts;
        }).catch(() => {});
    }

    const modal = document.getElementById('schedule-draft-modal');
    if (modal) modal.classList.add('show');
}

function closeScheduleDraftModal() {
    const modal = document.getElementById('schedule-draft-modal');
    if (modal) modal.classList.remove('show');
}

async function confirmScheduleDraft() {
    const draftId = document.getElementById('sched-draft-id')?.value;
    const channel = document.getElementById('sched-draft-channel')?.value;
    const datetime = document.getElementById('sched-draft-datetime')?.value;
    const mediaId = document.getElementById('sched-draft-media')?.value;

    if (!draftId || !channel || !datetime) {
        showToast("Please specify channel and scheduled time.", "warning");
        return;
    }

    const btn = document.getElementById('confirm-schedule-draft-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scheduling...`;
    }

    try {
        const payload = {
            channel,
            scheduled_time: datetime,
            media_asset_id: mediaId ? Number(mediaId) : null
        };

        const res = await authFetch(`/api/drafts/${draftId}/schedule`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeScheduleDraftModal();
            showToast("Draft successfully converted into scheduled publishing queue!", "success");
            // Reload Studio drafts or Queue
            renderAIStudioView(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to schedule draft", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-calendar-check"></i> Schedule Post`;
        }
    }
}

// Content Planner Modal
let activeContentPlan = null;

function openContentPlannerModal(campaignId) {
    document.getElementById('planner-campaign-id').value = campaignId;
    document.getElementById('planner-plan-container').style.display = 'none';
    document.getElementById('planner-loading-state').style.display = 'none';

    // Set default start date to today
    const startEl = document.getElementById('planner-start-date');
    if (startEl && !startEl.value) {
        startEl.value = new Date().toISOString().slice(0, 10);
    }

    const modal = document.getElementById('content-planner-modal');
    if (modal) modal.classList.add('show');
}

function closeContentPlannerModal() {
    const modal = document.getElementById('content-planner-modal');
    if (modal) modal.classList.remove('show');
}

async function generateContentPlanFromModal() {
    const cid = document.getElementById('planner-campaign-id')?.value;
    const horizon = document.getElementById('planner-horizon-select')?.value || 'weekly';
    const provider = document.getElementById('planner-provider-select')?.value || 'mock';
    const startDate = document.getElementById('planner-start-date')?.value;
    const focusTheme = document.getElementById('planner-focus-theme')?.value.trim();

    if (!cid) return;

    document.getElementById('planner-loading-state').style.display = 'block';
    document.getElementById('planner-plan-container').style.display = 'none';

    const btn = document.getElementById('btn-generate-plan');
    if (btn) btn.disabled = true;

    try {
        const payload = {
            schedule_horizon: horizon,
            provider,
            start_date: startDate,
            themes: focusTheme ? [focusTheme] : []
        };

        const res = await authFetch(`/api/campaigns/${cid}/planner`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        document.getElementById('planner-loading-state').style.display = 'none';

        if (res.ok) {
            const data = await res.json();
            activeContentPlan = data.content_plan;
            renderPlannerEntriesInModal(data.content_plan, data.entries || []);
            showToast("Content roadmap generated successfully!", "success");
        } else {
            const err = await res.json();
            showToast(err.error || "Planner generation failed", "danger");
        }
    } catch (e) {
        document.getElementById('planner-loading-state').style.display = 'none';
        showToast(e.message || "Network error", "danger");
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderPlannerEntriesInModal(plan, entries) {
    const titleEl = document.getElementById('planner-plan-title');
    if (titleEl) titleEl.textContent = plan.title || 'Marketing Content Plan';

    const listEl = document.getElementById('planner-entries-list');
    if (!listEl) return;

    if (!entries || entries.length === 0) {
        listEl.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No planned posts in this roadmap.</div>`;
    } else {
        listEl.innerHTML = entries.map(e => `
            <div style="background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 0.75rem 1rem; display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem;">
                        <span class="badge badge-primary" style="font-size: 0.7rem;">${escapeHtml((e.target_platform || 'all').toUpperCase())}</span>
                        <span style="font-weight: 700; font-size: 0.88rem;">${escapeHtml(e.headline || e.theme || 'Planned Post')}</span>
                    </div>
                    <p style="font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 0.4rem 0; line-height: 1.4;">${escapeHtml(e.copy_angle || e.caption_concept || '')}</p>
                    <div style="font-size: 0.74rem; color: var(--text-muted);">
                        <strong>Suggested Date:</strong> ${escapeHtml(e.scheduled_date || 'Day ' + (e.day_number || 1))} · <strong>CTA:</strong> ${escapeHtml(e.call_to_action || 'Learn More')}
                    </div>
                </div>
            </div>
        `).join('');
    }

    document.getElementById('planner-plan-container').style.display = 'block';
}

async function convertActivePlanToDrafts() {
    if (!activeContentPlan || !activeContentPlan.id) {
        showToast("No active plan to convert.", "warning");
        return;
    }

    const btn = document.getElementById('btn-convert-plan-drafts');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Converting...`;
    }

    try {
        const res = await authFetch(`/api/content-plans/${activeContentPlan.id}/convert-drafts`, {
            method: 'POST'
        });

        if (res.ok) {
            const data = await res.json();
            showToast(`Converted plan into ${data.drafts_count || data.drafts?.length || 'multiple'} content drafts!`, "success");
            closeContentPlannerModal();
            renderAIStudioView(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Conversion failed", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-file-import"></i> Convert All to Content Drafts`;
        }
    }
}

// Org Member Invite Modal
function openOrgMemberModal() {
    const modal = document.getElementById('org-member-modal');
    if (modal) modal.classList.add('show');
}

function closeOrgMemberModal() {
    const modal = document.getElementById('org-member-modal');
    if (modal) modal.classList.remove('show');
}

async function confirmAddOrgMember() {
    const username = document.getElementById('member-username-input')?.value.trim();
    const email = document.getElementById('member-email-input')?.value.trim();
    const password = document.getElementById('member-password-input')?.value.trim();
    const role = document.getElementById('member-role-select')?.value || 'contributor';

    if (!username || !email || !password) {
        showToast("Please fill in username, email, and password.", "warning");
        return;
    }

    try {
        const res = await authFetch('/api/org/members', {
            method: 'POST',
            body: JSON.stringify({ username, email, password, role })
        });

        if (res.ok) {
            closeOrgMemberModal();
            showToast(`Team member ${username} added successfully!`, "success");
            renderSettings(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to add member", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}

// Subscription Upgrade Modal
function openSubscriptionUpgradeModal() {
    const modal = document.getElementById('subscription-upgrade-modal');
    if (modal) modal.classList.add('show');
}

function closeSubscriptionUpgradeModal() {
    const modal = document.getElementById('subscription-upgrade-modal');
    if (modal) modal.classList.remove('show');
}

function handleUpgradeTierChange(tier) {
    const titleEl = document.getElementById('tier-summary-title');
    const featEl = document.getElementById('tier-summary-features');
    if (!titleEl || !featEl) return;

    if (tier === 'starter') {
        titleEl.textContent = "Starter Tier Benefits";
        featEl.innerHTML = `
            <li>1 Brand Workspace</li>
            <li>10 Concurrent Marketing Campaigns</li>
            <li>50,000 AI Content &amp; Strategy Tokens / Month</li>
            <li>Basic Publishing Automation</li>
        `;
    } else if (tier === 'growth') {
        titleEl.textContent = "Growth Tier Benefits";
        featEl.innerHTML = `
            <li>5 Brand Workspaces</li>
            <li>50 Concurrent Marketing Campaigns</li>
            <li>250,000 AI Content &amp; Strategy Tokens / Month</li>
            <li>Unlimited Scheduled Posts</li>
            <li>Full Media Asset Library</li>
        `;
    } else if (tier === 'enterprise') {
        titleEl.textContent = "Enterprise Tier Benefits";
        featEl.innerHTML = `
            <li>Unlimited Brand Workspaces</li>
            <li>500 Concurrent Marketing Campaigns</li>
            <li>2,000,000 AI Content &amp; Strategy Tokens / Month</li>
            <li>Unlimited Scheduled Posts &amp; Fast Worker Queue</li>
            <li>Role-Based Access Control &amp; Team Management</li>
        `;
    }
}

async function confirmSubscriptionUpgrade() {
    const plan = document.getElementById('upgrade-tier-select')?.value;
    const cycle = document.getElementById('upgrade-billing-cycle')?.value || 'monthly';
    if (!plan) return;

    try {
        const res = await authFetch('/api/saas/subscription/upgrade', {
            method: 'POST',
            body: JSON.stringify({ plan_id: plan, billing_cycle: cycle })
        });

        if (res.ok) {
            closeSubscriptionUpgradeModal();
            showToast(`Subscription upgraded to ${plan.toUpperCase()}!`, "success");
            renderSettings(document.getElementById('content-area'));
        } else {
            const err = await res.json();
            showToast(err.error || "Upgrade failed", "danger");
        }
    } catch (e) {
        showToast(e.message || "Network error", "danger");
    }
}
