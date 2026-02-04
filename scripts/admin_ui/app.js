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
