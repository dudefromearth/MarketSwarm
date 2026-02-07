/**
 * Simulation Module
 *
 * Risk graph and P&L simulation for option positions.
 * Platform-agnostic implementation.
 */
import type { Position, PositionLeg } from '../position/types.js';
import { type Greeks } from '../pricing/index.js';
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
/**
 * Calculate the value of a single leg at a given spot price
 */
export declare function calculateLegValue(leg: PositionLeg, spot: number, volatility: number, riskFreeRate: number, daysRemaining: number): number;
/**
 * Calculate Greeks for a single leg
 */
export declare function calculateLegGreeks(leg: PositionLeg, spot: number, volatility: number, riskFreeRate: number, daysRemaining: number): Greeks;
/**
 * Calculate the total value of a position at a given spot price
 */
export declare function calculatePositionValue(legs: PositionLeg[], spot: number, volatility: number, riskFreeRate: number, daysRemaining: number): number;
/**
 * Calculate aggregate Greeks for a position
 */
export declare function calculatePositionGreeks(legs: PositionLeg[], spot: number, volatility: number, riskFreeRate: number, daysRemaining: number): Greeks;
/**
 * Simulate P&L curve for a position
 */
export declare function simulatePosition(position: Position, params: SimulationParams): SimulationResult;
/**
 * Simulate P&L curve from raw legs (without a full Position object)
 */
export declare function simulateLegs(legs: PositionLeg[], entryDebit: number, dte: number, params: SimulationParams): SimulationResult;
//# sourceMappingURL=index.d.ts.map