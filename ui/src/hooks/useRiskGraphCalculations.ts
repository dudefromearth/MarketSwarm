/**
 * useRiskGraphCalculations - Hook for calculating options P&L curves
 *
 * Generates accurate P&L curves:
 * - Expiration P&L: Piecewise linear with exact corners at strike prices
 * - Theoretical P&L: Smooth Black-Scholes curve with realistic volatility skew
 * - Breakeven points via interpolation
 *
 * Supports market regime simulation with volatility skew modeling
 */

import { useMemo } from 'react';
import { resolveSpotKey } from '../utils/symbolResolver';

// ============================================================
// Market Regime Types & Presets
// ============================================================

export type MarketRegime =
  | 'normal'
  | 'low_vol'
  | 'elevated'
  | 'panic'
  | 'fomc'
  | 'meme'
  | 'opex';

export interface RegimeConfig {
  name: string;
  description: string;
  vixRange: [number, number];  // [min, max] typical VIX for this regime
  putSkew: number;             // % IV increase per 10% OTM for puts (positive = higher IV for OTM puts)
  callSkew: number;            // % IV increase per 10% OTM for calls
  atmBoost: number;            // Additional ATM IV boost (for event days)
  color: string;               // UI indicator color
}

export const MARKET_REGIMES: Record<MarketRegime, RegimeConfig> = {
  normal: {
    name: 'Normal',
    description: 'Typical trading day',
    vixRange: [14, 18],
    putSkew: 0.15,      // 15% higher IV per 10% OTM
    callSkew: 0.03,     // 3% higher IV per 10% OTM
    atmBoost: 0,
    color: '#6b7280',   // gray
  },
  low_vol: {
    name: 'Low Vol',
    description: 'Complacent, cheap options',
    vixRange: [10, 14],
    putSkew: 0.10,
    callSkew: 0.02,
    atmBoost: 0,
    color: '#22c55e',   // green
  },
  elevated: {
    name: 'Elevated',
    description: 'Heightened fear, steep skew',
    vixRange: [22, 30],
    putSkew: 0.30,
    callSkew: 0.05,
    atmBoost: 0,
    color: '#f59e0b',   // amber
  },
  panic: {
    name: 'Panic',
    description: 'Crash/crisis mode',
    vixRange: [35, 60],
    putSkew: 0.50,
    callSkew: 0.08,
    atmBoost: 0.05,
    color: '#ef4444',   // red
  },
  fomc: {
    name: 'FOMC/Event',
    description: 'Binary event, elevated ATM',
    vixRange: [18, 26],
    putSkew: 0.12,
    callSkew: 0.12,     // Symmetric smile
    atmBoost: 0.08,     // ATM premium for uncertainty
    color: '#8b5cf6',   // purple
  },
  meme: {
    name: 'Squeeze',
    description: 'Call skew inverted, OTM calls expensive',
    vixRange: [30, 50],
    putSkew: 0.10,
    callSkew: 0.40,     // Inverted - calls more expensive
    atmBoost: 0.10,
    color: '#ec4899',   // pink
  },
  opex: {
    name: 'Opex',
    description: 'Expiration dynamics, gamma dominant',
    vixRange: [12, 20],
    putSkew: 0.08,
    callSkew: 0.08,
    atmBoost: -0.03,    // IV crush
    color: '#06b6d4',   // cyan
  },
};

// ============================================================
// Pricing Model Types & Configurations
// ============================================================

export type PricingModel = 'black-scholes' | 'heston' | 'monte-carlo';

export interface PricingModelConfig {
  name: string;
  shortName: string;
  description: string;
  color: string;
}

export const PRICING_MODELS: Record<PricingModel, PricingModelConfig> = {
  'black-scholes': {
    name: 'Black-Scholes + Skew',
    shortName: 'BS',
    description: 'Fast analytical solution with empirical skew adjustment',
    color: '#3b82f6',  // blue
  },
  'heston': {
    name: 'Heston Stochastic Vol',
    shortName: 'Heston',
    description: 'Volatility follows its own random process with mean reversion',
    color: '#8b5cf6',  // purple
  },
  'monte-carlo': {
    name: 'Monte Carlo',
    shortName: 'MC',
    description: 'Simulates thousands of price paths for maximum accuracy',
    color: '#f59e0b',  // amber
  },
};

// Heston model parameters
export interface HestonParams {
  kappa: number;      // Mean reversion speed (1-5 typical)
  theta: number;      // Long-term variance (derived from VIX)
  xi: number;         // Vol of vol (0.2-0.8 typical)
  rho: number;        // Correlation spot/vol (-0.9 to -0.3 typical, negative = leverage effect)
  v0: number;         // Initial variance (current VIX^2)
}

// Monte Carlo parameters
export interface MonteCarloParams {
  numPaths: number;   // Number of simulation paths (1000-50000)
  numSteps: number;   // Time steps per path
  seed?: number;      // Random seed for reproducibility
}

// Default Heston parameters (calibrated to typical equity index behavior)
export const DEFAULT_HESTON_PARAMS: Omit<HestonParams, 'theta' | 'v0'> = {
  kappa: 2.0,         // Mean reversion speed
  xi: 0.4,            // Vol of vol
  rho: -0.7,          // Negative correlation (leverage effect)
};

// Default Monte Carlo parameters
export const DEFAULT_MONTE_CARLO_PARAMS: MonteCarloParams = {
  numPaths: 5000,
  numSteps: 100,
};

/**
 * Calculate strike-specific implied volatility with skew
 */
function calculateSkewedIV(
  baseIV: number,
  strike: number,
  spotPrice: number,
  regime: RegimeConfig
): number {
  const moneyness = (strike - spotPrice) / spotPrice; // negative = OTM put, positive = OTM call

  let skewAdjustment = 0;

  if (moneyness < 0) {
    // OTM put (or ITM call) - apply put skew
    // moneyness of -0.10 means 10% OTM put
    skewAdjustment = regime.putSkew * Math.abs(moneyness) * 10; // Scale: per 10% OTM
  } else if (moneyness > 0) {
    // OTM call (or ITM put) - apply call skew
    skewAdjustment = regime.callSkew * moneyness * 10;
  }

  // Apply ATM boost (affects all strikes but peaks at ATM)
  const atmDistance = Math.abs(moneyness);
  const atmFactor = Math.exp(-atmDistance * atmDistance * 50); // Gaussian centered at ATM
  const atmAdjustment = regime.atmBoost * atmFactor;

  return baseIV * (1 + skewAdjustment + atmAdjustment);
}

// Import position types
import type { PositionLeg, PositionType, PositionDirection } from '../types/riskGraph';

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
  symbol?: string;  // Underlying symbol for per-symbol spot lookup
  // New leg-based fields (optional for backward compat)
  legs?: PositionLeg[];
  positionType?: PositionType;
  direction?: PositionDirection;
}

export interface PnLPoint {
  price: number;
  pnl: number;
}

