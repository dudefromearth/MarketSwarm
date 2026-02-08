/**
 * useVexyContext - Gathers comprehensive app state for Vexy
 *
 * Collects data from all relevant contexts to give Vexy
 * situational awareness of the user's trading environment.
 */

import { useMemo } from 'react';
import { usePath } from '../contexts/PathContext';
import { useAlerts } from '../contexts/AlertContext';

// Types for the comprehensive context
export interface VexyPositionSummary {
  id: string;
  type: string;
  direction: 'long' | 'short';
  symbol: string;
  strikes: number[];
  expiration?: string;
  costBasis?: number;
  currentValue?: number;
  pnl?: number;
  pnlPercent?: number;
  daysToExpiry?: number;
}

export interface VexyTradeSummary {
  totalTrades: number;
  openTrades: number;
  closedTrades: number;
  todayTrades: number;
  winRate?: number;
  todayPnl?: number;
  weekPnl?: number;
}

export interface VexyAlertSummary {
  armed: number;
  triggered: number;
  recentTriggers: Array<{
    type: string;
    message: string;
    triggeredAt: string;
  }>;
}

export interface VexyRiskSummary {
  strategiesOnGraph: number;
  totalMaxProfit?: number;
  totalMaxLoss?: number;
  breakevenPoints?: number[];
}

export interface VexyMarketContext {
  spxPrice?: number | null;
  spxChange?: number | null;
  spxChangePercent?: number | null;
  vixLevel?: number | null;
  vixRegime?: string | null;
  gexPosture?: string | null;
  marketMode?: string | null;
  marketModeScore?: number | null;
  directionalStrength?: number | null;
  lfiScore?: number | null;
}

export interface VexyUIState {
  activePanel?: string | null;
  currentStage?: string;
  routineCompleted?: boolean;
  tourCompleted?: boolean;
}

export interface VexyFullContext {
  // Market data
  market: VexyMarketContext;

  // User's positions
  positions: VexyPositionSummary[];

  // Trading activity
  trading: VexyTradeSummary;

  // Alerts
  alerts: VexyAlertSummary;

  // Risk graph
  risk: VexyRiskSummary;

  // UI state
  ui: VexyUIState;

  // Timestamp
  timestamp: string;
}

interface UseVexyContextOptions {
  marketContext?: VexyMarketContext;
  positions?: any[];
  trades?: any[];
  openTrades?: any[];
  closedTrades?: any[];
  riskStrategies?: any[];
}

/**
 * Hook to gather comprehensive context for Vexy.
 *
 * Usage:
 * ```tsx
 * const vexyContext = useVexyContext({
 *   marketContext,
 *   positions,
 *   trades,
 *   riskStrategies,
 * });
 * ```
 */
