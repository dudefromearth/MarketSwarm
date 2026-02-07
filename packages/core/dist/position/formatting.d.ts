/**
 * Position Formatting
 *
 * Utilities for formatting positions for display.
 * Uses TastyTrade/CBOE notation conventions.
 */
import type { PositionLeg, PositionType, PositionDirection } from './types.js';
/**
 * Format a single leg for display
 * Example: "+1 5900C" or "-2 5950P"
 */
export declare function formatLeg(leg: PositionLeg): string;
/**
 * Format all legs as a compact notation string
 * Example: "+1 5880C / -2 5900C / +1 5920C"
 */
export declare function formatLegsDisplay(legs: PositionLeg[]): string;
/**
 * Format the full position label
 * Example: "Long Call Butterfly" or "Short Iron Condor"
 */
export declare function formatPositionLabel(positionType: PositionType, direction: PositionDirection, legs: PositionLeg[]): string;
/** Formatted position parts for flexible layout */
export interface FormattedPosition {
    /** Option symbol */
    symbol: string;
    /** Full label like "Long Call Butterfly" */
    label: string;
    /** Leg notation like "+1 5880C / -2 5900C / +1 5920C" */
    legsNotation: string;
    /** Days to expiration like "7d" */
    dte: string;
    /** Cost basis like "$2.50" */
    debit: string;
    /** Whether the position is asymmetric (BWB) */
    isAsymmetric: boolean;
}
/**
 * Format position for compact list display
 */
export declare function formatPositionForDisplay(symbol: string, positionType: PositionType, direction: PositionDirection, legs: PositionLeg[], dte: number, debit: number | null, isSymmetric?: boolean): FormattedPosition;
/**
 * Get short type code for badge display
 */
export declare function getPositionTypeCode(positionType: PositionType): string;
/**
 * Get badge color for position type
 */
export declare function getPositionTypeColor(positionType: PositionType): string;
/**
 * Get human-readable label for position type
 */
export declare function getPositionTypeLabel(positionType: PositionType): string;
/**
 * Format expiration date for display
 * Example: "Mar 14" or "Mar 14 '25"
 */
export declare function formatExpiration(expiration: string, includeYear?: boolean): string;
/**
 * Check if multiple legs have different expirations
 */
export declare function hasMultipleExpirations(legs: PositionLeg[]): boolean;
/**
 * Get all unique expirations from legs, sorted by date
 */
export declare function getUniqueExpirations(legs: PositionLeg[]): string[];
/**
 * Format a cost basis value with currency symbol
 */
export declare function formatCostBasis(value: number | null, type?: 'debit' | 'credit'): string;
/**
 * Format a price change or P&L value
 */
export declare function formatPnL(value: number): string;
/**
 * Format a percentage value
 */
export declare function formatPercent(value: number, decimals?: number): string;
//# sourceMappingURL=formatting.d.ts.map