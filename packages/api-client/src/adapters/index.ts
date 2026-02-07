/**
 * Platform Adapters
 *
 * Export adapter types and implementations.
 */

// Types
export type {
  StorageAdapter,
  NetworkAdapter,
  NotificationAdapter,
  PlatformAdapter,
  RequestOptions,
  NetworkResponse,
  SSEHandler,
  SSEConnection,
  NotificationOptions,
} from './types.js';

// Web adapter
export {
  webAdapter,
  webStorageAdapter,
  webNetworkAdapter,
  webNotificationAdapter,
} from './web.js';
