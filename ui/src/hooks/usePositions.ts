// hooks/usePositions.ts
// React hook for position management with offline support
//
// Uses @market-swarm/api-client for:
// - Optimistic updates (instant UI response)
// - Offline mutation queue (changes persist and sync when online)
// - Real-time SSE sync (multi-device/tab updates)

import { useState, useEffect, useCallback, useRef } from 'react';
import { useApiClient } from '../contexts/ApiClientContext';
import type {
  Position,
  PositionLeg,
  PositionType,
  PositionDirection,
  CostBasisType,
} from '@market-swarm/core';
import type { SSEEvent, SSEConnection } from '@market-swarm/api-client';

// Re-export types for consumers
export type { Position, PositionLeg, PositionType, PositionDirection, CostBasisType };

// Input for creating a new position
export interface CreatePositionInput {
  symbol?: string;
  positionType: PositionType;
  direction: PositionDirection;
  legs: PositionLeg[];
  costBasis?: number | null;
  costBasisType?: CostBasisType;
  visible?: boolean;
  color?: string | null;
  label?: string | null;
}

// Input for updating a position
export interface UpdatePositionInput {
  symbol?: string;
  positionType?: PositionType;
  direction?: PositionDirection;
  legs?: PositionLeg[];
  costBasis?: number | null;
  costBasisType?: CostBasisType;
  visible?: boolean;
  sortOrder?: number;
  color?: string | null;
  label?: string | null;
}

// Hook state
export interface UsePositionsState {
  positions: Position[];
  loading: boolean;
  error: string | null;
  connected: boolean;
}

// Hook return value
export interface UsePositionsResult extends UsePositionsState {
  // CRUD operations
  addPosition: (input: CreatePositionInput) => Promise<Position>;
  updatePosition: (id: string, input: UpdatePositionInput) => Promise<Position>;
  removePosition: (id: string) => Promise<void>;

  // Convenience operations
  toggleVisibility: (id: string) => Promise<void>;
  updateCostBasis: (id: string, costBasis: number | null, type?: CostBasisType) => Promise<void>;
  reorder: (order: Array<{ id: string; sortOrder: number }>) => Promise<void>;

  // Queries
  getPosition: (id: string) => Position | undefined;
  getVisiblePositions: () => Position[];

  // Batch operations
  importPositions: (positions: CreatePositionInput[]) => Promise<number>;

  // Refresh
  refresh: () => Promise<void>;
}

