/**
 * FOTW Service Admin - Dashboard JavaScript
 */

const API_BASE = '';
let refreshInterval = null;
let isLive = true;
let currentSort = { field: 'status', direction: 'asc' };
let cachedServices = [];

// ============================================================
// Alerts System
// ============================================================
let systemAlerts = [];

function addAlert(type, title, message, source = null) {
    // Avoid duplicate alerts from same source
    const existingIdx = systemAlerts.findIndex(a => a.source === source && a.title === title);
    if (existingIdx >= 0) {
        // Update existing alert
        systemAlerts[existingIdx].message = message;
        systemAlerts[existingIdx].time = new Date();
    } else {
        systemAlerts.push({
            id: Date.now() + Math.random(),
            type,  // 'error', 'warning', 'info'
            title,
            message,
            source,
            time: new Date()
        });
    }
    updateAlertsUI();
}

function removeAlert(source, title = null) {
    if (title) {
        systemAlerts = systemAlerts.filter(a => !(a.source === source && a.title === title));
    } else {
        systemAlerts = systemAlerts.filter(a => a.source !== source);
    }
    updateAlertsUI();
}

function clearAlerts() {
    systemAlerts = [];
    updateAlertsUI();
}

function updateAlertsUI() {
    const btn = document.getElementById('alerts-btn');
    const countEl = document.getElementById('alerts-count');
    const errorCount = systemAlerts.filter(a => a.type === 'error').length;
    const totalCount = systemAlerts.length;

    if (totalCount > 0) {
        btn.classList.add('has-alerts');
        countEl.textContent = totalCount;
        countEl.classList.remove('hidden');
    } else {
        btn.classList.remove('has-alerts');
        countEl.classList.add('hidden');
    }
}

function openAlertsPanel() {
    const modal = document.getElementById('alerts-modal');
    const listEl = document.getElementById('alerts-list');

    if (systemAlerts.length === 0) {
        listEl.innerHTML = '<div class="alerts-empty">No alerts - all systems operational</div>';
    } else {
        listEl.innerHTML = systemAlerts.map(alert => {
            const icon = alert.type === 'error' ? '✕' : alert.type === 'warning' ? '⚠' : 'ℹ';
            const timeStr = alert.time.toLocaleTimeString();
            return `
                <div class="alert-item ${alert.type}">
                    <span class="alert-icon">${icon}</span>
                    <div class="alert-content">
                        <div class="alert-title">${alert.title}</div>
                        <div class="alert-message">${alert.message}</div>
                        <div class="alert-time">${timeStr}</div>
                    </div>
                    <button class="alert-dismiss" onclick="dismissAlert(${alert.id})" title="Dismiss">&times;</button>
                </div>
            `;
        }).join('');
    }

    modal.classList.remove('hidden');
}

function closeAlertsPanel() {
    document.getElementById('alerts-modal').classList.add('hidden');
}

function dismissAlert(id) {
    systemAlerts = systemAlerts.filter(a => a.id !== id);
    updateAlertsUI();
    // Re-render if modal is open
    if (!document.getElementById('alerts-modal').classList.contains('hidden')) {
        openAlertsPanel();
    }
}

// Check status response for issues
function checkStatusForAlerts(data) {
    // Check Redis buses
    if (data.redis) {
        for (const [name, info] of Object.entries(data.redis)) {
            if (!info.running) {
                addAlert('error', `${name} Down`, `Redis bus ${name} is not running`, `redis:${name}`);
            } else {
                removeAlert(`redis:${name}`);
            }
        }
    }

    // Check truth loaded
    if (data.truth === false) {
        addAlert('warning', 'Truth Not Loaded', 'truth.json is not loaded in Redis', 'truth');
    } else {
        removeAlert('truth');
    }
}

// Check analytics response for issues
function checkAnalyticsForAlerts(analytics) {
    for (const [name, info] of Object.entries(analytics)) {
        if (info.error) {
            addAlert('error', `Analytics: ${name}`, info.error, `analytics:${name}`);
        } else {
            removeAlert(`analytics:${name}`);
        }
    }
}

// ENV config storage
const ENV_STORAGE_KEY = 'marketswarm_env_config';

function loadEnvConfig() {
    try {
        const stored = localStorage.getItem(ENV_STORAGE_KEY);
        return stored ? JSON.parse(stored) : { global: {}, services: {} };
    } catch (e) {
        return { global: {}, services: {} };
    }
}

function saveEnvConfigToStorage(config) {
    localStorage.setItem(ENV_STORAGE_KEY, JSON.stringify(config));
}

function parseEnvText(text) {
    const env = {};
    if (!text) return env;
    text.split('\n').forEach(line => {
        line = line.trim();
        if (!line || line.startsWith('#')) return;
        const idx = line.indexOf('=');
        if (idx > 0) {
            const key = line.substring(0, idx).trim();
            const value = line.substring(idx + 1).trim();
            if (key) env[key] = value;
        }
    });
    return env;
}

function envToText(env) {
    return Object.entries(env || {}).map(([k, v]) => `${k}=${v}`).join('\n');
}

function getEnvForService(serviceName) {
    const config = loadEnvConfig();
    return {
        ...config.global,
        ...(config.services[serviceName] || {})
    };
}

// Admin server info cache
let cachedAdminInfo = null;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    refreshStatus();
    startLiveUpdates();
    loadAdminVersion();
    // Also fetch analytics on startup to populate alerts
    setTimeout(refreshAnalytics, 1000);
    // Load ML Lab data
    setTimeout(refreshMLLab, 500);
});

// Load admin version on startup
async function loadAdminVersion() {
    try {
        const response = await fetch(`${API_BASE}/api/admin/info`);
        if (response.ok) {
            cachedAdminInfo = await response.json();
            const versionEl = document.getElementById('admin-version');
            if (versionEl) {
                versionEl.textContent = `v${cachedAdminInfo.version}`;
            }
        }
    } catch (error) {
        console.error('Failed to load admin info:', error);
    }
}

// Open admin info modal
function openAdminInfo() {
    const modal = document.getElementById('admin-info-modal');

    if (cachedAdminInfo) {
        displayAdminInfo(cachedAdminInfo);
    } else {
        // Fetch if not cached
        fetch(`${API_BASE}/api/admin/info`)
            .then(r => r.json())
            .then(info => {
                cachedAdminInfo = info;
                displayAdminInfo(info);
            })
            .catch(err => {
                document.getElementById('admin-info-features').innerHTML =
                    `<div class="error">Failed to load: ${err.message}</div>`;
            });
    }

    modal.classList.remove('hidden');
}

function displayAdminInfo(info) {
    document.getElementById('admin-info-version').textContent = info.version || '-';
    document.getElementById('admin-info-build').textContent = info.build_date || '-';
    document.getElementById('admin-info-config').textContent = info.config_file || '-';

    const featuresEl = document.getElementById('admin-info-features');
    if (info.features && info.features.length > 0) {
        featuresEl.innerHTML = info.features.map(f => `
            <div class="admin-feature">
                <span class="admin-feature-icon">✓</span>
                <div class="admin-feature-info">
                    <div class="admin-feature-name">${f.name}</div>
                    <div class="admin-feature-desc">${f.desc}</div>
                </div>
            </div>
        `).join('');
    } else {
        featuresEl.innerHTML = '<div class="text-muted">No features listed</div>';
    }
}

function closeAdminInfo() {
    document.getElementById('admin-info-modal').classList.add('hidden');
}

// Toggle live updates
function toggleLive() {
    const checkbox = document.getElementById('live-toggle');
    isLive = checkbox.checked;
    if (isLive) {
        startLiveUpdates();
    } else {
        stopLiveUpdates();
    }
}

function startLiveUpdates() {
    stopLiveUpdates();
    refreshInterval = setInterval(refreshStatus, 5000);
}

function stopLiveUpdates() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Fetch status and update UI
async function refreshStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        if (!response.ok) throw new Error('Failed to fetch status');
        const data = await response.json();

        updateNodeInfo(data.node);
        updateRedisStatus(data.redis);
        updateTruthStatus(data.truth);
        updateServicesList(data.services);
        updateServiceSummary(data.services);
        updateServiceSelect(data.services);
        updateLastUpdate(data.timestamp);

        // Check for issues and update alerts
        checkStatusForAlerts(data);
    } catch (error) {
        console.error('Failed to refresh status:', error);
        addAlert('error', 'Status Fetch Failed', error.message, 'status-fetch');
    }
}

// Update node info badge
function updateNodeInfo(node) {
    const badge = document.getElementById('node-info');
    const repoEl = document.getElementById('repo-path');

    if (!node) {
        badge.textContent = 'Unknown Node';
        badge.className = 'node-badge';
        if (repoEl) repoEl.textContent = 'Repo: unknown';
        return;
    }

    badge.textContent = `${node.name} (${node.env})`;
    badge.className = `node-badge ${node.env}`;
    document.title = `${node.name} - MarketSwarm Node Admin`;

    // Show repo path in footer
    if (repoEl && node.repo_path) {
        repoEl.textContent = `Repo: ${node.repo_path}`;
        repoEl.title = node.repo_path;
    }
}

// Update Redis bus status
function updateRedisStatus(redis) {
    const container = document.getElementById('redis-status');
    if (!redis) {
        container.innerHTML = '<div class="status-item"><span class="status-dot stopped"></span>Unknown</div>';
        return;
    }

    container.innerHTML = Object.entries(redis).map(([name, info]) => `
        <div class="status-item">
            <span class="status-dot ${info.running ? 'running' : 'stopped'}"></span>
            <span>${name.replace('-redis', '')}</span>
            <span style="color: var(--text-muted); margin-left: auto;">:${info.port}</span>
        </div>
    `).join('');
}

