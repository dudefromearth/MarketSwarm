/**
 * useRiskGraphCalculations - Hook for calculating options P&L curves
 *
 * Reusable hook that computes:
 * - Expiration P&L curve
 * - Theoretical (real-time) P&L curve using Black-Scholes
 * - Breakeven points
 * - Price range based on strategies and VIX
 */

import { useMemo } from 'react';

// Types
export interface Strategy {
  id: string;
  strike: number;
  width: number;
  side: 'call' | 'put';
  strategy: 'butterfly' | 'vertical' | 'single';
  debit: number | null;
  visible: boolean;
  dte?: number;
  expiration?: string;
}

export interface PnLPoint {
  price: number;
  pnl: number;
}

export interface RiskGraphData {
  // P&L curves
  expirationPoints: PnLPoint[];
  theoreticalPoints: PnLPoint[];

  // Price range
  minPrice: number;
  maxPrice: number;
  fullMinPrice: number;
  fullMaxPrice: number;

  // P&L range (for visible area)
  minPnL: number;
  maxPnL: number;

  // Breakeven prices
  expirationBreakevens: number[];
  theoreticalBreakevens: number[];

  // Current P&L at spot
  theoreticalPnLAtSpot: number;

  // Strategy info
  allStrikes: number[];
  centerPrice: number;
}

interface UseRiskGraphCalculationsProps {
  strategies: Strategy[];
  spotPrice: number;
  vix: number;
  timeMachineEnabled?: boolean;
  simVolatilityOffset?: number;
  simTimeOffsetHours?: number;
  panOffset?: number;
}

// Black-Scholes helper functions
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
  const y = 1.0 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);

  return 0.5 * (1.0 + sign * y);
}

function blackScholesCall(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0) return Math.max(0, S - K);
  if (sigma <= 0) return Math.max(0, S - K);

  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);

  return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);
}

function blackScholesPut(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0) return Math.max(0, K - S);
  if (sigma <= 0) return Math.max(0, K - S);

  const d1 = (Math.log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);

  return K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);
}

// Calculate expiration P&L for a strategy at a given price
function calculateExpirationPnL(strategy: Strategy, price: number): number {
  const debit = strategy.debit || 0;
  const multiplier = 100;

  if (strategy.strategy === 'single') {
    if (strategy.side === 'call') {
      const intrinsic = Math.max(0, price - strategy.strike);
      return (intrinsic - debit) * multiplier;
    } else {
      const intrinsic = Math.max(0, strategy.strike - price);
      return (intrinsic - debit) * multiplier;
    }
  }

  if (strategy.strategy === 'vertical') {
    if (strategy.side === 'call') {
      const longValue = Math.max(0, price - strategy.strike);
      const shortValue = Math.max(0, price - (strategy.strike + strategy.width));
      return (longValue - shortValue - debit) * multiplier;
    } else {
      const longValue = Math.max(0, strategy.strike - price);
      const shortValue = Math.max(0, (strategy.strike - strategy.width) - price);
      return (longValue - shortValue - debit) * multiplier;
    }
  }

  if (strategy.strategy === 'butterfly') {
    const lowerStrike = strategy.strike - strategy.width;
    const middleStrike = strategy.strike;
    const upperStrike = strategy.strike + strategy.width;

    if (strategy.side === 'call') {
      const lowerValue = Math.max(0, price - lowerStrike);
      const middleValue = Math.max(0, price - middleStrike);
      const upperValue = Math.max(0, price - upperStrike);
      return (lowerValue - 2 * middleValue + upperValue - debit) * multiplier;
    } else {
      const lowerValue = Math.max(0, lowerStrike - price);
      const middleValue = Math.max(0, middleStrike - price);
      const upperValue = Math.max(0, upperStrike - price);
      return (upperValue - 2 * middleValue + lowerValue - debit) * multiplier;
    }
  }

  return 0;
}

// Calculate theoretical P&L using Black-Scholes
function calculateTheoreticalPnL(
  strategy: Strategy,
  price: number,
  volatility: number,
  rate: number,
  timeOffsetHours: number
): number {
  const debit = strategy.debit || 0;
  const multiplier = 100;

  // Calculate time to expiration in years
  // Assume DTE is in days, convert to years, then subtract time offset
  const dte = strategy.dte || 0;
  const daysRemaining = Math.max(0, dte - timeOffsetHours / 24);
  const T = daysRemaining / 365;

  const bsCall = (K: number) => blackScholesCall(price, K, T, rate, volatility);
  const bsPut = (K: number) => blackScholesPut(price, K, T, rate, volatility);

  if (strategy.strategy === 'single') {
    if (strategy.side === 'call') {
      return (bsCall(strategy.strike) - debit) * multiplier;
    } else {
      return (bsPut(strategy.strike) - debit) * multiplier;
    }
  }

  if (strategy.strategy === 'vertical') {
    if (strategy.side === 'call') {
      const longValue = bsCall(strategy.strike);
      const shortValue = bsCall(strategy.strike + strategy.width);
      return (longValue - shortValue - debit) * multiplier;
    } else {
      const longValue = bsPut(strategy.strike);
      const shortValue = bsPut(strategy.strike - strategy.width);
      return (longValue - shortValue - debit) * multiplier;
    }
  }

  if (strategy.strategy === 'butterfly') {
    const lowerStrike = strategy.strike - strategy.width;
    const middleStrike = strategy.strike;
    const upperStrike = strategy.strike + strategy.width;

    if (strategy.side === 'call') {
      const lowerValue = bsCall(lowerStrike);
      const middleValue = bsCall(middleStrike);
      const upperValue = bsCall(upperStrike);
      return (lowerValue - 2 * middleValue + upperValue - debit) * multiplier;
    } else {
      const lowerValue = bsPut(lowerStrike);
      const middleValue = bsPut(middleStrike);
      const upperValue = bsPut(upperStrike);
      return (upperValue - 2 * middleValue + lowerValue - debit) * multiplier;
    }
  }

  return 0;
}

