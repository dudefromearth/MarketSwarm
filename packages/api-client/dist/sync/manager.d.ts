/**
 * Sync Manager
 *
 * Coordinates syncing queued mutations with the server.
 */
import type { NetworkAdapter } from '../adapters/types.js';
import type { SyncState, SyncEventHandler, ConflictHandler, ConflictStrategy } from './types.js';
import { MutationQueue } from './queue.js';
interface SyncManagerOptions {
    /** Base URL for API */
    baseUrl: string;
    /** Network adapter */
    network: NetworkAdapter;
    /** Mutation queue */
    queue: MutationQueue;
    /** Default conflict strategy */
    conflictStrategy?: ConflictStrategy;
    /** Sync interval in ms */
    syncInterval?: number;
    /** Auth token getter */
    getAuthToken?: () => Promise<string | null>;
}
/**
 * Sync Manager
 *
 * Manages synchronization of queued mutations with the server.
 * Handles online/offline transitions and conflict resolution.
 */
export declare class SyncManager {
    private baseUrl;
    private network;
    private queue;
    private conflictStrategy;
    private syncInterval;
    private getAuthToken?;
    private state;
    private syncTimer;
    private eventHandlers;
    private conflictHandler;
    private unsubscribeOnline;
    constructor(options: SyncManagerOptions);
    /**
     * Start sync manager
     */
    start(): void;
    /**
     * Stop sync manager
     */
    stop(): void;
    /**
     * Get current sync state
     */
    getState(): SyncState;
    /**
     * Subscribe to sync events
     */
    onEvent(handler: SyncEventHandler): () => void;
    /**
     * Set conflict handler
     */
    setConflictHandler(handler: ConflictHandler): void;
    /**
     * Emit sync event
     */
    private emit;
    /**
     * Sync all queued mutations
     */
    sync(): Promise<void>;
    /**
     * Sync a single mutation
     */
    private syncMutation;
    /**
     * Get API endpoint for mutation
     */
    private getMutationEndpoint;
    /**
     * Get HTTP method for mutation
     */
    private getMutationMethod;
    /**
     * Handle conflict
     */
    private handleConflict;
    /**
     * Force sync a mutation (override server version)
     */
    private forceSync;
    /**
     * Delay helper
     */
    private delay;
}
export {};
//# sourceMappingURL=manager.d.ts.map