// Update truth status
function updateTruthStatus(truth) {
    const container = document.getElementById('truth-status');
    if (truth) {
        container.innerHTML = '<span class="status-value ok">Loaded in Redis</span>';
    } else {
        container.innerHTML = '<span class="status-value warn">Not loaded</span>';
    }
}

// ============================================================
// Redis Control Functions
// ============================================================

async function startRedis() {
    const statusEl = document.getElementById('redis-status');
    statusEl.innerHTML = '<div class="loading">Starting Redis buses...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/redis/start`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            updateRedisStatus(data.buses);
            removeAlert('redis:system-redis');
            removeAlert('redis:market-redis');
            removeAlert('redis:intel-redis');
        } else {
            statusEl.innerHTML = `<div class="status-value error">Failed: ${data.error || 'Unknown error'}</div>`;
            addAlert('error', 'Redis Start Failed', data.error || 'Unknown error', 'redis-control');
        }
    } catch (error) {
        statusEl.innerHTML = `<div class="status-value error">Error: ${error.message}</div>`;
        addAlert('error', 'Redis Start Failed', error.message, 'redis-control');
    }
}

async function stopRedis() {
    if (!confirm('Stop all Redis buses? This will affect running services.')) {
        return;
    }

    const statusEl = document.getElementById('redis-status');
    statusEl.innerHTML = '<div class="loading">Stopping Redis buses...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/redis/stop`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            updateRedisStatus(data.buses);
        } else {
            statusEl.innerHTML = `<div class="status-value error">Failed: ${data.error || 'Unknown error'}</div>`;
            addAlert('error', 'Redis Stop Failed', data.error || 'Unknown error', 'redis-control');
        }
    } catch (error) {
        statusEl.innerHTML = `<div class="status-value error">Error: ${error.message}</div>`;
        addAlert('error', 'Redis Stop Failed', error.message, 'redis-control');
    }
}

// ============================================================
// Truth Control Functions
// ============================================================

async function loadTruth() {
    const statusEl = document.getElementById('truth-status');
    statusEl.innerHTML = '<span class="status-value">Loading truth...</span>';

    try {
        const response = await fetch(`${API_BASE}/api/truth/load`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            statusEl.innerHTML = '<span class="status-value ok">Loaded in Redis</span>';
            removeAlert('truth');
        } else {
            statusEl.innerHTML = `<span class="status-value error">Failed</span>`;
            addAlert('error', 'Truth Load Failed', data.error || 'Unknown error', 'truth-control');
        }
    } catch (error) {
        statusEl.innerHTML = `<span class="status-value error">Error</span>`;
        addAlert('error', 'Truth Load Failed', error.message, 'truth-control');
    }
}

async function updateTruth() {
    const statusEl = document.getElementById('truth-status');
    statusEl.innerHTML = '<span class="status-value">Updating truth...</span>';

    try {
        const response = await fetch(`${API_BASE}/api/truth/update`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            statusEl.innerHTML = '<span class="status-value ok">Loaded in Redis</span>';
            removeAlert('truth');
        } else {
            statusEl.innerHTML = `<span class="status-value error">Failed</span>`;
            addAlert('error', 'Truth Update Failed', data.error || 'Unknown error', 'truth-control');
        }
    } catch (error) {
        statusEl.innerHTML = `<span class="status-value error">Error</span>`;
        addAlert('error', 'Truth Update Failed', error.message, 'truth-control');
    }
}

// Update service summary
function updateServiceSummary(services) {
    const container = document.getElementById('service-summary');
    if (!services || !services.length) {
        container.innerHTML = '<span class="status-value">No services</span>';
        return;
    }

    const running = services.filter(s => s.running).length;
    const total = services.length;
    const statusClass = running === total ? 'ok' : (running > 0 ? 'warn' : 'error');

    container.innerHTML = `<span class="status-value ${statusClass}">${running}/${total} running</span>`;
}

// Check if a service has env overrides
function hasEnvOverrides(serviceName) {
    const config = loadEnvConfig();
    const overrides = config.services[serviceName];
    return overrides && Object.keys(overrides).length > 0;
}

function getOverrideCount(serviceName) {
    const config = loadEnvConfig();
    const overrides = config.services[serviceName];
    return overrides ? Object.keys(overrides).length : 0;
}

// Update services list
function updateServicesList(services) {
    const container = document.getElementById('services-list');
    if (!services || !services.length) {
        container.innerHTML = '<div style="padding: 16px; color: var(--text-muted);">No services found</div>';
        return;
    }

    // Cache and sort
    cachedServices = services;
    const sorted = sortServices(services);

    container.innerHTML = sorted.map(service => {
        let uptime = '';
        if (service.running) {
            uptime = service.uptime_seconds != null
                ? formatUptime(service.uptime_seconds)
                : '-';  // Running but no tracking (started before admin)
        }
        const overrideCount = getOverrideCount(service.name);
        const overrideAsterisk = overrideCount > 0
            ? `<span class="override-asterisk" title="${overrideCount} env override(s)">*</span>`
            : '';
        return `
        <div class="service-row" data-service="${service.name}" title="${service.description || ''}">
            <div class="service-status ${service.running ? 'running' : 'stopped'}"></div>
            <div class="service-name">${service.name}${overrideAsterisk}</div>
            ${service.port ? `<div class="service-port">:${service.port}</div>` : '<div class="service-port">-</div>'}
            <div class="service-uptime">${uptime}</div>
            <div class="service-actions">
                ${service.running
                    ? `<button class="btn btn-danger btn-sm" onclick="stopService('${service.name}')">Stop</button>`
                    : `<button class="btn btn-success btn-sm" onclick="startService('${service.name}')">Start</button>`
                }
                <button class="btn btn-secondary btn-sm" onclick="viewLogs('${service.name}')">Logs</button>
            </div>
        </div>
    `}).join('');
}

// Update service select dropdown
function updateServiceSelect(services) {
    const select = document.getElementById('log-service-select');
    const currentValue = select.value;

    select.innerHTML = '<option value="">Select service...</option>' +
        services.map(s => `<option value="${s.name}">${s.name}</option>`).join('');

    // Restore selection if it still exists
    if (currentValue && services.find(s => s.name === currentValue)) {
        select.value = currentValue;
    }
}

// Update last update timestamp
function updateLastUpdate(timestamp) {
    const el = document.getElementById('last-update');
    if (timestamp) {
        const date = new Date(timestamp);
        el.textContent = `Last update: ${date.toLocaleTimeString()}`;
    }
}

// Get selected log level
function getLogLevel() {
    const select = document.getElementById('log-level-select');
    return select ? select.value : 'INFO';
}

// Format uptime from seconds to human readable
function formatUptime(seconds) {
    if (!seconds && seconds !== 0) return '';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) {
        return `${days}d ${hours}h`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m`;
    } else {
        return `${seconds}s`;
    }
}

// Sort services based on current sort settings
function sortServices(services) {
    return [...services].sort((a, b) => {
        let cmp = 0;

        switch (currentSort.field) {
            case 'name':
                cmp = a.name.localeCompare(b.name);
                break;
            case 'status':
                // Running first (true > false), then by name
                if (a.running !== b.running) {
                    cmp = a.running ? -1 : 1;
                } else {
                    cmp = a.name.localeCompare(b.name);
                }
                break;
            case 'uptime':
                // Highest uptime first, nulls last
                const aUp = a.uptime_seconds ?? -1;
                const bUp = b.uptime_seconds ?? -1;
                cmp = bUp - aUp;
                break;
        }

        return currentSort.direction === 'desc' ? -cmp : cmp;
    });
}

// Set sort field and toggle direction
function setSortBy(field) {
    if (currentSort.field === field) {
        // Toggle direction
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.field = field;
        currentSort.direction = 'asc';
    }

    // Update button states
    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.classList.remove('active', 'asc', 'desc');
        if (btn.dataset.sort === field) {
            btn.classList.add('active', currentSort.direction);
        }
    });

    // Re-render with cached services
    if (cachedServices.length) {
        updateServicesList(cachedServices);
    }
}

// Start a service
async function startService(name) {
    const btn = event.target;
    btn.disabled = true;
    btn.classList.add('loading');

    const logLevel = getLogLevel();
    const envOverrides = getEnvForService(name);
    envOverrides.LOG_LEVEL = logLevel;  // Log level from dropdown

    try {
        const response = await fetch(`${API_BASE}/api/services/${name}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ env: envOverrides })
        });
        const data = await response.json();

        if (!response.ok) {
            alert(`Failed to start ${name}: ${data.detail || 'Unknown error'}`);
        }

        // Refresh after a short delay to let the service start
        setTimeout(refreshStatus, 1000);
    } catch (error) {
        alert(`Failed to start ${name}: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.classList.remove('loading');
    }
}

// Stop a service
async function stopService(name) {
    const btn = event.target;
    btn.disabled = true;
    btn.classList.add('loading');

    try {
        const response = await fetch(`${API_BASE}/api/services/${name}/stop`, { method: 'POST' });
        const data = await response.json();

        if (!response.ok) {
            alert(`Failed to stop ${name}: ${data.detail || 'Unknown error'}`);
        }

        // Refresh after a short delay
        setTimeout(refreshStatus, 500);
    } catch (error) {
        alert(`Failed to stop ${name}: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.classList.remove('loading');
    }
}