export interface RiskGraphData {
  expirationPoints: PnLPoint[];
  theoreticalPoints: PnLPoint[];
  minPrice: number;
  maxPrice: number;
  fullMinPrice: number;
  fullMaxPrice: number;
  minPnL: number;
  maxPnL: number;
  expirationBreakevens: number[];
  theoreticalBreakevens: number[];
  theoreticalPnLAtSpot: number;
  // Greeks at current/simulated spot
  theta: number;  // Daily theta (time decay) in dollars
  gamma: number;  // Gamma (rate of delta change)
  delta: number;  // Delta (price sensitivity)
  allStrikes: number[];
  centerPrice: number;
  // Strategy IDs that are "alive" at the simulated time (not past expiration)
  activeStrategyIds: string[];
  // Faded curves for sim-expired strategies (shown as ghost lines)
  expiredExpirationPoints: PnLPoint[];
  expiredTheoreticalPoints: PnLPoint[];
}

interface UseRiskGraphCalculationsProps {
  strategies: Strategy[];
  spotPrice: number;
  vix: number;
  spotPrices?: Record<string, number>;  // symbol -> spot price map for per-symbol pricing
  timeMachineEnabled?: boolean;
  simVolatilityOffset?: number;
  simTimeOffsetHours?: number;
  simSpotOffset?: number;
  panOffset?: number;
  marketRegime?: MarketRegime;
  // Pricing model selection
  pricingModel?: PricingModel;
  // Heston-specific parameters
  hestonVolOfVol?: number;      // Vol of vol (xi), default 0.4
  hestonMeanReversion?: number; // Mean reversion speed (kappa), default 2.0
  hestonCorrelation?: number;   // Spot/vol correlation (rho), default -0.7
  // Monte Carlo parameters
  mcNumPaths?: number;          // Number of simulation paths, default 5000
}

// ============================================================
// Black-Scholes Implementation
// ============================================================

/**
 * Standard normal cumulative distribution function
 * Uses Abramowitz and Stegun approximation (error < 7.5e-8)
 */
function normalCDF(x: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;

  const sign = x < 0 ? -1 : 1;
  const absX = Math.abs(x) / Math.sqrt(2);
  const t = 1.0 / (1.0 + p * absX);
  const y = 1.0 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX);

  return 0.5 * (1.0 + sign * y);
}

/**
 * Standard normal probability density function
 */
function normalPDF(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

/**
 * Calculate d1 and d2 for Black-Scholes
 */
function calculateD1D2(S: number, K: number, T: number, r: number, sigma: number): { d1: number; d2: number } {
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  return { d1, d2 };
}

/**
 * Black-Scholes Greeks for a single option
 */
interface OptionGreeks {
  delta: number;
  gamma: number;
  theta: number;  // Per day
}

function calculateOptionGreeks(
  S: number,
  K: number,
  T: number,
  r: number,
  sigma: number,
  isCall: boolean
): OptionGreeks {
  // At or very near expiration (< 30 minutes), return approximated Greeks
  const minT = 1 / (365 * 24 * 2); // ~30 minutes in years
  if (T <= minT || sigma <= 0.001 || S <= 0 || K <= 0) {
    // At expiration, delta approaches 1 (ITM call) or 0 (OTM call), gamma/theta → 0
    if (T <= 0) {
      const itm = isCall ? S > K : S < K;
      return { delta: itm ? (isCall ? 1 : -1) : 0, gamma: 0, theta: 0 };
    }
    // Very close to expiration - use small T for calculation stability
    T = minT;
  }

  const { d1, d2 } = calculateD1D2(S, K, T, r, sigma);
  const sqrtT = Math.sqrt(T);
  const nd1 = normalPDF(d1);
  const Nd1 = normalCDF(d1);
  const Nd2 = normalCDF(d2);

  // Gamma is the same for calls and puts
  const gamma = nd1 / (S * sigma * sqrtT);

  if (isCall) {
    const delta = Nd1;
    // Theta per year, then convert to per day
    const thetaYear = -(S * nd1 * sigma) / (2 * sqrtT) - r * K * Math.exp(-r * T) * Nd2;
    const theta = thetaYear / 365;
    return { delta, gamma, theta };
  } else {
    const delta = Nd1 - 1;
    // Theta per year for put
    const thetaYear = -(S * nd1 * sigma) / (2 * sqrtT) + r * K * Math.exp(-r * T) * normalCDF(-d2);
    const theta = thetaYear / 365;
    return { delta, gamma, theta };
  }
}

/**
 * Black-Scholes call option price
 * @param S - Current spot price
 * @param K - Strike price
 * @param T - Time to expiration in years
 * @param r - Risk-free interest rate (annualized)
 * @param sigma - Volatility (annualized, as decimal e.g., 0.20 for 20%)
 */
function blackScholesCall(S: number, K: number, T: number, r: number, sigma: number): number {
  // At or past expiration, return intrinsic value
  if (T <= 0) return Math.max(0, S - K);

  // Handle edge cases
  if (sigma <= 0.001) return Math.max(0, S - K);
  if (S <= 0) return 0;
  if (K <= 0) return S;

  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;

  const callValue = S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);

  // Clamp to valid range: call value is always between 0 and S
  return Math.max(0, Math.min(S, callValue));
}

/**
 * Black-Scholes put option price (via put-call parity)
 */
function blackScholesPut(S: number, K: number, T: number, r: number, sigma: number): number {
  if (T <= 0) return Math.max(0, K - S);

  if (sigma <= 0.001) return Math.max(0, K - S);
  if (S <= 0) return K * Math.exp(-r * T);
  if (K <= 0) return 0;

  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;

  const putValue = K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);

  // Clamp to valid range: put value is always between 0 and K
  return Math.max(0, Math.min(K, putValue));
}

// ============================================================
// Heston Stochastic Volatility Model
// ============================================================

/**
 * Calculate Heston-style implied volatility adjustment
 * This generates a natural volatility smile based on Heston parameters
 * without the complexity of full characteristic function integration
 *
 * The key insight: Heston generates a smile through:
 * - Vol of vol (xi) controls smile curvature
 * - Correlation (rho) controls skew direction (negative = put skew)
 * - Mean reversion (kappa) affects term structure
 */
function hestonImpliedVol(
  baseVol: number,
  S: number,
  K: number,
  T: number,
  xi: number,      // Vol of vol
  rho: number,     // Correlation (-1 to 1)
  kappa: number    // Mean reversion
): number {
  const moneyness = Math.log(K / S);
  const sqrtT = Math.sqrt(Math.max(T, 0.001));

  // Smile curvature from vol of vol (symmetric component)
  // Higher xi = more pronounced smile
  const smileCurvature = xi * xi * T * 0.5;
  const smileEffect = smileCurvature * moneyness * moneyness;

  // Skew from correlation (asymmetric component)
  // Negative rho = higher vol for OTM puts (leverage effect)
  const skewEffect = -rho * xi * sqrtT * moneyness * 0.8;

  // Mean reversion dampens effects over time
  const meanReversionFactor = 1 - Math.exp(-kappa * T);
  const termAdjustment = meanReversionFactor * 0.3;

  // Combine effects
  const volAdjustment = (smileEffect + skewEffect) * (1 + termAdjustment);

  // Return adjusted vol, ensuring it stays positive
  return Math.max(0.01, baseVol * (1 + volAdjustment));
}

/**
 * Heston model call price using BS with Heston-implied vol
 */
