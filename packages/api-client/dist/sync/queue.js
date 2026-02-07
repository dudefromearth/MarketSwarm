/**
 * Mutation Queue
 *
 * Persists mutations when offline for later sync.
 */
const QUEUE_KEY = 'mutation_queue';
const MAX_RETRIES = 3;
/**
 * Generate a unique mutation ID
 */
function generateMutationId() {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).slice(2, 8);
    return `mut_${timestamp}_${random}`;
}
/**
 * Mutation Queue
 *
 * Manages a queue of mutations that need to be synced with the server.
 * Persists to storage for durability across app restarts.
 */
export class MutationQueue {
    storage;
    queue = [];
    loaded = false;
    constructor(storage) {
        this.storage = storage;
    }
    /**
     * Load queue from storage
     */
    async load() {
        if (this.loaded)
            return;
        const stored = await this.storage.get(QUEUE_KEY);
        this.queue = stored ?? [];
        this.loaded = true;
    }
    /**
     * Save queue to storage
     */
    async save() {
        await this.storage.set(QUEUE_KEY, this.queue);
    }
    /**
     * Add a mutation to the queue
     */
    async enqueue(entityType, mutationType, payload, entityId, optimisticId) {
        await this.load();
        const mutation = {
            id: generateMutationId(),
            queuedAt: Date.now(),
            entityType,
            mutationType,
            entityId,
            payload,
            retryCount: 0,
            optimisticId,
        };
        this.queue.push(mutation);
        await this.save();
        return mutation;
    }
    /**
     * Get the next mutation to process
     */
    async peek() {
        await this.load();
        return this.queue[0] ?? null;
    }
    /**
     * Get all pending mutations
     */
    async getAll() {
        await this.load();
        return [...this.queue];
    }
    /**
     * Remove a mutation from the queue (after successful sync)
     */
    async dequeue(mutationId) {
        await this.load();
        this.queue = this.queue.filter(m => m.id !== mutationId);
        await this.save();
    }
    /**
     * Mark a mutation as failed and increment retry count
     */
    async markFailed(mutationId, error) {
        await this.load();
        const mutation = this.queue.find(m => m.id === mutationId);
        if (!mutation)
            return false;
        mutation.retryCount++;
        mutation.lastError = error;
        // If max retries reached, move to end of queue
        if (mutation.retryCount >= MAX_RETRIES) {
            this.queue = this.queue.filter(m => m.id !== mutationId);
            this.queue.push(mutation);
        }
        await this.save();
        return mutation.retryCount < MAX_RETRIES;
    }
    /**
     * Remove a specific mutation (e.g., after conflict resolution)
     */
    async remove(mutationId) {
        await this.load();
        this.queue = this.queue.filter(m => m.id !== mutationId);
        await this.save();
    }
    /**
     * Clear all mutations
     */
    async clear() {
        this.queue = [];
        await this.save();
    }
    /**
     * Get queue status
     */
    async getStatus() {
        await this.load();
        const pending = this.queue.filter(m => m.retryCount < MAX_RETRIES).length;
        const failed = this.queue.filter(m => m.retryCount >= MAX_RETRIES).length;
        return {
            pending,
            failed,
            syncing: false,
            lastSyncAt: null,
            lastError: null,
        };
    }
    /**
     * Get mutations for a specific entity
     */
    async getForEntity(entityType, entityId) {
        await this.load();
        return this.queue.filter(m => m.entityType === entityType && m.entityId === entityId);
    }
    /**
     * Check if there are pending mutations for an entity
     */
    async hasPending(entityType, entityId) {
        const mutations = await this.getForEntity(entityType, entityId);
        return mutations.length > 0;
    }
    /**
     * Get count of pending mutations
     */
    async count() {
        await this.load();
        return this.queue.length;
    }
}
//# sourceMappingURL=queue.js.map