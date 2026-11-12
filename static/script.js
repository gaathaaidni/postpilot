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
    facebook: {
        name: 'Facebook Pages',
        short: 'Facebook',
        handle: 'facebook_pages',
        category: 'Meta Graph API v19.0',
        icon: 'fa-brands fa-facebook',
        color: '#1877f2',
        bg: '#1877f2',
        platforms: ['facebook']
    },
    instagram: {
        name: 'Instagram Professional',
        short: 'Instagram',
        handle: 'instagram_pro',
        category: 'Meta 3-Phase Lifecycle',
        icon: 'fa-brands fa-instagram',
        color: '#e1306c',
        bg: '#e1306c',
        platforms: ['instagram']
    },
    linkedin: {
        name: 'LinkedIn Company',
        short: 'LinkedIn',
        handle: 'linkedin_org',
        category: 'REST Posts API 202401',
        icon: 'fa-brands fa-linkedin-in',
        color: '#0a66c2',
        bg: '#0a66c2',
        platforms: ['linkedin']
    },
    whatsapp: {
        name: 'WhatsApp Business Cloud',
        short: 'WhatsApp',
        handle: 'whatsapp_cloud',
        category: 'Meta WhatsApp Cloud API',
        icon: 'fa-brands fa-whatsapp',
        color: '#25d366',
        bg: '#25d366',
        platforms: ['whatsapp']
    },
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
function showLinkedInOAuthBanner(kind, title, message) {
    const content = document.getElementById('content-area');
    if (!content || !content.parentNode) return;
    let banner = document.getElementById('linkedin-oauth-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'linkedin-oauth-banner';
        content.parentNode.insertBefore(banner, content);
    }
    const isSuccess = kind === 'success';
    const borderColor = isSuccess ? 'rgba(5, 150, 105, 0.35)' : 'rgba(220, 38, 38, 0.35)';
    const bgColor = isSuccess ? 'var(--success-soft)' : 'var(--danger-soft)';
    const accentColor = isSuccess ? 'var(--success)' : 'var(--danger)';
    const iconClass = isSuccess ? 'fa-circle-check' : 'fa-triangle-exclamation';

    banner.style.cssText = `margin: 0 1.5rem 1rem 1.5rem; padding: 0.9rem 1.1rem; border-radius: 10px; border: 1px solid ${borderColor}; background: ${bgColor}; display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem;`;
    banner.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 0.7rem;">
            <i class="fa-solid ${iconClass}" style="color: ${accentColor}; margin-top: 0.2rem;"></i>
            <div>
                <div style="font-weight: 700; color: ${accentColor}; font-size: 0.92rem;">${escapeHtml(title)}</div>
                <div style="color: var(--text-secondary); font-size: 0.84rem; margin-top: 0.2rem; word-break: break-word;">${escapeHtml(message)}</div>
            </div>
        </div>
        <button type="button" onclick="this.parentElement.remove()" aria-label="Dismiss" style="background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; padding: 0 0.25rem;">&times;</button>
    `;
}

// Theme & Sidebar Preferences (Light-first SaaS defaults)
const THEME_STORAGE_KEY = 'postpilot_theme_v2';
const SIDEBAR_COLLAPSED_KEY = 'postpilot_sidebar_collapsed';

function getCurrentTheme() {
    try {
        return localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
    } catch (e) {
        return 'light';
    }
}

function applyThemeUI(mode) {
    const normalized = mode === 'dark' ? 'dark' : 'light';
    const root = document.documentElement;
    if (normalized === 'dark') {
        root.setAttribute('data-theme', 'dark');
    } else {
        root.removeAttribute('data-theme');
    }

    const desktopBtn = document.getElementById('theme-toggle-btn');
    if (desktopBtn) {
        desktopBtn.setAttribute('aria-pressed', normalized === 'dark' ? 'true' : 'false');
        desktopBtn.setAttribute('title', normalized === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        desktopBtn.innerHTML = normalized === 'dark'
            ? '<i class="fa-solid fa-sun"></i><span class="btn-label">Light</span>'
            : '<i class="fa-solid fa-moon"></i><span class="btn-label">Dark</span>';
    }

    const mobileBtn = document.getElementById('mobile-theme-btn');
    if (mobileBtn) {
        mobileBtn.setAttribute('aria-pressed', normalized === 'dark' ? 'true' : 'false');
        mobileBtn.innerHTML = normalized === 'dark'
            ? '<i class="fa-solid fa-sun"></i>'
            : '<i class="fa-solid fa-moon"></i>';
    }

    document.querySelectorAll('.theme-choice-card[data-theme-value]').forEach(btn => {
        const active = btn.dataset.themeValue === normalized;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
}

function setTheme(mode) {
    const normalized = mode === 'dark' ? 'dark' : 'light';
    try {
        localStorage.setItem(THEME_STORAGE_KEY, normalized);
    } catch (e) {}
    applyThemeUI(normalized);
}

function toggleTheme() {
    setTheme(getCurrentTheme() === 'dark' ? 'light' : 'dark');
}

function initTheme() {
    applyThemeUI(getCurrentTheme());
    ['theme-toggle-btn', 'mobile-theme-btn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn && !btn.getAttribute('onclick') && !btn.dataset.themeBound) {
            btn.dataset.themeBound = '1';
            btn.addEventListener('click', toggleTheme);
        }
    });
}

function applySidebarCollapseUI(collapsed) {
    const isDesktop = window.innerWidth >= 992;
    document.body.classList.toggle('sidebar-collapsed', Boolean(collapsed && isDesktop));
    const btn = document.getElementById('sidebar-collapse-btn');
    if (btn) {
        btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        btn.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        btn.innerHTML = collapsed
            ? '<i class="fa-solid fa-angles-right"></i>'
            : '<i class="fa-solid fa-angles-left"></i>';
    }
}

function toggleSidebarCollapse() {
    let current = false;
    try {
        current = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
    } catch (e) {}
    const next = !current;
    try {
        localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? '1' : '0');
    } catch (e) {}
    applySidebarCollapseUI(next);
}

function initSidebarCollapse() {
    let saved = false;
    try {
        saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
    } catch (e) {}
    applySidebarCollapseUI(saved);

    const btn = document.getElementById('sidebar-collapse-btn');
    if (btn && !btn.getAttribute('onclick') && !btn.dataset.collapseBound) {
        btn.dataset.collapseBound = '1';
        btn.addEventListener('click', toggleSidebarCollapse);
    }

    if (!window._ppResizeCollapseBound) {
        window._ppResizeCollapseBound = true;
        window.addEventListener('resize', () => {
            let pref = false;
            try {
                pref = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
            } catch (e) {}
            applySidebarCollapseUI(pref);
        });
    }
}

window.setTheme = setTheme;
window.toggleTheme = toggleTheme;
window.initTheme = initTheme;
window.toggleSidebarCollapse = toggleSidebarCollapse;

// Initial App Load
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSidebarCollapse();
    setupNavigation();
    setupMobileDrawer();
    setupGlobalSearch();

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const sidebar = document.getElementById('sidebar') || document.querySelector('.sidebar');
        const overlay = document.getElementById('drawer-overlay') || document.querySelector('.drawer-overlay');
        if (sidebar && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
        const postModal = document.getElementById('post-modal');
        if (postModal && postModal.classList.contains('show') && typeof closeModal === 'function') {
            closeModal();
        }
        const waModal = document.getElementById('wa-preview-modal');
        if (waModal && waModal.classList.contains('show') && typeof closeWaPreviewModal === 'function') {
            closeWaPreviewModal();
        }
    });

    const urlParams = new URLSearchParams(window.location.search);
    const liError = urlParams.get('linkedin_error');
    const liErrorDesc = urlParams.get('linkedin_error_description');
    const liApp = urlParams.get('linkedin_app');
    const liConnected = urlParams.get('linkedin_connected');
    const requestedTab = urlParams.get('tab');
    const initialTab = requestedTab || ((liError || liConnected) ? 'accounts' : 'dashboard');

    loadTab(initialTab);
    startStatusPolling();

    if (liConnected) {
        const appName = liConnected === 'aidni_global'
            ? 'Aidni Global LLP'
            : (liConnected === 'gaatha_ventures' ? 'Gaatha Ventures Sh.p.k.' : liConnected);
        showToast(`LinkedIn OAuth connected for ${appName}.`, 'success');
        showLinkedInOAuthBanner('success', `LinkedIn Connected: ${appName}`, 'OAuth authorization succeeded and the active token is saved.');
    } else if (liError) {
        const appLabel = liApp === 'aidni_global'
            ? 'Aidni Global LLP'
            : (liApp === 'gaatha_ventures' ? 'Gaatha Ventures Sh.p.k.' : 'LinkedIn App');
        const detail = liErrorDesc ? `${liError}: ${liErrorDesc}` : liError;
        showToast(`LinkedIn OAuth error (${appLabel}): ${detail}`, 'error');
        showLinkedInOAuthBanner('error', `LinkedIn OAuth Error (${appLabel})`, detail);
    }

    if (requestedTab || liError || liErrorDesc || liApp || liConnected) {
        try {
            const cleanUrl = window.location.pathname + (window.location.hash || '');
            window.history.replaceState({}, document.title, cleanUrl);
        } catch (e) {}
    }
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
        'dashboard': 'Executive Dashboard',
        'composer': 'Guided Post Composer',
        'calendar': 'Content Calendar',
        'drafts': 'Drafts Workspace',
        'history': 'Publishing History & Diagnostics',
        'accounts': 'Connected Social Platforms',
        'whatsapp': 'WhatsApp Cloud API',
        'settings': 'Organization Settings',
        'brands': 'Brand Workspaces',
        'studio': 'AI Marketing Studio',
        'campaigns': 'Campaigns Management',
        'media': 'Media Library',
        'approvals': 'Approvals Centre',
        'queue': 'Publishing Queue',
        'analytics': 'Marketing & AI Analytics',
        'tour': 'Nexora Suite Management',
        'nz': 'Phoenix International Management',
        'gaatha': 'Gaatha AI Automation',
        'insta': 'Instagram Synchronization',
        'about': 'Help & About PostPilot',
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
    } else if (tab === 'composer') {
        renderComposerView(content);
    } else if (tab === 'calendar') {
        renderCalendarView(content);
    } else if (tab === 'drafts') {
        renderDraftsView(content);
    } else if (tab === 'history') {
        renderHistory(content);
    } else if (tab === 'accounts') {
        renderAccounts(content);
    } else if (tab === 'whatsapp') {
        renderWhatsAppView(content);
    } else if (tab === 'settings') {
        renderSettings(content);
    } else if (tab === 'brands') {
        renderBrands(content);
    } else if (tab === 'studio') {
        renderAIStudioView(content);
    } else if (tab === 'campaigns') {
        renderCampaigns(content);
    } else if (tab === 'media') {
        renderMedia(content);
    } else if (tab === 'approvals') {
        renderApprovalsView(content);
    } else if (tab === 'queue') {
        renderQueueView(content);
    } else if (tab === 'analytics') {
        renderAnalytics(content);
    } else if (tab === 'about') {
        renderHelpAboutView(content);
    } else if (['tour', 'nz', 'gaatha', 'insta'].includes(tab)) {
        renderModule(content, tab);
    }
}

function renderHelpAboutView(container) {
    container.innerHTML = `
        <div class="hub-hero fade-in">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1.25rem; flex-wrap: wrap;">
                <div>
                    <span class="badge badge-primary" style="margin-bottom: 0.65rem;"><i class="fa-solid fa-shield-halved"></i> Enterprise Multi-Brand Operations</span>
                    <h2 style="font-size: 1.55rem; margin-bottom: 0.45rem;">PostPilot Help & Platform Documentation</h2>
                    <p style="font-size: 0.92rem; max-width: 720px;">Unified publishing control plane across GAATHA brands with strict workspace isolation, Asia/Kolkata scheduling alignment, and fail-closed publishing safety gates.</p>
                </div>
                <div style="display: flex; gap: 0.6rem; flex-wrap: wrap;">
                    <button class="btn btn-primary" onclick="loadTab('composer')"><i class="fa-solid fa-pen-nib"></i> Open Composer</button>
                    <button class="btn btn-outline-secondary" onclick="loadTab('accounts')"><i class="fa-solid fa-plug"></i> Connected Accounts</button>
                </div>
            </div>
        </div>

        <div class="dashboard-metrics-grid fade-in" style="margin-bottom: 1.5rem;">
            <div class="card">
                <div class="card-header"><h3 style="margin: 0;"><i class="fa-solid fa-lock text-primary"></i> Publishing Safety Model</h3></div>
                <div class="card-body">
                    <p style="color: var(--text-secondary); font-size: 0.88rem; line-height: 1.6; margin-bottom: 0.85rem;">
                        Scheduled jobs, queue testing, and UI workflows respect environment-level safety guardrails (<code>POSTPILOT_PUBLISHING_ENABLED</code> and <code>WHATSAPP_PUBLISHING_ENABLED</code>). When live dispatch is disabled, scheduled posts stay protected without hitting external social endpoints.
                    </p>
                    <div class="notice-callout notice-callout--info">
                        <i class="fa-solid fa-circle-info"></i>
                        <div>Check real gateway health on the <strong>Connected Accounts</strong> view before enabling any external brand schedule.</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-header"><h3 style="margin: 0;"><i class="fa-solid fa-sitemap text-primary"></i> Multi-Brand Isolation</h3></div>
                <div class="card-body">
                    <p style="color: var(--text-secondary); font-size: 0.88rem; line-height: 1.6; margin-bottom: 0.85rem;">
                        Each GAATHA workspace maintains isolated credentials, brand tones, hashtags, and destination bindings across Meta Pages, Instagram Business profiles, LinkedIn OAuth apps, and WhatsApp senders.
                    </p>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        <button class="btn btn-secondary btn-sm" onclick="loadTab('brands')"><i class="fa-solid fa-layer-group"></i> Manage Brands</button>
                        <button class="btn btn-secondary btn-sm" onclick="loadTab('settings')"><i class="fa-solid fa-sliders"></i> Theme & Settings</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="card fade-in">
            <div class="card-header"><h3 style="margin: 0;"><i class="fa-solid fa-book-open text-primary"></i> Legal & Governance Pages</h3></div>
            <div class="card-body" style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                <a class="btn btn-outline-secondary" href="/about" target="_blank" rel="noopener"><i class="fa-solid fa-circle-info"></i> Public About Page</a>
                <a class="btn btn-outline-secondary" href="/privacy" target="_blank" rel="noopener"><i class="fa-solid fa-user-shield"></i> Privacy Policy</a>
                <a class="btn btn-outline-secondary" href="/terms" target="_blank" rel="noopener"><i class="fa-solid fa-file-contract"></i> Terms of Service</a>
                <a class="btn btn-outline-secondary" href="/agreement" target="_blank" rel="noopener"><i class="fa-solid fa-handshake"></i> User Agreement</a>
            </div>
        </div>
    `;
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

        // Global status pulse based on engine status and scoped platform guardrails
        const pubEnabled = Boolean(data.publishing_enabled);
        const enabledPlats = Array.isArray(data.enabled_publishing_platforms) ? data.enabled_publishing_platforms : [];
        const dot = document.getElementById('system-pulsing-dot');
        const indicator = document.getElementById('global-status-indicator');
        if (dot) dot.style.backgroundColor = pubEnabled ? 'var(--success)' : '#10b981';
        if (indicator) {
            if (!pubEnabled) {
                indicator.textContent = 'Engine Ready (Safe)';
            } else if (enabledPlats.length > 0 && enabledPlats.length < 4) {
                indicator.textContent = `Live: ${enabledPlats.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(', ')}`;
            } else {
                indicator.textContent = 'Publishing Enabled';
            }
        }

        // Update active view
        if (currentTab === 'dashboard') {
            updateDashboardMetrics(data);
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
// VIEW: Dashboard (Executive Modern Global SaaS)
// ==========================================================================
let dashboardDateFilter = 'all';

function setDashboardDateFilter(filter) {
    dashboardDateFilter = filter;
    document.querySelectorAll('.dash-filter-btn').forEach(btn => {
        if (btn.dataset.filter === filter) btn.classList.add('active');
        else btn.classList.remove('active');
    });
    loadDashboardExecutiveMetrics();
}

function parseUtcTimestamp(raw) {
    if (raw === null || raw === undefined || raw === '') return null;
    if (raw instanceof Date) {
        return Number.isNaN(raw.getTime()) ? null : raw;
    }
    if (typeof raw === 'number') {
        if (!Number.isFinite(raw)) return null;
        const ms = raw < 1e12 ? raw * 1000 : raw;
        const d = new Date(ms);
        return Number.isNaN(d.getTime()) ? null : d;
    }

    const str = String(raw).trim();
    if (!str) return null;

    // Naive SQLite/backend UTC timestamps (e.g. "2026-11-04 06:30:13") have no offset; parse explicitly as UTC
    const naiveMatch = str.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?$/);
    if (naiveMatch) {
        const year = Number(naiveMatch[1]);
        const month = Number(naiveMatch[2]);
        const day = Number(naiveMatch[3]);
        const hour = Number(naiveMatch[4] || 0);
        const minute = Number(naiveMatch[5] || 0);
        const second = Number(naiveMatch[6] || 0);
        const ms = naiveMatch[7] ? Number(naiveMatch[7].slice(0, 3).padEnd(3, '0')) : 0;
        const d = new Date(Date.UTC(year, month - 1, day, hour, minute, second, ms));
        if (
            Number.isNaN(d.getTime()) ||
            d.getUTCFullYear() !== year ||
            d.getUTCMonth() !== month - 1 ||
            d.getUTCDate() !== day ||
            d.getUTCHours() !== hour ||
            d.getUTCMinutes() !== minute ||
            d.getUTCSeconds() !== second
        ) {
            return null;
        }
        return d;
    }

    const parsed = new Date(str);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatReadableDateTime(raw, fallback = '—') {
    const dt = parseUtcTimestamp(raw);
    if (!dt) return fallback;

    try {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: 'Asia/Kolkata',
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        }).formatToParts(dt);
        const partMap = {};
        parts.forEach(p => { partMap[p.type] = p.value; });
        const period = (partMap.dayPeriod || '').toUpperCase();
        return `${partMap.day} ${partMap.month} ${partMap.year}, ${partMap.hour}:${partMap.minute} ${period} IST`.trim();
    } catch (e) {
        // Fallback manual UTC+05:30 offset if Intl timeZone is unavailable
        const ist = new Date(dt.getTime() + (330 * 60 * 1000));
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const dd = String(ist.getUTCDate()).padStart(2, '0');
        const mmm = months[ist.getUTCMonth()];
        const yyyy = ist.getUTCFullYear();
        let hh = ist.getUTCHours();
        const min = String(ist.getUTCMinutes()).padStart(2, '0');
        const period = hh >= 12 ? 'PM' : 'AM';
        hh = hh % 12 || 12;
        return `${dd} ${mmm} ${yyyy}, ${String(hh).padStart(2, '0')}:${min} ${period} IST`;
    }
}

function parsePostDate(item) {
    const raw = item && (item.published_at || item.scheduled_for || item.updated_at || item.created_at);
    return parseUtcTimestamp(raw);
}

function filterItemsByDateRange(items, rangeKey) {
    const list = Array.isArray(items) ? items : [];
    if (!rangeKey || rangeKey === 'all') return list;
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let cutoff = startOfToday;
    if (rangeKey === '7d') {
        cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    } else if (rangeKey === '30d') {
        cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    }
    return list.filter(item => {
        const dt = parsePostDate(item);
        if (!dt) return false;
        return dt >= cutoff;
    });
}

function syncSidebarNavBadges({ draftsCount, connectedCount, totalAccountsCount } = {}) {
    const draftsBadge = document.getElementById('nav-drafts-count');
    if (draftsBadge && typeof draftsCount === 'number') {
        draftsBadge.textContent = String(draftsCount);
    }
    const accountsBadge = document.getElementById('nav-accounts-count');
    if (accountsBadge && typeof totalAccountsCount === 'number') {
        accountsBadge.textContent = totalAccountsCount > 0
            ? `${connectedCount || 0}/${totalAccountsCount}`
            : '0';
    }
}

async function renderDashboard(container) {
    container.innerHTML = `
        <!-- Executive Header & Refresh Controls -->
        <div class="dash-executive-header">
            <div>
                <h2 style="font-size: 1.35rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.25rem;">
                    <i class="fa-solid fa-chart-pie" style="color: var(--primary);"></i> Executive Publishing Dashboard
                </h2>
                <p style="color: var(--text-muted); font-size: 0.88rem; margin: 0;">
                    Multi-brand social media publishing health, verified destination records, and live gateway status.
                </p>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <div class="dash-filter-group" role="group" aria-label="Date Range Filters">
                    <button type="button" class="dash-filter-btn ${dashboardDateFilter === 'today' ? 'active' : ''}" data-filter="today" onclick="setDashboardDateFilter('today')">Today</button>
                    <button type="button" class="dash-filter-btn ${dashboardDateFilter === '7d' ? 'active' : ''}" data-filter="7d" onclick="setDashboardDateFilter('7d')">Last 7 Days</button>
                    <button type="button" class="dash-filter-btn ${dashboardDateFilter === '30d' ? 'active' : ''}" data-filter="30d" onclick="setDashboardDateFilter('30d')">Last 30 Days</button>
                    <button type="button" class="dash-filter-btn ${dashboardDateFilter === 'all' ? 'active' : ''}" data-filter="all" onclick="setDashboardDateFilter('all')">All Time</button>
                </div>
                <button type="button" class="btn btn-sm btn-secondary" onclick="refreshDashboard()" title="Refresh Dashboard Data">
                    <i class="fa-solid fa-rotate"></i> Refresh
                </button>
            </div>
        </div>

        <!-- 6 Executive KPI Metrics Grid -->
        <section class="stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));" aria-label="Key Performance Indicators">
            <!-- 1. Connected Social Accounts -->
            <div class="stat-card" style="border-top: 3px solid var(--info); cursor: pointer;" onclick="loadTab('accounts')">
                <div class="stat-icon bg-blue-soft">
                    <i class="fa-solid fa-share-nodes"></i>
                </div>
                <div class="stat-info">
                    <h4>Connected Accounts</h4>
                    <p id="kpi-accounts-count"><i class="fa-solid fa-circle-notch fa-spin fa-xs"></i></p>
                    <small id="kpi-accounts-desc">Checking destinations...</small>
                </div>
            </div>

            <!-- 2. Successfully Published -->
            <div class="stat-card" style="border-top: 3px solid var(--success); cursor: pointer;" onclick="loadTab('history')">
                <div class="stat-icon bg-green-soft">
                    <i class="fa-solid fa-circle-check"></i>
                </div>
                <div class="stat-info">
                    <h4>Published Dispatches</h4>
                    <p id="kpi-published-count"><i class="fa-solid fa-circle-notch fa-spin fa-xs"></i></p>
                    <small id="kpi-published-desc">Recorded database dispatches</small>
                </div>
            </div>

            <!-- 3. Scheduled Posts -->
            <div class="stat-card" style="border-top: 3px solid var(--primary); cursor: pointer;" onclick="loadTab('calendar')">
                <div class="stat-icon bg-blue-soft">
                    <i class="fa-solid fa-calendar-check"></i>
                </div>
                <div class="stat-info">
                    <h4>Scheduled Posts</h4>
                    <p id="kpi-scheduled-count"><i class="fa-solid fa-circle-notch fa-spin fa-xs"></i></p>
                    <small id="kpi-scheduled-desc">Queued in active database</small>
                </div>
            </div>

            <!-- 4. Content Drafts -->
            <div class="stat-card" style="border-top: 3px solid var(--accent-gold); cursor: pointer;" onclick="loadTab('drafts')">
                <div class="stat-icon bg-gold-soft">
                    <i class="fa-solid fa-file-pen"></i>
                </div>
                <div class="stat-info">
                    <h4>Content Drafts</h4>
                    <p id="kpi-drafts-count"><i class="fa-solid fa-circle-notch fa-spin fa-xs"></i></p>
                    <small>Creative workspace</small>
                </div>
            </div>

            <!-- 5. Failed / Needs Attention -->
            <div class="stat-card" style="border-top: 3px solid var(--danger); cursor: pointer;" onclick="loadTab('history')">
                <div class="stat-icon" style="background: var(--danger-soft); color: var(--danger);">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                </div>
                <div class="stat-info">
                    <h4>Needs Attention</h4>
                    <p id="kpi-failed-count" style="color: var(--danger);"><i class="fa-solid fa-circle-notch fa-spin fa-xs"></i></p>
                    <small id="kpi-failed-desc">Failed / Cancelled</small>
                </div>
            </div>

            <!-- 6. Publishing Success Rate -->
            <div class="stat-card" style="border-top: 3px solid var(--success);">
                <div class="stat-icon bg-green-soft">
                    <i class="fa-solid fa-chart-line"></i>
                </div>
                <div class="stat-info">
                    <h4>Publishing Success</h4>
                    <p id="kpi-success-rate">—</p>
                    <div class="success-rate-bar-track">
                        <div class="success-rate-bar-fill" id="kpi-success-fill" style="width: 0%;"></div>
                    </div>
                    <small id="kpi-success-desc">Measured from real dispatches</small>
                </div>
            </div>
        </section>

        <!-- Prominent Recent Successful Publishing Feed -->
        <section class="card" style="margin-bottom: 1.75rem;">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-tower-broadcast" style="color: var(--success);"></i>
                        <span>Recent Publishing Feed</span>
                    </div>
                    <div class="card-subtitle">Actual recorded dispatches across Facebook, Instagram, LinkedIn, and WhatsApp</div>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                    <span id="dashboard-feed-mode-badge" class="badge badge-neutral">
                        <i class="fa-solid fa-database"></i> Loading...
                    </span>
                    <button class="btn btn-sm btn-secondary" onclick="loadTab('history')">
                        <i class="fa-solid fa-clock-rotate-left"></i> View Full History
                    </button>
                </div>
            </div>

            <div class="published-feed-list" id="dashboard-published-feed">
                <div style="padding: 2rem; text-align: center; color: var(--text-muted);">
                    <i class="fa-solid fa-spinner fa-spin"></i> Loading published destination records...
                </div>
            </div>
        </section>

        <!-- Canonical Platform Publishing Gateways -->
        <section class="card" style="margin-bottom: 1.75rem;">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-cubes" style="color: var(--primary);"></i>
                        <span>Platform Publishing Gateways</span>
                    </div>
                    <div class="card-subtitle">Live status synced from backend integration checks and OAuth token health</div>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn btn-sm btn-primary" onclick="openModal('add')">
                        <i class="fa-solid fa-plus"></i> Compose Post
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="loadTab('accounts')">
                        <i class="fa-solid fa-gear"></i> Manage Accounts
                    </button>
                </div>
            </div>

            <div class="channel-grid">
                <!-- Gateway 1: Facebook Pages -->
                <div class="control-tile" id="tile-facebook" style="border-left: 4px solid #1877f2;">
                    <div class="tile-header">
                        <div class="tile-brand-group">
                            <div class="tile-icon-badge" style="background: rgba(24, 119, 242, 0.12); color: #1877f2; border: 1px solid rgba(24, 119, 242, 0.25);">
                                <i class="fa-brands fa-facebook"></i>
                            </div>
                            <div>
                                <div class="tile-title">Facebook Pages</div>
                                <div class="tile-subtitle">Graph API · Brand-Specific Routing</div>
                            </div>
                        </div>
                        <span id="tile-facebook-badge" class="badge badge-neutral">Checking...</span>
                    </div>
                    <div id="tile-facebook-meta" style="font-size: 0.82rem; color: var(--text-secondary); margin: 0.5rem 0;">
                        <span>Inspecting accessible Pages and permissions...</span>
                    </div>
                    <div class="tile-status-bar">
                        <span id="tile-facebook-guardrail" style="font-size: 0.75rem; color: var(--text-muted);"><i class="fa-solid fa-shield-halved"></i> Guardrail check...</span>
                        <span style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">Text, Photo &amp; Video</span>
                    </div>
                    <div class="tile-actions">
                        <button class="btn btn-sm btn-primary" onclick="openComposerForPlatform('facebook')" title="Compose for Facebook">
                            <i class="fa-solid fa-pen"></i> Compose
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="loadTab('accounts')" title="View Facebook Accounts">
                            <i class="fa-solid fa-plug"></i> Accounts
                        </button>
                    </div>
                </div>

                <!-- Gateway 2: Instagram Professional -->
                <div class="control-tile" id="tile-instagram" style="border-left: 4px solid #e1306c;">
                    <div class="tile-header">
                        <div class="tile-brand-group">
                            <div class="tile-icon-badge" style="background: rgba(225, 48, 108, 0.12); color: #e1306c; border: 1px solid rgba(225, 48, 108, 0.25);">
                                <i class="fa-brands fa-instagram"></i>
                            </div>
                            <div>
                                <div class="tile-title">Instagram Professional</div>
                                <div class="tile-subtitle">Container Lifecycle Publishing</div>
                            </div>
                        </div>
                        <span id="tile-instagram-badge" class="badge badge-neutral">Checking...</span>
                    </div>
                    <div id="tile-instagram-meta" style="font-size: 0.82rem; color: var(--text-secondary); margin: 0.5rem 0;">
                        <span>Inspecting linked Instagram business profiles...</span>
                    </div>
                    <div class="tile-status-bar">
                        <span id="tile-instagram-guardrail" style="font-size: 0.75rem; color: var(--text-muted);"><i class="fa-solid fa-shield-halved"></i> Guardrail check...</span>
                        <span style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">Photos &amp; Reels</span>
                    </div>
                    <div class="tile-actions">
                        <button class="btn btn-sm btn-primary" onclick="openComposerForPlatform('instagram')" title="Compose for Instagram">
                            <i class="fa-solid fa-pen"></i> Compose
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="loadTab('accounts')" title="View Instagram Accounts">
                            <i class="fa-solid fa-plug"></i> Accounts
                        </button>
                    </div>
                </div>

                <!-- Gateway 3: LinkedIn Enterprise -->
                <div class="control-tile" id="tile-linkedin" style="border-left: 4px solid #0a66c2;">
                    <div class="tile-header">
                        <div class="tile-brand-group">
                            <div class="tile-icon-badge" style="background: rgba(10, 102, 194, 0.12); color: #0a66c2; border: 1px solid rgba(10, 102, 194, 0.25);">
                                <i class="fa-brands fa-linkedin-in"></i>
                            </div>
                            <div>
                                <div class="tile-title">LinkedIn Pages</div>
                                <div class="tile-subtitle">REST Posts API · Dual OAuth Apps</div>
                            </div>
                        </div>
                        <span id="tile-linkedin-badge" class="badge badge-neutral">Checking...</span>
                    </div>
                    <div id="tile-linkedin-meta" style="font-size: 0.82rem; color: var(--text-secondary); margin: 0.5rem 0;">
                        <span>Inspecting Aidni Global &amp; Gaatha Ventures OAuth states...</span>
                    </div>
                    <div class="tile-status-bar">
                        <span id="tile-linkedin-guardrail" style="font-size: 0.75rem; color: var(--text-muted);"><i class="fa-solid fa-shield-halved"></i> Guardrail check...</span>
                        <span id="tile-linkedin-cap" style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">OAuth Status Synced</span>
                    </div>
                    <div class="tile-actions">
                        <button class="btn btn-sm btn-primary" onclick="openComposerForPlatform('linkedin')" title="Compose for LinkedIn">
                            <i class="fa-solid fa-pen"></i> Compose
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="loadTab('accounts')" title="View LinkedIn Details">
                            <i class="fa-solid fa-link"></i> OAuth Status
                        </button>
                    </div>
                </div>

                <!-- Gateway 4: WhatsApp Business Cloud -->
                <div class="control-tile" id="tile-whatsapp" style="border-left: 4px solid #059669;">
                    <div class="tile-header">
                        <div class="tile-brand-group">
                            <div class="tile-icon-badge" style="background: var(--success-soft); color: var(--success); border: 1px solid rgba(5, 150, 105, 0.25);">
                                <i class="fa-brands fa-whatsapp"></i>
                            </div>
                            <div>
                                <div class="tile-title">WhatsApp Cloud API</div>
                                <div class="tile-subtitle">Sender-Isolated Business Messaging</div>
                            </div>
                        </div>
                        <span id="tile-whatsapp-badge" class="badge badge-neutral">Checking...</span>
                    </div>
                    <div id="tile-whatsapp-meta" style="font-size: 0.82rem; color: var(--text-secondary); margin: 0.5rem 0;">
                        <span>Inspecting WhatsApp Cloud API verification status...</span>
                    </div>
                    <div class="tile-status-bar">
                        <span id="tile-whatsapp-guardrail" style="font-size: 0.75rem; color: var(--text-muted);"><i class="fa-solid fa-shield-halved"></i> Guardrail check...</span>
                        <span id="tile-whatsapp-cap" style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">Isolated Gateway</span>
                    </div>
                    <div class="tile-actions">
                        <button class="btn btn-sm btn-success" onclick="loadTab('whatsapp')" title="Open WhatsApp Studio">
                            <i class="fa-brands fa-whatsapp"></i> WhatsApp Studio
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="loadTab('accounts')" title="View WABA Connection">
                            <i class="fa-solid fa-circle-info"></i> Details
                        </button>
                    </div>
                </div>
            </div>
        </section>

        <!-- Upcoming Publishing Schedule Live Queue -->
        <section class="card" style="margin-bottom: 1.75rem;">
            <div class="card-header">
                <div>
                    <div class="card-title">
                        <i class="fa-solid fa-calendar-days" style="color: var(--primary);"></i>
                        <span>Upcoming Publishing Schedule (Active Queue)</span>
                    </div>
                    <div class="card-subtitle">Upcoming posts queued for dispatch in current organization</div>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                    <button class="btn btn-sm btn-primary" onclick="openModal('add')">
                        <i class="fa-solid fa-plus"></i> Schedule Post
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="loadTab('calendar')">
                        <i class="fa-solid fa-calendar"></i> View Calendar
                    </button>
                </div>
            </div>

            <div id="dashboard-upcoming-queue">
                <div style="padding: 2rem; text-align: center; color: var(--text-muted);">
                    <i class="fa-solid fa-spinner fa-spin"></i> Loading upcoming queue...
                </div>
            </div>
        </section>
    `;

    setTimeout(loadDashboardExecutiveMetrics, 20);
}

// Helper to open composer pre-filtered to target platform
function openComposerForPlatform(platform) {
    if (typeof openModal === 'function') {
        openModal('add', null, platform);
    } else {
        loadTab('composer');
    }
}

function updateGatewayTilesFromBackend(intData, statusData, accounts) {
    const pubEnabled = Boolean(statusData && statusData.publishing_enabled);
    const platFlags = (intData && intData.publishing_platforms) || (statusData && statusData.publishing_platforms) || {};
    const makeGuardHtml = (plat) => {
        const active = Object.prototype.hasOwnProperty.call(platFlags, plat) ? Boolean(platFlags[plat]) : pubEnabled;
        return active
            ? '<i class="fa-solid fa-circle-check" style="color: var(--success);"></i> Live Dispatch Enabled'
            : '<i class="fa-solid fa-shield-halved" style="color: var(--warning);"></i> Platform Guardrail Off (Disabled)';
    };
    const fbGuardHtml = makeGuardHtml('facebook');
    const igGuardHtml = makeGuardHtml('instagram');
    const liGuardHtml = makeGuardHtml('linkedin');

    // Meta (Facebook + Instagram)
    const meta = (intData && intData.meta) || {};
    const fbPages = Array.isArray(meta.pages) ? meta.pages : [];
    const igAccounts = Array.isArray(meta.instagram_accounts) ? meta.instagram_accounts : [];
    const metaHealthy = meta.status === 'connected' || fbPages.length > 0;

    const fbBadge = document.getElementById('tile-facebook-badge');
    const fbMeta = document.getElementById('tile-facebook-meta');
    const fbGuard = document.getElementById('tile-facebook-guardrail');
    if (fbBadge) {
        fbBadge.className = `badge ${metaHealthy ? 'badge-published' : 'badge-warning'}`;
        fbBadge.innerHTML = metaHealthy
            ? `<i class="fa-solid fa-circle-check"></i> ${fbPages.length || 0} Page${fbPages.length === 1 ? '' : 's'} Linked`
            : `<i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(meta.status_label || 'Check Meta Token')}`;
    }
    if (fbMeta) {
        fbMeta.innerHTML = fbPages.length > 0
            ? `<span><strong>Accessible Pages:</strong> ${fbPages.slice(0, 3).map(p => escapeHtml(p.name || p.id)).join(', ')}${fbPages.length > 3 ? ` (+${fbPages.length - 3})` : ''}</span>`
            : `<span>No active Pages returned by Meta Graph API check.</span>`;
    }
    if (fbGuard) fbGuard.innerHTML = fbGuardHtml;

    const igBadge = document.getElementById('tile-instagram-badge');
    const igMeta = document.getElementById('tile-instagram-meta');
    const igGuard = document.getElementById('tile-instagram-guardrail');
    if (igBadge) {
        const igOk = igAccounts.length > 0;
        igBadge.className = `badge ${igOk ? 'badge-published' : 'badge-warning'}`;
        igBadge.innerHTML = igOk
            ? `<i class="fa-solid fa-circle-check"></i> ${igAccounts.length} Profile${igAccounts.length === 1 ? '' : 's'}`
            : `<i class="fa-solid fa-triangle-exclamation"></i> No IG Profiles`;
    }
    if (igMeta) {
        igMeta.innerHTML = igAccounts.length > 0
            ? `<span><strong>Linked Profiles:</strong> ${igAccounts.slice(0, 3).map(a => `@${escapeHtml(a.username || a.id)}`).join(', ')}</span>`
            : `<span>Link an Instagram Professional profile via Facebook Page settings.</span>`;
    }
    if (igGuard) igGuard.innerHTML = igGuardHtml;

    // LinkedIn (Dual App accuracy)
    const li = (intData && intData.linkedin) || {};
    const liApps = Array.isArray(li.apps) ? li.apps : [];
    const liAuthed = liApps.filter(a => a.user_authenticated);
    const liCompanyReady = liApps.filter(a => a.company_publishing_ready);
    const liBadge = document.getElementById('tile-linkedin-badge');
    const liMeta = document.getElementById('tile-linkedin-meta');
    const liGuard = document.getElementById('tile-linkedin-guardrail');
    const liCap = document.getElementById('tile-linkedin-cap');

    if (liBadge) {
        if (liCompanyReady.length > 0) {
            liBadge.className = 'badge badge-published';
            liBadge.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${liCompanyReady.length}/${liApps.length || 2} Company Ready`;
        } else if (liAuthed.length > 0) {
            liBadge.className = 'badge badge-info';
            liBadge.innerHTML = `<i class="fa-solid fa-user-check"></i> ${liAuthed.length}/${liApps.length || 2} Personal Auth`;
        } else {
            liBadge.className = 'badge badge-warning';
            liBadge.innerHTML = `<i class="fa-solid fa-key"></i> Auth Required`;
        }
    }
    if (liMeta) {
        if (liApps.length > 0) {
            const summary = liApps.map(a => `${escapeHtml(a.app_name || a.app_key)}: ${a.user_authenticated ? 'Authorized' : 'Auth Required'}`).join(' &middot; ');
            liMeta.innerHTML = `<span><strong>OAuth Apps:</strong> ${summary}</span>`;
        } else {
            liMeta.innerHTML = `<span>${escapeHtml(li.status_label || 'LinkedIn OAuth pending setup.')}</span>`;
        }
    }
    if (liGuard) liGuard.innerHTML = liGuardHtml;
    if (liCap) {
        liCap.textContent = liCompanyReady.length > 0 ? 'Company & Member API Ready' : 'Company Posting Pending Review';
    }

    // WhatsApp (Sender isolated, never auto-assigns brands or fakes Verified)
    const wa = (intData && intData.whatsapp) || {};
    const waBadge = document.getElementById('tile-whatsapp-badge');
    const waMeta = document.getElementById('tile-whatsapp-meta');
    const waGuard = document.getElementById('tile-whatsapp-guardrail');
    const waCap = document.getElementById('tile-whatsapp-cap');
    const waOk = wa.status === 'connected';
    const waPubEnabled = Boolean(wa.publishing_enabled);

    if (waBadge) {
        waBadge.className = `badge ${waOk ? 'badge-published' : (wa.status === 'error' ? 'badge-failed' : 'badge-warning')}`;
        waBadge.innerHTML = `<i class="fa-solid ${waOk ? 'fa-circle-check' : 'fa-shield-halved'}"></i> ${escapeHtml(wa.status_label || 'Check WABA Status')}`;
    }
    if (waMeta) {
        const accts = Array.isArray(wa.accounts) ? wa.accounts : (Array.isArray(wa.numbers) ? wa.numbers : []);
        const pref = wa.preferred_candidate || accts[0];
        if (pref) {
            waMeta.innerHTML = `<span><strong>Preferred Candidate:</strong> ${escapeHtml(pref.display_phone_number || '+91 98257 28291')} (CLOUD_API) &middot; ${accts.length} WABAs preserved &middot; Sending blocked</span>`;
        } else {
            waMeta.innerHTML = `<span>${escapeHtml(wa.error || wa.action_required || 'Dual WhatsApp accounts isolated; sending disabled.')}</span>`;
        }
    }
    if (waGuard) {
        waGuard.innerHTML = waPubEnabled
            ? '<i class="fa-solid fa-circle-check" style="color: var(--success);"></i> WhatsApp Broadcast On'
            : '<i class="fa-solid fa-shield-halved" style="color: var(--warning);"></i> WhatsApp Dispatch Guardrail Off';
    }
    if (waCap) {
        waCap.textContent = wa.quality_rating ? `Quality: ${wa.quality_rating}` : 'Safely Isolated';
    }
}

