/**
 * Simulation Module
 *
 * Risk graph and P&L simulation for option positions.
 * Platform-agnostic implementation.
 */

import type { Position, PositionLeg } from '../position/types.js';
import { blackScholes, dteToYears, type Greeks } from '../pricing/index.js';

// ============================================================
// Types
// ============================================================

/** P&L at a specific price point */
export interface PnLPoint {
  /** Underlying price */
  price: number;
  /** P&L value */
  pnl: number;
}

/** Result of position simulation */
export interface SimulationResult {
  /** P&L curve points */
  curve: PnLPoint[];
  /** Maximum profit */
  maxProfit: number;
  /** Maximum loss */
  maxLoss: number;
  /** Breakeven prices */
  breakevens: number[];
  /** Position Greeks */
  greeks: Greeks;
}

/** Simulation parameters */
export interface SimulationParams {
  /** Current underlying price */
  spot: number;
  /** Annualized volatility */
  volatility: number;
  /** Risk-free interest rate */
  riskFreeRate: number;
  /** Price range as percentage of spot (e.g., 0.10 for 10%) */
  priceRange?: number;
  /** Number of points in the curve */
  numPoints?: number;
  /** Days until simulation target (0 = expiration) */
  daysForward?: number;
}

// ============================================================
// Default Values
// ============================================================

const DEFAULT_PRICE_RANGE = 0.15;  // 15% around spot
const DEFAULT_NUM_POINTS = 100;
const DEFAULT_VOLATILITY = 0.20;
const DEFAULT_RISK_FREE_RATE = 0.05;

// ============================================================
// Single Leg Calculation
// ============================================================

/**
 * Calculate the value of a single leg at a given spot price
 */
export function calculateLegValue(
  leg: PositionLeg,
  spot: number,
  volatility: number,
  riskFreeRate: number,
  daysRemaining: number
): number {
  const timeToExpiry = dteToYears(daysRemaining);

  const result = blackScholes({
    spot,
    strike: leg.strike,
    timeToExpiry,
    volatility,
    riskFreeRate,
    optionType: leg.right,
  });

  return result.price * leg.quantity;
}

/**
 * Calculate Greeks for a single leg
 */
export function calculateLegGreeks(
  leg: PositionLeg,
  spot: number,
  volatility: number,
  riskFreeRate: number,
  daysRemaining: number
): Greeks {
  const timeToExpiry = dteToYears(daysRemaining);

  const result = blackScholes({
    spot,
    strike: leg.strike,
    timeToExpiry,
    volatility,
    riskFreeRate,
    optionType: leg.right,
  });

  return {
    delta: result.greeks.delta * leg.quantity,
    gamma: result.greeks.gamma * leg.quantity,
    theta: result.greeks.theta * leg.quantity,
    vega: result.greeks.vega * leg.quantity,
    rho: (result.greeks.rho ?? 0) * leg.quantity,
  };
}

// ============================================================
// Position Calculation
// ============================================================

/**
 * Calculate the total value of a position at a given spot price
 */
export function calculatePositionValue(
  legs: PositionLeg[],
  spot: number,
  volatility: number,
  riskFreeRate: number,
  daysRemaining: number
): number {
  return legs.reduce((total, leg) => {
    return total + calculateLegValue(leg, spot, volatility, riskFreeRate, daysRemaining);
  }, 0);
}

/**
 * Calculate aggregate Greeks for a position
 */
export function calculatePositionGreeks(
  legs: PositionLeg[],
  spot: number,
  volatility: number,
  riskFreeRate: number,
  daysRemaining: number
): Greeks {
  const initial: Greeks = { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0 };

  return legs.reduce((total, leg) => {
    const legGreeks = calculateLegGreeks(leg, spot, volatility, riskFreeRate, daysRemaining);
    return {
      delta: total.delta + legGreeks.delta,
      gamma: total.gamma + legGreeks.gamma,
      theta: total.theta + legGreeks.theta,
      vega: total.vega + legGreeks.vega,
      rho: (total.rho ?? 0) + (legGreeks.rho ?? 0),
    };
  }, initial);
}

// ============================================================
// Full Simulation
// ============================================================

/**
 * Simulate P&L curve for a position
 */
