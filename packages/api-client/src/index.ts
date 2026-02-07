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

// Client
export type { MarketSwarmClient } from './client.js';
export { createClient } from './client.js';

// Types
export type {
  ApiResponse,
  CreatePositionInput,
  UpdatePositionInput,
  PositionsListResponse,
  PositionResponse,
  StrategyType,
  Side,
  Strategy,
  CreateStrategyInput,
  UpdateStrategyInput,
  StrategiesListResponse,
  StrategyResponse,
  Template,
  CreateTemplateInput,
  TemplatesListResponse,
  User,
  AuthResponse,
  LoginInput,
  RegisterInput,
  SSEEventType,
  SSEEvent,
  ClientOptions,
} from './types.js';

// Adapters
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
} from './adapters/types.js';

export {
  webAdapter,
  webStorageAdapter,
  webNetworkAdapter,
  webNotificationAdapter,
} from './adapters/web.js';

// Sync
export type {
  MutationType,
  EntityType,
  QueuedMutation,
  QueueStatus,
  SyncState,
  SyncEvent,
  SyncEventHandler,
  ConflictStrategy,
  Conflict,
  ConflictHandler,
} from './sync/types.js';

export { MutationQueue } from './sync/queue.js';
export { SyncManager } from './sync/manager.js';

// Endpoints
export type { StrategiesEndpoint } from './endpoints/strategies.js';
export type { PositionsEndpoint } from './endpoints/positions.js';