// Lightweight in-session cache for /api/integrations/status (avoids 15s Graph API stalls on every tab switch)
window._ppIntegrationsCache = { ts: 0, data: null, pending: null };

async function fetchIntegrationsStatusCached(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && window._ppIntegrationsCache.data && (now - window._ppIntegrationsCache.ts) < 60000) {
        return window._ppIntegrationsCache.data;
    }
    if (!forceRefresh && window._ppIntegrationsCache.pending) {
        return window._ppIntegrationsCache.pending;
    }
    const req = authFetch('/api/integrations/status')
        .then(r => (r.ok ? r.json() : {}))
        .then(data => {
            if (data && (data.meta || data.linkedin || data.whatsapp)) {
                window._ppIntegrationsCache = { ts: Date.now(), data, pending: null };
            } else {
                window._ppIntegrationsCache.pending = null;
            }
            return data;
        })
        .catch(err => {
            window._ppIntegrationsCache.pending = null;
            throw err;
        });
    window._ppIntegrationsCache.pending = req;
    return req;
}

async function loadDashboardExecutiveMetrics() {
    try {
        // Kick off slow external Meta/LinkedIn/WhatsApp integrations probe in background so local KPIs render immediately
        const intPromise = fetchIntegrationsStatusCached(false).catch(() => ({}));

        const [dashRes, schedRes, accountsRes, draftsRes, statusRes] = await Promise.all([
            authFetch('/api/analytics/dashboard'),
            authFetch('/api/schedule?envelope=1&limit=250'),
            authFetch('/api/accounts'),
            authFetch('/api/drafts'),
            authFetch('/api/status')
        ]);

        const dashData = dashRes.ok ? await dashRes.json() : {};
        const schedData = schedRes.ok ? await schedRes.json() : {};
        const accountsData = accountsRes.ok ? await accountsRes.json() : {};
        const draftsData = draftsRes.ok ? await draftsRes.json() : {};
        const statusData = statusRes.ok ? await statusRes.json() : {};

        const allPosts = Array.isArray(schedData.posts) ? schedData.posts : (Array.isArray(schedData) ? schedData : []);
        const accounts = Array.isArray(accountsData.accounts) ? accountsData.accounts : [];
        const allDrafts = Array.isArray(draftsData.drafts) ? draftsData.drafts : [];

        const posts = filterItemsByDateRange(allPosts, dashboardDateFilter);
        const drafts = dashboardDateFilter === 'all' ? allDrafts : filterItemsByDateRange(allDrafts, dashboardDateFilter);

        // 1. Connected Social Accounts
        const connectedAccounts = accounts.filter(a => a.status === 'connected');
        const totalAccounts = accounts.length;
        const accountsEl = document.getElementById('kpi-accounts-count');
        const accountsDesc = document.getElementById('kpi-accounts-desc');
        if (accountsEl) accountsEl.textContent = `${connectedAccounts.length} / ${totalAccounts}`;
        if (accountsDesc) {
            accountsDesc.textContent = totalAccounts > 0
                ? `${Math.max(0, totalAccounts - connectedAccounts.length)} Standby / Auth Required · ${connectedAccounts.length} Active`
                : 'No configured social destinations';
        }

        syncSidebarNavBadges({
            draftsCount: draftsData.count !== undefined ? draftsData.count : allDrafts.length,
            connectedCount: connectedAccounts.length,
            totalAccountsCount: totalAccounts
        });

        // 2. Scheduled Posts Count (status == 'scheduled' or 'publishing')
        const scheduledPosts = posts.filter(p => p.status === 'scheduled' || p.status === 'publishing');
        const schedEl = document.getElementById('kpi-scheduled-count');
        const schedDesc = document.getElementById('kpi-scheduled-desc');
        if (schedEl) schedEl.textContent = String(scheduledPosts.length);
        if (schedDesc) {
            schedDesc.textContent = dashboardDateFilter === 'all' ? 'Queued in active database' : `In selected range (${dashboardDateFilter})`;
        }

        // 3. Drafts count (genuine backend value only)
        const draftsEl = document.getElementById('kpi-drafts-count');
        const draftsTotal = dashboardDateFilter === 'all'
            ? (draftsData.count !== undefined ? draftsData.count : (allDrafts.length || dashData.total_drafts || 0))
            : drafts.length;
        if (draftsEl) draftsEl.textContent = String(draftsTotal);

        // 4. Failed / Cancelled Posts
        const failedPosts = posts.filter(p => p.status === 'failed');
        const cancelledPosts = posts.filter(p => p.status === 'cancelled');
        const failedOrCancelled = failedPosts.length + cancelledPosts.length;
        const failedEl = document.getElementById('kpi-failed-count');
        const failedDesc = document.getElementById('kpi-failed-desc');
        if (failedEl) failedEl.textContent = String(failedOrCancelled);
        if (failedDesc) failedDesc.textContent = `${failedPosts.length} Failed · ${cancelledPosts.length} Cancelled`;

        // 5. Successfully Published Count & Genuine Success Rate
        const publishedPosts = posts.filter(p => p.status === 'published');
        const pubCount = publishedPosts.length;
        const pubEl = document.getElementById('kpi-published-count');
        const pubDesc = document.getElementById('kpi-published-desc');
        if (pubEl) pubEl.textContent = String(pubCount);

        const realLiveCount = publishedPosts.filter(p => p.external_post_id && !String(p.external_post_id).includes('_sim_')).length;
        const simCount = pubCount - realLiveCount;
        if (pubDesc) {
            if (pubCount === 0) {
                pubDesc.textContent = statusData.publishing_enabled ? 'No dispatches yet' : 'Guardrail Safe Mode active';
            } else if (simCount > 0 && realLiveCount === 0) {
                pubDesc.textContent = `${simCount} simulated record${simCount === 1 ? '' : 's'} (no live IDs)`;
            } else {
                pubDesc.textContent = `${realLiveCount} live · ${simCount} simulated`;
            }
        }

        const totalAttempts = pubCount + failedPosts.length;
        const rateEl = document.getElementById('kpi-success-rate');
        const rateFill = document.getElementById('kpi-success-fill');
        const rateDesc = document.getElementById('kpi-success-desc');
        if (totalAttempts > 0) {
            const successRate = (pubCount / totalAttempts) * 100;
            if (rateEl) rateEl.textContent = `${successRate.toFixed(1)}%`;
            if (rateFill) rateFill.style.width = `${Math.min(100, Math.max(0, successRate))}%`;
            if (rateDesc) rateDesc.textContent = `From ${totalAttempts} recorded dispatch attempt${totalAttempts === 1 ? '' : 's'}`;
        } else {
            if (rateEl) rateEl.textContent = '—';
            if (rateFill) rateFill.style.width = '0%';
            if (rateDesc) rateDesc.textContent = 'No completed attempts in range';
        }

        // 6. Render Publishing Feed & Upcoming Queue immediately, then hydrate Gateway Tiles when /api/integrations/status resolves
        renderRecentPublishedFeed(posts, statusData);
        renderUpcomingQueue(scheduledPosts);

        intPromise.then(intData => {
            updateGatewayTilesFromBackend(intData, statusData, accounts);
        });

    } catch (e) {
        console.warn('Could not load executive dashboard metrics', e);
        renderRecentPublishedFeed([], {});
        renderUpcomingQueue([]);
    }
}

