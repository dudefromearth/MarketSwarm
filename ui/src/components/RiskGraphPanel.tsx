/**
 * RiskGraphPanel - Consolidated Risk Graph component
 *
 * Features:
 * - P&L chart (PnLChart) with expiration and theoretical curves
 * - Strategies list with visibility toggle and debit editing
 * - Alerts section with price line alerts
 * - 3D of Options controls (time, spot, volatility simulation)
 * - Summary stats (Real-Time P&L, Max Profit, Max Loss)
 */

import { useRef, useMemo, useCallback } from 'react';
import PnLChart, { type PnLChartHandle, type PriceAlertType } from './PnLChart';
import { useRiskGraphCalculations, type Strategy } from '../hooks/useRiskGraphCalculations';
import { useAlerts } from '../contexts/AlertContext';
import type {
  AlertType,
  AlertBehavior,
  AlertCondition,
} from '../types/alerts';

// Re-export types for consumers
export type { AlertBehavior, AlertType };

// Handle for imperative methods (used by parent via ref)
export interface RiskGraphPanelHandle {
  autoFit: () => void;
}

// Strategy details for popup/risk graph
export interface SelectedStrategy {
  strategy: 'butterfly' | 'vertical' | 'single';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
}

export interface RiskGraphStrategy extends SelectedStrategy {
  id: string;
  addedAt: number;
  visible: boolean;
}

// Price alert line (visual only, separate from strategy alerts)
export interface PriceAlertLine {
  id: string;
  price: number;
  color: string;
  label?: string;
  createdAt: number;
}

// Data for editing an alert (passed to modal)
export interface EditingAlertData {
  id: string;
  type: AlertType;
  condition: AlertCondition;
  targetValue: number;
  color: string;
  behavior: AlertBehavior;
  minProfitThreshold?: number;
}


// Local color palette (matches types/alerts.ts ALERT_COLORS)
const ALERT_COLOR_PALETTE = [
  '#ef4444', '#f97316', '#eab308',
  '#22c55e', '#3b82f6', '#8b5cf6',
  '#ffffff', '#9ca3af', '#4b5563',
];

export interface RiskGraphPanelProps {
  // Strategies
  strategies: RiskGraphStrategy[];
  onRemoveStrategy: (id: string) => void;
  onToggleStrategyVisibility: (id: string) => void;
  onUpdateStrategyDebit: (id: string, debit: number | null) => void;

  // Price alert lines (visual chart annotations, separate from strategy alerts)
  priceAlertLines: PriceAlertLine[];
  onDeletePriceAlertLine: (id: string) => void;

  // Alert dialog callbacks (connect to AlertCreationModal in App.tsx)
  // Note: condition limited to basic types - zone conditions handled by AI alerts separately
  onOpenAlertDialog: (strategyId: string, price: number | null, condition: 'above' | 'below' | 'at') => void;
  onStartNewAlert: (strategyId: string) => void;
  onStartEditingAlert: (alertId: string) => void;

  // Market data
  spotPrice: number;
  vix: number;

  // 3D of Options
  timeMachineEnabled: boolean;
  onTimeMachineToggle: () => void;
  simTimeOffsetHours: number;
  onSimTimeChange: (hours: number) => void;
  simVolatilityOffset: number;
  onSimVolatilityChange: (offset: number) => void;
  simSpotOffset: number;
  onSimSpotChange: (offset: number) => void;
  onResetSimulation: () => void;

  // Panel state
  collapsed: boolean;
  onToggleCollapse: () => void;
}

// Black-Scholes for theoretical P&L calculations
function normalCDF(x: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  x = Math.abs(x) / Math.sqrt(2);
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return 0.5 * (1.0 + sign * y);
}

function blackScholesCall(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0) return Math.max(0, S - K);
  if (sigma <= 0) return Math.max(0, S - K);
  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);
}

function blackScholesPut(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0) return Math.max(0, K - S);
  if (sigma <= 0) return Math.max(0, K - S);
  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);
}