// Find breakeven points in a P&L curve
function findBreakevens(points: PnLPoint[]): number[] {
  const breakevens: number[] = [];

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];

    if ((prev.pnl < 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl < 0)) {
      // Linear interpolation to find exact crossing
      const t = -prev.pnl / (curr.pnl - prev.pnl);
      const bePrice = prev.price + t * (curr.price - prev.price);
      breakevens.push(bePrice);
    }
  }

  return breakevens;
}

export function useRiskGraphCalculations({
  strategies,
  spotPrice,
  vix,
  timeMachineEnabled = false,
  simVolatilityOffset = 0,
  simTimeOffsetHours = 0,
  panOffset = 0,
}: UseRiskGraphCalculationsProps): RiskGraphData {
  return useMemo(() => {
    const visibleStrategies = strategies.filter(s => s.visible);

    // Empty state
    if (visibleStrategies.length === 0 || !spotPrice) {
      return {
        expirationPoints: [],
        theoreticalPoints: [],
        minPrice: spotPrice - 100,
        maxPrice: spotPrice + 100,
        fullMinPrice: spotPrice - 200,
        fullMaxPrice: spotPrice + 200,
        minPnL: -100,
        maxPnL: 100,
        expirationBreakevens: [],
        theoreticalBreakevens: [],
        theoreticalPnLAtSpot: 0,
        allStrikes: [],
        centerPrice: spotPrice,
      };
    }

    // Calculate volatility (apply time machine offset)
    const adjustedVix = timeMachineEnabled ? vix + simVolatilityOffset : vix;
    const volatility = Math.max(0.05, adjustedVix) / 100;

    // Time offset for simulation
    const timeOffset = timeMachineEnabled ? simTimeOffsetHours : 0;

    // Collect all strikes
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
    const strikeRange = maxStrike - minStrike || 50;

    // Calculate 5-sigma based price range
    const sigma = spotPrice * (adjustedVix / 100);
    const sigmaHalfWidth = sigma * 2.5;

    // Full range is 5-sigma or strategy range + padding, whichever is larger
    const strategyPadding = strikeRange * 1.5;
    const fullHalfWidth = Math.max(sigmaHalfWidth, strategyPadding);

    const fullMinPrice = spotPrice - fullHalfWidth;
    const fullMaxPrice = spotPrice + fullHalfWidth;

    // Visible range (with pan offset)
    const centerPrice = (minStrike + maxStrike) / 2 + panOffset;
    const viewportPadding = Math.max(strikeRange * 0.5, 30);
    const viewportHalfWidth = (strikeRange / 2) + viewportPadding;

    const minPrice = centerPrice - viewportHalfWidth;
    const maxPrice = centerPrice + viewportHalfWidth;

    // Generate P&L curves
    const numPoints = 400;
    const step = (fullMaxPrice - fullMinPrice) / numPoints;

    const expirationPoints: PnLPoint[] = [];
    const theoreticalPoints: PnLPoint[] = [];
    let minPnL = Infinity;
    let maxPnL = -Infinity;

    for (let i = 0; i <= numPoints; i++) {
      const price = fullMinPrice + i * step;

      // Expiration P&L
      let expPnL = 0;
      for (const strat of visibleStrategies) {
        expPnL += calculateExpirationPnL(strat, price);
      }
      expirationPoints.push({ price, pnl: expPnL });

      // Theoretical P&L
      let theoPnL = 0;
      for (const strat of visibleStrategies) {
        theoPnL += calculateTheoreticalPnL(strat, price, volatility, 0.05, timeOffset);
      }
      theoreticalPoints.push({ price, pnl: theoPnL });

      // Track P&L range within visible viewport
      if (price >= minPrice && price <= maxPrice) {
        minPnL = Math.min(minPnL, expPnL, theoPnL);
        maxPnL = Math.max(maxPnL, expPnL, theoPnL);
      }
    }

    // Fallback for empty viewport
    if (minPnL === Infinity) minPnL = -100;
    if (maxPnL === -Infinity) maxPnL = 100;

    // Add padding to P&L range
    const pnlPadding = (maxPnL - minPnL) * 0.1 || 50;
    minPnL -= pnlPadding;
    maxPnL += pnlPadding;

    // Find breakevens
    const expirationBreakevens = findBreakevens(expirationPoints);
    const theoreticalBreakevens = findBreakevens(theoreticalPoints);

    // Calculate theoretical P&L at current spot
    let theoreticalPnLAtSpot = 0;
    for (const strat of visibleStrategies) {
      theoreticalPnLAtSpot += calculateTheoreticalPnL(strat, spotPrice, volatility, 0.05, timeOffset);
    }

    return {
      expirationPoints,
      theoreticalPoints,
      minPrice,
      maxPrice,
      fullMinPrice,
      fullMaxPrice,
      minPnL,
      maxPnL,
      expirationBreakevens,
      theoreticalBreakevens,
      theoreticalPnLAtSpot,
      allStrikes,
      centerPrice,
    };
  }, [strategies, spotPrice, vix, timeMachineEnabled, simVolatilityOffset, simTimeOffsetHours, panOffset]);
}

// Export calculation functions for use elsewhere
export { calculateExpirationPnL, calculateTheoreticalPnL };