export function useVexyContext(options: UseVexyContextOptions = {}): VexyFullContext {
  const { currentStage, activePanel, tourCompleted } = usePath();
  const { alerts } = useAlerts();

  const context = useMemo<VexyFullContext>(() => {
    // Process positions
    const positionSummaries: VexyPositionSummary[] = (options.positions || []).map((pos: any) => {
      const strikes = pos.legs?.map((l: any) => l.strike).filter(Boolean) || [];
      const expiration = pos.legs?.[0]?.expiration;
      const daysToExpiry = expiration
        ? Math.ceil((new Date(expiration).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
        : undefined;

      return {
        id: pos.id,
        type: pos.positionType || pos.strategy || 'unknown',
        direction: pos.direction || 'long',
        symbol: pos.symbol || 'SPX',
        strikes,
        expiration,
        costBasis: pos.costBasis,
        currentValue: pos.currentValue,
        pnl: pos.pnl,
        pnlPercent: pos.pnlPercent,
        daysToExpiry,
      };
    });

    // Process trades
    const trades = options.trades || [];
    const openTrades = options.openTrades || trades.filter((t: any) => t.status === 'open');
    const closedTrades = options.closedTrades || trades.filter((t: any) => t.status === 'closed');

    const today = new Date().toDateString();
    const todayTrades = trades.filter((t: any) => {
      const entryDate = new Date(t.entryTime || t.entry_time).toDateString();
      return entryDate === today;
    });

    const closedWithPnl = closedTrades.filter((t: any) => t.pnl != null);
    const winners = closedWithPnl.filter((t: any) => t.pnl > 0);
    const winRate = closedWithPnl.length > 0
      ? Math.round((winners.length / closedWithPnl.length) * 100)
      : undefined;

    const todayPnl = todayTrades.reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);

    // Week calculation
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    const weekTrades = trades.filter((t: any) => {
      const entryDate = new Date(t.entryTime || t.entry_time);
      return entryDate >= weekAgo;
    });
    const weekPnl = weekTrades.reduce((sum: number, t: any) => sum + (t.pnl || 0), 0);

    const tradingSummary: VexyTradeSummary = {
      totalTrades: trades.length,
      openTrades: openTrades.length,
      closedTrades: closedTrades.length,
      todayTrades: todayTrades.length,
      winRate,
      todayPnl: todayPnl || undefined,
      weekPnl: weekPnl || undefined,
    };

    // Process alerts
    const armedAlerts = alerts.filter((a: any) => a.status === 'armed' || !a.triggeredAt);
    const triggeredAlerts = alerts.filter((a: any) => a.status === 'triggered' || a.triggeredAt);

    // Recent triggers (last hour)
    const hourAgo = Date.now() - 60 * 60 * 1000;
    const recentTriggers = triggeredAlerts
      .filter((a: any) => a.triggeredAt && a.triggeredAt > hourAgo)
      .slice(0, 3)
      .map((a: any) => ({
        type: a.type || a.alertType || 'alert',
        message: a.name || a.message || 'Alert triggered',
        triggeredAt: new Date(a.triggeredAt).toLocaleTimeString(),
      }));

    const alertSummary: VexyAlertSummary = {
      armed: armedAlerts.length,
      triggered: triggeredAlerts.length,
      recentTriggers,
    };

    // Process risk graph strategies
    const riskStrategies = options.riskStrategies || [];
    const visibleStrategies = riskStrategies.filter((s: any) => s.visible !== false);

    const riskSummary: VexyRiskSummary = {
      strategiesOnGraph: visibleStrategies.length,
      // These would need to be calculated from actual risk graph data
    };

    // UI state
    const uiState: VexyUIState = {
      activePanel,
      currentStage,
      tourCompleted,
    };

    return {
      market: options.marketContext || {},
      positions: positionSummaries,
      trading: tradingSummary,
      alerts: alertSummary,
      risk: riskSummary,
      ui: uiState,
      timestamp: new Date().toISOString(),
    };
  }, [
    options.marketContext,
    options.positions,
    options.trades,
    options.openTrades,
    options.closedTrades,
    options.riskStrategies,
    alerts,
    currentStage,
    activePanel,
    tourCompleted,
  ]);

  return context;
}

/**
 * Formats the context for sending to the API.
 * Only includes non-empty sections to reduce payload size.
 */
export function formatContextForApi(context: VexyFullContext): Record<string, any> {
  const result: Record<string, any> = {};

  // Always include market data if present
  if (context.market && Object.keys(context.market).some(k => context.market[k as keyof VexyMarketContext] != null)) {
    result.market_data = context.market;
  }

  // Include positions if any
  if (context.positions.length > 0) {
    result.positions = context.positions;
  }

  // Include trading summary if there's activity
  if (context.trading.totalTrades > 0 || context.trading.openTrades > 0) {
    result.trading = context.trading;
  }

  // Include alerts if any are armed or recently triggered
  if (context.alerts.armed > 0 || context.alerts.recentTriggers.length > 0) {
    result.alerts = context.alerts;
  }

  // Include risk graph if strategies present
  if (context.risk.strategiesOnGraph > 0) {
    result.risk = context.risk;
  }

  // Always include UI state
  result.ui = context.ui;

  return result;
}
