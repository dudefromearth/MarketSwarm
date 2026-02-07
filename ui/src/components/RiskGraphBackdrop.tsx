/**
 * RiskGraphBackdrop - Dealer Gravity visualization backdrop for Risk Graph
 *
 * LANDSCAPE ORIENTATION: Risk Graph has price on X-axis, P&L on Y-axis.
 * Volume Profile bars extend VERTICALLY from the bottom edge.
 * Structural lines are VERTICAL at specific price levels.
 *
 * Architectural Rules (Non-Negotiable):
 *   - Renders BEHIND all Risk Graph elements (z-index)
 *   - Shares EXACT same price scale as Risk Graph (X-axis)
 *   - Resizes and zooms in perfect sync
 *   - Never introduces independent axes or layout logic
 *   - Risk Graph remains visually dominant
 *
 * Dealer Gravity Lexicon:
 *   - Volume Node: Concentrated attention (yellow vertical lines)
 *   - Volume Well: Neglect (purple vertical lines)
 *   - Crevasse: Extended scarcity region (red vertical zones)
 *   - Market Memory: Persistent topology
 */

import { useMemo } from 'react';
import { useDealerGravity } from '../contexts/DealerGravityContext';
import type { DGStructures, DGProfile } from '../types/dealerGravity';

/** GEX data by strike price */
export interface GexByStrike {
  [strike: number]: { calls: number; puts: number };
}

/** GEX display configuration (from indicator settings) */
export interface GexBackdropConfig {
  callColor: string;
  putColor: string;
  mode: 'combined' | 'net';
  barHeight: number;  // Controls max bar height
}

/** VP display configuration (from indicator settings) */
export interface VPBackdropConfig {
  color: string;
  widthPercent: number;  // Controls VP bar max width
  rowsLayout: 'number_of_rows' | 'ticks_per_row';
  rowSize: number;
  transparency: number;
}

interface RiskGraphBackdropProps {
  /** Chart container dimensions */
  width: number;
  height: number;

  /** Price range from Risk Graph X-axis (must match exactly) */
  priceMin: number;
  priceMax: number;

  /** Optional spot price for reference line */
  spotPrice?: number;

  /** Toggle controls */
  showVolumeProfile?: boolean;
  showGex?: boolean;
  showStructuralLines?: boolean;

  /** Opacity (0-1) */
  opacity?: number;

  /** Height percentage for volume bars (from bottom) - DEPRECATED, use vpConfig */
  volumeHeightPercent?: number;

  /** GEX data for backdrop (from App.tsx) */
  gexByStrike?: GexByStrike;

  /** GEX display config (from indicator settings) */
  gexConfig?: GexBackdropConfig;

  /** VP display config (from indicator settings) */
  vpConfig?: VPBackdropConfig;
}

/**
 * Convert price to X coordinate (LANDSCAPE orientation)
 * Price axis is horizontal in Risk Graph
 */
function priceToX(
  price: number,
  priceMin: number,
  priceMax: number,
  width: number
): number {
  const range = priceMax - priceMin;
  if (range <= 0) return width / 2;
  return ((price - priceMin) / range) * width;
}

/**
 * Volume Profile Backdrop (LANDSCAPE)
 * Renders VERTICAL bars from the BOTTOM edge showing volume distribution.
 * Price is on X-axis, bar height represents volume.
 *
 * Supports TradingView-style binning:
 * - number_of_rows: Fixed count of rows across visible range
 * - ticks_per_row: Fixed tick size per row
 *
 * IMPORTANT: Bars are rendered edge-to-edge with MAXIMAL thickness.
 * No gaps between adjacent bars - each bar fills its entire allocated space.
 */