// Start all services
async function startAll() {
    const logLevel = getLogLevel();
    const config = loadEnvConfig();
    const globalEnv = { ...config.global, LOG_LEVEL: logLevel };

    if (!confirm(`Start all services with log level ${logLevel}?`)) return;

    try {
        const response = await fetch(`${API_BASE}/api/services/start-all`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ env: globalEnv, service_env: config.services })
        });
        if (!response.ok) {
            const data = await response.json();
            alert(`Failed: ${data.detail || 'Unknown error'}`);
        }
        setTimeout(refreshStatus, 2000);
    } catch (error) {
        alert(`Failed: ${error.message}`);
    }
}

// Stop all services
async function stopAll() {
    if (!confirm('Stop all services?')) return;

    try {
        const response = await fetch(`${API_BASE}/api/services/stop-all`, { method: 'POST' });
        if (!response.ok) {
            const data = await response.json();
            alert(`Failed: ${data.detail || 'Unknown error'}`);
        }
        setTimeout(refreshStatus, 1000);
    } catch (error) {
        alert(`Failed: ${error.message}`);
    }
}

// View logs for a service
function viewLogs(name) {
    const select = document.getElementById('log-service-select');
    select.value = name;
    loadLogs();
}

// Load logs for selected service
async function loadLogs() {
    const select = document.getElementById('log-service-select');
    const name = select.value;
    const viewer = document.getElementById('log-viewer');

    if (!name) {
        viewer.textContent = 'Select a service to view logs...';
        return;
    }

    viewer.textContent = 'Loading logs...';

    try {
        const response = await fetch(`${API_BASE}/api/services/${name}/logs?lines=200`);
        if (!response.ok) {
            const data = await response.json();
            viewer.textContent = `Error: ${data.detail || 'Failed to load logs'}`;
            return;
        }

        const data = await response.json();
        viewer.textContent = data.logs || '(no logs)';

        // Scroll to bottom
        viewer.scrollTop = viewer.scrollHeight;
    } catch (error) {
        viewer.textContent = `Error: ${error.message}`;
    }
}

// Clear log viewer
function clearLogs() {
    const viewer = document.getElementById('log-viewer');
    viewer.textContent = 'Select a service to view logs...';
    document.getElementById('log-service-select').value = '';
}

// ============================================================
// ENV Config Modal functions
// ============================================================
let currentServiceConfig = null;

function openEnvConfig() {
    const modal = document.getElementById('env-modal');
    const config = loadEnvConfig();

    // Populate global settings
    const logLevel = config.global.LOG_LEVEL || '';
    document.getElementById('env-global-log-level').value = logLevel;

    // Custom global overrides (excluding LOG_LEVEL)
    const customGlobal = { ...config.global };
    delete customGlobal.LOG_LEVEL;
    document.getElementById('env-global-custom').value = envToText(customGlobal);

    // Populate service select with override indicators
    const select = document.getElementById('env-service-select');
    select.innerHTML = '<option value="">Select service...</option>' +
        cachedServices.map(s => {
            const count = getOverrideCount(s.name);
            const marker = count > 0 ? ` ● (${count})` : '';
            return `<option value="${s.name}">${s.name}${marker}</option>`;
        }).join('');

    // Reset service tab
    document.getElementById('env-service-desc').textContent = '';
    document.getElementById('env-service-vars').innerHTML =
        '<div class="env-placeholder">Select a service to view its environment variables</div>';
    currentServiceConfig = null;

    // Show global tab by default
    switchEnvTab('global');

    modal.classList.remove('hidden');
}

function closeEnvConfig() {
    document.getElementById('env-modal').classList.add('hidden');
}

function switchEnvTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.env-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Show/hide tab content
    document.getElementById('env-tab-global').classList.toggle('hidden', tab !== 'global');
    document.getElementById('env-tab-service').classList.toggle('hidden', tab !== 'service');
}

async function loadServiceConfig() {
    const select = document.getElementById('env-service-select');
    const serviceName = select.value;
    const descEl = document.getElementById('env-service-desc');
    const container = document.getElementById('env-service-vars');
    const loadingEl = document.getElementById('env-service-loading');

    if (!serviceName) {
        descEl.textContent = '';
        container.innerHTML = '<div class="env-placeholder">Select a service to view its environment variables</div>';
        currentServiceConfig = null;
        return;
    }

    // Show loading
    loadingEl.classList.remove('hidden');
    container.innerHTML = '';

    try {
        const response = await fetch(`${API_BASE}/api/services/${serviceName}/config`);
        if (!response.ok) throw new Error('Failed to fetch config');

        currentServiceConfig = await response.json();
        descEl.textContent = currentServiceConfig.meta?.description || '';

        renderEnvVars(serviceName, currentServiceConfig.categorized);
    } catch (error) {
        console.error('Failed to load service config:', error);
        container.innerHTML = `<div class="env-placeholder">Error: ${error.message}</div>`;
    } finally {
        loadingEl.classList.add('hidden');
    }
}

function renderEnvVars(serviceName, categorized) {
    const container = document.getElementById('env-service-vars');
    const config = loadEnvConfig();
    const overrides = config.services[serviceName] || {};

    const categoryLabels = {
        boolean: 'Feature Flags (Boolean)',
        number: 'Numeric Settings',
        string: 'Configuration Values'
    };

    let html = '';

    for (const [category, vars] of Object.entries(categorized)) {
        if (vars.length === 0) continue;

        html += `<div class="env-category">
            <div class="env-category-header">${categoryLabels[category]} (${vars.length})</div>`;

        for (const v of vars) {
            const hasOverride = v.key in overrides;
            const overrideValue = overrides[v.key];
            const overrideDot = hasOverride ? '<span class="override-dot"></span>' : '';

            if (category === 'boolean') {
                const defaultBool = String(v.default).toLowerCase() === 'true';
                const currentBool = hasOverride
                    ? String(overrideValue).toLowerCase() === 'true'
                    : defaultBool;

                html += `
                    <div class="env-var-row">
                        <span class="env-var-key">${v.key}</span>
                        <span class="env-var-default" data-key="${v.key}">${overrideDot}Default: ${v.default}</span>
                        <div class="env-var-override">
                            <label class="env-toggle ${hasOverride ? 'overridden' : ''}" title="${hasOverride ? 'Overridden' : 'Using default'}">
                                <input type="checkbox"
                                    data-key="${v.key}"
                                    data-type="boolean"
                                    data-default="${v.default}"
                                    ${currentBool ? 'checked' : ''}
                                    onchange="markEnvOverride(this)">
                                <span class="env-toggle-slider"></span>
                            </label>
                        </div>
                    </div>`;
            } else {
                html += `
                    <div class="env-var-row">
                        <span class="env-var-key">${v.key}</span>
                        <span class="env-var-default" data-key="${v.key}" title="${v.default}">${overrideDot}Default: ${truncateValue(v.default)}</span>
                        <div class="env-var-override">
                            <input type="text"
                                class="env-override-input ${hasOverride ? 'overridden' : ''}"
                                data-key="${v.key}"
                                data-type="${category}"
                                data-default="${v.default}"
                                value="${hasOverride ? overrideValue : ''}"
                                placeholder="${truncateValue(v.default, 15)}"
                                onchange="markEnvOverride(this)"
                                oninput="markEnvOverride(this)">
                        </div>
                    </div>`;
            }
        }

        html += '</div>';
    }

    container.innerHTML = html || '<div class="env-placeholder">No environment variables defined</div>';
}

function truncateValue(value, maxLen = 30) {
    const str = String(value);
    return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
}

function markEnvOverride(el) {
    const isBoolean = el.dataset.type === 'boolean';
    const defaultVal = el.dataset.default;
    const key = el.dataset.key;

    let isOverridden;
    if (isBoolean) {
        const currentVal = el.checked ? 'true' : 'false';
        isOverridden = currentVal !== defaultVal.toLowerCase();
        el.closest('.env-toggle').classList.toggle('overridden', isOverridden);
    } else {
        const currentVal = el.value.trim();
        isOverridden = currentVal !== '' && currentVal !== defaultVal;
        el.classList.toggle('overridden', isOverridden);
    }

    // Update the red dot before "Default:" label
    const defaultLabel = document.querySelector(`.env-var-default[data-key="${key}"]`);
    if (defaultLabel) {
        const existingDot = defaultLabel.querySelector('.override-dot');
        if (isOverridden && !existingDot) {
            defaultLabel.insertAdjacentHTML('afterbegin', '<span class="override-dot"></span>');
        } else if (!isOverridden && existingDot) {
            existingDot.remove();
        }
    }
}

function saveEnvConfig() {
    const config = loadEnvConfig();

    // Save global settings
    const logLevel = document.getElementById('env-global-log-level').value;
    const customGlobal = parseEnvText(document.getElementById('env-global-custom').value);

    config.global = customGlobal;
    if (logLevel) {
        config.global.LOG_LEVEL = logLevel;
    }

    // Save service-specific overrides if a service is selected
    const serviceName = document.getElementById('env-service-select').value;
    if (serviceName && currentServiceConfig) {
        const overrides = collectServiceOverrides();
        if (Object.keys(overrides).length > 0) {
            config.services[serviceName] = overrides;
        } else {
            delete config.services[serviceName];
        }
    }

    saveEnvConfigToStorage(config);
    closeEnvConfig();

    // Refresh service list to update override indicators
    if (cachedServices.length) {
        updateServicesList(cachedServices);
    }
}

