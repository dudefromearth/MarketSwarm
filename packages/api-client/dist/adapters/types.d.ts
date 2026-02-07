/**
 * Platform Adapter Types
 *
 * Interfaces that each platform (web, desktop, mobile) implements
 * to provide storage, network, and notification capabilities.
 */
/**
 * Abstract storage interface for persisting data
 *
 * Implementations:
 * - Web: localStorage/IndexedDB
 * - Desktop (Tauri): SQLite via Rust commands
 * - Mobile (React Native): AsyncStorage/SQLite
 */
export interface StorageAdapter {
    /** Get a value by key */
    get<T>(key: string): Promise<T | null>;
    /** Set a value by key */
    set<T>(key: string, value: T): Promise<void>;
    /** Delete a value by key */
    delete(key: string): Promise<void>;
    /** Clear all storage */
    clear(): Promise<void>;
    /** Get all keys */
    keys(): Promise<string[]>;
    /** Check if a key exists */
    has(key: string): Promise<boolean>;
}
/**
 * Network request options
 */
export interface RequestOptions {
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    headers?: Record<string, string>;
    body?: unknown;
    timeout?: number;
    signal?: AbortSignal;
}
/**
 * Network response
 */
export interface NetworkResponse<T = unknown> {
    ok: boolean;
    status: number;
    statusText: string;
    data: T;
    headers: Record<string, string>;
}
/**
 * SSE event handler
 */
export interface SSEHandler {
    onMessage: (event: {
        type: string;
        data: unknown;
    }) => void;
    onError?: (error: Error) => void;
    onOpen?: () => void;
    onClose?: () => void;
}
/**
 * SSE connection
 */
export interface SSEConnection {
    close(): void;
    readonly readyState: 'connecting' | 'open' | 'closed';
}
/**
 * Abstract network interface
 *
 * Implementations:
 * - Web: fetch API
 * - Desktop (Tauri): Tauri HTTP plugin or fetch
 * - Mobile (React Native): fetch with polyfills
 */
export interface NetworkAdapter {
    /** Make an HTTP request */
    request<T>(url: string, options?: RequestOptions): Promise<NetworkResponse<T>>;
    /** Check if currently online */
    isOnline(): boolean;
    /** Subscribe to online/offline changes */
    onOnlineChange(handler: (online: boolean) => void): () => void;
    /** Create an SSE connection */
    createSSE(url: string, handler: SSEHandler): SSEConnection;
}
/**
 * Notification options
 */
export interface NotificationOptions {
    title: string;
    body?: string;
    icon?: string;
    tag?: string;
    data?: unknown;
    silent?: boolean;
    requireInteraction?: boolean;
}
/**
 * Abstract notification interface
 *
 * Implementations:
 * - Web: Notification API
 * - Desktop (Tauri): Native notifications via Rust
 * - Mobile (React Native): Push notifications
 */
export interface NotificationAdapter {
    /** Request notification permission */
    requestPermission(): Promise<'granted' | 'denied' | 'default'>;
    /** Check current permission status */
    getPermission(): 'granted' | 'denied' | 'default';
    /** Show a notification */
    show(options: NotificationOptions): Promise<void>;
    /** Cancel a notification by tag */
    cancel(tag: string): Promise<void>;
}
/**
 * Complete platform adapter bundle
 *
 * Each platform provides an implementation of this interface
 * that gets passed to the API client on initialization.
 */
export interface PlatformAdapter {
    storage: StorageAdapter;
    network: NetworkAdapter;
    notifications?: NotificationAdapter;
    /** Platform identifier */
    platform: 'web' | 'desktop' | 'mobile';
    /** Platform-specific info */
    info?: {
        version?: string;
        os?: string;
        device?: string;
    };
}
//# sourceMappingURL=types.d.ts.map