function VolumeProfileLayer({
  profile,
  width,
  height,
  priceMin,
  priceMax,
  opacity = 0.3,
  color = '#9333ea',
  heightPercent = 25,
  rowsLayout = 'number_of_rows',
  rowSize = 24,
}: {
  profile: DGProfile;
  width: number;
  height: number;
  priceMin: number;
  priceMax: number;
  opacity?: number;
  color?: string;
  heightPercent?: number;
  rowsLayout?: 'number_of_rows' | 'ticks_per_row';
  rowSize?: number;
}) {
  const bars = useMemo(() => {
    if (!profile?.bins?.length) return [];

    const priceRange = priceMax - priceMin;
    if (priceRange <= 0) return [];

    // Calculate number of display bins and exact pixel width per bin
    let numDisplayBins: number;
    if (rowsLayout === 'number_of_rows') {
      // Fixed number of rows across visible range
      numDisplayBins = Math.max(1, rowSize);
    } else {
      // Fixed ticks per row - calculate how many bins fit
      const ticksPerRow = Math.max(1, rowSize);
      numDisplayBins = Math.ceil(priceRange / ticksPerRow);
    }

    // Each bin gets exactly this many pixels (MAXIMAL thickness, edge-to-edge)
    const pixelWidthPerBin = width / numDisplayBins;
    const priceWidthPerBin = priceRange / numDisplayBins;

    // Aggregate raw profile data into display bins
    const displayBins: number[] = new Array(numDisplayBins).fill(0);

    // Aggregate source data into display bins
    for (let i = 0; i < profile.bins.length; i++) {
      const vol = profile.bins[i];
      if (vol === 0) continue;

      const price = profile.min + i * profile.step;
      if (price < priceMin || price > priceMax) continue;

      // Find which display bin this price falls into
      const binIndex = Math.min(
        numDisplayBins - 1,
        Math.floor((price - priceMin) / priceWidthPerBin)
      );
      if (binIndex >= 0) {
        displayBins[binIndex] += vol;
      }
    }

    // Find max volume for normalization
    const maxVol = Math.max(...displayBins);
    if (maxVol === 0) return [];

    // Max height for bars (percentage of chart height, from bottom)
    const maxBarHeight = (height * heightPercent) / 100;

    // Convert to render-ready bars - positioned edge-to-edge
    const result: { x: number; barWidth: number; barHeight: number }[] = [];
    for (let i = 0; i < numDisplayBins; i++) {
      const volume = displayBins[i];
      if (volume === 0) continue;

      // X position is the LEFT edge of this bin (not center)
      const x = i * pixelWidthPerBin;
      // Width fills entire bin space (edge-to-edge, no gaps)
      const barWidth = pixelWidthPerBin;
      // Height based on volume
      const barHeight = (volume / maxVol) * maxBarHeight;

      result.push({ x, barWidth, barHeight });
    }

    return result;
  }, [profile, width, height, priceMin, priceMax, heightPercent, rowsLayout, rowSize]);

  return (
    <g className="volume-profile-layer" opacity={opacity}>
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={bar.x}
          y={height - bar.barHeight}
          width={bar.barWidth}
          height={bar.barHeight}
          fill={color}
        />
      ))}
    </g>
  );
}

/**
 * GEX Layer (LANDSCAPE)
 * Renders VERTICAL bars at each strike showing GEX values.
 * Price is on X-axis, bar height represents GEX magnitude.
 * Calls extend UP from center, Puts extend DOWN from center.
 */
function GexLayer({
  gexByStrike,
  width,
  height,
  priceMin,
  priceMax,
  opacity = 0.4,
  callColor = '#22c55e',
  putColor = '#ef4444',
  mode = 'combined',
  heightPercent = 40,
}: {
  gexByStrike: GexByStrike;
  width: number;
  height: number;
  priceMin: number;
  priceMax: number;
  opacity?: number;
  callColor?: string;
  putColor?: string;
  mode?: 'combined' | 'net';
  heightPercent?: number;
}) {
  const bars = useMemo(() => {
    const entries = Object.entries(gexByStrike);
    if (entries.length === 0) return [];

    const priceRange = priceMax - priceMin;
    if (priceRange <= 0) return [];

    // Find max GEX for normalization
    let maxGex = 0;
    for (const [, { calls, puts }] of entries) {
      maxGex = Math.max(maxGex, Math.abs(calls), Math.abs(puts));
    }
    if (maxGex === 0) return [];

    // GEX bars extend from the vertical center
    const centerY = height / 2;
    const maxBarHeight = height * (heightPercent / 100); // Max % of height each direction

    // Calculate bar width based on strike density
    const strikes = entries.map(([s]) => parseFloat(s)).sort((a, b) => a - b);
    const strikeSpacing = strikes.length > 1
      ? Math.min(...strikes.slice(1).map((s, i) => s - strikes[i]))
      : 5;
    const barWidth = Math.max(1, (strikeSpacing / priceRange) * width * 0.8);

    const result: {
      x: number;
      callHeight: number;
      putHeight: number;
      barWidth: number;
    }[] = [];

    for (const [strikeStr, { calls, puts }] of entries) {
      const strike = parseFloat(strikeStr);
      if (strike < priceMin || strike > priceMax) continue;

      const x = priceToX(strike, priceMin, priceMax, width) - barWidth / 2;

      if (mode === 'net') {
        // Net mode: single bar showing net GEX
        const net = calls - puts;
        result.push({
          x,
          callHeight: net > 0 ? (net / maxGex) * maxBarHeight : 0,
          putHeight: net < 0 ? (Math.abs(net) / maxGex) * maxBarHeight : 0,
          barWidth,
        });
      } else {
        // Combined mode: separate call and put bars
        result.push({
          x,
          callHeight: (Math.abs(calls) / maxGex) * maxBarHeight,
          putHeight: (Math.abs(puts) / maxGex) * maxBarHeight,
          barWidth,
        });
      }
    }

    return result;
  }, [gexByStrike, width, height, priceMin, priceMax, mode, heightPercent]);

  const centerY = height / 2;

  return (
    <g className="gex-layer" opacity={opacity}>
      {bars.map((bar, i) => (
        <g key={i}>
          {/* Call bar - extends UP from center */}
          {bar.callHeight > 0 && (
            <rect
              x={bar.x}
              y={centerY - bar.callHeight}
              width={bar.barWidth}
              height={bar.callHeight}
              fill={callColor}
            />
          )}
          {/* Put bar - extends DOWN from center */}
          {bar.putHeight > 0 && (
            <rect
              x={bar.x}
              y={centerY}
              width={bar.barWidth}
              height={bar.putHeight}
              fill={putColor}
            />
          )}
        </g>
      ))}
    </g>
  );
}

