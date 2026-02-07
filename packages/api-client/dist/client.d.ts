/**
 * Market Swarm API Client
 *
 * Main client class that provides typed access to all API endpoints
 * with offline support and automatic sync.
 */
import type { PlatformAdapter, SSEConnection } from './adapters/types.js';
import type { ClientOptions, SSEEvent } from './types.js';
import type { StrategiesEndpoint } from './endpoints/strategies.js';
import type { PositionsEndpoint } from './endpoints/positions.js';
import type { SyncState, SyncEventHandler, ConflictHandler } from './sync/types.js';
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
export declare function createClient(adapter: PlatformAdapter, options: ClientOptions): MarketSwarmClient;
//# sourceMappingURL=client.d.ts.map