/**
 * useMEL - React hook for MEL (Model Effectiveness Layer) data.
 *
 * Connects to the Copilot service via WebSocket for real-time MEL updates.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const COPILOT_BASE = 'http://localhost:8095';
const COPILOT_WS = 'ws://localhost:8095/ws/mel';

export type ModelState = 'VALID' | 'DEGRADED' | 'REVOKED';
export type CoherenceState = 'STABLE' | 'MIXED' | 'COLLAPSING' | 'RECOVERED';
export type Trend = 'improving' | 'stable' | 'degrading';

export interface MELModelScore {
  effectiveness: number;
  trend: Trend;
  state: ModelState;
  confidence: 'high' | 'medium' | 'low';
  detail: Record<string, unknown>;
}

export interface MELSnapshot {
  timestamp_utc: string;
  snapshot_id: string;
  session: 'RTH' | 'ETH' | 'GLOBEX';
  event_flags: string[];
  gamma: MELModelScore;
  volume_profile: MELModelScore;
  liquidity: MELModelScore;
  volatility: MELModelScore;
  session_structure: MELModelScore;
  cross_model_coherence: number;
  coherence_state: CoherenceState;
  global_structure_integrity: number;
  delta?: {
    gamma_effectiveness: number;
    volume_profile_effectiveness: number;
    liquidity_effectiveness: number;
    volatility_effectiveness: number;
    session_effectiveness: number;
    global_integrity: number;
  };
}

export interface UseMELResult {
  snapshot: MELSnapshot | null;
  connected: boolean;
  error: string | null;
  isStructurePresent: boolean;
  globalIntegrity: number;
  getModelState: (model: string) => ModelState | null;
  refresh: () => Promise<void>;
}

export function useMEL(): UseMELResult {
  const [snapshot, setSnapshot] = useState<MELSnapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(COPILOT_WS);

      ws.onopen = () => {
        setConnected(true);
        setError(null);
        console.log('[MEL] WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'mel_snapshot') {
            setSnapshot(data.data);
          }
        } catch (e) {
          console.error('[MEL] Failed to parse message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error('[MEL] WebSocket error:', event);
        setError('Connection error');
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;

        // Reconnect after delay
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log('[MEL] Reconnecting...');
          connect();
        }, 5000);
      };

      wsRef.current = ws;
    } catch (e) {
      console.error('[MEL] Failed to connect:', e);
      setError('Failed to connect');
    }
  }, []);

  // Initial connection
  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  // Manual refresh via HTTP
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${COPILOT_BASE}/api/mel/snapshot`);
      if (response.ok) {
        const data = await response.json();
        setSnapshot(data);
      }
    } catch (e) {
      console.error('[MEL] Refresh failed:', e);
    }
  }, []);

  const getModelState = useCallback((model: string): ModelState | null => {
    if (!snapshot) return null;

    const modelMap: Record<string, MELModelScore | undefined> = {
      gamma: snapshot.gamma,
      volume_profile: snapshot.volume_profile,
      liquidity: snapshot.liquidity,
      volatility: snapshot.volatility,
      session: snapshot.session_structure,
    };

    return modelMap[model]?.state ?? null;
  }, [snapshot]);

  const isStructurePresent = snapshot ? snapshot.global_structure_integrity >= 50 : false;
  const globalIntegrity = snapshot?.global_structure_integrity ?? 0;

  return {
    snapshot,
    connected,
    error,
    isStructurePresent,
    globalIntegrity,
    getModelState,
    refresh,
  };
}

// Helper to get state indicator character
export function getStateIndicator(state: ModelState): string {
  switch (state) {
    case 'VALID': return '✓';
    case 'DEGRADED': return '⚠';
    case 'REVOKED': return '✗';
    default: return '?';
  }
}

// Helper to get state color
export function getStateColor(state: ModelState): string {
  switch (state) {
    case 'VALID': return '#22c55e';
    case 'DEGRADED': return '#f59e0b';
    case 'REVOKED': return '#ef4444';
    default: return '#666';
  }
}

// Helper to get trend arrow
export function getTrendArrow(trend: Trend): string {
  switch (trend) {
    case 'improving': return '↑';
    case 'stable': return '→';
    case 'degrading': return '↓';
    default: return '';
  }
}
