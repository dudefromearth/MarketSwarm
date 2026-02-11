/**
 * RiskGraphPanel - Consolidated Risk Graph component
 *
 * Features:
 * - P&L chart (PnLChart) with expiration and theoretical curves
 * - Positions list with visibility toggle and debit editing
 * - Alerts section with price line alerts
 * - 3D of Options controls (time, spot, volatility simulation)
 * - Summary stats (Real-Time P&L, Max Profit, Max Loss)
 */

import { useRef, useMemo, useCallback, useState, forwardRef, useImperativeHandle } from 'react';
import PnLChart, { type PnLChartHandle, type PriceAlertType, type BackdropRenderProps } from './PnLChart';
import RiskGraphBackdrop from './RiskGraphBackdrop';
import DealerGravitySettings from './DealerGravitySettings';
import AlgoAlertPanel from './AlgoAlertPanel';
import WhatsNew from './WhatsNew';
import {
  useRiskGraphCalculations,
  type Strategy,
  type MarketRegime,
  type PricingModel,
  MARKET_REGIMES,
  PRICING_MODELS,
} from '../hooks/useRiskGraphCalculations';
import { resolveSpotKey } from '../utils/symbolResolver';
import { useAlerts } from '../contexts/AlertContext';
import { useDealerGravity } from '../contexts/DealerGravityContext';
import { useIndicatorSettings } from './chart-primitives';
import type {
  AlertType,
  AlertBehavior,
  AlertCondition,
} from '../types/alerts';
import type { PositionLeg, PositionType, PositionDirection, CostBasisType } from '../types/riskGraph';
import { recognizePositionType, strategyToLegs } from '../utils/positionRecognition';
import { formatLegsDisplay, formatPositionLabel } from '../utils/positionFormatting';

// Re-export types for consumers
export type { AlertBehavior, AlertType };

// Handle for imperative methods (used by parent via ref)
export interface RiskGraphPanelHandle {
  autoFit: () => void;
}

// Strategy details for popup/risk graph (legacy interface)
export interface SelectedStrategy {
  strategy: 'butterfly' | 'vertical' | 'single';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
  symbol?: string;  // Underlying symbol (SPX, NDX, etc.)
}

// Extended interface with leg support and cost basis
export interface RiskGraphStrategy extends SelectedStrategy {
  id: string;
  addedAt: number;
  visible: boolean;
  // New leg-based fields (optional for backward compat)
  legs?: PositionLeg[];
  positionType?: PositionType;
  direction?: PositionDirection;
  // Cost basis (debit = you paid, credit = you received)
  costBasis?: number | null;      // Absolute value of cost
  costBasisType?: CostBasisType;  // 'debit' or 'credit'
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
  simSpotPct: number;
  onSimSpotPctChange: (pct: number) => void;
  onResetSimulation: () => void;

  // Reflection hook - opens Journal for capturing insights
  onOpenJournal?: () => void;

  // Create Position - opens PositionCreateModal
  onCreatePosition?: () => void;

  // Edit strategy - opens modal to edit existing strategy
  onEditStrategy?: (id: string) => void;

  // Log trade - opens TradeEntryModal with strategy data
  onLogTrade?: (strategy: RiskGraphStrategy) => void;

  // Monitor - opens position monitor panel
  onOpenMonitor?: () => void;
  pendingOrderCount?: number;
  openTradeCount?: number;

  // GEX data for backdrop (from App.tsx)
  gexByStrike?: Record<number, { calls: number; puts: number }>;

  // Full spot data map for per-symbol pricing (from SSE spot channel)
  spotData?: Record<string, { value: number; [key: string]: any }>;
}

export interface RiskGraphPanelHandle {
  autoFit: () => void;
}

// P&L calculations are now handled by useRiskGraphCalculations hook

