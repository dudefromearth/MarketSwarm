/**
 * Core Position Types
 *
 * Platform-agnostic position types using TastyTrade/CBOE conventions.
 * This is the source of truth for all position-related types across
 * web, desktop, and mobile applications.
 */
/**
 * All supported position structures
 *
 * Notation reference (TastyTrade/CBOE):
 * - Structure: `1-2-1` (quantities per strike, low→high)
 * - Direction: `+` long, `-` short
 * - Type: `C` call, `P` put
 */
export type PositionType = 'single' | 'vertical' | 'calendar' | 'diagonal' | 'butterfly' | 'bwb' | 'condor' | 'straddle' | 'strangle' | 'iron_fly' | 'iron_condor' | 'custom';
/** Position direction (net long or short) */
export type PositionDirection = 'long' | 'short';
/** Option type */
export type OptionRight = 'call' | 'put';
/** Cost basis type: debit = you pay, credit = you receive */
export type CostBasisType = 'debit' | 'credit';
/**
 * Individual contract leg
 *
 * A position is composed of one or more legs. Each leg represents
 * a single option contract with its strike, expiration, and quantity.
 */
export interface PositionLeg {
    /** Strike price */
    strike: number;
    /** Expiration date (YYYY-MM-DD format) */
    expiration: string;
    /** Option type: call or put */
    right: OptionRight;
    /** Quantity: positive = long, negative = short */
    quantity: number;
    /** Price per contract at fill */
    fillPrice?: number;
    /** ISO timestamp of fill */
    fillDate?: string;
    /** Commission for this leg */
    commission?: number;
    /** Exchange/regulatory fees */
    fees?: number;
}
/**
 * Core Position interface
 *
 * This is the unified position model used across all platforms.
 * Positions are defined by their legs, with other fields computed.
 */
export interface Position {
    /** Unique identifier */
    id: string;
    /** User who owns this position */
    userId: number;
    /** Option symbol (e.g., "SPX") */
    symbol: string;
    /** Underlying instrument (e.g., "I:SPX") */
    underlying: string;
    /** Position structure type */
    positionType: PositionType;
    /** Net direction */
    direction: PositionDirection;
    /** Individual contracts that make up this position */
    legs: PositionLeg[];
    /** Earliest expiration across all legs */
    primaryExpiration: string;
    /** Days to primary expiration */
    dte: number;
    /** Center strike (for compatibility with legacy systems) */
    strike: number;
    /** Wing width for symmetric structures (null for asymmetric) */
    width: number | null;
    /** Absolute cost value (always positive) */
    costBasis: number;
    /** Whether this was a debit (paid) or credit (received) */
    costBasisType: CostBasisType;
    /** Whether to show in risk graph */
    visible: boolean;
    /** Order in position list */
    sortOrder: number;
    /** Custom color for risk graph line */
    color: string | null;
    /** Custom label for position */
    label: string | null;
    /** Metadata about import source */
    importMetadata?: ImportMetadata;
    /** When the position was added (epoch ms) */
    addedAt: number;
    /** ISO timestamp of creation */
    createdAt: string;
    /** ISO timestamp of last update */
    updatedAt: string;
}
/** Supported import sources */
export type ImportSource = 'manual' | 'tos' | 'tastyworks' | 'ibkr' | 'fidelity' | 'etrade' | 'webull' | 'robinhood' | 'tradier' | 'csv' | 'api';
/** Metadata for tracking trade origins */
export interface ImportMetadata {
    /** Source platform */
    source: ImportSource;
    /** When the import occurred */
    importedAt: string;
    /** External order ID from source */
    externalId?: string;
    /** External account ID from source */
    externalAccountId?: string;
    /** Original import data (JSON) */
    rawData?: string;
}
/** Human-readable labels for position types */
export declare const POSITION_TYPE_LABELS: Record<PositionType, string>;
/** Short codes for compact display */
export declare const POSITION_TYPE_CODES: Record<PositionType, string>;
/** Badge colors for position types */
export declare const POSITION_TYPE_COLORS: Record<PositionType, string>;
//# sourceMappingURL=types.d.ts.map