/**
 * @market-swarm/api-client
 *
 * API client for Market Swarm with offline support and platform adapters.
 *
 * Usage:
 * ```typescript
 * import { createClient, webAdapter } from '@market-swarm/api-client';
 *
 * const client = createClient(webAdapter, {
 *   baseUrl: 'http://localhost:3001',
 *   token: 'your-auth-token',
 * });
 *
 * // Fetch positions
 * const positions = await client.positions.list();
 *
 * // Subscribe to SSE events
 * const connection = client.sse.subscribeToPositions((event) => {
 *   console.log('Position event:', event);
 * });
 *
 * // Cleanup
 * client.destroy();
 * ```
 */
export { createClient } from './client.js';
export { webAdapter, webStorageAdapter, webNetworkAdapter, webNotificationAdapter, } from './adapters/web.js';
export { MutationQueue } from './sync/queue.js';
export { SyncManager } from './sync/manager.js';
//# sourceMappingURL=index.js.map