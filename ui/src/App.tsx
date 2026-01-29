import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import './App.css';
import { Tooltip } from './Tooltip';

const SSE_BASE = 'http://localhost:3001';

type Strategy = 'single' | 'vertical' | 'butterfly';
type GexMode = 'combined' | 'net';
type Side = 'call' | 'put';

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

// Strategy details for popup/risk graph
interface SelectedStrategy {
  strategy: Strategy;
  side: Side;
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

// Width options per strategy
const WIDTHS: Record<Strategy, number[]> = {
  single: [0],
  vertical: [20, 25, 30, 35, 40, 45, 50],
  butterfly: [20, 25, 30, 35, 40, 45, 50],
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
  const [connected, setConnected] = useState(false);
  const [updateCount, setUpdateCount] = useState(0);
  const [lastUpdateTime, setLastUpdateTime] = useState<number | null>(null);

  // Controls
  const [strategy, setStrategy] = useState<Strategy>('butterfly');
  const [side, setSide] = useState<Side>('call');
  const [dte, setDte] = useState(0);
  const [gexMode, setGexMode] = useState<GexMode>('net');
  const [threshold, setThreshold] = useState(50); // % change threshold for blue/red transition
  const [volumeProfile, setVolumeProfile] = useState<VolumeProfileData | null>(null);
  const [vpSmoothing, setVpSmoothing] = useState(5); // Gaussian kernel size (3, 5, 7, 9)
  const [vpOpacity, setVpOpacity] = useState(0.4); // Volume profile opacity

  // Popup and Risk Graph state
  const [selectedTile, setSelectedTile] = useState<SelectedStrategy | null>(null);
  const [riskGraphStrategies, setRiskGraphStrategies] = useState<RiskGraphStrategy[]>([]);
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
  const handleTileClick = (strike: number, width: number, debit: number | null) => {
    setSelectedTile({
      strategy,
      side,
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
    const currentSpot = spot?.['I:SPX']?.value || 0;
    if (currentSpot > 0 && theoreticalPoints.length > 1) {
      // Find the two points surrounding the spot price
      for (let i = 1; i < theoreticalPoints.length; i++) {
        const prev = theoreticalPoints[i - 1];
        const curr = theoreticalPoints[i];
        if (prev.price <= currentSpot && curr.price >= currentSpot) {
          // Linear interpolation
          const t = (currentSpot - prev.price) / (curr.price - prev.price);
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
  }, [riskGraphStrategies, spot, panOffset, heatmap]);

  // SSE connection
  useEffect(() => {
    const es = new EventSource(`${SSE_BASE}/sse/all`);

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    es.addEventListener('spot', (e: MessageEvent) => {
      try {
        setSpot(JSON.parse(e.data));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('gex', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.symbol === 'I:SPX') {
          if (data.calls) {
            setGexCalls(data.calls);
          }
          if (data.puts) {
            setGexPuts(data.puts);
          }
        }
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('heatmap', (e: MessageEvent) => {
      try {
        setHeatmap(JSON.parse(e.data));
        setUpdateCount(c => c + 1);
        setLastUpdateTime(Date.now());
      } catch {}
    });

    es.addEventListener('heatmap_diff', (e: MessageEvent) => {
      try {
        const diff = JSON.parse(e.data);
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
            symbol: diff.symbol || prev?.symbol || 'I:SPX',
            version: diff.version,
            dtes_available: diff.dtes_available || prev?.dtes_available,
            tiles: updatedTiles,
          };
        });
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

    return () => es.close();
  }, []);

  // Fetch initial data via REST
  useEffect(() => {
    fetch(`${SSE_BASE}/api/models/spot`)
      .then(r => r.json())
      .then(d => d.success && setSpot(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/heatmap/I:SPX`)
      .then(r => r.json())
      .then(d => d.success && setHeatmap(d.data))
      .catch(() => {});

    fetch(`${SSE_BASE}/api/models/gex/I:SPX`)
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
  }, []);

  // Fetch volume profile based on spot price (±300 points)
  useEffect(() => {
    const spxPrice = spot?.['I:SPX']?.value;
    if (!spxPrice) return;

    const minPrice = Math.floor(spxPrice - 300);
    const maxPrice = Math.ceil(spxPrice + 300);

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
  }, [spot?.['I:SPX']?.value]);

  const spxSpot = spot?.['I:SPX']?.value || null;
  const widths = WIDTHS[strategy];

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

        // Get value based on strategy and side
        if (strategy === 'single') {
          // For single, use mid price
          heatmapGrid[strike][0] = tile[side]?.mid ?? null;
        } else {
          // For vertical/butterfly, use debit
          heatmapGrid[strike][width] = tile[side]?.debit ?? null;
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

      for (const w of (strategy === 'single' ? [0] : [20, 25, 30, 35, 40, 45, 50])) {
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
  }, [gexCalls, gexPuts, heatmap, strategy, side, dte]);

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
  const visibleStrikes = useMemo(() => {
    if (strikes.length > 0) {
      if (!spxSpot) return strikes.slice(0, 50);

      const atmIndex = strikes.findIndex(s => s <= spxSpot);
      const rangeStart = Math.max(0, atmIndex - 25);
      const rangeEnd = Math.min(strikes.length, atmIndex + 25);
      return strikes.slice(rangeStart, rangeEnd);
    }

    const basePrice = spxSpot || 6000;
    const roundedBase = Math.round(basePrice / 5) * 5;
    const placeholderStrikes: number[] = [];
    for (let i = 25; i >= -25; i--) {
      placeholderStrikes.push(roundedBase + i * 5);
    }
    return placeholderStrikes;
  }, [strikes, spxSpot]);

  // Scroll to ATM function
  const scrollToAtm = useCallback(() => {
    if (!spxSpot || visibleStrikes.length === 0) return;

    const atmIndex = visibleStrikes.findIndex(s => s <= spxSpot);
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
  }, [spxSpot, visibleStrikes]);

  // Scroll to ATM on first load only
  useEffect(() => {
    if (!hasScrolledToAtm && spxSpot && visibleStrikes.length > 0) {
      // Delay to ensure layout is fully rendered
      const timer = setTimeout(() => {
        scrollToAtm();
        setHasScrolledToAtm(true);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [hasScrolledToAtm, spxSpot, visibleStrikes, scrollToAtm]);

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
          <h1>MarketSwarm - SPX</h1>
          <div className="spot-display">
            {spot?.['I:SPX'] && (
              <span className="spot-price">
                SPX {spot['I:SPX'].value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
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
          <div className="widget-header">
            <Tooltip content="marketMode"><h4>Market Mode</h4></Tooltip>
            <Tooltip content="marketModeBadge"><span className="mode-badge transition">Transition</span></Tooltip>
          </div>
          <div className="widget-content mm-content">
            <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" className="mm-svg">
              <defs>
                <linearGradient id="compressionGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#0ea5e9" />
                  <stop offset="100%" stopColor="#06b6d4" />
                </linearGradient>
                <linearGradient id="transitionGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#eab308" />
                  <stop offset="100%" stopColor="#f59e0b" />
                </linearGradient>
                <linearGradient id="expansionGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#f97316" />
                  <stop offset="100%" stopColor="#ef4444" />
                </linearGradient>
              </defs>

              {/* Background arc */}
              <path d="M 10 75 A 40 40 0 0 1 90 75" fill="none" stroke="#1a1a1a" strokeWidth="12" />

              {/* Compression segment (0-35%) */}
              <path d="M 10 75 A 40 40 0 0 1 26.5 41" fill="none" stroke="url(#compressionGrad)" strokeWidth="10" strokeLinecap="round">
                <title>Compression: 0-35 - Tight ranges, mean reversion favored</title>
              </path>

              {/* Transition segment (35-65%) */}
              <path d="M 26.5 41 A 40 40 0 0 1 73.5 41" fill="none" stroke="url(#transitionGrad)" strokeWidth="10">
                <title>Transition: 35-65 - Mixed conditions, be cautious</title>
              </path>

              {/* Expansion segment (65-100%) */}
              <path d="M 73.5 41 A 40 40 0 0 1 90 75" fill="none" stroke="url(#expansionGrad)" strokeWidth="10" strokeLinecap="round">
                <title>Expansion: 65-100 - Trending, breakouts favored</title>
              </path>

              {/* Needle - 59% = 59/100 * 180 = 106.2 degrees from left */}
              <g transform="rotate(106.2, 50, 75)">
                <line x1="50" y1="75" x2="50" y2="42" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="50" cy="75" r="5" fill="#1a1a1a" stroke="#333" strokeWidth="1" />
                <circle cx="50" cy="75" r="2" fill="#f59e0b" />
              </g>

              {/* Score display */}
              <text x="50" y="68" textAnchor="middle" fill="#fff" fontSize="18" fontWeight="700">59</text>
              <text x="50" y="76" textAnchor="middle" fill="#555" fontSize="6">/100</text>

              {/* Zone labels - minimal */}
              <g><text x="8" y="85" fill="#0ea5e9" fontSize="5">C</text><title>Compression: Tight ranges, mean reversion</title></g>
              <g><text x="50" y="32" textAnchor="middle" fill="#f59e0b" fontSize="5">T</text><title>Transition: Mixed conditions</title></g>
              <g><text x="92" y="85" textAnchor="end" fill="#ef4444" fontSize="5">E</text><title>Expansion: Trending, breakouts</title></g>

              {/* Scale markers */}
              <text x="6" y="78" fill="#444" fontSize="4">0</text>
              <text x="94" y="78" textAnchor="end" fill="#444" fontSize="4">100</text>
            </svg>

            {/* Legend bar at bottom */}
            <div className="mm-legend">
              <Tooltip content="marketModeCompression" position="bottom"><span className="mm-zone compression">Compression</span></Tooltip>
              <Tooltip content="marketModeTransition" position="bottom"><span className="mm-zone transition">Transition</span></Tooltip>
              <Tooltip content="marketModeExpansion" position="bottom"><span className="mm-zone expansion">Expansion</span></Tooltip>
            </div>
          </div>
        </div>

        {/* Liquidity Intent Map Widget - Quadrant Chart */}
        <div className="widget lim-widget">
          <div className="widget-header">
            <Tooltip content="liquidityIntent"><h4>Liquidity Intent</h4></Tooltip>
            <div className="lim-header-values">
              <Tooltip content="limBias"><span>Bias: <strong className="bias-value">+61</strong></span></Tooltip>
              <Tooltip content="limLFI"><span>LFI: <strong className="lfi-value">31</strong></span></Tooltip>
            </div>
          </div>
          <div className="widget-content lim-content">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="lim-svg">
              {/* Quadrant backgrounds with hover titles */}
              <g>
                <rect x="0" y="0" width="50" height="50" fill="#0ea5e9" opacity="0.12" />
                <title>Pin / Mean Reversion: Liquidity contains price, expect range-bound action</title>
              </g>
              <g>
                <rect x="50" y="0" width="50" height="50" fill="#a855f7" opacity="0.12" />
                <title>False Breakout Risk: Moves need confirmation, be cautious of traps</title>
              </g>
              <g>
                <rect x="0" y="50" width="50" height="50" fill="#ef4444" opacity="0.12" />
                <title>Downside Acceleration: Liquidity amplifies selling, risk of rapid drops</title>
              </g>
              <g>
                <rect x="50" y="50" width="50" height="50" fill="#22c55e" opacity="0.12" />
                <title>Air-Pocket Expansion: Price can travel quickly with little resistance</title>
              </g>

              {/* Grid lines */}
              <line x1="50" y1="0" x2="50" y2="100" stroke="#333" strokeWidth="0.4" />
              <line x1="0" y1="50" x2="100" y2="50" stroke="#333" strokeWidth="0.4" />

              {/* Quadrant labels - clean and minimal */}
              <text x="25" y="20" textAnchor="middle" fill="#0ea5e9" fontSize="4.5" fontWeight="600">Pin</text>
              <text x="25" y="26" textAnchor="middle" fill="#555" fontSize="3">Mean Reversion</text>

              <text x="75" y="20" textAnchor="middle" fill="#a855f7" fontSize="4.5" fontWeight="600">Trap</text>
              <text x="75" y="26" textAnchor="middle" fill="#555" fontSize="3">False Breakout</text>

              <text x="25" y="70" textAnchor="middle" fill="#ef4444" fontSize="4.5" fontWeight="600">Sell</text>
              <text x="25" y="76" textAnchor="middle" fill="#555" fontSize="3">Acceleration</text>

              <text x="75" y="70" textAnchor="middle" fill="#22c55e" fontSize="4.5" fontWeight="600">Run</text>
              <text x="75" y="76" textAnchor="middle" fill="#555" fontSize="3">Air Pocket</text>

              {/* Current position - Bias +61, LFI 31 */}
              <circle cx="80.5" cy="65.5" r="10" fill="#22c55e" opacity="0.1" />
              <circle cx="80.5" cy="65.5" r="6" fill="#22c55e" opacity="0.25" />
              <circle cx="80.5" cy="65.5" r="3" fill="#22c55e" opacity="0.6" />
              <circle cx="80.5" cy="65.5" r="1.5" fill="#fff" />

              {/* Axis indicators - subtle */}
              <text x="2" y="52" fill="#444" fontSize="2.5">−</text>
              <text x="98" y="52" fill="#444" fontSize="2.5" textAnchor="end">+</text>
              <text x="51" y="4" fill="#444" fontSize="2.5">+</text>
              <text x="51" y="99" fill="#444" fontSize="2.5">−</text>
            </svg>
          </div>
        </div>

        {/* Dealer Gravity Widget - Candle Chart with Bands */}
        <div className="widget dealer-gravity-widget">
          <div className="widget-header">
            <Tooltip content="dealerGravity"><h4>Dealer Gravity</h4></Tooltip>
            <div className="dg-header-right">
              <div className="timeframe-tabs">
                <Tooltip content="dealerGravity5m" position="bottom"><button className="tf-tab">5m</button></Tooltip>
                <Tooltip content="dealerGravity15m" position="bottom"><button className="tf-tab active">15m</button></Tooltip>
                <Tooltip content="dealerGravity1h" position="bottom"><button className="tf-tab">1h</button></Tooltip>
              </div>
            </div>
          </div>
          <div className="widget-content dg-content">
            <div className="dealer-gravity-chart">
              {/* Legend with prices */}
              <div className="dg-price-legend">
                <Tooltip content="dealerGravityBest"><span className="dg-price-item best"><span className="dg-line"></span>Best <strong>6983.66</strong></span></Tooltip>
                <Tooltip content="dealerGravityHigh"><span className="dg-price-item high"><span className="dg-line"></span>High <strong>6988.92</strong></span></Tooltip>
                <Tooltip content="dealerGravityLow"><span className="dg-price-item low"><span className="dg-line"></span>Low <strong>6978.42</strong></span></Tooltip>
              </div>
              <svg viewBox="0 0 380 260" className="dg-svg">
                {/* Confidence cloud - billowy background effect */}
                <defs>
                  <linearGradient id="cloudGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.08" />
                    <stop offset="30%" stopColor="#3b82f6" stopOpacity="0.15" />
                    <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.08" />
                    <stop offset="70%" stopColor="#3b82f6" stopOpacity="0.15" />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.08" />
                  </linearGradient>
                  <filter id="cloudBlur" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur in="SourceGraphic" stdDeviation="8" />
                  </filter>
                </defs>

                {/* Confidence cloud shape */}
                <path
                  d="M 20 60 Q 50 45, 80 55 Q 120 70, 160 50 Q 200 35, 240 55 Q 280 70, 320 50 Q 350 40, 360 55
                     L 360 200 Q 350 215, 320 205 Q 280 190, 240 205 Q 200 220, 160 200 Q 120 185, 80 200 Q 50 215, 20 200 Z"
                  fill="url(#cloudGradient)"
                  filter="url(#cloudBlur)"
                />

                {/* Y-axis price scale */}
                <line x1="355" y1="30" x2="355" y2="230" stroke="#333" strokeWidth="1" />
                <text x="362" y="40" fill="#555" fontSize="9">7010.00</text>
                <text x="362" y="80" fill="#555" fontSize="9">7000.00</text>
                <text x="362" y="120" fill="#555" fontSize="9">6990.00</text>
                <text x="362" y="160" fill="#ef4444" fontSize="9" fontWeight="500">6983.66</text>
                <text x="362" y="200" fill="#555" fontSize="9">6970.00</text>
                <text x="362" y="230" fill="#555" fontSize="9">6960.00</text>

                {/* High band (green dashed) */}
                <path
                  d="M 20 70 Q 60 60, 100 75 Q 150 85, 200 65 Q 250 50, 300 70 Q 330 80, 350 65"
                  fill="none"
                  stroke="#22c55e"
                  strokeWidth="1.5"
                  opacity="0.7"
                />

                {/* Low band (pink/red dashed) */}
                <path
                  d="M 20 190 Q 60 200, 100 185 Q 150 175, 200 195 Q 250 205, 300 185 Q 330 175, 350 190"
                  fill="none"
                  stroke="#f472b6"
                  strokeWidth="1.5"
                  opacity="0.7"
                />

                {/* Best guess band (cyan solid) */}
                <path
                  d="M 20 130 Q 60 120, 100 135 Q 150 145, 200 125 Q 250 115, 300 135 Q 330 145, 350 130"
                  fill="none"
                  stroke="#0ea5e9"
                  strokeWidth="2"
                />

                {/* Current price horizontal line */}
                <line x1="20" y1="160" x2="350" y2="160" stroke="#ef4444" strokeWidth="1" strokeDasharray="3 3" opacity="0.6" />

                {/* Candlesticks */}
                {[
                  { x: 35, o: 145, c: 130, h: 120, l: 155 },
                  { x: 60, o: 130, c: 140, h: 125, l: 150 },
                  { x: 85, o: 140, c: 125, h: 115, l: 148 },
                  { x: 110, o: 125, c: 135, h: 118, l: 142 },
                  { x: 135, o: 135, c: 120, h: 110, l: 145 },
                  { x: 160, o: 120, c: 130, h: 112, l: 138 },
                  { x: 185, o: 130, c: 115, h: 105, l: 140 },
                  { x: 210, o: 115, c: 125, h: 108, l: 132 },
                  { x: 235, o: 125, c: 140, h: 118, l: 148 },
                  { x: 260, o: 140, c: 155, h: 135, l: 162 },
                  { x: 285, o: 155, c: 145, h: 140, l: 165 },
                  { x: 310, o: 145, c: 160, h: 138, l: 168 },
                  { x: 335, o: 160, c: 150, h: 145, l: 170 },
                ].map((candle, i) => {
                  const bullish = candle.c < candle.o;
                  const color = bullish ? '#22c55e' : '#ef4444';
                  const top = Math.min(candle.o, candle.c);
                  const height = Math.abs(candle.o - candle.c) || 2;
                  return (
                    <g key={i}>
                      <line x1={candle.x} y1={candle.h} x2={candle.x} y2={candle.l} stroke={color} strokeWidth="1" />
                      <rect x={candle.x - 7} y={top} width="14" height={height} fill={color} rx="1" />
                    </g>
                  );
                })}

                {/* Time axis markers */}
                <text x="35" y="250" fill="#444" fontSize="8" textAnchor="middle">1:30</text>
                <text x="135" y="250" fill="#444" fontSize="8" textAnchor="middle">2:00</text>
                <text x="235" y="250" fill="#444" fontSize="8" textAnchor="middle">2:30</text>
                <text x="335" y="250" fill="#444" fontSize="8" textAnchor="middle">3:00</text>
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Controls Row - GEX/Heatmap settings */}
      <div className="controls">
        {/* GEX Panel controls first */}
        <div className="control-group">
          <label>GEX</label>
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

        {/* Heatmap controls */}
        <div className="control-group">
          <label>Strategy</label>
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
        </div>

        <div className="control-group">
          <label>Side</label>
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
          </div>
        </div>

        <div className="control-group">
          <label>DTE</label>
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
        </div>

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

        {/* Scroll controls */}
        <div className="control-group">
          <label>Scroll</label>
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
                  const isAtm = spxSpot && Math.abs(strike - spxSpot) < 5;

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
                    const isAtm = spxSpot && Math.abs(strike - spxSpot) < 5;
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
                                {val === null ? '-' : val > 0 ? val.toFixed(2) : 'NA'}
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
                                {val === null ? '-' : val > 0 ? val.toFixed(2) : 'NA'}
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
                              {strat.debit !== null ? `$${strat.debit.toFixed(2)}` : '-'}
                            </span>
                          </div>
                        </div>
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
                  {spxSpot && spxSpot >= riskGraphData.minPrice && spxSpot <= riskGraphData.maxPrice && (
                    <line
                      x1={50 + ((spxSpot - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530}
                      y1="20"
                      x2={50 + ((spxSpot - riskGraphData.minPrice) / (riskGraphData.maxPrice - riskGraphData.minPrice)) * 530}
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
                      {spxSpot && (
                        <div className="stat">
                          <span className="stat-label">Spot</span>
                          <span className="stat-value">{spxSpot.toFixed(2)}</span>
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
              <button className="btn btn-primary" onClick={copyTosScript}>
                Copy TOS Script
              </button>
              <button className="btn btn-secondary" onClick={addToRiskGraph}>
                Add to Risk Graph
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