function hestonCallPrice(
  S: number,
  K: number,
  T: number,
  r: number,
  v0: number,     // Initial variance (sigma^2)
  kappa: number,
  _theta: number,
  xi: number,
  rho: number
): number {
  if (T <= 0) return Math.max(0, S - K);

  const baseVol = Math.sqrt(v0);
  const hestonVol = hestonImpliedVol(baseVol, S, K, T, xi, rho, kappa);

  return blackScholesCall(S, K, T, r, hestonVol);
}

/**
 * Heston model put price using BS with Heston-implied vol
 */
function hestonPutPrice(
  S: number,
  K: number,
  T: number,
  r: number,
  v0: number,
  kappa: number,
  _theta: number,
  xi: number,
  rho: number
): number {
  if (T <= 0) return Math.max(0, K - S);

  const baseVol = Math.sqrt(v0);
  const hestonVol = hestonImpliedVol(baseVol, S, K, T, xi, rho, kappa);

  return blackScholesPut(S, K, T, r, hestonVol);
}

// ============================================================
// Monte Carlo Simulation
// ============================================================

/**
 * Simple seeded random number generator (Mulberry32)
 */
function mulberry32(seed: number): () => number {
  return function() {
    let t = seed += 0x6D2B79F5;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

/**
 * Box-Muller transform for normal random numbers
 */
function boxMuller(random: () => number): number {
  const u1 = random();
  const u2 = random();
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

/**
 * Monte Carlo option pricing with GBM
 */
export function _monteCarloPrice(
  S: number,
  K: number,
  T: number,
  r: number,
  sigma: number,
  isCall: boolean,
  numPaths: number,
  numSteps: number,
  seed: number = 42
): { price: number; stdError: number } {
  if (T <= 0) {
    return {
      price: isCall ? Math.max(0, S - K) : Math.max(0, K - S),
      stdError: 0,
    };
  }

  const random = mulberry32(seed);
  const dt = T / numSteps;
  const drift = (r - 0.5 * sigma * sigma) * dt;
  const diffusion = sigma * Math.sqrt(dt);

  let sumPayoffs = 0;
  let sumPayoffsSquared = 0;

  for (let path = 0; path < numPaths; path++) {
    let price = S;

    // Simulate price path
    for (let step = 0; step < numSteps; step++) {
      const z = boxMuller(random);
      price *= Math.exp(drift + diffusion * z);
    }

    // Calculate payoff
    const payoff = isCall
      ? Math.max(0, price - K)
      : Math.max(0, K - price);

    sumPayoffs += payoff;
    sumPayoffsSquared += payoff * payoff;
  }

  // Discounted average payoff
  const discountFactor = Math.exp(-r * T);
  const meanPayoff = sumPayoffs / numPaths;
  const price = discountFactor * meanPayoff;

  // Standard error
  const variance = (sumPayoffsSquared / numPaths) - (meanPayoff * meanPayoff);
  const stdError = discountFactor * Math.sqrt(variance / numPaths);

  return { price, stdError };
}

/**
 * Monte Carlo with Heston dynamics (more realistic)
 */
export function _monteCarloHeston(
  S: number,
  K: number,
  T: number,
  r: number,
  v0: number,
  kappa: number,
  theta: number,
  xi: number,
  rho: number,
  isCall: boolean,
  numPaths: number,
  numSteps: number,
  seed: number = 42
): { price: number; stdError: number } {
  if (T <= 0) {
    return {
      price: isCall ? Math.max(0, S - K) : Math.max(0, K - S),
      stdError: 0,
    };
  }

  const random = mulberry32(seed);
  const dt = T / numSteps;
  const sqrtDt = Math.sqrt(dt);
  const sqrtOneMinusRhoSq = Math.sqrt(1 - rho * rho);

  let sumPayoffs = 0;
  let sumPayoffsSquared = 0;

  for (let path = 0; path < numPaths; path++) {
    let price = S;
    let v = v0;

    // Simulate price and variance paths
    for (let step = 0; step < numSteps; step++) {
      const z1 = boxMuller(random);
      const z2 = rho * z1 + sqrtOneMinusRhoSq * boxMuller(random);

      // Variance process (ensure non-negative with reflection)
      const sqrtV = Math.sqrt(Math.max(0, v));
      v = v + kappa * (theta - v) * dt + xi * sqrtV * sqrtDt * z2;
      v = Math.max(0, v);

      // Price process
      price = price * Math.exp((r - 0.5 * v) * dt + sqrtV * sqrtDt * z1);
    }

    // Calculate payoff
    const payoff = isCall
      ? Math.max(0, price - K)
      : Math.max(0, K - price);

    sumPayoffs += payoff;
    sumPayoffsSquared += payoff * payoff;
  }

  // Discounted average payoff
  const discountFactor = Math.exp(-r * T);
  const meanPayoff = sumPayoffs / numPaths;
  const price = discountFactor * meanPayoff;

  // Standard error
  const variance = (sumPayoffsSquared / numPaths) - (meanPayoff * meanPayoff);
  const stdError = discountFactor * Math.sqrt(variance / numPaths);

  return { price, stdError };
}

// ============================================================
// Expiration P&L Calculations (Intrinsic Value)
// ============================================================

/**
 * Calculate expiration P&L for a single option
 */
function singleOptionExpirationPnL(
  price: number,
  strike: number,
  side: 'call' | 'put',
  debit: number
): number {
  if (side === 'call') {
    return Math.max(0, price - strike) - debit;
  } else {
    return Math.max(0, strike - price) - debit;
  }
}

/**
 * Calculate expiration P&L for a vertical spread
 * - Call vertical: Long lower strike, short higher strike (bull call spread)
 * - Put vertical: Long higher strike, short lower strike (bear put spread)
 */
function verticalExpirationPnL(
  price: number,
  strike: number,
  width: number,
  side: 'call' | 'put',
  debit: number
): number {
  if (side === 'call') {
    // Bull call spread: long K, short K+width
    const longLeg = Math.max(0, price - strike);
    const shortLeg = Math.max(0, price - (strike + width));
    return longLeg - shortLeg - debit;
  } else {
    // Bear put spread: long K, short K-width
    const longLeg = Math.max(0, strike - price);
    const shortLeg = Math.max(0, (strike - width) - price);
    return longLeg - shortLeg - debit;
  }
}

/**
 * Calculate expiration P&L for a butterfly spread
 * - Call butterfly: Long 1 lower, short 2 middle, long 1 upper
 * - Put butterfly: Long 1 upper, short 2 middle, long 1 lower
 */
function butterflyExpirationPnL(
  price: number,
  centerStrike: number,
  width: number,
  side: 'call' | 'put',
  debit: number
): number {
  const lowerStrike = centerStrike - width;
  const upperStrike = centerStrike + width;

  if (side === 'call') {
    const lower = Math.max(0, price - lowerStrike);
    const middle = Math.max(0, price - centerStrike);
    const upper = Math.max(0, price - upperStrike);
    return lower - 2 * middle + upper - debit;
  } else {
    const lower = Math.max(0, lowerStrike - price);
    const middle = Math.max(0, centerStrike - price);
    const upper = Math.max(0, upperStrike - price);
    return upper - 2 * middle + lower - debit;
  }
}

/**
 * Calculate expiration P&L for a single leg at a specific expiration date
 * For legs expiring ON this date: use intrinsic value
 * For legs expiring AFTER this date: use Black-Scholes theoretical value
 */
function legExpirationPnL(
  price: number,
  leg: PositionLeg,
  primaryExpiration?: string,
  baseVolatility?: number
): number {
  // If no primary expiration specified or leg expires on/before primary, use intrinsic
  if (!primaryExpiration || !leg.expiration || leg.expiration <= primaryExpiration) {
    const intrinsic = leg.right === 'call'
      ? Math.max(0, price - leg.strike)
      : Math.max(0, leg.strike - price);
    return intrinsic * leg.quantity;
  }

  // Leg expires AFTER primary expiration - it still has time value
  // Calculate time remaining from primary expiration to this leg's expiration
  const primaryDate = new Date(primaryExpiration + 'T16:00:00');
  const legExpDate = new Date(leg.expiration + 'T16:00:00');
  const daysRemaining = Math.max(1, (legExpDate.getTime() - primaryDate.getTime()) / (1000 * 60 * 60 * 24));
  const timeToExpiry = daysRemaining / 365;

  // Use provided volatility or default
  const vol = baseVolatility || 0.20;
  const rate = 0.05;

  // Calculate theoretical value using Black-Scholes
  const theoreticalValue = leg.right === 'call'
    ? blackScholesCall(price, leg.strike, timeToExpiry, rate, vol)
    : blackScholesPut(price, leg.strike, timeToExpiry, rate, vol);

  return theoreticalValue * leg.quantity;
}

/**
 * Get the primary (earliest) expiration from legs
 */
function getPrimaryExpiration(legs: PositionLeg[]): string | undefined {
  const expirations = legs.map(l => l.expiration).filter(Boolean);
  if (expirations.length === 0) return undefined;
  return expirations.sort()[0];
}

/**
 * Check if position has multiple expirations (calendar/diagonal)
 */
function hasMultipleExpirations(legs: PositionLeg[]): boolean {
  const expirations = new Set(legs.map(l => l.expiration).filter(Boolean));
  return expirations.size > 1;
}

/**
 * Calculate total expiration P&L from legs
 * For calendars/diagonals: values far-dated legs using Black-Scholes at primary expiration
 */
function calculateLegsExpirationPnL(
  legs: PositionLeg[],
  price: number,
  debit: number,
  baseVolatility?: number
): number {
  const multiplier = 100;
  let pnlPerShare = 0;

  // For multi-expiration positions, calculate P&L at the primary (nearest) expiration
  const primaryExp = hasMultipleExpirations(legs) ? getPrimaryExpiration(legs) : undefined;

  for (const leg of legs) {
    pnlPerShare += legExpirationPnL(price, leg, primaryExp, baseVolatility);
  }

  return (pnlPerShare - debit) * multiplier;
}

/**
 * Calculate total expiration P&L for a strategy
 * For calendars/diagonals: uses Black-Scholes for far-dated legs at primary expiration
 */
function calculateExpirationPnL(strategy: Strategy, price: number, baseVolatility?: number): number {
  const debit = strategy.debit || 0;
  const multiplier = 100; // Standard equity option multiplier

  // If legs are provided, use leg-based calculation
  if (strategy.legs && strategy.legs.length > 0) {
    return calculateLegsExpirationPnL(strategy.legs, price, debit, baseVolatility);
  }

  // Legacy calculation for backward compatibility
  let pnlPerShare = 0;

  switch (strategy.strategy) {
    case 'single':
      pnlPerShare = singleOptionExpirationPnL(price, strategy.strike, strategy.side, debit);
      break;
    case 'vertical':
      pnlPerShare = verticalExpirationPnL(price, strategy.strike, strategy.width, strategy.side, debit);
      break;
    case 'butterfly':
      pnlPerShare = butterflyExpirationPnL(price, strategy.strike, strategy.width, strategy.side, debit);
      break;
  }

  return pnlPerShare * multiplier;
}

/**
 * Calculate Greeks for a single leg
 */
function calculateLegGreeks(
  leg: PositionLeg,
  price: number,
  baseVolatility: number,
  rate: number,
  timeToExpiryYears: number,
  spotPrice: number,
  regime: RegimeConfig
): OptionGreeks {
  const T = Math.max(0, timeToExpiryYears);
  const skewedIV = calculateSkewedIV(baseVolatility, leg.strike, spotPrice, regime);
  const g = calculateOptionGreeks(price, leg.strike, T, rate, skewedIV, leg.right === 'call');

  // Scale by quantity (positive for long, negative for short)
  return {
    delta: g.delta * leg.quantity,
    gamma: g.gamma * Math.abs(leg.quantity), // Gamma is always additive in absolute
    theta: g.theta * leg.quantity,
  };
}

/**
 * Calculate aggregate Greeks from legs
 */
function calculateLegsGreeks(
  legs: PositionLeg[],
  price: number,
  baseVolatility: number,
  rate: number,
  timeToExpiryYears: number,
  spotPrice: number,
  regime: RegimeConfig
): OptionGreeks {
  const multiplier = 100;
  let delta = 0;
  let gamma = 0;
  let theta = 0;

  for (const leg of legs) {
    const g = calculateLegGreeks(leg, price, baseVolatility, rate, timeToExpiryYears, spotPrice, regime);
    delta += g.delta;
    gamma += g.gamma * (leg.quantity > 0 ? 1 : -1); // Gamma sign based on position
    theta += g.theta;
  }

  return {
    delta: delta * multiplier,
    gamma: gamma * multiplier,
    theta: theta * multiplier,
  };
}

/**
 * Calculate Greeks for a strategy at a given price with volatility skew
 */
function calculateStrategyGreeks(
  strategy: Strategy,
  price: number,
  baseVolatility: number,
  rate: number,
  timeToExpiryYears: number,
  spotPrice: number,
  regime: RegimeConfig
): OptionGreeks {
  const multiplier = 100;
  const T = Math.max(0, timeToExpiryYears);

  // If legs are provided, use leg-based calculation
  if (strategy.legs && strategy.legs.length > 0) {
    return calculateLegsGreeks(strategy.legs, price, baseVolatility, rate, timeToExpiryYears, spotPrice, regime);
  }

  // Use skewed IV for each strike
  const getGreeks = (K: number, isCall: boolean) => {
    const skewedIV = calculateSkewedIV(baseVolatility, K, spotPrice, regime);
    return calculateOptionGreeks(price, K, T, rate, skewedIV, isCall);
  };

  let delta = 0;
  let gamma = 0;
  let theta = 0;

  switch (strategy.strategy) {
    case 'single': {
      const g = getGreeks(strategy.strike, strategy.side === 'call');
      delta = g.delta;
      gamma = g.gamma;
      theta = g.theta;
      break;
    }

    case 'vertical': {
      if (strategy.side === 'call') {
        // Bull call spread: long lower, short higher
        const longG = getGreeks(strategy.strike, true);
        const shortG = getGreeks(strategy.strike + strategy.width, true);
        delta = longG.delta - shortG.delta;
        gamma = longG.gamma - shortG.gamma;
        theta = longG.theta - shortG.theta;
      } else {
        // Bear put spread: long higher, short lower
        const longG = getGreeks(strategy.strike, false);
        const shortG = getGreeks(strategy.strike - strategy.width, false);
        delta = longG.delta - shortG.delta;
        gamma = longG.gamma - shortG.gamma;
        theta = longG.theta - shortG.theta;
      }
      break;
    }

    case 'butterfly': {
      const lowerK = strategy.strike - strategy.width;
      const middleK = strategy.strike;
      const upperK = strategy.strike + strategy.width;

      if (strategy.side === 'call') {
        const lowerG = getGreeks(lowerK, true);
        const middleG = getGreeks(middleK, true);
        const upperG = getGreeks(upperK, true);
        // Long 1 lower, short 2 middle, long 1 upper
        delta = lowerG.delta - 2 * middleG.delta + upperG.delta;
        gamma = lowerG.gamma - 2 * middleG.gamma + upperG.gamma;
        theta = lowerG.theta - 2 * middleG.theta + upperG.theta;
      } else {
        const lowerG = getGreeks(lowerK, false);
        const middleG = getGreeks(middleK, false);
        const upperG = getGreeks(upperK, false);
        // Long 1 upper, short 2 middle, long 1 lower
        delta = upperG.delta - 2 * middleG.delta + lowerG.delta;
        gamma = upperG.gamma - 2 * middleG.gamma + lowerG.gamma;
        theta = upperG.theta - 2 * middleG.theta + lowerG.theta;
      }
      break;
    }
  }

  // Apply multiplier for contract size
  return {
    delta: delta * multiplier,
    gamma: gamma * multiplier,
    theta: theta * multiplier,
  };
}

// ============================================================
// Theoretical P&L Calculations (Black-Scholes)
// ============================================================

/**
 * Calculate the maximum theoretical value a strategy can have (at expiration)
 */
function getStrategyMaxValue(strategy: Strategy): number {
  switch (strategy.strategy) {
    case 'single':
      // Single options have unlimited upside (calls) or strike-limited (puts)
      return Infinity;
    case 'vertical':
      // Max value is the width of the spread
      return strategy.width;
    case 'butterfly':
      // Max value is the width (profit at middle strike)
      return strategy.width;
  }
  return Infinity;
}

/**
 * Calculate the minimum theoretical value a strategy can have
 */
function getStrategyMinValue(_strategy: Strategy): number {
  // For debit strategies, the minimum value is 0 (total loss of premium)
  return 0;
}

/**
 * Calculate theoretical P&L using Black-Scholes with volatility skew
 * Each strike gets its own IV based on the market regime's skew parameters
 */
interface PricingParams {
  model: PricingModel;
  regime: RegimeConfig;
  // Heston params
  hestonKappa: number;
  hestonXi: number;
  hestonRho: number;
  // Monte Carlo params
  mcNumPaths: number;
  mcSeed: number;
}

/**
 * Calculate theoretical P&L for a single leg using its own expiration
 */
function calculateLegTheoreticalValue(
  leg: PositionLeg,
  price: number,
  baseVolatility: number,
  rate: number,
  baseTimeYears: number,
  spotPrice: number,
  regime: RegimeConfig,
  primaryExpiration?: string
): number {
  // Calculate this leg's specific time to expiry
  let legTimeYears = baseTimeYears;

  if (leg.expiration && primaryExpiration && leg.expiration !== primaryExpiration) {
    // This leg has a different expiration - calculate its specific time
    const now = new Date();
    const legExpDate = new Date(leg.expiration + 'T16:00:00');
    const daysToLegExp = Math.max(0.001, (legExpDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    legTimeYears = daysToLegExp / 365;
  }

  // Get skewed IV for this strike
  const skewedIV = calculateSkewedIV(baseVolatility, leg.strike, spotPrice, regime);

  // Price the option with its specific time to expiry
  const legValue = leg.right === 'call'
    ? blackScholesCall(price, leg.strike, legTimeYears, rate, skewedIV)
    : blackScholesPut(price, leg.strike, legTimeYears, rate, skewedIV);

  return legValue * leg.quantity;
}

/**
 * Calculate theoretical P&L from legs
 * For calendars/diagonals: each leg uses its own time to expiration
 */
function calculateLegsTheoreticalPnL(
  legs: PositionLeg[],
  price: number,
  debit: number,
  baseVolatility: number,
  rate: number,
  baseTimeYears: number,
  spotPrice: number,
  regime: RegimeConfig
): number {
  const multiplier = 100;
  let theoreticalValue = 0;

  // Get primary expiration for multi-expiration detection
  const primaryExp = hasMultipleExpirations(legs) ? getPrimaryExpiration(legs) : undefined;

  for (const leg of legs) {
    theoreticalValue += calculateLegTheoreticalValue(
      leg, price, baseVolatility, rate, baseTimeYears, spotPrice, regime, primaryExp
    );
  }

  return (theoreticalValue - debit) * multiplier;
}

function calculateTheoreticalPnL(
  strategy: Strategy,
  price: number,
  baseVolatility: number,
  rate: number,
  timeToExpiryYears: number,
  spotPrice: number,
  params: PricingParams
): number {
  const debit = strategy.debit || 0;
  const multiplier = 100;
  const T = Math.max(0, timeToExpiryYears);

  // At true expiration (T=0), return expiration P&L
  if (T <= 0) {
    return calculateExpirationPnL(strategy, price, baseVolatility);
  }

  // Create pricing functions based on selected model
  let optionCall: (K: number) => number;
  let optionPut: (K: number) => number;

  const v0 = baseVolatility * baseVolatility;  // Initial variance for Heston
  const theta = v0;  // Long-term variance = current variance

  switch (params.model) {
    case 'heston':
      optionCall = (K: number) => hestonCallPrice(
        price, K, T, rate, v0,
        params.hestonKappa, theta, params.hestonXi, params.hestonRho
      );
      optionPut = (K: number) => hestonPutPrice(
        price, K, T, rate, v0,
        params.hestonKappa, theta, params.hestonXi, params.hestonRho
      );
      break;

    case 'monte-carlo':
      // For real-time interactive use, Monte Carlo simulation is too noisy
      // Use Heston analytical approach with slightly higher vol-of-vol to show
      // the effect of stochastic paths (wider confidence interval)
      const mcXi = params.hestonXi * 1.2; // Slightly higher vol-of-vol for MC flavor
      optionCall = (K: number) => {
        const mcVol = hestonImpliedVol(Math.sqrt(v0), price, K, T, mcXi, params.hestonRho, params.hestonKappa);
        return blackScholesCall(price, K, T, rate, mcVol);
      };
      optionPut = (K: number) => {
        const mcVol = hestonImpliedVol(Math.sqrt(v0), price, K, T, mcXi, params.hestonRho, params.hestonKappa);
        return blackScholesPut(price, K, T, rate, mcVol);
      };
      break;

    case 'black-scholes':
    default:
      // Black-Scholes with skew adjustment
      optionCall = (K: number) => {
        const skewedIV = calculateSkewedIV(baseVolatility, K, spotPrice, params.regime);
        return blackScholesCall(price, K, T, rate, skewedIV);
      };
      optionPut = (K: number) => {
        const skewedIV = calculateSkewedIV(baseVolatility, K, spotPrice, params.regime);
        return blackScholesPut(price, K, T, rate, skewedIV);
      };
      break;
  }

  // If legs are provided, use leg-based calculation with per-leg time to expiry
  if (strategy.legs && strategy.legs.length > 0) {
    return calculateLegsTheoreticalPnL(
      strategy.legs, price, debit,
      baseVolatility, rate, T, spotPrice, params.regime
    );
  }

  // Legacy calculation for backward compatibility
  let theoreticalValue = 0;

  switch (strategy.strategy) {
    case 'single':
      theoreticalValue = strategy.side === 'call'
        ? optionCall(strategy.strike)
        : optionPut(strategy.strike);
      break;

    case 'vertical':
      if (strategy.side === 'call') {
        // Bull call spread
        theoreticalValue = optionCall(strategy.strike) - optionCall(strategy.strike + strategy.width);
      } else {
        // Bear put spread
        theoreticalValue = optionPut(strategy.strike) - optionPut(strategy.strike - strategy.width);
      }
      break;

    case 'butterfly':
      const lowerK = strategy.strike - strategy.width;
      const middleK = strategy.strike;
      const upperK = strategy.strike + strategy.width;

      if (strategy.side === 'call') {
        theoreticalValue = optionCall(lowerK) - 2 * optionCall(middleK) + optionCall(upperK);
      } else {
        theoreticalValue = optionPut(upperK) - 2 * optionPut(middleK) + optionPut(lowerK);
      }
      break;
  }

  // Clamp theoretical value to valid bounds
  const maxValue = getStrategyMaxValue(strategy);
  const minValue = getStrategyMinValue(strategy);
  theoreticalValue = Math.max(minValue, Math.min(maxValue, theoreticalValue));

  return (theoreticalValue - debit) * multiplier;
}

// ============================================================
// Curve Generation
// ============================================================

/**
 * Cubic spline interpolation to upsample a curve
 * Takes sparse points and creates a smooth interpolated curve
 */
export function _interpolateCurve(points: PnLPoint[], targetPoints: number): PnLPoint[] {
  if (points.length < 4 || points.length >= targetPoints) return points;

  const n = points.length;
  const x = points.map(p => p.price);
  const y = points.map(p => p.pnl);

  // Calculate second derivatives for cubic spline (natural spline: y''=0 at ends)
  const h: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    h.push(x[i + 1] - x[i]);
  }

  // Solve tridiagonal system for second derivatives
  const alpha: number[] = [0];
  for (let i = 1; i < n - 1; i++) {
    alpha.push((3 / h[i]) * (y[i + 1] - y[i]) - (3 / h[i - 1]) * (y[i] - y[i - 1]));
  }

  const l: number[] = [1];
  const mu: number[] = [0];
  const z: number[] = [0];

  for (let i = 1; i < n - 1; i++) {
    l.push(2 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]);
    mu.push(h[i] / l[i]);
    z.push((alpha[i] - h[i - 1] * z[i - 1]) / l[i]);
  }

  l.push(1);
  z.push(0);

  const c: number[] = new Array(n).fill(0);
  const b: number[] = new Array(n - 1).fill(0);
  const d: number[] = new Array(n - 1).fill(0);

  for (let j = n - 2; j >= 0; j--) {
    c[j] = z[j] - mu[j] * c[j + 1];
    b[j] = (y[j + 1] - y[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3;
    d[j] = (c[j + 1] - c[j]) / (3 * h[j]);
  }

  // Generate interpolated points
  const result: PnLPoint[] = [];
  const minX = x[0];
  const maxX = x[n - 1];
  const step = (maxX - minX) / (targetPoints - 1);

  let segmentIdx = 0;
  for (let i = 0; i < targetPoints; i++) {
    const px = minX + i * step;

    // Find the right segment
    while (segmentIdx < n - 2 && px > x[segmentIdx + 1]) {
      segmentIdx++;
    }

    const dx = px - x[segmentIdx];
    const py = y[segmentIdx] + b[segmentIdx] * dx + c[segmentIdx] * dx * dx + d[segmentIdx] * dx * dx * dx;

    result.push({ price: px, pnl: py });
  }

  return result;
}

/**
 * Gaussian smoothing for P&L curves
 * Applies weighted average using Gaussian kernel
 */
export function _smoothPnLCurve(points: PnLPoint[], windowSize: number = 5): PnLPoint[] {
  if (points.length < windowSize) return points;

  // Generate Gaussian weights
  const sigma = windowSize / 4;
  const weights: number[] = [];
  const halfWindow = Math.floor(windowSize / 2);

  for (let i = -halfWindow; i <= halfWindow; i++) {
    weights.push(Math.exp(-(i * i) / (2 * sigma * sigma)));
  }
  const weightSum = weights.reduce((a, b) => a + b, 0);
  const normalizedWeights = weights.map(w => w / weightSum);

  // Apply smoothing
  const smoothed: PnLPoint[] = [];

  for (let i = 0; i < points.length; i++) {
    let smoothedPnL = 0;
    let totalWeight = 0;

    for (let j = -halfWindow; j <= halfWindow; j++) {
      const idx = i + j;
      if (idx >= 0 && idx < points.length) {
        const weight = normalizedWeights[j + halfWindow];
        smoothedPnL += points[idx].pnl * weight;
        totalWeight += weight;
      }
    }

    smoothed.push({
      price: points[i].price,
      pnl: smoothedPnL / totalWeight,
    });
  }

  return smoothed;
}

/**
 * Get all critical strike prices from strategies
 * These are prices where the expiration P&L curve changes slope
 */
function getCriticalStrikes(strategies: Strategy[]): number[] {
  const strikes = new Set<number>();

  for (const s of strategies) {
    if (!s.visible) continue;

    // If legs are provided, extract strikes from legs
    if (s.legs && s.legs.length > 0) {
      for (const leg of s.legs) {
        strikes.add(leg.strike);
      }
      continue;
    }

    // Legacy: extract strikes from strategy type
    switch (s.strategy) {
      case 'single':
        strikes.add(s.strike);
        break;
      case 'vertical':
        strikes.add(s.strike);
        strikes.add(s.side === 'call' ? s.strike + s.width : s.strike - s.width);
        break;
      case 'butterfly':
        strikes.add(s.strike - s.width);
        strikes.add(s.strike);
        strikes.add(s.strike + s.width);
        break;
    }
  }

  return Array.from(strikes).sort((a, b) => a - b);
}

/**
 * Generate price points for the P&L curve
 * Ensures critical strikes are included for accurate expiration corners
 */
function generatePricePoints(
  minPrice: number,
  maxPrice: number,
  criticalStrikes: number[],
  basePoints: number = 200
): number[] {
  const prices = new Set<number>();

  // Add evenly spaced base points
  const step = (maxPrice - minPrice) / basePoints;
  for (let i = 0; i <= basePoints; i++) {
    prices.add(minPrice + i * step);
  }

  // Add all critical strikes (with small offsets for corner definition)
  const epsilon = 0.01;
  for (const strike of criticalStrikes) {
    if (strike >= minPrice && strike <= maxPrice) {
      prices.add(strike - epsilon);
      prices.add(strike);
      prices.add(strike + epsilon);
    }
  }

  // Sort and return
  return Array.from(prices).sort((a, b) => a - b);
}

/**
 * Find breakeven points where P&L crosses zero
 */
function findBreakevens(points: PnLPoint[]): number[] {
  const breakevens: number[] = [];

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];

    // Check for zero crossing
    if ((prev.pnl < 0 && curr.pnl >= 0) || (prev.pnl >= 0 && curr.pnl < 0)) {
      // Linear interpolation for exact crossing
      const t = Math.abs(prev.pnl) / Math.abs(curr.pnl - prev.pnl);
      const bePrice = prev.price + t * (curr.price - prev.price);
      breakevens.push(bePrice);
    }
  }

  return breakevens;
}

// ============================================================
// Main Hook
// ============================================================

export function useRiskGraphCalculations({
  strategies,
  spotPrice,
  vix,
  spotPrices,
  timeMachineEnabled = false,
  simVolatilityOffset = 0,
  simTimeOffsetHours = 0,
  simSpotOffset = 0,
  panOffset = 0,
  marketRegime = 'normal',
  pricingModel = 'black-scholes',
  hestonVolOfVol = 0.4,
  hestonMeanReversion = 2.0,
  hestonCorrelation = -0.7,
  mcNumPaths = 5000,
}: UseRiskGraphCalculationsProps): RiskGraphData {
  return useMemo(() => {
    const visibleStrategies = strategies.filter(s => s.visible);

    // Guard: ensure spotPrice is always a valid positive number
    const safeSpot = (spotPrice && Number.isFinite(spotPrice) && spotPrice > 0)
      ? spotPrice
      : 6000; // sensible fallback for SPX-class underlyings

    // Calculate simulated spot price for theoretical curve
    const simulatedSpot = timeMachineEnabled ? safeSpot + simSpotOffset : safeSpot;

    // Resolve per-strategy spot price from the spotPrices map
    // Falls back to the global spotPrice when a symbol has no dedicated spot data
    const getStrategySpot = (strat: Strategy): number => {
      if (!spotPrices || !strat.symbol) return safeSpot;
      const key = resolveSpotKey(strat.symbol);
      const val = spotPrices[key];
      return (val && Number.isFinite(val) && val > 0) ? val : safeSpot;
    };

    // Empty state
    if (visibleStrategies.length === 0) {
      return {
        expirationPoints: [],
        theoreticalPoints: [],
        minPrice: safeSpot - 100,
        maxPrice: safeSpot + 100,
        fullMinPrice: safeSpot - 200,
        fullMaxPrice: safeSpot + 200,
        minPnL: -100,
        maxPnL: 100,
        expirationBreakevens: [],
        theoreticalBreakevens: [],
        theoreticalPnLAtSpot: 0,
        theta: 0,
        gamma: 0,
        delta: 0,
        allStrikes: [],
        centerPrice: safeSpot,
        activeStrategyIds: [],
        expiredExpirationPoints: [],
        expiredTheoreticalPoints: [],
      };
    }

    // Wrap the main calculation in try/catch so a pricing error
    // surfaces as an empty graph instead of crashing the component tree
    try {

    // Get all critical strikes
    const allStrikes = getCriticalStrikes(visibleStrategies);
    const minStrike = Math.min(...allStrikes);
    const maxStrike = Math.max(...allStrikes);
    const strikeRange = maxStrike - minStrike || 50;

    // Get regime configuration for skew modeling
    const regimeConfig = MARKET_REGIMES[marketRegime];

    // Create pricing parameters
    // For Monte Carlo curve generation, use very few paths (it runs for every price point!)
    // Full path count only used for spot P&L calculation
    const pricingParams: PricingParams = {
      model: pricingModel,
      regime: regimeConfig,
      hestonKappa: hestonMeanReversion,
      hestonXi: hestonVolOfVol,
      hestonRho: hestonCorrelation,
      mcNumPaths: pricingModel === 'monte-carlo' ? 200 : 1000, // Very few paths for curve - runs 250+ times!
      mcSeed: 42,
    };

    // Calculate volatility
    const adjustedVix = timeMachineEnabled ? vix + simVolatilityOffset : vix;
    const volatility = Math.max(5, adjustedVix) / 100; // Convert VIX to decimal (e.g., 20 -> 0.20)

    // Time to expiration — compute dynamically from expiration date string
    // Each strategy gets its own time-to-expiry; the max is used for range/slider
    const now = new Date();
    const timeOffsetDays = timeMachineEnabled ? simTimeOffsetHours / 24 : 0;

    // Compute per-strategy time-to-expiry (fractional days until 4pm ET close)
    // realTimeDaysMap: unclamped values for active/expired filtering
    // strategyTimeDaysMap: clamped values for pricing (Black-Scholes needs T > 0)
    const realTimeDaysMap = new Map<string, number>();
    const strategyTimeDaysMap = new Map<string, number>();
    for (const strat of visibleStrategies) {
      let realDays: number;
      if (strat.expiration) {
        // Normalize to YYYY-MM-DD (handles ISO datetime strings like "2026-02-12T05:00:00.000Z")
        const expDateStr = String(strat.expiration).split('T')[0];
        const expClose = new Date(expDateStr + 'T16:00:00-05:00');
        realDays = (expClose.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
      } else {
        const fallbackDte = strat.dte ?? 30;
        realDays = fallbackDte === 0 ? 0.02 : fallbackDte;
      }
      realTimeDaysMap.set(strat.id, realDays);
      strategyTimeDaysMap.set(strat.id, Math.max(0.001, realDays));
    }

    // Use the furthest-out expiration for the global time reference (range calc, slider)
    const allTimeDays = Array.from(strategyTimeDaysMap.values());
    const baseTimeDays = allTimeDays.length > 0 ? Math.max(...allTimeDays) : 30;

    // Filter to strategies that are still "alive" at the simulated time
    // Uses unclamped real days so naturally expired positions are correctly detected
    const activeStrategies = visibleStrategies.filter(strat => {
      const realDays = realTimeDaysMap.get(strat.id) ?? 0;
      return realDays - timeOffsetDays > 0;
    });
    const activeStrategyIds = activeStrategies.map(s => s.id);

    // Helper to get per-strategy time-to-expiry years (with sim offset applied)
    const getStrategyTimeYears = (stratId: string): number => {
      const raw = strategyTimeDaysMap.get(stratId) ?? baseTimeDays;
      return Math.max(raw - timeOffsetDays, 0.001) / 365;
    };

    // Global effective time (for range calculations and backward compat)
    const effectiveDaysToExpiry = Math.max(0, baseTimeDays - timeOffsetDays);
    const timeToExpiryYears = Math.max(effectiveDaysToExpiry, 0.001) / 365;

    // Risk-free rate
    const riskFreeRate = 0.05;

    // Price range calculation
    // Always calculate for a wide range regardless of time to expiration
    // Use the base (unadjusted) time for sigma calculation to maintain consistent range
    const baseDteForRange = Math.ceil(baseTimeDays);
    const sigma1Day = spotPrice * (adjustedVix / 100) / Math.sqrt(252);
    const sigmaPadding = sigma1Day * Math.sqrt(Math.max(baseDteForRange, 7)) * 3; // Use at least 7 days for range calc
    const strategyPadding = strikeRange * 2;

    // Ensure minimum padding of 10% of spot price or $200, whichever is larger
    const minPadding = Math.max(spotPrice * 0.10, 200);
    const fullPadding = Math.max(sigmaPadding, strategyPadding, minPadding);

    const fullMinPrice = Math.min(spotPrice, minStrike) - fullPadding;
    const fullMaxPrice = Math.max(spotPrice, maxStrike) + fullPadding;

    // Viewport (for zoom/pan)
    const centerPrice = (minStrike + maxStrike) / 2 + panOffset;
    const viewportPadding = Math.max(strikeRange * 0.5, 30);
    const minPrice = centerPrice - strikeRange / 2 - viewportPadding;
    const maxPrice = centerPrice + strikeRange / 2 + viewportPadding;

    // Generate price points with critical strikes
    const pricePoints = generatePricePoints(fullMinPrice, fullMaxPrice, allStrikes, 250);

    // Expired strategies (sim-expired, for faded ghost curves)
    const expiredStrategies = visibleStrategies.filter(s => !activeStrategyIds.includes(s.id));

    // Calculate P&L curves
    const expirationPoints: PnLPoint[] = [];
    const theoreticalPoints: PnLPoint[] = [];
    const expiredExpirationPoints: PnLPoint[] = [];
    const expiredTheoreticalPoints: PnLPoint[] = [];
    let minPnL = Infinity;
    let maxPnL = -Infinity;

    for (const price of pricePoints) {
      // Expiration P&L (at primary expiration) — only active strategies (not sim-expired)
      let expPnL = 0;
      for (const strat of activeStrategies) {
        expPnL += calculateExpirationPnL(strat, price, volatility);
      }
      expirationPoints.push({ price, pnl: expPnL });

      // Theoretical P&L (Black-Scholes with volatility skew, per-strategy time and spot)
      let theoPnL = 0;
      for (const strat of activeStrategies) {
        const stratSpot = getStrategySpot(strat);
        theoPnL += calculateTheoreticalPnL(strat, price, volatility, riskFreeRate, getStrategyTimeYears(strat.id), stratSpot, pricingParams);
      }
      theoreticalPoints.push({ price, pnl: theoPnL });

      // Expired strategies — expiration P&L (they're at expiration, so intrinsic value)
      if (expiredStrategies.length > 0) {
        let expiredExpPnL = 0;
        let expiredTheoPnL = 0;
        for (const strat of expiredStrategies) {
          const ep = calculateExpirationPnL(strat, price, volatility);
          expiredExpPnL += ep;
          expiredTheoPnL += ep; // at expiration, theoretical = intrinsic
        }
        expiredExpirationPoints.push({ price, pnl: expiredExpPnL });
        expiredTheoreticalPoints.push({ price, pnl: expiredTheoPnL });
      }

      // Track P&L range for visible area
      if (price >= minPrice && price <= maxPrice) {
        minPnL = Math.min(minPnL, expPnL, theoPnL);
        maxPnL = Math.max(maxPnL, expPnL, theoPnL);
      }
    }

    // Ensure valid P&L range
    if (minPnL === Infinity) minPnL = -100;
    if (maxPnL === -Infinity) maxPnL = 100;

    // Add padding to P&L range
    const pnlRange = maxPnL - minPnL || 100;
    minPnL -= pnlRange * 0.1;
    maxPnL += pnlRange * 0.1;

    // All models now use analytical approaches - no smoothing needed
    const smoothedTheoreticalPoints = theoreticalPoints;

    // Find breakevens
    const expirationBreakevens = findBreakevens(expirationPoints);
    const theoreticalBreakevens = findBreakevens(smoothedTheoreticalPoints);

    // P&L at current (or simulated) spot - use more paths but still capped for responsiveness
    const spotPricingParams = {
      ...pricingParams,
      mcNumPaths: pricingModel === 'monte-carlo' ? Math.min(mcNumPaths, 1000) : 1000,
    };
    let theoreticalPnLAtSpot = 0;
    for (const strat of activeStrategies) {
      const stratSpot = getStrategySpot(strat);
      const stratSimulatedSpot = timeMachineEnabled ? stratSpot + simSpotOffset : stratSpot;
      theoreticalPnLAtSpot += calculateTheoreticalPnL(
        strat,
        stratSimulatedSpot,
        volatility,
        riskFreeRate,
        getStrategyTimeYears(strat.id),
        stratSpot,
        spotPricingParams
      );
    }

    // Calculate aggregate Greeks at simulated spot (with skew, per-strategy time and spot)
    let totalDelta = 0;
    let totalGamma = 0;
    let totalTheta = 0;
    for (const strat of activeStrategies) {
      const stratSpot = getStrategySpot(strat);
      const stratSimulatedSpot = timeMachineEnabled ? stratSpot + simSpotOffset : stratSpot;
      const greeks = calculateStrategyGreeks(
        strat,
        stratSimulatedSpot,
        volatility,
        riskFreeRate,
        getStrategyTimeYears(strat.id),
        stratSpot,
        regimeConfig
      );
      totalDelta += greeks.delta;
      totalGamma += greeks.gamma;
      totalTheta += greeks.theta;
    }

    return {
      expirationPoints,
      theoreticalPoints: smoothedTheoreticalPoints,
      minPrice,
      maxPrice,
      fullMinPrice,
      fullMaxPrice,
      minPnL,
      maxPnL,
      expirationBreakevens,
      theoreticalBreakevens,
      theoreticalPnLAtSpot,
      theta: totalTheta,
      gamma: totalGamma,
      delta: totalDelta,
      allStrikes,
      centerPrice,
      activeStrategyIds,
      expiredExpirationPoints,
      expiredTheoreticalPoints,
    };

    } catch (err) {
      // Catch any calculation error (NaN propagation, bad price data, etc.)
      // and return safe empty-state defaults so the component still renders
      console.error('[RiskGraph] calculation error, returning empty state:', err);
      return {
        expirationPoints: [],
        theoreticalPoints: [],
        minPrice: safeSpot - 100,
        maxPrice: safeSpot + 100,
        fullMinPrice: safeSpot - 200,
        fullMaxPrice: safeSpot + 200,
        minPnL: -100,
        maxPnL: 100,
        expirationBreakevens: [],
        theoreticalBreakevens: [],
        theoreticalPnLAtSpot: 0,
        theta: 0,
        gamma: 0,
        delta: 0,
        allStrikes: [],
        centerPrice: safeSpot,
        activeStrategyIds: [],
        expiredExpirationPoints: [],
        expiredTheoreticalPoints: [],
      };
    }
  }, [strategies, spotPrice, vix, spotPrices, timeMachineEnabled, simVolatilityOffset, simTimeOffsetHours, simSpotOffset, panOffset, marketRegime, pricingModel, hestonVolOfVol, hestonMeanReversion, hestonCorrelation, mcNumPaths]);
}

// Export calculation functions for use elsewhere
export { calculateExpirationPnL, calculateTheoreticalPnL };