// Calculate strategy P&L at a given price (expiration)
function calculateStrategyPnL(strat: RiskGraphStrategy, price: number): number {
  const multiplier = 100;
  const debit = (strat.debit || 0) * multiplier;

  if (strat.strategy === 'single') {
    if (strat.side === 'call') {
      const intrinsic = Math.max(0, price - strat.strike);
      return intrinsic * multiplier - debit;
    } else {
      const intrinsic = Math.max(0, strat.strike - price);
      return intrinsic * multiplier - debit;
    }
  } else if (strat.strategy === 'vertical') {
    if (strat.side === 'call') {
      const longStrike = strat.strike;
      const shortStrike = strat.strike + strat.width;
      const longValue = Math.max(0, price - longStrike);
      const shortValue = Math.max(0, price - shortStrike);
      return (longValue - shortValue) * multiplier - debit;
    } else {
      const longStrike = strat.strike;
      const shortStrike = strat.strike - strat.width;
      const longValue = Math.max(0, longStrike - price);
      const shortValue = Math.max(0, shortStrike - price);
      return (longValue - shortValue) * multiplier - debit;
    }
  } else {
    // Butterfly
    const lowerStrike = strat.strike - strat.width;
    const upperStrike = strat.strike + strat.width;

    if (strat.side === 'call') {
      const longLower = Math.max(0, price - lowerStrike);
      const shortMiddle = Math.max(0, price - strat.strike) * 2;
      const longUpper = Math.max(0, price - upperStrike);
      return (longLower - shortMiddle + longUpper) * multiplier - debit;
    } else {
      const longUpper = Math.max(0, upperStrike - price);
      const shortMiddle = Math.max(0, strat.strike - price) * 2;
      const longLower = Math.max(0, lowerStrike - price);
      return (longUpper - shortMiddle + longLower) * multiplier - debit;
    }
  }
}

// Calculate theoretical P&L using Black-Scholes
function calculateTheoreticalPnL(
  strat: RiskGraphStrategy,
  price: number,
  volatility: number,
  dte: number,
  timeOffset: number
): number {
  const multiplier = 100;
  const debit = (strat.debit || 0) * multiplier;
  const r = 0.05;
  const stratDte = strat.dte || dte;
  const effectiveDte = Math.max(0, stratDte - timeOffset / 24);
  const T = effectiveDte / 365;

  if (strat.strategy === 'single') {
    const optionValue = strat.side === 'call'
      ? blackScholesCall(price, strat.strike, T, r, volatility)
      : blackScholesPut(price, strat.strike, T, r, volatility);
    return optionValue * multiplier - debit;
  } else if (strat.strategy === 'vertical') {
    if (strat.side === 'call') {
      const longValue = blackScholesCall(price, strat.strike, T, r, volatility);
      const shortValue = blackScholesCall(price, strat.strike + strat.width, T, r, volatility);
      return (longValue - shortValue) * multiplier - debit;
    } else {
      const longValue = blackScholesPut(price, strat.strike, T, r, volatility);
      const shortValue = blackScholesPut(price, strat.strike - strat.width, T, r, volatility);
      return (longValue - shortValue) * multiplier - debit;
    }
  } else {
    // Butterfly
    const lowerStrike = strat.strike - strat.width;
    const upperStrike = strat.strike + strat.width;

    if (strat.side === 'call') {
      const longLower = blackScholesCall(price, lowerStrike, T, r, volatility);
      const shortMiddle = blackScholesCall(price, strat.strike, T, r, volatility) * 2;
      const longUpper = blackScholesCall(price, upperStrike, T, r, volatility);
      return (longLower - shortMiddle + longUpper) * multiplier - debit;
    } else {
      const longUpper = blackScholesPut(price, upperStrike, T, r, volatility);
      const shortMiddle = blackScholesPut(price, strat.strike, T, r, volatility) * 2;
      const longLower = blackScholesPut(price, lowerStrike, T, r, volatility);
      return (longUpper - shortMiddle + longLower) * multiplier - debit;
    }
  }
}

