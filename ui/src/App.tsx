import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { marked } from 'marked';
import './App.css';

// Configure marked for markdown rendering
marked.setOptions({ breaks: true, gfm: true });
import './styles/mel.css';
import './styles/commentary.css';
import './styles/path-indicator.css';
import PathIndicator from './components/PathIndicator';
import WelcomeTour from './components/WelcomeTour';
import LightweightPriceChart from './components/LightweightPriceChart';
import MELStatusBar from './components/MELStatusBar';
import { useMEL } from './hooks/useMEL';
import type { RawSnapshot } from './components/LightweightPriceChart';
import BiasLfiQuadrantCard from './components/BiasLfiQuadrantCard';
import MarketModeGaugeCard from './components/MarketModeGaugeCard';
import VixRegimeCard from './components/VixRegimeCard';
import TradeLogPanel, { type TradeReflectionContext } from './components/TradeLogPanel';
import type { Trade } from './components/TradeLogPanel';
import type { TradeLog } from './components/LogSelector';
import TradeEntryModal from './components/TradeEntryModal';
import type { TradeEntryData } from './components/TradeEntryModal';
import LogManagerModal from './components/LogManagerModal';
import TradeDetailModal from './components/TradeDetailModal';
import ReportingView from './components/ReportingView';
import SettingsModal from './components/SettingsModal';
import JournalView from './components/JournalView';
import PlaybookView from './components/PlaybookView';
import AlertCreationModal, { type EditingAlertData } from './components/AlertCreationModal';
import RiskGraphPanel from './components/RiskGraphPanel';
import TosImportModal from './components/TosImportModal';
import StrategyEditModal, { type StrategyData } from './components/StrategyEditModal';
import type { ParsedStrategy } from './utils/tosParser';
import { useAlerts } from './contexts/AlertContext';
import { usePath } from './contexts/PathContext';
import type { AlertType, AlertBehavior } from './types/alerts';
import ObserverPanel from './components/ObserverPanel';
import GexChartPanel from './components/GexChartPanel';
import TradeRecommendationsPanel from './components/TradeRecommendationsPanel';
import TradeTrackingPanel from './components/TradeTrackingPanel';
import TrackingAnalyticsDashboard from './components/TrackingAnalyticsDashboard';
import LeaderboardView from './components/LeaderboardView';
import MonitorPanel from './components/MonitorPanel';
import { VolumeProfileSettings, useIndicatorSettings, sigmaToPercentile } from './components/chart-primitives';
import type { TradeSelectorModel, TradeRecommendation } from './types/tradeSelector';

const SSE_BASE = ''; // Use relative URLs - Vite proxy handles /api/* and /sse/*

type Strategy = 'single' | 'vertical' | 'butterfly';
type GexMode = 'combined' | 'net';
type Side = 'call' | 'put' | 'both';

interface SpotData {
  [symbol: string]: { value: number; ts: string; symbol: string };
}

interface HeatmapTile {
  symbol: string;
  strategy: string;
  dte: number;
  strike: number;
  width: number;
  call?: { mid?: number; debit?: number };
  put?: { mid?: number; debit?: number };
}

interface HeatmapData {
  ts: number;
  symbol: string;
  version?: number;
  dtes_available?: number[];
  tiles: Record<string, HeatmapTile>;
}

interface GexData {
  symbol: string;
  ts: number;
  expirations: Record<string, Record<string, number>>;
}

interface VolumeProfileLevel {
  price: number;
  volume: number;
}

interface VolumeProfileData {
  levels: VolumeProfileLevel[];
  maxVolume: number;
  meta?: Record<string, string>;
}

// Vexy commentary data
interface VexyMessage {
  kind: 'epoch' | 'event';
  text: string;
  meta: Record<string, unknown>;
  ts: string;
  voice: string;
}

interface VexyData {
  epoch: VexyMessage | null;
  event: VexyMessage | null;
}

// Bias/LFI model data
interface BiasLfiData {
  directional_strength: number;
  lfi_score: number;
  ts?: string;
}

// Market Mode model data
interface MarketModeData {
  score: number;
  mode: 'compression' | 'transition' | 'expansion';
  ts?: string;
}

// User profile for header greeting
interface UserProfile {
  display_name: string;
  is_admin: boolean;
}

// Strategy details for popup/risk graph (side is always 'call' or 'put', never 'both')
interface SelectedStrategy {
  strategy: Strategy;
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
  symbol?: string;
}

interface RiskGraphStrategy extends SelectedStrategy {
  id: string;
  addedAt: number;
  visible: boolean;
}

// Legacy RiskGraphAlert for local alert evaluation (will be migrated to backend)
interface RiskGraphAlert {
  id: string;
  strategyId: string;
  type: AlertType;
  condition: 'above' | 'below' | 'at';
  targetValue: number;
  enabled: boolean;
  triggered: boolean;
  triggeredAt?: number;
  createdAt: number;
  // Snapshot of strategy info for display
  strategyLabel: string;
  // For trailing stop
  highWaterMark?: number;
  // Visual customization
  color: string;
  // Behavior when triggered
  behavior: AlertBehavior;
  // Track if price was previously on the other side (for repeat alerts)
  wasOnOtherSide?: boolean;
  // AI Theta/Gamma specific fields
  minProfitThreshold?: number;  // Default 0.5 (50% of debit)
  entryDebit?: number;          // Debit when alert was created
  highWaterMarkProfit?: number; // Highest profit achieved
  zoneLow?: number;             // Current safe zone lower bound (price)
  zoneHigh?: number;            // Current safe zone upper bound (price)
  isZoneActive?: boolean;       // Whether minimum profit threshold was met
}

// Visual price alert line on risk graph
interface PriceAlertLine {
  id: string;
  price: number;
  color: string;
  label?: string;
  createdAt: number;
}



/**
 * Throttle function - limits how often a function can be called
 * Returns the throttled function and a flush function to force immediate execution
 */
function createThrottle<T>(fn: (value: T) => void, limitMs: number): {
  throttled: (value: T) => void;
  flush: () => void;
} {
  let lastValue: T | undefined;
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let lastCall = 0;

  const throttled = (value: T) => {
    lastValue = value;
    const now = Date.now();
    const timeSinceLastCall = now - lastCall;

    if (timeSinceLastCall >= limitMs) {
      // Enough time has passed, call immediately
      lastCall = now;
      fn(value);
    } else if (!timeoutId) {
      // Schedule a call for when the throttle period ends
      timeoutId = setTimeout(() => {
        lastCall = Date.now();
        timeoutId = null;
        if (lastValue !== undefined) {
          fn(lastValue);
        }
      }, limitMs - timeSinceLastCall);
    }
    // If timeout already scheduled, just update lastValue (it will use latest)
  };

  const flush = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
    if (lastValue !== undefined) {
      lastCall = Date.now();
      fn(lastValue);
    }
  };

  return { throttled, flush };
}

/**
 * Calculate Volume Profile using TradingView's VRVP algorithm
 * Divides price range into N bins and accumulates volume into each bin
 */
function calculateVolumeProfileBins(
  levels: { price: number; volume: number }[],
  numBins: number
): { price: number; volume: number }[] {
  if (levels.length === 0) return [];

  // Find price range
  const prices = levels.map(l => l.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice;

  if (priceRange <= 0) return levels;

  // Clamp numBins to valid range
  const effectiveBins = Math.max(20, Math.min(1000, numBins));

  // TradingView formula: bin size = (High - Low) / Number of Rows
  const binSize = priceRange / effectiveBins;

  // Initialize bins
  const bins: number[] = new Array(effectiveBins).fill(0);

  // Assign each data point's volume to its bin
  for (const level of levels) {
    let binIndex = Math.floor((level.price - minPrice) / binSize);
    // Handle edge case where price equals maxPrice
    if (binIndex >= effectiveBins) binIndex = effectiveBins - 1;
    if (binIndex < 0) binIndex = 0;
    bins[binIndex] += level.volume;
  }

  // Convert bins back to levels with price at bin center
  const rebinnedLevels: { price: number; volume: number }[] = [];
  for (let i = 0; i < effectiveBins; i++) {
    if (bins[i] > 0) {
      const price = minPrice + (i + 0.5) * binSize; // Center of bin
      rebinnedLevels.push({ price, volume: bins[i] });
    }
  }

  return rebinnedLevels;
}

// Width options per strategy, per underlying
const WIDTHS: Record<string, Record<Strategy, number[]>> = {
  'I:SPX': {
    single: [0],
    vertical: [20, 25, 30, 35, 40, 45, 50],
    butterfly: [20, 25, 30, 35, 40, 45, 50],
  },
  'I:NDX': {
    single: [0],
    vertical: [50, 100, 150, 200],
    butterfly: [50, 100, 150, 200],
  },
};

// Strike increment per underlying
const STRIKE_INCREMENT: Record<string, number> = {
  'I:SPX': 5,
  'I:NDX': 50,
};

// Standard normal CDF approximation
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
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);

  return 0.5 * (1.0 + sign * y);
}

// Black-Scholes option pricing
function blackScholes(
  S: number,      // Underlying price
  K: number,      // Strike price
  T: number,      // Time to expiration in years
  r: number,      // Risk-free rate
  sigma: number,  // Volatility
  isCall: boolean
): number {
  if (T <= 0) {
    // At expiration, return intrinsic value
    return isCall ? Math.max(0, S - K) : Math.max(0, K - S);
  }

  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);

  if (isCall) {
    return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);
  } else {
    return K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);
  }
}

// Calculate actual time to expiration in years (calendar time for Black-Scholes)
// SPX options expire at 4:00 PM ET (market close)
function getTimeToExpiration(dte: number): number {
  const now = new Date();

  // Get current time in ET using Intl API (handles DST automatically)
  const etTimeStr = now.toLocaleString('en-US', { timeZone: 'America/New_York', hour12: false });
  const etTimeParts = etTimeStr.split(', ')[1]?.split(':') || ['12', '0'];
  const etHours = parseInt(etTimeParts[0]) + parseInt(etTimeParts[1]) / 60;

  // Market close is 16:00 ET (4 PM)
  const marketCloseHour = 16;

  // Calculate hours until today's market close
  const hoursUntilClose = Math.max(0, marketCloseHour - etHours);

  if (dte === 0) {
    // 0-DTE: convert hours to calendar years
    // T = hours / 24 / 365 (calendar time for Black-Scholes)
    // Minimum of ~1 minute to avoid numerical issues
    return Math.max(1 / 24 / 365, hoursUntilClose / 24 / 365);
  }

  // For DTE > 0: full calendar days plus hours until close
  // Each DTE is a calendar day
  const calendarDays = dte + hoursUntilClose / 24;
  return calendarDays / 365;
}

// Calculate theoretical P&L for a strategy at given underlying price (before expiration)
// timeOffsetHours: optional hours forward from now (for time machine simulation)
function calculateStrategyTheoreticalPnL(
  strat: { strategy: Strategy; side: Side; strike: number; width: number; debit: number | null; dte: number },
  underlyingPrice: number,
  volatility: number,
  riskFreeRate: number = 0.05,
  timeOffsetHours: number = 0
): number {
  const debit = strat.debit ?? 0;
  const multiplier = 100;
  // Get base time to expiration, then subtract simulated hours
  const baseT = getTimeToExpiration(strat.dte);
  const offsetYears = timeOffsetHours / (24 * 365);
  const T = Math.max(0.0001, baseT - offsetYears); // Don't go below ~1 minute
  const isCall = strat.side === 'call';

  if (strat.strategy === 'single') {
    const value = blackScholes(underlyingPrice, strat.strike, T, riskFreeRate, volatility, isCall);
    // Single option value cannot be negative
    const clampedValue = Math.max(0, value);
    // P&L cannot be worse than losing the premium paid
    const pnl = (clampedValue - debit) * multiplier;
    const maxLoss = -debit * multiplier;
    return Math.max(maxLoss, pnl);
  }

  if (strat.strategy === 'vertical') {
    const longStrike = strat.strike;
    const shortStrike = isCall ? strat.strike + strat.width : strat.strike - strat.width;
    const longValue = blackScholes(underlyingPrice, longStrike, T, riskFreeRate, volatility, isCall);
    const shortValue = blackScholes(underlyingPrice, shortStrike, T, riskFreeRate, volatility, isCall);

    // Vertical spread value (debit spread)
    const spreadValue = longValue - shortValue;

    // Clamp to valid range [0, width]
    const clampedValue = Math.max(0, Math.min(strat.width, spreadValue));

    // P&L with bounds
    const pnl = (clampedValue - debit) * multiplier;
    const maxLoss = -debit * multiplier;
    const maxProfit = (strat.width - debit) * multiplier;

    return Math.max(maxLoss, Math.min(maxProfit, pnl));
  }

  if (strat.strategy === 'butterfly') {
    const lowerStrike = strat.strike - strat.width;
    const middleStrike = strat.strike;
    const upperStrike = strat.strike + strat.width;
    const lowerValue = blackScholes(underlyingPrice, lowerStrike, T, riskFreeRate, volatility, isCall);
    const middleValue = blackScholes(underlyingPrice, middleStrike, T, riskFreeRate, volatility, isCall);
    const upperValue = blackScholes(underlyingPrice, upperStrike, T, riskFreeRate, volatility, isCall);

    // Butterfly value = long lower + short 2x middle + long upper
    const butterflyValue = lowerValue - 2 * middleValue + upperValue;

    // Clamp butterfly value to valid range [0, width]
    // A butterfly can never be worth less than 0 or more than its width
    const clampedValue = Math.max(0, Math.min(strat.width, butterflyValue));

    // P&L with bounds: cannot lose more than debit, cannot gain more than (width - debit)
    const pnl = (clampedValue - debit) * multiplier;
    const maxLoss = -debit * multiplier;
    const maxProfit = (strat.width - debit) * multiplier;

    return Math.max(maxLoss, Math.min(maxProfit, pnl));
  }

  return 0;
}

