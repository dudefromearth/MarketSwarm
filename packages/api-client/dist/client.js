/**
 * Market Swarm API Client
 *
 * Main client class that provides typed access to all API endpoints
 * with offline support and automatic sync.
 */
import { createStrategiesEndpoint } from './endpoints/strategies.js';
import { createPositionsEndpoint } from './endpoints/positions.js';
import { MutationQueue } from './sync/queue.js';
import { SyncManager } from './sync/manager.js';
/**
 * Create a Market Swarm API client
 */
export function createClient(adapter, options) {
    const { baseUrl, offlineEnabled = true } = options;
    let token = options.token ?? null;
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
    const getHeaders = () => {
        const headers = {
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
    const sseConnections = new Set();
    const createSSESubscription = (path, handler) => {
        const url = `${baseUrl}${path}${token ? `?token=${token}` : ''}`;
        const sseHandler = {
            onMessage: (event) => {
                handler(event);
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
            onEvent(handler) {
                return syncManager.onEvent(handler);
            },
            setConflictHandler(handler) {
                syncManager.setConflictHandler(handler);
            },
            async flush() {
                await syncManager.sync();
            },
        },
        sse: {
            subscribe(handler) {
                return createSSESubscription('/sse', handler);
            },
            subscribeToStrategies(handler) {
                return createSSESubscription('/sse/risk-graph', handler);
            },
            subscribeToPositions(handler) {
                return createSSESubscription('/sse/positions', handler);
            },
        },
        auth: {
            setToken(newToken) {
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
//# sourceMappingURL=client.js.map