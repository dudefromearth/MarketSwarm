// contexts/TradeLogContext.tsx
// React context for trade log state management with SSE sync
//
// This context is a CLIENT, not the system of record.
// - Cache server state
// - Apply optimistic updates
// - Reconcile via version
// - Subscribe to SSE

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
  Position,
  PositionSnapshot,
  PendingOrder,
  JournalEntry,
  LegacyTrade,
  LegacyOrder,
  TradeLogEvent,
  CreatePositionInput,
  UpdatePositionInput,
  RecordFillInput,
  CreateOrderInput,
  CreateJournalEntryInput,
} from '../types/tradeLog';
import { toLegacyOrder } from '../types/tradeLog';
import * as tradeLogService from '../services/tradeLogService';
import type { TradeLogSSESubscription } from '../services/tradeLogService';

// =============================================================================
// Feature Flags
// =============================================================================

// Use new normalized position API (Phase 2+)
const USE_POSITION_API = false;

// Use SSE for real-time sync (Phase 2+)
const USE_SSE_SYNC = false;

// =============================================================================
// Context Interface
// =============================================================================

export interface TradeLogContextValue {
  // State (cached from server)
  positions: Position[];
  pendingOrders: LegacyOrder[];
  loading: boolean;
  connected: boolean;
  lastEventSeq: number;
  error: string | null;

  // Legacy state (during migration)
  trades: LegacyTrade[];
  openTrades: LegacyTrade[];
  closedTrades: LegacyTrade[];

  // Position Operations (new API)
  refreshPositions: () => Promise<void>;
  createPosition: (input: CreatePositionInput) => Promise<Position>;
  updatePosition: (id: string, updates: UpdatePositionInput) => Promise<void>;
  recordFill: (positionId: string, fill: RecordFillInput) => Promise<void>;
  closePosition: (id: string) => Promise<void>;
  getPositionSnapshot: (id: string) => Promise<PositionSnapshot>;

  // Order Operations
  refreshOrders: () => Promise<void>;
  createOrder: (input: CreateOrderInput) => Promise<PendingOrder>;
  cancelOrder: (id: number) => Promise<void>;
  executeOrder: (id: number) => Promise<Position>;
  getPendingOrderCount: () => number;

  // Journal Operations
  addJournalEntry: (input: CreateJournalEntryInput) => Promise<JournalEntry>;
  getJournalEntries: (positionId: string) => Promise<JournalEntry[]>;

  // Legacy Operations (during migration)
  refreshTrades: () => Promise<void>;
  closeTrade: (tradeId: string, exitPrice: number, exitSpot?: number) => Promise<void>;

  // Queries (derived from cached state)
  getOpenPositions: () => Position[];
  getClosedPositions: () => Position[];
  getPositionById: (id: string) => Position | undefined;
}

// =============================================================================
// Context Creation
// =============================================================================

const TradeLogContext = createContext<TradeLogContextValue | null>(null);

// =============================================================================
// Provider Component
// =============================================================================

interface TradeLogProviderProps {
  children: ReactNode;
}