/**
 * Structural Lines Layer (LANDSCAPE)
 * Renders VERTICAL lines for Volume Nodes, Volume Wells, and Crevasses.
 * Price is on X-axis, so structural levels are vertical lines.
 */
function StructuralLinesLayer({
  structures,
  width,
  height,
  priceMin,
  priceMax,
  opacity = 0.6,
}: {
  structures: DGStructures;
  width: number;
  height: number;
  priceMin: number;
  priceMax: number;
  opacity?: number;
}) {
  const lines = useMemo(() => {
    const result: {
      type: 'node' | 'well' | 'crevasse';
      x: number;
      x2?: number;
    }[] = [];

    // Volume Nodes (yellow - concentrated attention) - vertical lines
    for (const price of structures.volumeNodes) {
      if (price >= priceMin && price <= priceMax) {
        result.push({ type: 'node', x: priceToX(price, priceMin, priceMax, width) });
      }
    }

    // Volume Wells (purple - neglect) - vertical lines
    for (const price of structures.volumeWells) {
      if (price >= priceMin && price <= priceMax) {
        result.push({ type: 'well', x: priceToX(price, priceMin, priceMax, width) });
      }
    }

    // Crevasses (red zones - extended scarcity) - vertical bands
    for (const [start, end] of structures.crevasses) {
      if (end >= priceMin && start <= priceMax) {
        const clampedStart = Math.max(start, priceMin);
        const clampedEnd = Math.min(end, priceMax);
        result.push({
          type: 'crevasse',
          x: priceToX(clampedStart, priceMin, priceMax, width),
          x2: priceToX(clampedEnd, priceMin, priceMax, width),
        });
      }
    }

    return result;
  }, [structures, width, priceMin, priceMax]);

  const colors = {
    node: '#facc15',    // Yellow - concentrated attention
    well: '#9333ea',    // Purple - neglect
    crevasse: '#ef4444', // Red - structural void
  };

  return (
    <g className="structural-lines-layer" opacity={opacity}>
      {lines.map((line, i) => {
        if (line.type === 'crevasse' && line.x2 !== undefined) {
          // Crevasse zone (vertical filled rectangle spanning full height)
          return (
            <rect
              key={i}
              x={Math.min(line.x, line.x2)}
              y={0}
              width={Math.abs(line.x2 - line.x)}
              height={height}
              fill={colors.crevasse}
              opacity={0.15}
            />
          );
        }

        // Node or Well - vertical line spanning full height
        return (
          <line
            key={i}
            x1={line.x}
            y1={0}
            x2={line.x}
            y2={height}
            stroke={colors[line.type]}
            strokeWidth={line.type === 'node' ? 2 : 1}
            strokeDasharray={line.type === 'well' ? '4,4' : undefined}
          />
        );
      })}
    </g>
  );
}

