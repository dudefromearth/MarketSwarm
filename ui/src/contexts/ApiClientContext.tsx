// contexts/ApiClientContext.tsx
// React context for MarketSwarm API client with offline support

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import {
  createClient,
  webAdapter,
  type MarketSwarmClient,
  type SyncState,
  type SyncEvent,
} from '@market-swarm/api-client';

// Context value interface
export interface ApiClientContextValue {
  client: MarketSwarmClient | null;
  isOnline: boolean;
  syncState: SyncState;
  pendingMutations: number;
  lastSyncError: string | null;

  // Manual sync control
  flush: () => Promise<void>;
}

const ApiClientContext = createContext<ApiClientContextValue | null>(null);

interface ApiClientProviderProps {
  children: ReactNode;
  /** Base URL for API (defaults to '' for relative URLs via Vite proxy) */
  baseUrl?: string;
  /** Initial auth token (optional - can be set later) */
  token?: string;
  /** Callback when token is refreshed */
  onTokenRefresh?: (token: string) => void;
  /** Enable offline support (default: true) */
  offlineEnabled?: boolean;
}

export function ApiClientProvider({
  children,
  baseUrl = '',
  token,
  onTokenRefresh,
  offlineEnabled = true,
}: ApiClientProviderProps) {
  const [client, setClient] = useState<MarketSwarmClient | null>(null);
  const [isOnline, setIsOnline] = useState(true);
  const [syncState, setSyncState] = useState<SyncState>({
    status: 'idle',
    pendingCount: 0,
    lastSyncAt: null,
    lastError: null,
  });
  const [lastSyncError, setLastSyncError] = useState<string | null>(null);

  const clientRef = useRef<MarketSwarmClient | null>(null);

  // Initialize client
  useEffect(() => {
    const newClient = createClient(webAdapter, {
      baseUrl,
      token,
      onTokenRefresh,
      offlineEnabled,
    });

    clientRef.current = newClient;
    setClient(newClient);
    setIsOnline(newClient.isOnline());

    // Listen to sync events
    const unsubscribe = newClient.sync.onEvent((event: SyncEvent) => {
      switch (event.type) {
        case 'sync_started':
          setSyncState(prev => ({ ...prev, status: 'syncing' }));
          break;
        case 'sync_completed':
          setSyncState({
            status: 'idle',
            pendingCount: 0,
            lastSyncAt: Date.now(),
            lastError: null,
          });
          setLastSyncError(null);
          break;
        case 'sync_failed':
          setSyncState(prev => ({
            ...prev,
            status: 'error',
            lastError: event.error ?? 'Sync failed',
          }));
          setLastSyncError(event.error ?? 'Sync failed');
          break;
        case 'mutation_queued':
          setSyncState(prev => ({
            ...prev,
            pendingCount: prev.pendingCount + 1,
          }));
          break;
        case 'mutation_completed':
          setSyncState(prev => ({
            ...prev,
            pendingCount: Math.max(0, prev.pendingCount - 1),
          }));
          break;
        case 'mutation_failed':
          // Keep in queue for retry
          break;
        case 'online':
          setIsOnline(true);
          break;
        case 'offline':
          setIsOnline(false);
          break;
      }
    });

    // Listen to browser online/offline events
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      unsubscribe();
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      newClient.destroy();
    };
  }, [baseUrl, token, onTokenRefresh, offlineEnabled]);

  // Update token when it changes
  useEffect(() => {
    if (clientRef.current && token) {
      clientRef.current.auth.setToken(token);
    }
  }, [token]);

  // Manual flush
  const flush = useCallback(async () => {
    if (clientRef.current) {
      await clientRef.current.sync.flush();
    }
  }, []);

  const value: ApiClientContextValue = {
    client,
    isOnline,
    syncState,
    pendingMutations: syncState.pendingCount,
    lastSyncError,
    flush,
  };

  return (
    <ApiClientContext.Provider value={value}>
      {children}
    </ApiClientContext.Provider>
  );
}

// Hook for consuming the context
export function useApiClient(): ApiClientContextValue {
  const context = useContext(ApiClientContext);
  if (!context) {
    throw new Error('useApiClient must be used within an ApiClientProvider');
  }
  return context;
}

// Convenience hook for just the client
export function useMarketSwarmClient(): MarketSwarmClient | null {
  const { client } = useApiClient();
  return client;
}

// Hook for sync status (useful for UI indicators)
export function useSyncStatus() {
  const { isOnline, syncState, pendingMutations, lastSyncError } = useApiClient();

  return {
    isOnline,
    isSyncing: syncState.status === 'syncing',
    hasPendingChanges: pendingMutations > 0,
    pendingCount: pendingMutations,
    lastSyncAt: syncState.lastSyncAt,
    hasError: syncState.status === 'error',
    errorMessage: lastSyncError,
  };
}