export function TradeLogProvider({ children }: TradeLogProviderProps) {
  // Server state (new normalized model)
  const [positions, setPositions] = useState<Position[]>([]);

  // Legacy state (flattened trades)
  const [trades, setTrades] = useState<LegacyTrade[]>([]);

  // Orders
  const [pendingOrders, setPendingOrders] = useState<LegacyOrder[]>([]);

  // Connection state
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastEventSeq, setLastEventSeq] = useState(0);

  // SSE subscription ref
  const sseRef = useRef<TradeLogSSESubscription | null>(null);

  // Version tracking for optimistic concurrency
  const positionVersions = useRef<Map<string, number>>(new Map());

  // =============================================================================
  // Derived State
  // =============================================================================

  const openTrades = useMemo(
    () => trades.filter(t => t.status === 'open'),
    [trades]
  );

  const closedTrades = useMemo(
    () => trades.filter(t => t.status === 'closed'),
    [trades]
  );

  // =============================================================================
  // Data Fetching
  // =============================================================================

  const refreshPositions = useCallback(async () => {
    if (!USE_POSITION_API) return;

    try {
      const data = await tradeLogService.fetchPositions();
      setPositions(data);
      // Update version cache
      for (const p of data) {
        positionVersions.current.set(p.id, p.version);
      }
      setError(null);
    } catch (err) {
      console.error('[TradeLog] Failed to fetch positions:', err);
      setError(err instanceof Error ? err.message : 'Failed to load positions');
    }
  }, []);

  const refreshTrades = useCallback(async () => {
    console.log('[TradeLogContext] refreshTrades called');
    const startTime = performance.now();
    try {
      setLoading(true);
      const data = await tradeLogService.fetchLegacyTrades();
      console.log('[TradeLogContext] Got', data.length, 'trades in', (performance.now() - startTime).toFixed(0), 'ms');
      setTrades(data);
      setError(null);
    } catch (err) {
      console.error('[TradeLogContext] Failed to fetch trades in', (performance.now() - startTime).toFixed(0), 'ms:', err);
      setError(err instanceof Error ? err.message : 'Failed to load trades');
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshOrders = useCallback(async () => {
    try {
      const data = await tradeLogService.fetchLegacyOrders();
      setPendingOrders(data);
    } catch (err) {
      console.error('[TradeLog] Failed to fetch orders:', err);
    }
  }, []);

  // =============================================================================
  // SSE Event Handling
  // =============================================================================

  const handleSSEEvent = useCallback((event: TradeLogEvent) => {
    // Update sequence tracking
    setLastEventSeq(event.eventSeq);

    // Deduplicate by event_id (could use Set for seen events)

    switch (event.type) {
      case 'PositionCreated':
        setPositions(prev => {
          const newPosition = event.payload as Position;
          if (prev.some(p => p.id === newPosition.id)) return prev;
          positionVersions.current.set(newPosition.id, newPosition.version);
          return [...prev, newPosition];
        });
        break;

      case 'PositionAdjusted':
      case 'FillRecorded':
        setPositions(prev =>
          prev.map(p => {
            if (p.id !== event.aggregateId) return p;
            // Only update if version is newer
            const currentVersion = positionVersions.current.get(p.id) || 0;
            if (event.aggregateVersion <= currentVersion) return p;
            const updated = event.payload as Position;
            positionVersions.current.set(updated.id, updated.version);
            return updated;
          })
        );
        break;

      case 'PositionClosed':
        setPositions(prev =>
          prev.map(p =>
            p.id === event.aggregateId
              ? { ...p, status: 'closed' as const, closedAt: event.occurredAt }
              : p
          )
        );
        break;

      case 'OrderCreated':
        // Refresh orders to get the new one
        refreshOrders();
        break;

      case 'OrderCancelled':
      case 'OrderFilled':
        setPendingOrders(prev =>
          prev.filter(o => String(o.id) !== event.aggregateId)
        );
        if (event.type === 'OrderFilled') {
          refreshPositions();
        }
        break;
    }
  }, [refreshOrders, refreshPositions]);

  // =============================================================================
  // Initialization
  // =============================================================================

  useEffect(() => {
    // Initial data fetch
    const init = async () => {
      setLoading(true);
      await Promise.all([
        refreshTrades(),
        refreshOrders(),
        USE_POSITION_API && refreshPositions(),
      ]);
      setLoading(false);
    };

    init();

    // Set up SSE subscription if enabled
    if (USE_SSE_SYNC) {
      sseRef.current = tradeLogService.subscribeToTradeLogStream(
        handleSSEEvent,
        () => setConnected(true),
        () => setConnected(false),
        lastEventSeq
      );
    }

    return () => {
      sseRef.current?.close();
    };
  }, [refreshTrades, refreshOrders, refreshPositions, handleSSEEvent, lastEventSeq]);

  // =============================================================================
  // Position Operations
  // =============================================================================

  const createPosition = useCallback(async (
    input: CreatePositionInput
  ): Promise<Position> => {
    const created = await tradeLogService.createPosition(input);
    positionVersions.current.set(created.id, created.version);
    setPositions(prev => [...prev, created]);
    return created;
  }, []);

  const updatePosition = useCallback(async (
    id: string,
    updates: UpdatePositionInput
  ): Promise<void> => {
    const version = positionVersions.current.get(id);
    if (version === undefined) {
      throw new Error('Position not in cache - refresh first');
    }

    // Optimistic update
    const oldPosition = positions.find(p => p.id === id);
    setPositions(prev =>
      prev.map(p => p.id === id ? { ...p, ...updates } : p)
    );

    try {
      const updated = await tradeLogService.updatePosition(id, updates, version);
      positionVersions.current.set(id, updated.version);
      setPositions(prev =>
        prev.map(p => p.id === id ? updated : p)
      );
    } catch (err) {
      // Rollback on failure
      if (oldPosition) {
        setPositions(prev =>
          prev.map(p => p.id === id ? oldPosition : p)
        );
      }
      throw err;
    }
  }, [positions]);

  const recordFill = useCallback(async (
    positionId: string,
    fill: RecordFillInput
  ): Promise<void> => {
    const updated = await tradeLogService.recordFill(positionId, fill);
    positionVersions.current.set(updated.id, updated.version);
    setPositions(prev =>
      prev.map(p => p.id === positionId ? updated : p)
    );
  }, []);

  const closePositionFn = useCallback(async (id: string): Promise<void> => {
    const version = positionVersions.current.get(id);
    if (version === undefined) {
      throw new Error('Position not in cache - refresh first');
    }

    const closed = await tradeLogService.closePosition(id, version);
    positionVersions.current.set(id, closed.version);
    setPositions(prev =>
      prev.map(p => p.id === id ? closed : p)
    );
  }, []);

  const getPositionSnapshot = useCallback(async (
    id: string
  ): Promise<PositionSnapshot> => {
    return tradeLogService.fetchPositionSnapshot(id);
  }, []);

  // =============================================================================
  // Order Operations
  // =============================================================================

  const createOrderFn = useCallback(async (
    input: CreateOrderInput
  ): Promise<PendingOrder> => {
    const created = await tradeLogService.createOrder(input);
    setPendingOrders(prev => [...prev, toLegacyOrder(created)]);
    return created;
  }, []);

  const cancelOrderFn = useCallback(async (id: number): Promise<void> => {
    // Optimistic removal
    const removed = pendingOrders.find(o => o.id === id);
    setPendingOrders(prev => prev.filter(o => o.id !== id));

    try {
      await tradeLogService.cancelLegacyOrder(id);
    } catch (err) {
      // Rollback
      if (removed) {
        setPendingOrders(prev => [...prev, removed]);
      }
      throw err;
    }
  }, [pendingOrders]);

  const executeOrderFn = useCallback(async (id: number): Promise<Position> => {
    const position = await tradeLogService.executeOrder(id);
    setPendingOrders(prev => prev.filter(o => o.id !== id));
    if (USE_POSITION_API) {
      setPositions(prev => [...prev, position]);
      positionVersions.current.set(position.id, position.version);
    }
    // Also refresh legacy trades
    await refreshTrades();
    return position;
  }, [refreshTrades]);

  // =============================================================================
  // Legacy Operations
  // =============================================================================

  const closeTrade = useCallback(async (
    tradeId: string,
    exitPrice: number,
    exitSpot?: number
  ): Promise<void> => {
    const closed = await tradeLogService.closeLegacyTrade(tradeId, exitPrice, exitSpot);
    setTrades(prev =>
      prev.map(t => t.id === tradeId ? closed : t)
    );
  }, []);

  // =============================================================================
  // Journal Operations
  // =============================================================================

  const addJournalEntry = useCallback(async (
    input: CreateJournalEntryInput
  ): Promise<JournalEntry> => {
    return tradeLogService.createJournalEntry(input);
  }, []);

  const getJournalEntries = useCallback(async (
    positionId: string
  ): Promise<JournalEntry[]> => {
    return tradeLogService.fetchJournalEntries(positionId);
  }, []);

  // =============================================================================
  // Query Functions
  // =============================================================================

  const getOpenPositions = useCallback((): Position[] => {
    return positions.filter(p => p.status === 'open');
  }, [positions]);

  const getClosedPositions = useCallback((): Position[] => {
    return positions.filter(p => p.status === 'closed');
  }, [positions]);

  const getPositionById = useCallback((id: string): Position | undefined => {
    return positions.find(p => p.id === id);
  }, [positions]);

  const getPendingOrderCount = useCallback((): number => {
    return pendingOrders.length;
  }, [pendingOrders]);

  // =============================================================================
  // Context Value
  // =============================================================================

  const value: TradeLogContextValue = {
    // State
    positions,
    pendingOrders,
    loading,
    connected,
    lastEventSeq,
    error,

    // Legacy state
    trades,
    openTrades,
    closedTrades,

    // Position Operations
    refreshPositions,
    createPosition,
    updatePosition,
    recordFill,
    closePosition: closePositionFn,
    getPositionSnapshot,

    // Order Operations
    refreshOrders,
    createOrder: createOrderFn,
    cancelOrder: cancelOrderFn,
    executeOrder: executeOrderFn,
    getPendingOrderCount,

    // Journal Operations
    addJournalEntry,
    getJournalEntries,

    // Legacy Operations
    refreshTrades,
    closeTrade,

    // Queries
    getOpenPositions,
    getClosedPositions,
    getPositionById,
  };

  return (
    <TradeLogContext.Provider value={value}>
      {children}
    </TradeLogContext.Provider>
  );
}

// =============================================================================
// Hook
// =============================================================================

export function useTradeLog(): TradeLogContextValue {
  const context = useContext(TradeLogContext);
  if (!context) {
    throw new Error('useTradeLog must be used within a TradeLogProvider');
  }
  return context;
}