/**
 * Main RiskGraphBackdrop Component (LANDSCAPE)
 *
 * Renders as an SVG layer that sits behind the Risk Graph chart.
 * Must be positioned absolutely within the chart container.
 *
 * ORIENTATION: Price on X-axis (horizontal), P&L on Y-axis (vertical)
 * - Volume Profile: Vertical bars from bottom edge
 * - Structural Lines: Vertical lines at price levels
 * - Crevasses: Vertical bands spanning full height
 */
export default function RiskGraphBackdrop({
  width,
  height,
  priceMin,
  priceMax,
  showVolumeProfile = true,
  showGex = false,
  showStructuralLines = true,
  opacity = 0.5,
  volumeHeightPercent = 25,
  gexByStrike,
  gexConfig,
  vpConfig,
}: RiskGraphBackdropProps) {
  const { artifact, config } = useDealerGravity();

  // Debug logging
  console.log('[RiskGraphBackdrop] State:', {
    hasArtifact: !!artifact,
    hasProfile: !!artifact?.profile,
    profileBins: artifact?.profile?.bins?.length,
    profileMin: artifact?.profile?.min,
    profileStep: artifact?.profile?.step,
    priceRange: [priceMin, priceMax],
    showVolumeProfile,
    showGex,
  });

  // Early return if nothing to show
  const hasVPData = artifact?.profile;
  const hasGexData = gexByStrike && Object.keys(gexByStrike).length > 0;
  const hasStructures = artifact?.structures;

  if (!hasVPData && !hasGexData && !hasStructures) return null;
  if (!showVolumeProfile && !showGex && !showStructuralLines) return null;

  const { profile, structures } = artifact || {};

  // Use vpConfig if provided, otherwise fall back to context config
  const effectiveVPConfig = vpConfig || config;
  const effectiveOpacity = opacity * (effectiveVPConfig?.transparency ?? 50) / 100;

  // VP heightPercent: in landscape, VP bars extend vertically from bottom
  // widthPercent setting controls how high the bars extend (as % of chart height)
  const vpHeightPercent = vpConfig?.widthPercent ?? volumeHeightPercent;

  // GEX heightPercent: barHeight setting controls max bar extent (as % of chart height)
  // barHeight is in pixels in GEX settings, but we'll use it as a percentage here
  const gexHeightPercent = gexConfig?.barHeight ? Math.min(50, gexConfig.barHeight / 8) : 40;

  return (
    <svg
      className="risk-graph-backdrop"
      width={width}
      height={height}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        pointerEvents: 'none',
        zIndex: 0, // Behind chart elements
      }}
    >
      {/* Volume Profile Layer - vertical bars from bottom */}
      {showVolumeProfile && profile && (() => {
        console.log('[RiskGraphBackdrop] Rendering VP layer:', {
          binsLength: profile.bins?.length,
          priceRange: [priceMin, priceMax],
          profileRange: [profile.min, profile.min + profile.bins.length * profile.step],
          vpHeightPercent,
          opacity,
        });
        return (
          <VolumeProfileLayer
            profile={profile}
            width={width}
            height={height}
            priceMin={priceMin}
            priceMax={priceMax}
            opacity={opacity}
            color={vpConfig?.color ?? config?.color ?? '#9333ea'}
            heightPercent={vpHeightPercent}
            rowsLayout={vpConfig?.rowsLayout ?? config?.rowsLayout ?? 'number_of_rows'}
            rowSize={vpConfig?.rowSize ?? config?.rowSize ?? 24}
          />
        );
      })()}

      {/* GEX Layer - vertical bars at strike prices */}
      {showGex && hasGexData && (
        <GexLayer
          gexByStrike={gexByStrike!}
          width={width}
          height={height}
          priceMin={priceMin}
          priceMax={priceMax}
          opacity={opacity}
          callColor={gexConfig?.callColor ?? '#22c55e'}
          putColor={gexConfig?.putColor ?? '#ef4444'}
          mode={gexConfig?.mode ?? 'combined'}
          heightPercent={gexHeightPercent}
        />
      )}

      {/* Structural Lines Layer - vertical lines at price levels */}
      {showStructuralLines && structures && (
        <StructuralLinesLayer
          structures={structures}
          width={width}
          height={height}
          priceMin={priceMin}
          priceMax={priceMax}
          opacity={effectiveOpacity}
        />
      )}
    </svg>
  );
}