export default function RiskGraphPanel({
  strategies,
  onRemoveStrategy,
  onToggleStrategyVisibility,
  onUpdateStrategyDebit,
  priceAlertLines,
  onDeletePriceAlertLine,
  onOpenAlertDialog,
  onStartNewAlert,
  onStartEditingAlert,
  spotPrice,
  vix,
  timeMachineEnabled,
  onTimeMachineToggle,
  simTimeOffsetHours,
  onSimTimeChange,
  simVolatilityOffset,
  onSimVolatilityChange,
  simSpotOffset,
  onSimSpotChange,
  onResetSimulation,
  collapsed,
  onToggleCollapse,
}: RiskGraphPanelProps) {
  // Get alerts from shared context
  const {
    alerts,
    deleteAlert,
    clearTriggeredAlerts,
    getTriggeredAlerts,
  } = useAlerts();

  const pnlChartRef = useRef<PnLChartHandle>(null);

  // Simulated spot for 3D of Options
  const simulatedSpot = timeMachineEnabled ? spotPrice + simSpotOffset : spotPrice;
  const currentVix = vix + (timeMachineEnabled ? simVolatilityOffset : 0);

  // Map strategies to the format expected by useRiskGraphCalculations
  const chartStrategies: Strategy[] = useMemo(() =>
    strategies.map(s => ({
      id: s.id,
      strike: s.strike,
      width: s.width,
      side: s.side,
      strategy: s.strategy,
      debit: s.debit,
      visible: s.visible,
      dte: s.dte,
      expiration: s.expiration,
    })),
    [strategies]
  );

  // Calculate P&L data for PnLChart
  const pnlChartData = useRiskGraphCalculations({
    strategies: chartStrategies,
    spotPrice: spotPrice,
    vix: vix,
    timeMachineEnabled,
    simVolatilityOffset,
    simTimeOffsetHours,
  });

  // Extract strikes from strategies for chart
  const chartStrikes = useMemo(() => {
    return strategies.filter(s => s.visible).flatMap(strat => {
      if (strat.strategy === 'butterfly') {
        return [strat.strike - strat.width, strat.strike, strat.strike + strat.width];
      } else if (strat.strategy === 'vertical') {
        return [strat.strike, strat.side === 'call' ? strat.strike + strat.width : strat.strike - strat.width];
      }
      return [strat.strike];
    });
  }, [strategies]);

  // Calculate risk graph data for stats (includes market P&L)
  const riskGraphData = useMemo(() => {
    const visibleStrategies = strategies.filter(s => s.visible);
    if (visibleStrategies.length === 0) {
      return {
        minPnL: 0,
        maxPnL: 0,
        theoreticalPnLAtSpot: 0,
        marketPnL: null as number | null,
      };
    }

    const volatility = Math.max(0.05, currentVix) / 100;
    const timeOffset = timeMachineEnabled ? simTimeOffsetHours : 0;

    // Calculate min/max P&L
    let minPnL = Infinity;
    let maxPnL = -Infinity;
    const allStrikes = visibleStrategies.flatMap(s => {
      if (s.strategy === 'butterfly') {
        return [s.strike - s.width, s.strike, s.strike + s.width];
      } else if (s.strategy === 'vertical') {
        return [s.strike, s.side === 'call' ? s.strike + s.width : s.strike - s.width];
      }
      return [s.strike];
    });

    const minStrike = Math.min(...allStrikes);
    const maxStrike = Math.max(...allStrikes);
    const range = maxStrike - minStrike || 100;
    const fullPadding = Math.max(range * 1.5, 150);
    const fullMinPrice = minStrike - fullPadding;
    const fullMaxPrice = maxStrike + fullPadding;

    const numPoints = 400;
    const step = (fullMaxPrice - fullMinPrice) / numPoints;

    for (let i = 0; i <= numPoints; i++) {
      const price = fullMinPrice + i * step;
      let totalPnL = 0;
      for (const strat of visibleStrategies) {
        totalPnL += calculateStrategyPnL(strat, price);
      }
      minPnL = Math.min(minPnL, totalPnL);
      maxPnL = Math.max(maxPnL, totalPnL);
    }

    // Theoretical P&L at current spot
    let theoreticalPnLAtSpot = 0;
    const dte = visibleStrategies[0]?.dte || 0;
    for (const strat of visibleStrategies) {
      theoreticalPnLAtSpot += calculateTheoreticalPnL(strat, spotPrice, volatility, dte, timeOffset);
    }

    return {
      minPnL,
      maxPnL,
      theoreticalPnLAtSpot,
      marketPnL: null as number | null,
    };
  }, [strategies, spotPrice, currentVix, timeMachineEnabled, simTimeOffsetHours]);

  // Convert price alert lines to format expected by PnLChart
  const alertLinesForChart = useMemo(() => {
    const lines: { price: number; color: string; label?: string }[] = [];

    // Price alert lines
    priceAlertLines.forEach(line => {
      lines.push({
        price: line.price,
        color: line.color,
        label: line.label,
      });
    });

    // Strategy price alerts
    alerts.filter(a => a.enabled && a.type === 'price').forEach(alert => {
      lines.push({
        price: alert.targetValue,
        color: alert.color,
        label: alert.targetValue.toFixed(0),
      });
    });

    return lines;
  }, [priceAlertLines, alerts]);

  // Handle opening alert dialog from chart context menu
  const handleOpenAlertDialog = useCallback((price: number, type: PriceAlertType) => {
    const conditionMap: Record<PriceAlertType, 'above' | 'below' | 'at'> = {
      'price_above': 'above',
      'price_below': 'below',
      'price_touch': 'at',
    };
    const strategyId = strategies[0]?.id || 'chart-alert';
    onOpenAlertDialog(strategyId, Math.round(price), conditionMap[type]);
  }, [strategies, onOpenAlertDialog]);

  // Format DTE display
  const formatDTE = (hours: number) => {
    if (hours <= 0) return '0m';
    if (hours < 4) {
      const mins = Math.round(hours * 60);
      if (mins < 60) return `${mins}m`;
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }
    if (hours < 24) return `${hours.toFixed(0)}h`;
    const days = hours / 24;
    if (days < 1.5) {
      const h = Math.round(hours % 24);
      return `1d ${h}h`;
    }
    return `${days.toFixed(1)}d`;
  };

  // Calculate time machine limits
  const visibleStrategies = strategies.filter(s => s.visible);
  const minDTE = visibleStrategies.length > 0
    ? Math.min(...visibleStrategies.map(s => s.dte))
    : 1;
  const maxHours = Math.max(1, minDTE) * 24;
  const hoursRemaining = maxHours - simTimeOffsetHours;
  const effectiveHoursRemaining = Math.max(0, hoursRemaining);
  const stepSize = effectiveHoursRemaining <= 4 ? 0.25 : 1;

  return (
    <div className={`panel echarts-risk-graph-panel ${collapsed ? 'collapsed' : ''}`}>
      <div className="panel-header" onClick={onToggleCollapse}>
        <span className="panel-toggle">{collapsed ? '>' : 'v'}</span>
        <h3>Risk Graph {strategies.length > 0 && `(${strategies.length})`}</h3>
        {strategies.length > 0 && !collapsed && (
          <button
            className="btn-auto-fit-header"
            onClick={(e) => {
              e.stopPropagation();
              pnlChartRef.current?.autoFit();
            }}
          >
            Auto-Fit
          </button>
        )}
      </div>
      {!collapsed && (
        <div className="panel-content risk-graph-consolidated">
          {strategies.length === 0 ? (
            <div className="risk-graph-empty">
              <p>No strategies added yet.</p>
              <p className="hint">Click on a heatmap tile and select "Add to Risk Graph"</p>
            </div>
          ) : (
            <>
              {/* Main content: Chart + Sidebar */}
              <div className="risk-graph-main">
                {/* Chart Area */}
                <div className="risk-graph-chart-area">
                  <PnLChart
                    ref={pnlChartRef}
                    expirationData={pnlChartData.expirationPoints}
                    theoreticalData={pnlChartData.theoreticalPoints}
                    spotPrice={spotPrice}
                    expirationBreakevens={pnlChartData.expirationBreakevens}
                    theoreticalBreakevens={pnlChartData.theoreticalBreakevens}
                    strikes={chartStrikes}
                    onOpenAlertDialog={handleOpenAlertDialog}
                    alertLines={alertLinesForChart}
                  />
                </div>
              </div>

              {/* Sidebar: Strategies + Alerts */}
              <div className="risk-graph-sidebar">
                {/* Strategy List */}
                <div className="risk-graph-strategies">
                  <div className="section-header">Strategies</div>
                  <div className="strategies-list">
                    {strategies.map(strat => (
                      <div key={strat.id} className={`risk-graph-strategy-item ${!strat.visible ? 'hidden-strategy' : ''}`}>
                        <div className="strategy-content">
                          <div className="strategy-row-top">
                            <span className="strategy-type">
                              {strat.strategy === 'butterfly' ? 'BF' : strat.strategy === 'vertical' ? 'VS' : 'SGL'}
                            </span>
                            <span className="strategy-strike">
                              {strat.strike}{strat.width > 0 ? `/${strat.width}` : ''}
                            </span>
                            <span className={`strategy-side ${strat.side}`}>
                              {strat.side}
                            </span>
                            <span className="strategy-dte">{strat.dte}d</span>
                            <span className="strategy-debit">
                              $<input
                                type="number"
                                className="debit-input"
                                defaultValue={strat.debit !== null ? strat.debit.toFixed(2) : ''}
                                key={`debit-${strat.id}-${strat.debit}`}
                                step="0.01"
                                min="0"
                                onBlur={(e) => {
                                  const val = parseFloat(e.target.value);
                                  onUpdateStrategyDebit(strat.id, isNaN(val) ? null : val);
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    e.currentTarget.blur();
                                  }
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                            </span>
                          </div>
                          <div className="strategy-row-bottom">
                            <button
                              className={`btn-toggle-visibility ${strat.visible ? 'visible' : 'hidden'}`}
                              onClick={() => onToggleStrategyVisibility(strat.id)}
                            >
                              {strat.visible ? 'Hide' : 'Show'}
                            </button>
                            <button
                              className="btn-alert"
                              onClick={() => onStartNewAlert(strat.id)}
                              title="Set alert"
                            >
                              Alert
                            </button>
                            <button className="btn-remove" onClick={() => onRemoveStrategy(strat.id)}>x</button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Alerts Section */}
                <div className="risk-graph-alerts">
                  <div className="section-header">
                    Alerts
                    {getTriggeredAlerts().length > 0 && (
                      <button className="btn-clear-triggered" onClick={clearTriggeredAlerts}>
                        Clear
                      </button>
                    )}
                  </div>
                  <div className="alerts-list">
                    {alerts.map(alert => (
                      <div
                        key={alert.id}
                        className={`alert-item clickable ${alert.triggered ? 'triggered' : ''} ${!alert.enabled ? 'disabled' : ''}`}
                        onClick={() => onStartEditingAlert(alert.id)}
                      >
                        <div className="alert-info">
                          <div
                            className="alert-color-dot"
                            style={{ backgroundColor: alert.color || ALERT_COLOR_PALETTE[0] }}
                          />
                          <span className="alert-condition">
                            {alert.type === 'price' && `${alert.condition === 'above' ? '>=' : alert.condition === 'below' ? '<=' : '~'} ${alert.targetValue.toFixed(0)}`}
                            {alert.type === 'debit' && `$${alert.targetValue.toFixed(2)}`}
                            {alert.type === 'profit_target' && `+$${alert.targetValue.toFixed(2)}`}
                            {alert.type === 'trailing_stop' && `Trail $${alert.targetValue.toFixed(2)}`}
                            {alert.type === 'ai_theta_gamma' && `AI Th/Gm`}
                            {alert.type === 'ai_sentiment' && `AI Sent`}
                            {alert.type === 'ai_risk_zone' && `AI Zone`}
                          </span>
                        </div>
                        <button
                          className="btn-delete-alert"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteAlert(alert.id);
                          }}
                        >
                          x
                        </button>
                      </div>
                    ))}

                    {/* Price Line Alerts */}
                    {priceAlertLines.map(alert => (
                      <div key={alert.id} className="alert-item price-line-alert">
                        <div className="alert-info">
                          <div
                            className="alert-color-dot"
                            style={{ backgroundColor: alert.color }}
                          />
                          <span className="alert-condition">
                            Line @ {alert.price.toFixed(0)}
                          </span>
                        </div>
                        <button
                          className="btn-delete-alert"
                          onClick={() => onDeletePriceAlertLine(alert.id)}
                        >
                          x
                        </button>
                      </div>
                    ))}

                    {alerts.length === 0 && priceAlertLines.length === 0 && (
                      <div className="alerts-empty">No alerts<br/><span className="hint">Right-click chart for price line</span></div>
                    )}
                  </div>
                </div>
              </div>

              {/* 3D of Options Controls */}
              <div className={`time-machine-panel ${timeMachineEnabled ? 'active' : ''}`}>
                <div className="time-machine-header">
                  <div className="time-machine-switch">
                    <span className="switch-label">3D of Options</span>
                    <button
                      className={`switch-toggle ${timeMachineEnabled ? 'on' : 'off'}`}
                      onClick={onTimeMachineToggle}
                    >
                      {timeMachineEnabled ? 'ON' : 'OFF'}
                    </button>
                    {timeMachineEnabled && (
                      <button className="btn-reset" onClick={onResetSimulation}>
                        Reset
                      </button>
                    )}
                  </div>
                </div>
                <div className={`time-machine-controls ${!timeMachineEnabled ? 'disabled' : ''}`}>
                  <div className="horizontal-controls">
                    <div className="control-group time-control">
                      <div className="slider-row">
                        <span className="control-label">Time</span>
                        <input
                          type="range"
                          min="0"
                          max={maxHours}
                          step={stepSize}
                          value={simTimeOffsetHours}
                          onChange={(e) => onSimTimeChange(parseFloat(e.target.value))}
                          className="time-slider"
                          disabled={!timeMachineEnabled}
                        />
                        <span className="control-readout time-readout">
                          {formatDTE(effectiveHoursRemaining)}
                        </span>
                      </div>
                    </div>
                    <div className="control-group spot-control">
                      <div className="slider-row">
                        <span className="control-label">Spot</span>
                        <div className="slider-with-thumb-value">
                          <input
                            type="range"
                            min="-150"
                            max="150"
                            step="1"
                            value={simSpotOffset}
                            onChange={(e) => onSimSpotChange(parseFloat(e.target.value))}
                            className="spot-slider"
                            disabled={!timeMachineEnabled}
                          />
                          <div
                            className="thumb-value"
                            style={{ left: `${((simSpotOffset + 150) / 300) * 100}%` }}
                          >
                            {simulatedSpot?.toFixed(0) || '-'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="vertical-control vol-control">
                    <div className="vol-label-left">
                      <span className="vol-label-text">VIX</span>
                      <span className="vol-value">{currentVix.toFixed(1)}</span>
                    </div>
                    <div className="vertical-slider-container">
                      <span className="vol-tick">30</span>
                      <input
                        type="range"
                        min="5"
                        max="30"
                        step="0.5"
                        value={currentVix}
                        onChange={(e) => {
                          const newVix = parseFloat(e.target.value);
                          onSimVolatilityChange(newVix - vix);
                        }}
                        className="vol-slider-vertical"
                        disabled={!timeMachineEnabled}
                      />
                      <span className="vol-tick">5</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Summary Stats */}
              <div className="risk-graph-stats">
                <div className="stat highlight">
                  <span className="stat-label">Real-Time P&L</span>
                  {(() => {
                    const pnl = riskGraphData.marketPnL ?? riskGraphData.theoreticalPnLAtSpot;
                    return (
                      <span className={`stat-value ${pnl >= 0 ? 'profit' : 'loss'}`}>
                        ${(pnl / 100).toFixed(2)}
                      </span>
                    );
                  })()}
                </div>
                <div className="stat-divider" />
                <div className="stat">
                  <span className="stat-label">Max Profit</span>
                  <span className="stat-value profit">${(riskGraphData.maxPnL / 100).toFixed(2)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Max Loss</span>
                  <span className="stat-value loss">${(riskGraphData.minPnL / 100).toFixed(2)}</span>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
