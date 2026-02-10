/**
 * GexChartPanel - Candlestick chart with Volume Profile and separate GEX panel
 *
 * Combines:
 * - TradingView Lightweight Charts for candlesticks (1 week of data)
 * - Volume Profile as canvas-rendered horizontal bars (left side, inside chart)
 * - GEX bars in a separate panel on the right (outside chart, no overlap)
 * - Timeframe selector: 5m, 10m, 15m
 * - Settings dialogs for each indicator
 *
 * Performance optimizations:
 * - Chart persists across open/close cycles
 * - Loading overlay shows on top of existing data
 * - No artificial delays
 * - Skeleton placeholder during initial load
 */

import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import WhatsNew from './WhatsNew';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  CrosshairMode,
} from 'lightweight-charts';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import {
  VolumeProfilePrimitive,
  GexSettings,
  VolumeProfileSettings,
  useIndicatorSettings,
  sigmaToPercentile,
} from './chart-primitives';
import type { VolumeProfileDataPoint } from './chart-primitives';
import { captureChart } from '../utils/chartCapture';
import { analyzeChart, type DGAnalysisResult } from '../services/dealerGravityService';
import { useDealerGravity } from '../contexts/DealerGravityContext';

// Types
type CandleData = {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
};

type VolumeProfileLevel = {
  price: number;
  volume: number;
};

type VolumeProfileData = {
  levels: VolumeProfileLevel[];
  maxVolume: number;
};

type GexByStrike = Record<number, { calls: number; puts: number }>;

type Timeframe = '5m' | '10m' | '15m';

interface Props {
  symbol?: string;
  volumeProfile: VolumeProfileData | null;
  gexByStrike: GexByStrike;
  maxGex: number;
  maxNetGex: number;
  gexMode: 'combined' | 'net';
  currentSpot: number | null;
  height?: number;
  isOpen?: boolean;
}

