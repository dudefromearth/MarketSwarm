/**
 * Sync Types
 *
 * Types for offline queue and synchronization.
 */
/** Mutation operation type */
export type MutationType = 'create' | 'update' | 'delete';
/** Entity type being mutated */
export type EntityType = 'position' | 'strategy' | 'template' | 'alert';
/** Queued mutation */
export interface QueuedMutation {
    /** Unique mutation ID */
    id: string;
    /** When the mutation was queued */
    queuedAt: number;
    /** Entity type */
    entityType: EntityType;
    /** Mutation type */
    mutationType: MutationType;
    /** Entity ID (for update/delete) */
    entityId?: string;
    /** Mutation payload */
    payload: unknown;
    /** Number of retry attempts */
    retryCount: number;
    /** Last error message if failed */
    lastError?: string;
    /** Optimistic ID for creates */
    optimisticId?: string;
}
/** Queue status */
export interface QueueStatus {
    /** Number of pending mutations */
    pending: number;
    /** Number of failed mutations */
    failed: number;
    /** Whether sync is in progress */
    syncing: boolean;
    /** Last sync timestamp */
    lastSyncAt: number | null;
    /** Last error */
    lastError: string | null;
}
/** Sync status */
export type SyncState = 'idle' | 'syncing' | 'error' | 'offline';
/** Sync event */
export interface SyncEvent {
    type: 'sync_start' | 'sync_complete' | 'sync_error' | 'mutation_synced' | 'mutation_failed';
    mutation?: QueuedMutation;
    error?: Error;
    timestamp: number;
}
/** Sync event handler */
export type SyncEventHandler = (event: SyncEvent) => void;
/** Conflict resolution strategy */
export type ConflictStrategy = 'client_wins' | 'server_wins' | 'manual';
/** Conflict details */
export interface Conflict {
    /** Entity type */
    entityType: EntityType;
    /** Entity ID */
    entityId: string;
    /** Client version */
    clientData: unknown;
    /** Server version */
    serverData: unknown;
    /** Mutation that caused conflict */
    mutation: QueuedMutation;
}
/** Conflict resolution handler */
export type ConflictHandler = (conflict: Conflict) => Promise<'client' | 'server' | 'merge'>;
//# sourceMappingURL=types.d.ts.map