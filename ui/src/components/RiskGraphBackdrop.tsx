/**
 * RiskGraphBackdrop - Dealer Gravity visualization backdrop for Risk Graph
 *
 * Renders Volume Profile, GEX, and structural overlays BEHIND the Risk Graph.
 *
 * Architectural Rules (Non-Negotiable):
 *   - Renders BEHIND all Risk Graph elements (z-index)
 *   - Shares EXACT same price scale as Risk Graph
 *   - Resizes and zooms in perfect sync
 *   - Never introduces independent axes or layout logic
 *   - Risk Graph remains visually dominant
 *
 * Dealer Gravity Lexicon:
 *   - Volume Node: Concentrated attention (yellow lines)
 *   - Volume Well: Neglect (purple lines)
 *   - Crevasse: Extended scarcity region (red zones)
 *   - Market Memory: Persistent topology
 */

import { useMemo } from 'react';
import { useDealerGravity } from '../contexts/DealerGravityContext';
import type { DGStructures, DGProfile } from '../types/dealerGravity';

interface RiskGraphBackdropProps {
  /** Chart container dimensions */
  width: number;
  height: number;

  /** Price range from Risk Graph (must match exactly) */
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
}

/**
 * Convert price to Y coordinate
 */
function priceToY(
  price: number,
  priceMin: number,
  priceMax: number,
  height: number
): number {
  const range = priceMax - priceMin;
  if (range <= 0) return height / 2;
  return height - ((price - priceMin) / range) * height;
}

/**
 * Volume Profile Backdrop
 * Renders horizontal bars showing volume distribution
 */
function VolumeProfileLayer({
  profile,
  width,
  height,
  priceMin,
  priceMax,
  opacity = 0.3,
  color = '#9333ea',
  widthPercent = 15,
}: {
  profile: DGProfile;
  width: number;
  height: number;
  priceMin: number;
  priceMax: number;
  opacity?: number;
  color?: string;
  widthPercent?: number;
}) {
  const bars = useMemo(() => {
    if (!profile?.bins?.length) return [];

    const maxWidth = (width * widthPercent) / 100;
    const maxVol = Math.max(...profile.bins.filter(v => v > 0));
    if (maxVol === 0) return [];

    const result: { y: number; barWidth: number; barHeight: number }[] = [];
    const priceRange = priceMax - priceMin;

    for (let i = 0; i < profile.bins.length; i++) {
      const vol = profile.bins[i];
      if (vol === 0) continue;

      const price = profile.min + i * profile.step;

      // Skip if outside visible range
      if (price < priceMin || price > priceMax) continue;

      const y = priceToY(price, priceMin, priceMax, height);
      const barWidth = (vol / maxVol) * maxWidth;
      const barHeight = Math.max(1, (profile.step / priceRange) * height);

      result.push({ y, barWidth, barHeight });
    }

    return result;
  }, [profile, width, height, priceMin, priceMax, widthPercent]);

  return (
    <g className="volume-profile-layer" opacity={opacity}>
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={0}
          y={bar.y - bar.barHeight / 2}
          width={bar.barWidth}
          height={bar.barHeight}
          fill={color}
        />
      ))}
    </g>
  );
}

/**
 * Structural Lines Layer
 * Renders Volume Nodes, Volume Wells, and Crevasses
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
      y: number;
      y2?: number;
    }[] = [];

    // Volume Nodes (yellow - concentrated attention)
    for (const price of structures.volumeNodes) {
      if (price >= priceMin && price <= priceMax) {
        result.push({ type: 'node', y: priceToY(price, priceMin, priceMax, height) });
      }
    }

    // Volume Wells (purple - neglect)
    for (const price of structures.volumeWells) {
      if (price >= priceMin && price <= priceMax) {
        result.push({ type: 'well', y: priceToY(price, priceMin, priceMax, height) });
      }
    }

    // Crevasses (red zones - extended scarcity)
    for (const [start, end] of structures.crevasses) {
      if (end >= priceMin && start <= priceMax) {
        const clampedStart = Math.max(start, priceMin);
        const clampedEnd = Math.min(end, priceMax);
        result.push({
          type: 'crevasse',
          y: priceToY(clampedEnd, priceMin, priceMax, height),
          y2: priceToY(clampedStart, priceMin, priceMax, height),
        });
      }
    }

    return result;
  }, [structures, height, priceMin, priceMax]);

  const colors = {
    node: '#facc15',    // Yellow - concentrated attention
    well: '#9333ea',    // Purple - neglect
    crevasse: '#ef4444', // Red - structural void
  };

  return (
    <g className="structural-lines-layer" opacity={opacity}>
      {lines.map((line, i) => {
        if (line.type === 'crevasse' && line.y2 !== undefined) {
          // Crevasse zone (filled rectangle)
          return (
            <rect
              key={i}
              x={0}
              y={Math.min(line.y, line.y2)}
              width={width}
              height={Math.abs(line.y2 - line.y)}
              fill={colors.crevasse}
              opacity={0.15}
            />
          );
        }

        // Node or Well line
        return (
          <line
            key={i}
            x1={0}
            y1={line.y}
            x2={width}
            y2={line.y}
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
 * Main RiskGraphBackdrop Component
 *
 * Renders as an SVG layer that sits behind the Risk Graph chart.
 * Must be positioned absolutely within the chart container.
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
      {/* Volume Profile Layer */}
      {showVolumeProfile && profile && (
        <VolumeProfileLayer
          profile={profile}
          width={width}
          height={height}
          priceMin={priceMin}
          priceMax={priceMax}
          opacity={effectiveOpacity}
          color={config?.color ?? '#9333ea'}
          widthPercent={config?.widthPercent ?? 15}
        />
      )}

      {/* GEX Layer (placeholder - requires GEX data integration) */}
      {showGex && (
        <g className="gex-layer" opacity={effectiveOpacity}>
          {/* GEX visualization will be implemented when GEX data is integrated */}
        </g>
      )}

      {/* Structural Lines Layer */}
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