async function saveAndRestartService() {
    const serviceName = document.getElementById('env-service-select').value;
    if (!serviceName) {
        alert('Select a service first');
        return;
    }

    // Save the config first
    const config = loadEnvConfig();

    // Save global settings
    const logLevel = document.getElementById('env-global-log-level').value;
    const customGlobal = parseEnvText(document.getElementById('env-global-custom').value);
    config.global = customGlobal;
    if (logLevel) {
        config.global.LOG_LEVEL = logLevel;
    }

    // Save service-specific overrides
    if (currentServiceConfig) {
        const overrides = collectServiceOverrides();
        if (Object.keys(overrides).length > 0) {
            config.services[serviceName] = overrides;
        } else {
            delete config.services[serviceName];
        }
    }
    saveEnvConfigToStorage(config);

    // Close modal and show status
    closeEnvConfig();

    // Update UI
    if (cachedServices.length) {
        updateServicesList(cachedServices);
    }

    // Stop the service
    try {
        const stopResp = await fetch(`${API_BASE}/api/services/${serviceName}/stop`, { method: 'POST' });
        if (!stopResp.ok) {
            const data = await stopResp.json();
            alert(`Failed to stop ${serviceName}: ${data.detail || 'Unknown error'}`);
            return;
        }
    } catch (error) {
        alert(`Failed to stop ${serviceName}: ${error.message}`);
        return;
    }

    // Wait a moment for clean shutdown
    await new Promise(resolve => setTimeout(resolve, 1500));

    // Start with new ENV
    const envOverrides = getEnvForService(serviceName);
    try {
        const startResp = await fetch(`${API_BASE}/api/services/${serviceName}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ env: envOverrides })
        });
        const data = await startResp.json();
        if (!startResp.ok) {
            alert(`Failed to start ${serviceName}: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        alert(`Failed to start ${serviceName}: ${error.message}`);
    }

    // Refresh status
    setTimeout(refreshStatus, 1000);
}

function collectServiceOverrides() {
    const overrides = {};
    const container = document.getElementById('env-service-vars');

    // Collect boolean overrides
    container.querySelectorAll('input[data-type="boolean"]').forEach(input => {
        const currentVal = input.checked ? 'true' : 'false';
        const defaultVal = input.dataset.default.toLowerCase();
        if (currentVal !== defaultVal) {
            overrides[input.dataset.key] = currentVal;
        }
    });

    // Collect text overrides
    container.querySelectorAll('input[data-type="number"], input[data-type="string"]').forEach(input => {
        const val = input.value.trim();
        if (val && val !== input.dataset.default) {
            overrides[input.dataset.key] = val;
        }
    });

    return overrides;
}

function clearServiceOverrides() {
    const serviceName = document.getElementById('env-service-select').value;
    if (!serviceName) {
        alert('Select a service first');
        return;
    }

    if (!confirm(`Clear all overrides for ${serviceName}?`)) return;

    const config = loadEnvConfig();
    delete config.services[serviceName];
    saveEnvConfigToStorage(config);

    // Re-render env vars
    if (currentServiceConfig) {
        renderEnvVars(serviceName, currentServiceConfig.categorized);
    }

    // Update dropdown to remove indicator
    const select = document.getElementById('env-service-select');
    const option = select.querySelector(`option[value="${serviceName}"]`);
    if (option) {
        option.textContent = serviceName;
    }

    // Refresh service list to update override indicators
    if (cachedServices.length) {
        updateServicesList(cachedServices);
    }
}

// ============================================================
// Analytics / Instrumentation
// ============================================================
let cachedAnalytics = {};

async function refreshAnalytics() {
    const container = document.getElementById('analytics-container');
    container.innerHTML = '<div class="analytics-placeholder">Loading analytics...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/analytics`);
        if (!response.ok) throw new Error('Failed to fetch analytics');
        const data = await response.json();
        cachedAnalytics = data.analytics || data;  // Handle both {analytics: {...}} and direct object

        // Check for analytics errors and update alerts
        checkAnalyticsForAlerts(cachedAnalytics);

        // Update analytics source dropdown
        updateAnalyticsSourceSelect();

        // Display selected or first source
        displayAnalytics();
    } catch (error) {
        console.error('Failed to refresh analytics:', error);
        container.innerHTML = `<div class="analytics-placeholder error">Error: ${error.message}</div>`;
    }
}

function updateAnalyticsSourceSelect() {
    const select = document.getElementById('analytics-source-select');
    const currentValue = select.value;

    const sources = Object.keys(cachedAnalytics).sort();
    select.innerHTML = '<option value="">All sources</option>' +
        sources.map(s => `<option value="${s}">${s}</option>`).join('');

    // Restore selection if it still exists
    if (currentValue && sources.includes(currentValue)) {
        select.value = currentValue;
    }
}

function displayAnalytics() {
    const container = document.getElementById('analytics-container');
    const selectedSource = document.getElementById('analytics-source-select').value;

    if (Object.keys(cachedAnalytics).length === 0) {
        container.innerHTML = '<div class="analytics-placeholder">No analytics data. Click Refresh to load.</div>';
        return;
    }

    // Filter sources based on selection
    const sources = selectedSource
        ? { [selectedSource]: cachedAnalytics[selectedSource] }
        : cachedAnalytics;

    const html = Object.entries(sources).map(([name, info]) => {
        if (info.error) {
            return `
                <div class="analytics-card error">
                    <div class="analytics-card-header">
                        <span class="analytics-source-name">${name}</span>
                        <span class="analytics-source-type">${info.source}</span>
                    </div>
                    <div class="analytics-card-body">
                        <div class="analytics-error">${info.error}</div>
                    </div>
                </div>
            `;
        }

        let data = info.data || {};

        // Handle nested structures (e.g., journal returns {success, data: {summary: {...}}})
        if (data.data && typeof data.data === 'object') {
            data = data.data.summary || data.data;
        }

        const metrics = Object.entries(data);

        return `
            <div class="analytics-card">
                <div class="analytics-card-header">
                    <span class="analytics-source-name">${name}</span>
                    <span class="analytics-source-type">${info.source}${info.bus ? ` (${info.bus})` : ''}</span>
                </div>
                <div class="analytics-card-body">
                    ${metrics.length === 0
                        ? '<div class="analytics-empty">No metrics</div>'
                        : `<div class="analytics-metrics">
                            ${metrics.map(([key, value]) => `
                                <div class="analytics-metric">
                                    <span class="metric-key">${formatMetricKey(key)}</span>
                                    <span class="metric-value">${formatMetricValue(value)}</span>
                                </div>
                            `).join('')}
                        </div>`
                    }
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html || '<div class="analytics-placeholder">No analytics data available.</div>';
}

function formatMetricKey(key) {
    // Convert snake_case or camelCase to Title Case with spaces
    return key
        .replace(/_/g, ' ')
        .replace(/([a-z])([A-Z])/g, '$1 $2')
        .replace(/\b\w/g, c => c.toUpperCase());
}

function formatMetricValue(value) {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'number') {
        // Format large numbers with commas, small decimals nicely
        if (Number.isInteger(value)) {
            return value.toLocaleString();
        } else {
            return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
        }
    }
    if (typeof value === 'object') {
        return JSON.stringify(value);
    }
    return String(value);
}

// ============================================================
// Data Diagnostics
// ============================================================

async function runDiagnostics() {
    const container = document.getElementById('diagnostics-container');
    container.innerHTML = '<div class="diagnostics-placeholder">Running diagnostics...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/diagnostics`);
        if (!response.ok) throw new Error('Failed to run diagnostics');
        const data = await response.json();
        displayDiagnostics(data);
    } catch (error) {
        console.error('Diagnostics error:', error);
        container.innerHTML = `<div class="diagnostics-placeholder error">Error: ${error.message}</div>`;
    }
}

function displayDiagnostics(data) {
    const container = document.getElementById('diagnostics-container');

    // Redis connection status
    const redisStatus = data.redis?.connected
        ? '<span class="status-ok">Connected</span>'
        : `<span class="status-error">Disconnected: ${data.redis?.error || 'Unknown'}</span>`;

    // Build data availability table
    const symbols = Object.keys(data.data || {}).filter(k => k !== 'global');
    const dataTypes = ['spot', 'heatmap', 'gex', 'trade_selector'];

    let tableRows = symbols.map(symbol => {
        const symbolData = data.data[symbol];
        const cells = dataTypes.map(type => {
            const d = symbolData[type];
            if (!d) return '<td><span class="status-unknown">-</span></td>';
            if (d.exists) {
                let detail = '';
                if (type === 'spot' && d.value) detail = `$${d.value.toFixed(2)}`;
                else if (type === 'heatmap' && d.tileCount) detail = `${d.tileCount} tiles`;
                else if (type === 'trade_selector') {
                    if (d.error) detail = `<span class="status-warn">${d.error}</span>`;
                    else detail = d.vix_regime || '';
                }
                const age = d.age_sec !== null ? `(${formatAge(d.age_sec)})` : '';
                return `<td><span class="status-ok">✓</span> <span class="status-detail">${detail} ${age}</span></td>`;
            } else {
                return `<td><span class="status-error">✗</span></td>`;
            }
        }).join('');
        return `<tr><td class="symbol-cell">${symbol}</td>${cells}</tr>`;
    }).join('');

    // Global data
    const global = data.data?.global || {};
    let globalHtml = '';
    if (global.vix) {
        globalHtml += `<span class="global-item ${global.vix.exists ? 'ok' : 'error'}">
            VIX: ${global.vix.exists ? global.vix.value + ' (' + formatAge(global.vix.age_sec) + ')' : 'Missing'}
        </span>`;
    }
    if (global.market_mode) {
        globalHtml += `<span class="global-item ${global.market_mode.exists ? 'ok' : 'error'}">
            Mode: ${global.market_mode.exists ? global.market_mode.mode : 'Missing'}
        </span>`;
    }

    container.innerHTML = `
        <div class="diag-section">
            <div class="diag-header">
                <span class="diag-label">Redis (market-redis:6380):</span>
                ${redisStatus}
            </div>
        </div>

        <div class="diag-section">
            <h4>Data Availability</h4>
            <table class="diag-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Spot</th>
                        <th>Heatmap</th>
                        <th>GEX</th>
                        <th>Trade Selector</th>
                    </tr>
                </thead>
                <tbody>
                    ${tableRows}
                </tbody>
            </table>
            ${globalHtml ? `<div class="global-data">${globalHtml}</div>` : ''}
        </div>
    `;
}