// Render Recent Publishing Feed strictly from real database records (never fabricated)
function renderRecentPublishedFeed(posts, statusData) {
    const feedEl = document.getElementById('dashboard-published-feed');
    const modeBadge = document.getElementById('dashboard-feed-mode-badge');
    if (!feedEl) return;

    const published = (posts || []).filter(p => p.status === 'published');
    const liveCount = published.filter(p => p.external_post_id && !String(p.external_post_id).includes('_sim_')).length;

    if (modeBadge) {
        if (published.length === 0) {
            modeBadge.className = 'badge badge-neutral';
            modeBadge.innerHTML = statusData && statusData.publishing_enabled
                ? '<i class="fa-solid fa-database"></i> Awaiting First Live Post'
                : '<i class="fa-solid fa-shield-halved"></i> Guardrail Safe Mode (Off)';
        } else if (liveCount > 0) {
            modeBadge.className = 'badge badge-published';
            modeBadge.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${liveCount} Live Provider ID${liveCount === 1 ? '' : 's'}`;
        } else {
            modeBadge.className = 'badge badge-warning';
            modeBadge.innerHTML = `<i class="fa-solid fa-flask"></i> Simulated Records Only`;
        }
    }

    if (published.length === 0) {
        feedEl.innerHTML = `
            <div class="empty-state" style="padding: 2.25rem 1.25rem;">
                <i class="fa-solid fa-tower-broadcast empty-state-icon" style="color: var(--primary);"></i>
                <div class="empty-state-title">No Published Posts Recorded Yet</div>
                <p class="empty-state-desc">Real provider post IDs will appear here once posts are dispatched with publishing enabled. In Guardrail Safe Mode, external APIs are never triggered.</p>
                <div style="display: flex; gap: 0.6rem; justify-content: center; flex-wrap: wrap; margin-top: 0.75rem;">
                    <button class="btn btn-sm btn-primary" onclick="openModal('add')">
                        <i class="fa-solid fa-plus"></i> Create Scheduled Post
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="loadTab('history')">
                        <i class="fa-solid fa-clock-rotate-left"></i> Inspect History
                    </button>
                </div>
            </div>
        `;
        return;
    }

    const platformIcons = {
        'facebook': { icon: 'fa-brands fa-facebook', name: 'Facebook Page', color: '#1877f2', bg: 'rgba(24, 119, 242, 0.12)' },
        'instagram': { icon: 'fa-brands fa-instagram', name: 'Instagram Professional', color: '#e1306c', bg: 'rgba(225, 48, 108, 0.12)' },
        'linkedin': { icon: 'fa-brands fa-linkedin-in', name: 'LinkedIn', color: '#0a66c2', bg: 'rgba(10, 102, 194, 0.12)' },
        'whatsapp': { icon: 'fa-brands fa-whatsapp', name: 'WhatsApp Cloud', color: '#059669', bg: 'var(--success-soft)' }
    };

    feedEl.innerHTML = published.slice(0, 8).map(post => {
        const plat = post.post_type || 'facebook';
        const pInfo = platformIcons[plat] || platformIcons['facebook'];
        const extId = post.external_post_id || '';
        const isSimulated = !extId || String(extId).includes('_sim_');
        const pubTime = post.local_display || post.published_at || post.scheduled_for || post.created_at || 'Recorded';

        return `
            <div class="published-feed-card" style="display: flex; justify-content: space-between; align-items: flex-start; padding: 1.1rem 1.25rem; border-bottom: 1px solid var(--border); gap: 1rem; flex-wrap: wrap;">
                <div class="published-feed-left" style="display: flex; gap: 0.9rem; align-items: flex-start; flex: 1; min-width: 240px;">
                    <div class="published-thumb-wrap" style="width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; background: ${pInfo.bg}; border: 1px solid var(--border); flex-shrink: 0;">
                        <i class="${pInfo.icon}" style="font-size: 1.25rem; color: ${pInfo.color};"></i>
                    </div>
                    <div class="published-meta-wrap" style="flex: 1; min-width: 0;">
                        <div class="published-headline-row" style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.35rem;">
                            <span style="font-weight: 700; font-size: 0.94rem; color: var(--text-primary);">${escapeHtml(post.brand_name || 'GAATHA Brand')}</span>
                            <span class="platform-pill ${plat}" style="font-size: 0.72rem; padding: 0.15rem 0.5rem;">
                                <i class="${pInfo.icon}"></i> ${pInfo.name}
                            </span>
                            ${isSimulated ? `
                                <span class="badge badge-warning">
                                    <i class="fa-solid fa-flask"></i> Simulated (Not Live)
                                </span>
                            ` : `
                                <span class="badge badge-published">
                                    <i class="fa-solid fa-circle-check"></i> Live Provider ID
                                </span>
                            `}
                        </div>
                        <div class="published-caption-snippet" style="font-size: 0.88rem; color: var(--text-secondary); line-height: 1.45; margin-bottom: 0.35rem;" title="${escapeHtml(post.message || '')}">
                            ${escapeHtml(post.message ? (post.message.length > 140 ? post.message.substring(0, 140) + '...' : post.message) : 'Media post.')}
                        </div>
                        <div style="font-size: 0.76rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
                            <span><i class="fa-regular fa-clock"></i> ${escapeHtml(pubTime)}</span>
                            <span>&middot;</span>
                            <span>External ID: <code style="background: var(--bg-surface-subtle); padding: 0.1rem 0.4rem; border-radius: 4px; color: var(--text-primary);">${escapeHtml(extId || 'none')}</code></span>
                        </div>
                    </div>
                </div>

                <div class="published-actions" style="display: flex; gap: 0.5rem; align-items: center;">
                    <button class="btn btn-sm btn-secondary" onclick="loadTab('history')" title="Inspect History Log">
                        <i class="fa-solid fa-clock-rotate-left"></i>
                        <span>History</span>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Render Upcoming Scheduled Posts Queue
function renderUpcomingQueue(scheduledPosts) {
    const queueEl = document.getElementById('dashboard-upcoming-queue');
    if (!queueEl) return;

    if (!scheduledPosts || scheduledPosts.length === 0) {
        queueEl.innerHTML = `
            <div class="empty-state" style="padding: 2.25rem 1.25rem;">
                <i class="fa-solid fa-calendar-check empty-state-icon" style="color: var(--primary);"></i>
                <div class="empty-state-title">No Posts Queued For Release</div>
                <p class="empty-state-desc">Your publishing queue is clear. Use the composer or calendar to schedule announcements across connected channels.</p>
                <button class="btn btn-sm btn-primary" onclick="openModal('add')" style="margin-top: 0.75rem;">
                    <i class="fa-solid fa-plus"></i> Compose New Post
                </button>
            </div>
        `;
        return;
    }

    const platformIcons = {
        'facebook': 'fa-brands fa-facebook',
        'instagram': 'fa-brands fa-instagram',
        'linkedin': 'fa-brands fa-linkedin-in',
        'whatsapp': 'fa-brands fa-whatsapp'
    };

    queueEl.innerHTML = `
        <div class="table-responsive queue-table-wrap">
            <table class="data-table" style="width: 100%;">
                <thead>
                    <tr>
                        <th>Scheduled For</th>
                        <th>Brand</th>
                        <th>Platform</th>
                        <th>Message Preview</th>
                        <th>Status</th>
                        <th style="text-align: right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${scheduledPosts.slice(0, 6).map(p => {
                        const plat = p.post_type || 'facebook';
                        const pIcon = platformIcons[plat] || 'fa-solid fa-share-nodes';
                        const timeStr = p.local_display || p.scheduled_for || 'Upcoming';
                        const preview = p.message ? (p.message.length > 60 ? p.message.substring(0, 60) + '...' : p.message) : 'Media post';
                        const st = (p.status || 'scheduled').toLowerCase();
                        const stClass = st === 'publishing' ? 'badge-publishing' : 'badge-scheduled';

                        return `
                            <tr>
                                <td style="font-weight: 600; font-size: 0.85rem; white-space: nowrap;"><i class="fa-regular fa-clock"></i> ${escapeHtml(timeStr)}</td>
                                <td><span class="badge badge-primary">${escapeHtml(p.brand_name || 'Brand #' + (p.brand_id || 1))}</span></td>
                                <td>
                                    <span class="platform-pill ${plat}" style="font-size: 0.75rem; padding: 0.15rem 0.5rem;">
                                        <i class="${pIcon}"></i> ${plat.toUpperCase()}
                                    </span>
                                </td>
                                <td style="font-size: 0.85rem; color: var(--text-secondary); max-width: 280px;" title="${escapeHtml(p.message || '')}">${escapeHtml(preview)}</td>
                                <td><span class="badge ${stClass}"><i class="fa-solid fa-clock"></i> ${escapeHtml(st)}</span></td>
                                <td style="text-align: right;">
                                    <button class="btn btn-sm btn-secondary" onclick="openModal('edit', ${p.id}, '${plat}')" title="Review or Edit Scheduled Post">
                                        <i class="fa-solid fa-pen"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
        <div class="mobile-posts-list" style="padding: 0.25rem 0;">
            ${scheduledPosts.slice(0, 6).map(p => {
                const plat = p.post_type || 'facebook';
                const pIcon = platformIcons[plat] || 'fa-solid fa-share-nodes';
                const timeStr = p.local_display || p.scheduled_for || 'Upcoming';
                const preview = p.message ? (p.message.length > 100 ? p.message.substring(0, 100) + '...' : p.message) : 'Media post';
                return `
                    <div class="mobile-post-card">
                        <div class="mobile-post-header">
                            <span class="platform-pill ${plat}" style="font-size: 0.72rem;"><i class="${pIcon}"></i> ${plat.toUpperCase()}</span>
                            <span class="badge badge-scheduled">${escapeHtml(p.status || 'scheduled')}</span>
                        </div>
                        <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.3rem;">${escapeHtml(p.brand_name || 'Brand #' + (p.brand_id || 1))} &middot; ${escapeHtml(timeStr)}</div>
                        <div style="font-size: 0.82rem; color: var(--text-secondary); margin-bottom: 0.65rem;">${escapeHtml(preview)}</div>
                        <div class="mobile-post-actions">
                            <button class="btn btn-sm btn-secondary" onclick="openModal('edit', ${p.id}, '${plat}')"><i class="fa-solid fa-pen"></i> Edit</button>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}
// Count total posts across active organization
async function loadDashboardTotalPosts() {
    try {
        const res = await authFetch('/api/schedule?envelope=1');
        if (res.ok) {
            const data = await res.json();
            const total = data.count !== undefined ? data.count : (Array.isArray(data) ? data.length : 0);
            const totalEl = document.getElementById('kpi-total-posts');
            if (totalEl) totalEl.textContent = total;
        }
    } catch (e) {
        console.warn("Could not calculate total queued posts", e);
    }
}

function updateDashboardMetrics(data) {
    const pubEnabled = data && data.publishing_enabled;
    const dot = document.getElementById('system-pulsing-dot');
    const indicator = document.getElementById('global-status-indicator');
    if (dot) dot.style.backgroundColor = pubEnabled ? 'var(--success)' : '#f59e0b';
    if (indicator) indicator.textContent = pubEnabled ? 'Publishing Live' : 'Guardrail Active (Safe)';
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
    if (typeof loadDashboardExecutiveMetrics === 'function') {
        loadDashboardExecutiveMetrics();
    }
    if (typeof loadDashboardTotalPosts === 'function') {
        loadDashboardTotalPosts();
    }
    const filter = document.getElementById('dashboard-filter');
    if (filter && filter.value) {
        filterDashboardPosts(filter.value);
    }
    showToast('Dashboard data refreshed', 'info');
}

// ==========================================================================
// VIEW: Connected Social Accounts & Integrations Hub
// ==========================================================================
function renderAccounts(container) {
    container.innerHTML = `
        <div class="hub-hero fade-in">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <h2 style="font-size: 1.35rem; font-weight: 800; margin-bottom: 0.35rem;">
                        <i class="fa-solid fa-share-nodes text-primary"></i> Social Accounts &amp; Integrations Hub
                    </h2>
                    <p style="font-size: 0.9rem;">
                        Backend-verified connectivity, Meta property discovery, LinkedIn dual OAuth apps, and isolated WhatsApp Business gateways.
                    </p>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                    <button class="btn btn-sm btn-secondary" onclick="loadIntegrationsDashboard(true)">
                        <i class="fa-solid fa-rotate"></i> Refresh Integrations
                    </button>
                    <span class="badge badge-published">
                        <i class="fa-solid fa-shield-halved"></i> Secrets Protected
                    </span>
                    <span class="badge badge-warning" id="badge-publishing-guardrail">
                        <i class="fa-solid fa-lock"></i> Checking Guardrail...
                    </span>
                </div>
            </div>
        </div>

        <div id="integrations-dashboard-view">
            <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
                <i class="fa-solid fa-spinner fa-spin" style="font-size: 2rem; margin-bottom: 1rem; color: var(--primary);"></i>
                <p>Querying backend platform integrations (Meta Graph, LinkedIn OAuth, WhatsApp Cloud)...</p>
            </div>
        </div>
    `;

    setTimeout(loadIntegrationsDashboard, 20);
}

// Standardized Status Label Pill Generator using accessible semantic tokens
function getIntegrationsStatusBadge(statusLabel, actionRequired) {
    let badgeClass = 'badge-neutral';
    let icon = 'fa-circle-dot';
    const label = (statusLabel || 'Disconnected').trim();

    if (label === 'Live Publishing Ready') {
        badgeClass = 'badge-published';
        icon = 'fa-circle-check';
    } else if (label === 'Connected') {
        badgeClass = 'badge-info';
        icon = 'fa-check';
    } else if (label === 'Connected — Limited Permissions') {
        badgeClass = 'badge-warning';
        icon = 'fa-triangle-exclamation';
    } else if (label === 'Authentication Required') {
        badgeClass = 'badge-warning';
        icon = 'fa-key';
    } else if (label === 'Verification Required') {
        badgeClass = 'badge-failed';
        icon = 'fa-shield-halved';
    } else if (label === 'Credentials Configured') {
        badgeClass = 'badge-primary';
        icon = 'fa-wrench';
    } else if (label === 'Credentials Missing') {
        badgeClass = 'badge-failed';
        icon = 'fa-circle-xmark';
    } else if (label === 'Publishing Not Approved') {
        badgeClass = 'badge-warning';
        icon = 'fa-ban';
    } else if (label === 'Disconnected') {
        badgeClass = 'badge-neutral';
        icon = 'fa-circle-stop';
    }

    const titleAttr = actionRequired ? `title="${escapeHtml(actionRequired)}"` : '';
    return `<span class="badge ${badgeClass}" ${titleAttr}>
        <i class="fa-solid ${icon}"></i> ${escapeHtml(label)}
    </span>`;
}

// Fetch and render all platform integrations dynamically
async function loadIntegrationsDashboard(forceRefresh = false) {
    const view = document.getElementById('integrations-dashboard-view');
    if (!view) return;

    try {
        const [intData, brandsRes] = await Promise.all([
            fetchIntegrationsStatusCached(forceRefresh),
            authFetch('/api/brands')
        ]);

        if (!intData || (!intData.meta && !intData.linkedin && !intData.whatsapp && !intData.success)) {
            throw new Error('Failed to fetch platform integrations status');
        }
        const brands = brandsRes.ok ? await brandsRes.json() : [];

        // Update Guardrail pill with per-platform precision
        const guardrailPill = document.getElementById('badge-publishing-guardrail');
        if (guardrailPill) {
            const enabledPlats = Array.isArray(intData.enabled_publishing_platforms) ? intData.enabled_publishing_platforms : [];
            if (intData.publishing_enabled && enabledPlats.length > 0 && enabledPlats.length < 4) {
                guardrailPill.className = 'badge badge-published';
                guardrailPill.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> Scoped Live: ${enabledPlats.map(p => escapeHtml(p.toUpperCase())).join(', ')} (WhatsApp Off)`;
            } else if (intData.publishing_enabled) {
                guardrailPill.className = 'badge badge-published';
                guardrailPill.innerHTML = '<i class="fa-solid fa-tower-broadcast"></i> Live Publishing Enabled';
            } else {
                guardrailPill.className = 'badge badge-warning';
                guardrailPill.innerHTML = '<i class="fa-solid fa-lock"></i> Standby (POSTPILOT_PUBLISHING_ENABLED=0)';
            }
        }

        const meta = intData.meta || {};
        const linkedin = intData.linkedin || {};
        const whatsapp = intData.whatsapp || {};

        let html = '';

        // =========================================================================
        // 1. META ECOSYSTEM: FACEBOOK PAGES & LINKED INSTAGRAM
        // =========================================================================
        const pages = meta.pages || [];
        const igAccounts = meta.instagram_accounts || [];

        html += `
            <div class="hub-hero hub-hero--meta">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0.3rem;">
                            <i class="fa-brands fa-facebook" style="color: #1877f2;"></i> Meta Brand Ecosystem (Facebook &amp; Instagram)
                        </h2>
                        <p style="font-size: 0.88rem;">
                            Discovered from Meta Graph API. Explicit brand mapping enforces workspace isolation.
                        </p>
                    </div>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        ${getIntegrationsStatusBadge(meta.status_label || (meta.token_valid ? 'Connected' : 'Credentials Configured'), meta.action_required)}
                        <span class="badge badge-info">
                            <i class="fa-solid fa-layer-group"></i> ${pages.length} Pages &middot; ${igAccounts.length} Instagram
                        </span>
                    </div>
                </div>
            </div>

            <!-- Facebook Pages Section -->
            <div style="margin-bottom: 1.5rem;">
                <h3 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 0.75rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-brands fa-facebook" style="color: #1877f2;"></i> Discovered Facebook Pages (${pages.length})
                </h3>
                <div class="accounts-grid">
                    ${pages.map(p => {
                        const brandOptions = brands.map(b => `
                            <option value="${b.id}" ${b.id === p.assigned_brand_id ? 'selected' : ''}>
                                ${escapeHtml(b.name)}
                            </option>
                        `).join('');

                        return `
                            <div class="account-card" id="card-fb-${p.id}">
                                <div class="account-card-header">
                                    <div class="account-identity">
                                        <div class="account-avatar" style="background: #1877f2; color: #fff;">
                                            <i class="fa-brands fa-facebook-f"></i>
                                        </div>
                                        <div class="account-meta">
                                            <h3>${escapeHtml(p.name)}</h3>
                                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                                <span class="platform-pill facebook"><i class="fa-brands fa-facebook"></i> ${escapeHtml(p.category || 'Facebook Page')}</span>
                                                ${p.assigned_brand_name ? `<span class="badge badge-info"><i class="fa-solid fa-tag"></i> ${escapeHtml(p.assigned_brand_name)}</span>` : '<span class="badge badge-neutral">Unassigned</span>'}
                                            </div>
                                        </div>
                                    </div>
                                    ${getIntegrationsStatusBadge(p.status_label, p.action_required)}
                                </div>

                                <div class="account-details-list">
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Page ID</span>
                                        <code class="account-detail-value">${escapeHtml(p.id)}</code>
                                    </div>
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Publishing Capability</span>
                                        <span class="badge ${p.can_publish ? 'badge-success' : 'badge-warning'}">
                                            ${p.can_publish ? '<i class="fa-solid fa-check"></i> Allowed (CREATE_CONTENT)' : '<i class="fa-solid fa-triangle-exclamation"></i> Restricted'}
                                        </span>
                                    </div>
                                    ${p.action_required ? `
                                        <div class="account-detail-item" style="flex-direction: column; align-items: flex-start; gap: 0.25rem;">
                                            <span class="account-detail-label" style="color: #b45309;">Notice</span>
                                            <div style="font-size: 0.8rem; color: #b45309; line-height: 1.35;">${escapeHtml(p.action_required)}</div>
                                        </div>
                                    ` : ''}
                                </div>

                                <!-- Brand Mapping Assignment Dropdown -->
                                <div style="margin-top: 1rem; padding-top: 0.85rem; border-top: 1px solid var(--border-color, #e2e8f0);">
                                    <label style="display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.35rem;">
                                        Assign to GAATHA Brand Workspace:
                                    </label>
                                    <div style="display: flex; gap: 0.4rem; align-items: center;">
                                        <select id="select-brand-fb-${p.id}" class="form-control" style="flex: 1; font-size: 0.85rem; padding: 0.35rem 0.5rem; height: auto;">
                                            <option value="">-- Unassigned --</option>
                                            ${brandOptions}
                                        </select>
                                        <button class="btn btn-sm btn-primary" onclick="saveSocialPropertyMapping('facebook', '${p.id}', '${escapeAttr(p.name)}', 'select-brand-fb-${p.id}', '${(p.tasks||[]).join(',')}', 'meta_graph')" title="Save brand workspace mapping">
                                            <i class="fa-solid fa-floppy-disk"></i> Save
                                        </button>
                                        ${p.account_id ? `
                                            <button class="btn btn-sm btn-danger" onclick="unmapSocialProperty(${p.account_id}, '${escapeAttr(p.name)}')" title="Unlink from brand workspace">
                                                <i class="fa-solid fa-link-slash"></i>
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>

            <!-- Instagram Accounts Section -->
            <div style="margin-bottom: 2rem;">
                <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 0.75rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-brands fa-instagram" style="color: #e1306c;"></i> Discovered Instagram Business Accounts (${igAccounts.length})
                </h3>
                <div class="accounts-grid">
                    ${igAccounts.map(ig => {
                        const brandOptions = brands.map(b => `
                            <option value="${b.id}" ${b.id === ig.assigned_brand_id ? 'selected' : ''}>
                                ${escapeHtml(b.name)}
                            </option>
                        `).join('');

                        return `
                            <div class="account-card" id="card-ig-${ig.id}">
                                <div class="account-card-header">
                                    <div class="account-identity">
                                        <div class="account-avatar" style="background: linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%); color: #fff;">
                                            <i class="fa-brands fa-instagram"></i>
                                        </div>
                                        <div class="account-meta">
                                            <h3>${escapeHtml(ig.username || ig.name)}</h3>
                                            <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                                <span class="platform-pill instagram"><i class="fa-brands fa-instagram"></i> Instagram Business</span>
                                                ${ig.assigned_brand_name ? `<span class="badge badge-info"><i class="fa-solid fa-tag"></i> ${escapeHtml(ig.assigned_brand_name)}</span>` : '<span class="badge badge-neutral">Unassigned</span>'}
                                            </div>
                                        </div>
                                    </div>
                                    ${getIntegrationsStatusBadge(ig.status_label, ig.action_required)}
                                </div>

                                <div class="account-details-list">
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Instagram ID</span>
                                        <code class="account-detail-value">${escapeHtml(ig.id)}</code>
                                    </div>
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Linked Facebook Page</span>
                                        <span class="account-detail-value" style="font-size: 0.85rem;">${escapeHtml(ig.linked_facebook_page_name || 'N/A')}</span>
                                    </div>
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Audience &amp; Media</span>
                                        <span class="account-detail-value" style="font-size: 0.85rem;">
                                            ${ig.followers_count !== undefined ? Number(ig.followers_count).toLocaleString() : '0'} followers · ${ig.media_count || 0} posts
                                        </span>
                                    </div>
                                    <div class="account-detail-item">
                                        <span class="account-detail-label">Publishing Eligibility</span>
                                        <span class="badge ${ig.can_publish ? 'badge-success' : 'badge-warning'}">
                                            ${ig.can_publish ? '<i class="fa-solid fa-check"></i> Eligible (Content Publishing)' : '<i class="fa-solid fa-triangle-exclamation"></i> Limited'}
                                        </span>
                                    </div>
                                </div>

                                <!-- Brand Mapping Assignment Dropdown -->
                                <div style="margin-top: 1rem; padding-top: 0.85rem; border-top: 1px solid var(--border-color, #e2e8f0);">
                                    <label style="display: block; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.35rem;">
                                        Assign to GAATHA Brand Workspace:
                                    </label>
                                    <div style="display: flex; gap: 0.4rem; align-items: center;">
                                        <select id="select-brand-ig-${ig.id}" class="form-control" style="flex: 1; font-size: 0.85rem; padding: 0.35rem 0.5rem; height: auto;">
                                            <option value="">-- Unassigned --</option>
                                            ${brandOptions}
                                        </select>
                                        <button class="btn btn-sm btn-primary" onclick="saveSocialPropertyMapping('instagram', '${ig.id}', '${escapeAttr(ig.username || ig.name)}', 'select-brand-ig-${ig.id}', 'instagram_content_publish', 'meta_graph')" title="Save brand workspace mapping">
                                            <i class="fa-solid fa-floppy-disk"></i> Save
                                        </button>
                                        ${ig.account_id ? `
                                            <button class="btn btn-sm btn-danger" onclick="unmapSocialProperty(${ig.account_id}, '${escapeAttr(ig.username || ig.name)}')" title="Unlink from brand workspace">
                                                <i class="fa-solid fa-link-slash"></i>
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;

        // =========================================================================
        // 2. LINKEDIN ENTERPRISE ECOSYSTEM (DUAL APPLICATIONS)
        // =========================================================================
        const liApps = linkedin.apps || [];
        html += `
            <div class="hub-hero hub-hero--linkedin" style="margin-top: 2rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0.3rem;">
                            <i class="fa-brands fa-linkedin" style="color: #0a66c2;"></i> LinkedIn Enterprise Ecosystem (Dual Applications)
                        </h2>
                        <p style="font-size: 0.88rem;">
                            Independent OAuth 2.0 company integrations for Aidni Global LLP and Gaatha Ventures Sh.p.k.
                        </p>
                    </div>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        <span class="badge badge-info">
                            <i class="fa-solid fa-shield-halved"></i> 3-Legged OAuth Mandatory
                        </span>
                        <span class="badge badge-neutral">
                            <i class="fa-solid fa-code-branch"></i> REST Posts API
                        </span>
                    </div>
                </div>
            </div>

            <div class="accounts-grid" style="margin-bottom: 2rem;">
                ${liApps.map(app => {
                    const scopes = (app.token_scopes && app.token_scopes.length)
                        ? app.token_scopes
                        : (app.requested_scopes || []);
                    const hasCompanyScope = Boolean(app.company_publishing_ready || scopes.includes('w_organization_social'));
                    let eligibilityBanner = '';
                    if (!app.user_authenticated) {
                        eligibilityBanner = `
                            <div class="notice-callout notice-callout--warning" style="margin-top: 0.5rem;">
                                <i class="fa-solid fa-key"></i>
                                <div>
                                    <strong>Authentication Required</strong><br>
                                    Authorize via LinkedIn OAuth first to acquire an active token before publishing attempts.
                                </div>
                            </div>
                        `;
                    } else if (!hasCompanyScope) {
                        eligibilityBanner = `
                            <div class="notice-callout notice-callout--info" style="margin-top: 0.5rem;">
                                <i class="fa-solid fa-circle-info"></i>
                                <div>
                                    <strong>Personal Posting:</strong> Available via <code>w_member_social</code>.<br>
                                    <strong>Company Page Posting:</strong> Pending <strong>Community Management API</strong> approval (<code>w_organization_social</code>) in LinkedIn Developer Portal.
                                </div>
                            </div>
                        `;
                    } else {
                        eligibilityBanner = `
                            <div class="notice-callout notice-callout--success" style="margin-top: 0.5rem;">
                                <i class="fa-solid fa-circle-check"></i>
                                <div>
                                    <strong>Personal &amp; Company Page Posting:</strong> Active with <code>w_organization_social</code> approval.
                                </div>
                            </div>
                        `;
                    }

                    return `
                        <div class="account-card" id="card-linkedin-${app.app_key}">
                            <div class="account-card-header">
                                <div class="account-identity">
                                    <div class="account-avatar" style="background: #0a66c2; color: #fff;">
                                        <i class="fa-brands fa-linkedin-in"></i>
                                    </div>
                                    <div class="account-meta">
                                        <h3>${escapeHtml(app.name)}</h3>
                                        <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                            <span class="platform-pill linkedin"><i class="fa-brands fa-linkedin"></i> Company Page</span>
                                            <span class="badge badge-info">
                                                Org ID: ${escapeHtml(app.organization_id)}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                ${getIntegrationsStatusBadge(app.status_label, app.action_required)}
                            </div>

                            <div class="account-details-list">
                                <div class="account-detail-item">
                                    <span class="account-detail-label">Client Credentials</span>
                                    <span class="badge ${app.client_id_configured && app.client_secret_configured ? 'badge-success' : 'badge-danger'}">
                                        ${app.client_id_configured && app.client_secret_configured ? '<i class="fa-solid fa-check"></i> Configured in .env' : 'Missing in .env'}
                                    </span>
                                </div>
                                <div class="account-detail-item">
                                    <span class="account-detail-label">Redirect URI</span>
                                    <code class="account-detail-value" style="font-size: 0.75rem; word-break: break-all;">${escapeHtml(app.redirect_uri)}</code>
                                </div>
                                <div class="account-detail-item">
                                    <span class="account-detail-label">User Authentication</span>
                                    <span class="account-detail-value" style="font-size: 0.85rem;">
                                        ${app.user_authenticated ? `<span class="badge badge-success"><i class="fa-solid fa-check"></i> ${escapeHtml(app.authenticated_member || 'Active Member')}</span>` : '<span class="badge badge-warning"><i class="fa-solid fa-key"></i> Unauthenticated (OAuth Required)</span>'}
                                    </span>
                                </div>
                                <div class="account-detail-item">
                                    <span class="account-detail-label">${(app.token_scopes && app.token_scopes.length) ? 'Granted Scopes' : 'Requested Scopes'}</span>
                                    <code class="account-detail-value" style="font-size: 0.75rem;">${escapeHtml(
                                        (app.token_scopes && app.token_scopes.length)
                                            ? app.token_scopes.join(', ')
                                            : ((app.requested_scopes && app.requested_scopes.length)
                                                ? app.requested_scopes.join(', ')
                                                : (app.app_key === 'gaatha_ventures' ? 'w_member_social' : 'openid, profile, email, w_member_social'))
                                    )}</code>
                                </div>
                            </div>

                            ${eligibilityBanner}

                            <div style="display: flex; gap: 0.5rem; margin-top: 1.25rem; flex-wrap: wrap;">
                                <a class="btn btn-sm btn-primary" href="${app.connect_url}" style="flex: 1; text-align: center; text-decoration: none;">
                                    <i class="fa-brands fa-linkedin"></i> ${app.user_authenticated ? 'Reconnect OAuth' : 'Connect via LinkedIn OAuth'}
                                </a>
                                <a class="btn btn-sm btn-secondary" href="${app.connect_url}" title="Start fresh OAuth authorization">
                                    <i class="fa-solid fa-arrow-rotate-right"></i> Re-authorize
                                </a>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;

        // =========================================================================
        // 3. WHATSAPP BUSINESS CLOUD API (DUAL ACCOUNT CONFIGURATION)
        // =========================================================================
        const prefWa = whatsapp.preferred_candidate || (Array.isArray(whatsapp.accounts) && whatsapp.accounts[0]) || {
            display_phone_number: '+91 98257 28291',
            phone_number_id: '1298748379987770',
            waba_id: '1471882524763501',
            verified_name: 'Aidni Global',
            platform_type: 'CLOUD_API',
            phone_status: 'CONNECTED',
            code_verification_status: 'NOT_VERIFIED',
            approved_templates_count: 0,
            health_can_send: 'BLOCKED',
            billing_readiness: { ready: false, reason: 'Payment method missing/invalid (Meta Error 141006)' },
            messaging_eligibility: { eligible: false, reason: 'Cloud API connected, but sending blocked pending verification/readiness' }
        };
        const legWa = whatsapp.preserved_disconnected_account || (Array.isArray(whatsapp.accounts) && whatsapp.accounts[1]) || {
            display_phone_number: '+91 90990 28291',
            phone_number_id: '1171737406016871',
            waba_id: '1370721214882653',
            verified_name: 'Gaatha Ventures',
            platform_type: 'ON_PREMISE',
            phone_status: 'DISCONNECTED',
            code_verification_status: 'NOT_VERIFIED',
            approved_templates_count: 0,
            health_can_send: 'BLOCKED',
            billing_readiness: { ready: false, reason: 'Payment method missing/invalid (Meta Error 141006)' },
            messaging_eligibility: { eligible: false, reason: 'Disconnected ON_PREMISE account preserved only; never activated' }
        };

        html += `
            <div class="hub-hero hub-hero--whatsapp" style="margin-top: 2rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0.3rem;">
                            <i class="fa-brands fa-whatsapp" style="color: #059669;"></i> Dual WhatsApp Business Cloud API Configuration
                        </h2>
                        <p style="font-size: 0.88rem;">
                            Both registered accounts are tracked independently. <strong>+91 98257 28291</strong> is retained as the preferred future broadcasting candidate; <strong>+91 90990 28291</strong> is preserved disconnected without activation or auto brand binding.
                        </p>
                    </div>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        <span class="badge badge-warning"><i class="fa-solid fa-lock"></i> WHATSAPP_PUBLISHING_ENABLED=0</span>
                        ${getIntegrationsStatusBadge(whatsapp.status_label || 'Verification Required', whatsapp.action_required)}
                    </div>
                </div>
            </div>

            <div class="accounts-grid" style="margin-bottom: 1.5rem;">
                <!-- Account 1: Preferred Future Broadcasting Candidate (+91 98257 28291) -->
                <div class="account-card" style="border-left: 4px solid var(--primary);">
                    <div class="account-card-header">
                        <div class="account-identity">
                            <div class="account-avatar" style="background: var(--success-soft); color: var(--success);">
                                <i class="fa-brands fa-whatsapp"></i>
                            </div>
                            <div class="account-meta">
                                <h3>${escapeHtml(prefWa.verified_name || 'Aidni Global')} &middot; ${escapeHtml(prefWa.display_phone_number || '+91 98257 28291')}</h3>
                                <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                    <span class="badge badge-info"><i class="fa-solid fa-star"></i> Preferred Future Candidate</span>
                                    <span class="badge badge-success">${escapeHtml(prefWa.platform_type || 'CLOUD_API')} &middot; ${escapeHtml(prefWa.phone_status || 'CONNECTED')}</span>
                                </div>
                            </div>
                        </div>
                        <span class="badge badge-warning">Sending Blocked</span>
                    </div>

                    <div class="account-details-list">
                        <div class="account-detail-item"><span class="account-detail-label">Phone Number</span><code class="account-detail-value">${escapeHtml(prefWa.display_phone_number || '+91 98257 28291')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">Phone Number ID</span><code class="account-detail-value">${escapeHtml(prefWa.phone_number_id || '1298748379987770')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">WABA ID</span><code class="account-detail-value">${escapeHtml(prefWa.waba_id || '1471882524763501')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">Connection Status</span><span class="badge badge-info">${escapeHtml(prefWa.platform_type || 'CLOUD_API')} &middot; ${escapeHtml(prefWa.phone_status || 'CONNECTED')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Verification Status</span><span class="badge ${prefWa.code_verification_status === 'VERIFIED' ? 'badge-success' : 'badge-warning'}">Business Verified &middot; OTP: ${escapeHtml(prefWa.code_verification_status || 'NOT_VERIFIED')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Messaging Eligibility</span><span class="badge badge-danger">${escapeHtml(prefWa.messaging_eligibility && prefWa.messaging_eligibility.eligible ? 'ELIGIBLE' : 'BLOCKED')} (${escapeHtml(prefWa.health_can_send || 'BLOCKED')})</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Template Readiness</span><span class="badge ${(prefWa.approved_templates_count || 0) > 0 ? 'badge-success' : 'badge-warning'}">${prefWa.approved_templates_count || 0} Approved on Meta</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Billing Readiness</span><span class="badge badge-danger">${escapeHtml((prefWa.billing_readiness && prefWa.billing_readiness.reason) || 'Payment Required (141006)')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Brand Assignment</span><span class="badge badge-neutral">Unassigned (Auto-binding Disabled)</span></div>
                    </div>

                    <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
                        <button class="btn btn-sm btn-success" onclick="loadTab('whatsapp')" style="flex: 1;">
                            <i class="fa-brands fa-whatsapp"></i> Open WhatsApp Studio
                        </button>
                    </div>
                </div>

                <!-- Account 2: Preserved Disconnected / Legacy .env Line (+91 90990 28291) -->
                <div class="account-card">
                    <div class="account-card-header">
                        <div class="account-identity">
                            <div class="account-avatar" style="background: var(--bg-surface-subtle); color: var(--text-muted); border: 1px solid var(--border);">
                                <i class="fa-brands fa-whatsapp"></i>
                            </div>
                            <div class="account-meta">
                                <h3>${escapeHtml(legWa.verified_name || 'Gaatha Ventures')} &middot; ${escapeHtml(legWa.display_phone_number || '+91 90990 28291')}</h3>
                                <div style="display: flex; gap: 0.35rem; margin-top: 0.2rem; flex-wrap: wrap;">
                                    <span class="badge badge-neutral"><i class="fa-solid fa-lock"></i> Preserved Legacy (.env Ref)</span>
                                    <span class="badge badge-warning">${escapeHtml(legWa.platform_type || 'ON_PREMISE')} &middot; ${escapeHtml(legWa.phone_status || 'DISCONNECTED')}</span>
                                </div>
                            </div>
                        </div>
                        <span class="badge badge-neutral">Never Activated</span>
                    </div>

                    <div class="account-details-list">
                        <div class="account-detail-item"><span class="account-detail-label">Phone Number</span><code class="account-detail-value">${escapeHtml(legWa.display_phone_number || '+91 90990 28291')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">Phone Number ID</span><code class="account-detail-value">${escapeHtml(legWa.phone_number_id || '1171737406016871')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">WABA ID</span><code class="account-detail-value">${escapeHtml(legWa.waba_id || '1370721214882653')}</code></div>
                        <div class="account-detail-item"><span class="account-detail-label">Connection Status</span><span class="badge badge-warning">${escapeHtml(legWa.platform_type || 'ON_PREMISE')} &middot; ${escapeHtml(legWa.phone_status || 'DISCONNECTED')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Verification Status</span><span class="badge badge-danger">Business: ${escapeHtml(legWa.business_verification_status || 'not_verified')} &middot; OTP: ${escapeHtml(legWa.code_verification_status || 'NOT_VERIFIED')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Messaging Eligibility</span><span class="badge badge-danger">INELIGIBLE (Disconnected Standby)</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Template Readiness</span><span class="badge badge-warning">${legWa.approved_templates_count || 0} Approved on Meta</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Billing Readiness</span><span class="badge badge-danger">${escapeHtml((legWa.billing_readiness && legWa.billing_readiness.reason) || 'Payment Required (141006)')}</span></div>
                        <div class="account-detail-item"><span class="account-detail-label">Brand Assignment</span><span class="badge badge-neutral">Unassigned (Preserved Only)</span></div>
                    </div>

                    <div class="notice-callout notice-callout--info" style="margin-top: 0.75rem;">
                        <i class="fa-solid fa-lock"></i>
                        <div>Preserved in .env without deletion, migration, or activation.</div>
                    </div>
                </div>
            </div>

            <div class="card" style="margin-bottom: 1.5rem; border-left: 4px solid var(--warning);">
                <h4 style="font-weight: 700; font-size: 0.95rem; margin-bottom: 0.65rem; color: var(--warning); display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-solid fa-list-check"></i> Manual Meta-Side Actions Required Before Activation (+91 98257 28291 Candidate)
                </h4>
                <ol style="margin: 0; padding-left: 1.25rem; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6;">
                    <li>Add billing/payment method on WABA <code>1471882524763501</code> (clears Error <code>141006</code>) and set WABA timezone (clears Error <code>141007</code>).</li>
                    <li>Complete OTP phone verification, 2-step PIN, and display name review for <code>+91 98257 28291</code> (<code>1298748379987770</code>).</li>
                    <li>Submit and obtain Meta <code>APPROVED</code> status for message templates, then subscribe App <code>1397769361108621</code> to <code>/api/webhooks/whatsapp</code>.</li>
                </ol>
            </div>
        `;

        // =========================================================================
        // 4. SECURITY & TOKEN ISOLATION ARCHITECTURE
        // =========================================================================
        html += `
            <div class="card" style="border-left: 4px solid var(--primary); background: var(--bg-surface-subtle); margin-top: 1.25rem;">
                <div style="display: flex; gap: 0.85rem; align-items: flex-start;">
                    <i class="fa-solid fa-shield-halved" style="color: var(--primary); font-size: 1.35rem; margin-top: 0.2rem;"></i>
                    <div>
                        <h4 style="font-weight: 700; font-size: 0.95rem; margin-bottom: 0.2rem; color: var(--text-primary);">Security &amp; Secret Isolation Architecture</h4>
                        <p style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.45; margin: 0;">
                            Meta system access tokens, LinkedIn client secrets, and WhatsApp bearer keys remain isolated on the server filesystem and environment store. They are never rendered or transmitted to browser storage.
                        </p>
                    </div>
                </div>
            </div>
        `;

        view.innerHTML = html;

    } catch (err) {
        view.innerHTML = `
            <div class="card" style="color: #ef4444; padding: 2rem; text-align: center;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; margin-bottom: 0.75rem;"></i>
                <h3 style="margin-bottom: 0.5rem;">Failed to Load Integrations</h3>
                <p style="color: #94a3b8; margin-bottom: 1rem;">${escapeHtml(err.message)}</p>
                <button class="btn btn-sm btn-primary" onclick="loadIntegrationsDashboard()">
                    <i class="fa-solid fa-rotate"></i> Retry
                </button>
            </div>
        `;
    }
}

// Map a social property (FB Page, IG account) to a GAATHA brand workspace
async function saveSocialPropertyMapping(platform, accountIdentifier, accountName, selectId, permissionsScope, appIdentifier) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const brandId = select.value;

    if (!brandId) {
        showToast('Please select a brand workspace to assign this property', 'warning');
        return;
    }

    try {
        const payload = {
            platform: platform,
            account_identifier: accountIdentifier,
            account_name: accountName,
            brand_id: parseInt(brandId, 10),
            permissions_scope: permissionsScope || 'standard',
            app_identifier: appIdentifier || 'meta_graph'
        };

        const res = await authFetch('/api/integrations/map', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
            showToast(`Property mapped successfully to ${data.brand_name || 'brand workspace'}`, 'success');
            loadIntegrationsDashboard();
        } else {
            showToast(`Mapping failed: ${data.error || 'Server error'}`, 'error');
        }
    } catch (err) {
        showToast(`Request error: ${err.message}`, 'error');
    }
}

// Unmap a social property
async function unmapSocialProperty(accountId, accountName) {
    if (!confirm(`Are you sure you want to unmap ${accountName || 'this property'} from its brand workspace?`)) {
        return;
    }

    try {
        const res = await authFetch(`/api/integrations/map/${accountId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            showToast('Property unmapped successfully', 'success');
            loadIntegrationsDashboard();
        } else {
            showToast(`Unmap failed: ${data.error || 'Server error'}`, 'error');
        }
    } catch (err) {
        showToast(`Request error: ${err.message}`, 'error');
    }
}

// Compatibility Aliases
function refreshAccountsList() {
    loadIntegrationsDashboard();
}

function loadLinkedInStatus() {
    loadIntegrationsDashboard();
}

function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

// ==========================================================================
// ==========================================================================
// VIEW: Guided 5-Step Post Composer (Modern SaaS Flow)
// ==========================================================================
let composerCurrentStep = 1;
let composerDestinations = {
    'fb_gaathasuite': { selected: true, name: 'GAATHA Suite (FB)', platform: 'facebook', brand_id: 1, meta: 'Facebook Page · ID 104690782333066', icon: 'fa-building-flag', color: '#4f46e5', statusLabel: 'Checking...', statusKind: 'neutral' },
    'fb_tour': { selected: false, name: 'Nexora Suite (FB)', platform: 'facebook', brand_id: 4, meta: 'Facebook Page · ID 967550829768297', icon: 'fa-earth-americas', color: '#0284c7', statusLabel: 'Checking...', statusKind: 'neutral' },
    'fb_nz': { selected: false, name: 'Phoenix Intl (FB)', platform: 'facebook', brand_id: 5, meta: 'Facebook Page · ID 954901604381882', icon: 'fa-passport', color: '#16a34a', statusLabel: 'Checking...', statusKind: 'neutral' },
    'fb_gaatha': { selected: false, name: 'Gaatha AI (FB)', platform: 'facebook', brand_id: 6, meta: 'Facebook Page · ID 1028368893692590', icon: 'fa-wand-magic-sparkles', color: '#9333ea', statusLabel: 'Checking...', statusKind: 'neutral' },
    'fb_grahak': { selected: false, name: 'GAATHA POS (FB)', platform: 'facebook', brand_id: 2, meta: 'Facebook Page · ID 61571408331302', icon: 'fa-scale-balanced', color: '#d97706', statusLabel: 'Checking...', statusKind: 'neutral' },
    'ig_gaathasuite': { selected: false, name: 'GAATHA Suite (IG)', platform: 'instagram', brand_id: 1, meta: '@nexora_suite · Professional', icon: 'fa-camera-retro', color: '#e1306c', statusLabel: 'Checking...', statusKind: 'neutral' },
    'ig_phoenix': { selected: false, name: 'Phoenix Intl (IG)', platform: 'instagram', brand_id: 5, meta: '@phoenixbygaatha · ID 17841471822022390', icon: 'fa-camera-retro', color: '#e1306c', statusLabel: 'Checking...', statusKind: 'neutral' },
    'li_aidni': { selected: false, name: 'Aidni Global LLP (LinkedIn)', platform: 'linkedin', brand_id: 2, meta: 'Company Page · Org ID 145240694', icon: 'fa-linkedin-in', color: '#0a66c2', statusLabel: 'Auth Required', statusKind: 'warning' },
    'li_gaatha': { selected: false, name: 'Gaatha Ventures Sh.p.k. (LinkedIn)', platform: 'linkedin', brand_id: 3, meta: 'Company Page · Org ID 145250613', icon: 'fa-linkedin-in', color: '#0a66c2', statusLabel: 'Auth Required', statusKind: 'warning' },
    'wa_gaatha': { selected: false, name: 'WhatsApp Cloud API (Standby)', platform: 'whatsapp', brand_id: 1, meta: 'Sender-Isolated Gateway · Verification Pending', icon: 'fa-whatsapp', color: '#059669', statusLabel: 'Isolated Standby', statusKind: 'warning' }
};

function setComposerStep(step) {
    if (step < 1 || step > 5) return;

    // Validation before moving forward
    if (step > 1 && composerCurrentStep === 1) {
        const anySelected = Object.values(composerDestinations).some(d => d.selected);
        if (!anySelected) {
            showToast('Please select at least one destination channel', 'error');
            return;
        }
    }

    if (step > 2 && composerCurrentStep === 2) {
        const caption = document.getElementById('view-composer-caption')?.value.trim();
        const file = document.getElementById('view-composer-file');
        if (!caption && (!file || file.files.length === 0)) {
            showToast('Please enter a caption or attach media before proceeding', 'error');
            return;
        }
    }

    composerCurrentStep = step;

    // Update stepper UI
    for (let i = 1; i <= 5; i++) {
        const node = document.getElementById(`step-node-${i}`);
        const pane = document.getElementById(`step-pane-${i}`);
        const line = document.getElementById(`step-line-${i}`);

        if (node) {
            node.classList.remove('active', 'completed');
            if (i === step) node.classList.add('active');
            else if (i < step) node.classList.add('completed');
        }

        if (pane) {
            if (i === step) pane.classList.add('active');
            else pane.classList.remove('active');
        }

        if (line) {
            if (i < step) line.classList.add('completed');
            else line.classList.remove('completed');
        }
    }

    // Update dynamic views
    if (step === 3) {
        syncComposerPreviews();
    } else if (step === 5) {
        updateComposerSummary();
    }
}

function toggleComposerDestination(key) {
    if (composerDestinations[key]) {
        composerDestinations[key].selected = !composerDestinations[key].selected;
        const card = document.getElementById(`dest-card-${key}`);
        if (card) {
            if (composerDestinations[key].selected) card.classList.add('selected');
            else card.classList.remove('selected');
        }
        updateSelectedDestCount();
    }
}

function updateSelectedDestCount() {
    const count = Object.values(composerDestinations).filter(d => d.selected).length;
    const countEl = document.getElementById('selected-dest-count-badge');
    if (countEl) countEl.textContent = `${count} Destinations Selected`;
}

function syncComposerPreviews() {
    const caption = document.getElementById('view-composer-caption')?.value.trim() || 'Your engaging social caption will render here across destinations...';
    
    // Facebook preview sync
    const fbCap = document.getElementById('v-fb-preview-caption');
    if (fbCap) fbCap.textContent = caption;

    // Instagram preview sync
    const igCap = document.getElementById('v-ig-preview-caption');
    if (igCap) igCap.textContent = caption;

    // LinkedIn preview sync
    const liCap = document.getElementById('v-li-preview-caption');
    if (liCap) liCap.textContent = caption;
}

function switchComposerPreviewTab(platform) {
    const fbBtn = document.getElementById('v-tab-btn-fb');
    const igBtn = document.getElementById('v-tab-btn-ig');
    const liBtn = document.getElementById('v-tab-btn-li');
    const fbBox = document.getElementById('v-mockup-container-fb');
    const igBox = document.getElementById('v-mockup-container-ig');
    const liBox = document.getElementById('v-mockup-container-li');

    [fbBtn, igBtn, liBtn].forEach(b => b?.classList.remove('active'));
    [fbBox, igBox, liBox].forEach(m => { if (m) m.style.display = 'none'; });

    if (platform === 'fb') {
        fbBtn?.classList.add('active');
        if (fbBox) fbBox.style.display = 'block';
    } else if (platform === 'ig') {
        igBtn?.classList.add('active');
        if (igBox) igBox.style.display = 'block';
    } else if (platform === 'li') {
        liBtn?.classList.add('active');
        if (liBox) liBox.style.display = 'block';
    }
}

function updateComposerSummary() {
    const summaryDestEl = document.getElementById('summary-dest-chips');
    const summaryCapEl = document.getElementById('summary-caption-text');
    const summaryTimeEl = document.getElementById('summary-scheduled-time');
    const summaryTzEl = document.getElementById('summary-timezone');
    const summaryMediaEl = document.getElementById('summary-media-badge');

    const selected = Object.values(composerDestinations).filter(d => d.selected);
    if (summaryDestEl) {
        summaryDestEl.innerHTML = selected.map(d => {
            const iconClass = d.platform === 'facebook' ? 'facebook' : (d.platform === 'instagram' ? 'instagram' : (d.platform === 'linkedin' ? 'linkedin' : 'whatsapp'));
            return `
                <span class="platform-pill ${d.platform}" style="font-size: 0.8rem; padding: 0.25rem 0.65rem;">
                    <i class="fa-brands fa-${iconClass}"></i>
                    ${escapeHtml(d.name)}
                </span>
            `;
        }).join('');
    }

    const caption = document.getElementById('view-composer-caption')?.value.trim() || 'No caption';
    if (summaryCapEl) summaryCapEl.textContent = caption;

    const dtVal = document.getElementById('view-composer-datetime')?.value;
    const tzVal = document.getElementById('view-composer-timezone')?.value || 'UTC';
    if (summaryTimeEl) summaryTimeEl.textContent = dtVal ? dtVal.replace('T', ' ') : 'Immediate (Continuous Periodic Loop)';
    if (summaryTzEl) summaryTzEl.textContent = tzVal;

    const fileInput = document.getElementById('view-composer-file');
    if (summaryMediaEl) {
        if (fileInput && fileInput.files.length > 0) {
            summaryMediaEl.innerHTML = `<i class="fa-solid fa-paperclip" style="color: var(--success);"></i> Media File: <strong>${escapeHtml(fileInput.files[0].name)}</strong>`;
        } else {
            summaryMediaEl.innerHTML = `<i class="fa-solid fa-font" style="color: var(--text-muted);"></i> Text-Only Post (No media attached)`;
        }
    }

    const preflightEl = document.getElementById('composer-preflight-list');
    if (preflightEl) {
        const unready = selected.filter(d => d.statusKind === 'warning' || d.statusKind === 'failed');
        const hasIgWithoutMedia = selected.some(d => d.platform === 'instagram') && (!fileInput || fileInput.files.length === 0);
        const items = [];
        if (unready.length > 0) {
            items.push(`<div><i class="fa-solid fa-triangle-exclamation" style="color: var(--warning);"></i> <strong>Pending Destination Setup:</strong> ${unready.map(u => escapeHtml(u.name) + ' (' + escapeHtml(u.statusLabel) + ')').join(', ')}. Live dispatch requires authorization/verification first.</div>`);
        } else {
            items.push(`<div><i class="fa-solid fa-check" style="color: var(--success);"></i> Selected destination tokens checked against current integration status.</div>`);
        }
        if (hasIgWithoutMedia) {
            items.push(`<div><i class="fa-solid fa-triangle-exclamation" style="color: var(--warning);"></i> Instagram posts require an attached image or reel video before live publishing.</div>`);
        } else {
            items.push(`<div><i class="fa-solid fa-check" style="color: var(--success);"></i> Media &amp; caption inputs formatted cleanly for selected destinations.</div>`);
        }
        items.push(`<div><i class="fa-solid fa-shield-halved" style="color: var(--primary);"></i> Publishing safety guardrails &amp; idempotent scheduling are enforced server-side.</div>`);
        preflightEl.innerHTML = items.join('');
    }
}

function renderComposerView(container) {
    composerCurrentStep = 1;

    container.innerHTML = `
        <div class="card" style="margin-bottom: 2rem;">
            <!-- Stepper Progress Header -->
            <div class="composer-stepper" aria-label="Post Creation Steps">
                <button type="button" class="step-node active" id="step-node-1" onclick="setComposerStep(1)">
                    <div class="step-number">1</div>
                    <span class="step-label">Destinations</span>
                </button>
                <div class="step-line" id="step-line-1"></div>

                <button type="button" class="step-node" id="step-node-2" onclick="setComposerStep(2)">
                    <div class="step-number">2</div>
                    <span class="step-label">Content &amp; Media</span>
                </button>
                <div class="step-line" id="step-line-2"></div>

                <button type="button" class="step-node" id="step-node-3" onclick="setComposerStep(3)">
                    <div class="step-number">3</div>
                    <span class="step-label">Previews</span>
                </button>
                <div class="step-line" id="step-line-3"></div>

                <button type="button" class="step-node" id="step-node-4" onclick="setComposerStep(4)">
                    <div class="step-number">4</div>
                    <span class="step-label">Publish Options</span>
                </button>
                <div class="step-line" id="step-line-4"></div>

                <button type="button" class="step-node" id="step-node-5" onclick="setComposerStep(5)">
                    <div class="step-number">5</div>
                    <span class="step-label">Final Review</span>
                </button>
            </div>

            <!-- STEP 1: DESTINATIONS -->
            <div class="composer-step-pane active" id="step-pane-1">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
                    <div>
                        <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">
                            <i class="fa-solid fa-share-nodes" style="color: var(--primary);"></i> Step 1: Select Publishing Destinations
                        </h3>
                        <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                            Choose one or more verified Facebook Pages, Instagram Accounts, or LinkedIn Company Pages.
                        </p>
                    </div>
                    <span class="badge badge-approved" id="selected-dest-count-badge" style="font-size: 0.82rem; padding: 0.35rem 0.75rem;">
                        1 Destination Selected
                    </span>
                </div>

                <div class="dest-grid">
                    ${Object.entries(composerDestinations).map(([key, item]) => {
                        const platIcon = item.platform === 'facebook' ? 'fa-facebook' : (item.platform === 'instagram' ? 'fa-instagram' : (item.platform === 'linkedin' ? 'fa-linkedin-in' : 'fa-whatsapp'));
                        const badgeClass = item.statusKind === 'published' ? 'badge-published' : (item.statusKind === 'info' ? 'badge-info' : (item.statusKind === 'warning' ? 'badge-warning' : 'badge-neutral'));
                        return `
                            <div class="dest-card ${item.selected ? 'selected' : ''}" id="dest-card-${key}" onclick="toggleComposerDestination('${key}')">
                                <div class="dest-card-left">
                                    <div class="dest-avatar" style="background: ${item.color};">
                                        <i class="fa-brands ${platIcon}"></i>
                                    </div>
                                    <div>
                                        <div class="dest-info-title" style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
                                            <span>${escapeHtml(item.name)}</span>
                                            <span id="dest-status-${key}" class="badge ${badgeClass}" style="font-size: 0.66rem; padding: 0.1rem 0.45rem;">${escapeHtml(item.statusLabel || 'Checking...')}</span>
                                        </div>
                                        <div class="dest-info-sub">${escapeHtml(item.meta)}</div>
                                    </div>
                                </div>
                                <div class="dest-check-indicator">
                                    <i class="fa-solid fa-check"></i>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>

                <div style="display: flex; justify-content: flex-end; margin-top: 2rem;">
                    <button type="button" class="btn btn-primary btn-lg" onclick="setComposerStep(2)">
                        <span>Continue to Content &amp; Media</span> <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>
            </div>

            <!-- STEP 2: CONTENT & MEDIA -->
            <div class="composer-step-pane" id="step-pane-2">
                <div style="margin-bottom: 1.25rem;">
                    <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">
                        <i class="fa-solid fa-pen-fancy" style="color: var(--primary);"></i> Step 2: Compose Copy &amp; Attach Media
                    </h3>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                        Draft high-converting captions, apply smart hashtag tags, and upload high-resolution media.
                    </p>
                </div>

                <div class="form-group">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <label for="view-composer-caption" class="form-label" style="margin-bottom: 0;">Post Caption / Message</label>
                        <span id="view-char-counter" style="font-size: 0.78rem; color: var(--text-muted);">0 / 2200 characters</span>
                    </div>
                    <textarea 
                        id="view-composer-caption" 
                        rows="5" 
                        class="form-control" 
                        placeholder="Write your compelling multi-channel caption here..."
                        oninput="handleCaptionInput(this.value); syncComposerPreviews();"
                    ></textarea>

                    <div class="hashtag-chips-row">
                        <span class="hashtag-chip" onclick="insertTag('#PostPilot')">#PostPilot</span>
                        <span class="hashtag-chip" onclick="insertTag('#Nexora')">#Nexora</span>
                        <span class="hashtag-chip" onclick="insertTag('#Travel')">#Travel</span>
                        <span class="hashtag-chip" onclick="insertTag('#PhoenixIntl')">#PhoenixIntl</span>
                        <span class="hashtag-chip" onclick="insertTag('#Visa')">#Visa</span>
                        <span class="hashtag-chip" onclick="insertTag('#GaathaAI')">#GaathaAI</span>
                        <span class="hashtag-chip" onclick="insertTag('#Advocacy')">#Advocacy</span>
                        <span class="hashtag-chip" onclick="insertTag('#Automation')">#Automation</span>
                    </div>
                </div>

                <div class="form-group" style="margin-top: 1.5rem;">
                    <label class="form-label">Attached Media Asset</label>
                    <div class="file-upload-wrapper">
                        <input type="file" id="view-composer-file" accept="image/*,video/*" onchange="handleFileSelect(this); syncComposerPreviews();">
                        <div class="file-upload-icon"><i class="fa-solid fa-cloud-arrow-up"></i></div>
                        <div class="file-upload-text" id="view-file-name">Drag &amp; drop image or browse files</div>
                        <div class="file-upload-hint">Supports PNG, JPG, WEBP, MP4 (Max 16 MB)</div>
                    </div>

                    <div id="view-file-preview-card" class="file-preview-card">
                        <img id="view-preview-thumb-img" class="file-preview-thumb" src="" alt="Selected Media">
                        <div style="flex: 1; min-width: 0;">
                            <div id="view-selected-file-label" style="font-weight: 600; font-size: 0.85rem;" class="text-truncate">filename.png</div>
                            <div style="font-size: 0.75rem; color: var(--success);"><i class="fa-solid fa-check"></i> Media verified and ready</div>
                        </div>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="clearSelectedMedia(); syncComposerPreviews();" title="Remove Media">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; margin-top: 2rem;">
                    <button type="button" class="btn btn-secondary btn-lg" onclick="setComposerStep(1)">
                        <i class="fa-solid fa-arrow-left"></i> <span>Back: Destinations</span>
                    </button>
                    <button type="button" class="btn btn-primary btn-lg" onclick="setComposerStep(3)">
                        <span>Continue to Previews</span> <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>
            </div>

            <!-- STEP 3: PREVIEWS -->
            <div class="composer-step-pane" id="step-pane-3">
                <div class="composer-preview-header">
                    <div>
                        <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">
                            <i class="fa-solid fa-eye" style="color: var(--primary);"></i> Step 3: Multi-Platform Live Feed Previews
                        </h3>
                        <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                            Validate your exact layout and typography across target social networks.
                        </p>
                    </div>
                    <div class="preview-toggle-group">
                        <button type="button" id="v-tab-btn-fb" class="preview-tab-btn active" onclick="switchComposerPreviewTab('fb')">
                            <i class="fa-brands fa-facebook" style="color: var(--fb-blue);"></i> Facebook
                        </button>
                        <button type="button" id="v-tab-btn-ig" class="preview-tab-btn" onclick="switchComposerPreviewTab('ig')">
                            <i class="fa-brands fa-instagram" style="color: var(--ig-pink);"></i> Instagram
                        </button>
                        <button type="button" id="v-tab-btn-li" class="preview-tab-btn" onclick="switchComposerPreviewTab('li')">
                            <i class="fa-brands fa-linkedin" style="color: #38bdf8;"></i> LinkedIn
                        </button>
                    </div>
                </div>

                <div style="max-width: 580px; margin: 1.5rem auto;">
                    <!-- Facebook Mockup -->
                    <div id="v-mockup-container-fb" class="fb-post-mockup">
                        <div class="fb-mockup-header">
                            <div class="fb-mockup-avatar" id="v-fb-preview-avatar">P</div>
                            <div>
                                <div class="fb-mockup-page-name">
                                    <span id="v-fb-preview-name">PostPilot &middot; Multi-Channel</span>
                                    <i class="fa-solid fa-circle-check"></i>
                                </div>
                                <div class="fb-mockup-time">Just now &middot; <i class="fa-solid fa-earth-americas"></i></div>
                            </div>
                        </div>
                        <div class="fb-mockup-caption" id="v-fb-preview-caption">Your caption will appear here in real-time...</div>
                        <div class="fb-mockup-media-container" id="v-fb-preview-media">
                            <div class="fb-mockup-media-placeholder">
                                <i class="fa-regular fa-image"></i>
                                <div>Attach an image or video to preview layout</div>
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
                                <div class="ig-avatar-inner" id="v-ig-preview-avatar">P</div>
                            </div>
                            <div>
                                <div class="ig-mockup-user" id="v-ig-preview-username">phoenixbygaatha</div>
                                <div class="ig-mockup-location">Global &middot; Meta Business Verified</div>
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
                            <span class="ig-mockup-username-prefix" id="v-ig-preview-prefix">phoenixbygaatha</span>
                            <span id="v-ig-preview-caption">Your caption will appear here...</span>
                        </div>
                    </div>

                    <!-- LinkedIn Mockup -->
                    <div id="v-mockup-container-li" class="li-post-mockup" style="display: none;">
                        <div class="li-mockup-header">
                            <div class="li-mockup-avatar"><i class="fa-brands fa-linkedin-in"></i></div>
                            <div>
                                <div class="li-mockup-name">
                                    <span>Aidni Global LLP</span> &middot; <span style="font-weight: 400; color: #8c9094; font-size: 0.8rem;">1st</span>
                                </div>
                                <div class="li-mockup-meta">Company Page Preview &middot; <i class="fa-solid fa-earth-americas"></i></div>
                            </div>
                        </div>
                        <div class="li-mockup-caption" id="v-li-preview-caption">Your LinkedIn article or post will render here...</div>
                        <div class="li-mockup-media-container" id="v-li-preview-media">
                            <div class="fb-mockup-media-placeholder">
                                <i class="fa-brands fa-linkedin"></i>
                                <div>Attach media to preview LinkedIn high-res card</div>
                            </div>
                        </div>
                        <div class="li-mockup-footer">
                            <div class="li-footer-action"><i class="fa-regular fa-thumbs-up"></i> Like</div>
                            <div class="li-footer-action"><i class="fa-regular fa-comment"></i> Comment</div>
                            <div class="li-footer-action"><i class="fa-solid fa-repeat"></i> Repost</div>
                            <div class="li-footer-action"><i class="fa-regular fa-paper-plane"></i> Send</div>
                        </div>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; margin-top: 2rem;">
                    <button type="button" class="btn btn-secondary btn-lg" onclick="setComposerStep(2)">
                        <i class="fa-solid fa-arrow-left"></i> <span>Back: Content</span>
                    </button>
                    <button type="button" class="btn btn-primary btn-lg" onclick="setComposerStep(4)">
                        <span>Continue to Publish Options</span> <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>
            </div>

            <!-- STEP 4: PUBLISHING OPTIONS -->
            <div class="composer-step-pane" id="step-pane-4">
                <div style="margin-bottom: 1.25rem;">
                    <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">
                        <i class="fa-solid fa-calendar-days" style="color: var(--primary);"></i> Step 4: Scheduling &amp; Publishing Strategy
                    </h3>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                        Select whether to schedule for precise audience timing, save as workspace draft, or dispatch via automated loop.
                    </p>
                </div>

                <div style="background: var(--bg-surface-subtle); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.5rem; margin-bottom: 1.5rem;">
                    <div style="font-weight: 700; font-size: 0.95rem; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-clock" style="color: var(--primary);"></i>
                        <span>Schedule Date, Time &amp; Timezone</span>
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem;">
                        <div class="form-group" style="margin-bottom: 0;">
                            <label for="view-composer-datetime" class="form-label">Scheduled Date &amp; Time (Local)</label>
                            <input type="datetime-local" id="view-composer-datetime" class="form-control">
                        </div>
                        <div class="form-group" style="margin-bottom: 0;">
                            <label for="view-composer-timezone" class="form-label">Timezone</label>
                            <select id="view-composer-timezone" class="form-control">
                                <option value="Asia/Kolkata" selected>Asia/Kolkata (IST)</option>
                                <option value="UTC">UTC (Coordinated Universal Time)</option>
                                <option value="America/New_York">America/New_York (EST)</option>
                                <option value="Europe/London">Europe/London (GMT)</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Safe Mode Banner -->
                <div class="notice-callout notice-callout--success" style="margin-bottom: 1.5rem;">
                    <i class="fa-solid fa-shield-halved"></i>
                    <div>
                        <strong>Publishing Safeguards Enforced:</strong> Guardrails prevent accidental external publishing while allowing scheduling, drafts, and layout previewing.
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; margin-top: 2rem; flex-wrap: wrap; gap: 0.75rem;">
                    <button type="button" class="btn btn-secondary btn-lg" onclick="setComposerStep(3)">
                        <i class="fa-solid fa-arrow-left"></i> <span>Back: Previews</span>
                    </button>
                    <button type="button" class="btn btn-primary btn-lg" onclick="setComposerStep(5)">
                        <span>Continue to Final Review</span> <i class="fa-solid fa-arrow-right"></i>
                    </button>
                </div>
            </div>

            <!-- STEP 5: FINAL REVIEW & CONFIRMATION -->
            <div class="composer-step-pane" id="step-pane-5">
                <div style="margin-bottom: 1.25rem;">
                    <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.2rem;">
                        <i class="fa-solid fa-clipboard-check" style="color: var(--success);"></i> Step 5: Final Review &amp; Confirmation
                    </h3>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                        Review selected accounts, formatted copy, attached media, and confirm publication.
                    </p>
                </div>

                <div style="display: flex; flex-direction: column; gap: 1rem;">
                    <!-- Destinations Summary -->
                    <div class="card" style="margin-bottom: 0; background: var(--bg-surface-subtle);">
                        <label class="studio-card-field-label">Target Destinations</label>
                        <div id="summary-dest-chips" style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.35rem;">
                            <!-- Populated dynamically -->
                        </div>
                    </div>

                    <!-- Caption Summary -->
                    <div class="card" style="margin-bottom: 0; background: var(--bg-surface-subtle);">
                        <label class="studio-card-field-label">Formatted Post Copy</label>
                        <div id="summary-caption-text" style="font-size: 0.92rem; color: var(--text-primary); line-height: 1.5; white-space: pre-wrap; margin-top: 0.35rem;">
                            <!-- Populated dynamically -->
                        </div>
                    </div>

                    <!-- Media & Time Summary -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem;">
                        <div class="card" style="margin-bottom: 0; background: var(--bg-surface-subtle);">
                            <label class="studio-card-field-label">Media Attachment</label>
                            <div id="summary-media-badge" style="font-size: 0.88rem; color: var(--text-primary); margin-top: 0.35rem;">
                                <!-- Populated dynamically -->
                            </div>
                        </div>
                        <div class="card" style="margin-bottom: 0; background: var(--bg-surface-subtle);">
                            <label class="studio-card-field-label">Scheduled Time &amp; Zone</label>
                            <div style="font-size: 0.88rem; color: var(--primary); font-weight: 600; margin-top: 0.35rem;">
                                <i class="fa-regular fa-clock"></i> <span id="summary-scheduled-time">--</span> (<span id="summary-timezone">--</span>)
                            </div>
                        </div>
                    </div>

                    <!-- Verification Checklist -->
                    <div class="notice-callout notice-callout--info" style="flex-direction: column; align-items: stretch;">
                        <div style="font-weight: 700; font-size: 0.85rem; color: var(--primary); margin-bottom: 0.35rem;">
                            <i class="fa-solid fa-list-check"></i> Pre-Flight Check
                        </div>
                        <div id="composer-preflight-list" style="font-size: 0.82rem; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.3rem;">
                            <div><i class="fa-solid fa-circle-info"></i> Checking selected destinations...</div>
                        </div>
                    </div>
                </div>

                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 2rem; flex-wrap: wrap; gap: 0.75rem;">
                    <button type="button" class="btn btn-secondary btn-lg" onclick="setComposerStep(4)">
                        <i class="fa-solid fa-arrow-left"></i> <span>Back: Options</span>
                    </button>
                    <div style="display: flex; gap: 0.75rem;">
                        <button type="button" class="btn btn-secondary btn-lg" onclick="handleComposerSubmit('draft')">
                            <i class="fa-solid fa-file-pen"></i> <span>Save as Draft</span>
                        </button>
                        <button type="button" class="btn btn-primary btn-lg" onclick="handleComposerSubmit('scheduled')">
                            <i class="fa-solid fa-calendar-check"></i> <span>Confirm &amp; Schedule Post</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    initComposerView();
    updateSelectedDestCount();
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
function showModalValidationAlert(message) {
    const el = document.getElementById('modal-validation-alert');
    if (!el) {
        showToast(message, 'error');
        return;
    }
    el.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i><span>${escapeHtml(message)}</span>`;
    el.classList.add('show');
    el.style.display = 'flex';
}

function clearModalValidationAlert() {
    const el = document.getElementById('modal-validation-alert');
    if (!el) return;
    el.classList.remove('show');
    el.style.display = 'none';
    el.innerHTML = '';
}

async function syncModalBrandDropdown(preferredBrandId) {
    const brandSelect = document.getElementById('post-brand');
    if (!brandSelect) return;
    try {
        if (!Array.isArray(window._ppCachedBrands) || window._ppCachedBrands.length === 0) {
            const res = await authFetch('/api/brands');
            if (res.ok) {
                const list = await res.json();
                if (Array.isArray(list) && list.length > 0) {
                    window._ppCachedBrands = list;
                }
            }
        }
        if (Array.isArray(window._ppCachedBrands) && window._ppCachedBrands.length > 0) {
            const cur = preferredBrandId ? String(preferredBrandId) : brandSelect.value;
            brandSelect.innerHTML = window._ppCachedBrands
                .map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`)
                .join('');
            if (cur) brandSelect.value = cur;
        }
    } catch (e) {}
}

function openModal(mode, postId, type, brandId) {
    const modal = document.getElementById('post-modal');
    const modalTitle = document.getElementById('modal-title');
    const typeSelect = document.getElementById('post-type');
    const brandSelect = document.getElementById('post-brand');
    const idInput = document.getElementById('post-id');
    const msgInput = document.getElementById('post-message');
    const curImgInput = document.getElementById('current-image-filename');
    const fileLabel = document.getElementById('file-name');
    const fileInput = document.getElementById('post-file');
    const previewCard = document.getElementById('file-preview-card');
    const previewThumb = document.getElementById('preview-thumb-img');
    const schedDtInput = document.getElementById('post-schedule-datetime');
    const schedTzSelect = document.getElementById('post-schedule-timezone');

    if (!modal) return;

    clearModalValidationAlert();
    modal.classList.add('show');
    modalTitle.textContent = mode === 'edit' ? 'Edit Social Post' : 'Create New Post';
    const canonicalPlatforms = ['facebook', 'instagram', 'linkedin', 'whatsapp'];
    typeSelect.value = (type && canonicalPlatforms.includes(type)) ? type : 'facebook';
    syncModalBrandDropdown(brandId);
    if (brandSelect && brandId) {
        brandSelect.value = String(brandId);
        handleComposerBrandChange(brandId);
    }

    if (mode === 'edit' && postId) {
        const post = currentModulePosts.find(p => p.id === postId)
            || (typeof calendarPostsCache !== 'undefined' && Array.isArray(calendarPostsCache) ? calendarPostsCache.find(p => p.id === postId) : null);
        if (post) {
            idInput.value = post.id;
            msgInput.value = post.message || '';
            curImgInput.value = post.image_filename || '';
            fileLabel.textContent = post.image_filename ? `Current: ${post.image_filename}` : 'Choose new file or drag here';
            if (schedDtInput) {
                const rawDt = (post.local_scheduled_for || post.scheduled_for || '').trim();
                schedDtInput.value = rawDt ? rawDt.replace(' ', 'T').substring(0, 16) : '';
            }
            if (schedTzSelect && post.timezone) schedTzSelect.value = post.timezone;
            
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
        if (schedDtInput) schedDtInput.value = '';
        if (schedTzSelect) schedTzSelect.value = 'Asia/Kolkata';
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
    const len = text ? text.length : 0;
    const modalChannel = document.getElementById('post-type')?.value || 'facebook';

    // Platform character limits
    const limits = {
        facebook: 63206,
        instagram: 2200,
        linkedin: 3000,
        whatsapp: 4096
    };
    const maxLimit = limits[modalChannel] || 2200;

    // Hashtag count (Instagram limit: 30)
    const hashtags = text ? (text.match(/#[a-zA-Z0-9_\u0080-\uffff]+/g) || []) : [];
    const hashtagCount = hashtags.length;
    const isIg = modalChannel === 'instagram';
    let hashtagWarning = '';
    if (isIg && hashtagCount > 30) {
        hashtagWarning = ` <span style="color: #ef4444; font-weight: 700;">⚠️ ${hashtagCount}/30 tags (exceeds IG limit)</span>`;
    } else if (hashtagCount > 0) {
        hashtagWarning = ` <span style="color: var(--text-muted);">&middot; ${hashtagCount} tags</span>`;
    }

    const isOver = len > maxLimit;
    const counterColor = isOver ? '#ef4444' : (len > maxLimit * 0.9 ? '#f59e0b' : 'var(--text-muted)');

    // Update modal char counter
    const counterModal = document.getElementById('char-counter');
    if (counterModal) {
        counterModal.innerHTML = `<span style="color: ${counterColor}; font-weight: ${isOver ? '700' : 'normal'}">${len} / ${maxLimit} chars</span>${hashtagWarning}`;
    }

    // Update view char counter
    const counterView = document.getElementById('view-char-counter');
    if (counterView) {
        counterView.innerHTML = `<span style="color: ${counterColor}; font-weight: ${isOver ? '700' : 'normal'}">${len} / 2200 chars</span>${hashtagWarning}`;
    }

    const displayText = (text && text.trim()) ? escapeHtml(text) : 'Your caption will appear here in real-time...';

    // Update modal mockup captions
    const fbCapModal = document.getElementById('fb-preview-caption');
    if (fbCapModal) fbCapModal.innerHTML = displayText;
    const igCapModal = document.getElementById('ig-preview-caption');
    if (igCapModal) igCapModal.innerHTML = displayText;
    const liCapModal = document.getElementById('li-preview-caption');
    if (liCapModal) liCapModal.innerHTML = displayText;
    const waCapModal = document.getElementById('wa-preview-caption');
    if (waCapModal) waCapModal.innerHTML = displayText;

    // Update view mockup captions
    const fbCapView = document.getElementById('v-fb-preview-caption');
    if (fbCapView) fbCapView.innerHTML = displayText;
    const igCapView = document.getElementById('v-ig-preview-caption');
    if (igCapView) igCapView.innerHTML = displayText;
    const liCapView = document.getElementById('v-li-preview-caption');
    if (liCapView) liCapView.innerHTML = displayText;
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

function handleComposerBrandChange(brandId) {
    const brandMap = {
        '1': { name: 'GAATHA Suite', ig: 'nexora_suite', li: 'Aidni Global LLP', wa: 'Gaatha Ventures' },
        '2': { name: 'GAATHA POS', ig: 'gaatha_pos', li: 'Aidni Global LLP', wa: 'Gaatha Ventures' },
        '3': { name: 'Sentira AI', ig: 'sentira_ai', li: 'Gaatha Ventures Sh.p.k.', wa: 'Gaatha Ventures' },
        '4': { name: 'GAATHA Terra', ig: 'gaatha_terra', li: 'Aidni Global LLP', wa: 'Gaatha Ventures' },
        '5': { name: 'Phoenix — BY GAATHA', ig: 'phoenixbygaatha', li: 'Aidni Global LLP', wa: 'Gaatha Ventures' },
        '6': { name: 'GAATHA AI', ig: 'gaatha_ai', li: 'Gaatha Ventures Sh.p.k.', wa: 'Gaatha Ventures' }
    };
    const b = brandMap[String(brandId)] || brandMap['1'];

    const fbName = document.getElementById('fb-preview-name');
    const igUser = document.getElementById('ig-preview-username');
    const igPrefix = document.getElementById('ig-preview-prefix');
    const liName = document.getElementById('li-preview-name');
    const waName = document.getElementById('wa-preview-name');

    if (fbName) fbName.textContent = b.name;
    if (igUser) igUser.textContent = b.ig;
    if (igPrefix) igPrefix.textContent = b.ig;
    if (liName) liName.textContent = b.li;
    if (waName) waName.textContent = b.wa;
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

    // Auto-switch preview tab to match selected channel
    const platMap = { 'facebook': 'fb', 'instagram': 'ig', 'linkedin': 'li', 'whatsapp': 'wa' };
    if (platMap[channel]) {
        switchPreviewPlatform(platMap[channel]);
    }

    // Refresh char counter with platform limit
    const captionText = document.getElementById('post-message')?.value || '';
    handleCaptionInput(captionText);
}

function switchPreviewPlatform(platform) {
    const platforms = ['fb', 'ig', 'li', 'wa'];
    platforms.forEach(p => {
        const btnModal = document.getElementById(`tab-btn-${p}`);
        const boxModal = document.getElementById(`mockup-container-${p}`);
        const btnView = document.getElementById(`v-tab-btn-${p}`);
        const boxView = document.getElementById(`v-mockup-container-${p}`);

        const isActive = p === platform;
        if (btnModal) {
            if (isActive) btnModal.classList.add('active');
            else btnModal.classList.remove('active');
        }
        if (boxModal) boxModal.style.display = isActive ? 'block' : 'none';

        if (btnView) {
            if (isActive) btnView.classList.add('active');
            else btnView.classList.remove('active');
        }
        if (boxView) boxView.style.display = isActive ? 'block' : 'none';
    });
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
    clearModalValidationAlert();
    const type = document.getElementById('post-type').value;
    const postId = document.getElementById('post-id').value;
    const message = document.getElementById('post-message').value.trim();
    const fileInput = document.getElementById('post-file');
    let filename = document.getElementById('current-image-filename').value;
    const schedDtVal = document.getElementById('post-schedule-datetime')?.value.trim() || '';
    const schedTzVal = document.getElementById('post-schedule-timezone')?.value || 'Asia/Kolkata';
    const saveBtn = document.getElementById('save-post-btn');

    const hasNewFile = fileInput && fileInput.files && fileInput.files.length > 0;
    if (!message && !hasNewFile && !filename) {
        showModalValidationAlert('Please enter a caption or attach media before saving.');
        document.getElementById('post-message')?.focus();
        return;
    }

    const platformLimits = { facebook: 63206, instagram: 2200, linkedin: 3000, whatsapp: 4096 };
    const limit = platformLimits[type] || 3000;
    if (message.length > limit) {
        showModalValidationAlert(`Caption exceeds the ${limit.toLocaleString()} character limit for ${type}.`);
        document.getElementById('post-message')?.focus();
        return;
    }

    if (type === 'instagram' && !hasNewFile && !filename) {
        showModalValidationAlert('Instagram publishing requires an image or video attachment. Attach media or click Save as Draft.');
        return;
    }

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';
    }

    // Media upload if a new file was chosen
    if (hasNewFile) {
        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            const uploadRes = await authFetch('/api/upload', { method: 'POST', body: formData });
            const uploadData = await uploadRes.json();
            if (uploadData.filename) {
                filename = uploadData.filename;
            } else {
                showModalValidationAlert(uploadData.error || 'Media upload failed.');
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
                }
                return;
            }
        } catch (e) {
            showModalValidationAlert('Media upload failed due to a network error.');
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
            }
            return;
        }
    }

    const brandId = document.getElementById('post-brand')?.value || '1';
    const payload = { 
        message, 
        image_filename: filename,
        brand_id: parseInt(brandId, 10)
    };

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
                const err = await res.json().catch(() => ({}));
                showModalValidationAlert(err.error || 'Failed to update post.');
                return;
            }
        } else if (schedDtVal) {
            const schedRes = await authFetch('/api/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...payload,
                    post_type: type,
                    scheduled_for: schedDtVal.replace('T', ' '),
                    timezone: schedTzVal,
                    status: 'scheduled'
                })
            });
            if (schedRes.ok) {
                showToast(`Post scheduled for ${schedDtVal.replace('T', ' ')} (${schedTzVal})`, 'success');
            } else {
                const err = await schedRes.json().catch(() => ({}));
                showModalValidationAlert(err.error || 'Failed to schedule post.');
                return;
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
                const err = await res.json().catch(() => ({}));
                showModalValidationAlert(err.error || 'Failed to create post.');
                return;
            }
        }
    } catch (e) {
        showModalValidationAlert('Error communicating with server.');
        return;
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Post';
        }
    }

    closeModal();
    if (currentTab === type) loadPosts(type);
    if (currentTab === 'dashboard') {
        loadDashboardExecutiveMetrics();
    } else if (currentTab === 'calendar' && typeof renderCalendarContent === 'function') {
        loadTab('calendar');
    } else if (currentTab === 'queue' && typeof renderQueueView === 'function') {
        loadTab('queue');
    }
}

// 1-Click Save as Draft from Modal
async function savePostAsDraft() {
    const message = document.getElementById('post-message')?.value.trim();
    const brandId = document.getElementById('post-brand')?.value || '1';
    const platform = document.getElementById('post-type')?.value || 'facebook';
    const fileInput = document.getElementById('post-file');
    let filename = document.getElementById('current-image-filename')?.value || null;

    if (!message && (!fileInput || fileInput.files.length === 0)) {
        showToast('Please provide a caption or attach media for the draft', 'error');
        return;
    }

    // Media upload if a file was selected
    if (fileInput && fileInput.files.length > 0) {
        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            const uploadRes = await authFetch('/api/upload', { method: 'POST', body: formData });
            const uploadData = await uploadRes.json();
            if (uploadData.filename) {
                filename = uploadData.filename;
            }
        } catch (e) {
            console.warn('Draft media upload error:', e);
        }
    }

    try {
        const res = await authFetch('/api/drafts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                brand_id: parseInt(brandId, 10),
                caption: message,
                target_platform: platform,
                image_filename: filename,
                headline: message.substring(0, 60)
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('Draft saved successfully to Drafts Workspace!', 'success');
            closeModal();
            loadTab('drafts');
        } else {
            showToast(data.error || 'Failed to save draft', 'error');
        }
    } catch (e) {
        showToast('Error saving draft: ' + e.message, 'error');
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

    // 4. Sync real backend integration readiness onto destination cards (read-only metadata)
    try {
        const intData = await fetchIntegrationsStatusCached(false);
        if (intData && (intData.meta || intData.linkedin || intData.whatsapp)) {
            const meta = intData.meta || {};
            const fbPages = Array.isArray(meta.pages) ? meta.pages : [];
            const igAccts = Array.isArray(meta.instagram_accounts) ? meta.instagram_accounts : [];
            const liApps = Array.isArray((intData.linkedin || {}).apps) ? intData.linkedin.apps : [];
            const wa = intData.whatsapp || {};

            const setDestStatus = (key, label, kind) => {
                if (composerDestinations[key]) {
                    composerDestinations[key].statusLabel = label;
                    composerDestinations[key].statusKind = kind;
                }
                const el = document.getElementById(`dest-status-${key}`);
                if (el) {
                    const cls = kind === 'published' ? 'badge-published' : (kind === 'info' ? 'badge-info' : (kind === 'warning' ? 'badge-warning' : 'badge-neutral'));
                    el.className = `badge ${cls}`;
                    el.textContent = label;
                }
            };

            const fbOk = fbPages.length > 0;
            const igOk = igAccts.length > 0;
            ['fb_gaathasuite', 'fb_tour', 'fb_nz', 'fb_gaatha', 'fb_grahak'].forEach(k => {
                setDestStatus(k, fbOk ? 'Connected' : 'Check Token', fbOk ? 'published' : 'warning');
            });
            ['ig_gaathasuite', 'ig_phoenix'].forEach(k => {
                setDestStatus(k, igOk ? 'Connected' : 'Unlinked', igOk ? 'published' : 'warning');
            });

            liApps.forEach(app => {
                const key = app.app_key === 'aidni_global' ? 'li_aidni' : (app.app_key === 'gaatha_ventures' ? 'li_gaatha' : null);
                if (!key) return;
                if (!app.user_authenticated) {
                    setDestStatus(key, 'Auth Required', 'warning');
                } else if (app.company_publishing_ready) {
                    setDestStatus(key, 'Company Ready', 'published');
                } else {
                    setDestStatus(key, 'Personal Auth Only', 'info');
                }
            });

            const waReady = Boolean(wa.publishing_enabled && wa.status === 'connected');
            setDestStatus('wa_gaatha', waReady ? 'Ready' : (wa.status_label || 'Isolated Standby'), waReady ? 'published' : 'warning');
        }
    } catch (e) {
        console.warn('Could not sync composer destination status pills:', e);
    }
}

async function handleComposerSubmit(status) {
    const message = document.getElementById('view-composer-caption')?.value.trim() || '';
    const fileInput = document.getElementById('view-composer-file');
    const brandId = document.getElementById('view-composer-brand')?.value || null;
    const dtVal = document.getElementById('view-composer-datetime')?.value;
    const tzVal = document.getElementById('view-composer-timezone')?.value || 'UTC';
    const selectedDests = Object.entries(composerDestinations).filter(([k, d]) => d.selected);

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

    // Save as draft directly via drafts API
    if (status === 'draft') {
        const primaryDest = selectedDests.length > 0 ? selectedDests[0][1] : { platform: 'facebook', brand_id: 1 };
        const bId = brandId ? parseInt(brandId, 10) : (primaryDest.brand_id || 1);
        const pType = primaryDest.platform || 'facebook';

        try {
            const res = await authFetch('/api/drafts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    brand_id: bId,
                    caption: message,
                    target_platform: pType,
                    image_filename: imageFilename,
                    headline: message.substring(0, 60)
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast('Draft post saved successfully in Drafts Workspace!', 'success');
                loadTab('drafts');
                resetViewComposer();
                return;
            } else {
                showToast(data.error || 'Failed to save draft', 'error');
                return;
            }
        } catch (e) {
            showToast('Draft creation error: ' + e.message, 'error');
            return;
        }
    }

    let scheduledFor = dtVal;
    if (!scheduledFor) {
        const d = new Date(Date.now() + 3600 * 1000);
        scheduledFor = d.toISOString();
    }

    const destsToSchedule = selectedDests.length > 0 ? selectedDests.map(([k, d]) => d) : [{ platform: 'facebook', brand_id: brandId ? parseInt(brandId, 10) : 1 }];
    let successCount = 0;
    let lastError = null;

    try {
        for (const dest of destsToSchedule) {
            const payload = {
                post_type: dest.platform,
                scheduled_for: scheduledFor,
                timezone: tzVal,
                message: message,
                image_filename: imageFilename,
                brand_id: dest.brand_id || (brandId ? parseInt(brandId, 10) : 1),
                status: status
            };

            const res = await authFetch('/api/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                successCount++;
            } else {
                const data = await res.json();
                lastError = data.error || 'Server error';
            }
        }

        if (successCount > 0) {
            showToast(`Scheduled ${successCount} post(s) successfully across destinations!`, 'success');
            loadTab('calendar');
            resetViewComposer();
        } else {
            showToast(lastError || 'Failed to schedule post', 'error');
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
                    <option value="all">All Platforms</option>
                    <option value="facebook">Facebook Pages</option>
                    <option value="instagram">Instagram Professional</option>
                    <option value="linkedin">LinkedIn Pages</option>
                    <option value="whatsapp">WhatsApp Business Cloud</option>
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
                <div style="font-size: 0.72rem; color: var(--primary); font-weight: 700; text-align: center; cursor: pointer;" onclick="setCalendarView('day'); calendarCurrentDate = new Date('${dateStr}T12:00:00'); renderCalendarContent(); event.stopPropagation();">
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
        <div class="calendar-week-grid">
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
                    <i class="fa-solid fa-list-check" style="color: var(--primary);"></i> Publishing Queue &amp; Schedule
                </h3>
                <small style="color: var(--text-secondary);">Filter and manage queued, scheduled, draft, and failed campaign posts.</small>
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
                    <option value="all">All Platforms</option>
                    <option value="facebook">Facebook Pages</option>
                    <option value="instagram">Instagram</option>
                    <option value="linkedin">LinkedIn</option>
                    <option value="whatsapp">WhatsApp</option>
                </select>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadQueueData()" title="Refresh Queue">
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
                <div style="font-weight: 600; font-size: 1rem; margin-bottom: 0.25rem; color: var(--text-primary);">No posts match current queue filters</div>
                <p style="font-size: 0.85rem;">Try selecting a different status or platform filter above.</p>
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
                        <th>Platform</th>
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
                <td><span class="badge badge-${p.status}">${escapeHtml(p.status)}</span></td>
                <td>
                    <div style="font-weight: 600; font-size: 0.85rem;">${escapeHtml(p.local_display || p.scheduled_for || 'Queued')}</div>
                    <small style="color: var(--text-muted); font-size: 0.72rem;">UTC: ${escapeHtml(p.scheduled_for || '—')}</small>
                </td>
                <td>
                    <span class="badge badge-neutral">
                        ${escapeHtml(CHANNEL_INFO[p.post_type]?.name || p.post_type)}
                    </span>
                </td>
                <td style="max-width: 280px;">
                    <div class="text-truncate" style="font-size: 0.85rem;" title="${escapeHtml(p.message || '')}">
                        ${escapeHtml(p.message || '(No text caption)')}
                    </div>
                    ${p.status === 'failed' && p.error_message ? `
                        <div style="font-size: 0.75rem; color: var(--danger); margin-top: 0.2rem; background: var(--danger-soft); padding: 2px 6px; border-radius: 4px;" class="text-truncate" title="${escapeHtml(p.error_message)}">
                            <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(p.error_message)}
                        </div>
                    ` : ''}
                </td>
                <td>
                    ${p.image_filename ? `
                        <span class="badge badge-neutral" style="font-size: 0.75rem;" title="${escapeHtml(p.image_filename)}">
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
        <div class="mobile-posts-list">
            ${filtered.map(p => `
                <div class="mobile-post-card">
                    <div class="mobile-post-header">
                        <span class="platform-pill ${escapeHtml(p.post_type || 'facebook')}" style="font-size: 0.72rem;">
                            ${escapeHtml(CHANNEL_INFO[p.post_type]?.name || p.post_type)}
                        </span>
                        <span class="badge badge-${escapeHtml(p.status)}">${escapeHtml(p.status)}</span>
                    </div>
                    <div style="font-size: 0.8rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">
                        <i class="fa-regular fa-clock"></i> ${escapeHtml(p.local_display || p.scheduled_for || 'Queued')}
                    </div>
                    <div style="font-size: 0.84rem; color: var(--text-secondary); margin-bottom: 0.6rem; line-height: 1.45;">
                        ${escapeHtml(p.message || '(Media-only post)')}
                    </div>
                    ${p.status === 'failed' && p.error_message ? `
                        <div style="font-size: 0.75rem; color: var(--danger); background: var(--danger-soft); padding: 0.35rem 0.55rem; border-radius: 6px; margin-bottom: 0.6rem;">
                            <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(p.error_message)}
                        </div>
                    ` : ''}
                    <div class="mobile-post-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id})"><i class="fa-solid fa-eye"></i> Details</button>
                        ${p.status === 'failed' ? `<button type="button" class="btn btn-primary btn-sm" onclick="retryPostFromDetails(${p.id})"><i class="fa-solid fa-rotate-right"></i> Retry</button>` : ''}
                        ${['scheduled', 'draft'].includes(p.status) ? `<button type="button" class="btn btn-secondary btn-sm" onclick="openRescheduleModal(${p.id})"><i class="fa-solid fa-clock"></i></button><button type="button" class="btn btn-danger btn-sm" onclick="cancelPostFromDetails(${p.id})"><i class="fa-solid fa-ban"></i></button>` : ''}
                    </div>
                </div>
            `).join('')}
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
                        ${escapeHtml(draft.ai_provider || 'ai')} · ${formatReadableDateTime(draft.created_at, 'Draft')}
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
        document.getElementById('strategy-last-updated').textContent = `Blueprint updated: ${formatReadableDateTime(lastUpdated)}`;
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
        const [brandsRes, accsRes, schedRes, draftsRes] = await Promise.all([
            authFetch('/api/brands'),
            authFetch('/api/accounts'),
            authFetch('/api/schedule?envelope=1&limit=500'),
            authFetch('/api/drafts')
        ]);
        const brands = brandsRes.ok ? await brandsRes.json() : [];
        const accountsData = accsRes.ok ? await accsRes.json() : {};
        const schedData = schedRes.ok ? await schedRes.json() : {};
        const draftsData = draftsRes.ok ? await draftsRes.json() : {};

        const allAccounts = accountsData.accounts || [];
        const allPosts = schedData.posts || (Array.isArray(schedData) ? schedData : []);
        const allDrafts = draftsData.drafts || [];

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
                const bAccounts = allAccounts.filter(a => a.brand_id === b.id || (b.id === 1 && !a.brand_id));
                const bPosts = allPosts.filter(p => p.brand_id === b.id);
                const bDrafts = allDrafts.filter(d => d.brand_id === b.id);

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

                            <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                                <span class="badge badge-info">
                                    <i class="fa-solid fa-share-nodes"></i> ${bAccounts.length} Accounts
                                </span>
                                <span class="badge badge-published">
                                    <i class="fa-solid fa-calendar-check"></i> ${bPosts.length} Scheduled
                                </span>
                                <span class="badge badge-warning">
                                    <i class="fa-solid fa-file-pen"></i> ${bDrafts.length} Drafts
                                </span>
                            </div>

                            <div style="display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.78rem; color: var(--text-muted); background: var(--bg-surface-subtle); padding: 0.65rem 0.85rem; border-radius: var(--radius-md); border: 1px solid var(--border);">
                                <div><i class="fa-solid fa-globe" style="width: 16px;"></i> ${escapeHtml(b.website || 'No website set')}</div>
                                <div><i class="fa-solid fa-users" style="width: 16px;"></i> ${escapeHtml(b.target_audience || 'Universal audiences')}</div>
                                <div><i class="fa-solid fa-earth-americas" style="width: 16px;"></i> ${escapeHtml(b.target_markets || 'Global')}</div>
                            </div>
                        </div>

                        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; padding-top: 0.65rem; border-top: 1px solid var(--border);">
                            <button type="button" class="btn btn-primary btn-sm" onclick="openModal('add', null, 'facebook', ${b.id})" title="Compose post for this brand">
                                <i class="fa-solid fa-pen"></i> Compose
                            </button>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="openBrandProfileModal(${b.id})" title="Edit brand positioning and factual guardrails">
                                <i class="fa-solid fa-id-card" style="color: var(--primary);"></i> Profile
                            </button>
                            <button type="button" class="btn btn-outline-secondary btn-sm" onclick="switchToStudioWithBrand(${b.id})" title="Open brand in AI Marketing Studio">
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

                            <div style="display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.76rem; color: var(--text-muted); background: var(--bg-surface-subtle); padding: 0.55rem 0.75rem; border-radius: var(--radius-md); border: 1px solid var(--border);">
                                <div><strong>Objective:</strong> ${escapeHtml(c.objective || 'Brand Awareness')}</div>
                                <div><strong>Audience:</strong> ${escapeHtml(c.target_audience || 'Universal')}</div>
                                <div><strong>Markets:</strong> ${escapeHtml(c.target_markets || 'Global')}</div>
                            </div>
                        </div>

                        <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; padding-top: 0.65rem; border-top: 1px solid var(--border);">
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
        const mediaPayload = mediaRes.ok ? await mediaRes.json() : [];
        const mediaAssets = Array.isArray(mediaPayload) ? mediaPayload : (Array.isArray(mediaPayload && mediaPayload.assets) ? mediaPayload.assets : []);

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
                <div class="card" style="padding: 1.25rem; margin-bottom: 1.5rem; background: var(--bg-surface-subtle); border: 2px dashed var(--border-strong);">
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
                const assetName = m.original_filename || m.original_name || m.filename || 'Media Asset';
                const assetUrl = m.file_url || (m.filename ? `/images/${encodeURIComponent(m.filename)}` : '');
                const assetType = m.content_type || m.mime_type || m.file_type || 'image';

                html += `
                    <div class="card media-asset-card" style="overflow: hidden; padding: 0; display: flex; flex-direction: column;">
                        <div style="height: 150px; background: var(--bg-surface-subtle); display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative; border-bottom: 1px solid var(--border);">
                            ${assetUrl ? `<img src="${escapeHtml(assetUrl)}" alt="${escapeHtml(assetName)}" style="width: 100%; height: 100%; object-fit: cover;">` : `<i class="fa-regular fa-image fa-2x" style="color: var(--text-muted);"></i>`}
                            <span class="badge" style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: #fff; font-size: 0.65rem;">
                                ${escapeHtml(brandName)}
                            </span>
                        </div>
                        <div style="padding: 0.85rem; flex: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 0.5rem;">
                            <div>
                                <div style="font-weight: 600; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(assetName)}">
                                    ${escapeHtml(assetName)}
                                </div>
                                <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">
                                    ${sizeKb} · ${escapeHtml(assetType)}
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
// VIEW: Publishing History & Diagnostics (Unit L)
// ==========================================================================
let historyFilterChannel = 'all';
let historyFilterStatus = 'all';

async function renderHistory(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Publishing History &amp; Diagnostics...</p>
        </div>
    `;

    try {
        // Fetch from /api/schedule which contains full queue, scheduled, and failed history
        let allPosts = [];
        const schedRes = await authFetch('/api/schedule');
        if (schedRes.ok) {
            allPosts = await schedRes.json();
        } else {
            const postsRes = await authFetch('/api/posts');
            if (postsRes.ok) allPosts = await postsRes.json();
        }

        // Apply filters
        let historyPosts = allPosts;
        if (historyFilterChannel !== 'all') {
            historyPosts = historyPosts.filter(p => (p.post_type || p.type || p.channel) === historyFilterChannel);
        }
        if (historyFilterStatus !== 'all') {
            historyPosts = historyPosts.filter(p => p.status === historyFilterStatus);
        }

        const totalCount = allPosts.length;
        const failedCount = allPosts.filter(p => p.status === 'failed' || p.error_message).length;
        const pubCount = allPosts.filter(p => p.status === 'publishing').length;
        const schedCount = allPosts.filter(p => p.status === 'scheduled').length;

        let html = `
            <div class="history-view-container">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-clock-rotate-left" style="color: var(--primary);"></i> Publishing History &amp; Audit Trail
                        </h2>
                        <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                            Destination-level lifecycle records, failure diagnostics, idempotency keys, and audit timeline.
                        </p>
                    </div>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn btn-secondary btn-sm" onclick="renderHistory(document.getElementById('content-area'))">
                            <i class="fa-solid fa-rotate"></i> Refresh History
                        </button>
                    </div>
                </div>

                <!-- Diagnostics Summary Bar -->
                <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 1.25rem;">
                    <div class="stat-card" style="padding: 0.75rem 1rem;">
                        <div style="font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700;">Total Dispatches</div>
                        <div style="font-size: 1.35rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${totalCount}</div>
                    </div>
                    <div class="stat-card" style="padding: 0.75rem 1rem;">
                        <div style="font-size: 0.72rem; color: var(--primary); text-transform: uppercase; font-weight: 700;">Scheduled</div>
                        <div style="font-size: 1.35rem; font-weight: 800; color: var(--primary); margin-top: 0.2rem;">${schedCount}</div>
                    </div>
                    <div class="stat-card" style="padding: 0.75rem 1rem;">
                        <div style="font-size: 0.72rem; color: var(--warning); text-transform: uppercase; font-weight: 700;">Publishing In-Flight</div>
                        <div style="font-size: 1.35rem; font-weight: 800; color: var(--warning); margin-top: 0.2rem;">${pubCount}</div>
                    </div>
                    <div class="stat-card" style="padding: 0.75rem 1rem;">
                        <div style="font-size: 0.72rem; color: var(--danger); text-transform: uppercase; font-weight: 700;">Diagnostics / Errors</div>
                        <div style="font-size: 1.35rem; font-weight: 800; color: var(--danger); margin-top: 0.2rem;">${failedCount}</div>
                    </div>
                </div>

                <!-- Filters -->
                <div class="card" style="padding: 0.75rem 1rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                        <div style="display: flex; align-items: center; gap: 0.4rem;">
                            <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Platform:</label>
                            <select class="form-control" style="font-size: 0.85rem; width: auto;" onchange="historyFilterChannel = this.value; renderHistory(document.getElementById('content-area'))">
                                <option value="all" ${historyFilterChannel === 'all' ? 'selected' : ''}>All Platforms</option>
                                <option value="facebook" ${historyFilterChannel === 'facebook' ? 'selected' : ''}>Facebook Pages</option>
                                <option value="instagram" ${historyFilterChannel === 'instagram' ? 'selected' : ''}>Instagram Professional</option>
                                <option value="linkedin" ${historyFilterChannel === 'linkedin' ? 'selected' : ''}>LinkedIn Company</option>
                                <option value="whatsapp" ${historyFilterChannel === 'whatsapp' ? 'selected' : ''}>WhatsApp Cloud API</option>
                            </select>
                        </div>
                        <div style="display: flex; align-items: center; gap: 0.4rem;">
                            <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-muted);">Status:</label>
                            <select class="form-control" style="font-size: 0.85rem; width: auto;" onchange="historyFilterStatus = this.value; renderHistory(document.getElementById('content-area'))">
                                <option value="all" ${historyFilterStatus === 'all' ? 'selected' : ''}>All Statuses</option>
                                <option value="published" ${historyFilterStatus === 'published' ? 'selected' : ''}>Published</option>
                                <option value="scheduled" ${historyFilterStatus === 'scheduled' ? 'selected' : ''}>Scheduled</option>
                                <option value="publishing" ${historyFilterStatus === 'publishing' ? 'selected' : ''}>Publishing</option>
                                <option value="cancelled" ${historyFilterStatus === 'cancelled' ? 'selected' : ''}>Cancelled</option>
                                <option value="failed" ${historyFilterStatus === 'failed' ? 'selected' : ''}>Failed</option>
                            </select>
                        </div>
                    </div>
                    <span style="font-size: 0.82rem; color: var(--text-muted); font-weight: 600;">Showing ${historyPosts.length} of ${totalCount} Records</span>
                </div>

                <div class="card queue-table-wrap" style="overflow-x: auto; padding: 0;">
                    <table class="data-table" style="width: 100%; border-collapse: collapse; table-layout: fixed;">
                        <colgroup>
                            <col style="width: 46px;">
                            <col style="width: 128px;">
                            <col style="width: 155px;">
                            <col style="width: 64px;">
                            <col style="width: 105px;">
                            <col style="width: 132px;">
                            <col style="width: 140px;">
                            <col style="width: 146px;">
                        </colgroup>
                        <thead>
                            <tr style="background: var(--bg-surface-subtle); border-bottom: 1px solid var(--border);">
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">ID</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Brand</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Caption</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Media</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Status</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Diagnostics</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: left; font-size: 0.7rem; text-transform: uppercase;">Scheduled (IST)</th>
                                <th style="padding: 0.6rem 0.5rem; text-align: right; font-size: 0.7rem; text-transform: uppercase;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        if (historyPosts.length === 0) {
            html += `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 2.5rem; color: var(--text-muted);">
                        No publishing records match the selected criteria.
                    </td>
                </tr>
            `;
        } else {
            historyPosts.forEach(p => {
                const cKey = p.post_type || p.type || p.channel || 'facebook';
                const info = CHANNEL_INFO[cKey] || { name: cKey.toUpperCase(), icon: 'fa-share-nodes' };
                const isFailed = p.status === 'failed' || !!p.error_message;
                const statusBadge = p.status === 'published' ? 'badge-success' : (p.status === 'publishing' ? 'badge-warning' : (p.status === 'scheduled' ? 'badge-info' : (p.status === 'cancelled' ? 'badge-secondary' : 'badge-danger')));
                const isSim = Boolean(p.external_post_id && p.external_post_id.includes('_sim_'));

                html += `
                    <tr style="border-bottom: 1px solid var(--border);">
                        <td style="padding: 0.6rem 0.5rem; font-weight: 700; font-size: 0.78rem; white-space: nowrap;">#${p.id}</td>
                        <td style="padding: 0.6rem 0.5rem;">
                            <span style="font-weight: 600; font-size: 0.8rem; display: flex; align-items: center; gap: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                <i class="${info.icon || 'fa-solid fa-share-nodes'}" style="color: var(--primary); flex-shrink: 0;"></i>
                                <span style="overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.brand_name || info.name)}</span>
                            </span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem;">
                            <div style="font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-primary);" title="${escapeHtml(p.message || '')}">
                                ${escapeHtml(p.message || 'No caption')}
                            </div>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; font-size: 0.75rem; white-space: nowrap;">
                            ${p.image_filename ? `<span class="badge badge-info" style="font-size: 0.68rem;">Image</span>` : `<span style="color: var(--text-muted);">Text</span>`}
                        </td>
                        <td style="padding: 0.6rem 0.5rem;">
                            <span class="badge ${statusBadge}" style="text-transform: capitalize; font-size: 0.68rem;">${escapeHtml(p.status)}</span>
                            ${p.external_post_id ? (isSim ? `
                                <span class="badge badge-warning" style="font-size: 0.64rem; display: inline-flex; margin-top: 0.2rem;" title="Simulated via safety guardrail">SIMULATED</span>
                            ` : `
                                <span class="badge badge-published" style="font-size: 0.64rem; display: inline-flex; margin-top: 0.2rem;">LIVE ID</span>
                            `) : ''}
                            ${p.retry_count ? `<small style="color: var(--text-muted); display: block; font-size: 0.66rem;">Retries: ${p.retry_count}</small>` : ''}
                        </td>
                        <td style="padding: 0.6rem 0.5rem;">
                            ${p.error_message ? `
                                <span class="badge badge-danger" style="font-size: 0.66rem; cursor: pointer; display: inline-flex; align-items: center; gap: 0.2rem; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" onclick="openPostDetails(${p.id})" title="${escapeHtml(p.error_message)}">
                                    <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(p.error_message.slice(0, 16))}...
                                </span>
                            ` : `<span style="color: var(--success); font-size: 0.72rem;"><i class="fa-solid fa-circle-check"></i> Healthy</span>`}
                        </td>
                        <td style="padding: 0.6rem 0.5rem; font-size: 0.74rem; color: var(--text-muted);">
                            <div style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.local_display || p.scheduled_for || formatReadableDateTime(p.created_at))}</div>
                            ${p.external_post_id ? `<code style="font-size: 0.66rem; background: var(--bg-surface-subtle); color: var(--text-primary); padding: 0.05rem 0.25rem; border-radius: 3px; display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(p.external_post_id)}">${escapeHtml(p.external_post_id)}</code>` : ''}
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: right; white-space: nowrap;">
                            <div style="display: inline-flex; gap: 0.25rem;">
                                <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id})" title="View Lifecycle Audit Trail" style="padding: 0.28rem 0.48rem; font-size: 0.74rem;">
                                    <i class="fa-solid fa-eye"></i> Audit
                                </button>
                                ${isFailed || p.status === 'cancelled' ? `
                                    <button type="button" class="btn btn-primary btn-sm" onclick="retryHistoryPost(${p.id})" title="Retry Scheduled Dispatch" style="padding: 0.28rem 0.48rem; font-size: 0.74rem;">
                                        <i class="fa-solid fa-rotate-right"></i> Retry
                                    </button>
                                ` : ''}
                            </div>
                        </td>
                    </tr>
                `;
            });
        }

        html += `
                        </tbody>
                    </table>
                </div>

                <!-- Mobile History Cards -->
                <div class="mobile-posts-list">
                    ${historyPosts.length === 0 ? `
                        <div class="card" style="text-align: center; padding: 2.5rem 1rem; color: var(--text-muted);">
                            No publishing records match the selected criteria.
                        </div>
                    ` : historyPosts.map(p => {
                        const cKey = p.post_type || p.type || p.channel || 'facebook';
                        const info = CHANNEL_INFO[cKey] || { name: cKey.toUpperCase() };
                        const isFailed = p.status === 'failed' || !!p.error_message;
                        const statusBadge = p.status === 'published' ? 'badge-success' : (p.status === 'publishing' ? 'badge-warning' : (p.status === 'scheduled' ? 'badge-info' : (p.status === 'cancelled' ? 'badge-secondary' : 'badge-danger')));
                        const isSim = Boolean(p.external_post_id && p.external_post_id.includes('_sim_'));
                        return `
                            <div class="mobile-post-card">
                                <div class="mobile-post-header">
                                    <span style="font-weight: 700; font-size: 0.85rem; color: var(--text-primary);">#${p.id} &middot; ${escapeHtml(p.brand_name || info.name)}</span>
                                    <span class="badge ${statusBadge}">${escapeHtml(p.status)}</span>
                                </div>
                                <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.35rem;">
                                    <i class="fa-regular fa-clock"></i> ${escapeHtml(p.local_display || p.scheduled_for || formatReadableDateTime(p.created_at))}
                                    ${p.external_post_id ? ` &middot; <span class="badge ${isSim ? 'badge-warning' : 'badge-published'}">${isSim ? 'SIMULATED' : 'LIVE'}</span>` : ''}
                                </div>
                                <div style="font-size: 0.84rem; color: var(--text-secondary); margin-bottom: 0.6rem; line-height: 1.45;">
                                    ${escapeHtml(p.message || '(No text caption)')}
                                </div>
                                ${p.error_message ? `
                                    <div style="font-size: 0.75rem; color: var(--danger); background: var(--danger-soft); padding: 0.35rem 0.55rem; border-radius: 6px; margin-bottom: 0.6rem;">
                                        <i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(p.error_message)}
                                    </div>
                                ` : ''}
                                <div class="mobile-post-actions">
                                    <button type="button" class="btn btn-secondary btn-sm" onclick="openPostDetails(${p.id})"><i class="fa-solid fa-eye"></i> Audit</button>
                                    ${isFailed || p.status === 'cancelled' ? `<button type="button" class="btn btn-primary btn-sm" onclick="retryHistoryPost(${p.id})"><i class="fa-solid fa-rotate-right"></i> Retry</button>` : ''}
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card" style="padding: 2rem; color: var(--danger);">Failed to load history: ${escapeHtml(e.message)}</div>`;
    }
}

// Aliases and handlers for history actions
window.openDetailsModal = openPostDetails;

async function retryHistoryPost(id) {
    try {
        const res = await authFetch(`/api/schedule/${id}/retry`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast(`Post #${id} returned to active publishing queue!`, 'success');
            renderHistory(document.getElementById('content-area'));
        } else {
            showToast(data.error || 'Failed to retry post', 'danger');
        }
    } catch (e) {
        showToast('Retry network error: ' + e.message, 'danger');
    }
}

// ==========================================================================
// VIEW: Dedicated Drafts Workspace
// ==========================================================================
let allDraftsList = [];
let draftsFilterStatus = 'all';
let draftsFilterPlatform = 'all';
let draftsSearchQuery = '';

async function renderDraftsView(container) {
    if (!container) return;
    container.innerHTML = `
        <div style="text-align: center; padding: 3rem 1rem;">
            <i class="fa-solid fa-spinner fa-spin fa-2x" style="color: var(--primary);"></i>
            <p style="margin-top: 1rem; color: var(--text-muted);">Loading Drafts Workspace...</p>
        </div>
    `;

    try {
        let drafts = [];
        const draftsRes = await authFetch('/api/drafts');
        if (draftsRes.ok) {
            const data = await draftsRes.json();
            drafts = data.drafts || [];
        } else {
            const campRes = await authFetch('/api/campaigns');
            const campaigns = campRes.ok ? await campRes.json() : [];
            for (const c of campaigns) {
                const dRes = await authFetch(`/api/campaigns/${c.id}/drafts`);
                if (dRes.ok) {
                    const cDrafts = await dRes.json();
                    cDrafts.forEach(d => {
                        d.campaign_name = d.campaign_name || c.name;
                        drafts.push(d);
                    });
                }
            }
        }

        allDraftsList = drafts;
        studioDrafts = drafts; // Sync with studioDrafts so modals and existing actions work seamlessly

        renderDraftsListUI(container);
    } catch (e) {
        container.innerHTML = `
            <div class="card" style="padding: 2rem; color: var(--danger); text-align: center;">
                <i class="fa-solid fa-triangle-exclamation fa-2x" style="margin-bottom: 0.5rem;"></i>
                <p>Failed to load drafts: ${escapeHtml(e.message)}</p>
            </div>
        `;
    }
}

function renderDraftsListUI(container) {
    const totalCount = allDraftsList.length;
    const approvedCount = allDraftsList.filter(d => d.status === 'approved').length;
    const draftCount = allDraftsList.filter(d => d.status === 'draft').length;
    const pendingCount = allDraftsList.filter(d => d.status === 'pending_approval').length;
    const scheduledCount = allDraftsList.filter(d => d.status === 'scheduled').length;

    // Filter
    let filtered = allDraftsList.filter(d => {
        if (draftsFilterStatus !== 'all' && d.status !== draftsFilterStatus) return false;
        if (draftsFilterPlatform !== 'all' && (d.target_platform || '').toLowerCase() !== draftsFilterPlatform) return false;
        if (draftsSearchQuery) {
            const q = draftsSearchQuery.toLowerCase();
            const text = `${d.headline || ''} ${d.caption || ''} ${d.hashtags || ''} ${d.campaign_name || ''}`.toLowerCase();
            if (!text.includes(q)) return false;
        }
        return true;
    });

    let html = `
        <div class="drafts-workspace-container">
            <!-- Header -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
                <div>
                    <h2 style="margin: 0; font-size: 1.35rem; font-weight: 800; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-file-pen" style="color: var(--primary);"></i> Content Drafts Workspace
                    </h2>
                    <p style="margin: 0.25rem 0 0 0; color: var(--text-muted); font-size: 0.88rem;">
                        Inspect, edit, validate, and convert brand-aligned copy into scheduled posts.
                    </p>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn btn-secondary btn-sm" onclick="renderDraftsView(document.getElementById('content-area'))">
                        <i class="fa-solid fa-rotate"></i> Refresh Drafts
                    </button>
                    <button class="btn btn-primary btn-sm" onclick="loadTab('composer')">
                        <i class="fa-solid fa-plus"></i> Create Post
                    </button>
                </div>
            </div>

            <!-- Stats Bar -->
            <div class="stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem; margin-bottom: 1.5rem;">
                <div class="stat-card" style="padding: 0.85rem; cursor: pointer; border: 1px solid ${draftsFilterStatus === 'all' ? 'var(--primary)' : 'var(--border)'};" onclick="draftsFilterStatus = 'all'; renderDraftsListUI(document.getElementById('content-area'))">
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700;">Total Drafts</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${totalCount}</div>
                </div>
                <div class="stat-card" style="padding: 0.85rem; cursor: pointer; border: 1px solid ${draftsFilterStatus === 'approved' ? 'var(--success)' : 'var(--border)'};" onclick="draftsFilterStatus = 'approved'; renderDraftsListUI(document.getElementById('content-area'))">
                    <div style="font-size: 0.75rem; color: var(--success); text-transform: uppercase; font-weight: 700;"><i class="fa-solid fa-check"></i> Approved</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${approvedCount}</div>
                </div>
                <div class="stat-card" style="padding: 0.85rem; cursor: pointer; border: 1px solid ${draftsFilterStatus === 'draft' ? '#94a3b8' : 'var(--border)'};" onclick="draftsFilterStatus = 'draft'; renderDraftsListUI(document.getElementById('content-area'))">
                    <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700;"><i class="fa-solid fa-pen-ruler"></i> In Draft</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${draftCount}</div>
                </div>
                <div class="stat-card" style="padding: 0.85rem; cursor: pointer; border: 1px solid ${draftsFilterStatus === 'pending_approval' ? 'var(--warning)' : 'var(--border)'};" onclick="draftsFilterStatus = 'pending_approval'; renderDraftsListUI(document.getElementById('content-area'))">
                    <div style="font-size: 0.75rem; color: var(--warning); text-transform: uppercase; font-weight: 700;"><i class="fa-solid fa-hourglass-half"></i> Pending Review</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${pendingCount}</div>
                </div>
                <div class="stat-card" style="padding: 0.85rem; cursor: pointer; border: 1px solid ${draftsFilterStatus === 'scheduled' ? 'var(--primary)' : 'var(--border)'};" onclick="draftsFilterStatus = 'scheduled'; renderDraftsListUI(document.getElementById('content-area'))">
                    <div style="font-size: 0.75rem; color: var(--primary); text-transform: uppercase; font-weight: 700;"><i class="fa-solid fa-calendar-check"></i> Scheduled</div>
                    <div style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-top: 0.2rem;">${scheduledCount}</div>
                </div>
            </div>

            <!-- Filters & Search Toolbar -->
            <div class="card" style="padding: 0.85rem 1.25rem; margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; flex: 1;">
                    <div class="search-box" style="min-width: 240px; position: relative;">
                        <input type="text" class="form-control" style="font-size: 0.85rem; padding-left: 2rem;" placeholder="Search drafts by hook, caption, hashtag..." value="${escapeHtml(draftsSearchQuery)}" oninput="draftsSearchQuery = this.value; renderDraftsListUI(document.getElementById('content-area'))">
                        <i class="fa-solid fa-magnifying-glass" style="position: absolute; left: 0.75rem; top: 50%; transform: translateY(-50%); color: var(--text-muted); font-size: 0.82rem;"></i>
                    </div>

                    <select class="form-control" style="font-size: 0.85rem; width: auto;" onchange="draftsFilterPlatform = this.value; renderDraftsListUI(document.getElementById('content-area'))">
                        <option value="all" ${draftsFilterPlatform === 'all' ? 'selected' : ''}>All Platforms</option>
                        <option value="facebook" ${draftsFilterPlatform === 'facebook' ? 'selected' : ''}>Facebook</option>
                        <option value="instagram" ${draftsFilterPlatform === 'instagram' ? 'selected' : ''}>Instagram</option>
                        <option value="linkedin" ${draftsFilterPlatform === 'linkedin' ? 'selected' : ''}>LinkedIn</option>
                        <option value="whatsapp" ${draftsFilterPlatform === 'whatsapp' ? 'selected' : ''}>WhatsApp</option>
                    </select>
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted); font-weight: 600;">
                    Showing ${filtered.length} of ${totalCount} Drafts
                </div>
            </div>

            <!-- Grid of Drafts -->
            ${filtered.length === 0 ? `
                <div class="card" style="text-align: center; padding: 3rem 1.5rem; border: 2px dashed var(--border);">
                    <i class="fa-regular fa-folder-open fa-2x" style="color: var(--text-muted); margin-bottom: 0.75rem;"></i>
                    <p style="color: var(--text-muted); margin: 0;">No content drafts match the selected filters.</p>
                </div>
            ` : `
                <div class="studio-drafts-grid">
                    ${filtered.map(d => renderStudioDraftCard(d)).join('')}
                </div>
            `}
        </div>
    `;
    container.innerHTML = html;
}

// ==========================================================================
// VIEW: Dedicated WhatsApp Cloud API Interface
// ==========================================================================
let waSelectedTemplate = 'client_welcome';
let waSelectedSenderId = '1298748379987770';
let waSimulatedLogs = [];
let waDualAccountsCache = [
    {
        phone_number_id: '1298748379987770',
        waba_id: '1471882524763501',
        display_phone_number: '+91 98257 28291',
        verified_name: 'Aidni Global',
        role: 'preferred_candidate',
        is_preferred_candidate: true,
        is_disconnected_legacy: false,
        platform_type: 'CLOUD_API',
        phone_status: 'CONNECTED',
        code_verification_status: 'NOT_VERIFIED',
        business_verification_status: 'verified',
        health_can_send: 'BLOCKED',
        approved_templates_count: 0,
        messaging_eligibility: { eligible: false, reason: 'Sending blocked pending verification, billing & templates' },
        billing_readiness: { ready: false, reason: 'Payment missing (141006) / Timezone unset (141007)' },
        template_readiness: { meta_approved_count: 0, local_preview_count: 4 }
    },
    {
        phone_number_id: '1171737406016871',
        waba_id: '1370721214882653',
        display_phone_number: '+91 90990 28291',
        verified_name: 'Gaatha Ventures',
        role: 'preserved_disconnected',
        is_preferred_candidate: false,
        is_disconnected_legacy: true,
        platform_type: 'ON_PREMISE',
        phone_status: 'DISCONNECTED',
        code_verification_status: 'NOT_VERIFIED',
        business_verification_status: 'not_verified',
        health_can_send: 'BLOCKED',
        approved_templates_count: 0,
        messaging_eligibility: { eligible: false, reason: 'ON_PREMISE / DISCONNECTED (Preserved only; never activated)' },
        billing_readiness: { ready: false, reason: 'Payment missing (141006) / Timezone unset (141007)' },
        template_readiness: { meta_approved_count: 0, local_preview_count: 4 }
    }
];

const WA_TEMPLATES = {
    'client_welcome': {
        name: 'client_welcome',
        label: 'Client Welcome & Onboarding',
        category: 'UTILITY',
        status: 'LOCAL_PREVIEW',
        meta_approved: false,
        body: 'Welcome to Gaatha Ventures! We are delighted to partner with you on your strategic growth journey. Our advisory team will reach out shortly with your tailored roadmap.'
    },
    'consultation_reminder': {
        name: 'consultation_reminder',
        label: 'Consultation Session Reminder',
        category: 'UTILITY',
        status: 'LOCAL_PREVIEW',
        meta_approved: false,
        body: 'Reminder: Your upcoming strategic consultation with Gaatha Ventures is scheduled for tomorrow at 11:00 AM IST. Please let us know if you need to adjust your calendar.'
    },
    'campaign_announcement': {
        name: 'campaign_announcement',
        label: 'Marketing Campaign Announcement',
        category: 'MARKETING',
        status: 'LOCAL_PREVIEW',
        meta_approved: false,
        body: 'Gaatha Ventures & Aidni Global LLP have released our new digital operations suite at https://gaatha.tech/. Explore how our systems accelerate enterprise growth.'
    },
    'custom_direct': {
        name: 'custom_direct',
        label: 'Custom Business Message (24h Window Only)',
        category: 'CONVERSATIONAL',
        status: 'LOCAL_PREVIEW',
        meta_approved: false,
        body: 'Hello from Gaatha Ventures. Thank you for your inquiry. We are reviewing your requirements and will provide an update shortly.'
    }
};

function _getSelectedWAAccount() {
    return waDualAccountsCache.find(a => a.phone_number_id === waSelectedSenderId) || waDualAccountsCache[0];
}

function _renderDualWhatsAppAccountCards(accounts) {
    return (accounts || []).map(acc => {
        const isPref = !!acc.is_preferred_candidate || acc.phone_number_id === '1298748379987770';
        const isDisc = !!acc.is_disconnected_legacy || acc.platform_type === 'ON_PREMISE' || acc.phone_status === 'DISCONNECTED';
        const borderCol = isPref ? 'var(--primary)' : 'var(--border)';
        const roleBadge = isPref
            ? '<span class="badge badge-info"><i class="fa-solid fa-star"></i> Preferred Future Candidate</span>'
            : '<span class="badge badge-neutral"><i class="fa-solid fa-lock"></i> Preserved (.env Ref &middot; Never Activate)</span>';
        const connBadge = `<span class="badge ${isDisc ? 'badge-warning' : 'badge-success'}">${escapeHtml(acc.platform_type || 'UNKNOWN')} &middot; ${escapeHtml(acc.phone_status || 'UNKNOWN')}</span>`;
        const verSummary = `Portfolio: ${escapeHtml(acc.business_verification_status || 'unknown')} &middot; OTP: ${escapeHtml(acc.code_verification_status || 'NOT_VERIFIED')} &middot; Name: ${escapeHtml(acc.name_status || 'UNREVIEWED')}`;
        const msgReason = (acc.messaging_eligibility && acc.messaging_eligibility.reason) || (isDisc ? 'Disconnected standby only' : 'Sending blocked pending readiness');
        const billReason = (acc.billing_readiness && acc.billing_readiness.reason) || 'Billing setup pending (141006)';
        const tplApproved = (acc.template_readiness && acc.template_readiness.meta_approved_count) ?? (acc.approved_templates_count ?? 0);
        const tplLocal = (acc.template_readiness && acc.template_readiness.local_preview_count) ?? 4;

        return `
            <div style="padding: 0.9rem 1rem; border: 1px solid var(--border); border-left: 4px solid ${borderCol}; border-radius: var(--radius-md); background: var(--bg-surface-subtle);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.55rem;">
                    <div>
                        <div style="font-size: 0.95rem; font-weight: 800; color: var(--text-primary);">${escapeHtml(acc.display_phone_number || acc.phone_number_id)} &mdash; ${escapeHtml(acc.verified_name || acc.business_name || '')}</div>
                        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.25rem;">
                            ${roleBadge}
                            ${connBadge}
                        </div>
                    </div>
                    <span class="badge badge-danger">Eligibility: BLOCKED</span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.35rem 0.75rem; font-size: 0.78rem; color: var(--text-secondary);">
                    <div><strong>Phone Number ID:</strong> <code>${escapeHtml(acc.phone_number_id)}</code></div>
                    <div><strong>WABA ID:</strong> <code>${escapeHtml(acc.waba_id)}</code></div>
                    <div><strong>Connection:</strong> ${escapeHtml(acc.platform_type || 'UNKNOWN')} / ${escapeHtml(acc.phone_status || 'UNKNOWN')}</div>
                    <div><strong>Templates:</strong> ${tplApproved} Meta-Approved &middot; ${tplLocal} Local Previews</div>
                    <div style="grid-column: 1 / -1;"><strong>Verification:</strong> ${verSummary}</div>
                    <div style="grid-column: 1 / -1;"><strong>Messaging Eligibility:</strong> ${escapeHtml(msgReason)}</div>
                    <div style="grid-column: 1 / -1;"><strong>Billing Readiness:</strong> ${escapeHtml(billReason)}</div>
                    <div style="grid-column: 1 / -1;"><strong>Brand Assignment:</strong> None (Auto-binding disabled) &middot; <strong>Sandbox vs Live:</strong> Sandbox Simulation Only</div>
                </div>
            </div>
        `;
    }).join('');
}

function renderWhatsAppView(container) {
    if (!container) return;

    const tpl = WA_TEMPLATES[waSelectedTemplate] || WA_TEMPLATES['client_welcome'];
    const selAcc = _getSelectedWAAccount();

    const html = `
        <div class="whatsapp-view-container">
            <!-- Header & Safe Mode Alert -->
            <div class="hub-hero hub-hero--whatsapp">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.35rem; flex-wrap: wrap;">
                            <i class="fa-brands fa-whatsapp fa-2x" style="color: #059669;"></i>
                            <h2 style="font-size: 1.35rem; font-weight: 800; margin: 0;">WhatsApp Cloud API Studio</h2>
                            <span id="wa-studio-verification-badge" class="badge badge-warning">
                                <i class="fa-solid fa-shield-halved"></i> Inspecting Dual Accounts...
                            </span>
                        </div>
                        <p id="wa-studio-subtitle" style="font-size: 0.88rem; margin: 0;">
                            Dual-account WhatsApp Studio. <strong>+91 98257 28291</strong> (Cloud API) is retained as preferred candidate; <strong>+91 90990 28291</strong> (ON_PREMISE) is preserved disconnected.
                        </p>
                    </div>
                    <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                        <span id="wa-studio-guardrail-pill" class="badge badge-warning">
                            <i class="fa-solid fa-lock"></i> WHATSAPP_PUBLISHING_ENABLED=0 (Sandbox Only)
                        </span>
                    </div>
                </div>
            </div>

            <!-- Safe Mode & Config Diagnosis Banner -->
            <div class="notice-callout notice-callout--info" style="margin-bottom: 1.25rem;">
                <i class="fa-solid fa-lock"></i>
                <div>
                    <strong>Sandbox vs Live Distinction:</strong> Live WhatsApp messaging is <strong>DISABLED</strong> (<code>WHATSAPP_PUBLISHING_ENABLED=0</code>) and sending remains blocked on Meta even for Cloud API lines until verification, billing, timezone, and templates are approved. Simulated messages execute locally only and are NEVER real deliveries.
                    <div id="wa-config-diagnosis-text" style="margin-top: 0.35rem; font-size: 0.8rem; color: var(--text-muted);">
                        Inspecting why .env and database previously surfaced +91 90990 28291...
                    </div>
                </div>
            </div>

            <!-- Dual Registered Accounts Matrix -->
            <div id="wa-readiness-panel" class="card" style="padding: 1.15rem 1.35rem; margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.85rem;">
                    <div style="font-size: 0.94rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-tower-observation" style="color: var(--primary);"></i> Registered WhatsApp Business Accounts (Independent Tracking)
                    </div>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        <span id="wa-templates-meta-pill" class="badge badge-warning">Meta Templates: Checking...</span>
                        <span id="wa-webhook-meta-pill" class="badge badge-warning">Webhook: Checking...</span>
                        <span id="wa-token-meta-pill" class="badge badge-warning">Token: Checking...</span>
                    </div>
                </div>
                <div id="wa-preserved-numbers-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 1rem;">
                    ${_renderDualWhatsAppAccountCards(waDualAccountsCache)}
                </div>
            </div>

            <!-- Two-Column Studio Layout -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 1.5rem; align-items: start;">
                <!-- Left Column: Message Dispatch Studio -->
                <div class="card" style="padding: 1.5rem;">
                    <h3 style="font-size: 1.05rem; font-weight: 700; margin-bottom: 1.25rem; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fa-solid fa-paper-plane" style="color: var(--success);"></i> Template Preview &amp; Sandbox Simulator
                    </h3>

                    <div style="margin-bottom: 1rem;">
                        <label for="wa-sender-select" style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.35rem; display: block;">Sender Account Selector (Both Numbers Â· Sandbox Preview)</label>
                        <select id="wa-sender-select" class="form-control" style="font-size: 0.85rem;" onchange="handleWASenderChange(this.value)">
                            ${waDualAccountsCache.map(a => `
                                <option value="${escapeHtml(a.phone_number_id)}" ${a.phone_number_id === waSelectedSenderId ? 'selected' : ''}>
                                    ${escapeHtml(a.display_phone_number)} &mdash; ID ${escapeHtml(a.phone_number_id)} &middot; WABA ${escapeHtml(a.waba_id)} (${a.is_preferred_candidate ? 'CLOUD_API Â· Preferred Candidate' : 'ON_PREMISE Â· Disconnected Preserved'})
                                </option>
                            `).join('')}
                        </select>
                        <div style="display: flex; align-items: center; gap: 0.65rem; padding: 0.6rem 0.8rem; margin-top: 0.5rem; background: var(--bg-surface-subtle); border: 1px solid var(--border); border-radius: var(--radius-md);">
                            <div style="width: 30px; height: 30px; border-radius: 50%; background: var(--success); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.8rem;">
                                WA
                            </div>
                            <div>
                                <div id="wa-sender-name" style="font-size: 0.84rem; font-weight: 700; color: var(--text-primary);">${escapeHtml(selAcc.verified_name || 'Aidni Global')} (${selAcc.is_preferred_candidate ? 'Preferred Candidate' : 'Preserved Disconnected'})</div>
                                <div id="wa-sender-meta" style="font-size: 0.74rem; color: var(--text-muted);">${escapeHtml(selAcc.display_phone_number)} &middot; WABA ${escapeHtml(selAcc.waba_id)} &middot; ${escapeHtml(selAcc.platform_type)} / ${escapeHtml(selAcc.phone_status)} &middot; No Auto Brand Binding</div>
                            </div>
                        </div>
                        <div id="wa-sender-policy-note" style="font-size: 0.74rem; margin-top: 0.35rem; color: var(--text-muted);">
                            Preferred future broadcasting candidate (+91 98257 28291) is selected for sandbox simulation; live dispatch blocked while WHATSAPP_PUBLISHING_ENABLED=0.
                        </div>
                    </div>

                    <div style="margin-bottom: 1rem;">
                        <label style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.35rem; display: block;">Test Recipient Phone (Sandbox Only)</label>
                        <input type="text" id="wa-recipient-input" class="form-control" value="+91 98257 28291" placeholder="+91XXXXXXXXXX" style="font-size: 0.88rem;">
                        <small style="color: var(--text-muted); font-size: 0.74rem;">Include international E.164 country code prefix (e.g. +91, +1, +44)</small>
                    </div>

                    <div style="margin-bottom: 1rem;">
                        <label style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.35rem; display: block;">Message Template (Local Previews â€” Not Meta-Approved)</label>
                        <select id="wa-template-select" class="form-control" style="font-size: 0.88rem;" onchange="handleWATemplateChange(this.value)">
                            ${Object.keys(WA_TEMPLATES).map(k => `
                                <option value="${k}" ${k === waSelectedTemplate ? 'selected' : ''}>${WA_TEMPLATES[k].label} (${WA_TEMPLATES[k].category} Â· Local Preview)</option>
                            `).join('')}
                        </select>
                    </div>

                    <div style="margin-bottom: 1.25rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                            <label style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0;">Message Content</label>
                            <span id="wa-char-count" style="font-size: 0.74rem; color: var(--text-muted);">${tpl.body.length} / 1024 chars</span>
                        </div>
                        <textarea id="wa-message-body" class="form-control" rows="5" style="font-size: 0.88rem; line-height: 1.45;" oninput="handleWAMessageInput(this.value)">${escapeHtml(tpl.body)}</textarea>
                    </div>

                    <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
                        <button type="button" class="btn btn-success" onclick="handleWASendSimulation()" style="flex: 1;">
                            <i class="fa-solid fa-flask"></i> Run Sandbox Simulation (Not Live)
                        </button>
                        <button type="button" class="btn btn-secondary" onclick="handleWAValidateFormat()">
                            <i class="fa-solid fa-code"></i> Validate Format
                        </button>
                    </div>
                </div>

                <!-- Right Column: Sandbox Preview Phone Mockup -->
                <div>
                    <div class="card" style="padding: 1.5rem; background: #0b141a; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 18px; max-width: 420px; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 0.75rem; margin-bottom: 1rem;">
                            <div style="display: flex; align-items: center; gap: 0.6rem;">
                                <i class="fa-solid fa-arrow-left" style="color: #8696a0; font-size: 0.85rem;"></i>
                                <div style="width: 36px; height: 36px; border-radius: 50%; background: #128c7e; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.85rem;">
                                    WA
                                </div>
                                <div>
                                    <div id="wa-mockup-header-name" style="font-size: 0.88rem; font-weight: 700; color: #e9edef; display: flex; align-items: center; gap: 0.3rem;">
                                        ${escapeHtml(selAcc.verified_name || 'Aidni Global')}
                                    </div>
                                    <div id="wa-mockup-header-sub" style="font-size: 0.72rem; color: #fbbf24;">Sandbox Preview (${escapeHtml(selAcc.display_phone_number)}) Â· Not Sent</div>
                                </div>
                            </div>
                        </div>

                        <div style="min-height: 220px; display: flex; flex-direction: column; justify-content: flex-end; padding: 0.5rem 0;">
                            <div style="text-align: center; margin-bottom: 1rem;">
                                <span style="background: #182229; color: #fbbf24; font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 6px;">SANDBOX PREVIEW ONLY Â· NOT SENT TO META</span>
                            </div>

                            <div style="align-self: flex-end; max-width: 90%; background: #005c4b; color: #e9edef; padding: 0.65rem 0.85rem; border-radius: 10px 10px 2px 10px; font-size: 0.84rem; line-height: 1.45; box-shadow: 0 1px 2px rgba(0,0,0,0.3); word-break: break-word; position: relative;">
                                <div id="wa-preview-text">${escapeHtml(tpl.body)}</div>
                                <div style="display: flex; align-items: center; justify-content: flex-end; gap: 0.3rem; margin-top: 0.35rem; font-size: 0.68rem; color: rgba(255,255,255,0.7);">
                                    <span id="wa-preview-time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                    <span>LOCAL SIMULATION</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Sandbox Simulation Log (explicitly never shown as delivered) -->
                    <div class="card" style="margin-top: 1.25rem; padding: 1rem;">
                        <h4 style="font-size: 0.85rem; font-weight: 700; margin-bottom: 0.6rem; color: var(--text-muted); text-transform: uppercase;">
                            <i class="fa-solid fa-flask"></i> Sandbox Simulation Log (Local Only Â· Not Meta Delivery)
                        </h4>
                        <div id="wa-activity-log" style="display: flex; flex-direction: column; gap: 0.4rem;">
                            ${waSimulatedLogs.length === 0 ? '<div style="font-size: 0.78rem; color: var(--text-muted);">No sandbox simulations run yet. Local simulations never send external WhatsApp messages.</div>' : ''}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    container.innerHTML = html;

    Promise.all([
        authFetch('/api/integrations/whatsapp/status').then(r => (r.ok ? r.json() : null)).catch(() => null),
        authFetch('/api/whatsapp/templates').then(r => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([wa, tplData]) => {
        if (!wa) return;
        const accts = Array.isArray(wa.accounts) ? wa.accounts : (Array.isArray(wa.numbers) ? wa.numbers : []);
        if (accts.length > 0) {
            waDualAccountsCache = accts;
            const selEl = document.getElementById('wa-sender-select');
            if (selEl) {
                selEl.innerHTML = accts.map(a => `
                    <option value="${escapeHtml(a.phone_number_id)}" ${a.phone_number_id === waSelectedSenderId ? 'selected' : ''}>
                        ${escapeHtml(a.display_phone_number)} &mdash; ID ${escapeHtml(a.phone_number_id)} &middot; WABA ${escapeHtml(a.waba_id)} (${a.is_preferred_candidate ? 'CLOUD_API Â· Preferred Candidate' : 'ON_PREMISE Â· Disconnected Preserved'})
                    </option>
                `).join('');
            }
            const numsGrid = document.getElementById('wa-preserved-numbers-grid');
            if (numsGrid) {
                numsGrid.innerHTML = _renderDualWhatsAppAccountCards(accts);
            }
            handleWASenderChange(waSelectedSenderId, true);
        }

        const badgeEl = document.getElementById('wa-studio-verification-badge');
        const guardEl = document.getElementById('wa-studio-guardrail-pill');
        const diagEl = document.getElementById('wa-config-diagnosis-text');
        const tplPill = document.getElementById('wa-templates-meta-pill');
        const whPill = document.getElementById('wa-webhook-meta-pill');
        const tokPill = document.getElementById('wa-token-meta-pill');

        if (badgeEl) {
            badgeEl.className = 'badge badge-warning';
            badgeEl.innerHTML = `<i class="fa-solid fa-shield-halved"></i> ${escapeHtml(wa.status_label || 'Verification Required')}`;
        }
        if (guardEl) {
            guardEl.className = `badge ${wa.publishing_enabled ? 'badge-published' : 'badge-warning'}`;
            guardEl.innerHTML = wa.publishing_enabled
                ? '<i class="fa-solid fa-tower-broadcast"></i> WhatsApp Broadcast Active'
                : '<i class="fa-solid fa-lock"></i> WHATSAPP_PUBLISHING_ENABLED=0 (Sandbox Only)';
        }
        if (diagEl && wa.config_diagnosis && wa.config_diagnosis.why_90990_appeared) {
            diagEl.textContent = `Configuration Diagnosis: ${wa.config_diagnosis.why_90990_appeared}`;
        }
        if (tplPill) {
            const liveApproved = tplData ? (tplData.meta_approved_count ?? 0) : (wa.approved_templates_count ?? 0);
            const localCount = tplData ? (tplData.local_previews_count ?? 4) : (wa.local_preview_templates_count ?? 4);
            tplPill.className = `badge ${liveApproved > 0 ? 'badge-published' : 'badge-warning'}`;
            tplPill.textContent = `Meta Templates: ${liveApproved} Approved Â· ${localCount} Local Previews`;
        }
        if (whPill && wa.webhook_status) {
            const whReady = wa.webhook_status.app_secret_configured && wa.webhook_status.postpilot_app_subscribed;
            whPill.className = `badge ${whReady ? 'badge-published' : 'badge-warning'}`;
            whPill.textContent = whReady
                ? 'Webhook: Subscribed & Signed'
                : `Webhook: ${wa.webhook_status.app_secret_configured ? 'Secret OK' : 'Secret Missing'} Â· ${wa.webhook_status.postpilot_app_subscribed ? 'Subscribed' : 'Not Subscribed'}`;
        }
        if (tokPill && wa.token_health) {
            const tokOk = !!wa.token_health.valid;
            tokPill.className = `badge ${tokOk ? 'badge-published' : 'badge-danger'}`;
            tokPill.textContent = tokOk ? 'Token: Valid (Scoped)' : 'Token: Needs Attention';
        }
    });
}

function handleWASenderChange(senderId, silent) {
    waSelectedSenderId = senderId || '1298748379987770';
    const acc = _getSelectedWAAccount();
    const nameEl = document.getElementById('wa-sender-name');
    const metaEl = document.getElementById('wa-sender-meta');
    const noteEl = document.getElementById('wa-sender-policy-note');
    const mockName = document.getElementById('wa-mockup-header-name');
    const mockSub = document.getElementById('wa-mockup-header-sub');

    if (nameEl) {
        nameEl.textContent = `${acc.verified_name || acc.business_name || 'WhatsApp Business'} (${acc.is_preferred_candidate ? 'Preferred Candidate' : 'Preserved Disconnected'})`;
    }
    if (metaEl) {
        metaEl.textContent = `${acc.display_phone_number} Â· WABA ${acc.waba_id} Â· ${acc.platform_type} / ${acc.phone_status} Â· No Auto Brand Binding`;
    }
    if (noteEl) {
        if (acc.is_disconnected_legacy || acc.platform_type === 'ON_PREMISE') {
            noteEl.innerHTML = '<span style="color: var(--warning);"><strong>Notice:</strong> +91 90990 28291 is ON_PREMISE / DISCONNECTED and preserved only â€” it will NEVER be activated. Sandbox preview stays local.</span>';
        } else {
            noteEl.textContent = 'Preferred future broadcasting candidate (+91 98257 28291) selected for sandbox simulation; live dispatch blocked pending readiness & WHATSAPP_PUBLISHING_ENABLED=0.';
        }
    }
    if (mockName) mockName.textContent = acc.verified_name || 'Aidni Global';
    if (mockSub) mockSub.textContent = `Sandbox Preview (${acc.display_phone_number}) Â· Not Sent`;
    if (!silent) {
        showToast(`Selected sender preview: ${acc.display_phone_number} (Sandbox Only)`, 'info');
    }
}

function handleWATemplateChange(templateKey) {
    waSelectedTemplate = templateKey;
    const tpl = WA_TEMPLATES[templateKey];
    if (tpl) {
        const bodyEl = document.getElementById('wa-message-body');
        const charEl = document.getElementById('wa-char-count');
        const prevEl = document.getElementById('wa-preview-text');
        if (bodyEl) bodyEl.value = tpl.body;
        if (charEl) charEl.textContent = `${tpl.body.length} / 1024 chars`;
        if (prevEl) prevEl.textContent = tpl.body;
    }
}

function handleWAMessageInput(text) {
    const charEl = document.getElementById('wa-char-count');
    const prevEl = document.getElementById('wa-preview-text');
    if (charEl) charEl.textContent = `${text.length} / 1024 chars`;
    if (prevEl) prevEl.textContent = text;
}

function _renderWASimulatedLogs() {
    const logEl = document.getElementById('wa-activity-log');
    if (!logEl) return;
    if (waSimulatedLogs.length === 0) {
        logEl.innerHTML = '<div style="font-size: 0.78rem; color: var(--text-muted);">No sandbox simulations run yet.</div>';
        return;
    }
    logEl.innerHTML = waSimulatedLogs.map(l => `
        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; padding: 0.45rem 0.6rem; background: var(--bg-surface-subtle); border-radius: 6px; border: 1px solid var(--border); gap: 0.5rem;">
            <div>
                <span style="font-weight: 600; color: var(--text-primary);">To: ${escapeHtml(l.recipient)}</span>
                <span style="color: var(--text-muted); margin-left: 0.35rem;">via ${escapeHtml(l.senderLabel || '')}</span>
                <div style="color: var(--text-muted); font-size: 0.72rem;">${escapeHtml(l.template)}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.4rem;">
                <span class="badge badge-warning" style="font-size: 0.68rem;">${escapeHtml(l.status)}</span>
                <span style="color: var(--text-muted); font-size: 0.72rem;">${escapeHtml(l.time)}</span>
            </div>
        </div>
    `).join('');
}

function handleWAValidateFormat() {
    const recip = document.getElementById('wa-recipient-input')?.value || '';
    const text = document.getElementById('wa-message-body')?.value || '';
    authFetch('/api/whatsapp/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            recipient_phone: recip,
            template_name: waSelectedTemplate,
            message: text,
            phone_number_id: waSelectedSenderId,
        }),
    })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (ok && d.success) {
                showToast(`Format & E.164 validated (${d.recipient_phone}) for sender ${d.sender_phone_number_id}. Sandbox only.`, 'success');
            } else {
                showToast(d.error || 'Template payload validation failed.', 'warning');
            }
        })
        .catch(() => {
            showToast('Validation request failed cleanly.', 'warning');
        });
}

function handleWASendSimulation() {
    const recip = document.getElementById('wa-recipient-input')?.value || '';
    const text = document.getElementById('wa-message-body')?.value || '';
    if (!text.trim()) {
        showToast("Message body cannot be empty.", "warning");
        return;
    }
    const selAcc = _getSelectedWAAccount();

    authFetch('/api/whatsapp/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            recipient_phone: recip,
            template_name: waSelectedTemplate,
            message: text,
            phone_number_id: waSelectedSenderId,
        }),
    })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok || !d.success) {
                showToast(d.error || "Sandbox simulation validation failed.", "warning");
                return;
            }
            const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            waSimulatedLogs.unshift({
                time: now,
                recipient: d.recipient_phone || recip,
                senderLabel: selAcc.display_phone_number || waSelectedSenderId,
                template: `${waSelectedTemplate} (${d.external_message_id || 'sim'})`,
                status: 'Simulated Only (Not Sent)',
            });
            showToast(`[SANDBOX ONLY] Validated & simulated locally for ${d.recipient_phone || recip} via ${selAcc.display_phone_number}. Zero external WhatsApp dispatch.`, "info");
            _renderWASimulatedLogs();
        })
        .catch(() => {
            showToast("Sandbox simulation failed cleanly.", "warning");
        });
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
                                <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.draft || 0) / Math.max(1, totalDrafts)) * 100)}%; background: var(--text-muted); height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Pending Approval</span>
                                    <span style="font-weight: 700;">${funnel.pending_approval || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.pending_approval || 0) / Math.max(1, totalDrafts)) * 100)}%; background: var(--warning); height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Approved</span>
                                    <span style="font-weight: 700;">${funnel.approved || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.approved || 0) / Math.max(1, totalDrafts)) * 100)}%; background: var(--success); height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Scheduled &amp; Queued</span>
                                    <span style="font-weight: 700;">${funnel.scheduled || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.scheduled || 0) / Math.max(1, totalDrafts)) * 100)}%; background: var(--primary); height: 100%;"></div>
                                </div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 0.25rem;">
                                    <span>Published Dispatches</span>
                                    <span style="font-weight: 700;">${funnel.published || 0}</span>
                                </div>
                                <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="width: ${Math.min(100, ((funnel.published || 0) / Math.max(1, totalDrafts)) * 100)}%; background: var(--success); height: 100%;"></div>
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
                                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.7rem; background: var(--bg-surface-subtle); border-radius: var(--radius-md); border: 1px solid var(--border);">
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

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 1.25rem; margin-bottom: 1.5rem;">
                    <!-- Appearance & Theme Card (Light-first SaaS Default) -->
                    <div class="card" style="padding: 1.25rem;">
                        <h4 style="margin: 0 0 0.5rem 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                            <i class="fa-solid fa-palette" style="color: var(--primary);"></i> Interface Appearance
                        </h4>
                        <p style="font-size: 0.84rem; color: var(--text-secondary); margin: 0 0 1rem 0;">
                            PostPilot defaults to high-clarity Light Mode for editorial accuracy. Switch cleanly to optional Dark Mode whenever preferred.
                        </p>
                        <div class="theme-choice-group" role="group" aria-label="Interface Theme Selection">
                            <button type="button" class="theme-choice-card ${getCurrentTheme() === 'light' ? 'active' : ''}" data-theme-value="light" onclick="setTheme('light')">
                                <i class="fa-solid fa-sun" style="color: var(--accent-gold);"></i> Light Mode (Default)
                            </button>
                            <button type="button" class="theme-choice-card ${getCurrentTheme() === 'dark' ? 'active' : ''}" data-theme-value="dark" onclick="setTheme('dark')">
                                <i class="fa-solid fa-moon" style="color: var(--primary);"></i> Dark Mode
                            </button>
                        </div>
                    </div>

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
                                    <i class="fa-solid fa-crown" style="color: var(--accent-gold);"></i> Subscription Plan
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
                                    <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                        <div style="width: ${tokensPct}%; background: var(--accent-gold); height: 100%;"></div>
                                    </div>
                                </div>
                                <div>
                                    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.25rem;">
                                        <span>Campaigns: <strong>${campsUsed} / ${campsLimit}</strong></span>
                                        <span>${campsPct}%</span>
                                    </div>
                                    <div style="background: var(--bg-surface-subtle); height: 8px; border-radius: 4px; overflow: hidden;">
                                        <div style="width: ${campsPct}%; background: var(--primary); height: 100%;"></div>
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
                                <tr style="background: var(--bg-surface-subtle); border-bottom: 1px solid var(--border);">
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

                <!-- Legal & Public Information Card -->
                <div class="card" style="padding: 1.25rem; margin-top: 1.25rem; border-left: 4px solid var(--primary);">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                        <div>
                            <h4 style="margin: 0 0 0.25rem 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.5rem;">
                                <i class="fa-solid fa-scale-balanced" style="color: var(--primary);"></i> Legal Governance &amp; Public Policies
                            </h4>
                            <p style="margin: 0; font-size: 0.85rem; color: var(--text-muted);">
                                Review terms of service, acceptable use guidelines, privacy practices, and platform identity.
                            </p>
                        </div>
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                            <a href="/about" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration: none;">
                                <i class="fa-solid fa-circle-info"></i> About Us
                            </a>
                            <a href="/privacy" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration: none;">
                                <i class="fa-solid fa-shield-halved"></i> Privacy Policy
                            </a>
                            <a href="/terms" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration: none;">
                                <i class="fa-solid fa-file-contract"></i> Terms of Service
                            </a>
                        </div>
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
            <div style="background: var(--bg-surface-subtle); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 0.75rem 1rem; display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem;">
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