// Helper: format time for crosshair
function formatCrosshairLabel(time: unknown): string {
  let dUtc: Date;
  if (typeof time === 'number') {
    dUtc = new Date(time * 1000);
  } else if (time && typeof time === 'object' && 'year' in time) {
    const t = time as { year: number; month: number; day: number };
    dUtc = new Date(Date.UTC(t.year, t.month - 1, t.day));
  } else {
    return '';
  }
  return dUtc.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

// Helper: theme-aware chart colors for LightweightCharts canvas
function getChartColors(theme: string) {
  const isLight = theme === 'light';
  return {
    background: isLight ? '#ffffff' : '#0a0a0a',
    textColor: isLight ? 'rgba(110,110,115,1)' : 'rgba(148,163,184,1)',
    gridColor: isLight ? 'rgba(0,0,0,0.06)' : 'transparent',
    borderColor: isLight ? 'rgba(209,209,214,1)' : 'rgba(30,41,59,1)',
  };
}

// Helper: convert hex to rgba
function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Calculate Volume Profile with binning (TradingView style)
 *
 * @param levels - Volume data at specific price levels
 * @param rowsLayout - 'number_of_rows' or 'ticks_per_row'
 * @param rowSize - Number of rows (if number_of_rows) or ticks per row (if ticks_per_row)
 * @returns Binned volume profile data
 */
function calculateVolumeProfile(
  levels: VolumeProfileLevel[],
  rowsLayout: 'number_of_rows' | 'ticks_per_row',
  rowSize: number
): { levels: VolumeProfileLevel[]; maxVolume: number; binSize: number } {
  if (levels.length === 0) return { levels: [], maxVolume: 0, binSize: 1 };

  // Find price range
  const prices = levels.map(l => l.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice;

  if (priceRange <= 0) return { levels, maxVolume: Math.max(...levels.map(l => l.volume)), binSize: 1 };

  // Calculate effective number of bins based on layout mode
  let effectiveBins: number;
  if (rowsLayout === 'number_of_rows') {
    // Fixed number of rows across visible range
    effectiveBins = Math.max(1, rowSize);
  } else {
    // Fixed ticks per row - calculate how many bins fit
    const ticksPerRow = Math.max(1, rowSize);
    effectiveBins = Math.ceil(priceRange / ticksPerRow);
  }

  // Clamp to reasonable range (allow up to 2000 for 1-pixel resolution)
  effectiveBins = Math.max(1, Math.min(2000, effectiveBins));
  const binSize = priceRange / effectiveBins;

  // Bin the raw data - track sum and count for averaging
  const binSums: number[] = new Array(effectiveBins).fill(0);
  const binCounts: number[] = new Array(effectiveBins).fill(0);

  for (const level of levels) {
    let binIndex = Math.floor((level.price - minPrice) / binSize);
    if (binIndex >= effectiveBins) binIndex = effectiveBins - 1;
    if (binIndex < 0) binIndex = 0;
    binSums[binIndex] += level.volume;
    binCounts[binIndex] += 1;
  }

  // Convert back to levels using AVERAGE volume per row
  const binnedLevels: VolumeProfileLevel[] = [];
  let maxVolume = 0;

  for (let i = 0; i < effectiveBins; i++) {
    const count = binCounts[i];
    if (count > 0) {
      // Average volume = sum / count of raw bins in this row
      const avgVolume = binSums[i] / count;
      const price = minPrice + (i + 0.5) * binSize;
      binnedLevels.push({ price, volume: avgVolume });
      maxVolume = Math.max(maxVolume, avgVolume);
    }
  }

  return { levels: binnedLevels, maxVolume, binSize };
}

export default function GexChartPanel({
  symbol = 'SPX',
  volumeProfile,
  gexByStrike,
  maxGex,
  maxNetGex,
  gexMode: externalGexMode,
  currentSpot,
  height: _height = 600,
  isOpen = true,
}: Props) {
  void _height;

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const vpPrimitiveRef = useRef<VolumeProfilePrimitive | null>(null);
  const gexPanelRef = useRef<HTMLDivElement>(null);

  const [timeframe, setTimeframe] = useState<Timeframe>('5m');
  const [candles, setCandles] = useState<CandleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartReady, setChartReady] = useState(false);

  // Track price range for GEX panel synchronization
  const [priceRange, setPriceRange] = useState<{ min: number; max: number } | null>(null);
  // Track the GEX panel's actual height for pixel-accurate positioning
  const [gexPanelHeight, setGexPanelHeight] = useState<number>(0);
  const gexBarsRef = useRef<HTMLDivElement>(null);

  // Persistent settings from hook
  const {
    gexConfig,
    vpConfig,
    setGexConfig,
    setVpConfig,
    saveAsDefault,
    resetToFactoryDefaults,
  } = useIndicatorSettings();

  // Settings dialog visibility
  const [showVpSettings, setShowVpSettings] = useState(false);
  const [showGexSettings, setShowGexSettings] = useState(false);

  // AI Analysis state
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<DGAnalysisResult | null>(null);
  const [showAnalysis, setShowAnalysis] = useState(false);

  // Structural lines from Dealer Gravity context
  const { artifact: dgArtifact } = useDealerGravity();
  const [showStructuralLines, setShowStructuralLines] = useState(true);
  const structuralLinesRef = useRef<any[]>([]);

  // Theme awareness for canvas chart
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'dark');
  useEffect(() => {
    const observer = new MutationObserver(() => {
      setTheme(document.documentElement.dataset.theme || 'dark');
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);

  // Handle AI analysis request
  const handleAnalyze = useCallback(async () => {
    if (!chartRef.current || analyzing) return;

    setAnalyzing(true);
    setShowAnalysis(true);
    setAnalysisResult(null);

    try {
      // Capture chart screenshot
      const imageBase64 = captureChart(chartRef.current);
      if (!imageBase64) {
        console.error('[GexChartPanel] Failed to capture chart');
        setAnalyzing(false);
        return;
      }

      // Call AI analysis API
      const result = await analyzeChart(imageBase64, currentSpot || 0);
      setAnalysisResult(result);
    } catch (error) {
      console.error('[GexChartPanel] Analysis failed:', error);
    } finally {
      setAnalyzing(false);
    }
  }, [analyzing, currentSpot]);

  // Sync external gexMode prop with config (if parent changes it)
  useEffect(() => {
    if (externalGexMode !== gexConfig.mode) {
      setGexConfig(c => ({ ...c, mode: externalGexMode }));
    }
  }, [externalGexMode]);

  // Fetch candle data (5 DTE) and filter to market hours only
  useEffect(() => {
    const fetchCandles = async () => {
      setLoading(true);
      try {
        const apiSymbol = symbol.startsWith('I:') ? symbol : `I:${symbol}`;
        const encodedSymbol = encodeURIComponent(apiSymbol);
        const response = await fetch(`/api/models/candles/${encodedSymbol}?days=20`, {
          credentials: 'include',
        });
        const data = await response.json();
        if (data.success && data.data) {
          const candleKey = `candles_${timeframe}` as keyof typeof data.data;
          const candleData = data.data[candleKey] as CandleData[] | undefined;
          if (candleData && Array.isArray(candleData)) {
            // Filter to regular trading hours only (9:30 AM - 4:00 PM ET)
            // This removes overnight gaps and pre/post market
            const filteredCandles = candleData.filter((candle) => {
              const date = new Date(candle.t * 1000);
              // Convert to Eastern Time
              const etTime = date.toLocaleString('en-US', { timeZone: 'America/New_York' });
              const etDate = new Date(etTime);
              const hours = etDate.getHours();
              const minutes = etDate.getMinutes();
              const timeInMinutes = hours * 60 + minutes;
              // Market hours: 9:30 AM (570 min) to 4:00 PM (960 min)
              return timeInMinutes >= 570 && timeInMinutes < 960;
            });
            setCandles(filteredCandles);
          }
        }
      } catch (err) {
        console.error('[GexChartPanel] Failed to fetch candles:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCandles();
    // Only poll when tab is visible to save resources
    const interval = setInterval(() => {
      if (!document.hidden) fetchCandles();
    }, 30000);
    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  // Create chart with primitives - no delay, chart persists across toggles
  useEffect(() => {
    if (!containerRef.current || !isOpen) return;
    if (chartRef.current) return;

    const colors = getChartColors(document.documentElement.dataset.theme || 'dark');

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.textColor,
      },
      grid: {
        vertLines: { color: colors.gridColor },
        horzLines: { color: colors.gridColor },
      },
      rightPriceScale: {
        borderColor: colors.borderColor,
        scaleMargins: { top: 0.08, bottom: 0.08 },  // More margin for broader view
      },
      timeScale: {
        borderColor: colors.borderColor,
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: 'rgba(147, 51, 234, 0.5)',
          width: 1,
          style: 0, // Solid
          labelBackgroundColor: 'rgba(147, 51, 234, 0.9)',
        },
        horzLine: {
          color: 'rgba(147, 51, 234, 0.5)',
          width: 1,
          style: 0, // Solid
          labelBackgroundColor: 'rgba(147, 51, 234, 0.9)',
        },
      },
      localization: {
        timeFormatter: (time: unknown) => formatCrosshairLabel(time),
      },
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = (chart as any).addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      priceLineVisible: true,
      lastValueVisible: true,
      priceLineColor: 'rgba(16, 185, 129, 0.85)',
    });

    chartRef.current = chart;
    seriesRef.current = series;

    try {
      const vpPrimitive = new VolumeProfilePrimitive();
      series.attachPrimitive(vpPrimitive);
      vpPrimitiveRef.current = vpPrimitive;
    } catch (err) {
      console.error('[GexChartPanel] Failed to attach VP primitive:', err);
    }

    setChartReady(true);
    chart.priceScale('right').applyOptions({ autoScale: true });

    // Subscribe to crosshair move to detect any chart interaction (zoom/pan/resize)
    // This will update the GEX panel to stay in sync with the chart's price scale
    const updateVisiblePriceRange = () => {
      if (!seriesRef.current || !chartRef.current) return;
      try {
        // Get the visible price range by checking coordinates at top and bottom of chart
        const chartHeight = containerRef.current?.clientHeight || 400;
        const topPrice = seriesRef.current.coordinateToPrice(0);
        const bottomPrice = seriesRef.current.coordinateToPrice(chartHeight - 30); // Account for time scale

        if (topPrice !== null && bottomPrice !== null && topPrice !== bottomPrice) {
          setPriceRange({
            min: Math.min(topPrice, bottomPrice),
            max: Math.max(topPrice, bottomPrice)
          });
        }
      } catch (e) {
        // Ignore errors during initialization
      }
    };

    // Subscribe to multiple events to catch all view changes
    chart.subscribeCrosshairMove(updateVisiblePriceRange);
    chart.timeScale().subscribeVisibleLogicalRangeChange(updateVisiblePriceRange);

    // Debounced update using requestAnimationFrame
    let rafId: number | null = null;
    const debouncedUpdate = () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = null;
        updateVisiblePriceRange();
      });
    };

    // Also update on any chart click/drag
    const chartElement = containerRef.current;
    chartElement?.addEventListener('mouseup', debouncedUpdate);
    chartElement?.addEventListener('wheel', debouncedUpdate);

    const handleResize = () => {
      if (!containerRef.current || !chartRef.current) return;
      debouncedUpdate();
    };

    window.addEventListener('resize', handleResize);
    (chartRef.current as any)._resizeHandler = handleResize;
    (chartRef.current as any)._rangeHandler = updateVisiblePriceRange;
    (chartRef.current as any)._debouncedHandler = debouncedUpdate;
    (chartRef.current as any)._rafId = rafId;
    (chartRef.current as any)._chartElement = chartElement;

    return () => {
      if (chartRef.current) {
        const handler = (chartRef.current as any)._resizeHandler;
        const debouncedHandler = (chartRef.current as any)._debouncedHandler;
        const element = (chartRef.current as any)._chartElement;
        const pendingRaf = (chartRef.current as any)._rafId;

        // Cancel any pending RAF
        if (pendingRaf !== null) cancelAnimationFrame(pendingRaf);

        if (handler) window.removeEventListener('resize', handler);
        if (element && debouncedHandler) {
          element.removeEventListener('mouseup', debouncedHandler);
          element.removeEventListener('wheel', debouncedHandler);
        }
        chartRef.current.unsubscribeCrosshairMove(
          (chartRef.current as any)._rangeHandler
        );
        chartRef.current.timeScale().unsubscribeVisibleLogicalRangeChange(
          (chartRef.current as any)._rangeHandler
        );
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
        vpPrimitiveRef.current = null;
      }
    };
  }, [isOpen]);

  // Update chart colors when theme changes
  useEffect(() => {
    if (!chartRef.current) return;
    const colors = getChartColors(theme);
    chartRef.current.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: colors.background },
        textColor: colors.textColor,
      },
      grid: {
        vertLines: { color: colors.gridColor },
        horzLines: { color: colors.gridColor },
      },
      rightPriceScale: { borderColor: colors.borderColor },
      timeScale: { borderColor: colors.borderColor },
    });
  }, [theme]);

  // Track GEX bars panel height for pixel-accurate positioning
  useEffect(() => {
    if (!gexBarsRef.current) return;
    const updateHeight = () => {
      if (gexBarsRef.current) {
        setGexPanelHeight(gexBarsRef.current.clientHeight);
      }
    };
    updateHeight();
    const resizeObserver = new ResizeObserver(updateHeight);
    resizeObserver.observe(gexBarsRef.current);
    return () => resizeObserver.disconnect();
  }, [chartReady]);

  // Draw structural lines from Dealer Gravity artifact
  useEffect(() => {
    if (!chartReady || !seriesRef.current) return;
    const series = seriesRef.current;

    // Remove existing price lines
    structuralLinesRef.current.forEach(line => {
      try {
        series.removePriceLine(line);
      } catch (e) {
        // Line may already be removed
      }
    });
    structuralLinesRef.current = [];

    // Draw new lines if enabled and we have structures
    if (showStructuralLines && dgArtifact?.structures?.volumeNodes) {
      const nodes = dgArtifact.structures.volumeNodes;
      nodes.forEach(node => {
        const priceLine = series.createPriceLine({
          price: node.price,
          color: node.color,
          lineWidth: Math.round(node.weight) as 1 | 2 | 3 | 4,
          lineStyle: 0, // Solid
          axisLabelVisible: false,
          title: '',
        });
        structuralLinesRef.current.push(priceLine);
      });
    }
  }, [chartReady, showStructuralLines, dgArtifact?.structures?.volumeNodes]);

  // Update candle data and track price range
  useEffect(() => {
    if (!chartReady || !seriesRef.current || !candles || candles.length === 0) return;

    const formatted = candles.map((c) => ({
      time: c.t as UTCTimestamp,
      open: c.o,
      high: c.h,
      low: c.l,
      close: c.c,
    }));

    seriesRef.current.setData(formatted);

    // Calculate price range from candle data for GEX panel
    const highs = candles.map(c => c.h);
    const lows = candles.map(c => c.l);
    const minPrice = Math.min(...lows);
    const maxPrice = Math.max(...highs);
    setPriceRange({ min: minPrice, max: maxPrice });

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();

      // Set default price scale: 5 pixels per point
      // This gives a comfortable view where price movements are clearly visible
      const DEFAULT_PIXELS_PER_POINT = 5;
      const chartHeight = containerRef.current?.clientHeight || 600;
      const desiredPriceRange = chartHeight / DEFAULT_PIXELS_PER_POINT;

      // Center on the last candle's close price
      const lastCandle = candles[candles.length - 1];
      const centerPrice = lastCandle?.c || (minPrice + maxPrice) / 2;

      const scaledMin = centerPrice - desiredPriceRange / 2;
      const scaledMax = centerPrice + desiredPriceRange / 2;

      // Use autoscaleInfoProvider to set the initial price range
      seriesRef.current.applyOptions({
        autoscaleInfoProvider: () => ({
          priceRange: {
            minValue: scaledMin,
            maxValue: scaledMax,
          },
        }),
      });

      // Trigger a re-scale to apply the new range
      chartRef.current.priceScale('right').applyOptions({ autoScale: true });
    }
  }, [candles, chartReady]);

  // VP Structural Levels - will be derived from actual VP data in the future
  // For now, let the chart auto-scale based on candle data
  // TODO: Implement VP structural analysis to dynamically identify nodes/wells/edges

  // Calculate GEX bars for the separate panel with pixel-accurate positioning
  const gexBars = useMemo(() => {
    if (!gexConfig.enabled || !priceRange || gexPanelHeight === 0) return [];

    const { min: minPrice, max: maxPrice } = priceRange;
    const priceSpan = maxPrice - minPrice;
    if (priceSpan <= 0) return [];

    // Chart has 5% margin top and bottom, so effective price range is in the middle 90%
    const chartMargin = 0.05;
    const effectiveHeight = gexPanelHeight * (1 - 2 * chartMargin);
    const topOffset = gexPanelHeight * chartMargin;

    // Filter GEX data to visible price range (with some margin)
    const margin = priceSpan * 0.1;
    const visibleMin = minPrice - margin;
    const visibleMax = maxPrice + margin;

    return Object.entries(gexByStrike)
      .map(([strike, values]) => {
        const strikePrice = parseFloat(strike);
        if (strikePrice < visibleMin || strikePrice > visibleMax) return null;

        const netGex = values.calls - values.puts;
        // Only mark as ATM if showATM is enabled
        const isATM = gexConfig.showATM && currentSpot && Math.abs(strikePrice - currentSpot) < 2;

        // Calculate pixel position from top (higher price = smaller Y)
        const priceRatio = (maxPrice - strikePrice) / priceSpan;
        const pixelY = topOffset + (priceRatio * effectiveHeight);

        return {
          strike: strikePrice,
          calls: values.calls,
          puts: values.puts,
          netGex,
          isATM,
          pixelY: Math.round(pixelY),
        };
      })
      .filter((b): b is NonNullable<typeof b> => b !== null)
      .sort((a, b) => b.strike - a.strike); // Sort by strike descending (top to bottom)
  }, [gexByStrike, priceRange, currentSpot, gexConfig.enabled, gexConfig.showATM, gexPanelHeight]);

  // Calculate max values for bar scaling
  const gexScaleMax = useMemo(() => {
    if (gexConfig.mode === 'net') {
      return maxNetGex || 1;
    }
    return maxGex || 1;
  }, [maxGex, maxNetGex, gexConfig.mode]);

  // Update Volume Profile primitive when data or config changes
  useEffect(() => {
    if (!vpPrimitiveRef.current || !volumeProfile) return;

    // Step 1: Filter outliers using sigma-based percentile capping
    // This removes anomalies from large block trades that skew the profile
    const percentile = sigmaToPercentile(vpConfig.cappingSigma);
    const volumes = volumeProfile.levels.map(l => l.volume).sort((a, b) => a - b);
    const capIndex = Math.floor(volumes.length * percentile);
    const volumeCap = volumes[capIndex] || volumeProfile.maxVolume;

    const cappedLevels: VolumeProfileLevel[] = volumeProfile.levels.map((level) => ({
      price: level.price,
      volume: Math.min(level.volume, volumeCap),
    }));

    // Step 2: Calculate volume profile - bin the data into rows
    const { levels: rebinnedLevels, maxVolume: rebinnedMax, binSize } = calculateVolumeProfile(
      cappedLevels,
      vpConfig.rowsLayout,
      vpConfig.rowSize
    );

    const vpData: VolumeProfileDataPoint[] = rebinnedLevels.map((level) => ({
      price: level.price,
      volume: level.volume,
    }));

    const alpha = (100 - vpConfig.transparency) / 100;

    vpPrimitiveRef.current.setData(vpConfig.enabled ? vpData : []);
    vpPrimitiveRef.current.setOptions({
      maxVolume: rebinnedMax,
      color: hexToRgba(vpConfig.color, alpha),
      maxBarWidthPercent: vpConfig.widthPercent,
      binSize: binSize,
      // For "number of rows" mode, pass numRows so bar height = viewport_height / numRows
      numRows: vpConfig.rowsLayout === 'number_of_rows' ? vpConfig.rowSize : undefined,
    });
  }, [volumeProfile, vpConfig]);


  return (
    <div className="gex-chart-panel">
      {/* Header with timeframe selector */}
      <div className="gex-chart-header">
        <h3>Dealer Gravity</h3>
        <div className="gex-chart-header-controls">
          <WhatsNew area="dealer-gravity" />
          <div className="gex-chart-tf-selector">
            {(['5m', '10m', '15m'] as Timeframe[]).map((tf) => (
              <button
                key={tf}
                className={`gex-chart-tf-btn ${timeframe === tf ? 'active' : ''}`}
                onClick={() => setTimeframe(tf)}
              >
                {tf}
              </button>
            ))}
          </div>
          <button
            className={`gex-chart-ai-btn ${analyzing ? 'analyzing' : ''}`}
            onClick={handleAnalyze}
            disabled={analyzing || !chartRef.current}
            title="AI Analysis - Analyze chart structure"
          >
            {analyzing ? (
              <span className="ai-spinner" />
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 16v-4M12 8h.01"/>
              </svg>
            )}
            AI
          </button>
        </div>
      </div>

      {/* Chart + GEX Panel Container */}
      <div className="gex-chart-body">
        {/* Chart Area (left) */}
        <div className="gex-chart-area">
          {/* Loading overlay - shows on top of existing data */}
          {loading && (
            <div className="gex-chart-loading-overlay">
              <div className="gex-chart-spinner" />
              <span>Updating...</span>
            </div>
          )}

          {/* Skeleton placeholder when no data yet */}
          {!chartReady && candles.length === 0 && (
            <div className="gex-chart-skeleton">
              <div className="skeleton-candles">
                {Array.from({ length: 20 }).map((_, i) => (
                  <div key={i} className="skeleton-candle" style={{ height: `${30 + Math.random() * 40}%` }} />
                ))}
              </div>
            </div>
          )}

          <div ref={containerRef} className="gex-chart-container" />

        {/* Indicator Labels - Top Left inside chart (VRVP only) */}
        <div className="dealer-gravity-indicators">
          {/* Volume Profile */}
          <div
            className={`dg-indicator ${!vpConfig.enabled ? 'disabled' : ''}`}
            onDoubleClick={() => setShowVpSettings(true)}
            title="Double-click for settings"
          >
            <span className="dg-indicator-color" style={{ backgroundColor: vpConfig.color }} />
            <span className="dg-indicator-name">VRVP</span>
            <button
              className="dg-indicator-btn"
              onClick={() => setVpConfig(c => ({ ...c, enabled: !c.enabled }))}
              title={vpConfig.enabled ? 'Hide' : 'Show'}
            >
              {vpConfig.enabled ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              )}
            </button>
            <button
              className="dg-indicator-btn"
              onClick={() => setShowVpSettings(true)}
              title="Settings"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
          </div>

          {/* Structural Lines Toggle */}
          <div
            className={`dg-indicator ${!showStructuralLines ? 'disabled' : ''}`}
            title="Structural lines from VP Line Editor"
          >
            <span className="dg-indicator-color" style={{ backgroundColor: '#ffff00' }} />
            <span className="dg-indicator-name">DG</span>
            <button
              className="dg-indicator-btn"
              onClick={() => setShowStructuralLines(!showStructuralLines)}
              title={showStructuralLines ? 'Hide structural lines' : 'Show structural lines'}
            >
              {showStructuralLines ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Volume Profile Settings Dialog */}
        {showVpSettings && (
          <div className="dg-settings-overlay" onClick={() => setShowVpSettings(false)}>
            <div onClick={(e) => e.stopPropagation()}>
              <VolumeProfileSettings
                config={vpConfig}
                onConfigChange={setVpConfig}
                onSaveDefault={saveAsDefault}
                onResetToFactory={resetToFactoryDefaults}
                onClose={() => setShowVpSettings(false)}
              />
            </div>
          </div>
        )}

        </div>

        {/* Separate GEX Panel (right side) - always visible */}
        <div className="gex-side-panel" ref={gexPanelRef}>
          <div className={`gex-side-header ${!gexConfig.enabled ? 'disabled' : ''}`}>
            <span className="gex-side-color-pair">
              <span style={{ backgroundColor: gexConfig.callColor }} />
              <span style={{ backgroundColor: gexConfig.putColor }} />
            </span>
            <span className="gex-side-title">GEX</span>
            <button
              className="gex-side-btn"
              onClick={() => setGexConfig(c => ({ ...c, enabled: !c.enabled }))}
              title={gexConfig.enabled ? 'Hide GEX' : 'Show GEX'}
            >
              {gexConfig.enabled ? '👁' : '👁‍🗨'}
            </button>
            <button
              className="gex-side-btn"
              onClick={() => setShowGexSettings(true)}
              title="GEX Settings"
            >
              ⚙
            </button>
          </div>
          {/* GEX bars - only show when enabled */}
          {gexConfig.enabled && (
            <div className="gex-side-bars" ref={gexBarsRef}>
              {gexConfig.mode === 'combined' ? (
                // Combined mode: calls on right, puts on left
                gexBars.map((bar) => {
                  const callWidth = (bar.calls / gexScaleMax) * 50; // 50% max width each side
                  const putWidth = (bar.puts / gexScaleMax) * 50;
                  // barHeight controls the thickness of each bar (100-500 maps to 1-20px)
                  const barThickness = Math.round(1 + ((gexConfig.barHeight - 100) / 400) * 19);

                  return (
                    <div
                      key={bar.strike}
                      className={`gex-side-bar-row ${bar.isATM ? 'atm' : ''}`}
                      style={{ top: `${bar.pixelY}px`, height: `${barThickness}px` }}
                      title={`Strike: ${bar.strike}\nCalls: ${bar.calls.toFixed(1)}M\nPuts: ${bar.puts.toFixed(1)}M`}
                    >
                      {/* Put bar (left side, grows right-to-left) */}
                      <div
                        className="gex-side-bar put"
                        style={{
                          width: `${putWidth}%`,
                          height: `${barThickness}px`,
                          backgroundColor: gexConfig.putColor,
                        }}
                      />
                      {/* Call bar (right side, grows left-to-right) */}
                      <div
                        className="gex-side-bar call"
                        style={{
                          width: `${callWidth}%`,
                          height: `${barThickness}px`,
                          backgroundColor: gexConfig.callColor,
                        }}
                      />
                      {bar.isATM && (
                        <div
                          className="gex-side-atm-marker"
                          style={{ backgroundColor: hexToRgba(gexConfig.atmColor, 0.8) }}
                        />
                      )}
                    </div>
                  );
                })
              ) : (
                // Net mode: single bar showing net GEX
                gexBars.map((bar) => {
                  const netWidth = Math.abs(bar.netGex / gexScaleMax) * 45;
                  const isPositive = bar.netGex >= 0;
                  // barHeight controls the thickness of each bar (100-500 maps to 1-20px)
                  const barThickness = Math.round(1 + ((gexConfig.barHeight - 100) / 400) * 19);

                  return (
                    <div
                      key={bar.strike}
                      className={`gex-side-bar-row net ${bar.isATM ? 'atm' : ''}`}
                      style={{ top: `${bar.pixelY}px`, height: `${barThickness}px` }}
                      title={`Strike: ${bar.strike}\nNet GEX: ${bar.netGex.toFixed(1)}M`}
                    >
                      <div
                        className={`gex-side-bar net ${isPositive ? 'positive' : 'negative'}`}
                        style={{
                          width: `${netWidth}%`,
                          height: `${barThickness}px`,
                          backgroundColor: isPositive ? gexConfig.callColor : gexConfig.putColor,
                          left: isPositive ? '50%' : `${50 - netWidth}%`,
                        }}
                      />
                      {bar.isATM && (
                        <div
                          className="gex-side-atm-marker"
                          style={{ backgroundColor: hexToRgba(gexConfig.atmColor, 0.8) }}
                        />
                      )}
                    </div>
                  );
                })
              )}
              {/* Center line for combined mode */}
              {gexConfig.mode === 'combined' && <div className="gex-side-center-line" />}
            </div>
          )}
          {/* Placeholder when disabled */}
          {!gexConfig.enabled && (
            <div className="gex-side-disabled">
              <span>GEX Hidden</span>
            </div>
          )}
          {/* Mode toggle at bottom */}
          <div className="gex-side-footer">
            <button
              className={`gex-mode-btn ${gexConfig.mode === 'combined' ? 'active' : ''}`}
              onClick={() => setGexConfig(c => ({ ...c, mode: 'combined' }))}
            >
              C/P
            </button>
            <button
              className={`gex-mode-btn ${gexConfig.mode === 'net' ? 'active' : ''}`}
              onClick={() => setGexConfig(c => ({ ...c, mode: 'net' }))}
            >
              Net
            </button>
          </div>
        </div>
      </div>

      {/* Footer legend - just candle count now */}
      <div className="gex-chart-legend">
        {candles.length > 0 && (
          <span className="legend-item candle-count">{candles.length} candles</span>
        )}
      </div>

      {/* GEX Settings Dialog - at root level for proper overlay */}
      {showGexSettings && (
        <div className="dg-settings-overlay" onClick={() => setShowGexSettings(false)}>
          <div onClick={(e) => e.stopPropagation()}>
            <GexSettings
              config={gexConfig}
              onConfigChange={setGexConfig}
              onSaveDefault={saveAsDefault}
              onResetToFactory={resetToFactoryDefaults}
              onClose={() => setShowGexSettings(false)}
            />
          </div>
        </div>
      )}

      {/* AI Analysis Results Panel */}
      {showAnalysis && (
        <div className="dg-analysis-panel">
          <div className="dg-analysis-header">
            <h4>AI Analysis</h4>
            <button
              className="dg-analysis-close"
              onClick={() => setShowAnalysis(false)}
              title="Close"
            >
              ×
            </button>
          </div>
          <div className="dg-analysis-content">
            {analyzing ? (
              <div className="dg-analysis-loading">
                <div className="ai-spinner" />
                <span>Analyzing chart structure...</span>
              </div>
            ) : analysisResult ? (
              <>
                <div className="dg-analysis-bias">
                  <span className={`bias-badge ${analysisResult.bias}`}>
                    {analysisResult.bias.toUpperCase()}
                  </span>
                  <span className="memory-strength">
                    Memory: {(analysisResult.marketMemoryStrength * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="dg-analysis-structures">
                  {analysisResult.volumeNodes.length > 0 && (
                    <div className="structure-item">
                      <span className="structure-label">Volume Nodes:</span>
                      <span className="structure-values">
                        {analysisResult.volumeNodes.map(p => p.toFixed(0)).join(', ')}
                      </span>
                    </div>
                  )}
                  {analysisResult.volumeWells.length > 0 && (
                    <div className="structure-item">
                      <span className="structure-label">Volume Wells:</span>
                      <span className="structure-values">
                        {analysisResult.volumeWells.map(p => p.toFixed(0)).join(', ')}
                      </span>
                    </div>
                  )}
                  {analysisResult.crevasses.length > 0 && (
                    <div className="structure-item">
                      <span className="structure-label">Crevasses:</span>
                      <span className="structure-values">
                        {analysisResult.crevasses.map(([s, e]) => `${s.toFixed(0)}-${e.toFixed(0)}`).join(', ')}
                      </span>
                    </div>
                  )}
                </div>
                <div className="dg-analysis-summary">
                  {analysisResult.summary}
                </div>
              </>
            ) : (
              <div className="dg-analysis-empty">
                Click AI to analyze the chart
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