function formatAge(seconds) {
    if (seconds === null || seconds === undefined) return '?';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
}

// Redis Key Explorer
function setRedisPrefix(prefix) {
    const patternInput = document.getElementById('redis-pattern');
    if (prefix === '') {
        patternInput.value = '*';
    } else {
        patternInput.value = prefix + '*';
    }
    // Auto-search when changing prefix
    searchRedisKeys();
}

async function searchRedisKeys() {
    const pattern = document.getElementById('redis-pattern').value || '*';
    const content = document.getElementById('redis-explorer-content');
    const keysList = document.getElementById('redis-keys-list');

    content.classList.remove('hidden');
    keysList.innerHTML = '<div class="loading">Searching...</div>';

    try {
        const response = await fetch(`${API_BASE}/api/diagnostics/redis?pattern=${encodeURIComponent(pattern)}&limit=100`);
        if (!response.ok) throw new Error('Failed to search Redis');
        const data = await response.json();

        if (data.error) {
            keysList.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        if (data.keys.length === 0) {
            keysList.innerHTML = '<div class="empty">No keys found</div>';
            return;
        }

        keysList.innerHTML = `
            <div class="keys-header">${data.returned} of ${data.total} keys</div>
            ${data.keys.map(k => `
                <div class="redis-key-item" onclick="loadRedisKey('${k.key.replace(/'/g, "\\'")}')">
                    <span class="key-name">${k.key}</span>
                    <span class="key-meta">${k.type} | ${k.size || 0}${k.age_sec !== undefined ? ' | ' + formatAge(k.age_sec) : ''}</span>
                </div>
            `).join('')}
        `;
    } catch (error) {
        console.error('Redis search error:', error);
        keysList.innerHTML = `<div class="error">${error.message}</div>`;
    }
}

async function loadRedisKey(key) {
    const panel = document.getElementById('redis-value-panel');
    const keySpan = document.getElementById('redis-value-key');
    const content = document.getElementById('redis-value-content');

    panel.classList.remove('hidden');
    keySpan.textContent = key;
    content.textContent = 'Loading...';

    try {
        const response = await fetch(`${API_BASE}/api/diagnostics/redis/${encodeURIComponent(key)}`);
        if (!response.ok) throw new Error('Failed to fetch key');
        const data = await response.json();

        if (data.error) {
            content.textContent = `Error: ${data.error}`;
            return;
        }

        content.textContent = typeof data.value === 'object'
            ? JSON.stringify(data.value, null, 2)
            : String(data.value);
    } catch (error) {
        content.textContent = `Error: ${error.message}`;
    }
}

function closeRedisValue() {
    document.getElementById('redis-value-panel').classList.add('hidden');
}

// ============================================================
// ML Lab
// ============================================================

let mlLabData = {
    circuitBreakers: null,
    breakerCheck: null,
    champion: null,
    experiments: [],
    decisions: [],
    dailyPerformance: []
};

async function refreshMLLab() {
    try {
        const safeFetch = async (url, options = {}) => {
            try {
                const res = await fetch(url, options);
                if (!res.ok) return null;
                const json = await res.json();
                return json.success ? json.data : json;
            } catch {
                return null;
            }
        };

        const [cb, champ, exps, decs, perf] = await Promise.all([
            safeFetch(`${API_BASE}/api/ml/circuit-breakers`),
            safeFetch(`${API_BASE}/api/ml/models/champion`),
            safeFetch(`${API_BASE}/api/ml/experiments`),
            safeFetch(`${API_BASE}/api/ml/decisions?limit=10`),
            safeFetch(`${API_BASE}/api/ml/daily-performance?limit=7`),
        ]);

        if (cb) mlLabData.circuitBreakers = { data: cb };
        if (champ) mlLabData.champion = champ?.data || champ;
        mlLabData.experiments = Array.isArray(exps) ? exps : (exps?.data || []);
        mlLabData.decisions = Array.isArray(decs) ? decs : (decs?.data || []);
        mlLabData.dailyPerformance = Array.isArray(perf) ? perf : (perf?.data || []);

        renderMLLab();
    } catch (err) {
        console.error('ML Lab refresh error:', err);
    }
}

function renderMLLab() {
    renderMLStatus();
    renderMLBreakers();
    renderMLChampion();
    renderMLExperiments();
    renderMLDecisions();
    renderMLPerformance();
}

function renderMLStatus() {
    const statusEl = document.getElementById('ml-system-status');
    const toggleBtn = document.getElementById('ml-toggle-btn');
    const check = mlLabData.breakerCheck;
    const cb = mlLabData.circuitBreakers;

    if (!cb) {
        statusEl.innerHTML = '<span class="status-dot unknown"></span><span class="status-text">Unable to connect to ML service</span>';
        toggleBtn.textContent = 'ML: Unknown';
        toggleBtn.className = 'btn btn-sm btn-secondary';
        return;
    }

    // Check if any breakers triggered
    const data = cb.data || cb;
    const breakers = data.breakers || {};
    const triggeredBreakers = Object.entries(breakers).filter(([k, v]) => v.triggered);
    const hasTriggered = triggeredBreakers.length > 0;

    const statusClass = !hasTriggered ? 'ok' : 'warning';
    const statusText = !hasTriggered ? 'All Systems Go' : 'Breakers Triggered';

    statusEl.innerHTML = `<span class="status-dot ${statusClass}"></span><span class="status-text">${statusText}</span>`;

    if (hasTriggered) {
        statusEl.innerHTML += `<span class="triggered-count">${triggeredBreakers.length} breaker(s) triggered</span>`;
    }

    const mlEnabled = data.mlEnabled ?? true;
    toggleBtn.textContent = mlEnabled ? 'ML: Enabled' : 'ML: Disabled';
    toggleBtn.className = mlEnabled ? 'btn btn-sm btn-success' : 'btn btn-sm btn-danger';
}

