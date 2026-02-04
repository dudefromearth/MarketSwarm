// ui/src/hooks/useTradeSelector.ts
// State management hook for Trade Selector

import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  TradeSelectorModel,
  TradeRecommendation,
  TileScore,
} from '../types/tradeSelector';

const SSE_BASE = ''; // Use relative URLs - Vite proxy handles /api/* and /sse/*

// Throttle updates to prevent UI flashing (max 1 update per 3 seconds)
const UPDATE_THROTTLE_MS = 3000;

// Check if recommendations have meaningfully changed
function hasRecommendationsChanged(
  prev: TradeRecommendation[] | undefined,
  next: TradeRecommendation[] | undefined
): boolean {
  if (!prev || !next) return true;
  if (prev.length !== next.length) return true;

  // Compare top 5 recommendations by tile_key and score
  const topN = Math.min(5, prev.length, next.length);
  for (let i = 0; i < topN; i++) {
    if (prev[i].tile_key !== next[i].tile_key) return true;
    if (Math.abs(prev[i].score.composite - next[i].score.composite) > 2) return true;
  }

  return false;
}

interface UseTradeSelectorOptions {
  symbol: string;
  enabled?: boolean;
}

interface UseTradeSelectorReturn {
  model: TradeSelectorModel | null;
  recommendations: TradeRecommendation[];
  loading: boolean;
  error: string | null;
  getScoreForTile: (tileKey: string) => TileScore | null;
  refresh: () => Promise<void>;
}

export function useTradeSelector({
  symbol,
  enabled = true,
}: UseTradeSelectorOptions): UseTradeSelectorReturn {
  const [model, setModel] = useState<TradeSelectorModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial data via REST
  const fetchInitial = useCallback(async () => {
    if (!enabled) return;

    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${SSE_BASE}/api/models/trade_selector/${symbol}`);
      if (!response.ok) {
        if (response.status === 404) {
          // No data yet - this is normal during startup
          setModel(null);
          return;
        }
        throw new Error(`Failed to fetch: ${response.status}`);
      }

      const result = await response.json();
      if (result.success && result.data) {
        setModel(result.data);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      console.error('[useTradeSelector] Fetch error:', message);
    } finally {
      setLoading(false);
    }
  }, [symbol, enabled]);

  // Initial fetch
  useEffect(() => {
    fetchInitial();
  }, [fetchInitial]);

  // Track last update time for throttling
  const lastUpdateRef = useRef<number>(0);
  const pendingUpdateRef = useRef<TradeSelectorModel | null>(null);
  const throttleTimeoutRef = useRef<number | null>(null);

  // Listen for SSE updates via window events (throttled)
  useEffect(() => {
    if (!enabled) return;

    const handleTradeSelectorUpdate = (e: CustomEvent) => {
      const data = e.detail as TradeSelectorModel;
      if (data.symbol !== symbol) return;

      const now = Date.now();
      const timeSinceLastUpdate = now - lastUpdateRef.current;

      // Check if update is meaningful (recommendations changed)
      const shouldUpdate = hasRecommendationsChanged(model?.recommendations, data.recommendations);

      if (!shouldUpdate) {
        // Data hasn't meaningfully changed, skip update
        return;
      }

      if (timeSinceLastUpdate >= UPDATE_THROTTLE_MS) {
        // Enough time has passed, update immediately
        lastUpdateRef.current = now;
        setModel(data);
        setError(null);
      } else {
        // Throttle: store pending update
        pendingUpdateRef.current = data;

        // Clear any existing timeout before scheduling new one
        if (throttleTimeoutRef.current) {
          clearTimeout(throttleTimeoutRef.current);
        }

        // Schedule update for when throttle period ends
        const delay = UPDATE_THROTTLE_MS - timeSinceLastUpdate;
        throttleTimeoutRef.current = window.setTimeout(() => {
          if (pendingUpdateRef.current) {
            lastUpdateRef.current = Date.now();
            setModel(pendingUpdateRef.current);
            setError(null);
            pendingUpdateRef.current = null;
          }
          throttleTimeoutRef.current = null;
        }, delay);
      }
    };

    window.addEventListener('trade-selector-update', handleTradeSelectorUpdate as EventListener);

    return () => {
      window.removeEventListener('trade-selector-update', handleTradeSelectorUpdate as EventListener);
      if (throttleTimeoutRef.current) {
        clearTimeout(throttleTimeoutRef.current);
        throttleTimeoutRef.current = null;
      }
    };
  }, [symbol, enabled, model?.recommendations]);

  // Get score for a specific tile key
  const getScoreForTile = useCallback((tileKey: string): TileScore | null => {
    if (!model?.scores) return null;
    return model.scores[tileKey] || null;
  }, [model]);

  return {
    model,
    recommendations: model?.recommendations || [],
    loading,
    error,
    getScoreForTile,
    refresh: fetchInitial,
  };
}

export default useTradeSelector;