export function usePositions(): UsePositionsResult {
  const { client, isOnline } = useApiClient();

  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  const sseConnectionRef = useRef<SSEConnection | null>(null);

  // Debug: log whenever positions changes
  useEffect(() => {
    console.log('[usePositions] positions state changed:', positions.length, 'positions', positions.map(p => p.id));
  }, [positions]);

  // Fetch positions from server
  const fetchPositions = useCallback(async () => {
    if (!client) return;

    console.log('[usePositions] fetchPositions called');
    console.trace('[usePositions] fetchPositions stack trace');

    try {
      setLoading(true);
      const response = await client.positions.list();
      console.log('[usePositions] fetchPositions response:', response);
      if (response.success && response.data) {
        console.log('[usePositions] fetchPositions setting positions:', response.data.length);
        setPositions(response.data);
        setError(null);
      } else {
        console.error('[usePositions] fetchPositions error:', response.error);
        setError(response.error ?? 'Failed to fetch positions');
      }
    } catch (err) {
      console.error('[usePositions] fetchPositions exception:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch positions');
    } finally {
      setLoading(false);
    }
  }, [client]);

  // Handle SSE events for real-time sync
  const handleSSEEvent = useCallback((event: SSEEvent) => {
    // SSE event has { type, data } structure - extract the data payload
    const payload = (event as { type: string; data: unknown }).data;
    const data = payload as {
      action?: string;
      position?: Position;
      ids?: string[];
      order?: Array<{ id: string; sortOrder: number }>;
    };

    switch (data.action) {
      case 'created':
        if (data.position) {
          setPositions(prev => {
            // Avoid duplicates
            if (prev.some(p => p.id === data.position!.id)) return prev;
            return [...prev, data.position!];
          });
        }
        break;

      case 'updated':
        if (data.position) {
          setPositions(prev =>
            prev.map(p => p.id === data.position!.id ? data.position! : p)
          );
        }
        break;

      case 'deleted':
        if (data.position?.id) {
          setPositions(prev => prev.filter(p => p.id !== data.position!.id));
        }
        break;

      case 'batch_created':
        // Refresh to get all new positions
        fetchPositions();
        break;

      case 'reordered':
        if (data.order) {
          setPositions(prev => {
            const orderMap = new Map(data.order!.map(o => [o.id, o.sortOrder]));
            return prev
              .map(p => ({
                ...p,
                sortOrder: orderMap.get(p.id) ?? p.sortOrder,
              }))
              .sort((a, b) => a.sortOrder - b.sortOrder);
          });
        }
        break;
    }
  }, [fetchPositions]);

  // Initialize: fetch data and connect SSE
  useEffect(() => {
    if (!client) return;

    console.log('[usePositions] Init effect running - fetching positions and connecting SSE');

    fetchPositions();

    // Subscribe to position updates via SSE
    sseConnectionRef.current = client.sse.subscribeToPositions(handleSSEEvent);
    setConnected(true);

    return () => {
      console.log('[usePositions] Init effect cleanup - closing SSE');
      sseConnectionRef.current?.close();
      setConnected(false);
    };
  }, [client, fetchPositions, handleSSEEvent]);

  // CRUD Operations with optimistic updates

  const addPosition = useCallback(async (input: CreatePositionInput): Promise<Position> => {
    if (!client) throw new Error('Client not initialized');

    console.log('[usePositions] addPosition called with:', input);

    // Create optimistic position
    const optimisticId = `optimistic_${Date.now()}`;
    const optimisticPosition: Position = {
      id: optimisticId,
      userId: 0,
      symbol: input.symbol ?? 'SPX',
      positionType: input.positionType,
      direction: input.direction,
      legs: input.legs,
      primaryExpiration: input.legs[0]?.expiration ?? new Date().toISOString().split('T')[0],
      dte: (() => {
        const exp = input.legs[0]?.expiration;
        if (!exp) return 0;
        const expClose = new Date(exp + 'T16:00:00-05:00');
        return Math.max(0, Math.ceil((expClose.getTime() - Date.now()) / (1000 * 60 * 60 * 24)));
      })(),
      costBasis: input.costBasis ?? null,
      costBasisType: input.costBasisType ?? 'debit',
      visible: input.visible ?? true,
      sortOrder: positions.length,
      color: input.color ?? null,
      label: input.label ?? null,
      addedAt: Date.now(),
      version: 1,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    console.log('[usePositions] Optimistic position:', optimisticPosition);

    // Optimistic update
    setPositions(prev => [...prev, optimisticPosition]);

    try {
      console.log('[usePositions] Calling API to create position...');
      const response = await client.positions.create({
        symbol: input.symbol ?? 'SPX',
        positionType: input.positionType,
        direction: input.direction,
        legs: input.legs,
        costBasis: input.costBasis,
        costBasisType: input.costBasisType,
        visible: input.visible,
        color: input.color,
        label: input.label,
      });

      console.log('[usePositions] API response:', response);

      if (!response.success || !response.data) {
        console.error('[usePositions] API error:', response.error);
        throw new Error(response.error ?? 'Failed to create position');
      }

      console.log('[usePositions] Position created successfully:', response.data);

      // Replace optimistic with real
      setPositions(prev =>
        prev.map(p => p.id === optimisticId ? response.data! : p)
      );

      return response.data;
    } catch (err) {
      console.error('[usePositions] Error creating position:', err);
      // Rollback optimistic update
      setPositions(prev => prev.filter(p => p.id !== optimisticId));
      throw err;
    }
  }, [client, positions.length]);

  const updatePosition = useCallback(async (
    id: string,
    input: UpdatePositionInput
  ): Promise<Position> => {
    if (!client) throw new Error('Client not initialized');

    const current = positions.find(p => p.id === id);
    if (!current) throw new Error('Position not found');

    // Optimistic update
    const optimisticUpdate: Position = { ...current, ...input };
    setPositions(prev => prev.map(p => p.id === id ? optimisticUpdate : p));

    try {
      const response = await client.positions.update(id, input);

      if (!response.success || !response.data) {
        throw new Error(response.error ?? 'Failed to update position');
      }

      // Replace with server response
      setPositions(prev => prev.map(p => p.id === id ? response.data! : p));
      return response.data;
    } catch (err) {
      // Rollback
      setPositions(prev => prev.map(p => p.id === id ? current : p));
      throw err;
    }
  }, [client, positions]);

  const removePosition = useCallback(async (id: string): Promise<void> => {
    if (!client) throw new Error('Client not initialized');

    const current = positions.find(p => p.id === id);
    if (!current) return;

    // Optimistic removal
    setPositions(prev => prev.filter(p => p.id !== id));

    try {
      const response = await client.positions.delete(id);
      if (!response.success) {
        throw new Error(response.error ?? 'Failed to delete position');
      }
    } catch (err) {
      // Rollback
      setPositions(prev => [...prev, current]);
      throw err;
    }
  }, [client, positions]);

  // Convenience operations

  const toggleVisibility = useCallback(async (id: string): Promise<void> => {
    const current = positions.find(p => p.id === id);
    if (!current) return;
    await updatePosition(id, { visible: !current.visible });
  }, [positions, updatePosition]);

  const updateCostBasis = useCallback(async (
    id: string,
    costBasis: number | null,
    type?: CostBasisType
  ): Promise<void> => {
    await updatePosition(id, {
      costBasis,
      costBasisType: type,
    });
  }, [updatePosition]);

  const reorder = useCallback(async (
    order: Array<{ id: string; sortOrder: number }>
  ): Promise<void> => {
    if (!client) throw new Error('Client not initialized');

    // Optimistic reorder
    const orderMap = new Map(order.map(o => [o.id, o.sortOrder]));
    setPositions(prev =>
      prev
        .map(p => ({ ...p, sortOrder: orderMap.get(p.id) ?? p.sortOrder }))
        .sort((a, b) => a.sortOrder - b.sortOrder)
    );

    try {
      await client.positions.reorder(order);
    } catch (err) {
      // Refresh to get correct order
      await fetchPositions();
      throw err;
    }
  }, [client, fetchPositions]);

  // Queries

  const getPosition = useCallback((id: string): Position | undefined => {
    return positions.find(p => p.id === id);
  }, [positions]);

  const getVisiblePositions = useCallback((): Position[] => {
    return positions.filter(p => p.visible);
  }, [positions]);

  // Batch operations

  const importPositions = useCallback(async (
    inputs: CreatePositionInput[]
  ): Promise<number> => {
    if (!client) throw new Error('Client not initialized');

    const response = await client.positions.createBatch(
      inputs.map(input => ({
        symbol: input.symbol ?? 'SPX',
        positionType: input.positionType,
        direction: input.direction,
        legs: input.legs,
        costBasis: input.costBasis,
        costBasisType: input.costBasisType,
        visible: input.visible,
        color: input.color,
        label: input.label,
      }))
    );

    if (!response.success) {
      throw new Error(response.error ?? 'Failed to import positions');
    }

    // Refresh to get imported positions
    await fetchPositions();
    return response.data?.created ?? 0;
  }, [client, fetchPositions]);

  // Refresh

  const refresh = useCallback(async (): Promise<void> => {
    await fetchPositions();
  }, [fetchPositions]);

  return {
    // State
    positions,
    loading,
    error,
    connected,

    // CRUD
    addPosition,
    updatePosition,
    removePosition,

    // Convenience
    toggleVisibility,
    updateCostBasis,
    reorder,

    // Queries
    getPosition,
    getVisiblePositions,

    // Batch
    importPositions,

    // Refresh
    refresh,
  };
}