function App() {
  // Shared alert context (alerts read by RiskGraphPanel, deleteAlert used by context directly)
  const {
    createAlert: contextCreateAlert,
    updateAlert: contextUpdateAlert,
    getAlert: contextGetAlert,
  } = useAlerts();

  // Path context for stage inference
  const { setActivePanel } = usePath();

  const [spot, setSpot] = useState<SpotData | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [gexCalls, setGexCalls] = useState<GexData | null>(null);
  const [gexPuts, setGexPuts] = useState<GexData | null>(null);
  const [vexy, setVexy] = useState<VexyData | null>(null);
  const [biasLfi, setBiasLfi] = useState<BiasLfiData | null>(null);
  const [marketMode, setMarketMode] = useState<MarketModeData | null>(null);
  const [tradeSelector, setTradeSelector] = useState<TradeSelectorModel | null>(null);
  const [connected, setConnected] = useState(false);
  const [heartbeatPulse, setHeartbeatPulse] = useState(false);

  // Controls
  const [underlying, setUnderlying] = useState<'I:SPX' | 'I:NDX'>('I:SPX');

  // Sync underlying to window for SSE handlers and fetch initial candles
  useEffect(() => {
    (window as any).__currentUnderlying = underlying;

    // Fetch initial candle data for Dealer Gravity chart
    const fetchCandles = async () => {
      try {
        console.log('[App] Fetching candles for', underlying);
        const response = await fetch(`${SSE_BASE}/api/models/candles/${underlying}`, { credentials: 'include' });
        console.log('[App] Candles response status:', response.status);
        if (response.ok) {
          const result = await response.json();
          console.log('[App] Candles result:', result.success, 'candles_5m:', result.data?.candles_5m?.length);
          if (result.success && result.data) {
            const snapshot = {
              spot: result.data.spot,
              ts: result.data.ts,
              _index: {
                spot: result.data.spot,
                ts: result.data.ts,
                candles_5m: result.data.candles_5m,
                candles_15m: result.data.candles_15m,
                candles_1h: result.data.candles_1h,
              }
            };
            console.log('[App] Setting dgSnapshot with', snapshot._index?.candles_5m?.length, '5m candles');
            setDgSnapshot(snapshot);
          }
        }
      } catch (err) {
        console.error('[App] Failed to fetch initial candles:', err);
      }
    };

    fetchCandles();
  }, [underlying]);
  const [strategy, setStrategy] = useState<Strategy>('butterfly');
  const [side, setSide] = useState<Side>('both');
  const [dte, setDte] = useState(0);

  // MEL (Model Effectiveness Layer) - uses selected DTE
  const mel = useMEL(dte);

  const [gexMode, setGexMode] = useState<GexMode>('net');
  const [threshold, setThreshold] = useState(50); // % change threshold for blue/red transition
  const [volumeProfile, setVolumeProfile] = useState<VolumeProfileData | null>(null);

  // Heatmap display modes and overlays
  const [heatmapDisplayMode, setHeatmapDisplayMode] = useState<'debit' | 'r2r' | 'pct_diff'>('debit');
  const [showEMBoundary, setShowEMBoundary] = useState(true);
  const [optimalZoneThreshold, setOptimalZoneThreshold] = useState(45); // % change threshold for optimal zone outline
  const [blueCompression, setBlueCompression] = useState(0); // 0-100%, compress low-convexity rows

  // Strike column drag-to-compress state
  const [strikesDragActive, setStrikesDragActive] = useState(false);
  const strikesDragStart = useRef({ y: 0, compression: 0 });

  // Volume Profile settings - shared with Dealer Gravity panel
  const {
    vpConfig,
    setVpConfig,
    saveAsDefault: saveVpDefault,
    resetToFactoryDefaults: resetVpToFactory,
  } = useIndicatorSettings();
  const [showVpSettingsDialog, setShowVpSettingsDialog] = useState(false); // VP settings dialog

  // User profile for header
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);

  // Popup and Risk Graph state
  const [selectedTile, setSelectedTile] = useState<SelectedStrategy | null>(null);
  const [riskGraphStrategies, setRiskGraphStrategies] = useState<RiskGraphStrategy[]>(() => {
    try {
      const saved = localStorage.getItem('riskGraphStrategies');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [riskGraphAlerts, setRiskGraphAlerts] = useState<RiskGraphAlert[]>(() => {
    try {
      const saved = localStorage.getItem('riskGraphAlerts');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [alertModalStrategy, setAlertModalStrategy] = useState<string | null>(null); // strategyId for modal
  const [alertModalInitialPrice, setAlertModalInitialPrice] = useState<number | null>(null);
  const [alertModalInitialCondition, setAlertModalInitialCondition] = useState<'above' | 'below' | 'at'>('below');
  const [alertModalEditingAlert, setAlertModalEditingAlert] = useState<EditingAlertData | null>(null); // Alert being edited

  // Memoized strategy lookup for O(1) access in alert evaluation (vs O(n) .find())
  const strategyLookup = useMemo(() =>
    new Map(riskGraphStrategies.map(s => [s.id, s])),
    [riskGraphStrategies]
  );
  const [tosCopied, setTosCopied] = useState(false);
  const [showTosImport, setShowTosImport] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<RiskGraphStrategy | null>(null);

  // Panel collapse and layout state
  const [gexCollapsed, setGexCollapsed] = useState(false);
  const [gexDrawerOpen, setGexDrawerOpen] = useState(false); // GEX drawer overlay state
  const [heatmapCollapsed, setHeatmapCollapsed] = useState(false);
  const [widgetsRowCollapsed, setWidgetsRowCollapsed] = useState(false);
  const prevWidgetsCollapsed = useRef(widgetsRowCollapsed);
  const [priceAlertLines, setPriceAlertLines] = useState<PriceAlertLine[]>(() => {
    try {
      const saved = localStorage.getItem('priceAlertLines');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // 3D of Options controls - analyze time, price, and volatility dimensions
  const [timeMachineEnabled, setTimeMachineEnabled] = useState(false);
  const [simTimeOffsetHours, setSimTimeOffsetHours] = useState(0); // Hours forward from now toward expiration
  const [simVolatilityOffset, setSimVolatilityOffset] = useState(0); // Percentage points offset from current VIX
  const [simSpotOffset, setSimSpotOffset] = useState(0); // Points offset from current spot price

  const [scrollLocked, setScrollLocked] = useState(true);
  const [hasScrolledToAtm, setHasScrolledToAtm] = useState(false);
  const [strategyExpanded, setStrategyExpanded] = useState(false);
  const [sideExpanded, setSideExpanded] = useState(false);
  const [dteExpanded, setDteExpanded] = useState(false);
  const [gexExpanded, setGexExpanded] = useState(false);
  const [vexyAdvisorTab, setVexyAdvisorTab] = useState<'vexy' | 'advisor'>('vexy');

  // Dealer Gravity snapshot data for LightweightPriceChart
  const [dgSnapshot, setDgSnapshot] = useState<RawSnapshot | null>(null);

  // Trade Log state
  const [tradeLogCollapsed, setTradeLogCollapsed] = useState(true);
  const [tradeEntryOpen, setTradeEntryOpen] = useState(false);
  const [tradeEntryPrefill, setTradeEntryPrefill] = useState<TradeEntryData | null>(null);
  const [editingTrade, setEditingTrade] = useState<Trade | null>(null);
  const [tradeRefreshTrigger, setTradeRefreshTrigger] = useState(0);

  // FOTW Trade Log v2 state
  const [selectedLog, setSelectedLog] = useState<TradeLog | null>(null);
  const [logManagerOpen, setLogManagerOpen] = useState(false);
  const [tradeDetailTrade, setTradeDetailTrade] = useState<Trade | null>(null);
  const [reportingLogId, setReportingLogId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [trackingAnalyticsOpen, setTrackingAnalyticsOpen] = useState(false);
  const [leaderboardOpen, setLeaderboardOpen] = useState(false);
  const [journalOpen, setJournalOpen] = useState(false);
  const [journalTradeContext, setJournalTradeContext] = useState<TradeReflectionContext | null>(null);
  const [playbookOpen, setPlaybookOpen] = useState(false);
  const [playbookSource, setPlaybookSource] = useState<'journal' | 'tradelog' | null>(null);
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [pendingOrderCount, setPendingOrderCount] = useState(0);
  const [openTradeCount, setOpenTradeCount] = useState(0);

  // Commentary panel state
  const [commentaryCollapsed, setCommentaryCollapsed] = useState(true);

  // Path stage inference - infer active panel from UI state
  useEffect(() => {
    // Action stage - modals take priority
    if (alertModalStrategy !== null) {
      setActivePanel('alert-creation-modal');
      return;
    }
    if (showTosImport) {
      setActivePanel('tos-import');
      return;
    }
    if (tradeEntryOpen) {
      setActivePanel('trade-entry-modal');
      return;
    }

    // Right-side overlay panel views
    if (!tradeLogCollapsed) {
      if (playbookOpen) {
        setActivePanel('playbook');
        return;
      }
      if (journalOpen) {
        setActivePanel('journal');
        return;
      }
      if (reportingLogId) {
        setActivePanel('reporting');
        return;
      }
      // Default trade log view
      setActivePanel('trade-log');
      return;
    }

    // Observer panel open
    if (!commentaryCollapsed) {
      setActivePanel('observer');
      return;
    }

    // Default - main trading view is Discovery/Analysis
    // The risk graph and heatmap are visible, so we default to discovery
    setActivePanel('heatmap');
  }, [
    alertModalStrategy,
    showTosImport,
    tradeEntryOpen,
    tradeLogCollapsed,
    playbookOpen,
    journalOpen,
    reportingLogId,
    commentaryCollapsed,
    setActivePanel,
  ]);

  // Refs for scroll sync
  const gexScrollRef = useRef<HTMLDivElement>(null);
  const heatmapScrollRef = useRef<HTMLDivElement>(null);
  const isScrolling = useRef<boolean>(false); // Prevent scroll event loops

  // Track widgets collapse state changes
  useEffect(() => {
    prevWidgetsCollapsed.current = widgetsRowCollapsed;
  }, [widgetsRowCollapsed]);

  // Available DTEs from data
  const availableDtes = useMemo(() => {
    return heatmap?.dtes_available || [0];
  }, [heatmap]);

  // Auto-select first DTE with data (outside market hours, 0 DTE may be stale/empty)
  useEffect(() => {
    if (!heatmap?.tiles || availableDtes.length === 0) return;

    // Count tiles for current DTE
    const currentDteTileCount = Object.keys(heatmap.tiles).filter(key => {
      const parts = key.split(':');
      return parts.length >= 2 && parseInt(parts[1]) === dte;
    }).length;

    // If current DTE has no tiles, find first DTE with tiles
    if (currentDteTileCount === 0) {
      for (const d of availableDtes) {
        const tileCount = Object.keys(heatmap.tiles).filter(key => {
          const parts = key.split(':');
          return parts.length >= 2 && parseInt(parts[1]) === d;
        }).length;
        if (tileCount > 0) {
          setDte(d);
          break;
        }
      }
    }
  }, [heatmap, availableDtes, dte]);

  // Get expiration date string for current DTE
  const currentExpiration = useMemo(() => {
    if (!gexCalls?.expirations) return '';
    const expirations = Object.keys(gexCalls.expirations).sort();
    return expirations[dte] || expirations[0] || '';
  }, [gexCalls, dte]);

  // Generate TOS order script for a strategy
  const generateTosScript = (strat: SelectedStrategy): string => {
    const sideUpper = strat.side.toUpperCase();
    // Format expiration: "2026-01-31" -> "31 JAN 26"
    const expParts = strat.expiration.split('-');
    const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
    const expFormatted = expParts.length === 3
      ? `${expParts[2]} ${months[parseInt(expParts[1]) - 1]} ${expParts[0].slice(2)}`
      : strat.expiration;

    const price = strat.debit !== null ? `@${strat.debit.toFixed(2)} LMT` : '';

    if (strat.strategy === 'single') {
      return `BUY +1 SPX 100 (Weeklys) ${expFormatted} ${strat.strike} ${sideUpper} ${price}`;
    } else if (strat.strategy === 'vertical') {
      const longStrike = strat.strike;
      const shortStrike = strat.side === 'call' ? strat.strike + strat.width : strat.strike - strat.width;
      return `BUY +1 VERTICAL SPX 100 (Weeklys) ${expFormatted} ${longStrike}/${shortStrike} ${sideUpper} ${price}`;
    } else {
      // Butterfly
      const lowerStrike = strat.strike - strat.width;
      const upperStrike = strat.strike + strat.width;
      return `BUY +1 BUTTERFLY SPX 100 (Weeklys) ${expFormatted} ${lowerStrike}/${strat.strike}/${upperStrike} ${sideUpper} ${price}`;
    }
  };

  // Handle tile click
  const handleTileClick = (strike: number, width: number, debit: number | null, effectiveSide?: 'call' | 'put') => {
    // For 'both' mode, determine side based on strike vs spot
    let tileSide: 'call' | 'put';
    if (effectiveSide) {
      tileSide = effectiveSide;
    } else if (side === 'both') {
      tileSide = strike > (currentSpot || 0) ? 'call' : 'put';
    } else {
      tileSide = side;
    }
    setSelectedTile({
      strategy,
      side: tileSide,
      strike,
      width,
      dte,
      expiration: currentExpiration,
      debit,
    });
  };

  // Copy TOS script to clipboard
  const copyTosScript = async () => {
    if (!selectedTile) return;
    const script = generateTosScript(selectedTile);
    await navigator.clipboard.writeText(script);
    setTosCopied(true);
    setTimeout(() => setTosCopied(false), 2000);
  };

  // Add strategy to risk graph list
  const addToRiskGraph = () => {
    if (!selectedTile) return;
    const newStrategy: RiskGraphStrategy = {
      ...selectedTile,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      addedAt: Date.now(),
      visible: true,
    };
    setRiskGraphStrategies(prev => [...prev, newStrategy]);
    setSelectedTile(null);
  };

  // Import ToS script as new strategy
  const handleTosImport = (parsed: ParsedStrategy) => {
    const newStrategy: RiskGraphStrategy = {
      symbol: 'SPX',  // Default to SPX for ToS imports
      strategy: parsed.strategy,
      side: parsed.side,
      strike: parsed.strike,
      width: parsed.width,
      dte: parsed.dte,
      expiration: parsed.expiration,
      debit: parsed.debit,
      id: `tos-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      addedAt: Date.now(),
      visible: true,
    };
    setRiskGraphStrategies(prev => [...prev, newStrategy]);
  };

  // Close popup
  const closePopup = () => setSelectedTile(null);

  // Handle trade recommendation selection
  const handleTradeRecommendationSelect = useCallback((rec: TradeRecommendation) => {
    // Convert recommendation to selectedTile format
    const expDate = new Date();
    expDate.setDate(expDate.getDate() + rec.dte);
    const expiration = expDate.toISOString().split('T')[0];

    setSelectedTile({
      strategy: rec.strategy,
      side: rec.side,
      strike: rec.strike,
      width: rec.width,
      dte: rec.dte,
      expiration,
      debit: rec.debit,
    });
  }, []);

  // Remove strategy from risk graph
  const removeFromRiskGraph = (id: string) => {
    setRiskGraphStrategies(prev => prev.filter(s => s.id !== id));
  };

  // Toggle strategy visibility in risk graph
  const toggleStrategyVisibility = (id: string) => {
    setRiskGraphStrategies(prev => prev.map(s =>
      s.id === id ? { ...s, visible: !s.visible } : s
    ));
  };

  // Update strategy from edit modal
  const handleStrategyEdit = (updated: StrategyData) => {
    setRiskGraphStrategies(prev => prev.map(s =>
      s.id === updated.id ? { ...s, ...updated } : s
    ));
  };

  // Persist risk graph strategies to localStorage
  useEffect(() => {
    localStorage.setItem('riskGraphStrategies', JSON.stringify(riskGraphStrategies));
  }, [riskGraphStrategies]);

  // Persist risk graph alerts to localStorage
  useEffect(() => {
    localStorage.setItem('riskGraphAlerts', JSON.stringify(riskGraphAlerts));
  }, [riskGraphAlerts]);

  // Persist price alert lines to localStorage
  useEffect(() => {
    localStorage.setItem('priceAlertLines', JSON.stringify(priceAlertLines));
  }, [priceAlertLines]);

  // Fetch user profile for header greeting
  useEffect(() => {
    fetch('/api/profile/me', { credentials: 'include' })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.display_name) {
          setUserProfile({ display_name: data.display_name, is_admin: data.is_admin || false });
        }
      })
      .catch(err => console.error('Failed to fetch user profile:', err));
  }, []);

  // Price alert line management
  const deletePriceAlertLine = (alertId: string) => {
    setPriceAlertLines(prev => prev.filter(a => a.id !== alertId));
  };

  const startEditingAlert = (alertId: string) => {
    const alert = contextGetAlert(alertId);
    if (!alert) return;
    // Get strategyId from source or type-specific field
    const strategyId = 'strategyId' in alert ? alert.strategyId : alert.source.id;
    // Get minProfitThreshold for AI alerts
    const minProfitThreshold = 'minProfitThreshold' in alert ? alert.minProfitThreshold : undefined;
    // Set up the modal for editing
    setAlertModalStrategy(strategyId);
    setAlertModalEditingAlert({
      id: alert.id,
      type: alert.type,
      condition: alert.condition,
      targetValue: alert.targetValue,
      color: alert.color,
      behavior: alert.behavior,
      minProfitThreshold,
    });
    setAlertModalInitialPrice(null); // Clear any right-click price
  };

  const startNewAlert = (strategyId: string) => {
    const strategy = riskGraphStrategies.find(s => s.id === strategyId);
    if (!strategy) return;
    setAlertModalStrategy(strategyId);
    setAlertModalEditingAlert(null); // Clear any editing
  };

  // Update strategy debit (for when actual fill differs from quoted price)
  const updateStrategyDebit = (id: string, newDebit: number | null) => {
    setRiskGraphStrategies(prev => prev.map(s =>
      s.id === id ? { ...s, debit: newDebit } : s
    ));
  };

  // Trade Log handlers
  const openTradeEntry = useCallback((logIdOrPrefill?: string | TradeEntryData) => {
    if (typeof logIdOrPrefill === 'string') {
      // Called with logId from TradeLogPanel
      setTradeEntryPrefill(null);
    } else {
      // Called with prefill data from heatmap
      setTradeEntryPrefill(logIdOrPrefill || null);
    }
    setEditingTrade(null);
    setTradeEntryOpen(true);
  }, []);

  const openTradeEdit = useCallback((trade: Trade) => {
    // Open trade detail modal instead of entry modal for editing
    setTradeDetailTrade(trade);
  }, []);

  const closeTradeEntry = useCallback(() => {
    setTradeEntryOpen(false);
    setTradeEntryPrefill(null);
    setEditingTrade(null);
  }, []);

  const onTradeSaved = useCallback(() => {
    setTradeRefreshTrigger(prev => prev + 1);
  }, []);

  // Log management handlers
  const handleSelectLog = useCallback((log: TradeLog) => {
    setSelectedLog(log);
  }, []);

  const handleManageLogs = useCallback(() => {
    setLogManagerOpen(true);
  }, []);

  const handleViewReporting = useCallback((logId: string) => {
    setReportingLogId(logId);
  }, []);

  const handleCloseReporting = useCallback(() => {
    setReportingLogId(null);
  }, []);

  const handleTradeDetailClose = useCallback(() => {
    setTradeDetailTrade(null);
  }, []);

  const handleLogCreated = useCallback(() => {
    setTradeRefreshTrigger(prev => prev + 1);
  }, []);

  // Fetch monitor counts (pending orders + open trades)
  const fetchMonitorCounts = useCallback(async () => {
    try {
      const ordersRes = await fetch('/api/orders/active', { credentials: 'include' });
      if (!ordersRes.ok) {
        console.warn('[Monitor] Orders fetch failed:', ordersRes.status);
      } else {
        const ordersData = await ordersRes.json();
        if (ordersData.success) {
          const pendingCount = (ordersData.data.pending_entries?.length || 0) +
                              (ordersData.data.pending_exits?.length || 0);
          setPendingOrderCount(pendingCount);
        }
      }

      const tradesRes = await fetch('/api/trades?status=open', { credentials: 'include' });
      if (!tradesRes.ok) {
        console.warn('[Monitor] Trades fetch failed:', tradesRes.status);
      } else {
        const tradesData = await tradesRes.json();
        if (tradesData.success) {
          setOpenTradeCount(tradesData.data?.length || 0);
        }
      }
    } catch (err) {
      console.error('[Monitor] Failed to fetch counts:', err);
    }
  }, []);

  // Fetch monitor counts on mount and periodically
  useEffect(() => {
    fetchMonitorCounts();
    const interval = setInterval(fetchMonitorCounts, 30000); // Every 30 seconds
    return () => clearInterval(interval);
  }, [fetchMonitorCounts]);

  // Scroll sync handler for GEX panel
  const handleGexScroll = useCallback(() => {
    if (!scrollLocked || isScrolling.current || !gexScrollRef.current || !heatmapScrollRef.current) return;
    isScrolling.current = true;
    heatmapScrollRef.current.scrollTop = gexScrollRef.current.scrollTop;
    requestAnimationFrame(() => { isScrolling.current = false; });
  }, [scrollLocked]);

  // Scroll sync handler for Heatmap panel
  const handleHeatmapScroll = useCallback(() => {
    if (!scrollLocked || isScrolling.current || !gexScrollRef.current || !heatmapScrollRef.current) return;
    isScrolling.current = true;
    gexScrollRef.current.scrollTop = heatmapScrollRef.current.scrollTop;
    requestAnimationFrame(() => { isScrolling.current = false; });
  }, [scrollLocked]);

  // Strike column drag handlers for compression
  const handleStrikesDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setStrikesDragActive(true);
    strikesDragStart.current = { y: e.clientY, compression: blueCompression };
  }, [blueCompression]);

  const handleStrikesDragMove = useCallback((e: MouseEvent) => {
    if (!strikesDragActive) return;
    const dy = e.clientY - strikesDragStart.current.y;
    // Drag down = more compression (collapse blue, pull outliers to spot)
    // Drag up = less compression (expand back to normal)
    // 100px drag = full range (0-100%)
    const newCompression = Math.max(0, Math.min(100, strikesDragStart.current.compression + dy));
    setBlueCompression(Math.round(newCompression));
  }, [strikesDragActive]);

  const handleStrikesDragEnd = useCallback(() => {
    setStrikesDragActive(false);
  }, []);

  // Global mouse events for strike drag
  useEffect(() => {
    if (strikesDragActive) {
      window.addEventListener('mousemove', handleStrikesDragMove);
      window.addEventListener('mouseup', handleStrikesDragEnd);
      return () => {
        window.removeEventListener('mousemove', handleStrikesDragMove);
        window.removeEventListener('mouseup', handleStrikesDragEnd);
      };
    }
  }, [strikesDragActive, handleStrikesDragMove, handleStrikesDragEnd]);

  // Heartbeat animation - CSS handles the infinite loop, JS just toggles on/off
  useEffect(() => {
    setHeartbeatPulse(connected);
  }, [connected]);

  // SSE connection with auto-reconnect
  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_DELAY = 30000; // 30 seconds max

    const connect = () => {
      // Clean up existing connection
      if (es) {
        es.close();
      }

      es = new EventSource(`${SSE_BASE}/sse/all`, { withCredentials: true });

      es.onopen = () => {
        setConnected(true);
        reconnectAttempts = 0; // Reset on successful connection
        console.log('[SSE] Connected');
      };

      es.onerror = () => {
        setConnected(false);
        console.warn('[SSE] Connection error, will reconnect...');

        // Exponential backoff with jitter
        const baseDelay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
        const jitter = Math.random() * 1000;
        const delay = baseDelay + jitter;
        reconnectAttempts++;

        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connect, delay);
      };

      // Throttle spot updates to max 2/second to reduce re-renders
    // Humans can't perceive price changes faster than ~500ms anyway
    const { throttled: throttledSpotUpdate, flush: flushSpot } = createThrottle((spotData: SpotData) => {
      setSpot(spotData);

      // Update Dealer Gravity snapshot with current spot (for selected underlying)
      const currentUnderlying = (window as any).__currentUnderlying || 'I:SPX';
      const underlyingSpot = spotData[currentUnderlying] || spotData['I:SPX'];
      if (underlyingSpot) {
        setDgSnapshot(prev => ({
          ...prev,
          spot: underlyingSpot.value,
          ts: underlyingSpot.ts,
          _index: {
            ...prev?._index,
            spot: underlyingSpot.value,
            ts: underlyingSpot.ts,
          }
        }));
      }
    }, 500);

    es.addEventListener('spot', (e: MessageEvent) => {
      try {
        const spotData = JSON.parse(e.data);
        throttledSpotUpdate(spotData);
      } catch {}
    });

    // Store flush function for cleanup
    (es as any)._flushSpot = flushSpot;

    // Candle data for Dealer Gravity chart
    es.addEventListener('candles', (e: MessageEvent) => {
      try {
        const candleData = JSON.parse(e.data);
        // candleData expected format: { symbol, candles_5m, candles_15m, candles_1h, spot, ts }
        const currentUnderlying = (window as any).__currentUnderlying || 'I:SPX';
        if (candleData.symbol === currentUnderlying || candleData.symbol === currentUnderlying.replace('I:', '')) {
          setDgSnapshot({
            spot: candleData.spot,
            ts: candleData.ts,
            _index: {
              spot: candleData.spot,
              ts: candleData.ts,
              candles_5m: candleData.candles_5m,
              candles_15m: candleData.candles_15m,
              candles_1h: candleData.candles_1h,
            }
          });
        }
      } catch {}
    });

    es.addEventListener('gex', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        // Store in window for underlying switching
        (window as any).__gexCache = (window as any).__gexCache || {};
        if (data.symbol) {
          (window as any).__gexCache[data.symbol] = data;
        }
        window.dispatchEvent(new CustomEvent('gex-update', { detail: data }));
      } catch {}
    });

    es.addEventListener('heatmap', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        // Cache heatmap by symbol
        (window as any).__heatmapCache = (window as any).__heatmapCache || {};
        if (data.symbol) {
          (window as any).__heatmapCache[data.symbol] = data;
        }
        window.dispatchEvent(new CustomEvent('heatmap-update', { detail: data }));
      } catch {}
    });

    es.addEventListener('heatmap_diff', (e: MessageEvent) => {
      try {
        const diff = JSON.parse(e.data);
        // Dispatch for underlying-aware handling
        window.dispatchEvent(new CustomEvent('heatmap-diff-update', { detail: diff }));
      } catch {}
    });

    es.addEventListener('vexy', (e: MessageEvent) => {
      try {
        setVexy(JSON.parse(e.data));
      } catch {}
    });

    es.addEventListener('bias_lfi', (e: MessageEvent) => {
      try {
        setBiasLfi(JSON.parse(e.data));
      } catch {}
    });

    es.addEventListener('market_mode', (e: MessageEvent) => {
      try {
        setMarketMode(JSON.parse(e.data));
      } catch {}
    });

    es.addEventListener('trade_selector', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        // Cache by symbol and dispatch event for underlying-aware handling
        (window as any).__tradeSelectorCache = (window as any).__tradeSelectorCache || {};
        if (data.symbol) {
          (window as any).__tradeSelectorCache[data.symbol] = data;
        }
        window.dispatchEvent(new CustomEvent('trade-selector-update', { detail: data }));
      } catch {}
    });
    };

    // Start connection
    connect();

    return () => {
      // Flush any pending throttled updates before closing
      if (es) {
        const flushSpot = (es as any)._flushSpot;
        if (flushSpot) flushSpot();
        es.close();
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // Handle SSE updates filtered by selected underlying
  useEffect(() => {
    const handleGexUpdate = (e: CustomEvent) => {
      const data = e.detail;
      if (data.symbol === underlying) {
        if (data.calls) setGexCalls(data.calls);
        if (data.puts) setGexPuts(data.puts);
      }
    };

    const handleHeatmapUpdate = (e: CustomEvent) => {
      const data = e.detail;
      if (data.symbol === underlying) {
        setHeatmap(data);
      }
    };

    const handleHeatmapDiffUpdate = (e: CustomEvent) => {
      const diff = e.detail;
      if (diff.symbol !== underlying) return;

      const changedKeys = diff.changed ? Object.keys(diff.changed) : [];
      const removedKeys = diff.removed || [];

      // Skip if no actual changes
      if (changedKeys.length === 0 && removedKeys.length === 0) return;

      setHeatmap(prev => {
        if (prev?.version && diff.version && diff.version <= prev.version) {
          return prev;
        }

        // Only copy tiles if we have previous tiles and changes to make
        const prevTiles = prev?.tiles || {};
        let updatedTiles: Record<string, HeatmapTile>;

        // Optimization: if there are many changes, use Object.assign instead of spread
        // This avoids creating intermediate iterator objects
        if (changedKeys.length > 50 || removedKeys.length > 10) {
          // For large diffs, build a new object with only changed tiles
          updatedTiles = Object.assign({}, prevTiles);
        } else {
          updatedTiles = { ...prevTiles };
        }

        // Apply changes using direct key access (faster than Object.entries)
        for (const key of changedKeys) {
          updatedTiles[key] = diff.changed[key] as HeatmapTile;
        }

        // Apply removals
        for (const key of removedKeys) {
          delete updatedTiles[key];
        }

        return {
          ts: diff.ts,
          symbol: diff.symbol || prev?.symbol || underlying,
          version: diff.version,
          dtes_available: diff.dtes_available || prev?.dtes_available,
          tiles: updatedTiles,
        };
      });
    };

    const handleTradeSelectorUpdate = (e: CustomEvent) => {
      const data = e.detail;
      if (data.symbol === underlying) {
        setTradeSelector(data);
      }
    };

    window.addEventListener('gex-update', handleGexUpdate as EventListener);
    window.addEventListener('heatmap-update', handleHeatmapUpdate as EventListener);
    window.addEventListener('heatmap-diff-update', handleHeatmapDiffUpdate as EventListener);
    window.addEventListener('trade-selector-update', handleTradeSelectorUpdate as EventListener);

    return () => {
      window.removeEventListener('gex-update', handleGexUpdate as EventListener);
      window.removeEventListener('heatmap-update', handleHeatmapUpdate as EventListener);
      window.removeEventListener('heatmap-diff-update', handleHeatmapDiffUpdate as EventListener);
      window.removeEventListener('trade-selector-update', handleTradeSelectorUpdate as EventListener);
    };
  }, [underlying]);

  // Fetch initial data via REST (refetch when underlying changes)
  useEffect(() => {
    const opts = { credentials: 'include' as RequestCredentials };

    fetch(`${SSE_BASE}/api/models/spot`, opts)
      .then(r => r.json())
      .then(d => d.success && setSpot(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/heatmap/${underlying}`, opts)
      .then(r => r.json())
      .then(d => d.success && setHeatmap(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/gex/${underlying}`, opts)
      .then(r => r.json())
      .then(d => {
        if (d.success && d.data) {
          if (d.data.calls) {
            setGexCalls(d.data.calls);
          }
          if (d.data.puts) {
            setGexPuts(d.data.puts);
          }
        }
      })
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/vexy/latest`, opts)
      .then(r => r.json())
      .then(d => d.success && setVexy(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/bias_lfi`, opts)
      .then(r => r.json())
      .then(d => d.success && setBiasLfi(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/market_mode`, opts)
      .then(r => r.json())
      .then(d => d.success && setMarketMode(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/trade_selector/${underlying}`, opts)
      .then(r => r.json())
      .then(d => d.success && setTradeSelector(d.data))
      .catch(() => {});

    // Reset scroll state when underlying changes
    setHasScrolledToAtm(false);
  }, [underlying]);

  // Fetch volume profile based on spot price (±300 points) - SPX only for now
  useEffect(() => {
    if (underlying !== 'I:SPX') {
      setVolumeProfile(null);
      return;
    }

    const spotPrice = spot?.[underlying]?.value;
    if (!spotPrice) return;

    const minPrice = Math.floor(spotPrice - 300);
    const maxPrice = Math.ceil(spotPrice + 300);

    fetch(`${SSE_BASE}/api/models/volume_profile?min=${minPrice}&max=${maxPrice}`, { credentials: 'include' })
      .then(r => r.json())
      .then(d => {
        if (d.success && d.data) {
          setVolumeProfile(d.data);
        }
      })
      .catch(() => {});

    // Refresh every 5 seconds (only when tab is visible)
    const interval = setInterval(() => {
      if (document.hidden) return;
      fetch(`${SSE_BASE}/api/models/volume_profile?min=${minPrice}&max=${maxPrice}`, { credentials: 'include' })
        .then(r => r.json())
        .then(d => {
          if (d.success && d.data) {
            setVolumeProfile(d.data);
          }
        })
        .catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [underlying, spot?.[underlying]?.value]);

  const currentSpot = spot?.[underlying]?.value || null;

  // Market hours check (9:30 AM - 4:00 PM ET, Mon-Fri)
  const isMarketOpen = useMemo(() => {
    const now = new Date();
    const day = now.getDay();
    // Weekend check
    if (day === 0 || day === 6) return false;

    // Convert to ET (Eastern Time)
    const etTime = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    }).format(now);
    const [hours, minutes] = etTime.split(':').map(Number);
    const timeMinutes = hours * 60 + minutes;

    // Market hours: 9:30 AM (570 min) to 4:00 PM (960 min)
    return timeMinutes >= 570 && timeMinutes < 960;
  }, []);

  // Simulated spot for 3D of Options (actual spot + offset when enabled)
  const simulatedSpot = currentSpot && timeMachineEnabled
    ? currentSpot + simSpotOffset
    : currentSpot;

  // Check alerts against current spot price (use simulated if time machine enabled)
  useEffect(() => {
    if (!currentSpot) return;

    let alertsToRemove: string[] = [];

    setRiskGraphAlerts(prev => {
      let hasChanges = false;
      const updated = prev.map(alert => {
        if (!alert.enabled) return alert;

        // Use memoized Map lookup for O(1) instead of O(n) .find()
        const strategy = strategyLookup.get(alert.strategyId);
        let conditionMet = false;
        let isOnOtherSide = false;
        let updatedAlert = alert;

        if (alert.type === 'price') {
          switch (alert.condition) {
            case 'above':
              conditionMet = currentSpot >= alert.targetValue;
              isOnOtherSide = currentSpot < alert.targetValue;
              break;
            case 'below':
              conditionMet = currentSpot <= alert.targetValue;
              isOnOtherSide = currentSpot > alert.targetValue;
              break;
            case 'at':
              conditionMet = Math.abs(currentSpot - alert.targetValue) < 1;
              isOnOtherSide = Math.abs(currentSpot - alert.targetValue) >= 5;
              break;
          }
        } else if (alert.type === 'debit') {
          if (strategy && strategy.debit !== null) {
            switch (alert.condition) {
              case 'above':
                conditionMet = strategy.debit >= alert.targetValue;
                isOnOtherSide = strategy.debit < alert.targetValue;
                break;
              case 'below':
                conditionMet = strategy.debit <= alert.targetValue;
                isOnOtherSide = strategy.debit > alert.targetValue;
                break;
              case 'at':
                conditionMet = Math.abs(strategy.debit - alert.targetValue) < 0.05;
                isOnOtherSide = Math.abs(strategy.debit - alert.targetValue) >= 0.2;
                break;
            }
          }
        } else if (alert.type === 'profit_target') {
          if (strategy && strategy.debit !== null) {
            const entryDebit = alert.highWaterMark || strategy.debit;
            const currentProfit = entryDebit - strategy.debit;
            conditionMet = currentProfit >= alert.targetValue;
            isOnOtherSide = currentProfit < alert.targetValue * 0.5;
          }
        } else if (alert.type === 'trailing_stop') {
          if (strategy && strategy.debit !== null) {
            const hwm = alert.highWaterMark || strategy.debit;
            if (strategy.debit < hwm) {
              updatedAlert = { ...alert, highWaterMark: strategy.debit };
              hasChanges = true;
            }
            const currentHwm = updatedAlert.highWaterMark || hwm;
            conditionMet = strategy.debit >= currentHwm + alert.targetValue;
            isOnOtherSide = strategy.debit < currentHwm + alert.targetValue * 0.5;
          }
        } else if (alert.type === 'ai_theta_gamma') {
          // AI Theta/Gamma: Dynamic zone that appears when profit exceeds threshold
          // Zone edges = trigger levels. If price exits zone, risk is too high to stay in position.
          // Uses simulated values when 3D of Options is enabled
          const effectiveSpot = simulatedSpot || currentSpot;
          if (strategy && effectiveSpot) {
            const entryDebit = alert.entryDebit || strategy.debit || 1;

            // Calculate current P&L using Black-Scholes theoretical value
            // Uses 3D of Options settings when enabled (simulated spot, volatility, time)
            const vix = spot?.['I:VIX']?.value || 20;
            const adjustedVix = timeMachineEnabled ? vix + simVolatilityOffset : vix;
            const volatility = Math.max(0.05, adjustedVix) / 100;
            const timeOffset = timeMachineEnabled ? simTimeOffsetHours : 0;
            const theoreticalPnL = calculateStrategyTheoreticalPnL(strategy, effectiveSpot, volatility, 0.05, timeOffset);

            // theoreticalPnL is in cents, entryDebit is in dollars
            // Profit = current P&L (already accounts for entry debit in the function)
            const currentProfit = theoreticalPnL / 100; // convert to dollars
            const profitPercent = entryDebit > 0 ? currentProfit / entryDebit : 0;
            const minProfitThreshold = alert.minProfitThreshold || 0.5;

            // Zone only appears when profit threshold is met
            const profitThresholdMet = profitPercent >= minProfitThreshold;

            // Calculate dynamic zone width based on EFFECTIVE time remaining
            // As expiration approaches, gamma increases and zone SHRINKS
            // - Less time = higher gamma = narrower safe zone (price moves hurt more)
            // - More time = lower gamma = wider safe zone (time to recover)
            const nominalDTE = strategy.dte || 0;
            const effectiveDTE = Math.max(0, nominalDTE - (timeOffset / 24));

            // Time factor: zone shrinks as we approach expiration
            // At 0 DTE: factor ~0.3 (very tight zone)
            // At 1 DTE: factor ~0.6
            // At 3 DTE: factor ~1.0
            // At 7+ DTE: factor ~1.5 (wider zone, more buffer)
            const timeFactor = Math.min(1.5, Math.max(0.3, Math.sqrt(effectiveDTE) * 0.75));

            // Gamma factor: butterflies have extreme gamma near center, need tighter zone
            const gammaFactor = strategy.strategy === 'butterfly' ? 0.6 : strategy.strategy === 'vertical' ? 0.8 : 1.0;

            // Profit factor: slightly more buffer with profit, but less impact near expiration
            const profitBuffer = effectiveDTE > 1 ? (1 + Math.max(0, profitPercent) * 0.3) : 1;

            // Base zone width: starts at 20 points, scaled by factors
            // Near expiration (0 DTE), this could be as low as 20 * 0.3 * 0.6 = 3.6 points
            const baseWidth = 20 * timeFactor * gammaFactor * profitBuffer;
            const zoneHalfWidth = Math.max(3, baseWidth); // Minimum 3 points

            // Track high water mark profit (but don't expand zone from it)
            const hwmProfit = alert.highWaterMarkProfit || 0;
            let newHwmProfit = hwmProfit;
            if (currentProfit > hwmProfit) {
              newHwmProfit = currentProfit;
              hasChanges = true;
            }

            // Zone width is purely based on time/gamma risk - no expansion
            const finalZoneWidth = zoneHalfWidth;

            // Calculate zone bounds centered on effective spot (simulated or real)
            const newZoneLow = effectiveSpot - finalZoneWidth;
            const newZoneHigh = effectiveSpot + finalZoneWidth;

            if (profitThresholdMet) {
              // Profit threshold met - zone is active
              const wasActive = alert.isZoneActive;
              const currentZoneLow = wasActive ? alert.zoneLow! : newZoneLow;
              const currentZoneHigh = wasActive ? alert.zoneHigh! : newZoneHigh;

              // Check if price is within zone
              const inZone = effectiveSpot >= currentZoneLow && effectiveSpot <= currentZoneHigh;

              // Trigger alert if price exits zone - risk too high to remain in position
              if (!inZone) {
                conditionMet = true;
                isOnOtherSide = false;
              } else {
                isOnOtherSide = true;
              }

              if (!wasActive) {
                // First time crossing threshold - initialize zone
                updatedAlert = {
                  ...updatedAlert,
                  isZoneActive: true,
                  zoneLow: newZoneLow,
                  zoneHigh: newZoneHigh,
                  highWaterMarkProfit: newHwmProfit,
                };
                hasChanges = true;
              } else {
                // Zone active - expand zone as price moves favorably
                const expandedZoneLow = Math.min(currentZoneLow, newZoneLow);
                const expandedZoneHigh = Math.max(currentZoneHigh, newZoneHigh);
                if (expandedZoneLow !== alert.zoneLow || expandedZoneHigh !== alert.zoneHigh || newHwmProfit !== hwmProfit) {
                  updatedAlert = {
                    ...updatedAlert,
                    zoneLow: expandedZoneLow,
                    zoneHigh: expandedZoneHigh,
                    highWaterMarkProfit: newHwmProfit,
                  };
                  hasChanges = true;
                }
              }
            } else {
              // Profit below threshold - zone not active, but track HWM
              if (alert.isZoneActive) {
                // Was active, now profit dropped below threshold - deactivate zone
                updatedAlert = {
                  ...updatedAlert,
                  isZoneActive: false,
                };
                hasChanges = true;
              }
              if (newHwmProfit !== hwmProfit) {
                updatedAlert = { ...updatedAlert, highWaterMarkProfit: newHwmProfit };
                hasChanges = true;
              }
              isOnOtherSide = true; // Not in triggerable state
            }
          }
        }

        // Handle "repeat" behavior - reset triggered when price crosses back
        const behavior = alert.behavior || 'once_only';
        if (behavior === 'repeat' && alert.triggered && isOnOtherSide) {
          hasChanges = true;
          updatedAlert = { ...updatedAlert, triggered: false, wasOnOtherSide: true };
        }

        // Check if should trigger
        const canTrigger = !alert.triggered || (behavior === 'repeat' && alert.wasOnOtherSide);

        if (conditionMet && canTrigger) {
          hasChanges = true;
          // Play alert sound
          try {
            const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQA6s+DZpGgLJJPo7bN1');
            audio.volume = 0.3;
            audio.play().catch(() => {});
          } catch {}

          // Handle based on behavior
          if (behavior === 'remove_on_hit') {
            alertsToRemove.push(alert.id);
            return updatedAlert; // Will be removed after
          }

          return { ...updatedAlert, triggered: true, triggeredAt: Date.now(), wasOnOtherSide: false };
        }

        return updatedAlert;
      });

      return hasChanges ? updated : prev;
    });

    // Remove alerts that should be removed after hit
    if (alertsToRemove.length > 0) {
      setTimeout(() => {
        setRiskGraphAlerts(prev => prev.filter(a => !alertsToRemove.includes(a.id)));
      }, 100);
    }
  }, [currentSpot, simulatedSpot, strategyLookup, spot, timeMachineEnabled, simTimeOffsetHours, simVolatilityOffset]);

  const widths = WIDTHS[underlying][strategy];

  // Process data for the grid view - all widths as columns
  const { strikes, gexByStrike, heatmapGrid, changeGrid, maxGex, maxNetGex } = useMemo(() => {
    const gexByStrike: Record<number, { calls: number; puts: number }> = {};
    // heatmapGrid[strike][width] = value
    const heatmapGrid: Record<number, Record<number, number | null>> = {};

    // Get GEX data for selected DTE
    if (gexCalls?.expirations) {
      const expirations = Object.keys(gexCalls.expirations).sort();
      const targetExp = expirations[dte] || expirations[0];

      const callLevels = gexCalls.expirations[targetExp] || {};
      const putLevels = gexPuts?.expirations?.[targetExp] || {};

      Object.entries(callLevels).forEach(([strike, value]) => {
        const s = parseFloat(strike);
        if (!gexByStrike[s]) gexByStrike[s] = { calls: 0, puts: 0 };
        gexByStrike[s].calls = value;
      });

      Object.entries(putLevels).forEach(([strike, value]) => {
        const s = parseFloat(strike);
        if (!gexByStrike[s]) gexByStrike[s] = { calls: 0, puts: 0 };
        gexByStrike[s].puts = value;
      });
    }

    // Get heatmap data for selected strategy/DTE - ALL widths
    const spotPrice = spot?.[underlying]?.value || 0;

    if (heatmap?.tiles) {
      Object.entries(heatmap.tiles).forEach(([key, tile]) => {
        // Key format: "strategy:dte:width:strike"
        const parts = key.split(':');
        if (parts.length !== 4) return;

        const [tileStrategy, tileDte, tileWidth, tileStrike] = parts;

        if (tileStrategy !== strategy) return;
        if (parseInt(tileDte) !== dte) return;

        const strike = parseFloat(tileStrike);
        const width = parseInt(tileWidth);

        if (!heatmapGrid[strike]) {
          heatmapGrid[strike] = {};
        }

        // Determine effective side: for 'both', use calls above spot, puts at/below
        const effectiveSide = side === 'both'
          ? (strike > spotPrice ? 'call' : 'put')
          : side;

        // Get value based on strategy and side
        if (strategy === 'single') {
          // For single, use mid price
          heatmapGrid[strike][0] = tile[effectiveSide]?.mid ?? null;
        } else {
          // For vertical/butterfly, use debit
          heatmapGrid[strike][width] = tile[effectiveSide]?.debit ?? null;
        }
      });
    }

    // Combine strikes and sort descending
    const allStrikes = new Set([
      ...Object.keys(gexByStrike).map(Number),
      ...Object.keys(heatmapGrid).map(Number),
    ]);
    const strikes = Array.from(allStrikes).sort((a, b) => b - a);

    // Calculate max values for scaling
    let maxGex = 1;
    let maxNetGex = 1;
    Object.values(gexByStrike).forEach(v => {
      maxGex = Math.max(maxGex, Math.abs(v.calls), Math.abs(v.puts));
      const net = v.calls - v.puts;
      maxNetGex = Math.max(maxNetGex, Math.abs(net));
    });

    // Calculate % change between adjacent strikes for each width
    // changeGrid[strike][width] = % change from previous strike
    const changeGrid: Record<number, Record<number, number>> = {};
    const sortedStrikes = Array.from(allStrikes).sort((a, b) => b - a); // descending

    for (let i = 0; i < sortedStrikes.length; i++) {
      const strike = sortedStrikes[i];
      const prevStrike = sortedStrikes[i - 1]; // strike above (higher value)
      changeGrid[strike] = {};

      const currentData = heatmapGrid[strike] || {};
      const prevData = prevStrike ? (heatmapGrid[prevStrike] || {}) : {};

      const widthsForCalc = WIDTHS[underlying][strategy];
      for (const w of widthsForCalc) {
        const curr = currentData[w];
        const prev = prevData[w];

        if (curr !== null && curr !== undefined && prev !== null && prev !== undefined && prev !== 0) {
          const pctChange = Math.abs((curr - prev) / prev) * 100;
          changeGrid[strike][w] = pctChange;
        } else {
          changeGrid[strike][w] = 0;
        }
      }
    }

    return { strikes, gexByStrike, heatmapGrid, changeGrid, maxGex, maxNetGex };
  }, [gexCalls, gexPuts, heatmap, strategy, side, dte, underlying, spot]);

  // Calculate Expected Move based on VIX and DTE
  const expectedMove = useMemo(() => {
    const spotPrice = currentSpot || 6000;
    const vix = spot?.['I:VIX']?.value || 20;
    // EM = Spot * (VIX/100) * sqrt(DTE/365)
    // For 0 DTE, use fraction of trading day (6.5 hours = ~0.018 years)
    const dteYears = dte === 0 ? 1/365 : (dte + 1) / 365;
    const em = spotPrice * (vix / 100) * Math.sqrt(dteYears);
    return Math.round(em * 10) / 10; // Round to 0.1
  }, [currentSpot, spot, dte]);

  // Calculate EM boundary strikes (upper and lower)
  const emBoundaryStrikes = useMemo(() => {
    const spotPrice = currentSpot || 6000;
    return {
      upper: spotPrice + expectedMove,
      lower: spotPrice - expectedMove,
    };
  }, [currentSpot, expectedMove]);

  // Helper to check if a strike is at the EM boundary (within 5 points)
  const isAtEMBoundary = useCallback((strike: number) => {
    return Math.abs(strike - emBoundaryStrikes.upper) <= 5 ||
           Math.abs(strike - emBoundaryStrikes.lower) <= 5;
  }, [emBoundaryStrikes]);

  // Helper to check if strike is in optimal convexity zone
  const isInOptimalZone = useCallback((strike: number, width: number) => {
    const pctChange = changeGrid[strike]?.[width] ?? 0;
    return pctChange >= optimalZoneThreshold;
  }, [changeGrid, optimalZoneThreshold]);

  // Get maximum convexity (% change) at a strike across all widths
  const getMaxConvexity = useCallback((strike: number) => {
    const widthsForStrategy = WIDTHS[underlying][strategy];
    let maxPct = 0;
    for (const w of widthsForStrategy) {
      const pct = changeGrid[strike]?.[w] ?? 0;
      if (pct > maxPct) maxPct = pct;
    }
    return maxPct;
  }, [changeGrid, underlying, strategy]);

  // Calculate row height based on convexity and compression setting
  const getRowHeight = useCallback((strike: number) => {
    if (blueCompression === 0) return 24; // Default height, no compression

    // Only compress tiles INSIDE the expected move range
    // Tiles at or beyond EM boundaries stay full height
    const isInsideEM = strike > emBoundaryStrikes.lower && strike < emBoundaryStrikes.upper;

    // Also keep EM boundary highlighted rows at full height
    const atEMBoundary = isAtEMBoundary(strike);

    if (!isInsideEM || atEMBoundary) {
      return 24; // Full height for anything at or beyond EM, or highlighted as EM boundary
    }

    const maxConvexity = getMaxConvexity(strike);
    const isHighConvexity = maxConvexity >= optimalZoneThreshold;

    // Keep full height for high-convexity rows even inside EM
    if (isHighConvexity) {
      return 24;
    }

    // Compress low-convexity rows inside EM range
    // At 100% compression, blue rows shrink to 1px (nearly invisible)
    const minHeight = 1;
    const compressionFactor = blueCompression / 100;
    return Math.max(minHeight, Math.round(24 - (24 - minHeight) * compressionFactor));
  }, [blueCompression, getMaxConvexity, optimalZoneThreshold, emBoundaryStrikes, isAtEMBoundary]);

  // Calculate R2R (Risk to Reward) for a given debit and width
  const calculateR2R = useCallback((debit: number | null, width: number) => {
    if (debit === null || debit <= 0 || width <= 0) return null;
    const maxProfit = width - debit;
    return maxProfit / debit;
  }, []);

  // Get display value based on mode
  const getDisplayValue = useCallback((strike: number, width: number) => {
    const debit = heatmapGrid[strike]?.[width] ?? null;
    const pctChange = changeGrid[strike]?.[width] ?? 0;

    switch (heatmapDisplayMode) {
      case 'r2r':
        const r2r = calculateR2R(debit, width);
        return r2r !== null ? r2r.toFixed(1) : '-';
      case 'pct_diff':
        return pctChange > 0 ? pctChange.toFixed(0) : '-';
      case 'debit':
      default:
        return debit !== null && debit > 0 ? debit.toFixed(2) : '-';
    }
  }, [heatmapGrid, changeGrid, heatmapDisplayMode, calculateR2R]);

  // Process volume profile using TradingView VRVP bin algorithm
  // vpByPrice: key is price * 10 (e.g., 60001 = $6000.10)
  const vpByPrice = useMemo(() => {
    const result: Record<number, number> = {};

    if (!volumeProfile?.levels || volumeProfile.levels.length === 0) {
      return result;
    }

    // Step 1: Apply sigma-based percentile capping to filter outliers
    const percentile = sigmaToPercentile(vpConfig.cappingSigma);
    const volumes = volumeProfile.levels.map(l => l.volume).sort((a, b) => a - b);
    const capIndex = Math.floor(volumes.length * percentile);
    const volumeCap = volumes[capIndex] || volumeProfile.maxVolume;

    const cappedLevels = volumeProfile.levels.map((level) => ({
      price: level.price,
      volume: Math.min(level.volume, volumeCap),
    }));

    // Step 2: Apply TradingView VRVP algorithm to bin the data
    const rebinnedLevels = calculateVolumeProfileBins(cappedLevels, vpConfig.numBins);

    // Convert rebinned levels to price-tenths format for getVpLevelsForStrike
    for (const level of rebinnedLevels) {
      const priceTenths = Math.round(level.price * 10);
      result[priceTenths] = level.volume;
    }

    return result;
  }, [volumeProfile, vpConfig.numBins, vpConfig.cappingSigma]);

  // Get volume profile levels for a strike (all $0.10 levels within ±2.5 range)
  const getVpLevelsForStrike = (strike: number): { pos: number; volume: number }[] => {
    const levels: { pos: number; volume: number }[] = [];
    const startTenths = Math.round((strike - 2.5) * 10);
    const endTenths = Math.round((strike + 2.5) * 10);

    for (let priceTenths = startTenths; priceTenths < endTenths; priceTenths++) {
      const volume = vpByPrice[priceTenths];
      if (volume !== undefined && volume > 0) {
        // Position 0 = top of row (highest price), 49 = bottom (lowest price)
        const pos = endTenths - 1 - priceTenths;
        levels.push({ pos, volume });
      }
    }
    return levels;
  };

  // Filter strikes around ATM
  const strikeIncrement = STRIKE_INCREMENT[underlying];
  const visibleStrikes = useMemo(() => {
    let baseStrikes: number[];

    if (strikes.length > 0) {
      if (!currentSpot) {
        baseStrikes = strikes.slice(0, 50);
      } else {
        const atmIndex = strikes.findIndex(s => s <= currentSpot);
        const rangeStart = Math.max(0, atmIndex - 25);
        const rangeEnd = Math.min(strikes.length, atmIndex + 25);
        baseStrikes = strikes.slice(rangeStart, rangeEnd);
      }
    } else {
      // Fallback placeholder strikes when no data
      const defaultSpot = underlying === 'I:NDX' ? 21000 : 6000;
      const basePrice = currentSpot || defaultSpot;
      const roundedBase = Math.round(basePrice / strikeIncrement) * strikeIncrement;
      const placeholderStrikes: number[] = [];
      for (let i = 25; i >= -25; i--) {
        placeholderStrikes.push(roundedBase + i * strikeIncrement);
      }
      baseStrikes = placeholderStrikes;
    }

    return baseStrikes;
  }, [strikes, currentSpot, underlying, strikeIncrement]);

  // Scroll to ATM function
  const scrollToAtm = useCallback(() => {
    if (!currentSpot || visibleStrikes.length === 0) return;

    // Find the strike closest to current spot
    let closestIndex = 0;
    let closestDiff = Math.abs(visibleStrikes[0] - currentSpot);
    for (let i = 1; i < visibleStrikes.length; i++) {
      const diff = Math.abs(visibleStrikes[i] - currentSpot);
      if (diff < closestDiff) {
        closestDiff = diff;
        closestIndex = i;
      }
    }

    // Calculate scroll position accounting for variable row heights
    let scrollPosition = 0;
    for (let i = 0; i < closestIndex; i++) {
      scrollPosition += getRowHeight(visibleStrikes[i]);
    }

    // Center the ATM in the viewport
    const viewportHeight = gexScrollRef.current?.clientHeight || 600;
    const centeredPosition = Math.max(0, scrollPosition - viewportHeight / 2 + 12);

    if (gexScrollRef.current) {
      gexScrollRef.current.scrollTop = centeredPosition;
    }
    if (heatmapScrollRef.current) {
      heatmapScrollRef.current.scrollTop = centeredPosition;
    }
  }, [currentSpot, visibleStrikes, getRowHeight]);

  // Scroll to ATM on first load only
  useEffect(() => {
    if (!hasScrolledToAtm && currentSpot && visibleStrikes.length > 0) {
      // Delay to ensure layout is fully rendered
      const timer = setTimeout(() => {
        scrollToAtm();
        setHasScrolledToAtm(true);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [hasScrolledToAtm, currentSpot, visibleStrikes, scrollToAtm]);

  // Re-center when window resizes (row height changes)
  useEffect(() => {
    let resizeTimer: ReturnType<typeof setTimeout>;

    const handleResize = () => {
      // Debounce resize events
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        scrollToAtm();
      }, 200);
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      clearTimeout(resizeTimer);
    };
  }, [scrollToAtm]);

  // Calculate max volume from VISIBLE strikes for linear scaling (individual $0.10 levels)
  const maxVpVolume = useMemo(() => {
    let max = 1;
    for (const strike of visibleStrikes) {
      const startTenths = Math.round((strike - 2.5) * 10);
      const endTenths = Math.round((strike + 2.5) * 10);
      for (let priceTenths = startTenths; priceTenths < endTenths; priceTenths++) {
        const volume = vpByPrice[priceTenths];
        if (volume !== undefined && volume > max) {
          max = volume;
        }
      }
    }
    return max;
  }, [visibleStrikes, vpByPrice]);

  // Linear scale volume to width percentage based on config
  const vpVolumeToWidth = (volume: number): number => {
    if (volume <= 0 || maxVpVolume <= 0) return 0;
    return (volume / maxVpVolume) * vpConfig.widthPercent;
  };

  // Color function based on % change from adjacent tile
  // Uses threshold state for blue/red transition point
  const debitColor = (value: number | null, pctChange: number) => {
    if (value === null || value <= 0) return '#1a1a1a';

    const maxRedPct = threshold * 2.5; // Brightest red at 2.5x threshold
    let r, g, b;

    if (pctChange < threshold) {
      // Blue zone: 0% = bright blue, threshold = very dark blue
      const t = pctChange / threshold; // 0 to 1
      // Bright blue rgb(59, 130, 246) to very dark blue rgb(15, 25, 50)
      r = Math.round(59 - t * (59 - 15));
      g = Math.round(130 - t * (130 - 25));
      b = Math.round(246 - t * (246 - 50));
    } else {
      // Red zone: threshold = very dark red, maxRedPct = bright red
      const t = Math.min((pctChange - threshold) / (maxRedPct - threshold), 1);
      // Very dark red rgb(50, 15, 15) to bright red rgb(239, 68, 68)
      r = Math.round(50 + t * (239 - 50));
      g = Math.round(15 + t * (68 - 15));
      b = Math.round(15 + t * (68 - 15));
    }

    return `rgb(${r}, ${g}, ${b})`;
  };

  const gexColor = (value: number, isPositive: boolean) => {
    const intensity = Math.min(Math.abs(value) / maxGex, 1);
    const alpha = 0.3 + intensity * 0.7;
    return isPositive
      ? `rgba(74, 222, 128, ${alpha})`
      : `rgba(248, 113, 113, ${alpha})`;
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <span className="header-greeting">
            Hi, {userProfile?.display_name || 'User'}
          </span>
          <button
            className="header-settings-btn"
            onClick={() => setSettingsOpen(true)}
            title="Settings"
          >
            Settings
          </button>
          <button
            className="header-leaderboard-btn"
            onClick={() => setLeaderboardOpen(true)}
            title="Leaderboard"
          >
            Leaderboard
          </button>
          {userProfile?.is_admin && (
            <>
              <button
                className="header-admin-btn"
                onClick={() => setTrackingAnalyticsOpen(true)}
                title="Trade Idea Analytics"
              >
                Analytics
              </button>
              <button
                className="header-admin-btn"
                onClick={() => window.location.href = '/admin'}
                title="Admin Panel"
              >
                Admin
              </button>
            </>
          )}
        </div>
        <div className="header-center">
          <div className="underlying-selector">
            <button
              className={`underlying-btn${underlying === 'I:SPX' ? ' active' : ''}`}
              onClick={() => setUnderlying('I:SPX')}
            >
              SPX
            </button>
            <button
              className={`underlying-btn${underlying === 'I:NDX' ? ' active' : ''}`}
              onClick={() => setUnderlying('I:NDX')}
            >
              NDX
            </button>
          </div>
          <div className="spot-display">
            {spot?.[underlying] && (
              <span className="spot-price">
                {underlying.replace('I:', '')} {spot[underlying].value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </span>
            )}
            {spot?.['I:VIX'] && (
              <span className="vix-price">
                VIX {spot['I:VIX'].value.toFixed(2)}
              </span>
            )}
          </div>
        </div>
        <div className={`connection-status ${connected && heartbeatPulse ? 'alive' : ''} ${!connected ? 'offline' : ''}`}>
          <div className="heartbeat-monitor">
            <svg viewBox="0 0 60 20" className={`heartbeat-line ${heartbeatPulse ? 'pulse' : ''}`}>
              {connected ? (
                <polyline
                  className={`heartbeat-trace ${heartbeatPulse ? 'pulse' : ''}`}
                  points="0,10 6,10 10,7 14,10 18,2 22,16 26,10 30,6 34,10 60,10"
                  fill="none"
                  strokeWidth="1.5"
                />
              ) : (
                <line className="flatline" x1="0" y1="10" x2="60" y2="10" strokeWidth="1.5" />
              )}
            </svg>
          </div>
          <span className="status-text">{connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </header>

      {/* Widget Row - Indicator Widgets */}
      <div className={`widget-row-container ${widgetsRowCollapsed ? 'collapsed' : ''}`}>
        <div
          className="widget-row-header"
          onClick={() => setWidgetsRowCollapsed(!widgetsRowCollapsed)}
          style={{ cursor: 'pointer' }}
        >
          <span className="panel-toggle">{widgetsRowCollapsed ? '▶' : '▼'}</span>
          <h3>Indicators</h3>
          {widgetsRowCollapsed && (
            <div className="widget-row-summary">
              <span className="summary-item">
                <span className="summary-label">Mode</span>
                <span className={`summary-value ${(marketMode?.score ?? 50) >= 60 ? 'bullish' : (marketMode?.score ?? 50) <= 40 ? 'bearish' : ''}`}>
                  {marketMode?.score?.toFixed(0) ?? '--'}
                </span>
              </span>
              <span className="summary-item">
                <span className="summary-label">VIX</span>
                <span className={`summary-value ${(spot?.['I:VIX']?.value ?? 20) > 25 ? 'elevated' : ''}`}>
                  {spot?.['I:VIX']?.value?.toFixed(1) ?? '--'}
                </span>
              </span>
              <span className="summary-item">
                <span className="summary-label">Bias</span>
                <span className={`summary-value ${(biasLfi?.directional_strength ?? 0) > 0 ? 'bullish' : (biasLfi?.directional_strength ?? 0) < 0 ? 'bearish' : ''}`}>
                  {(biasLfi?.directional_strength ?? 0) > 0 ? '▲' : (biasLfi?.directional_strength ?? 0) < 0 ? '▼' : '—'} {Math.abs(biasLfi?.directional_strength ?? 0).toFixed(0)}%
                </span>
              </span>
              <span className="summary-item">
                <span className="summary-label">LFI</span>
                <span className="summary-value">{biasLfi?.lfi_score?.toFixed(0) ?? '--'}</span>
              </span>
              <span className="summary-item">
                <span className="summary-label">SPX</span>
                <span className="summary-value">{spot?.['I:SPX']?.value?.toFixed(2) ?? '--'}</span>
              </span>
            </div>
          )}
        </div>
        {!widgetsRowCollapsed && (
        <div className="widget-row">
        {/* Market Mode Score Widget */}
        <div className="widget market-mode-widget">
          <MarketModeGaugeCard score={marketMode?.score ?? 50} />
        </div>

        {/* Liquidity Intent Map Widget - Quadrant Chart */}
        <div className="widget lim-widget-container">
          <BiasLfiQuadrantCard
            directional_strength={biasLfi?.directional_strength ?? 0}
            lfi_score={biasLfi?.lfi_score ?? 50}
          />
        </div>

        {/* Dealer Gravity Widget - Candle Chart with Bands */}
        <div className="widget dealer-gravity-widget">
          <LightweightPriceChart snap={dgSnapshot} height={280} title="Dealer Gravity" />
        </div>

        {/* VIX Regime Widget */}
        <div className="widget vix-regime-widget">
          <VixRegimeCard
            vix={spot?.['I:VIX']?.value ?? null}
            ts={spot?.['I:VIX']?.ts}
          />
        </div>

        {/* Trade Recommendations Widget */}
        <div className="widget trade-recommendations-widget">
          <TradeRecommendationsPanel
            model={tradeSelector}
            onSelectTrade={handleTradeRecommendationSelect}
            maxVisible={5}
          />
        </div>

        {/* Trade Tracking Widget (Admin Only) */}
        {userProfile?.is_admin && (
          <div className="widget trade-tracking-widget">
            <TradeTrackingPanel isOpen={true} />
          </div>
        )}

        {/* Vexy / AI Advisor Widget - Tabbed (Far Right) */}
        <div className="widget vexy-advisor-widget">
          <div className="widget-tabs">
            <button
              className={`widget-tab ${vexyAdvisorTab === 'vexy' ? 'active' : ''}`}
              onClick={() => setVexyAdvisorTab('vexy')}
            >
              🎙️ Vexy
            </button>
            <button
              className={`widget-tab ${vexyAdvisorTab === 'advisor' ? 'active' : ''}`}
              onClick={() => setVexyAdvisorTab('advisor')}
            >
              🤖 Advisor
            </button>
          </div>

          {vexyAdvisorTab === 'vexy' ? (
            <div className="widget-content vexy-content">
              {vexy?.epoch ? (
                <div className="vexy-section">
                  <div className="vexy-epoch">
                    <span className="vexy-icon">🎙️</span>
                    <span className="vexy-label">Epoch</span>
                    {typeof vexy.epoch.meta?.epoch_name === 'string' && (
                      <span className="vexy-epoch-name">{vexy.epoch.meta.epoch_name}</span>
                    )}
                  </div>
                  <div className="vexy-text epoch-text" dangerouslySetInnerHTML={{ __html: marked.parse(vexy.epoch.text || '') as string }} />
                </div>
              ) : (
                <div className="vexy-empty">Awaiting epoch...</div>
              )}
              {vexy?.event && (
                <div className="vexy-section event-section">
                  <div className="vexy-event-header">
                    <span className="vexy-icon">💥</span>
                    <span className="vexy-label">Event</span>
                    {vexy.event.ts && (
                      <span className="vexy-event-time">
                        {new Date(vexy.event.ts).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                  <div className="vexy-text event-text" dangerouslySetInnerHTML={{ __html: marked.parse(vexy.event.text || '') as string }} />
                </div>
              )}
            </div>
          ) : (
            /* AI Advisor Tab Content */
            (() => {
              const vixValue = spot?.['I:VIX']?.value || 20;
              const currentHour = new Date().getHours();
              const currentMinute = new Date().getMinutes();
              const isAfternoon = currentHour >= 14;
              const timeString = `${currentHour}:${currentMinute.toString().padStart(2, '0')}`;

              const marketCloseHour = 16;
              const hoursToClose = Math.max(0, marketCloseHour - currentHour - currentMinute / 60);

              const activeAlerts = riskGraphAlerts.filter(a => a.enabled && a.type === 'ai_theta_gamma');
              const effectiveSpot = simulatedSpot || currentSpot;

              const isZombieland = vixValue <= 17;
              const isGoldilocks = vixValue > 17 && vixValue <= 32;
              const isChaos = vixValue > 32;
              const isBatmanTerritory = vixValue > 40;
              const isGammaScalpWindow = isZombieland && isAfternoon;
              const isTimeWarp = vixValue <= 15;

              const commentary: string[] = [];
              let advisorMood: 'neutral' | 'bullish' | 'cautious' | 'alert' = 'neutral';

              if (isBatmanTerritory) {
                commentary.push(`🦇 Batman territory at VIX ${vixValue.toFixed(1)}. Gamma is crushed - bracket spot with wide flies.`);
                advisorMood = 'bullish';
              } else if (isChaos) {
                commentary.push(`Chaos zone. Wide flies cheap, suppressed gamma. Good for asymmetric setups.`);
                advisorMood = 'bullish';
              } else if (isGammaScalpWindow) {
                commentary.push(`⚡ Gamma Scalp window OPEN. Look for backstop to sandwich 10-20w fly near spot.`);
                advisorMood = 'bullish';
              } else if (isTimeWarp && !isAfternoon) {
                commentary.push(`⏰ TimeWarp. VIX ${vixValue.toFixed(1)} - go 1-2 DTE, 0 DTE premium gone.`);
                advisorMood = 'cautious';
              } else if (isZombieland) {
                commentary.push(`Zombieland. High gamma - narrow flies, manage carefully.`);
                advisorMood = 'cautious';
              } else if (isGoldilocks) {
                commentary.push(`Goldilocks. Ideal for OTM butterfly utility trades.`);
                advisorMood = 'neutral';
              }

              if (hoursToClose <= 0.5) {
                commentary.push(`⚠️ Final 30 min. Gamma max. Close or tight stops.`);
                advisorMood = 'alert';
              } else if (hoursToClose <= 1) {
                commentary.push(`Last hour. Protect gains aggressively.`);
                if (advisorMood === 'neutral' || advisorMood === 'bullish') advisorMood = 'cautious';
              }

              if (activeAlerts.length > 0 && effectiveSpot) {
                activeAlerts.forEach(alert => {
                  // Use memoized Map lookup for O(1) instead of O(n) .find()
                  const strategy = strategyLookup.get(alert.strategyId);
                  if (!strategy) return;

                  const entryDebit = alert.entryDebit || strategy.debit || 1;
                  const adjustedVix = timeMachineEnabled ? vixValue + simVolatilityOffset : vixValue;
                  const volatility = Math.max(0.05, adjustedVix) / 100;
                  const timeOffset = timeMachineEnabled ? simTimeOffsetHours : 0;

                  const pnlAtSpot = calculateStrategyTheoreticalPnL(strategy, effectiveSpot, volatility, 0.05, timeOffset);
                  const currentProfit = pnlAtSpot / 100;
                  const profitPercent = entryDebit > 0 ? (currentProfit / entryDebit) * 100 : 0;

                  const pnlPlus = calculateStrategyTheoreticalPnL(strategy, effectiveSpot + 1, volatility, 0.05, timeOffset);
                  const pnlMinus = calculateStrategyTheoreticalPnL(strategy, effectiveSpot - 1, volatility, 0.05, timeOffset);
                  const delta = (pnlPlus - pnlMinus) / 200;

                  const strategyLabel = `${strategy.strike}${strategy.width ? '/' + strategy.width : ''}`;

                  if (profitPercent >= 100) {
                    commentary.push(`✨ ${strategyLabel}: ${profitPercent.toFixed(0)}% profit${Math.abs(delta) < 0.5 ? ', at peak' : ''}.`);
                  } else if (profitPercent >= 50) {
                    commentary.push(`💰 ${strategyLabel}: ${profitPercent.toFixed(0)}% profit.`);
                  } else if (profitPercent > 0) {
                    commentary.push(`${strategyLabel}: ${profitPercent.toFixed(0)}% - building.`);
                  } else {
                    commentary.push(`🔻 ${strategyLabel}: underwater.`);
                    if (advisorMood === 'neutral' || advisorMood === 'bullish') advisorMood = 'cautious';
                  }
                });
              }

              if (commentary.length === 0) {
                commentary.push(`VIX ${vixValue.toFixed(1)}, ${hoursToClose.toFixed(1)}h to close.`);
              }

              return (
                <div className={`ai-advisor-content ${advisorMood}`}>
                  <div className="ai-advisor-time">{timeString} ET • {hoursToClose.toFixed(1)}h left</div>
                  <div className="ai-advisor-commentary">
                    {commentary.map((line, i) => (
                      <p key={i} className="ai-commentary-line">{line}</p>
                    ))}
                  </div>
                </div>
              );
            })()
          )}
        </div>
        </div>
        )}
      </div>

      {/* Controls Row - GEX/Heatmap settings */}
      <div className="controls">
        {/* GEX - collapsible */}
        <div className={`control-group collapsible-control ${gexExpanded ? 'expanded' : ''}`}>
          <button
            className={`control-toggle ${gexExpanded ? 'active' : ''}`}
            onClick={() => setGexExpanded(!gexExpanded)}
          >
            GEX
          </button>
          {gexExpanded && (
            <div className="button-group">
              <button
                className={gexMode === 'net' ? 'active' : ''}
                onClick={() => setGexMode('net')}
              >
                Net
              </button>
              <button
                className={gexMode === 'combined' ? 'active' : ''}
                onClick={() => setGexMode('combined')}
              >
                C/P
              </button>
            </div>
          )}
        </div>

        {/* Strategy - collapsible */}
        <div className={`control-group collapsible-control ${strategyExpanded ? 'expanded' : ''}`}>
          <button
            className={`control-toggle ${strategyExpanded ? 'active' : ''}`}
            onClick={() => setStrategyExpanded(!strategyExpanded)}
          >
            Strategy
          </button>
          {strategyExpanded && (
            <div className="button-group">
              {(['single', 'vertical', 'butterfly'] as Strategy[]).map(s => (
                <button
                  key={s}
                  className={strategy === s ? 'active' : ''}
                  onClick={() => setStrategy(s)}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Side - collapsible */}
        <div className={`control-group collapsible-control ${sideExpanded ? 'expanded' : ''}`}>
          <button
            className={`control-toggle ${sideExpanded ? 'active' : ''}`}
            onClick={() => setSideExpanded(!sideExpanded)}
          >
            Side
          </button>
          {sideExpanded && (
            <div className="button-group">
              <button
                className={side === 'call' ? 'active' : ''}
                onClick={() => setSide('call')}
              >
                Call
              </button>
              <button
                className={side === 'put' ? 'active' : ''}
                onClick={() => setSide('put')}
              >
                Put
              </button>
              <button
                className={side === 'both' ? 'active' : ''}
                onClick={() => setSide('both')}
              >
                Both
              </button>
            </div>
          )}
        </div>

        {/* DTE - collapsible */}
        <div className={`control-group collapsible-control ${dteExpanded ? 'expanded' : ''}`}>
          <button
            className={`control-toggle ${dteExpanded ? 'active' : ''}`}
            onClick={() => setDteExpanded(!dteExpanded)}
          >
            DTE
          </button>
          {dteExpanded && (
            <div className="button-group">
              {availableDtes.map(d => (
                <button
                  key={d}
                  className={dte === d ? 'active' : ''}
                  onClick={() => setDte(d)}
                >
                  {d}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Gradient */}
        <div className="control-group">
          <label>Gradient {threshold}%</label>
          <input
            type="range"
            min="1"
            max="100"
            value={threshold}
            onChange={(e) => setThreshold(parseInt(e.target.value))}
            className="threshold-slider"
          />
        </div>

        <div className="control-separator" />

        {/* Heatmap Display Controls */}
        <div className="control-group">
          <label>Display</label>
          <select
            value={heatmapDisplayMode}
            onChange={(e) => setHeatmapDisplayMode(e.target.value as 'debit' | 'r2r' | 'pct_diff')}
            className="control-select"
          >
            <option value="debit">Debit</option>
            <option value="r2r">R2R</option>
            <option value="pct_diff">% Diff</option>
          </select>
        </div>

        <div className="control-group">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showEMBoundary}
              onChange={(e) => setShowEMBoundary(e.target.checked)}
            />
            EM ±{expectedMove.toFixed(0)}
          </label>
        </div>

        <div className="control-group">
          <label>Optimal {optimalZoneThreshold}%</label>
          <input
            type="range"
            min="20"
            max="90"
            value={optimalZoneThreshold}
            onChange={(e) => setOptimalZoneThreshold(Number(e.target.value))}
            className="threshold-slider"
          />
        </div>

        <div className="control-separator" />

        {/* MEL Status */}
        <MELStatusBar snapshot={mel.snapshot} connected={mel.connected} />
      </div>

      {/* Main Content Row - Horizontal Scrollable */}
      <div className="main-content-row">
        {/* GEX Panel - Inline (collapsible via header) */}
        <div className={`panel gex-panel ${gexCollapsed ? 'collapsed' : ''}`}>
          <div className="panel-header" onClick={() => setGexCollapsed(!gexCollapsed)}>
            <span className="panel-toggle">{gexCollapsed ? '▶' : '▼'}</span>
            <h3>GEX + Volume Profile</h3>
          </div>
          {!gexCollapsed && (
            <div className="panel-content gex-panel-content">
              {/* Indicator Labels */}
              <div className="gex-indicator-labels">
                <div
                  className={`gex-indicator-label ${!vpConfig.enabled ? 'disabled' : ''}`}
                  onDoubleClick={() => setShowVpSettingsDialog(true)}
                  title="Double-click for settings"
                >
                  <span className="indicator-dot" style={{ backgroundColor: vpConfig.color }} />
                  <span className="indicator-text">VRVP</span>
                  <button
                    className="indicator-icon-btn"
                    onClick={(e) => { e.stopPropagation(); setVpConfig({ ...vpConfig, enabled: !vpConfig.enabled }); }}
                    title={vpConfig.enabled ? 'Hide' : 'Show'}
                  >
                    {vpConfig.enabled ? '👁' : '👁‍🗨'}
                  </button>
                  <button
                    className="indicator-icon-btn"
                    onClick={(e) => { e.stopPropagation(); setShowVpSettingsDialog(true); }}
                    title="Settings"
                  >
                    ⚙️
                  </button>
                </div>
              </div>

              {/* VP Settings Dialog - Same floating dialog as Dealer Gravity */}
              {showVpSettingsDialog && (
                <div className="dg-settings-overlay" onClick={() => setShowVpSettingsDialog(false)}>
                  <div onClick={(e) => e.stopPropagation()}>
                    <VolumeProfileSettings
                      config={vpConfig}
                      onConfigChange={setVpConfig}
                      onSaveDefault={saveVpDefault}
                      onResetToFactory={resetVpToFactory}
                      onClose={() => setShowVpSettingsDialog(false)}
                    />
                  </div>
                </div>
              )}

              {/* Invisible overlay over strike column - click to expand */}
              <div
                className="gex-strike-overlay"
                onClick={() => setGexDrawerOpen(true)}
                title="Click to expand"
              />
              {/* GEX Header - outside scroll container */}
              <div className="gex-header">
                <div className="header-gex">GEX</div>
                <div className="header-strike">Strike</div>
              </div>
              {/* GEX Body - scrollable */}
              <div
                className="gex-scroll-container"
                ref={gexScrollRef}
                onScroll={handleGexScroll}
              >
                {visibleStrikes.map((strike, idx) => {
                  const gex = gexByStrike[strike] || { calls: 0, puts: 0 };
                  const netGex = gex.calls - gex.puts;
                  const prevStrike = idx > 0 ? visibleStrikes[idx - 1] : Infinity;
                  const nextStrike = idx < visibleStrikes.length - 1 ? visibleStrikes[idx + 1] : -Infinity;
                  const isAtmBelow = currentSpot && strike <= currentSpot && prevStrike > currentSpot;
                  const isAtmAbove = currentSpot && strike > currentSpot && nextStrike <= currentSpot;
                  const isAtm = isAtmBelow || isAtmAbove;
                  const rowHeight = getRowHeight(strike);
                  const isCompressed = rowHeight < 16;

                  return (
                    <div
                      key={strike}
                      className={`gex-row ${isAtm ? 'atm' : ''} ${isAtmBelow ? 'atm-line' : ''} ${isCompressed ? 'compressed' : ''}`}
                      style={{ height: `${rowHeight}px`, minHeight: `${rowHeight}px` }}
                    >
                      <div className="gex-cell-standalone" style={{ height: `${rowHeight}px` }}>
                        {/* Volume profile */}
                        {vpConfig.enabled && getVpLevelsForStrike(strike).map((level, idx) => (
                          <div
                            key={idx}
                            className="volume-profile-bar"
                            style={{
                              width: `${vpVolumeToWidth(level.volume)}%`,
                              top: `${(level.pos / 50) * 100}%`,
                              height: `${100 / 50}%`,
                              backgroundColor: vpConfig.color,
                              opacity: (100 - vpConfig.transparency) / 100,
                            }}
                          />
                        ))}
                        {/* Left side (puts or negative net) */}
                        <div className="gex-half left">
                          {gexMode === 'net' ? (
                            netGex < 0 && (
                              <div
                                className="gex-bar"
                                style={{
                                  width: `${(Math.abs(netGex) / maxNetGex) * 100}%`,
                                  backgroundColor: gexColor(netGex, false),
                                }}
                              />
                            )
                          ) : (
                            <div
                              className="gex-bar"
                              style={{
                                width: `${(Math.abs(gex.puts) / maxGex) * 100}%`,
                                backgroundColor: gexColor(gex.puts, false),
                              }}
                            />
                          )}
                        </div>
                        {/* Center axis */}
                        <div className="gex-axis" />
                        {/* Right side (calls or positive net) */}
                        <div className="gex-half right">
                          {gexMode === 'net' ? (
                            netGex > 0 && (
                              <div
                                className="gex-bar"
                                style={{
                                  width: `${(Math.abs(netGex) / maxNetGex) * 100}%`,
                                  backgroundColor: gexColor(netGex, true),
                                }}
                              />
                            )
                          ) : (
                            <div
                              className="gex-bar"
                              style={{
                                width: `${(Math.abs(gex.calls) / maxGex) * 100}%`,
                                backgroundColor: gexColor(gex.calls, true),
                              }}
                            />
                          )}
                        </div>
                      </div>
                      <div className={`strike-label ${isAtm ? 'atm' : ''}`} style={{ height: `${rowHeight}px` }}>
                        {!isCompressed && strike}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Heatmap Panel */}
        <div className={`panel heatmap-panel ${heatmapCollapsed ? 'collapsed' : ''}`}>
          <div className="panel-header" onClick={() => setHeatmapCollapsed(!heatmapCollapsed)} style={{ cursor: 'pointer' }}>
            <span className="panel-toggle">{heatmapCollapsed ? '▶' : '▼'}</span>
            <h3>Heatmap</h3>
            {!heatmapCollapsed && (
              <div className="panel-header-icons">
                <button
                  className={`header-icon ${scrollLocked ? 'active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); setScrollLocked(!scrollLocked); }}
                  title={scrollLocked ? 'Unlock scroll' : 'Lock scroll'}
                >
                  {scrollLocked ? '🔒' : '🔓'}
                </button>
                <button
                  className="header-icon"
                  onClick={(e) => { e.stopPropagation(); scrollToAtm(); }}
                  title="Center on ATM"
                >
                  ◎
                </button>
              </div>
            )}
          </div>
          {!heatmapCollapsed && (
            <div className="panel-content">
              {/* Invisible drag overlay for strike column */}
              <div
                className={`strike-drag-overlay ${strikesDragActive ? 'drag-active' : ''}`}
                onMouseDown={handleStrikesDragStart}
              />

              {/* Heatmap Header - outside scroll container */}
              <div className="heatmap-header">
                <div className="header-strike">Strike</div>
                {strategy === 'single' ? (
                  <div className="header-width">Mid</div>
                ) : (
                  widths.map(w => (
                    <div key={w} className="header-width">{w}</div>
                  ))
                )}
              </div>
              {/* Heatmap Body - scrollable */}
              <div
                className="heatmap-scroll-container"
                ref={heatmapScrollRef}
                onScroll={handleHeatmapScroll}
              >
                {visibleStrikes.map((strike, idx) => {
                    // ATM: both strikes adjacent to spot (spot falls between them)
                    const prevStrike = idx > 0 ? visibleStrikes[idx - 1] : Infinity;
                    const nextStrike = idx < visibleStrikes.length - 1 ? visibleStrikes[idx + 1] : -Infinity;
                    const isAtmBelow = currentSpot && strike <= currentSpot && prevStrike > currentSpot;
                    const isAtmAbove = currentSpot && strike > currentSpot && nextStrike <= currentSpot;
                    const isAtm = isAtmBelow || isAtmAbove;
                    const strikeData = heatmapGrid[strike] || {};
                    const atEMBoundary = showEMBoundary && isAtEMBoundary(strike);
                    const rowHeight = getRowHeight(strike);
                    const isCompressed = rowHeight < 16; // Hide text when too compressed

                    return (
                      <div
                        key={strike}
                        className={`heatmap-row ${isAtm ? 'atm' : ''} ${isAtmBelow ? 'atm-line' : ''} ${atEMBoundary ? 'em-boundary' : ''} ${isCompressed ? 'compressed' : ''}`}
                        style={{ height: `${rowHeight}px`, minHeight: `${rowHeight}px` }}
                      >
                        <div
                          className={`strike-cell ${isAtm ? 'atm' : ''} ${atEMBoundary ? 'em-boundary' : ''}`}
                          style={{ height: `${rowHeight}px` }}
                        >
                          {!isCompressed && strike}
                        </div>
                        {strategy === 'single' ? (
                          (() => {
                            const val = strikeData[0] ?? null;
                            const isValid = val !== null && val > 0;
                            return (
                              <div
                                className="width-cell clickable"
                                style={{ backgroundColor: debitColor(val, changeGrid[strike]?.[0] ?? 0), height: `${rowHeight}px` }}
                                onClick={() => handleTileClick(strike, 0, val)}
                              >
                                {!isCompressed && (isValid ? val.toFixed(2) : '-')}
                              </div>
                            );
                          })()
                        ) : (
                          widths.map(w => {
                            const val = strikeData[w] ?? null;
                            const pctChange = changeGrid[strike]?.[w] ?? 0;
                            const inOptimalZone = isInOptimalZone(strike, w);
                            const tileClasses = [
                              'width-cell',
                              'clickable',
                              inOptimalZone ? 'optimal-zone' : '',
                              atEMBoundary ? 'em-boundary-tile' : '',
                            ].filter(Boolean).join(' ');

                            return (
                              <div
                                key={w}
                                className={tileClasses}
                                style={{ backgroundColor: debitColor(val, pctChange), height: `${rowHeight}px` }}
                                onClick={() => handleTileClick(strike, w, val)}
                              >
                                {!isCompressed && getDisplayValue(strike, w)}
                              </div>
                            );
                          })
                        )}
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>

        {/* Risk Graph Panel */}
        <RiskGraphPanel
          strategies={riskGraphStrategies}
          onRemoveStrategy={removeFromRiskGraph}
          onToggleStrategyVisibility={toggleStrategyVisibility}
          onUpdateStrategyDebit={updateStrategyDebit}
          onStartNewAlert={startNewAlert}
          onStartEditingAlert={startEditingAlert}
          priceAlertLines={priceAlertLines}
          onDeletePriceAlertLine={deletePriceAlertLine}
          onOpenAlertDialog={(strategyId, price, condition) => {
            setAlertModalStrategy(strategyId);
            setAlertModalInitialPrice(price);
            setAlertModalInitialCondition(condition);
          }}
          spotPrice={currentSpot || 6000}
          vix={spot?.['I:VIX']?.value || 20}
          timeMachineEnabled={timeMachineEnabled}
          onTimeMachineToggle={() => setTimeMachineEnabled(!timeMachineEnabled)}
          simTimeOffsetHours={simTimeOffsetHours}
          onSimTimeChange={setSimTimeOffsetHours}
          simVolatilityOffset={simVolatilityOffset}
          onSimVolatilityChange={setSimVolatilityOffset}
          simSpotOffset={simSpotOffset}
          onSimSpotChange={setSimSpotOffset}
          onResetSimulation={() => {
            setSimTimeOffsetHours(0);
            setSimVolatilityOffset(0);
            setSimSpotOffset(0);
          }}
          onOpenJournal={() => setJournalOpen(true)}
          onImportToS={() => setShowTosImport(true)}
          onEditStrategy={(id) => {
            const strat = riskGraphStrategies.find(s => s.id === id);
            if (strat) setEditingStrategy(strat);
          }}
          onLogTrade={(strategy) => {
            // Prefill trade entry with strategy data
            setTradeEntryPrefill({
              symbol: strategy.symbol || underlying.replace('I:', ''),
              underlying: underlying,
              strategy: strategy.strategy,
              side: strategy.side,
              strike: strategy.strike,
              width: strategy.width,
              dte: strategy.dte,
              entry_price: strategy.debit || undefined,
              entry_spot: currentSpot || undefined,
              source: 'risk_graph',
            });
            setTradeEntryOpen(true);
          }}
          onOpenMonitor={() => setMonitorOpen(true)}
          pendingOrderCount={pendingOrderCount}
          openTradeCount={openTradeCount}
        />

      </div>

      <div className="footer">
        <span>Heatmap: {heatmap?.ts ? new Date(heatmap.ts * 1000).toLocaleTimeString() : '-'}</span>
        <span>GEX: {gexCalls?.ts ? new Date(gexCalls.ts * 1000).toLocaleTimeString() : '-'}</span>
        <span>Tiles: {Object.keys(heatmap?.tiles || {}).length}</span>
        <span>v{heatmap?.version || '-'}</span>
      </div>

      {/* Commentary Panel (Left Edge) */}
      <div
        className={`commentary-edge-bar ${!commentaryCollapsed ? 'open' : ''}`}
        onClick={() => setCommentaryCollapsed(!commentaryCollapsed)}
      >
        <span className="edge-bar-label">💬 Observer</span>
      </div>

      <div className={`commentary-overlay ${!commentaryCollapsed ? 'open' : ''}`}>
        <div
          className="commentary-close-bar"
          onClick={() => setCommentaryCollapsed(true)}
        >
          <span className="close-bar-label">Close</span>
        </div>
        <div className="commentary-panel-inner">
          <ObserverPanel />
        </div>
      </div>

      {/* Trade Log Edge Bar + Overlay */}
      <div
        className={`trade-log-edge-bar ${!tradeLogCollapsed ? 'open' : ''}`}
        onClick={() => setTradeLogCollapsed(!tradeLogCollapsed)}
      >
        <span className="edge-bar-label">Trade Log</span>
      </div>

      <div className={`trade-log-overlay ${!tradeLogCollapsed ? 'open' : ''}`}>
        <div
          className="trade-log-close-bar"
          onClick={() => setTradeLogCollapsed(true)}
        >
          <span className="close-bar-label">Close</span>
        </div>
        <div className="trade-log-panel-inner">
          {playbookOpen ? (
            <PlaybookView
              onClose={() => {
                setPlaybookOpen(false);
                if (playbookSource === 'journal') {
                  setJournalOpen(true);
                }
                setPlaybookSource(null);
              }}
              backLabel={playbookSource === 'journal' ? 'Back to Journal' : 'Back to Trades'}
            />
          ) : journalOpen ? (
            <JournalView
              onClose={() => {
                setJournalOpen(false);
                setJournalTradeContext(null);
              }}
              onOpenPlaybook={() => { setPlaybookSource('journal'); setPlaybookOpen(true); }}
              tradeContext={journalTradeContext}
            />
          ) : reportingLogId ? (
            <ReportingView
              logId={reportingLogId}
              logName={selectedLog?.name || 'Trade Log'}
              onClose={handleCloseReporting}
            />
          ) : (
            <>
              <div className="trade-log-overlay-content">
              {!tradeLogCollapsed && (
                <>
                  <TradeLogPanel
                    onOpenTradeEntry={openTradeEntry}
                    onEditTrade={openTradeEdit}
                    onViewReporting={handleViewReporting}
                    onManageLogs={handleManageLogs}
                    onOpenJournal={(tradeContext) => {
                      setJournalTradeContext(tradeContext || null);
                      setJournalOpen(true);
                    }}
                    onOpenPlaybook={() => { setPlaybookSource('tradelog'); setPlaybookOpen(true); }}
                    selectedLogId={selectedLog?.id || null}
                    selectedLog={selectedLog}
                    onSelectLog={handleSelectLog}
                    refreshTrigger={tradeRefreshTrigger}
                  />
                </>
              )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* GEX Expanded Drawer Overlay */}
      <div className={`gex-overlay ${gexDrawerOpen ? 'open' : ''}`}>
        <div
          className="gex-close-bar"
          onClick={() => setGexDrawerOpen(false)}
        >
          <span className="close-bar-label">Close</span>
        </div>
        <div className="gex-panel-inner">
          <GexChartPanel
            symbol="SPX"
            volumeProfile={volumeProfile}
            gexByStrike={gexByStrike}
            maxGex={maxGex}
            maxNetGex={maxNetGex}
            gexMode={gexMode}
            currentSpot={currentSpot}
            height={window.innerHeight - 100}
            isOpen={gexDrawerOpen}
          />
        </div>
      </div>

      {/* Log Manager Modal */}
      <LogManagerModal
        isOpen={logManagerOpen}
        onClose={() => setLogManagerOpen(false)}
        selectedLogId={selectedLog?.id || null}
        onSelectLog={handleSelectLog}
        onLogCreated={handleLogCreated}
      />

      {/* Trade Detail Modal */}
      <TradeDetailModal
        trade={tradeDetailTrade}
        isOpen={tradeDetailTrade !== null}
        onClose={handleTradeDetailClose}
        onTradeUpdated={onTradeSaved}
      />

      {/* Settings Modal */}
      {settingsOpen && (
        <SettingsModal onClose={() => setSettingsOpen(false)} />
      )}

      {/* Tracking Analytics Dashboard (Admin Only) */}
      {userProfile?.is_admin && (
        <TrackingAnalyticsDashboard
          isOpen={trackingAnalyticsOpen}
          onClose={() => setTrackingAnalyticsOpen(false)}
        />
      )}

      {/* Leaderboard Modal */}
      {leaderboardOpen && (
        <LeaderboardView onClose={() => setLeaderboardOpen(false)} />
      )}

      {/* Position Monitor Panel */}
      {monitorOpen && (
        <MonitorPanel
          onClose={() => setMonitorOpen(false)}
          onCloseTrade={() => {
            // Refresh counts after closing a trade
            fetchMonitorCounts();
          }}
          onCancelOrder={() => {
            // Refresh counts after cancelling an order
            fetchMonitorCounts();
          }}
        />
      )}

      {/* Strategy Popup Modal */}
      {selectedTile && (
        <div className="popup-overlay" onClick={closePopup}>
          <div className="popup-modal" onClick={e => e.stopPropagation()}>
            <div className="popup-header">
              <h3>
                {selectedTile.strategy === 'single' ? 'Single Option' :
                 selectedTile.strategy === 'vertical' ? 'Vertical Spread' : 'Butterfly'}
              </h3>
              <button className="popup-close" onClick={closePopup}>&times;</button>
            </div>

            <div className="popup-body">
              <div className="order-details">
                <div className="order-row">
                  <span className="order-label">Symbol</span>
                  <span className="order-value">SPX</span>
                </div>
                <div className="order-row">
                  <span className="order-label">Expiration</span>
                  <span className="order-value">{selectedTile.expiration}</span>
                </div>
                <div className="order-row">
                  <span className="order-label">Strike</span>
                  <span className="order-value">{selectedTile.strike}</span>
                </div>
                {selectedTile.strategy !== 'single' && (
                  <div className="order-row">
                    <span className="order-label">Width</span>
                    <span className="order-value">{selectedTile.width}</span>
                  </div>
                )}
                <div className="order-row">
                  <span className="order-label">Side</span>
                  <span className="order-value side-badge" data-side={selectedTile.side}>
                    {selectedTile.side.toUpperCase()}
                  </span>
                </div>
                <div className="order-row">
                  <span className="order-label">DTE</span>
                  <span className="order-value">{selectedTile.dte}</span>
                </div>
                <div className="order-row highlight">
                  <span className="order-label">Debit</span>
                  <span className="order-value price">
                    {selectedTile.debit !== null ? `$${selectedTile.debit.toFixed(2)}` : '-'}
                  </span>
                </div>
              </div>

              {selectedTile.strategy === 'butterfly' && (
                <div className="strategy-legs">
                  <div className="leg">Buy 1x {selectedTile.strike - selectedTile.width} {selectedTile.side}</div>
                  <div className="leg">Sell 2x {selectedTile.strike} {selectedTile.side}</div>
                  <div className="leg">Buy 1x {selectedTile.strike + selectedTile.width} {selectedTile.side}</div>
                </div>
              )}

              {selectedTile.strategy === 'vertical' && (
                <div className="strategy-legs">
                  <div className="leg">Buy 1x {selectedTile.strike} {selectedTile.side}</div>
                  <div className="leg">
                    Sell 1x {selectedTile.side === 'call'
                      ? selectedTile.strike + selectedTile.width
                      : selectedTile.strike - selectedTile.width} {selectedTile.side}
                  </div>
                </div>
              )}

              <div className="tos-script">
                <label>TOS Script</label>
                <code>{generateTosScript(selectedTile)}</code>
              </div>
            </div>

            <div className="popup-actions">
              <button
                className={`btn btn-primary${tosCopied ? ' copied' : ''}`}
                onClick={copyTosScript}
              >
                {tosCopied ? 'Copied!' : 'Copy TOS Script'}
              </button>
              <button className="btn btn-secondary" onClick={addToRiskGraph}>
                Add to Risk Graph
              </button>
              <button
                className="btn btn-success"
                onClick={() => {
                  openTradeEntry({
                    symbol: 'SPX',
                    underlying,
                    strategy: selectedTile.strategy as 'single' | 'vertical' | 'butterfly',
                    side: selectedTile.side as 'call' | 'put',
                    strike: selectedTile.strike,
                    width: selectedTile.width,
                    dte: selectedTile.dte,
                    entry_price: selectedTile.debit || undefined,
                    entry_spot: currentSpot || undefined,
                    source: 'heatmap'
                  });
                  closePopup();
                }}
              >
                Log Trade
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Trade Entry Modal */}
      <TradeEntryModal
        isOpen={tradeEntryOpen}
        onClose={closeTradeEntry}
        onSaved={onTradeSaved}
        prefillData={tradeEntryPrefill}
        editTrade={editingTrade}
        currentSpot={currentSpot}
        isMarketOpen={isMarketOpen}
      />

      {/* Alert Creation Modal */}
      <AlertCreationModal
        isOpen={alertModalStrategy !== null}
        onClose={() => {
          setAlertModalStrategy(null);
          setAlertModalInitialPrice(null);
          setAlertModalEditingAlert(null);
        }}
        onSave={(alertData) => {
          if (alertModalStrategy) {
            const strategy = riskGraphStrategies.find(s => s.id === alertModalStrategy);
            const strategyLabel = strategy
              ? `${strategy.strategy === 'butterfly' ? 'BF' : strategy.strategy === 'vertical' ? 'VS' : 'SGL'} ${strategy.strike}${strategy.width > 0 ? '/' + strategy.width : ''} ${strategy.side.charAt(0).toUpperCase()}`
              : 'Chart Alert';

            if (alertData.id) {
              // Update existing alert via context
              contextUpdateAlert({
                id: alertData.id,
                type: alertData.type,
                condition: alertData.condition,
                targetValue: alertData.targetValue,
                color: alertData.color,
                behavior: alertData.behavior,
                minProfitThreshold: alertData.minProfitThreshold,
              });
            } else {
              // Create new alert via context
              contextCreateAlert({
                type: alertData.type,
                source: {
                  type: 'strategy',
                  id: alertModalStrategy,
                  label: strategyLabel,
                },
                condition: alertData.condition,
                targetValue: alertData.targetValue,
                color: alertData.color,
                behavior: alertData.behavior,
                strategyId: alertModalStrategy,
                entryDebit: strategy?.debit || undefined,
                minProfitThreshold: alertData.minProfitThreshold,
              });
            }
          }
        }}
        strategyLabel={(() => {
          const strat = riskGraphStrategies.find(s => s.id === alertModalStrategy);
          if (!strat) return 'Chart Alert';
          const typeLabel = strat.strategy === 'butterfly' ? 'BF' : strat.strategy === 'vertical' ? 'VS' : 'SGL';
          return `${typeLabel} ${strat.strike}`;
        })()}
        currentSpot={currentSpot}
        currentDebit={riskGraphStrategies.find(s => s.id === alertModalStrategy)?.debit || null}
        initialPrice={alertModalInitialPrice}
        initialCondition={alertModalInitialCondition}
        editingAlert={alertModalEditingAlert}
      />

      {/* ToS Import Modal */}
      <TosImportModal
        isOpen={showTosImport}
        onClose={() => setShowTosImport(false)}
        onImport={handleTosImport}
      />

      {/* Strategy Edit Modal */}
      <StrategyEditModal
        isOpen={editingStrategy !== null}
        onClose={() => setEditingStrategy(null)}
        onSave={handleStrategyEdit}
        strategy={editingStrategy}
      />

      {/* FOTW Path Indicator */}
      <PathIndicator />

      {/* Welcome Tour (shows once for new users) */}
      <WelcomeTour />

    </div>
  );
}

export default App;
