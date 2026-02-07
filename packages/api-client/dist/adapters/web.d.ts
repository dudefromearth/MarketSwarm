/**
 * Web Platform Adapter
 *
 * Implementation for browser environments using:
 * - localStorage for storage
 * - fetch for network requests
 * - EventSource for SSE
 * - Notification API for notifications
 */
import type { PlatformAdapter, StorageAdapter, NetworkAdapter, NotificationAdapter } from './types.js';
export declare const webStorageAdapter: StorageAdapter;
export declare const webNetworkAdapter: NetworkAdapter;
export declare const webNotificationAdapter: NotificationAdapter;
export declare const webAdapter: PlatformAdapter;
export default webAdapter;
//# sourceMappingURL=web.d.ts.map