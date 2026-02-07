/**
 * Web Platform Adapter
 *
 * Implementation for browser environments using:
 * - localStorage for storage
 * - fetch for network requests
 * - EventSource for SSE
 * - Notification API for notifications
 */
// ============================================================
// Web Storage Adapter (localStorage)
// ============================================================
const STORAGE_PREFIX = 'ms:';
export const webStorageAdapter = {
    async get(key) {
        try {
            const value = localStorage.getItem(STORAGE_PREFIX + key);
            if (value === null)
                return null;
            return JSON.parse(value);
        }
        catch {
            return null;
        }
    },
    async set(key, value) {
        localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
    },
    async delete(key) {
        localStorage.removeItem(STORAGE_PREFIX + key);
    },
    async clear() {
        const keys = await this.keys();
        for (const key of keys) {
            localStorage.removeItem(STORAGE_PREFIX + key);
        }
    },
    async keys() {
        const result = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith(STORAGE_PREFIX)) {
                result.push(key.slice(STORAGE_PREFIX.length));
            }
        }
        return result;
    },
    async has(key) {
        return localStorage.getItem(STORAGE_PREFIX + key) !== null;
    },
};
// ============================================================
// Web Network Adapter (fetch)
// ============================================================
export const webNetworkAdapter = {
    async request(url, options = {}) {
        const { method = 'GET', headers = {}, body, timeout = 30000, signal } = options;
        // Create timeout abort controller if needed
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        // Merge signals if provided
        const combinedSignal = signal
            ? new AbortController().signal
            : controller.signal;
        if (signal) {
            signal.addEventListener('abort', () => controller.abort());
        }
        try {
            const response = await fetch(url, {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    ...headers,
                },
                body: body ? JSON.stringify(body) : undefined,
                signal: combinedSignal,
            });
            clearTimeout(timeoutId);
            // Parse response headers
            const responseHeaders = {};
            response.headers.forEach((value, key) => {
                responseHeaders[key] = value;
            });
            // Parse response body
            let data;
            const contentType = response.headers.get('content-type');
            if (contentType?.includes('application/json')) {
                data = await response.json();
            }
            else {
                data = await response.text();
            }
            return {
                ok: response.ok,
                status: response.status,
                statusText: response.statusText,
                data,
                headers: responseHeaders,
            };
        }
        catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    },
    isOnline() {
        return navigator.onLine;
    },
    onOnlineChange(handler) {
        const onOnline = () => handler(true);
        const onOffline = () => handler(false);
        window.addEventListener('online', onOnline);
        window.addEventListener('offline', onOffline);
        return () => {
            window.removeEventListener('online', onOnline);
            window.removeEventListener('offline', onOffline);
        };
    },
    createSSE(url, handler) {
        const eventSource = new EventSource(url);
        eventSource.onopen = () => {
            handler.onOpen?.();
        };
        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handler.onMessage({ type: event.type, data });
            }
            catch {
                handler.onMessage({ type: event.type, data: event.data });
            }
        };
        eventSource.onerror = () => {
            handler.onError?.(new Error('SSE connection error'));
        };
        return {
            close() {
                eventSource.close();
                handler.onClose?.();
            },
            get readyState() {
                switch (eventSource.readyState) {
                    case EventSource.CONNECTING:
                        return 'connecting';
                    case EventSource.OPEN:
                        return 'open';
                    default:
                        return 'closed';
                }
            },
        };
    },
};
// ============================================================
// Web Notification Adapter
// ============================================================
export const webNotificationAdapter = {
    async requestPermission() {
        if (!('Notification' in window)) {
            return 'denied';
        }
        const result = await Notification.requestPermission();
        return result;
    },
    getPermission() {
        if (!('Notification' in window)) {
            return 'denied';
        }
        return Notification.permission;
    },
    async show(options) {
        if (!('Notification' in window)) {
            return;
        }
        if (Notification.permission !== 'granted') {
            return;
        }
        new Notification(options.title, {
            body: options.body,
            icon: options.icon,
            tag: options.tag,
            data: options.data,
            silent: options.silent,
            requireInteraction: options.requireInteraction,
        });
    },
    async cancel(tag) {
        // Web Notification API doesn't support programmatic cancellation
        // Tags are used for replacement only
        console.debug('Notification cancel not supported on web:', tag);
    },
};
// ============================================================
// Web Platform Adapter Bundle
// ============================================================
export const webAdapter = {
    storage: webStorageAdapter,
    network: webNetworkAdapter,
    notifications: webNotificationAdapter,
    platform: 'web',
    info: {
        version: '1.0.0',
        os: typeof navigator !== 'undefined' ? navigator.platform : 'unknown',
    },
};
export default webAdapter;
//# sourceMappingURL=web.js.map