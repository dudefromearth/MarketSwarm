// contexts/RiskGraphContext.tsx
// React context for risk graph state management with SSE sync

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  useMemo,
  type ReactNode,
} from 'react';
import type {
  RiskGraphStrategy,
  RiskGraphTemplate,
  RiskGraphStrategyVersion,
  LegacyRiskGraphStrategy,
  RiskGraphSSEEvent,
} from '../types/riskGraph';
import { toLegacyStrategy, fromLegacyStrategy } from '../types/riskGraph';
import * as riskGraphService from '../services/riskGraphService';
import type { RiskGraphSSESubscription } from '../services/riskGraphService';

// Feature flag for migration
const USE_SERVER_RISK_GRAPH = true;

// Local storage keys for fallback
const LS_STRATEGIES_KEY = 'riskGraphStrategies';

// Context value interface
export interface RiskGraphContextValue {
  // State
  strategies: LegacyRiskGraphStrategy[];
  templates: RiskGraphTemplate[];
  connected: boolean;
  loading: boolean;
  error: string | null;

  // Operations
  addStrategy: (strategy: Omit<LegacyRiskGraphStrategy, 'id' | 'addedAt' | 'visible'>) => Promise<LegacyRiskGraphStrategy>;
  removeStrategy: (id: string) => Promise<void>;
  toggleVisibility: (id: string) => Promise<void>;
  updateDebit: (id: string, debit: number | null, reason?: string) => Promise<void>;

  // Queries
  getStrategy: (id: string) => LegacyRiskGraphStrategy | undefined;
  getVisibleStrategies: () => LegacyRiskGraphStrategy[];
  getStrategyVersions: (id: string) => Promise<RiskGraphStrategyVersion[]>;

  // Templates
  loadTemplates: () => Promise<void>;
  useTemplate: (templateId: string, spotPrice: number, debit?: number | null) => Promise<LegacyRiskGraphStrategy>;

  // Bulk
  importStrategies: (strategies: LegacyRiskGraphStrategy[]) => Promise<void>;
  exportStrategies: () => LegacyRiskGraphStrategy[];

  // Migration helper
  migrateFromLocalStorage: () => Promise<void>;
}

const RiskGraphContext = createContext<RiskGraphContextValue | null>(null);

