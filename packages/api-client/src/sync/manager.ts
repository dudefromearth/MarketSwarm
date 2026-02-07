/**
 * Sync Manager
 *
 * Coordinates syncing queued mutations with the server.
 */

import type { NetworkAdapter } from '../adapters/types.js';
import type {
  SyncState,
  SyncEvent,
  SyncEventHandler,
  ConflictHandler,
  ConflictStrategy,
  QueuedMutation,
} from './types.js';
import { MutationQueue } from './queue.js';

const SYNC_INTERVAL = 5000; // 5 seconds
const RETRY_DELAY = 1000; // 1 second

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
export class SyncManager {
  private baseUrl: string;
  private network: NetworkAdapter;
  private queue: MutationQueue;
  private conflictStrategy: ConflictStrategy;
  private syncInterval: number;
  private getAuthToken?: () => Promise<string | null>;

  private state: SyncState = 'idle';
  private syncTimer: ReturnType<typeof setInterval> | null = null;
  private eventHandlers: Set<SyncEventHandler> = new Set();
  private conflictHandler: ConflictHandler | null = null;
  private unsubscribeOnline: (() => void) | null = null;

  constructor(options: SyncManagerOptions) {
    this.baseUrl = options.baseUrl;
    this.network = options.network;
    this.queue = options.queue;
    this.conflictStrategy = options.conflictStrategy ?? 'server_wins';
    this.syncInterval = options.syncInterval ?? SYNC_INTERVAL;
    this.getAuthToken = options.getAuthToken;
  }

  /**
   * Start sync manager
   */
  start(): void {
    if (this.syncTimer) return;

    // Initial sync if online
    if (this.network.isOnline()) {
      this.sync();
    } else {
      this.state = 'offline';
    }

    // Periodic sync
    this.syncTimer = setInterval(() => {
      if (this.network.isOnline() && this.state !== 'syncing') {
        this.sync();
      }
    }, this.syncInterval);

    // Listen for online/offline changes
    this.unsubscribeOnline = this.network.onOnlineChange((online) => {
      if (online) {
        this.state = 'idle';
        this.sync();
      } else {
        this.state = 'offline';
      }
    });
  }

  /**
   * Stop sync manager
   */
  stop(): void {
    if (this.syncTimer) {
      clearInterval(this.syncTimer);
      this.syncTimer = null;
    }

    if (this.unsubscribeOnline) {
      this.unsubscribeOnline();
      this.unsubscribeOnline = null;
    }
  }

  /**
   * Get current sync state
   */
  getState(): SyncState {
    return this.state;
  }

  /**
   * Subscribe to sync events
   */
  onEvent(handler: SyncEventHandler): () => void {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  /**
   * Set conflict handler
   */
  setConflictHandler(handler: ConflictHandler): void {
    this.conflictHandler = handler;
  }

  /**
   * Emit sync event
   */
  private emit(event: SyncEvent): void {
    for (const handler of this.eventHandlers) {
      try {
        handler(event);
      } catch (e) {
        console.error('Sync event handler error:', e);
      }
    }
  }

  /**
   * Sync all queued mutations
   */
  async sync(): Promise<void> {
    if (this.state === 'syncing') return;
    if (!this.network.isOnline()) {
      this.state = 'offline';
      return;
    }

    this.state = 'syncing';
    this.emit({ type: 'sync_start', timestamp: Date.now() });

    try {
      let mutation = await this.queue.peek();

      while (mutation) {
        const success = await this.syncMutation(mutation);

        if (success) {
          await this.queue.dequeue(mutation.id);
          this.emit({
            type: 'mutation_synced',
            mutation,
            timestamp: Date.now(),
          });
        } else {
          // If failed, markFailed handles retry logic
          const shouldRetry = await this.queue.markFailed(
            mutation.id,
            'Sync failed'
          );

          this.emit({
            type: 'mutation_failed',
            mutation,
            timestamp: Date.now(),
          });

          if (!shouldRetry) {
            // Max retries reached, skip this mutation
            await this.queue.dequeue(mutation.id);
          } else {
            // Wait before retry
            await this.delay(RETRY_DELAY);
          }
        }

        mutation = await this.queue.peek();
      }

      this.state = 'idle';
      this.emit({ type: 'sync_complete', timestamp: Date.now() });
    } catch (error) {
      this.state = 'error';
      this.emit({
        type: 'sync_error',
        error: error instanceof Error ? error : new Error(String(error)),
        timestamp: Date.now(),
      });
    }
  }

  /**
   * Sync a single mutation
   */
  private async syncMutation(mutation: QueuedMutation): Promise<boolean> {
    const endpoint = this.getMutationEndpoint(mutation);
    const method = this.getMutationMethod(mutation);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Add auth token if available
    if (this.getAuthToken) {
      const token = await this.getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    try {
      const response = await this.network.request(endpoint, {
        method,
        headers,
        body: mutation.mutationType !== 'delete' ? mutation.payload : undefined,
      });

      if (response.ok) {
        return true;
      }

      // Handle conflict (409)
      if (response.status === 409) {
        return this.handleConflict(mutation, response.data);
      }

      return false;
    } catch {
      return false;
    }
  }

  /**
   * Get API endpoint for mutation
   */
  private getMutationEndpoint(mutation: QueuedMutation): string {
    const base = `${this.baseUrl}/api/${mutation.entityType}s`;

    switch (mutation.mutationType) {
      case 'create':
        return base;
      case 'update':
      case 'delete':
        return `${base}/${mutation.entityId}`;
    }
  }

  /**
   * Get HTTP method for mutation
   */
  private getMutationMethod(mutation: QueuedMutation): 'POST' | 'PUT' | 'PATCH' | 'DELETE' {
    switch (mutation.mutationType) {
      case 'create':
        return 'POST';
      case 'update':
        return 'PATCH';
      case 'delete':
        return 'DELETE';
    }
  }

  /**
   * Handle conflict
   */
  private async handleConflict(
    mutation: QueuedMutation,
    serverData: unknown
  ): Promise<boolean> {
    // If we have a custom conflict handler, use it
    if (this.conflictHandler) {
      const resolution = await this.conflictHandler({
        entityType: mutation.entityType,
        entityId: mutation.entityId ?? '',
        clientData: mutation.payload,
        serverData,
        mutation,
      });

      if (resolution === 'client') {
        // Retry with force flag
        return this.forceSync(mutation);
      } else if (resolution === 'server') {
        // Accept server version, discard client changes
        return true;
      } else {
        // Merge - implementation depends on entity type
        return false;
      }
    }

    // Default conflict strategy
    switch (this.conflictStrategy) {
      case 'client_wins':
        return this.forceSync(mutation);
      case 'server_wins':
        return true; // Discard client changes
      case 'manual':
        return false; // Keep in queue for manual resolution
    }
  }

  /**
   * Force sync a mutation (override server version)
   */
  private async forceSync(mutation: QueuedMutation): Promise<boolean> {
    const endpoint = `${this.getMutationEndpoint(mutation)}?force=true`;
    const method = this.getMutationMethod(mutation);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.getAuthToken) {
      const token = await this.getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    try {
      const response = await this.network.request(endpoint, {
        method,
        headers,
        body: mutation.mutationType !== 'delete' ? mutation.payload : undefined,
      });

      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Delay helper
   */
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