function renderMLBreakers() {
    const container = document.getElementById('ml-breakers');
    const cb = mlLabData.circuitBreakers;

    if (!cb) {
        container.innerHTML = '<div class="empty">No data</div>';
        return;
    }

    const data = cb.data || cb;
    const breakers = data.breakers || {};

    const formatCurrency = (v) => {
        const sign = v >= 0 ? '+' : '-';
        return `${sign}$${Math.abs(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    };

    const formatPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—';

    const dailyPnl = data.dailyPnl ?? 0;
    const dailyLimit = breakers.dailyLossLimit?.threshold ?? 5000;
    const drawdownLimit = breakers.maxDrawdown?.threshold ?? 0.2;
    const orderRateLimit = breakers.orderRate?.threshold ?? 10;

    container.innerHTML = `
        <div class="breaker-row">
            <span class="breaker-label">Daily P&L</span>
            <span class="breaker-value ${dailyPnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(dailyPnl)}</span>
            <span class="breaker-limit">Limit: -$${dailyLimit.toLocaleString()}</span>
        </div>
        <div class="breaker-row">
            <span class="breaker-label">Loss Limit</span>
            <span class="breaker-value">${breakers.dailyLossLimit?.triggered ? 'TRIGGERED' : 'OK'}</span>
            <span class="breaker-limit">-$${dailyLimit}</span>
        </div>
        <div class="breaker-row">
            <span class="breaker-label">Drawdown</span>
            <span class="breaker-value">${breakers.maxDrawdown?.triggered ? 'TRIGGERED' : 'OK'}</span>
            <span class="breaker-limit">Max: ${formatPct(drawdownLimit)}</span>
        </div>
        <div class="breaker-row">
            <span class="breaker-label">Order Rate</span>
            <span class="breaker-value">${breakers.orderRate?.triggered ? 'TRIGGERED' : 'OK'}</span>
            <span class="breaker-limit">Max: ${orderRateLimit}/s</span>
        </div>
    `;
}

function renderMLChampion() {
    const container = document.getElementById('ml-champion');
    const champ = mlLabData.champion;

    if (!champ || (typeof champ === 'object' && Object.keys(champ).length === 0)) {
        container.innerHTML = '<div class="empty">No champion model deployed (rules-only mode)</div>';
        return;
    }

    // API uses camelCase
    const valAuc = champ.metrics?.valAuc ?? champ.val_auc;
    const trainSamples = champ.metrics?.trainSamples ?? champ.train_samples;
    const top10 = champ.topKUtility?.top10AvgPnl ?? champ.top_10_avg_pnl;

    container.innerHTML = `
        <div class="champion-info">
            <div class="champion-name">${champ.modelName || champ.model_name || 'Unknown'} <span class="version">v${champ.modelVersion || champ.model_version || '?'}</span></div>
            <div class="champion-type">${champ.modelType || champ.model_type || '—'} | ${champ.featureSetVersion || champ.feature_set_version || '—'}</div>
        </div>
        <div class="champion-stats">
            <div class="stat"><span class="label">Val AUC</span><span class="value">${valAuc ? parseFloat(valAuc).toFixed(3) : '—'}</span></div>
            <div class="stat"><span class="label">Samples</span><span class="value">${trainSamples?.toLocaleString() || '—'}</span></div>
            <div class="stat"><span class="label">Top-10</span><span class="value">${top10 ? '$' + parseFloat(top10).toFixed(0) : '—'}</span></div>
        </div>
    `;
}

function renderMLExperiments() {
    const container = document.getElementById('ml-experiments');
    const exps = mlLabData.experiments.filter(e => e.status === 'running');

    if (exps.length === 0) {
        container.innerHTML = '<div class="empty">No active experiments</div>';
        return;
    }

    container.innerHTML = exps.map(exp => `
        <div class="experiment-item">
            <div class="exp-name">${exp.experiment_name}</div>
            <div class="exp-stats">
                <span>Champion: ${exp.champion_samples} samples</span>
                <span>Challenger: ${exp.challenger_samples} samples</span>
            </div>
            ${exp.p_value ? `<div class="exp-pvalue">p = ${exp.p_value.toFixed(4)}</div>` : ''}
        </div>
    `).join('');
}

function renderMLDecisions() {
    const container = document.getElementById('ml-decisions');
    const decs = mlLabData.decisions;

    if (!decs || decs.length === 0) {
        container.innerHTML = '<div class="empty">No recent decisions</div>';
        return;
    }

    container.innerHTML = `
        <table class="ml-table">
            <thead>
                <tr><th>Time</th><th>Original</th><th>ML</th><th>Final</th><th>Action</th></tr>
            </thead>
            <tbody>
                ${decs.slice(0, 10).map(d => `
                    <tr>
                        <td>${d.decisionTime ? new Date(d.decisionTime).toLocaleTimeString() : '—'}</td>
                        <td>${d.originalScore != null ? Number(d.originalScore).toFixed(1) : '—'}</td>
                        <td class="ml-score">${d.mlScore != null ? Number(d.mlScore).toFixed(1) : '—'}</td>
                        <td>${d.finalScore != null ? Number(d.finalScore).toFixed(1) : '—'}</td>
                        <td><span class="action-badge ${d.actionTaken || 'unknown'}">${d.actionTaken || '—'}</span></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderMLPerformance() {
    const container = document.getElementById('ml-performance');
    const perf = mlLabData.dailyPerformance;

    if (!perf || perf.length === 0) {
        container.innerHTML = '<div class="empty">No performance data</div>';
        return;
    }

    const formatCurrency = (v) => {
        const sign = v >= 0 ? '+' : '-';
        return `${sign}$${Math.abs(v).toFixed(2)}`;
    };

    container.innerHTML = `
        <table class="ml-table">
            <thead>
                <tr><th>Date</th><th>Net P&L</th><th>Trades</th><th>Win Rate</th><th>Drawdown</th></tr>
            </thead>
            <tbody>
                ${perf.map(d => `
                    <tr>
                        <td>${d.date}</td>
                        <td class="${d.net_pnl >= 0 ? 'positive' : 'negative'}">${formatCurrency(d.net_pnl)}</td>
                        <td>${d.trade_count}</td>
                        <td>${d.trade_count > 0 ? ((d.win_count / d.trade_count) * 100).toFixed(1) + '%' : '—'}</td>
                        <td>${d.drawdown_pct ? (d.drawdown_pct * 100).toFixed(1) + '%' : '—'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function toggleML() {
    const cb = mlLabData.circuitBreakers;
    if (!cb) return;

    const data = cb.data || cb;
    const endpoint = data.mlEnabled
        ? `${API_BASE}/api/ml/circuit-breakers/disable-ml`
        : `${API_BASE}/api/ml/circuit-breakers/enable-ml`;

    try {
        await fetch(endpoint, { method: 'POST' });
        await refreshMLLab();
    } catch (err) {
        console.error('Toggle ML error:', err);
    }
}

// ============================================================
// Deployment
// ============================================================

let deployStatus = null;

async function refreshDeployStatus() {
    try {
        const [status, changelog] = await Promise.all([
            fetch(`${API_BASE}/api/deploy/status`).then(r => r.json()),
            fetch(`${API_BASE}/api/deploy/changelog?count=10`).then(r => r.json()),
        ]);

        deployStatus = status;
        renderDeployStatus(status);
        renderDeployChangelog(changelog);
    } catch (err) {
        console.error('Deploy status error:', err);
        const statusEl = document.getElementById('deploy-status');
        if (statusEl) {
            statusEl.innerHTML = '<span class="status-dot error"></span><span class="status-text">Error loading status</span>';
        }
    }
}

function renderDeployStatus(status) {
    const statusEl = document.getElementById('deploy-status');
    const commitEl = document.getElementById('deploy-commit');
    const gitStatusEl = document.getElementById('deploy-git-status');

    if (!statusEl) return;

    if (status.error) {
        statusEl.innerHTML = `<span class="status-dot error"></span><span class="status-text">Error: ${status.error}</span>`;
        return;
    }

    // Status indicator
    let statusClass = 'ok';
    let statusText = 'Up to date';

    if (status.behind_remote) {
        statusClass = 'warning';
        statusText = `${status.commits_behind} commit(s) behind`;
    }
    if (status.has_changes) {
        statusClass = 'warning';
        statusText = 'Local changes detected';
    }

    statusEl.innerHTML = `<span class="status-dot ${statusClass}"></span><span class="status-text">${statusText}</span>`;

    // Current commit
    if (commitEl) {
        commitEl.innerHTML = `
            <span class="commit-info">
                <strong>${status.current_branch || 'unknown'}</strong> @
                <code>${status.current_commit || 'unknown'}</code>
            </span>
        `;
    }

    // Git status details
    if (gitStatusEl) {
        gitStatusEl.innerHTML = `
            <div class="git-info">
                <div class="git-row"><span class="git-label">Branch:</span> <span>${status.current_branch || '—'}</span></div>
                <div class="git-row"><span class="git-label">Commit:</span> <code>${status.current_commit || '—'}</code></div>
                <div class="git-row"><span class="git-label">Local changes:</span> <span class="${status.has_changes ? 'warning' : ''}">${status.has_changes ? 'Yes' : 'None'}</span></div>
                <div class="git-row"><span class="git-label">Behind remote:</span> <span class="${status.behind_remote ? 'warning' : ''}">${status.behind_remote ? status.commits_behind + ' commits' : 'Up to date'}</span></div>
            </div>
        `;
    }
}

function renderDeployChangelog(data) {
    const container = document.getElementById('deploy-changelog');
    if (!container) return;

    if (!data.success || !data.commits || data.commits.length === 0) {
        container.innerHTML = '<div class="empty">No commits found</div>';
        return;
    }

    container.innerHTML = `
        <div class="changelog-list">
            ${data.commits.map(c => `
                <div class="changelog-item">
                    <code class="commit-hash">${c.hash}</code>
                    <span class="commit-message">${escapeHtml(c.message)}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showDeployLog(message, append = false) {
    const container = document.getElementById('deploy-log-container');
    const log = document.getElementById('deploy-log');

    if (!container || !log) return;

    container.classList.remove('hidden');

    if (append) {
        log.textContent += message + '\n';
    } else {
        log.textContent = message + '\n';
    }

    // Scroll to bottom
    log.scrollTop = log.scrollHeight;
}

async function deployPull() {
    const btn = document.getElementById('deploy-pull-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Pulling...';
    }

    showDeployLog('Starting git pull...');

    try {
        const response = await fetch(`${API_BASE}/api/deploy/pull`, { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            if (result.updated) {
                showDeployLog(`Updated: ${result.before_commit} → ${result.after_commit}`, true);
                if (result.changelog && result.changelog.length > 0) {
                    showDeployLog('\nChanges:', true);
                    result.changelog.forEach(c => showDeployLog('  ' + c, true));
                }
            } else {
                showDeployLog('Already up to date.', true);
            }
        } else {
            showDeployLog('Pull failed: ' + (result.error || 'Unknown error'), true);
        }

        await refreshDeployStatus();
    } catch (err) {
        showDeployLog('Error: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Pull Latest';
        }
    }
}

async function deployRestartAll() {
    const btn = document.getElementById('deploy-restart-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Restarting...';
    }

    showDeployLog('Restarting all services...');

    try {
        const response = await fetch(`${API_BASE}/api/deploy/restart-all`, { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showDeployLog('Services restarted successfully.', true);
            showDeployLog('\nStopped: ' + JSON.stringify(result.stopped), true);
            showDeployLog('Started: ' + JSON.stringify(result.started), true);
        } else {
            showDeployLog('Restart failed: ' + (result.error || 'Unknown error'), true);
        }

        // Refresh service status
        await fetchStatus();
    } catch (err) {
        showDeployLog('Error: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Restart All Services';
        }
    }
}

async function deployFull() {
    const btn = document.getElementById('deploy-full-btn');
    const syncNginxCheckbox = document.getElementById('deploy-sync-nginx');
    const syncNginx = syncNginxCheckbox ? syncNginxCheckbox.checked : false;

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Deploying...';
    }

    showDeployLog('Starting full deployment...');
    showDeployLog('Options: restart=true, nginx=' + syncNginx);

    try {
        const response = await fetch(`${API_BASE}/api/deploy/full`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                restart_services: true,
                sync_nginx: syncNginx,
                nginx_host: 'MiniThree',
            }),
        });
        const result = await response.json();

        // Pull result
        if (result.pull) {
            if (result.pull.updated) {
                showDeployLog(`\n✓ Pull: ${result.pull.before_commit} → ${result.pull.after_commit}`, true);
            } else {
                showDeployLog('\n✓ Pull: Already up to date', true);
            }
        }

        // Restart result
        if (result.restart) {
            showDeployLog('✓ Services restarted', true);
        }

        // Nginx result
        if (result.nginx) {
            if (result.nginx.success) {
                showDeployLog('✓ Nginx synced and reloaded', true);
            } else {
                showDeployLog('✗ Nginx sync failed: ' + result.nginx.error, true);
            }
        }

        showDeployLog('\nDeployment complete!', true);

        await Promise.all([
            refreshDeployStatus(),
            fetchStatus(),
        ]);
    } catch (err) {
        showDeployLog('Error: ' + err.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Full Deploy';
        }
    }
}

// Initialize deploy status after page load
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(refreshDeployStatus, 1000);
    // Start health monitoring (delay to allow first collection)
    setTimeout(refreshHealth, 6000);
    // Auto-refresh health every 30s
    setInterval(refreshHealth, 30000);
});

// ============================================================
// System Health
// ============================================================

let healthData = null;
let healthHistory = [];
let healthEvents = [];
let healthEventFilter = 'all';

async function refreshHealth() {
    try {
        const [healthResp, historyResp, eventsResp] = await Promise.all([
            fetch(`${API_BASE}/api/health`).then(r => r.ok ? r.json() : null),
            fetch(`${API_BASE}/api/health/history?count=240`).then(r => r.ok ? r.json() : null),
            fetch(`${API_BASE}/api/health/events?count=50`).then(r => r.ok ? r.json() : null),
        ]);

        if (!healthResp || healthResp.status === 'initializing') {
            return; // Collector still starting up
        }

        healthData = healthResp;
        healthHistory = (historyResp && historyResp.history) || [];
        healthEvents = (eventsResp && eventsResp.events) || [];

        renderHealthScore(healthResp);
        renderRedisGauges(healthResp.redis || {});
        renderHeartbeatGrid(healthResp.heartbeats || {});
        renderHealthTimeline(healthHistory);
        renderHealthEvents(healthEvents);
        refreshHealerStatus();
    } catch (err) {
        console.error('Health refresh error:', err);
    }
}

function renderHealthScore(data) {
    const circle = document.getElementById('health-score-circle');
    const valueEl = document.getElementById('health-score-value');
    const labelEl = document.getElementById('health-score-label');
    const tsEl = document.getElementById('health-score-ts');
    const alertsEl = document.getElementById('health-score-alerts');

    if (!data || data.score === undefined) {
        valueEl.textContent = '--';
        labelEl.textContent = 'Initializing...';
        return;
    }

    const score = data.score;
    const pct = Math.round(score * 100);
    const label = data.score_label || 'unknown';

    valueEl.textContent = pct;
    labelEl.textContent = label;

    // Update circle class
    circle.className = 'health-score-circle ' + label;

    // Color the score value
    if (score >= 0.95) valueEl.style.color = 'var(--accent-green)';
    else if (score >= 0.80) valueEl.style.color = '#7cb342';
    else if (score >= 0.60) valueEl.style.color = 'var(--accent-yellow)';
    else valueEl.style.color = 'var(--accent-red)';

    // Timestamp
    if (data.ts_iso) {
        const d = new Date(data.ts_iso);
        tsEl.textContent = `Last collected: ${d.toLocaleTimeString()}`;
    }

    // Alert count
    const evCount = data.events_count || 0;
    if (evCount > 0) {
        alertsEl.textContent = `${evCount} event(s)`;
        alertsEl.style.color = 'var(--accent-yellow)';
    } else {
        alertsEl.textContent = 'No events';
        alertsEl.style.color = 'var(--text-muted)';
    }
}

function renderRedisGauges(redis) {
    const container = document.getElementById('health-redis-gauges');
    if (!redis || Object.keys(redis).length === 0) {
        container.innerHTML = '<div class="loading">No data yet...</div>';
        return;
    }

    const instanceOrder = ['system-redis', 'market-redis', 'intel-redis'];
    container.innerHTML = instanceOrder.map(name => {
        const info = redis[name];
        if (!info) return '';

        if (!info.alive) {
            return `
                <div class="health-redis-row">
                    <span class="health-redis-dot dead"></span>
                    <span class="health-redis-name">${name.replace('-redis', '')}</span>
                    <div class="health-redis-stats">
                        <span style="color: var(--accent-red)">DOWN</span>
                    </div>
                </div>
            `;
        }

        return `
            <div class="health-redis-row">
                <span class="health-redis-dot alive"></span>
                <span class="health-redis-name">${name.replace('-redis', '')}</span>
                <div class="health-redis-stats">
                    <span><span class="health-redis-stat-label">mem</span>${info.used_memory_mb}MB</span>
                    <span><span class="health-redis-stat-label">keys</span>${(info.total_keys || 0).toLocaleString()}</span>
                    <span><span class="health-redis-stat-label">clients</span>${info.connected_clients}</span>
                    <span><span class="health-redis-stat-label">ops/s</span>${info.ops_per_sec}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderHeartbeatGrid(heartbeats) {
    const container = document.getElementById('health-heartbeat-grid');
    if (!heartbeats || Object.keys(heartbeats).length === 0) {
        container.innerHTML = '<div class="loading">No data yet...</div>';
        return;
    }

    const serviceOrder = [
        'massive', 'sse', 'journal',
        'copilot', 'vexy_ai', 'rss_agg',
        'content_anal', 'healer', 'mesh'
    ];

    container.innerHTML = serviceOrder.map(svc => {
        const info = heartbeats[svc];
        if (!info) return '';

        const status = info.status || 'unknown';
        let ageText = '--';
        if (info.alive && info.age_sec !== null && info.age_sec !== undefined) {
            ageText = info.age_sec < 60 ? `${info.age_sec.toFixed(0)}s ago` : `${Math.floor(info.age_sec / 60)}m ago`;
        } else if (status === 'running_no_heartbeat') {
            ageText = `PID ${info.pid || '?'}`;
        } else if (!info.alive) {
            ageText = 'no signal';
        }

        // Display label: show "running*" for PID-alive but heartbeat-dead
        const displayStatus = status === 'running_no_heartbeat' ? 'running*' : status;

        return `
            <div class="health-hb-tile ${status}">
                <div class="health-hb-name">${svc}</div>
                <div class="health-hb-age">${ageText}</div>
                <div class="health-hb-status ${status}">${displayStatus}</div>
            </div>
        `;
    }).join('');
}

function renderHealthTimeline(history) {
    const canvas = document.getElementById('health-timeline-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;
    const pad = { top: 8, right: 8, bottom: 20, left: 35 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    // Clear
    ctx.clearRect(0, 0, w, h);

    // Background zones
    const zones = [
        { min: 0.8, max: 1.0, color: 'rgba(63, 185, 80, 0.06)' },
        { min: 0.6, max: 0.8, color: 'rgba(210, 153, 34, 0.06)' },
        { min: 0.0, max: 0.6, color: 'rgba(248, 81, 73, 0.06)' },
    ];

    zones.forEach(z => {
        const y1 = pad.top + plotH * (1 - z.max);
        const y2 = pad.top + plotH * (1 - z.min);
        ctx.fillStyle = z.color;
        ctx.fillRect(pad.left, y1, plotW, y2 - y1);
    });

    // Grid lines
    ctx.strokeStyle = '#30363d';
    ctx.lineWidth = 0.5;
    [0.2, 0.4, 0.6, 0.8, 1.0].forEach(v => {
        const y = pad.top + plotH * (1 - v);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + plotW, y);
        ctx.stroke();
    });

    // Y-axis labels
    ctx.fillStyle = '#484f58';
    ctx.font = '10px SF Mono, Menlo, monospace';
    ctx.textAlign = 'right';
    [0, 0.5, 1.0].forEach(v => {
        const y = pad.top + plotH * (1 - v);
        ctx.fillText((v * 100).toFixed(0), pad.left - 4, y + 3);
    });

    if (!history || history.length < 2) {
        ctx.fillStyle = '#484f58';
        ctx.font = '12px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Collecting data...', w / 2, h / 2);
        return;
    }

    // Plot score line
    const points = history.map((h, i) => ({
        x: pad.left + (i / (history.length - 1)) * plotW,
        y: pad.top + plotH * (1 - Math.max(0, Math.min(1, h.score))),
    }));

    // Line
    ctx.beginPath();
    ctx.strokeStyle = '#58a6ff';
    ctx.lineWidth = 1.5;
    points.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    // Fill under the line
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, pad.top + plotH);
    ctx.lineTo(points[0].x, pad.top + plotH);
    ctx.closePath();
    ctx.fillStyle = 'rgba(88, 166, 255, 0.08)';
    ctx.fill();

    // Dots at each point (if not too many)
    if (points.length <= 60) {
        points.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
            ctx.fillStyle = '#58a6ff';
            ctx.fill();
        });
    }

    // Time labels
    if (history.length > 1) {
        ctx.fillStyle = '#484f58';
        ctx.font = '10px SF Mono, Menlo, monospace';
        ctx.textAlign = 'center';

        const first = new Date(history[0].ts * 1000);
        const last = new Date(history[history.length - 1].ts * 1000);
        ctx.fillText(first.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}), pad.left, h - 4);
        ctx.fillText(last.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}), pad.left + plotW, h - 4);

        if (history.length > 10) {
            const midIdx = Math.floor(history.length / 2);
            const mid = new Date(history[midIdx].ts * 1000);
            ctx.fillText(mid.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}), pad.left + plotW / 2, h - 4);
        }
    }
}

