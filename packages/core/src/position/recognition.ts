/**
 * Position Recognition
 *
 * Analyzes a set of legs to determine the position type and direction.
 * Uses pattern matching based on TastyTrade/CBOE conventions.
 */

import type { PositionLeg, PositionType, PositionDirection } from './types.js';

/** Result of position type recognition */
export interface PositionRecognitionResult {
  /** Detected position type */
  type: PositionType;

  /** Net direction (long or short) */
  direction: PositionDirection;

  /** For butterfly/BWB distinction */
  isSymmetric?: boolean;
}

/**
 * Recognize position type from a set of legs
 *
 * Detection logic:
 * - 1 leg: single
 * - 2 legs, same exp + same type: vertical
 * - 2 legs, diff exp + same strike: calendar
 * - 2 legs, diff exp + diff strike: diagonal
 * - 2 legs, same exp + diff type + same strike: straddle
 * - 2 legs, same exp + diff type + diff strike: strangle
 * - 3 legs, 1-2-1 pattern, same exp + same type: butterfly (symmetric) or bwb (asymmetric)
 * - 4 legs, same type: condor
 * - 4 legs, mixed P+C, middle strikes same: iron_fly
 * - 4 legs, mixed P+C, all diff strikes: iron_condor
 */
export function recognizePositionType(legs: PositionLeg[]): PositionRecognitionResult {
  const n = legs.length;

  if (n === 0) {
    return { type: 'custom', direction: 'long' };
  }

  // Sort legs by strike for consistent analysis
  const sorted = [...legs].sort((a, b) => a.strike - b.strike);

  // Analyze structure
  const expirations = new Set(legs.map(l => l.expiration));
  const allSameExp = expirations.size === 1;
  const rights = new Set(legs.map(l => l.right));
  const allSameRight = rights.size === 1;

  // Get strikes and quantities with type safety
  const getStrike = (idx: number): number => sorted[idx]?.strike ?? 0;
  const getQty = (idx: number): number => sorted[idx]?.quantity ?? 0;

  // Singles
  if (n === 1) {
    return {
      type: 'single',
      direction: getQty(0) > 0 ? 'long' : 'short',
    };
  }

  // 2-leg structures
  if (n === 2) {
    const q0 = getQty(0);
    const s0 = getStrike(0);
    const s1 = getStrike(1);

    // Same expiration, same type (call or put)
    if (allSameExp && allSameRight) {
      return {
        type: 'vertical',
        direction: q0 > 0 ? 'long' : 'short',
      };
    }

    // Different expiration, same type
    if (!allSameExp && allSameRight) {
      if (s0 === s1) {
        // Calendar: same strike, different expirations
        const byExp = [...legs].sort((a, b) =>
          new Date(a.expiration).getTime() - new Date(b.expiration).getTime()
        );
        const farLeg = byExp[1];
        return {
          type: 'calendar',
          direction: farLeg && farLeg.quantity > 0 ? 'long' : 'short',
        };
      } else {
        // Diagonal: different strikes, different expirations
        const byExp = [...legs].sort((a, b) =>
          new Date(a.expiration).getTime() - new Date(b.expiration).getTime()
        );
        const farLeg = byExp[1];
        return {
          type: 'diagonal',
          direction: farLeg && farLeg.quantity > 0 ? 'long' : 'short',
        };
      }
    }

    // Same expiration, mixed types (call + put)
    if (allSameExp && !allSameRight) {
      if (s0 === s1) {
        return {
          type: 'straddle',
          direction: q0 > 0 ? 'long' : 'short',
        };
      } else {
        return {
          type: 'strangle',
          direction: q0 > 0 ? 'long' : 'short',
        };
      }
    }
  }

  // 3-leg structures (butterfly patterns: 1-2-1)
  if (n === 3 && allSameExp && allSameRight) {
    const q0 = getQty(0);
    const q1 = getQty(1);
    const q2 = getQty(2);
    const absQ0 = Math.abs(q0);
    const absQ1 = Math.abs(q1);
    const absQ2 = Math.abs(q2);

    const isButterfly = (
      absQ0 === 1 &&
      absQ1 === 2 &&
      absQ2 === 1 &&
      q0 * q2 > 0 &&  // Wings same sign
      q0 * q1 < 0      // Body opposite sign
    );

    if (isButterfly) {
      const s0 = getStrike(0);
      const s1 = getStrike(1);
      const s2 = getStrike(2);
      const lowerWidth = s1 - s0;
      const upperWidth = s2 - s1;
      const isSymmetric = Math.abs(lowerWidth - upperWidth) < 0.01;

      return {
        type: isSymmetric ? 'butterfly' : 'bwb',
        direction: q0 > 0 ? 'long' : 'short',
        isSymmetric,
      };
    }
  }

  // 4-leg structures
  if (n === 4 && allSameExp) {
    const q0 = getQty(0);
    const q1 = getQty(1);
    const q2 = getQty(2);
    const q3 = getQty(3);
    const absQ0 = Math.abs(q0);
    const absQ1 = Math.abs(q1);
    const absQ2 = Math.abs(q2);
    const absQ3 = Math.abs(q3);
    const allQtyOne = absQ0 === 1 && absQ1 === 1 && absQ2 === 1 && absQ3 === 1;

    // Condor: all same type, 1-1-1-1 structure
    if (allSameRight && allQtyOne) {
      const isCondor = (
        q0 * q3 > 0 &&  // Outer wings same sign
        q1 * q2 > 0 &&  // Inner body same sign
        q0 * q1 < 0      // Outer and inner opposite
      );
      if (isCondor) {
        return {
          type: 'condor',
          direction: q0 > 0 ? 'long' : 'short',
        };
      }
    }

    // Iron structures: mixed puts and calls
    if (!allSameRight && allQtyOne) {
      const puts = sorted.filter(l => l.right === 'put');
      const calls = sorted.filter(l => l.right === 'call');

      if (puts.length === 2 && calls.length === 2) {
        const putStrikes = puts.map(l => l.strike).sort((a, b) => a - b);
        const callStrikes = calls.map(l => l.strike).sort((a, b) => a - b);
        const putHigh = putStrikes[1] ?? 0;
        const callLow = callStrikes[0] ?? 0;

        // Iron Fly: middle strikes are the same
        if (Math.abs(putHigh - callLow) < 0.01) {
          const longWingPut = puts.find(p => p.strike === putStrikes[0]);
          return {
            type: 'iron_fly',
            direction: longWingPut && longWingPut.quantity > 0 ? 'long' : 'short',
          };
        } else {
          // Iron Condor: all different strikes
          const longWingPut = puts.find(p => p.strike === putStrikes[0]);
          return {
            type: 'iron_condor',
            direction: longWingPut && longWingPut.quantity > 0 ? 'long' : 'short',
          };
        }
      }
    }
  }

  // Unrecognized structure
  return { type: 'custom', direction: 'long' };
}

