/**
 * GexChartPanel - Candlestick chart with Volume Profile and GEX as native chart primitives
 *
 * Combines:
 * - TradingView Lightweight Charts for candlesticks (1 week of data)
 * - Volume Profile as canvas-rendered horizontal bars (left side)
 * - GEX bars as canvas-rendered horizontal bars (right side)
 * - Timeframe selector: 5m, 10m, 15m
 * - Settings dialogs for each indicator
 *
 * All overlays are rendered using Lightweight Charts' Primitives API for perfect
 * synchronization with chart pan/zoom and native canvas performance.
 */

import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  CrosshairMode,
} from 'lightweight-charts';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import {
  GexPrimitive,
  VolumeProfilePrimitive,
  GexSettings,
  VolumeProfileSettings,
  useIndicatorSettings,
  sigmaToPercentile,
} from './chart-primitives';
import type { GexDataPoint, VolumeProfileDataPoint } from './chart-primitives';

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

// Helper: convert hex to rgba
function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Calculate Volume Profile using TradingView's VRVP algorithm
 *
 * TradingView's approach:
 * 1. Divide price range into N rows (bins)
 * 2. For each data point, calculate which bin(s) it overlaps
 * 3. Distribute volume proportionally based on overlap
 *
 * Since our data is pre-aggregated at specific price levels (not OHLCV candles),
 * each point contributes to the bin containing its price.
 *
 * @param levels - Volume data at specific price levels
 * @param numBins - Number of rows/bins to create (20-1000)
 * @returns Rebinned volume profile data
 */