function renderHealthEvents(events) {
    const container = document.getElementById('health-events-list');

    if (!events || events.length === 0) {
        container.innerHTML = '<div class="empty">No health events yet</div>';
        return;
    }

    // Filter by severity
    let filtered = events;
    if (healthEventFilter !== 'all') {
        filtered = events.filter(e => e.severity === healthEventFilter);
    }

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty">No ${healthEventFilter} events</div>`;
        return;
    }

    // Most recent first
    const sorted = [...filtered].reverse();

    container.innerHTML = sorted.map(event => {
        const severity = event.severity || 'info';
        const time = new Date(event.ts * 1000).toLocaleTimeString();
        const svcLabel = event.service || 'system';
        const icon = severity === 'critical' ? '!!!'
                   : severity === 'warning' ? '!'
                   : '\u2022';

        return `
            <div class="health-event-item ${severity}">
                <span class="health-event-severity ${severity}">${icon}</span>
                <span class="health-event-time">${time}</span>
                <span class="health-event-service">${svcLabel}</span>
                <span class="health-event-message">${event.message}</span>
            </div>
        `;
    }).join('');
}

function filterHealthEvents(severity) {
    healthEventFilter = severity;
    document.querySelectorAll('.health-filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.severity === severity);
    });
    renderHealthEvents(healthEvents);
}

