/**
 * Mutation Queue
 *
 * Persists mutations when offline for later sync.
 */
import type { StorageAdapter } from '../adapters/types.js';
import type { QueuedMutation, QueueStatus, MutationType, EntityType } from './types.js';
/**
 * Mutation Queue
 *
 * Manages a queue of mutations that need to be synced with the server.
 * Persists to storage for durability across app restarts.
 */
export declare class MutationQueue {
    private storage;
    private queue;
    private loaded;
    constructor(storage: StorageAdapter);
    /**
     * Load queue from storage
     */
    load(): Promise<void>;
    /**
     * Save queue to storage
     */
    private save;
    /**
     * Add a mutation to the queue
     */
    enqueue(entityType: EntityType, mutationType: MutationType, payload: unknown, entityId?: string, optimisticId?: string): Promise<QueuedMutation>;
    /**
     * Get the next mutation to process
     */
    peek(): Promise<QueuedMutation | null>;
    /**
     * Get all pending mutations
     */
    getAll(): Promise<QueuedMutation[]>;
    /**
     * Remove a mutation from the queue (after successful sync)
     */
    dequeue(mutationId: string): Promise<void>;
    /**
     * Mark a mutation as failed and increment retry count
     */
    markFailed(mutationId: string, error: string): Promise<boolean>;
    /**
     * Remove a specific mutation (e.g., after conflict resolution)
     */
    remove(mutationId: string): Promise<void>;
    /**
     * Clear all mutations
     */
    clear(): Promise<void>;
    /**
     * Get queue status
     */
    getStatus(): Promise<QueueStatus>;
    /**
     * Get mutations for a specific entity
     */
    getForEntity(entityType: EntityType, entityId: string): Promise<QueuedMutation[]>;
    /**
     * Check if there are pending mutations for an entity
     */
    hasPending(entityType: EntityType, entityId: string): Promise<boolean>;
    /**
     * Get count of pending mutations
     */
    count(): Promise<number>;
}
//# sourceMappingURL=queue.d.ts.map