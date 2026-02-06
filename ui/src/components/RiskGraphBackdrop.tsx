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

  /** Height percentage for volume bars (from bottom) */
  volumeHeightPercent?: number;
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
}: {
  profile: DGProfile;
  width: number;
  height: number;
  priceMin: number;
  priceMax: number;
  opacity?: number;
  color?: string;
  heightPercent?: number;
}) {
  const bars = useMemo(() => {
    if (!profile?.bins?.length) return [];

    // Max height for bars (percentage of chart height, from bottom)
    const maxBarHeight = (height * heightPercent) / 100;
    const maxVol = Math.max(...profile.bins.filter(v => v > 0));
    if (maxVol === 0) return [];

    const result: { x: number; barWidth: number; barHeight: number }[] = [];
    const priceRange = priceMax - priceMin;

    for (let i = 0; i < profile.bins.length; i++) {
      const vol = profile.bins[i];
      if (vol === 0) continue;

      const price = profile.min + i * profile.step;

      // Skip if outside visible range
      if (price < priceMin || price > priceMax) continue;

      // X position based on price (landscape: price on X-axis)
      const x = priceToX(price, priceMin, priceMax, width);

      // Bar width based on price step
      const barWidth = Math.max(1, (profile.step / priceRange) * width);

      // Bar height based on volume (extends upward from bottom)
      const barHeight = (vol / maxVol) * maxBarHeight;

      result.push({ x, barWidth, barHeight });
    }

    return result;
  }, [profile, width, height, priceMin, priceMax, heightPercent]);

  return (
    <g className="volume-profile-layer" opacity={opacity}>
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={bar.x - bar.barWidth / 2}
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
}: RiskGraphBackdropProps) {
  const { artifact, config } = useDealerGravity();

  // Early return if nothing to show
  if (!artifact) return null;
  if (!showVolumeProfile && !showGex && !showStructuralLines) return null;

  const { profile, structures } = artifact;
  const effectiveOpacity = opacity * (config?.transparency ?? 50) / 100;

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
      {showVolumeProfile && profile && (
        <VolumeProfileLayer
          profile={profile}
          width={width}
          height={height}
          priceMin={priceMin}
          priceMax={priceMax}
          opacity={effectiveOpacity}
          color={config?.color ?? '#9333ea'}
          heightPercent={volumeHeightPercent}
        />
      )}

      {/* GEX Layer (placeholder - requires GEX data integration) */}
      {showGex && (
        <g className="gex-layer" opacity={effectiveOpacity}>
          {/* GEX visualization will be implemented when GEX data is integrated */}
        </g>
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