export function simulatePosition(
  position: Position,
  params: SimulationParams
): SimulationResult {
  const {
    spot,
    volatility = DEFAULT_VOLATILITY,
    riskFreeRate = DEFAULT_RISK_FREE_RATE,
    priceRange = DEFAULT_PRICE_RANGE,
    numPoints = DEFAULT_NUM_POINTS,
    daysForward = 0,
  } = params;

  // Calculate price range
  const minPrice = spot * (1 - priceRange);
  const maxPrice = spot * (1 + priceRange);
  const priceStep = (maxPrice - minPrice) / (numPoints - 1);

  // Calculate current position value (entry cost)
  const entryValue = position.costBasisType === 'debit'
    ? -position.costBasis
    : position.costBasis;

  // Calculate remaining days
  const daysRemaining = Math.max(0, position.dte - daysForward);

  // Generate P&L curve
  const curve: PnLPoint[] = [];
  let maxProfit = -Infinity;
  let maxLoss = Infinity;

  for (let i = 0; i < numPoints; i++) {
    const price = minPrice + i * priceStep;

    // Value at this price point
    const value = calculatePositionValue(
      position.legs,
      price,
      volatility,
      riskFreeRate,
      daysRemaining
    );

    // P&L = current value + entry value
    const pnl = value + entryValue;

    curve.push({ price, pnl });

    if (pnl > maxProfit) maxProfit = pnl;
    if (pnl < maxLoss) maxLoss = pnl;
  }

  // Find breakevens (where P&L crosses zero)
  const breakevens: number[] = [];
  for (let i = 1; i < curve.length; i++) {
    const prev = curve[i - 1];
    const curr = curve[i];

    if (prev && curr && ((prev.pnl <= 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl <= 0))) {
      // Linear interpolation to find breakeven
      const ratio = Math.abs(prev.pnl) / (Math.abs(prev.pnl) + Math.abs(curr.pnl));
      const breakeven = prev.price + ratio * (curr.price - prev.price);
      breakevens.push(breakeven);
    }
  }

  // Calculate current Greeks
  const greeks = calculatePositionGreeks(
    position.legs,
    spot,
    volatility,
    riskFreeRate,
    daysRemaining
  );

  return {
    curve,
    maxProfit,
    maxLoss,
    breakevens,
    greeks,
  };
}

/**
 * Simulate P&L curve from raw legs (without a full Position object)
 */
export function simulateLegs(
  legs: PositionLeg[],
  entryDebit: number,
  dte: number,
  params: SimulationParams
): SimulationResult {
  const {
    spot,
    volatility = DEFAULT_VOLATILITY,
    riskFreeRate = DEFAULT_RISK_FREE_RATE,
    priceRange = DEFAULT_PRICE_RANGE,
    numPoints = DEFAULT_NUM_POINTS,
    daysForward = 0,
  } = params;

  // Calculate price range
  const minPrice = spot * (1 - priceRange);
  const maxPrice = spot * (1 + priceRange);
  const priceStep = (maxPrice - minPrice) / (numPoints - 1);

  // Entry value (negative for debit)
  const entryValue = -Math.abs(entryDebit);

  // Calculate remaining days
  const daysRemaining = Math.max(0, dte - daysForward);

  // Generate P&L curve
  const curve: PnLPoint[] = [];
  let maxProfit = -Infinity;
  let maxLoss = Infinity;

  for (let i = 0; i < numPoints; i++) {
    const price = minPrice + i * priceStep;

    const value = calculatePositionValue(
      legs,
      price,
      volatility,
      riskFreeRate,
      daysRemaining
    );

    const pnl = value + entryValue;
    curve.push({ price, pnl });

    if (pnl > maxProfit) maxProfit = pnl;
    if (pnl < maxLoss) maxLoss = pnl;
  }

  // Find breakevens
  const breakevens: number[] = [];
  for (let i = 1; i < curve.length; i++) {
    const prev = curve[i - 1];
    const curr = curve[i];

    if (prev && curr && ((prev.pnl <= 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl <= 0))) {
      const ratio = Math.abs(prev.pnl) / (Math.abs(prev.pnl) + Math.abs(curr.pnl));
      const breakeven = prev.price + ratio * (curr.price - prev.price);
      breakevens.push(breakeven);
    }
  }

  // Calculate current Greeks
  const greeks = calculatePositionGreeks(
    legs,
    spot,
    volatility,
    riskFreeRate,
    daysRemaining
  );

  return {
    curve,
    maxProfit,
    maxLoss,
    breakevens,
    greeks,
  };
}