/**
 * Convert legacy strategy format (strike/width) to legs
 */
export function strategyToLegs(
  strategy: 'single' | 'vertical' | 'butterfly',
  side: 'call' | 'put',
  strike: number,
  width: number,
  expiration: string
): PositionLeg[] {
  switch (strategy) {
    case 'single':
      return [{
        strike,
        expiration,
        right: side,
        quantity: 1,
      }];

    case 'vertical':
      if (side === 'call') {
        // Bull call spread: long lower, short higher
        return [
          { strike, expiration, right: 'call', quantity: 1 },
          { strike: strike + width, expiration, right: 'call', quantity: -1 },
        ];
      } else {
        // Bear put spread: long higher, short lower
        return [
          { strike: strike - width, expiration, right: 'put', quantity: -1 },
          { strike, expiration, right: 'put', quantity: 1 },
        ];
      }

    case 'butterfly':
      return [
        { strike: strike - width, expiration, right: side, quantity: 1 },
        { strike, expiration, right: side, quantity: -2 },
        { strike: strike + width, expiration, right: side, quantity: 1 },
      ];

    default:
      return [];
  }
}

/**
 * Derive center strike from legs (for legacy compatibility)
 */
export function getCenterStrike(legs: PositionLeg[]): number {
  if (legs.length === 0) return 0;

  const sorted = [...legs].sort((a, b) => a.strike - b.strike);

  // For 3-leg butterflies, middle strike is the center
  if (legs.length === 3) {
    return sorted[1]?.strike ?? 0;
  }

  // For 4-leg iron condors, return average of inner strikes
  if (legs.length === 4) {
    const s1 = sorted[1]?.strike ?? 0;
    const s2 = sorted[2]?.strike ?? 0;
    return (s1 + s2) / 2;
  }

  // For 2-leg structures, return average
  if (legs.length === 2) {
    const s0 = sorted[0]?.strike ?? 0;
    const s1 = sorted[1]?.strike ?? 0;
    return (s0 + s1) / 2;
  }

  // Single leg
  return sorted[0]?.strike ?? 0;
}

/**
 * Derive width from legs (for symmetric structures)
 */
export function getWidth(legs: PositionLeg[]): number | null {
  if (legs.length < 2) return null;

  const sorted = [...legs].sort((a, b) => a.strike - b.strike);

  // For butterflies (3 legs), width is distance from center to wing
  if (legs.length === 3) {
    const s0 = sorted[0]?.strike ?? 0;
    const s1 = sorted[1]?.strike ?? 0;
    const s2 = sorted[2]?.strike ?? 0;
    const lowerWidth = s1 - s0;
    const upperWidth = s2 - s1;
    return Math.abs(lowerWidth - upperWidth) < 0.01 ? lowerWidth : null;
  }

  // For verticals (2 legs), width is strike difference
  if (legs.length === 2) {
    const s0 = sorted[0]?.strike ?? 0;
    const s1 = sorted[1]?.strike ?? 0;
    return s1 - s0;
  }

  // For 4-leg structures, return outer wing width
  if (legs.length === 4) {
    const s0 = sorted[0]?.strike ?? 0;
    const s1 = sorted[1]?.strike ?? 0;
    return s1 - s0;
  }

  return null;
}

/**
 * Get primary (earliest) expiration from legs
 */
export function getPrimaryExpiration(legs: PositionLeg[]): string {
  if (legs.length === 0) return '';

  const expirations = legs.map(l => l.expiration);
  expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
  return expirations[0] ?? '';
}

/**
 * Get dominant side (call or put) from legs
 */
export function getDominantSide(legs: PositionLeg[]): 'call' | 'put' {
  const calls = legs.filter(l => l.right === 'call').length;
  const puts = legs.filter(l => l.right === 'put').length;
  return calls >= puts ? 'call' : 'put';
}

/**
 * Check if all legs have the same expiration
 */
export function hasSameExpiration(legs: PositionLeg[]): boolean {
  if (legs.length <= 1) return true;
  const first = legs[0];
  if (!first) return true;
  const exp = first.expiration;
  return legs.every(l => l.expiration === exp);
}

/**
 * Check if all legs have the same option type (all calls or all puts)
 */
export function hasSameRight(legs: PositionLeg[]): boolean {
  if (legs.length <= 1) return true;
  const first = legs[0];
  if (!first) return true;
  const right = first.right;
  return legs.every(l => l.right === right);
}
