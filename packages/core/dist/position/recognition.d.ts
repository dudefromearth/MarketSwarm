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
export declare function recognizePositionType(legs: PositionLeg[]): PositionRecognitionResult;
/**
 * Convert legacy strategy format (strike/width) to legs
 */
export declare function strategyToLegs(strategy: 'single' | 'vertical' | 'butterfly', side: 'call' | 'put', strike: number, width: number, expiration: string): PositionLeg[];
/**
 * Derive center strike from legs (for legacy compatibility)
 */
export declare function getCenterStrike(legs: PositionLeg[]): number;
/**
 * Derive width from legs (for symmetric structures)
 */
export declare function getWidth(legs: PositionLeg[]): number | null;
/**
 * Get primary (earliest) expiration from legs
 */
export declare function getPrimaryExpiration(legs: PositionLeg[]): string;
/**
 * Get dominant side (call or put) from legs
 */
export declare function getDominantSide(legs: PositionLeg[]): 'call' | 'put';
/**
 * Check if all legs have the same expiration
 */
export declare function hasSameExpiration(legs: PositionLeg[]): boolean;
/**
 * Check if all legs have the same option type (all calls or all puts)
 */
export declare function hasSameRight(legs: PositionLeg[]): boolean;
//# sourceMappingURL=recognition.d.ts.map