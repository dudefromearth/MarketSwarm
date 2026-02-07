/**
 * Market Swarm API Client
 *
 * Main client class that provides typed access to all API endpoints
 * with offline support and automatic sync.
 */

import type { PlatformAdapter, SSEConnection, SSEHandler } from './adapters/types.js';
import type { ClientOptions, SSEEvent } from './types.js';
import type { StrategiesEndpoint } from './endpoints/strategies.js';
import type { PositionsEndpoint } from './endpoints/positions.js';
import type { SyncState, SyncEventHandler, ConflictHandler } from './sync/types.js';

import { createStrategiesEndpoint } from './endpoints/strategies.js';
import { createPositionsEndpoint } from './endpoints/positions.js';
import { MutationQueue } from './sync/queue.js';
import { SyncManager } from './sync/manager.js';

export interface MarketSwarmClient {
  /** Position endpoints (leg-based model) */
  positions: PositionsEndpoint;

  /** Strategy endpoints (legacy model) */
  strategies: StrategiesEndpoint;

  /** Sync management */
  sync: {
    start(): void;
    stop(): void;
    getState(): SyncState;
    onEvent(handler: SyncEventHandler): () => void;
    setConflictHandler(handler: ConflictHandler): void;
    flush(): Promise<void>;
  };

  /** SSE subscriptions */
  sse: {
    subscribe(handler: (event: SSEEvent) => void): SSEConnection;
    subscribeToStrategies(handler: (event: SSEEvent) => void): SSEConnection;
    subscribeToPositions(handler: (event: SSEEvent) => void): SSEConnection;
  };

  /** Auth management */
  auth: {
    setToken(token: string): void;
    clearToken(): void;
    getToken(): string | null;
  };

  /** Check if online */
  isOnline(): boolean;

  /** Cleanup resources */
  destroy(): void;
}

/**
 * Create a Market Swarm API client
 */
export function createClient(
  adapter: PlatformAdapter,
  options: ClientOptions
): MarketSwarmClient {
  const { baseUrl, offlineEnabled = true } = options;

  let token: string | null = options.token ?? null;

  // Create mutation queue
  const queue = new MutationQueue(adapter.storage);

  // Create sync manager
  const syncManager = new SyncManager({
    baseUrl,
    network: adapter.network,
    queue,
    getAuthToken: async () => token,
  });

  // Helper to get headers with auth
  const getHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  };

  // Create endpoints
  const strategies = createStrategiesEndpoint(adapter.network, baseUrl, getHeaders);
  const positions = createPositionsEndpoint(adapter.network, baseUrl, getHeaders);

  // SSE connections
  const sseConnections: Set<SSEConnection> = new Set();

  const createSSESubscription = (
    path: string,
    handler: (event: SSEEvent) => void
  ): SSEConnection => {
    const url = `${baseUrl}${path}${token ? `?token=${token}` : ''}`;

    const sseHandler: SSEHandler = {
      onMessage: (event) => {
        handler(event as SSEEvent);
      },
      onError: (error) => {
        console.error('SSE error:', error);
      },
    };

    const connection = adapter.network.createSSE(url, sseHandler);
    sseConnections.add(connection);

    // Return wrapped connection that removes from set on close
    return {
      close() {
        connection.close();
        sseConnections.delete(connection);
      },
      get readyState() {
        return connection.readyState;
      },
    };
  };

  // Start sync if offline enabled
  if (offlineEnabled) {
    syncManager.start();
  }

  return {
    positions,
    strategies,

    sync: {
      start() {
        syncManager.start();
      },
      stop() {
        syncManager.stop();
      },
      getState() {
        return syncManager.getState();
      },
      onEvent(handler: SyncEventHandler) {
        return syncManager.onEvent(handler);
      },
      setConflictHandler(handler: ConflictHandler) {
        syncManager.setConflictHandler(handler);
      },
      async flush() {
        await syncManager.sync();
      },
    },

    sse: {
      subscribe(handler: (event: SSEEvent) => void): SSEConnection {
        return createSSESubscription('/sse', handler);
      },
      subscribeToStrategies(handler: (event: SSEEvent) => void): SSEConnection {
        return createSSESubscription('/sse/risk-graph', handler);
      },
      subscribeToPositions(handler: (event: SSEEvent) => void): SSEConnection {
        return createSSESubscription('/sse/positions', handler);
      },
    },

    auth: {
      setToken(newToken: string) {
        token = newToken;
        options.onTokenRefresh?.(newToken);
      },
      clearToken() {
        token = null;
      },
      getToken() {
        return token;
      },
    },

    isOnline() {
      return adapter.network.isOnline();
    },

    destroy() {
      // Stop sync
      syncManager.stop();

      // Close all SSE connections
      for (const connection of sseConnections) {
        connection.close();
      }
      sseConnections.clear();
    },
  };
}
