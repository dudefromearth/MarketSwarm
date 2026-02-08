/**
 * Web Platform Adapter
 *
 * Implementation for browser environments using:
 * - localStorage for storage
 * - fetch for network requests
 * - EventSource for SSE
 * - Notification API for notifications
 */

import type {
  PlatformAdapter,
  StorageAdapter,
  NetworkAdapter,
  NotificationAdapter,
  RequestOptions,
  NetworkResponse,
  SSEHandler,
  SSEConnection,
  NotificationOptions,
} from './types.js';

// ============================================================
// Web Storage Adapter (localStorage)
// ============================================================

const STORAGE_PREFIX = 'ms:';

export const webStorageAdapter: StorageAdapter = {
  async get<T>(key: string): Promise<T | null> {
    try {
      const value = localStorage.getItem(STORAGE_PREFIX + key);
      if (value === null) return null;
      return JSON.parse(value) as T;
    } catch {
      return null;
    }
  },

  async set<T>(key: string, value: T): Promise<void> {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
  },

  async delete(key: string): Promise<void> {
    localStorage.removeItem(STORAGE_PREFIX + key);
  },

  async clear(): Promise<void> {
    const keys = await this.keys();
    for (const key of keys) {
      localStorage.removeItem(STORAGE_PREFIX + key);
    }
  },

  async keys(): Promise<string[]> {
    const result: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(STORAGE_PREFIX)) {
        result.push(key.slice(STORAGE_PREFIX.length));
      }
    }
    return result;
  },

  async has(key: string): Promise<boolean> {
    return localStorage.getItem(STORAGE_PREFIX + key) !== null;
  },
};

// ============================================================
// Web Network Adapter (fetch)
// ============================================================

export const webNetworkAdapter: NetworkAdapter = {
  async request<T>(url: string, options: RequestOptions = {}): Promise<NetworkResponse<T>> {
    const { method = 'GET', headers = {}, body, timeout = 30000, signal } = options;

    console.log('[webNetworkAdapter.request]', method, url, { body, headers });

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
        credentials: 'include', // Send cookies for authentication
      });

      clearTimeout(timeoutId);

      // Parse response headers
      const responseHeaders: Record<string, string> = {};
      response.headers.forEach((value, key) => {
        responseHeaders[key] = value;
      });

      // Parse response body
      let data: T;
      const contentType = response.headers.get('content-type');
      const rawText = await response.text();
      console.log('[webNetworkAdapter.response]', response.status, contentType, rawText.slice(0, 200));
      if (contentType?.includes('application/json')) {
        data = JSON.parse(rawText) as T;
      } else {
        data = rawText as unknown as T;
      }

      return {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        data,
        headers: responseHeaders,
      };
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  },

  isOnline(): boolean {
    return navigator.onLine;
  },

  onOnlineChange(handler: (online: boolean) => void): () => void {
    const onOnline = () => handler(true);
    const onOffline = () => handler(false);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  },

  createSSE(url: string, handler: SSEHandler): SSEConnection {
    // Include credentials to send cookies for authentication
    const eventSource = new EventSource(url, { withCredentials: true });

    eventSource.onopen = () => {
      handler.onOpen?.();
    };

    // Handle unnamed events (fallback)
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handler.onMessage({ type: event.type, data });
      } catch {
        handler.onMessage({ type: event.type, data: event.data });
      }
    };

    // Handle named events (positions, strategies, etc.)
    // These are sent by server with `event: eventName\ndata: ...\n\n`
    const namedEventTypes = [
      'connected',
      'position_created',
      'position_updated',
      'position_deleted',
      'position_batch_created',
      'position_reordered',
      'strategy_created',
      'strategy_updated',
      'strategy_deleted',
    ];

    for (const eventType of namedEventTypes) {
      eventSource.addEventListener(eventType, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          // Extract action from event type (e.g., 'position_created' -> 'created')
          const parts = eventType.split('_');
          const action = parts.length > 1 ? parts.slice(1).join('_') : eventType;
          handler.onMessage({ type: eventType, data: { ...data, action } });
        } catch {
          handler.onMessage({ type: eventType, data: event.data });
        }
      });
    }

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
            return 'connecting' as const;
          case EventSource.OPEN:
            return 'open' as const;
          default:
            return 'closed' as const;
        }
      },
    };
  },
};

// ============================================================
// Web Notification Adapter
// ============================================================

export const webNotificationAdapter: NotificationAdapter = {
  async requestPermission(): Promise<'granted' | 'denied' | 'default'> {
    if (!('Notification' in window)) {
      return 'denied';
    }
    const result = await Notification.requestPermission();
    return result;
  },

  getPermission(): 'granted' | 'denied' | 'default' {
    if (!('Notification' in window)) {
      return 'denied';
    }
    return Notification.permission;
  },

  async show(options: NotificationOptions): Promise<void> {
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

  async cancel(tag: string): Promise<void> {
    // Web Notification API doesn't support programmatic cancellation
    // Tags are used for replacement only
    console.debug('Notification cancel not supported on web:', tag);
  },
};

// ============================================================
// Web Platform Adapter Bundle
// ============================================================

export const webAdapter: PlatformAdapter = {
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