// Health Webhook Config
async function openHealthWebhookConfig() {
    const modal = document.getElementById('health-webhook-modal');
    const urlInput = document.getElementById('health-webhook-url');

    // Load current config
    try {
        const resp = await fetch(`${API_BASE}/api/health/webhook`);
        if (resp.ok) {
            const config = await resp.json();
            urlInput.value = config.url || '';
        }
    } catch (e) {
        // Ignore, field stays empty
    }

    modal.classList.remove('hidden');
}

function closeHealthWebhookConfig() {
    document.getElementById('health-webhook-modal').classList.add('hidden');
}

async function saveHealthWebhook() {
    const url = document.getElementById('health-webhook-url').value.trim();

    try {
        const resp = await fetch(`${API_BASE}/api/health/webhook`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        if (resp.ok) {
            closeHealthWebhookConfig();
        } else {
            alert('Failed to save webhook config');
        }
    } catch (e) {
        alert('Error saving webhook: ' + e.message);
    }
}

// ============================================================
// AutoHealer Toggle
// ============================================================

async function refreshHealerStatus() {
    try {
        const resp = await fetch(`${API_BASE}/api/health/healer`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderHealerStatus(data);
    } catch (err) {
        console.error('Healer status error:', err);
    }
}

function renderHealerStatus(data) {
    const toggle = document.getElementById('healer-toggle');
    const statusText = document.getElementById('healer-status-text');
    const activeText = document.getElementById('healer-active-text');

    if (!toggle) return;

    toggle.checked = data.enabled;

    if (data.enabled) {
        statusText.textContent = 'Enabled';
        statusText.className = 'healer-status enabled';
    } else {
        statusText.textContent = 'Disabled';
        statusText.className = 'healer-status disabled';
    }

    if (data.active) {
        activeText.textContent = `Healing: ${data.active}`;
        activeText.className = 'healer-active active';
    } else {
        activeText.textContent = '';
    }
}

async function toggleHealer() {
    const toggle = document.getElementById('healer-toggle');
    const enabled = toggle.checked;

    try {
        const resp = await fetch(`${API_BASE}/api/health/healer/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (resp.ok) {
            const data = await resp.json();
            // Refresh full status to update UI
            refreshHealerStatus();
        } else {
            // Revert toggle on failure
            toggle.checked = !enabled;
            alert('Failed to toggle healer');
        }
    } catch (e) {
        toggle.checked = !enabled;
        alert('Error toggling healer: ' + e.message);
    }
}

// ============================================================
// Tier Gates
// ============================================================
let tierGatesConfig = null;

async function refreshTierGates() {
    try {
        const resp = await fetch(`${API_BASE}/api/tier-gates`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        tierGatesConfig = await resp.json();
        renderTierGatesEditor(tierGatesConfig);
    } catch (e) {
        console.error('Failed to load tier gates:', e);
        document.getElementById('tier-gates-grid').innerHTML =
            '<div class="empty">Failed to load tier gates config</div>';
    }
}

function renderTierGatesEditor(config) {
    // Update mode button
    const modeBtn = document.getElementById('tier-gates-mode-btn');
    const modeHint = document.getElementById('tier-gates-mode-hint');
    if (config.mode === 'full_production') {
        modeBtn.textContent = 'Full Production';
        modeBtn.className = 'tier-gates-mode-btn full-production';
        modeHint.textContent = 'All limits bypassed \u2014 every user gets full access';
    } else {
        modeBtn.textContent = 'Tier-Limited';
        modeBtn.className = 'tier-gates-mode-btn tier-limited';
        modeHint.textContent = 'Subscription enforcement active \u2014 limits applied per tier';
    }

    // Render allowed tiers toggles
    const allowedTiers = config.allowed_tiers || {};
    const accessContainer = document.getElementById('tier-gates-access-toggles');
    let accessHtml = '';
    for (const [tier, allowed] of Object.entries(allowedTiers)) {
        const label = tier.charAt(0).toUpperCase() + tier.slice(1);
        const checked = allowed ? 'checked' : '';
        accessHtml += `<label class="tier-gates-access-item">
            <label class="tier-gate-toggle">
                <input type="checkbox" data-access-tier="${tier}" ${checked}>
                <span class="slider"></span>
            </label>
            ${label}
        </label>`;
    }
    accessContainer.innerHTML = accessHtml;

    const tiers = ['observer', 'activator', 'navigator'];
    const defaults = config.defaults || {};
    const tierOverrides = config.tiers || {};

    let html = '<table class="tier-gates-table"><thead><tr>';
    html += '<th>Feature</th>';
    tiers.forEach(t => {
        html += `<th class="tier-col">${t.charAt(0).toUpperCase() + t.slice(1)}</th>`;
    });
    html += '</tr></thead><tbody>';

    for (const [key, feat] of Object.entries(defaults)) {
        html += '<tr>';
        html += `<td><div class="feature-label">${feat.label}</div><div class="feature-key">${key}</div></td>`;

        tiers.forEach(tier => {
            const tierVals = tierOverrides[tier] || {};
            const val = tierVals[key] !== undefined ? tierVals[key] : feat.value;

            html += '<td class="tier-col">';
            if (feat.type === 'boolean') {
                const checked = val ? 'checked' : '';
                html += `<label class="tier-gate-toggle">
                    <input type="checkbox" data-tier="${tier}" data-key="${key}" data-type="boolean" ${checked}>
                    <span class="slider"></span>
                </label>`;
            } else {
                const cls = val === -1 ? 'unlimited' : '';
                html += `<input type="number" class="tier-gate-number ${cls}"
                    data-tier="${tier}" data-key="${key}" data-type="number"
                    value="${val}" min="-1" step="1"
                    onchange="this.classList.toggle('unlimited', this.value=='-1')">`;
            }
            html += '</td>';
        });

        html += '</tr>';
    }

    html += '</tbody></table>';
    document.getElementById('tier-gates-grid').innerHTML = html;
}

async function toggleTierGatesMode() {
    if (!tierGatesConfig) return;
    const newMode = tierGatesConfig.mode === 'full_production' ? 'tier_limited' : 'full_production';
    tierGatesConfig.mode = newMode;
    // Collect current values and save immediately
    collectTierGateValues();
    await saveTierGates();
}

function collectTierGateValues() {
    if (!tierGatesConfig) return;

    // Read allowed tiers
    const accessInputs = document.querySelectorAll('[data-access-tier]');
    if (!tierGatesConfig.allowed_tiers) tierGatesConfig.allowed_tiers = {};
    accessInputs.forEach(input => {
        tierGatesConfig.allowed_tiers[input.dataset.accessTier] = input.checked;
    });

    // Read all inputs from the grid
    const inputs = document.querySelectorAll('#tier-gates-grid [data-tier]');
    inputs.forEach(input => {
        const tier = input.dataset.tier;
        const key = input.dataset.key;
        const type = input.dataset.type;

        if (!tierGatesConfig.tiers[tier]) tierGatesConfig.tiers[tier] = {};

        if (type === 'boolean') {
            tierGatesConfig.tiers[tier][key] = input.checked;
        } else {
            tierGatesConfig.tiers[tier][key] = parseInt(input.value, 10) || -1;
        }
    });
}

async function saveTierGates() {
    if (!tierGatesConfig) {
        alert('No tier gates config loaded');
        return;
    }

    collectTierGateValues();

    try {
        const resp = await fetch(`${API_BASE}/api/tier-gates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(tierGatesConfig),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        tierGatesConfig = data.config;
        renderTierGatesEditor(tierGatesConfig);
        addAlert('info', 'Tier Gates Saved', 'Configuration saved and published to all services', 'tier-gates');
    } catch (e) {
        alert('Failed to save tier gates: ' + e.message);
    }
}

async function resetTierGates() {
    if (!confirm('Reset all tier gates to defaults? This sets mode to Full Production and removes all custom limits.')) return;

    try {
        const resp = await fetch(`${API_BASE}/api/tier-gates/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        tierGatesConfig = data.config;
        renderTierGatesEditor(tierGatesConfig);
        addAlert('info', 'Tier Gates Reset', 'Configuration reset to defaults', 'tier-gates');
    } catch (e) {
        alert('Failed to reset tier gates: ' + e.message);
    }
}

// Load tier gates on page init
document.addEventListener('DOMContentLoaded', () => {
    refreshTierGates();
});