// Load from localStorage
function loadLocalStrategies(): LegacyRiskGraphStrategy[] {
  try {
    const saved = localStorage.getItem(LS_STRATEGIES_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

// Save to localStorage
function saveLocalStrategies(strategies: LegacyRiskGraphStrategy[]): void {
  try {
    localStorage.setItem(LS_STRATEGIES_KEY, JSON.stringify(strategies));
  } catch {}
}

interface RiskGraphProviderProps {
  children: ReactNode;
}

export function RiskGraphProvider({ children }: RiskGraphProviderProps) {
  // Server state
  const [serverStrategies, setServerStrategies] = useState<RiskGraphStrategy[]>([]);
  const [templates, setTemplates] = useState<RiskGraphTemplate[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Local fallback state
  const [localStrategies, setLocalStrategies] = useState<LegacyRiskGraphStrategy[]>(() =>
    loadLocalStrategies()
  );

  // SSE subscription ref
  const sseRef = useRef<RiskGraphSSESubscription | null>(null);

  // Convert server strategies to legacy format
  // Keep showing serverStrategies even when temporarily disconnected
  // (prevents flash-to-empty during SSE reconnects or StrictMode double-mount)
  const strategies = useMemo((): LegacyRiskGraphStrategy[] => {
    if (!USE_SERVER_RISK_GRAPH) {
      return localStrategies;
    }
    if (serverStrategies.length > 0) {
      return serverStrategies.map(toLegacyStrategy);
    }
    return localStrategies;
  }, [serverStrategies, localStrategies]);

  // Fetch initial data from server
  const fetchStrategies = useCallback(async () => {
    console.log('[RiskGraph] fetchStrategies called, USE_SERVER_RISK_GRAPH:', USE_SERVER_RISK_GRAPH);
    if (!USE_SERVER_RISK_GRAPH) return;

    const startTime = performance.now();
    try {
      setLoading(true);
      console.log('[RiskGraph] Starting fetch...');
      const data = await riskGraphService.fetchStrategies();
      console.log('[RiskGraph] Got', data.length, 'strategies in', (performance.now() - startTime).toFixed(0), 'ms');
      setServerStrategies(data);
      setError(null);
    } catch (err) {
      console.error('[RiskGraph] Failed to fetch strategies in', (performance.now() - startTime).toFixed(0), 'ms:', err);
      setError(err instanceof Error ? err.message : 'Failed to load strategies');
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle SSE events
  const handleSSEEvent = useCallback((event: RiskGraphSSEEvent) => {
    switch (event.type) {
      case 'strategy_added':
        setServerStrategies(prev => {
          const newStrategy = event.data as RiskGraphStrategy;
          // Avoid duplicates
          if (prev.some(s => s.id === newStrategy.id)) return prev;
          return [...prev, newStrategy];
        });
        break;

      case 'strategy_updated':
        setServerStrategies(prev =>
          prev.map(s =>
            s.id === (event.data as RiskGraphStrategy).id
              ? (event.data as RiskGraphStrategy)
              : s
          )
        );
        break;

      case 'strategy_removed':
        setServerStrategies(prev =>
          prev.filter(s => s.id !== (event.data as { id: string }).id)
        );
        break;
    }
  }, []);

  // Initialize SSE connection and fetch initial data
  useEffect(() => {
    if (!USE_SERVER_RISK_GRAPH) {
      setLoading(false);
      return;
    }

    // Fetch initial data
    fetchStrategies();

    // Set up SSE subscription
    sseRef.current = riskGraphService.subscribeToRiskGraphStream(
      handleSSEEvent,
      () => { setConnected(true); fetchStrategies(); },
      () => setConnected(false)
    );

    return () => {
      sseRef.current?.close();
    };
  }, [fetchStrategies, handleSSEEvent]);

  // Sync local strategies to localStorage when not using server
  useEffect(() => {
    if (!USE_SERVER_RISK_GRAPH) {
      saveLocalStrategies(localStrategies);
    }
  }, [localStrategies]);

  // Keep localStrategies synced from server as a hot fallback.
  // Without this, SSE disconnect causes strategies memo to return
  // stale/empty localStrategies (cleared after migration).
  useEffect(() => {
    if (USE_SERVER_RISK_GRAPH && connected) {
      const legacy = serverStrategies.map(toLegacyStrategy);
      setLocalStrategies(legacy);
      saveLocalStrategies(legacy);
    }
  }, [serverStrategies, connected]);

  // Operations

  const addStrategy = useCallback(async (
    input: Omit<LegacyRiskGraphStrategy, 'id' | 'addedAt' | 'visible'>
  ): Promise<LegacyRiskGraphStrategy> => {
    const newStrategy: LegacyRiskGraphStrategy = {
      ...input,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      addedAt: Date.now(),
      visible: true,
    };

    if (!USE_SERVER_RISK_GRAPH || !connected) {
      // Local mode
      setLocalStrategies(prev => [...prev, newStrategy]);
      return newStrategy;
    }

    // Server mode — wait for real server ID, then add to state.
    // SSE duplicate check will prevent double-add since IDs match.
    const created = await riskGraphService.createStrategy({
      symbol: input.symbol ?? 'SPX',
      underlying: input.symbol ? `I:${input.symbol}` : 'I:SPX',
      strategy: input.strategy,
      side: input.side,
      strike: input.strike,
      width: input.width || null,
      dte: input.dte,
      expiration: input.expiration,
      debit: input.debit,
      addedAt: newStrategy.addedAt,
    });
    setServerStrategies(prev => {
      if (prev.some(s => s.id === created.id)) return prev;
      return [...prev, created];
    });
    return toLegacyStrategy(created);
  }, [connected]);

  const removeStrategy = useCallback(async (id: string): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH || !connected) {
      setLocalStrategies(prev => prev.filter(s => s.id !== id));
      return;
    }

    // Optimistic removal
    const removed = serverStrategies.find(s => s.id === id);
    setServerStrategies(prev => prev.filter(s => s.id !== id));

    try {
      await riskGraphService.deleteStrategy(id);
    } catch (err) {
      // Rollback on failure
      if (removed) {
        setServerStrategies(prev => [...prev, removed]);
      }
      throw err;
    }
  }, [connected, serverStrategies]);

  const toggleVisibility = useCallback(async (id: string): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH || !connected) {
      setLocalStrategies(prev =>
        prev.map(s => s.id === id ? { ...s, visible: !s.visible } : s)
      );
      return;
    }

    const strategy = serverStrategies.find(s => s.id === id);
    if (!strategy) return;

    // Optimistic update
    const newVisible = !strategy.visible;
    setServerStrategies(prev =>
      prev.map(s => s.id === id ? { ...s, visible: newVisible } : s)
    );

    try {
      await riskGraphService.updateStrategy(id, { visible: newVisible });
    } catch (err) {
      // Rollback
      setServerStrategies(prev =>
        prev.map(s => s.id === id ? { ...s, visible: strategy.visible } : s)
      );
      throw err;
    }
  }, [connected, serverStrategies]);

  const updateDebit = useCallback(async (
    id: string,
    debit: number | null,
    reason?: string
  ): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH || !connected) {
      setLocalStrategies(prev =>
        prev.map(s => s.id === id ? { ...s, debit } : s)
      );
      return;
    }

    const strategy = serverStrategies.find(s => s.id === id);
    if (!strategy) return;

    // Optimistic update
    const oldDebit = strategy.debit;
    setServerStrategies(prev =>
      prev.map(s => s.id === id ? { ...s, debit } : s)
    );

    try {
      await riskGraphService.updateStrategy(id, { debit, changeReason: reason });
    } catch (err) {
      // Rollback
      setServerStrategies(prev =>
        prev.map(s => s.id === id ? { ...s, debit: oldDebit } : s)
      );
      throw err;
    }
  }, [connected, serverStrategies]);

  // Queries

  const getStrategy = useCallback((id: string): LegacyRiskGraphStrategy | undefined => {
    return strategies.find(s => s.id === id);
  }, [strategies]);

  const getVisibleStrategies = useCallback((): LegacyRiskGraphStrategy[] => {
    return strategies.filter(s => s.visible);
  }, [strategies]);

  const getStrategyVersions = useCallback(async (
    id: string
  ): Promise<RiskGraphStrategyVersion[]> => {
    if (!USE_SERVER_RISK_GRAPH) return [];
    return riskGraphService.fetchStrategyVersions(id);
  }, []);

  // Templates

  const loadTemplates = useCallback(async (): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH) return;
    try {
      const data = await riskGraphService.fetchTemplates(true);
      setTemplates(data);
    } catch (err) {
      console.error('[RiskGraph] Failed to load templates:', err);
    }
  }, []);

  const useTemplateFunc = useCallback(async (
    templateId: string,
    spotPrice: number,
    debit?: number | null
  ): Promise<LegacyRiskGraphStrategy> => {
    if (!USE_SERVER_RISK_GRAPH) {
      throw new Error('Templates require server mode');
    }
    const created = await riskGraphService.useTemplate(templateId, {
      spotPrice,
      debit,
    });
    // SSE will update, but also update locally for responsiveness
    setServerStrategies(prev => [...prev, created]);
    return toLegacyStrategy(created);
  }, []);

  // Bulk operations

  const importStrategiesFunc = useCallback(async (
    strategiesToImport: LegacyRiskGraphStrategy[]
  ): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH || !connected) {
      setLocalStrategies(prev => [...prev, ...strategiesToImport]);
      return;
    }

    const inputs = strategiesToImport.map(s => fromLegacyStrategy(s, 0));
    const imported = await riskGraphService.importStrategies(inputs);
    setServerStrategies(prev => [...prev, ...imported]);
  }, [connected]);

  const exportStrategiesFunc = useCallback((): LegacyRiskGraphStrategy[] => {
    return strategies;
  }, [strategies]);

  // Migration helper - moves localStorage data to server
  const migrateFromLocalStorage = useCallback(async (): Promise<void> => {
    if (!USE_SERVER_RISK_GRAPH || !connected) return;

    const local = loadLocalStrategies();
    if (local.length === 0) return;

    try {
      await importStrategiesFunc(local);
      // Clear localStorage after successful migration
      localStorage.removeItem(LS_STRATEGIES_KEY);
      console.log(`[RiskGraph] Migrated ${local.length} strategies from localStorage`);
    } catch (err) {
      console.error('[RiskGraph] Migration failed:', err);
    }
  }, [connected, importStrategiesFunc]);

  const value: RiskGraphContextValue = {
    strategies,
    templates,
    connected,
    loading,
    error,
    addStrategy,
    removeStrategy,
    toggleVisibility,
    updateDebit,
    getStrategy,
    getVisibleStrategies,
    getStrategyVersions,
    loadTemplates,
    useTemplate: useTemplateFunc,
    importStrategies: importStrategiesFunc,
    exportStrategies: exportStrategiesFunc,
    migrateFromLocalStorage,
  };

  return (
    <RiskGraphContext.Provider value={value}>
      {children}
    </RiskGraphContext.Provider>
  );
}

// Hook for consuming the context
export function useRiskGraph(): RiskGraphContextValue {
  const context = useContext(RiskGraphContext);
  if (!context) {
    throw new Error('useRiskGraph must be used within a RiskGraphProvider');
  }
  return context;
}

// Export for backward compatibility check
export { USE_SERVER_RISK_GRAPH };