function calculateVolumeProfile(
  levels: VolumeProfileLevel[],
  numBins: number
): { levels: VolumeProfileLevel[]; maxVolume: number } {
  if (levels.length === 0) return { levels: [], maxVolume: 0 };

  // Find price range
  const prices = levels.map(l => l.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice;

  if (priceRange <= 0) return { levels, maxVolume: Math.max(...levels.map(l => l.volume)) };

  // Clamp numBins to valid range
  const effectiveBins = Math.max(20, Math.min(1000, numBins));

  // TradingView formula: Ticks Per Row = (High - Low) / Number of Rows
  const binSize = priceRange / effectiveBins;

  // Initialize bins
  const bins: number[] = new Array(effectiveBins).fill(0);

  // TradingView algorithm: assign each data point's volume to overlapping bins
  // Since our data points are at specific prices (not ranges), each point
  // goes into the bin containing that price
  for (const level of levels) {
    // Calculate which bin this price falls into
    let binIndex = Math.floor((level.price - minPrice) / binSize);

    // Handle edge case where price equals maxPrice
    if (binIndex >= effectiveBins) binIndex = effectiveBins - 1;
    if (binIndex < 0) binIndex = 0;

    bins[binIndex] += level.volume;
  }

  // Convert bins back to levels with price at bin center
  const rebinnedLevels: VolumeProfileLevel[] = [];
  let maxVolume = 0;

  for (let i = 0; i < effectiveBins; i++) {
    if (bins[i] > 0) {
      const price = minPrice + (i + 0.5) * binSize; // Center of bin
      rebinnedLevels.push({ price, volume: bins[i] });
      maxVolume = Math.max(maxVolume, bins[i]);
    }
  }

  return { levels: rebinnedLevels, maxVolume };
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
  const gexPrimitiveRef = useRef<GexPrimitive | null>(null);
  const vpPrimitiveRef = useRef<VolumeProfilePrimitive | null>(null);

  const [timeframe, setTimeframe] = useState<Timeframe>('5m');
  const [candles, setCandles] = useState<CandleData[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartReady, setChartReady] = useState(false);

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

  // Sync external gexMode prop with config (if parent changes it)
  useEffect(() => {
    if (externalGexMode !== gexConfig.mode) {
      setGexConfig(c => ({ ...c, mode: externalGexMode }));
    }
  }, [externalGexMode]);

  // Fetch candle data (1 week)
  useEffect(() => {
    const fetchCandles = async () => {
      setLoading(true);
      try {
        const apiSymbol = symbol.startsWith('I:') ? symbol : `I:${symbol}`;
        const encodedSymbol = encodeURIComponent(apiSymbol);
        const response = await fetch(`/api/models/candles/${encodedSymbol}?days=7`, {
          credentials: 'include',
        });
        const data = await response.json();
        if (data.success && data.data) {
          const candleKey = `candles_${timeframe}` as keyof typeof data.data;
          const candleData = data.data[candleKey] as CandleData[] | undefined;
          if (candleData && Array.isArray(candleData)) {
            setCandles(candleData);
          }
        }
      } catch (err) {
        console.error('[GexChartPanel] Failed to fetch candles:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCandles();
    const interval = setInterval(fetchCandles, 30000);
    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  // Create chart with primitives
  useEffect(() => {
    if (!containerRef.current || !isOpen) return;
    if (chartRef.current) return;

    const timer = setTimeout(() => {
      if (!containerRef.current || chartRef.current) return;

      const chart = createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: '#0a0a0a' },
          textColor: 'rgba(148, 163, 184, 1)',
        },
        grid: {
          vertLines: { color: 'rgba(51, 65, 85, 0.3)' },
          horzLines: { color: 'rgba(51, 65, 85, 0.3)' },
        },
        rightPriceScale: {
          borderColor: 'rgba(30, 41, 59, 1)',
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
        timeScale: {
          borderColor: 'rgba(30, 41, 59, 1)',
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
        const gexPrimitive = new GexPrimitive();
        series.attachPrimitive(gexPrimitive);
        gexPrimitiveRef.current = gexPrimitive;

        const vpPrimitive = new VolumeProfilePrimitive();
        series.attachPrimitive(vpPrimitive);
        vpPrimitiveRef.current = vpPrimitive;
      } catch (err) {
        console.error('[GexChartPanel] Failed to attach primitives:', err);
      }

      setChartReady(true);
      chart.priceScale('right').applyOptions({ autoScale: true });

      const handleResize = () => {
        if (!containerRef.current || !chartRef.current) return;
      };

      window.addEventListener('resize', handleResize);
      (chartRef.current as any)._resizeHandler = handleResize;
    }, 400);

    return () => {
      clearTimeout(timer);
      if (chartRef.current) {
        const handler = (chartRef.current as any)._resizeHandler;
        if (handler) window.removeEventListener('resize', handler);
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
        gexPrimitiveRef.current = null;
        vpPrimitiveRef.current = null;
      }
    };
  }, [isOpen]);

  // Update candle data
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

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [candles, chartReady]);

  // Update GEX primitive when data or config changes
  useEffect(() => {
    if (!gexPrimitiveRef.current) return;

    const gexData: GexDataPoint[] = Object.entries(gexByStrike).map(([strike, values]) => ({
      strike: parseFloat(strike),
      calls: values.calls,
      puts: values.puts,
    }));

    const alpha = (100 - gexConfig.transparency) / 100;

    gexPrimitiveRef.current.setData(gexConfig.enabled ? gexData : []);
    gexPrimitiveRef.current.setOptions({
      mode: gexConfig.mode,
      maxGex,
      maxNetGex,
      currentSpot: gexConfig.showATM ? currentSpot : null,
      barHeight: gexConfig.barHeight,
      callColor: hexToRgba(gexConfig.callColor, alpha),
      putColor: hexToRgba(gexConfig.putColor, alpha),
      atmHighlightColor: hexToRgba(gexConfig.atmColor, 0.8),
      maxBarWidthPercent: gexConfig.widthPercent,
    });
  }, [gexByStrike, maxGex, maxNetGex, currentSpot, gexConfig]);

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

    // Step 2: Calculate volume profile using TradingView VRVP algorithm
    // numBins controls resolution: fewer bins = smoother, more bins = detailed
    const { levels: rebinnedLevels, maxVolume: rebinnedMax } = calculateVolumeProfile(
      cappedLevels,
      vpConfig.numBins
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
    });
  }, [volumeProfile, vpConfig]);


  return (
    <div className="gex-chart-panel">
      {/* Header with timeframe selector */}
      <div className="gex-chart-header">
        <h3>Dealer Gravity</h3>
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
      </div>

      {/* Loading indicator */}
      {loading && candles.length === 0 && (
        <div className="gex-chart-loading">Loading chart data...</div>
      )}

      {/* Chart Container */}
      <div className="gex-chart-area">
        <div ref={containerRef} className="gex-chart-container" />

        {/* Indicator Labels - Top Left inside chart */}
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

          {/* GEX */}
          <div
            className={`dg-indicator ${!gexConfig.enabled ? 'disabled' : ''}`}
            onDoubleClick={() => setShowGexSettings(true)}
            title="Double-click for settings"
          >
            <span className="dg-indicator-color-pair">
              <span style={{ backgroundColor: gexConfig.callColor }} />
              <span style={{ backgroundColor: gexConfig.putColor }} />
            </span>
            <span className="dg-indicator-name">GEX</span>
            <button
              className="dg-indicator-btn"
              onClick={() => setGexConfig(c => ({ ...c, enabled: !c.enabled }))}
              title={gexConfig.enabled ? 'Hide' : 'Show'}
            >
              {gexConfig.enabled ? (
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
              onClick={() => setShowGexSettings(true)}
              title="Settings"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
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

        {/* GEX Settings Dialog */}
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
      </div>

      {/* Footer legend - just candle count now */}
      <div className="gex-chart-legend">
        {candles.length > 0 && (
          <span className="legend-item candle-count">{candles.length} candles</span>
        )}
      </div>
    </div>
  );
}