const RiskGraphPanel = forwardRef<RiskGraphPanelHandle, RiskGraphPanelProps>(function RiskGraphPanel({
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
  simSpotPct,
  onSimSpotPctChange,
  onResetSimulation,
  onOpenJournal,
  onCreatePosition,
  onEditStrategy,
  onLogTrade,
  onOpenMonitor,
  pendingOrderCount = 0,
  openTradeCount = 0,
  gexByStrike,
  spotData,
}, ref) {
  // Get alerts from shared context
  const {
    alerts,
    deleteAlert,
    clearTriggeredAlerts,
    getTriggeredAlerts,
  } = useAlerts();

  // Dealer Gravity context for backdrop
  const { artifact: dgArtifact, config: dgConfig } = useDealerGravity();

  const pnlChartRef = useRef<PnLChartHandle>(null);

  // Track meaningful analyzer interaction for reflection hook
  const [hasAnalyzerInteraction, setHasAnalyzerInteraction] = useState(false);

  // Lock/unlock state for position pricing (locked = user-entered, unlocked = model theo value)
  const [priceLocked, setPriceLocked] = useState<Record<string, boolean>>({});

  // Backdrop visibility controls (off by default - user can enable as needed)
  const [showVolumeProfile, setShowVolumeProfile] = useState(false);
  const [showGex, setShowGex] = useState(false);
  const [showStructuralLines, setShowStructuralLines] = useState(false);
  const [backdropOpacity, setBackdropOpacity] = useState(0.8);
  const [showDGSettings, setShowDGSettings] = useState(false);

  // Get GEX and VP configs from indicator settings (inherits from DG chart settings)
  const { gexConfig, vpConfig: volumeProfileConfig } = useIndicatorSettings();

  // Expose autoFit to parent
  useImperativeHandle(ref, () => ({
    autoFit: () => pnlChartRef.current?.autoFit(),
  }));
  const vixInputRef = useRef<HTMLInputElement>(null);

  // VIX editing state
  const [isEditingVix, setIsEditingVix] = useState(false);
  const [vixInputValue, setVixInputValue] = useState('');

  // Market regime for volatility skew simulation
  const [marketRegime, setMarketRegime] = useState<MarketRegime>('normal');
  const regimeConfig = MARKET_REGIMES[marketRegime];

  // Pricing model selection and parameters
  const [pricingModel, setPricingModel] = useState<PricingModel>('black-scholes');
  const pricingModelConfig = PRICING_MODELS[pricingModel];

  // Heston parameters (user-adjustable)
  const [hestonVolOfVol, setHestonVolOfVol] = useState(0.4);
  const [hestonCorrelation, setHestonCorrelation] = useState(-0.7);

  // Monte Carlo parameters
  const [mcNumPaths, setMcNumPaths] = useState(5000);

  // Weighting index selector — determines the X-axis reference for portfolio-weighted view
  const underlyings = useMemo(() => {
    const syms = new Set(strategies.map(s => s.symbol || 'SPX'));
    return Array.from(syms).sort();
  }, [strategies]);

  const [weightingIndex, setWeightingIndex] = useState<string>('SPX');

  // Auto-select: prefer SPX if present, else first available symbol
  const effectiveWeightingIndex = underlyings.includes(weightingIndex) ? weightingIndex : (underlyings.includes('SPX') ? 'SPX' : underlyings[0] || 'SPX');

  // Compute the weighting spot price from spotData
  const weightingSpot = useMemo(() => {
    if (!spotData) return spotPrice;
    const key = resolveSpotKey(effectiveWeightingIndex);
    const val = spotData[key]?.value;
    return (val && val > 0) ? val : spotPrice;
  }, [spotData, effectiveWeightingIndex, spotPrice]);

  // Simulated spot for 3D of Options (percentage-based)
  const simulatedSpot = timeMachineEnabled ? weightingSpot * (1 + simSpotPct / 100) : weightingSpot;
  const currentVix = vix + (timeMachineEnabled ? simVolatilityOffset : 0);

  // Handle VIX edit
  const handleVixClick = useCallback(() => {
    if (!timeMachineEnabled) return;
    setVixInputValue(currentVix.toFixed(1));
    setIsEditingVix(true);
    // Focus input after render
    setTimeout(() => vixInputRef.current?.select(), 0);
  }, [timeMachineEnabled, currentVix]);

  const handleVixInputBlur = useCallback(() => {
    setIsEditingVix(false);
    const newVix = parseFloat(vixInputValue);
    if (!isNaN(newVix) && newVix >= 5 && newVix <= 80) {
      onSimVolatilityChange(newVix - vix);
    }
  }, [vixInputValue, vix, onSimVolatilityChange]);

  const handleVixInputKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleVixInputBlur();
    } else if (e.key === 'Escape') {
      setIsEditingVix(false);
    }
  }, [handleVixInputBlur]);

  // Build spotPrices map from spotData for per-symbol pricing
  const spotPrices = useMemo(() => {
    if (!spotData) return undefined;
    const map: Record<string, number> = {};
    for (const [key, data] of Object.entries(spotData)) {
      if (data?.value) map[key] = data.value;
    }
    return Object.keys(map).length > 0 ? map : undefined;
  }, [spotData]);

  // Lock/unlock toggle for position pricing (default: unlocked)
  const togglePriceLock = useCallback((id: string) => {
    setPriceLocked(prev => {
      const currentlyLocked = prev[id] ?? false;
      return { ...prev, [id]: !currentlyLocked };
    });
  }, []);

  // Compute set of unlocked strategy IDs for the calculation hook
  const unlockedStrategyIds = useMemo(() => {
    const ids = new Set<string>();
    for (const s of strategies) {
      const locked = priceLocked[s.id] ?? false;
      if (!locked) ids.add(s.id);
    }
    return ids;
  }, [strategies, priceLocked]);

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
      symbol: s.symbol,
      // Include leg-based fields for accurate multi-leg position rendering
      legs: s.legs,
      positionType: s.positionType,
      direction: s.direction,
    })),
    [strategies]
  );

  // Calculate P&L data for PnLChart
  const pnlChartData = useRiskGraphCalculations({
    strategies: chartStrategies,
    spotPrice: spotPrice,
    vix: vix,
    spotPrices,
    weightingSpot,
    timeMachineEnabled,
    simVolatilityOffset,
    simTimeOffsetHours,
    simSpotPct,
    marketRegime,
    pricingModel,
    hestonVolOfVol,
    hestonCorrelation,
    mcNumPaths,
    unlockedStrategyIds,
  });

  // Extract strikes from all visible strategies for chart (includes expired for auto-fit bounds)
  const chartStrikes = useMemo(() => {
    return strategies.filter(s => s.visible).flatMap(strat => {
      // Use legs if available for accurate strike extraction
      if (strat.legs && strat.legs.length > 0) {
        return strat.legs.map(leg => leg.strike);
      }
      // Legacy fallback
      if (strat.strategy === 'butterfly') {
        return [strat.strike - strat.width, strat.strike, strat.strike + strat.width];
      } else if (strat.strategy === 'vertical') {
        return [strat.strike, strat.side === 'call' ? strat.strike + strat.width : strat.strike - strat.width];
      }
      return [strat.strike];
    });
  }, [strategies]);

  // Stats derived from the hook's calculated data
  const riskGraphData = useMemo(() => {
    return {
      minPnL: pnlChartData.minPnL,
      maxPnL: pnlChartData.maxPnL,
      theoreticalPnLAtSpot: pnlChartData.theoreticalPnLAtSpot,
      marketPnL: null as number | null,
    };
  }, [pnlChartData]);

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
      const val = Number(alert.targetValue);
      lines.push({
        price: val,
        color: alert.color,
        label: val.toFixed(0),
      });
    });

    // AI Theta/Gamma zone lines
    alerts.filter(a => a.enabled && a.type === 'ai_theta_gamma' && a.isZoneActive && a.zoneLow && a.zoneHigh).forEach(alert => {
      lines.push({
        price: alert.zoneLow!,
        color: alert.color || '#f59e0b',
        label: `Zone ${alert.zoneLow!.toFixed(0)}`,
      });
      lines.push({
        price: alert.zoneHigh!,
        color: alert.color || '#f59e0b',
        label: `Zone ${alert.zoneHigh!.toFixed(0)}`,
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

  // Render backdrop for Dealer Gravity visualization (VP + GEX + Structural Lines)
  const renderBackdrop = useCallback((props: BackdropRenderProps) => {
    // Show backdrop if we have any data to display
    const hasVPData = dgArtifact?.profile;
    const hasGexData = gexByStrike && Object.keys(gexByStrike).length > 0;
    if (!hasVPData && !hasGexData) return null;

    return (
      <RiskGraphBackdrop
        width={props.width}
        height={props.height}
        priceMin={props.priceMin}
        priceMax={props.priceMax}
        spotPrice={props.spotPrice}
        showVolumeProfile={showVolumeProfile}
        showGex={showGex}
        showStructuralLines={showStructuralLines}
        opacity={backdropOpacity}
        gexByStrike={gexByStrike}
        gexConfig={{
          callColor: gexConfig.callColor,
          putColor: gexConfig.putColor,
          mode: gexConfig.mode,
          barHeight: gexConfig.barHeight,
        }}
        vpConfig={{
          color: volumeProfileConfig.color,
          widthPercent: volumeProfileConfig.widthPercent,
          rowsLayout: volumeProfileConfig.rowsLayout,
          rowSize: volumeProfileConfig.rowSize,
          transparency: volumeProfileConfig.transparency,
        }}
      />
    );
  }, [dgArtifact, dgConfig?.enabled, showVolumeProfile, showGex, showStructuralLines, backdropOpacity, gexByStrike, gexConfig, volumeProfileConfig]);

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

  // Calculate time machine limits based on ACTUAL hours remaining until expiration
  // Compute dynamically from expiration date to avoid stale DTE snapshots
  const visibleStrategies = strategies.filter(s => s.visible);
  const now = new Date();

  // Find the earliest expiration across visible strategies and compute hours remaining
  const expirations = visibleStrategies
    .map(s => s.expiration)
    .filter((e): e is string => !!e);

  let actualHoursRemaining: number;
  if (expirations.length > 0) {
    // Parse expiration dates with 4pm ET close, find the minimum
    const hoursPerExpiration = expirations.map(exp => {
      // Normalize to YYYY-MM-DD (handles ISO datetime strings from API)
      const expDateStr = String(exp).split('T')[0];
      const expClose = new Date(expDateStr + 'T16:00:00-05:00');
      return (expClose.getTime() - now.getTime()) / (1000 * 60 * 60);
    });
    actualHoursRemaining = Math.max(0.5, Math.max(...hoursPerExpiration));
  } else {
    // Fallback: use static dte
    const minDTE = visibleStrategies.length > 0
      ? Math.min(...visibleStrategies.map(s => s.dte))
      : 1;
    actualHoursRemaining = minDTE === 0 ? 0.5 : minDTE * 24;
  }

  const maxHours = actualHoursRemaining;
  const hoursRemaining = maxHours - simTimeOffsetHours;
  const effectiveHoursRemaining = Math.max(0, hoursRemaining);

  // Progressive time slider mapping using exponential curve
  // This provides more resolution near expiration without zone discontinuities
  // The curve parameter controls how much to favor resolution near expiration
  // Higher values = more resolution near expiration, less in the middle
  const CURVE_EXPONENT = 2.5;

  // Convert hours offset to slider position (0-100)
  // Uses power curve: position = (hours/maxHours)^(1/exp) * 100
  const hoursToSlider = useCallback((hours: number): number => {
    if (hours <= 0) return 0;
    if (hours >= maxHours) return 100;

    // Normalized offset (0 = now, 1 = expiration)
    const t = hours / maxHours;
    // Apply inverse power curve for slider position
    return Math.pow(t, 1 / CURVE_EXPONENT) * 100;
  }, [maxHours]);

  // Convert slider position (0-100) to hours offset
  // Inverse: hours = (position/100)^exp * maxHours
  const sliderToHours = useCallback((position: number): number => {
    if (position <= 0) return 0;
    if (position >= 100) return maxHours;

    // Normalized position (0-1)
    const t = position / 100;
    // Apply power curve for hours
    return Math.pow(t, CURVE_EXPONENT) * maxHours;
  }, [maxHours]);

  // Current slider position
  const sliderPosition = hoursToSlider(simTimeOffsetHours);

  // Compute expiration markers for the time slider
  // Shows where each position expires relative to the slider range
  const expirationMarkers = useMemo(() => {
    if (!timeMachineEnabled) return [];
    const markers: Array<{ position: number; label: string; expired: boolean }> = [];
    const seen = new Set<string>(); // dedupe by expiration date
    for (const s of visibleStrategies) {
      if (!s.expiration || seen.has(s.expiration)) continue;
      seen.add(s.expiration);
      const expClose = new Date(s.expiration + 'T16:00:00-05:00');
      const hoursToExp = (expClose.getTime() - now.getTime()) / (1000 * 60 * 60);
      if (hoursToExp <= 0 || hoursToExp >= maxHours) continue; // skip if at boundary
      const sliderPos = hoursToSlider(hoursToExp);
      const dateLabel = s.expiration.slice(5); // "MM-DD"
      markers.push({
        position: sliderPos,
        label: dateLabel,
        expired: simTimeOffsetHours >= hoursToExp,
      });
    }
    return markers;
  }, [visibleStrategies, timeMachineEnabled, maxHours, hoursToSlider, now, simTimeOffsetHours]);

  // Handle slider change with progressive mapping
  const handleTimeSliderChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const position = parseFloat(e.target.value);
    const hours = sliderToHours(position);
    onSimTimeChange(hours);
  }, [sliderToHours, onSimTimeChange]);

  return (
    <div className="panel echarts-risk-graph-panel">
      <div className="panel-header">
        <h3>Risk Graph {strategies.length > 0 && `(${strategies.length})`}</h3>
        {underlyings.length > 1 && (
          <div className="weighting-selector">
            {underlyings.map(sym => (
              <button
                key={sym}
                className={`weighting-btn ${sym === effectiveWeightingIndex ? 'active' : ''}`}
                onClick={() => setWeightingIndex(sym)}
                title={`Weight chart to ${sym} prices`}
              >
                {sym}
              </button>
            ))}
          </div>
        )}
        <WhatsNew area="risk-graph" className="whats-new-apple" />
        <div className="panel-header-actions">
          {/* Dealer Gravity Backdrop Controls */}
          {(dgArtifact || (gexByStrike && Object.keys(gexByStrike).length > 0)) && (
            <div className="backdrop-controls" title="Dealer Gravity Backdrop">
              <label className="backdrop-toggle-label" title="Toggle Volume Profile">
                <input type="checkbox" checked={showVolumeProfile} onChange={() => setShowVolumeProfile(!showVolumeProfile)} />
                <span>VP</span>
              </label>
              <label className="backdrop-toggle-label" title="Toggle Structural Lines (Volume Nodes, Wells, Crevasses)">
                <input type="checkbox" checked={showStructuralLines} onChange={() => setShowStructuralLines(!showStructuralLines)} />
                <span>DG</span>
              </label>
              <label className="backdrop-toggle-label" title="Toggle GEX (Gamma Exposure)">
                <input type="checkbox" checked={showGex} onChange={() => setShowGex(!showGex)} />
                <span>GEX</span>
              </label>
              <input
                type="range"
                className="backdrop-opacity-slider"
                min="0"
                max="100"
                value={backdropOpacity * 100}
                onChange={(e) => setBackdropOpacity(Number(e.target.value) / 100)}
                title={`Backdrop Opacity: ${Math.round(backdropOpacity * 100)}%`}
              />
              <button
                className="btn-backdrop-settings"
                onClick={() => setShowDGSettings(true)}
                title="Dealer Gravity Settings"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
                </svg>
              </button>
            </div>
          )}
          {onOpenMonitor && (
            <button
              className="btn-monitor"
              onClick={onOpenMonitor}
              title="Open Position Monitor"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                <line x1="8" y1="21" x2="16" y2="21"/>
                <line x1="12" y1="17" x2="12" y2="21"/>
              </svg>
              {(pendingOrderCount > 0 || openTradeCount > 0) && (
                <span className="monitor-badge">{pendingOrderCount + openTradeCount}</span>
              )}
            </button>
          )}
          {strategies.length > 0 && (
            <button
              className="btn-auto-fit-header"
              onClick={() => pnlChartRef.current?.autoFit()}
            >
              Auto-Fit
            </button>
          )}
        </div>
      </div>
      <div className={`panel-content risk-graph-consolidated${strategies.length === 0 ? ' empty-state' : ''}`}>
          {/* Main content: Chart + Sidebar */}
          <div className="risk-graph-main">
            {/* Chart Area */}
            <div className="risk-graph-chart-area">
              {strategies.length === 0 ? (
                <div className="risk-graph-chart-empty">
                  <div className="chart-empty-content">
                    <p className="empty-title">Add a position to begin analysis</p>
                    <p className="empty-hint">Click a heatmap tile → "Add to Risk Graph"</p>
                    {onCreatePosition && (
                      <button className="btn-import-tos-empty" onClick={onCreatePosition}>
                        + Create Position
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <PnLChart
                  ref={pnlChartRef}
                  expirationData={pnlChartData.expirationPoints}
                  theoreticalData={pnlChartData.theoreticalPoints}
                  spotPrice={simulatedSpot}
                  expirationBreakevens={pnlChartData.expirationBreakevens}
                  theoreticalBreakevens={pnlChartData.theoreticalBreakevens}
                  strikes={chartStrikes}
                  onOpenAlertDialog={handleOpenAlertDialog}
                  alertLines={alertLinesForChart}
                  expiredExpirationData={pnlChartData.expiredExpirationPoints}
                  expiredTheoreticalData={pnlChartData.expiredTheoreticalPoints}
                  renderBackdrop={renderBackdrop}
                />
              )}
            </div>
          </div>

          {/* Sidebar: Positions + Alerts */}
          <div className="risk-graph-sidebar">
                {/* Position List */}
                <div className="risk-graph-strategies">
                  <div className="section-header">
                    Positions
                    <div className="section-header-actions">
                      {onCreatePosition && (
                        <button
                          className="btn-create-position"
                          title="Create new position"
                          onClick={(e) => {
                            e.stopPropagation();
                            onCreatePosition();
                          }}
                        >
                          + Create
                        </button>
                      )}
                      {hasAnalyzerInteraction && onOpenJournal && (
                        <button
                          className="reflect-hook analyzer-reflect"
                          title="Capture an insight?"
                          onClick={(e) => {
                            e.stopPropagation();
                            setHasAnalyzerInteraction(false);
                            onOpenJournal();
                          }}
                        >
                          📝
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="strategies-list">
                    {strategies.map(strat => {
                      // Derive legs from strategy if not already provided
                      const legs = strat.legs || strategyToLegs(
                        strat.strategy,
                        strat.side,
                        strat.strike,
                        strat.width,
                        strat.expiration
                      );

                      // Recognize position type from legs
                      const recognition = strat.positionType
                        ? { type: strat.positionType, direction: strat.direction || 'long', isSymmetric: true }
                        : recognizePositionType(legs);

                      const positionType = recognition.type;
                      const direction = recognition.direction;
                      const isAsymmetric = recognition.isSymmetric === false;

                      // Format display values
                      const positionLabel = formatPositionLabel(positionType, direction, legs);
                      const legsNotation = formatLegsDisplay(legs);

                      // Determine cost basis
                      const costBasis = strat.costBasis ?? strat.debit ?? null;

                      // Lock/unlock state: locked = user-entered price, unlocked = model price
                      const isLocked = priceLocked[strat.id] ?? false;
                      const theoValue = pnlChartData.strategyTheoValues[strat.id];

                      // Derive credit/debit from the sign of the active value
                      // Negative value = credit in both locked and unlocked modes
                      const activeValue = isLocked ? costBasis : theoValue;
                      const isCredit = activeValue != null ? activeValue < 0 : (strat.costBasisType === 'credit');
                      const displayPrice = activeValue != null ? Math.abs(activeValue) : null;

                      return (
                        <div key={strat.id} className={`risk-graph-position-item ${!strat.visible ? 'hidden-position' : ''} ${strat.visible && !pnlChartData.activeStrategyIds.includes(strat.id) ? 'sim-expired' : ''} ${isCredit ? 'credit-tint' : 'debit-tint'}`}>
                          <div className="position-content">
                            {/* Header Row: Symbol, Label, DTE, Lock + Cost Basis */}
                            <div className="position-row-header">
                              {strat.symbol && (
                                <span className="position-symbol" title={strat.symbol}>
                                  {strat.symbol}
                                </span>
                              )}
                              <span className="position-label" title={positionLabel}>
                                {positionLabel}
                              </span>
                              <span className="position-dte" title={`${strat.dte} days to expiration`}>
                                {strat.dte}d
                              </span>
                              {/* Lock/Unlock Toggle */}
                              <button
                                className={`btn-price-lock ${isLocked ? 'locked' : 'unlocked'}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  // When unlocking, save current theo value as the debit so re-lock preserves it
                                  if (isLocked && theoValue != null) {
                                    // Transitioning to unlocked — no debit update needed, hook uses theo
                                  } else if (!isLocked && theoValue != null) {
                                    // Re-locking — persist the last theo value as debit
                                    onUpdateStrategyDebit(strat.id, theoValue);
                                  }
                                  togglePriceLock(strat.id);
                                }}
                                title={isLocked ? 'Price locked — click to use model price' : 'Using model price — click to lock'}
                              >
                                {isLocked ? (
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                                    <rect x="3" y="11" width="18" height="12" rx="2" />
                                    <path d="M7 11V7a5 5 0 0 1 10 0v4" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                                  </svg>
                                ) : (
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                                    <rect x="3" y="11" width="18" height="12" rx="2" />
                                    <path d="M7 11V7a5 5 0 0 1 10 0" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" transform="rotate(-30, 17, 7) translate(3, -4)" />
                                  </svg>
                                )}
                              </button>
                              {/* Price field */}
                              <span className="position-cost-basis">
                                <span className="cost-value">
                                  ${isLocked ? (
                                    <input
                                      type="number"
                                      className="debit-input"
                                      defaultValue={costBasis !== null ? Math.abs(costBasis).toFixed(2) : ''}
                                      key={`debit-${strat.id}-${costBasis}-locked`}
                                      step="0.01"
                                      min="0"
                                      placeholder="0.00"
                                      onBlur={(e) => {
                                        const val = parseFloat(e.target.value);
                                        setHasAnalyzerInteraction(true);
                                        onUpdateStrategyDebit(strat.id, isNaN(val) ? null : val);
                                      }}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                          e.currentTarget.blur();
                                        }
                                      }}
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                  ) : (
                                    <input
                                      type="number"
                                      className="debit-input"
                                      value={theoValue != null ? Math.abs(theoValue).toFixed(2) : ''}
                                      key={`debit-${strat.id}-unlocked`}
                                      step="0.01"
                                      min="0"
                                      placeholder="—"
                                      readOnly
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                  )}
                                </span>
                                <span className="cost-type-label">{isCredit ? 'Credit' : 'Debit'}</span>
                                {isLocked && theoValue != null && (() => {
                                  // P&L: for debits, lower theo = loss, higher = gain
                                  // For credits, the signs are already negative, so compare directly
                                  const lockedVal = costBasis ?? 0;
                                  const pnl = theoValue - lockedVal; // positive = position gained value
                                  const pnlColor = Math.abs(pnl) < 0.005 ? 'var(--text-faint)' : pnl > 0 ? '#22c55e' : '#ef4444';
                                  return (
                                    <span className="natural-price" style={{ color: pnlColor }}>
                                      ${Math.abs(theoValue).toFixed(2)}
                                    </span>
                                  );
                                })()}
                              </span>
                            </div>

                            {/* Legs Row: Leg notation */}
                            <div className="position-row-legs">
                              <span className="position-legs-notation" title={legsNotation}>
                                {legsNotation}
                              </span>
                              {isAsymmetric && (
                                <span className="position-asym-badge" title="Asymmetric wing widths">
                                  asym
                                </span>
                              )}
                            </div>

                            {/* Actions Row */}
                            <div className="position-row-actions">
                              <button
                                className={`btn-toggle-visibility ${strat.visible ? 'visible' : 'hidden'}`}
                                onClick={() => {
                                  setHasAnalyzerInteraction(true);
                                  onToggleStrategyVisibility(strat.id);
                                }}
                                title={strat.visible ? 'Hide from chart' : 'Show on chart'}
                              >
                                {strat.visible ? 'Hide' : 'Show'}
                              </button>
                              {onEditStrategy && (
                                <button
                                  className="btn-edit-strategy"
                                  onClick={() => onEditStrategy(strat.id)}
                                  title="Edit position"
                                >
                                  Edit
                                </button>
                              )}
                              <button
                                className="btn-alert"
                                onClick={() => onStartNewAlert(strat.id)}
                                title="Create alert for this position"
                              >
                                Alert
                              </button>
                              {onLogTrade && (
                                <button
                                  className="btn-log-trade"
                                  onClick={() => onLogTrade(strat)}
                                  title="Log trade with this position"
                                >
                                  Log
                                </button>
                              )}
                              <button
                                className="btn-remove"
                                onClick={() => onRemoveStrategy(strat.id)}
                                title="Remove position"
                              >
                                ×
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    {strategies.length === 0 && (
                      <div className="strategies-empty">
                        No positions loaded
                      </div>
                    )}
                  </div>
                </div>

                {/* Algo Alerts Section */}
                <AlgoAlertPanel
                  positionIds={strategies.map(s => s.id)}
                />

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
                    {alerts.map(alert => {
                      const isAI = alert.type.startsWith('ai_');
                      const val = Number(alert.targetValue);
                      const alertLabel = (() => {
                        switch (alert.type) {
                          case 'price':
                            const op = alert.condition === 'above' ? '≥' : alert.condition === 'below' ? '≤' : '≈';
                            return `Price ${op} ${val.toFixed(0)}`;
                          case 'debit':
                            return `Debit ≤ $${val.toFixed(2)}`;
                          case 'profit_target':
                            return `Profit ≥ $${val.toFixed(0)}`;
                          case 'trailing_stop':
                            return `Trail -$${val.toFixed(0)}`;
                          case 'ai_theta_gamma':
                            if (alert.isZoneActive && alert.zoneLow && alert.zoneHigh) {
                              return `Zone ${alert.zoneLow.toFixed(0)}–${alert.zoneHigh.toFixed(0)}`;
                            }
                            return `T/G Zone (${((alert.minProfitThreshold || 0.5) * 100).toFixed(0)}% to arm)`;
                          case 'ai_sentiment':
                            return 'Sentiment Shift';
                          case 'ai_risk_zone':
                            return 'Risk Zone Exit';
                          default:
                            return alert.type;
                        }
                      })();

                      return (
                        <div
                          key={alert.id}
                          className={`alert-item clickable ${alert.triggered ? 'triggered' : ''} ${!alert.enabled ? 'disabled' : ''} ${isAI ? 'ai-alert' : ''}`}
                          onClick={() => onStartEditingAlert(alert.id)}
                          title={`Click to edit${alert.triggered ? ' (triggered)' : ''}`}
                        >
                          <div className="alert-info">
                            <div
                              className="alert-color-dot"
                              style={{ backgroundColor: alert.color || ALERT_COLOR_PALETTE[0] }}
                            />
                            {isAI && <span className="alert-ai-badge">AI</span>}
                            <span className="alert-condition">{alertLabel}</span>
                          </div>
                          <button
                            className="btn-delete-alert"
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteAlert(alert.id);
                            }}
                            title="Delete alert"
                          >
                            ×
                          </button>
                        </div>
                      );
                    })}

                    {/* Price Line Alerts */}
                    {priceAlertLines.map(alert => (
                      <div key={alert.id} className="alert-item price-line-alert" title="Visual price line (no notification)">
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
                          title="Remove price line"
                        >
                          ×
                        </button>
                      </div>
                    ))}

                    {alerts.length === 0 && priceAlertLines.length === 0 && (
                      <div className="alerts-empty">
                        No alerts set
                        <span className="hint">Right-click chart to add price alerts</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Simulation Controls */}
              <div className={`time-machine-panel ${timeMachineEnabled ? 'active' : ''}`}>
                <div className="time-machine-header">
                  <div className="time-machine-switch">
                    <label className="toggle-switch live-whatif-toggle">
                      <span className={`toggle-label-live ${!timeMachineEnabled ? 'active' : ''}`}>
                        <span className="live-dot" />
                        Live
                      </span>
                      <div className="toggle-track" onClick={onTimeMachineToggle}>
                        <div className={`toggle-thumb ${timeMachineEnabled ? 'on' : ''}`} />
                      </div>
                      <span className={`toggle-label-whatif ${timeMachineEnabled ? 'active' : ''}`}>What-If</span>
                    </label>
                    {!timeMachineEnabled && (
                      <span className="live-price">{weightingSpot.toFixed(2)}</span>
                    )}
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
                      {/* Expiration markers above slider */}
                      {expirationMarkers.length > 0 && (
                        <div className="expiration-markers">
                          {expirationMarkers.map(m => (
                            <div
                              key={m.label}
                              className={`exp-marker ${m.expired ? 'expired' : ''}`}
                              style={{ left: `${m.position}%` }}
                              title={`Expires ${m.label}`}
                            >
                              <span className="exp-marker-line" />
                              <span className="exp-marker-label">{m.label}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="slider-row">
                        <span className="control-label">Time</span>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="0.1"
                          value={sliderPosition}
                          onChange={handleTimeSliderChange}
                          className="time-slider progressive"
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
                            min="-10"
                            max="10"
                            step="0.1"
                            value={simSpotPct}
                            onChange={(e) => onSimSpotPctChange(parseFloat(e.target.value))}
                            className="spot-slider"
                            disabled={!timeMachineEnabled}
                          />
                          <div
                            className="thumb-value"
                            style={{ left: `${((simSpotPct + 10) / 20) * 100}%` }}
                          >
                            {simSpotPct >= 0 ? '+' : ''}{simSpotPct.toFixed(1)}%
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="vertical-control vol-control">
                    <div className="vol-label-left">
                      <span className="vol-label-text">VIX</span>
                      {isEditingVix ? (
                        <input
                          ref={vixInputRef}
                          type="number"
                          className="vol-value-input"
                          value={vixInputValue}
                          onChange={(e) => setVixInputValue(e.target.value)}
                          onBlur={handleVixInputBlur}
                          onKeyDown={handleVixInputKeyDown}
                          min="5"
                          max="80"
                          step="0.1"
                        />
                      ) : (
                        <span
                          className="vol-value"
                          onClick={handleVixClick}
                          title={timeMachineEnabled ? "Click to edit" : "Enable simulation to edit"}
                        >
                          {currentVix.toFixed(1)}
                        </span>
                      )}
                    </div>
                    <div className="vertical-slider-container">
                      <input
                        type="range"
                        min="5"
                        max="80"
                        step="0.5"
                        value={currentVix}
                        onChange={(e) => {
                          const newVix = parseFloat(e.target.value);
                          onSimVolatilityChange(newVix - vix);
                        }}
                        className="vol-slider-vertical"
                        disabled={!timeMachineEnabled}
                      />
                    </div>
                  </div>
                  <div className="regime-control">
                    <div className="regime-description-row">
                      <div
                        className="regime-indicator"
                        style={{ backgroundColor: regimeConfig.color }}
                      />
                      <span className="regime-description">{regimeConfig.description}</span>
                    </div>
                    <div className="regime-select-row">
                      <span className="regime-label">Regime</span>
                      <select
                        className="regime-select"
                        value={marketRegime}
                        onChange={(e) => setMarketRegime(e.target.value as MarketRegime)}
                        disabled={!timeMachineEnabled}
                      >
                        {(Object.keys(MARKET_REGIMES) as MarketRegime[]).map((key) => (
                          <option key={key} value={key}>
                            {MARKET_REGIMES[key].name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="pricing-model-control">
                    <div className="model-description-row">
                      <div
                        className="model-indicator"
                        style={{ backgroundColor: pricingModelConfig.color }}
                      />
                      <span className="model-description">{pricingModelConfig.description}</span>
                    </div>
                    <div className="model-select-row">
                      <span className="model-label">Model</span>
                      <select
                        className="model-select"
                        value={pricingModel}
                        onChange={(e) => setPricingModel(e.target.value as PricingModel)}
                        disabled={!timeMachineEnabled}
                      >
                        {(Object.keys(PRICING_MODELS) as PricingModel[]).map((key) => (
                          <option key={key} value={key}>
                            {PRICING_MODELS[key].name}
                          </option>
                        ))}
                      </select>
                    </div>
                    {/* Model-specific parameters */}
                    {pricingModel === 'heston' && timeMachineEnabled && (
                      <div className="model-params">
                        <div className="param-row">
                          <span className="param-label" title="Volatility of Volatility - How much vol itself varies">ξ</span>
                          <input
                            type="range"
                            min="0.1"
                            max="1.0"
                            step="0.05"
                            value={hestonVolOfVol}
                            onChange={(e) => setHestonVolOfVol(parseFloat(e.target.value))}
                            className="param-slider"
                          />
                          <span className="param-value">{hestonVolOfVol.toFixed(2)}</span>
                        </div>
                        <div className="param-row">
                          <span className="param-label" title="Correlation between spot and vol (negative = leverage effect)">ρ</span>
                          <input
                            type="range"
                            min="-0.95"
                            max="0"
                            step="0.05"
                            value={hestonCorrelation}
                            onChange={(e) => setHestonCorrelation(parseFloat(e.target.value))}
                            className="param-slider"
                          />
                          <span className="param-value">{hestonCorrelation.toFixed(2)}</span>
                        </div>
                      </div>
                    )}
                    {pricingModel === 'monte-carlo' && timeMachineEnabled && (
                      <div className="model-params">
                        <div className="param-row">
                          <span className="param-label" title="Number of simulation paths">Paths</span>
                          <input
                            type="range"
                            min="1000"
                            max="20000"
                            step="1000"
                            value={mcNumPaths}
                            onChange={(e) => setMcNumPaths(parseInt(e.target.value))}
                            className="param-slider"
                          />
                          <span className="param-value">{(mcNumPaths / 1000).toFixed(0)}k</span>
                        </div>
                      </div>
                    )}
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
                        {pnl >= 0 ? '+' : ''}${pnl.toFixed(0)}
                      </span>
                    );
                  })()}
                </div>
                <div className="stat-divider" />
                <div className="stat">
                  <span className="stat-label">Max Profit</span>
                  <span className="stat-value profit">
                    +${riskGraphData.maxPnL.toFixed(0)}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Max Loss</span>
                  <span className="stat-value loss">${riskGraphData.minPnL.toFixed(0)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">R2R</span>
                  <span className="stat-value">
                    {(() => {
                      const visible = strategies.filter(s => s.visible && s.debit && s.debit > 0);
                      if (visible.length === 0) return '-';
                      const totalMaxProfit = visible.reduce((sum, s) => sum + (s.width - s.debit!), 0);
                      const totalDebit = visible.reduce((sum, s) => sum + s.debit!, 0);
                      if (totalDebit <= 0) return '-';
                      const r2r = totalMaxProfit / totalDebit;
                      return r2r.toFixed(1);
                    })()}
                  </span>
                </div>
                <div className="stat-divider" />
                <div className="stat">
                  <span className="stat-label">Delta</span>
                  <span className={`stat-value ${pnlChartData.delta >= 0 ? 'profit' : 'loss'}`}>
                    {pnlChartData.delta >= 0 ? '+' : ''}{pnlChartData.delta.toFixed(1)}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Gamma</span>
                  <span className="stat-value">{pnlChartData.gamma.toFixed(2)}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Theta</span>
                  <span className={`stat-value ${pnlChartData.theta >= 0 ? 'profit' : 'loss'}`}>
                    {pnlChartData.theta >= 0 ? '+' : ''}${pnlChartData.theta.toFixed(0)}/day
                  </span>
                </div>
                {timeMachineEnabled && (
                  <>
                    <div className="stat-divider" />
                    <div className="stat simulation-indicator">
                      <span className="stat-label">Simulation</span>
                      <span className="stat-value">
                        {simSpotPct !== 0 && <span className="sim-param">Spot {simSpotPct > 0 ? '+' : ''}{simSpotPct.toFixed(1)}%</span>}
                        {simTimeOffsetHours > 0 && <span className="sim-param">-{formatDTE(simTimeOffsetHours)} decay</span>}
                        {simVolatilityOffset !== 0 && <span className="sim-param">Vol {simVolatilityOffset > 0 ? '+' : ''}{simVolatilityOffset.toFixed(1)}</span>}
                      </span>
                    </div>
                  </>
                )}
              </div>
        </div>

        {/* Dealer Gravity Settings Modal */}
        <DealerGravitySettings
          isOpen={showDGSettings}
          onClose={() => setShowDGSettings(false)}
        />
    </div>
  );
});

export default RiskGraphPanel;
