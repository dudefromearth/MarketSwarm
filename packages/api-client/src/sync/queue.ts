/**
 * Mutation Queue
 *
 * Persists mutations when offline for later sync.
 */

import type { StorageAdapter } from '../adapters/types.js';
import type {
  QueuedMutation,
  QueueStatus,
  MutationType,
  EntityType,
} from './types.js';

const QUEUE_KEY = 'mutation_queue';
const MAX_RETRIES = 3;

/**
 * Generate a unique mutation ID
 */
function generateMutationId(): string {
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
  private storage: StorageAdapter;
  private queue: QueuedMutation[] = [];
  private loaded = false;

  constructor(storage: StorageAdapter) {
    this.storage = storage;
  }

  /**
   * Load queue from storage
   */
  async load(): Promise<void> {
    if (this.loaded) return;

    const stored = await this.storage.get<QueuedMutation[]>(QUEUE_KEY);
    this.queue = stored ?? [];
    this.loaded = true;
  }

  /**
   * Save queue to storage
   */
  private async save(): Promise<void> {
    await this.storage.set(QUEUE_KEY, this.queue);
  }

  /**
   * Add a mutation to the queue
   */
  async enqueue(
    entityType: EntityType,
    mutationType: MutationType,
    payload: unknown,
    entityId?: string,
    optimisticId?: string
  ): Promise<QueuedMutation> {
    await this.load();

    const mutation: QueuedMutation = {
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
  async peek(): Promise<QueuedMutation | null> {
    await this.load();
    return this.queue[0] ?? null;
  }

  /**
   * Get all pending mutations
   */
  async getAll(): Promise<QueuedMutation[]> {
    await this.load();
    return [...this.queue];
  }

  /**
   * Remove a mutation from the queue (after successful sync)
   */
  async dequeue(mutationId: string): Promise<void> {
    await this.load();
    this.queue = this.queue.filter(m => m.id !== mutationId);
    await this.save();
  }

  /**
   * Mark a mutation as failed and increment retry count
   */
  async markFailed(mutationId: string, error: string): Promise<boolean> {
    await this.load();

    const mutation = this.queue.find(m => m.id === mutationId);
    if (!mutation) return false;

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
  async remove(mutationId: string): Promise<void> {
    await this.load();
    this.queue = this.queue.filter(m => m.id !== mutationId);
    await this.save();
  }

  /**
   * Clear all mutations
   */
  async clear(): Promise<void> {
    this.queue = [];
    await this.save();
  }

  /**
   * Get queue status
   */
  async getStatus(): Promise<QueueStatus> {
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
  async getForEntity(entityType: EntityType, entityId: string): Promise<QueuedMutation[]> {
    await this.load();
    return this.queue.filter(
      m => m.entityType === entityType && m.entityId === entityId
    );
  }

  /**
   * Check if there are pending mutations for an entity
   */
  async hasPending(entityType: EntityType, entityId: string): Promise<boolean> {
    const mutations = await this.getForEntity(entityType, entityId);
    return mutations.length > 0;
  }

  /**
   * Get count of pending mutations
   */
  async count(): Promise<number> {
    await this.load();
    return this.queue.length;
  }
}
