import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import './App.css';
import LightweightPriceChart from './components/LightweightPriceChart';
import type { RawSnapshot } from './components/LightweightPriceChart';
import BiasLfiQuadrantCard from './components/BiasLfiQuadrantCard';
import MarketModeGaugeCard from './components/MarketModeGaugeCard';
import VixRegimeCard from './components/VixRegimeCard';
import TradeLogPanel from './components/TradeLogPanel';
import type { Trade } from './components/TradeLogPanel';
import type { TradeLog } from './components/LogSelector';
import TradeEntryModal from './components/TradeEntryModal';
import type { TradeEntryData } from './components/TradeEntryModal';
import EquityChartWidget from './components/EquityChartWidget';
import LogManagerModal from './components/LogManagerModal';
import TradeDetailModal from './components/TradeDetailModal';
import ReportingView from './components/ReportingView';
import SettingsModal from './components/SettingsModal';

const SSE_BASE = 'http://localhost:3001';

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

// Strategy details for popup/risk graph (side is always 'call' or 'put', never 'both')
interface SelectedStrategy {
  strategy: Strategy;
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
}

interface RiskGraphStrategy extends SelectedStrategy {
  id: string;
  addedAt: number;
  visible: boolean;
}

// Gaussian smoothing for volume profile
function gaussianSmooth(data: number[], kernelSize: number = 5): number[] {
  if (data.length === 0) return data;

  // Generate Gaussian kernel
  const sigma = kernelSize / 4;
  const kernel: number[] = [];
  let kernelSum = 0;
  const halfSize = Math.floor(kernelSize / 2);

  for (let i = -halfSize; i <= halfSize; i++) {
    const value = Math.exp(-(i * i) / (2 * sigma * sigma));
    kernel.push(value);
    kernelSum += value;
  }

  // Normalize kernel
  for (let i = 0; i < kernel.length; i++) {
    kernel[i] /= kernelSum;
  }

  // Apply convolution
  const result: number[] = [];
  for (let i = 0; i < data.length; i++) {
    let sum = 0;
    for (let j = 0; j < kernel.length; j++) {
      const dataIndex = i + j - halfSize;
      if (dataIndex >= 0 && dataIndex < data.length) {
        sum += data[dataIndex] * kernel[j];
      } else {
        // Edge handling: use nearest value
        const clampedIndex = Math.max(0, Math.min(data.length - 1, dataIndex));
        sum += data[clampedIndex] * kernel[j];
      }
    }
    result.push(sum);
  }

  return result;
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
function calculateStrategyTheoreticalPnL(
  strat: { strategy: Strategy; side: Side; strike: number; width: number; debit: number | null; dte: number },
  underlyingPrice: number,
  volatility: number,
  riskFreeRate: number = 0.05
): number {
  const debit = strat.debit ?? 0;
  const multiplier = 100;
  const T = getTimeToExpiration(strat.dte); // Actual time to expiration in years
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

// Calculate P&L for a single strategy at a given underlying price (at expiration)
function calculateStrategyPnL(
  strat: { strategy: Strategy; side: Side; strike: number; width: number; debit: number | null },
  underlyingPrice: number
): number {
  const debit = strat.debit ?? 0;
  const multiplier = 100; // SPX options multiplier

  if (strat.strategy === 'single') {
    if (strat.side === 'call') {
      // Long call: max(0, price - strike) - premium
      const intrinsic = Math.max(0, underlyingPrice - strat.strike);
      return (intrinsic - debit) * multiplier;
    } else {
      // Long put: max(0, strike - price) - premium
      const intrinsic = Math.max(0, strat.strike - underlyingPrice);
      return (intrinsic - debit) * multiplier;
    }
  }

  if (strat.strategy === 'vertical') {
    if (strat.side === 'call') {
      // Bull call spread: long lower strike, short higher strike
      const longStrike = strat.strike;
      const shortStrike = strat.strike + strat.width;
      const longValue = Math.max(0, underlyingPrice - longStrike);
      const shortValue = Math.max(0, underlyingPrice - shortStrike);
      return (longValue - shortValue - debit) * multiplier;
    } else {
      // Bear put spread: long higher strike, short lower strike
      const longStrike = strat.strike;
      const shortStrike = strat.strike - strat.width;
      const longValue = Math.max(0, longStrike - underlyingPrice);
      const shortValue = Math.max(0, shortStrike - underlyingPrice);
      return (longValue - shortValue - debit) * multiplier;
    }
  }

  if (strat.strategy === 'butterfly') {
    const lowerStrike = strat.strike - strat.width;
    const middleStrike = strat.strike;
    const upperStrike = strat.strike + strat.width;

    if (strat.side === 'call') {
      // Long call butterfly: long 1 lower, short 2 middle, long 1 upper
      const lowerValue = Math.max(0, underlyingPrice - lowerStrike);
      const middleValue = Math.max(0, underlyingPrice - middleStrike);
      const upperValue = Math.max(0, underlyingPrice - upperStrike);
      return (lowerValue - 2 * middleValue + upperValue - debit) * multiplier;
    } else {
      // Long put butterfly: long 1 upper, short 2 middle, long 1 lower
      const lowerValue = Math.max(0, lowerStrike - underlyingPrice);
      const middleValue = Math.max(0, middleStrike - underlyingPrice);
      const upperValue = Math.max(0, upperStrike - underlyingPrice);
      return (upperValue - 2 * middleValue + lowerValue - debit) * multiplier;
    }
  }

  return 0;
}

function App() {
  const [spot, setSpot] = useState<SpotData | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [gexCalls, setGexCalls] = useState<GexData | null>(null);
  const [gexPuts, setGexPuts] = useState<GexData | null>(null);
  const [vexy, setVexy] = useState<VexyData | null>(null);
  const [biasLfi, setBiasLfi] = useState<BiasLfiData | null>(null);
  const [marketMode, setMarketMode] = useState<MarketModeData | null>(null);
  const [connected, setConnected] = useState(false);
  const [updateCount, setUpdateCount] = useState(0);
  const [lastUpdateTime, setLastUpdateTime] = useState<number | null>(null);

  // Controls
  const [underlying, setUnderlying] = useState<'I:SPX' | 'I:NDX'>('I:SPX');

  // Sync underlying to window for SSE handlers and fetch initial candles
  useEffect(() => {
    (window as any).__currentUnderlying = underlying;

    // Fetch initial candle data for Dealer Gravity chart
    const fetchCandles = async () => {
      try {
        console.log('[App] Fetching candles for', underlying);
        const response = await fetch(`${SSE_BASE}/api/models/candles/${underlying}`);
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
  const [gexMode, setGexMode] = useState<GexMode>('net');
  const [threshold, setThreshold] = useState(50); // % change threshold for blue/red transition
  const [volumeProfile, setVolumeProfile] = useState<VolumeProfileData | null>(null);
  const [vpSmoothing, setVpSmoothing] = useState(5); // Gaussian kernel size (3, 5, 7, 9)
  const [vpOpacity, setVpOpacity] = useState(0.4); // Volume profile opacity

  // Popup and Risk Graph state
  const [selectedTile, setSelectedTile] = useState<SelectedStrategy | null>(null);
  const [riskGraphStrategies, setRiskGraphStrategies] = useState<RiskGraphStrategy[]>([]);
  const [tosCopied, setTosCopied] = useState(false);
  const [crosshairPos, setCrosshairPos] = useState<{ x: number; price: number; pnl: number } | null>(null);

  // Risk graph panning state
  const [panOffset, setPanOffset] = useState(0); // Offset in price units
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartOffset, setDragStartOffset] = useState(0);

  // Panel collapse and layout state
  const [gexCollapsed, setGexCollapsed] = useState(false);
  const [heatmapCollapsed, setHeatmapCollapsed] = useState(false);
  const [riskGraphCollapsed, setRiskGraphCollapsed] = useState(false);
  const [scrollLocked, setScrollLocked] = useState(true);
  const [hasScrolledToAtm, setHasScrolledToAtm] = useState(false);
  const [vpControlsExpanded, setVpControlsExpanded] = useState(false);
  const [strategyExpanded, setStrategyExpanded] = useState(false);
  const [sideExpanded, setSideExpanded] = useState(false);
  const [dteExpanded, setDteExpanded] = useState(false);
  const [gexExpanded, setGexExpanded] = useState(false);
  const [scrollExpanded, setScrollExpanded] = useState(false);

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

  // Refs for scroll sync
  const gexScrollRef = useRef<HTMLDivElement>(null);
  const heatmapScrollRef = useRef<HTMLDivElement>(null);
  const isScrolling = useRef<boolean>(false); // Prevent scroll event loops

  // Available DTEs from data
  const availableDtes = useMemo(() => {
    return heatmap?.dtes_available || [0];
  }, [heatmap]);

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

    const price = strat.debit !== null ? `@${strat.debit.toFixed(2)}` : '';

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

  // Close popup
  const closePopup = () => setSelectedTile(null);

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

  // Clear all strategies from risk graph
  const clearRiskGraph = () => {
    setRiskGraphStrategies([]);
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

  // Handle mouse down on risk graph chart (start drag)
  const handleChartMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    setIsDragging(true);
    setDragStartX(e.clientX);
    setDragStartOffset(panOffset);
    setCrosshairPos(null);
  };

  // Handle mouse move on risk graph chart
  const handleChartMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();

    // Handle dragging
    if (isDragging) {
      const deltaX = e.clientX - dragStartX;
      // Convert pixel delta to price delta (negative because drag right = pan left)
      const priceRange = riskGraphData.maxPrice - riskGraphData.minPrice;
      const priceDelta = -(deltaX / rect.width) * priceRange;
      setPanOffset(dragStartOffset + priceDelta);
      return;
    }

    if (riskGraphData.theoreticalPoints.length === 0) return;

    const svgX = ((e.clientX - rect.left) / rect.width) * 600;

    // Chart area is x: 50-580 (530px width)
    if (svgX < 50 || svgX > 580) {
      setCrosshairPos(null);
      return;
    }

    const chartX = svgX - 50;
    const priceRange = riskGraphData.maxPrice - riskGraphData.minPrice;
    const price = riskGraphData.minPrice + (chartX / 530) * priceRange;

    // Find the closest theoretical point to interpolate P&L
    const points = riskGraphData.theoreticalPoints;
    let pnl = 0;
    for (let i = 1; i < points.length; i++) {
      if (points[i].price >= price) {
        const prev = points[i - 1];
        const curr = points[i];
        const t = (price - prev.price) / (curr.price - prev.price);
        pnl = prev.pnl + t * (curr.pnl - prev.pnl);
        break;
      }
    }

    setCrosshairPos({ x: svgX, price, pnl });
  };

  // Handle mouse up on risk graph chart (end drag)
  const handleChartMouseUp = () => {
    setIsDragging(false);
  };

  const handleChartMouseLeave = () => {
    setCrosshairPos(null);
    setIsDragging(false);
  };

  // Reset pan when strategies change
  const resetPan = () => {
    setPanOffset(0);
  };

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

  // Calculate risk graph data points (only visible strategies)
  // Includes both expiration P&L and real-time theoretical P&L
  // Supports panning via panOffset
  const riskGraphData = useMemo(() => {
    const visibleStrategies = riskGraphStrategies.filter(s => s.visible);
    if (visibleStrategies.length === 0) return {
      points: [],
      theoreticalPoints: [],
      minPnL: 0,
      maxPnL: 0,
      minPrice: 0,
      maxPrice: 0,
      breakevens: [],
      theoreticalBreakevens: [],
      fullMinPrice: 0,
      fullMaxPrice: 0,
      theoreticalPnLAtSpot: 0,
      marketPnL: null
    };

    // Use VIX as volatility (convert from percentage to decimal)
    const vix = spot?.['I:VIX']?.value || 20;
    const volatility = vix / 100;

    // Determine base price range based on visible strategies
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

    // Visible viewport padding (what the user sees at once)
    const viewportPadding = Math.max(range * 0.5, 50);
    const viewportSize = (maxStrike - minStrike) + viewportPadding * 2;

    // Full data range (3x wider for panning)
    const fullPadding = Math.max(range * 1.5, 150);
    const fullMinPrice = minStrike - fullPadding;
    const fullMaxPrice = maxStrike + fullPadding;

    // Visible window with pan offset applied
    const centerPrice = (minStrike + maxStrike) / 2 + panOffset;
    const minPrice = centerPrice - viewportSize / 2;
    const maxPrice = centerPrice + viewportSize / 2;

    // Generate P&L points for the FULL range (expiration and theoretical)
    const numPoints = 400; // More points for wider range
    const step = (fullMaxPrice - fullMinPrice) / numPoints;
    const points: { price: number; pnl: number }[] = [];
    const theoreticalPoints: { price: number; pnl: number }[] = [];
    let minPnL = Infinity;
    let maxPnL = -Infinity;

    for (let i = 0; i <= numPoints; i++) {
      const price = fullMinPrice + i * step;

      // Expiration P&L
      let totalPnL = 0;
      for (const strat of visibleStrategies) {
        totalPnL += calculateStrategyPnL(strat, price);
      }
      points.push({ price, pnl: totalPnL });

      // Theoretical (real-time) P&L using Black-Scholes
      let theoreticalPnL = 0;
      for (const strat of visibleStrategies) {
        theoreticalPnL += calculateStrategyTheoreticalPnL(strat, price, volatility);
      }
      theoreticalPoints.push({ price, pnl: theoreticalPnL });

      // Track min/max P&L only within visible viewport for better scaling
      if (price >= minPrice && price <= maxPrice) {
        minPnL = Math.min(minPnL, totalPnL, theoreticalPnL);
        maxPnL = Math.max(maxPnL, totalPnL, theoreticalPnL);
      }
    }

    // Fallback if no points in viewport
    if (minPnL === Infinity) minPnL = -100;
    if (maxPnL === -Infinity) maxPnL = 100;

    // Find breakeven points for expiration curve
    const breakevens: number[] = [];
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      if ((prev.pnl < 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl < 0)) {
        const t = -prev.pnl / (curr.pnl - prev.pnl);
        const bePrice = prev.price + t * (curr.price - prev.price);
        breakevens.push(bePrice);
      }
    }

    // Find breakeven points for theoretical curve
    const theoreticalBreakevens: number[] = [];
    for (let i = 1; i < theoreticalPoints.length; i++) {
      const prev = theoreticalPoints[i - 1];
      const curr = theoreticalPoints[i];
      if ((prev.pnl < 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl < 0)) {
        const t = -prev.pnl / (curr.pnl - prev.pnl);
        const bePrice = prev.price + t * (curr.price - prev.price);
        theoreticalBreakevens.push(bePrice);
      }
    }

    // Calculate theoretical P&L at current spot price (interpolate from theoreticalPoints)
    let theoreticalPnLAtSpot = 0;
    const spotPrice = spot?.[underlying]?.value || 0;
    if (spotPrice > 0 && theoreticalPoints.length > 1) {
      // Find the two points surrounding the spot price
      for (let i = 1; i < theoreticalPoints.length; i++) {
        const prev = theoreticalPoints[i - 1];
        const curr = theoreticalPoints[i];
        if (prev.price <= spotPrice && curr.price >= spotPrice) {
          // Linear interpolation
          const t = (spotPrice - prev.price) / (curr.price - prev.price);
          theoreticalPnLAtSpot = prev.pnl + t * (curr.pnl - prev.pnl);
          break;
        }
      }
    }

    // Calculate market-based P&L using live heatmap tile prices
    // This is more accurate for 0-DTE where theoretical = intrinsic
    let marketPnL: number | null = null;
    if (heatmap?.tiles && visibleStrategies.length > 0) {
      let totalMarketPnL = 0;
      let allFound = true;

      for (const strat of visibleStrategies) {
        // Build tile key: strategy:dte:width:strike
        const tileKey = `${strat.strategy}:${strat.dte}:${strat.width}:${Math.round(strat.strike)}`;
        const tile = heatmap.tiles[tileKey];

        if (tile) {
          // Get current debit from tile
          const sideData = strat.side === 'call' ? tile.call : tile.put;
          const currentDebit = sideData?.debit;
          const entryDebit = strat.debit;

          if (currentDebit != null && entryDebit != null) {
            // P&L = (current value - entry cost) * multiplier
            // For long positions: current > entry = profit
            totalMarketPnL += (currentDebit - entryDebit) * 100;
          } else {
            allFound = false;
          }
        } else {
          allFound = false;
        }
      }

      if (allFound) {
        marketPnL = totalMarketPnL;
      }
    }

    return { points, theoreticalPoints, minPnL, maxPnL, minPrice, maxPrice, breakevens, theoreticalBreakevens, fullMinPrice, fullMaxPrice, theoreticalPnLAtSpot, marketPnL };
  }, [riskGraphStrategies, spot, panOffset, heatmap, underlying]);

  // SSE connection
  useEffect(() => {
    const es = new EventSource(`${SSE_BASE}/sse/all`);

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.addEventListener('spot', (e: MessageEvent) => {
      try {
        const spotData = JSON.parse(e.data);
        setSpot(spotData);
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());

        // Update Dealer Gravity snapshot with current spot (for selected underlying)
        // The component will build candles from live updates
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
      } catch {}
    });

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
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
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
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('heatmap_diff', (e: MessageEvent) => {
      try {
        const diff = JSON.parse(e.data);
        // Dispatch for underlying-aware handling
        window.dispatchEvent(new CustomEvent('heatmap-diff-update', { detail: diff }));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('vexy', (e: MessageEvent) => {
      try {
        setVexy(JSON.parse(e.data));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('bias_lfi', (e: MessageEvent) => {
      try {
        setBiasLfi(JSON.parse(e.data));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('market_mode', (e: MessageEvent) => {
      try {
        setMarketMode(JSON.parse(e.data));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    return () => es.close();
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

      console.log(`[UI] heatmap_diff received: changed=${Object.keys(diff.changed || {}).length} v=${diff.version}`);
      setHeatmap(prev => {
        if (prev?.version && diff.version && diff.version <= prev.version) {
          console.log(`[UI] Skipping stale diff: ${diff.version} <= ${prev.version}`);
          return prev;
        }

        const updatedTiles = { ...(prev?.tiles || {}) };

        if (diff.changed) {
          Object.entries(diff.changed).forEach(([key, tile]) => {
            updatedTiles[key] = tile as HeatmapTile;
          });
        }

        if (diff.removed) {
          diff.removed.forEach((key: string) => {
            delete updatedTiles[key];
          });
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

    window.addEventListener('gex-update', handleGexUpdate as EventListener);
    window.addEventListener('heatmap-update', handleHeatmapUpdate as EventListener);
    window.addEventListener('heatmap-diff-update', handleHeatmapDiffUpdate as EventListener);

    return () => {
      window.removeEventListener('gex-update', handleGexUpdate as EventListener);
      window.removeEventListener('heatmap-update', handleHeatmapUpdate as EventListener);
      window.removeEventListener('heatmap-diff-update', handleHeatmapDiffUpdate as EventListener);
    };
  }, [underlying]);

  // Fetch initial data via REST (refetch when underlying changes)
  useEffect(() => {
    fetch(`${SSE_BASE}/api/models/spot`)
      .then(r => r.json())
      .then(d => d.success && setSpot(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/heatmap/${underlying}`)
      .then(r => r.json())
      .then(d => d.success && setHeatmap(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/gex/${underlying}`)
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

    fetch(`${SSE_BASE}/api/models/vexy/latest`)
      .then(r => r.json())
      .then(d => d.success && setVexy(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/bias_lfi`)
      .then(r => r.json())
      .then(d => d.success && setBiasLfi(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/market_mode`)
      .then(r => r.json())
      .then(d => d.success && setMarketMode(d.data))
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

    fetch(`${SSE_BASE}/api/models/volume_profile?min=${minPrice}&max=${maxPrice}`)
      .then(r => r.json())
      .then(d => {
        if (d.success && d.data) {
          setVolumeProfile(d.data);
        }
      })
      .catch(() => {});

    // Refresh every 5 seconds
    const interval = setInterval(() => {
      fetch(`${SSE_BASE}/api/models/volume_profile?min=${minPrice}&max=${maxPrice}`)
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

  // Process volume profile with smoothing - keep full $0.10 resolution
  // vpByPrice: key is price * 10 (e.g., 60001 = $6000.10)
  const vpByPrice = useMemo(() => {
    const vpByPrice: Record<number, number> = {};

    if (!volumeProfile?.levels) {
      return vpByPrice;
    }

    // Build array at full $0.10 resolution
    const priceToVolume: Record<number, number> = {};
    for (const level of volumeProfile.levels) {
      // Keep full resolution: price in tenths (e.g., 6000.10 -> 60001)
      const priceTenths = Math.round(level.price * 10);
      priceToVolume[priceTenths] = (priceToVolume[priceTenths] || 0) + level.volume;
    }

    // Get sorted prices and volumes for smoothing
    const sortedPrices = Object.keys(priceToVolume).map(Number).sort((a, b) => a - b);
    const volumes = sortedPrices.map(p => priceToVolume[p]);

    // Apply Gaussian smoothing at full resolution
    const smoothedVolumes = gaussianSmooth(volumes, vpSmoothing);

    // Map back to prices
    for (let i = 0; i < sortedPrices.length; i++) {
      const priceTenths = sortedPrices[i];
      vpByPrice[priceTenths] = smoothedVolumes[i];
    }

    return vpByPrice;
  }, [volumeProfile, vpSmoothing]);

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
    if (strikes.length > 0) {
      if (!currentSpot) return strikes.slice(0, 50);

      const atmIndex = strikes.findIndex(s => s <= currentSpot);
      const rangeStart = Math.max(0, atmIndex - 25);
      const rangeEnd = Math.min(strikes.length, atmIndex + 25);
      return strikes.slice(rangeStart, rangeEnd);
    }

    // Fallback placeholder strikes when no data
    const defaultSpot = underlying === 'I:NDX' ? 21000 : 6000;
    const basePrice = currentSpot || defaultSpot;
    const roundedBase = Math.round(basePrice / strikeIncrement) * strikeIncrement;
    const placeholderStrikes: number[] = [];
    for (let i = 25; i >= -25; i--) {
      placeholderStrikes.push(roundedBase + i * strikeIncrement);
    }
    return placeholderStrikes;
  }, [strikes, currentSpot, underlying, strikeIncrement]);

  // Scroll to ATM function
  const scrollToAtm = useCallback(() => {
    if (!currentSpot || visibleStrikes.length === 0) return;

    const atmIndex = visibleStrikes.findIndex(s => s <= currentSpot);
    if (atmIndex === -1) return;

    const rowHeight = 24; // Height of each row in pixels
    const scrollPosition = atmIndex * rowHeight;

    // Center the ATM in the viewport
    const viewportHeight = gexScrollRef.current?.clientHeight || 600;
    const centeredPosition = Math.max(0, scrollPosition - viewportHeight / 2);

    if (gexScrollRef.current) {
      gexScrollRef.current.scrollTop = centeredPosition;
    }
    if (heatmapScrollRef.current) {
      heatmapScrollRef.current.scrollTop = centeredPosition;
    }
  }, [currentSpot, visibleStrikes]);

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

  // Linear scale volume to width percentage (0-90%)
  const vpVolumeToWidth = (volume: number): number => {
    if (volume <= 0 || maxVpVolume <= 0) return 0;
    return (volume / maxVpVolume) * 90;
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
          <h1>MarketSwarm</h1>
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
        <div className="connection-status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'Live' : 'Disconnected'}</span>
          <span className="update-count">#{updateCount}</span>
          {lastUpdateTime && (
            <span className="last-update">
              {new Date(lastUpdateTime).toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      {/* Widget Row - Indicator Widgets */}
      <div className="widget-row">
        <div className="widget vexy-widget">
          <div className="widget-header">
            <h4>Vexy</h4>
            {vexy?.epoch?.ts && (
              <span className="widget-timestamp">
                {new Date(vexy.epoch.ts).toLocaleTimeString()}
              </span>
            )}
          </div>
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
                <div className="vexy-text epoch-text">{vexy.epoch.text}</div>
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
                <div className="vexy-text event-text">{vexy.event.text}</div>
              </div>
            )}
          </div>
        </div>
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

        {/* VIX Regime Widget */}
        <div className="widget vix-regime-widget">
          <VixRegimeCard
            vix={spot?.['I:VIX']?.value ?? null}
            ts={spot?.['I:VIX']?.ts}
          />
        </div>

        {/* Dealer Gravity Widget - Candle Chart with Bands */}
        <div className="widget dealer-gravity-widget">
          <LightweightPriceChart snap={dgSnapshot} height={280} title="Dealer Gravity" />
        </div>
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

        <div className={`control-group vp-controls ${vpControlsExpanded ? 'expanded' : ''}`}>
          <button
            className={`vp-toggle ${vpControlsExpanded ? 'active' : ''}`}
            onClick={() => setVpControlsExpanded(!vpControlsExpanded)}
          >
            VP
          </button>
          {vpControlsExpanded && (
            <>
              <div className="vp-slider">
                <label>Opacity {Math.round(vpOpacity * 100)}%</label>
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.1"
                  value={vpOpacity}
                  onChange={(e) => setVpOpacity(parseFloat(e.target.value))}
                  className="threshold-slider"
                />
              </div>
              <div className="vp-slider">
                <label>Smooth {vpSmoothing}</label>
                <input
                  type="range"
                  min="1"
                  max="51"
                  step="2"
                  value={vpSmoothing}
                  onChange={(e) => setVpSmoothing(parseInt(e.target.value))}
                  className="threshold-slider"
                />
              </div>
            </>
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

        {/* Scroll - collapsible */}
        <div className={`control-group collapsible-control ${scrollExpanded ? 'expanded' : ''}`}>
          <button
            className={`control-toggle ${scrollExpanded ? 'active' : ''}`}
            onClick={() => setScrollExpanded(!scrollExpanded)}
          >
            Scroll
          </button>
          {scrollExpanded && (
            <div className="button-group">
              <button
                className={scrollLocked ? 'active' : ''}
                onClick={() => setScrollLocked(!scrollLocked)}
              >
                {scrollLocked ? 'Locked' : 'Unlocked'}
              </button>
              <button onClick={scrollToAtm}>
                Center ATM
              </button>
            </div>
          )}
        </div>

        {/* Gradient - at the end */}
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
      </div>

      {/* Main Content Row - Horizontal Scrollable */}
      <div className="main-content-row">
        {/* GEX Panel */}
        <div className={`panel gex-panel ${gexCollapsed ? 'collapsed' : ''}`}>
          <div className="panel-header" onClick={() => setGexCollapsed(!gexCollapsed)}>
            <span className="panel-toggle">{gexCollapsed ? '▶' : '▼'}</span>
            <h3>GEX + Volume Profile</h3>
          </div>
          {!gexCollapsed && (
            <div className="panel-content">
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
                {visibleStrikes.map(strike => {
                  const gex = gexByStrike[strike] || { calls: 0, puts: 0 };
                  const netGex = gex.calls - gex.puts;
                  const isAtm = currentSpot && Math.abs(strike - currentSpot) < 5;

                  return (
                    <div key={strike} className={`gex-row ${isAtm ? 'atm' : ''}`}>
                      <div className="gex-cell-standalone">
                        {/* Volume profile */}
                        {getVpLevelsForStrike(strike).map((level, idx) => (
                          <div
                            key={idx}
                            className="volume-profile-bar"
                            style={{
                              width: `${vpVolumeToWidth(level.volume)}%`,
                              top: `${(level.pos / 50) * 100}%`,
                              height: `${100 / 50}%`,
                              opacity: vpOpacity,
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
                      <div className={`strike-label ${isAtm ? 'atm' : ''}`}>{strike}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Heatmap Panel */}
        <div className={`panel heatmap-panel ${heatmapCollapsed ? 'collapsed' : ''}`}>
          <div className="panel-header" onClick={() => setHeatmapCollapsed(!heatmapCollapsed)}>
            <span className="panel-toggle">{heatmapCollapsed ? '▶' : '▼'}</span>
            <h3>Heatmap</h3>
          </div>
          {!heatmapCollapsed && (
            <div className="panel-content">
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
                {visibleStrikes.map(strike => {
                    const isAtm = currentSpot && Math.abs(strike - currentSpot) < 5;
                    const strikeData = heatmapGrid[strike] || {};

                    return (
                      <div key={strike} className={`heatmap-row ${isAtm ? 'atm' : ''}`}>
                        <div className={`strike-cell ${isAtm ? 'atm' : ''}`}>{strike}</div>
                        {strategy === 'single' ? (
                          (() => {
                            const val = strikeData[0] ?? null;
                            const isValid = val !== null && val > 0;
                            return (
                              <div
                                className={`width-cell ${isValid ? 'clickable' : ''}`}
                                style={{ backgroundColor: debitColor(val, changeGrid[strike]?.[0] ?? 0) }}
                                onClick={isValid ? () => handleTileClick(strike, 0, val) : undefined}
                              >
                                {isValid ? val.toFixed(2) : 'NA'}
                              </div>
                            );
                          })()
                        ) : (
                          widths.map(w => {
                            const val = strikeData[w] ?? null;
                            const pctChange = changeGrid[strike]?.[w] ?? 0;
                            const isValid = val !== null && val > 0;
                            return (
                              <div
                                key={w}
                                className={`width-cell ${isValid ? 'clickable' : ''}`}
                                style={{ backgroundColor: debitColor(val, pctChange) }}
                                onClick={isValid ? () => handleTileClick(strike, w, val) : undefined}
                              >
                                {isValid ? val.toFixed(2) : 'NA'}
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
        <div className={`panel risk-graph-panel ${riskGraphCollapsed ? 'collapsed' : ''}`}>
          <div className="panel-header" onClick={() => setRiskGraphCollapsed(!riskGraphCollapsed)}>
            <span className="panel-toggle">{riskGraphCollapsed ? '▶' : '▼'}</span>
            <h3>Risk Graph {riskGraphStrategies.length > 0 && `(${riskGraphStrategies.length})`}</h3>
            <div className="panel-header-actions" onClick={e => e.stopPropagation()}>
              {panOffset !== 0 && (
                <button className="btn-small" onClick={resetPan}>Reset View</button>
              )}
              {riskGraphStrategies.length > 0 && (
                <button className="btn-small btn-danger" onClick={clearRiskGraph}>Clear</button>
              )}
            </div>
          </div>
          {!riskGraphCollapsed && (
            <div className="panel-content risk-graph-content-panel">
              {riskGraphStrategies.length === 0 ? (
                <div className="risk-graph-empty">
                  <p>No strategies added yet.</p>
                  <p className="hint">Click on a heatmap tile and select "Add to Risk Graph"</p>
                </div>
              ) : (
                <div className="risk-graph-content">
                  {/* Strategy List - Left Side */}
                  <div className="risk-graph-strategies">
                    {riskGraphStrategies.map(strat => (
                      <div key={strat.id} className={`risk-graph-strategy-item ${!strat.visible ? 'hidden-strategy' : ''}`}>
                        <input
                          type="checkbox"
                          className="strategy-checkbox"
                          checked={strat.visible}
                          onChange={() => toggleStrategyVisibility(strat.id)}
                        />
                        <div className="strategy-info">
                          <div className="strategy-row">
                            <span className="strategy-type">
                              {strat.strategy === 'butterfly' ? 'BF' : strat.strategy === 'vertical' ? 'VS' : 'SGL'}
                            </span>
                            <span className="strategy-details">
                              {strat.strike} {strat.width > 0 && `w${strat.width}`} {strat.side.toUpperCase()}
                            </span>
                          </div>
                          <div className="strategy-row">
                            <span className="strategy-dte">DTE {strat.dte}</span>
                            <span className="strategy-debit">
                              $<input
                                type="number"
                                className="debit-input"
                                value={strat.debit !== null ? strat.debit.toFixed(2) : ''}
                                step="0.01"
                                min="0"
                                onChange={(e) => {
                                  const val = parseFloat(e.target.value);
                                  updateStrategyDebit(strat.id, isNaN(val) ? null : val);
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                            </span>
                          </div>
                        </div>
                        <button
                          className="btn-log-trade"
                          onClick={() => {
                            openTradeEntry({
                              symbol: underlying === 'I:SPX' ? 'SPX' : 'NDX',
                              underlying,
                              strategy: strat.strategy as 'single' | 'vertical' | 'butterfly',
                              side: strat.side as 'call' | 'put',
                              strike: strat.strike,
                              width: strat.width,
                              dte: strat.dte,
                              entry_price: strat.debit || undefined,
                              entry_spot: currentSpot || undefined,
                              source: 'risk_graph'
                            });
                          }}
                          title="Log this trade"
                        >
                          Log
                        </button>
                        <button className="btn-remove" onClick={() => removeFromRiskGraph(strat.id)}>&times;</button>
                      </div>
                    ))}
                  </div>

                  {/* P&L Chart - Right Side */}
                  <div className="risk-graph-chart-container">
                    <div className="risk-graph-chart">
                    <svg
                  viewBox="0 0 600 300"
                  preserveAspectRatio="xMidYMid meet"
                  onMouseDown={handleChartMouseDown}
                  onMouseMove={handleChartMouseMove}
                  onMouseUp={handleChartMouseUp}
                  onMouseLeave={handleChartMouseLeave}
                  style={{ cursor: isDragging ? 'grabbing' : 'crosshair' }}
                >
                  {/* Background */}
                  <rect x="0" y="0" width="600" height="300" fill="#0a0a0a" />

                  {/* Grid lines */}
                  <g className="grid-lines">
                    {[0, 60, 120, 180, 240, 300].map(y => (
                      <line key={y} x1="50" y1={y} x2="580" y2={y} stroke="#222" strokeWidth="1" />
                    ))}
                    {[50, 150, 250, 350, 450, 550].map(x => (
                      <line key={x} x1={x} y1="20" x2={x} y2="280" stroke="#222" strokeWidth="1" />
                    ))}
                  </g>

                  {/* Zero line */}
                  {riskGraphData.minPnL < 0 && riskGraphData.maxPnL > 0 && (
                    <line
                      x1="50"
                      y1={20 + (riskGraphData.maxPnL / (riskGraphData.maxPnL - riskGraphData.minPnL)) * 260}
                      x2="580"
                      y2={20 + (riskGraphData.maxPnL / (riskGraphData.maxPnL - riskGraphData.minPnL)) * 260}
                      stroke="#666"
                      strokeWidth="1"
                      strokeDasharray="4,4"
                    />
                  )}

                  {/* Current spot price - thin dashed line */}
                  {currentSpot && currentSpot >= riskGraphData.minPrice && currentSpot <= riskGraphData.maxPrice && (
                    <line
                      x1={50 + ((currentSpot - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530}
                      y1="20"
                      x2={50 + ((currentSpot - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530}
                      y2="280"
                      stroke="#fbbf24"
                      strokeWidth="1"
                      strokeDasharray="4,4"
                    />
                  )}

                  {/* Expiration P&L Line (blue) */}
                  <path
                    d={riskGraphData.points.map((p, i) => {
                      const x = 50 + ((p.price - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530;
                      const pnlRange = riskGraphData.maxPnL - riskGraphData.minPnL || 1;
                      const y = 20 + ((riskGraphData.maxPnL - p.pnl) / pnlRange) * 260;
                      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                    }).join(' ')}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                  />

                  {/* Real-Time P&L Line (magenta) */}
                  {riskGraphData.theoreticalPoints.length > 0 && (
                    <path
                      d={riskGraphData.theoreticalPoints.map((p, i) => {
                        const x = 50 + ((p.price - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530;
                        const pnlRange = riskGraphData.maxPnL - riskGraphData.minPnL || 1;
                        const y = 20 + ((riskGraphData.maxPnL - p.pnl) / pnlRange) * 260;
                        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
                      }).join(' ')}
                      fill="none"
                      stroke="#e879f9"
                      strokeWidth="2"
                    />
                  )}

                  {/* Profit area fill */}
                  <path
                    d={(() => {
                      const zeroY = riskGraphData.minPnL >= 0 ? 280 :
                                   riskGraphData.maxPnL <= 0 ? 20 :
                                   20 + (riskGraphData.maxPnL / (riskGraphData.maxPnL - riskGraphData.minPnL)) * 260;
                      let path = '';
                      riskGraphData.points.forEach((p) => {
                        const x = 50 + ((p.price - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530;
                        const pnlRange = riskGraphData.maxPnL - riskGraphData.minPnL || 1;
                        const y = 20 + ((riskGraphData.maxPnL - p.pnl) / pnlRange) * 260;
                        if (p.pnl > 0) {
                          path += `${path ? 'L' : 'M'} ${x} ${y}`;
                        } else if (path) {
                          path += ` L ${x} ${zeroY} Z`;
                          path = '';
                        }
                      });
                      return path;
                    })()}
                    fill="rgba(74, 222, 128, 0.2)"
                  />

                  {/* Real-time breakeven lines (where magenta line crosses zero) */}
                  {riskGraphData.theoreticalBreakevens.map((be, i) => {
                    const x = 50 + ((be - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530;
                    return (
                      <line
                        key={i}
                        x1={x}
                        y1="20"
                        x2={x}
                        y2="280"
                        stroke="#3b82f6"
                        strokeWidth="1"
                        strokeDasharray="4,4"
                      />
                    );
                  })}

                  {/* Interactive crosshair */}
                  {crosshairPos && (
                    <g className="crosshair">
                      {/* Vertical line */}
                      <line
                        x1={crosshairPos.x}
                        y1="20"
                        x2={crosshairPos.x}
                        y2="280"
                        stroke="#fff"
                        strokeWidth="1"
                        strokeOpacity="0.5"
                      />
                      {/* Horizontal line at P&L level */}
                      {(() => {
                        const pnlRange = riskGraphData.maxPnL - riskGraphData.minPnL || 1;
                        const y = 20 + ((riskGraphData.maxPnL - crosshairPos.pnl) / pnlRange) * 260;
                        return (
                          <line
                            x1="50"
                            y1={y}
                            x2="580"
                            y2={y}
                            stroke="#fff"
                            strokeWidth="1"
                            strokeOpacity="0.5"
                          />
                        );
                      })()}
                      {/* Info label */}
                      {(() => {
                        const pnlRange = riskGraphData.maxPnL - riskGraphData.minPnL || 1;
                        const y = 20 + ((riskGraphData.maxPnL - crosshairPos.pnl) / pnlRange) * 260;
                        const labelX = crosshairPos.x > 450 ? crosshairPos.x - 10 : crosshairPos.x + 10;
                        const anchor = crosshairPos.x > 450 ? 'end' : 'start';
                        const pnlColor = crosshairPos.pnl >= 0 ? '#4ade80' : '#f87171';
                        return (
                          <g>
                            {/* Background for readability */}
                            <rect
                              x={anchor === 'end' ? labelX - 85 : labelX - 5}
                              y={y < 60 ? y + 5 : y - 40}
                              width="90"
                              height="38"
                              fill="#1a1a1a"
                              fillOpacity="0.9"
                              rx="4"
                            />
                            <text
                              x={labelX}
                              y={y < 60 ? y + 20 : y - 25}
                              textAnchor={anchor}
                              fill="#888"
                              fontSize="11"
                            >
                              {crosshairPos.price.toFixed(2)}
                            </text>
                            <text
                              x={labelX}
                              y={y < 60 ? y + 36 : y - 9}
                              textAnchor={anchor}
                              fill={pnlColor}
                              fontSize="12"
                              fontWeight="bold"
                            >
                              ${(crosshairPos.pnl / 100).toFixed(2)}
                            </text>
                          </g>
                        );
                      })()}
                    </g>
                  )}

                  {/* Axis labels */}
                  <text x="50" y="295" fill="#666" fontSize="10">{riskGraphData.minPrice.toFixed(0)}</text>
                  <text x="580" y="295" fill="#666" fontSize="10" textAnchor="end">{riskGraphData.maxPrice.toFixed(0)}</text>
                  <text x="40" y="25" fill="#666" fontSize="10" textAnchor="end">${(riskGraphData.maxPnL / 100).toFixed(2)}</text>
                  <text x="40" y="280" fill="#666" fontSize="10" textAnchor="end">${(riskGraphData.minPnL / 100).toFixed(2)}</text>
                </svg>
                </div>

                    {/* Summary Stats */}
                    <div className="risk-graph-stats">
                      <div className="stat highlight">
                        <span className="stat-label">Real-Time P&L</span>
                        {(() => {
                          // Prefer market P&L (from live heatmap) over theoretical (Black-Scholes)
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
                      <div className="stat">
                        <span className="stat-label">Breakevens (RT)</span>
                        <span className="stat-value">{riskGraphData.theoreticalBreakevens.map(b => b.toFixed(0)).join(', ') || '-'}</span>
                      </div>
                      {currentSpot && (
                        <div className="stat">
                          <span className="stat-label">Spot</span>
                          <span className="stat-value">{currentSpot.toFixed(2)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

      </div>

      <div className="footer">
        <span>Heatmap: {heatmap?.ts ? new Date(heatmap.ts * 1000).toLocaleTimeString() : '-'}</span>
        <span>GEX: {gexCalls?.ts ? new Date(gexCalls.ts * 1000).toLocaleTimeString() : '-'}</span>
        <span>Tiles: {Object.keys(heatmap?.tiles || {}).length}</span>
        <span>v{heatmap?.version || '-'}</span>
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
          {reportingLogId ? (
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
                  <EquityChartWidget refreshTrigger={tradeRefreshTrigger} />
                  <TradeLogPanel
                    onOpenTradeEntry={openTradeEntry}
                    onEditTrade={openTradeEdit}
                    onViewReporting={handleViewReporting}
                    onManageLogs={handleManageLogs}
                    onOpenSettings={() => setSettingsOpen(true)}
                    selectedLogId={selectedLog?.id || null}
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
      />
    </div>
  );
}

export default App;
