/**
 * Core Position Types
 *
 * Platform-agnostic position types using TastyTrade/CBOE conventions.
 * This is the source of truth for all position-related types across
 * web, desktop, and mobile applications.
 */

// ============================================================
// Position Type Taxonomy
// ============================================================

/**
 * All supported position structures
 *
 * Notation reference (TastyTrade/CBOE):
 * - Structure: `1-2-1` (quantities per strike, low→high)
 * - Direction: `+` long, `-` short
 * - Type: `C` call, `P` put
 */
export type PositionType =
  | 'single'         // 1 leg
  | 'vertical'       // 2 legs, same exp, same type (1-1)
  | 'calendar'       // 2 legs, diff exp, same strike
  | 'diagonal'       // 2 legs, diff exp, diff strike
  | 'butterfly'      // 3 legs, symmetric (1-2-1)
  | 'bwb'            // 3 legs, asymmetric broken wing (1-2-1)
  | 'condor'         // 4 legs, same type (1-1-1-1)
  | 'straddle'       // 2 legs, same strike, C+P
  | 'strangle'       // 2 legs, diff strike, C+P
  | 'iron_fly'       // 4 legs, P spread + C spread, middle strikes same
  | 'iron_condor'    // 4 legs, P spread + C spread, all diff strikes
  | 'custom';        // Unrecognized structure

/** Position direction (net long or short) */
export type PositionDirection = 'long' | 'short';

/** Option type */
export type OptionRight = 'call' | 'put';

/** Cost basis type: debit = you pay, credit = you receive */
export type CostBasisType = 'debit' | 'credit';

// ============================================================
// Position Leg
// ============================================================

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

  // Optional fill/trade information
  /** Price per contract at fill */
  fillPrice?: number;
  /** ISO timestamp of fill */
  fillDate?: string;
  /** Commission for this leg */
  commission?: number;
  /** Exchange/regulatory fees */
  fees?: number;
}

// ============================================================
// Position
// ============================================================

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

  // ============================================================
  // Derived from legs (computed by recognizePositionType)
  // ============================================================

  /** Position structure type */
  positionType: PositionType;

  /** Net direction */
  direction: PositionDirection;

  // ============================================================
  // Source of truth: legs
  // ============================================================

  /** Individual contracts that make up this position */
  legs: PositionLeg[];

  // ============================================================
  // Computed convenience fields
  // ============================================================

  /** Earliest expiration across all legs */
  primaryExpiration: string;

  /** Days to primary expiration */
  dte: number;

  /** Center strike (for compatibility with legacy systems) */
  strike: number;

  /** Wing width for symmetric structures (null for asymmetric) */
  width: number | null;

  // ============================================================
  // Cost basis
  // ============================================================

  /** Absolute cost value (always positive) */
  costBasis: number;

  /** Whether this was a debit (paid) or credit (received) */
  costBasisType: CostBasisType;

  // ============================================================
  // Display and organization
  // ============================================================

  /** Whether to show in risk graph */
  visible: boolean;

  /** Order in position list */
  sortOrder: number;

  /** Custom color for risk graph line */
  color: string | null;

  /** Custom label for position */
  label: string | null;

  // ============================================================
  // Import tracking
  // ============================================================

  /** Metadata about import source */
  importMetadata?: ImportMetadata;

  // ============================================================
  // Timestamps
  // ============================================================

  /** When the position was added (epoch ms) */
  addedAt: number;

  /** ISO timestamp of creation */
  createdAt: string;

  /** ISO timestamp of last update */
  updatedAt: string;
}

// ============================================================
// Import Metadata
// ============================================================

/** Supported import sources */
export type ImportSource =
  | 'manual'           // Manually entered
  | 'tos'              // ThinkOrSwim (TD Ameritrade/Schwab)
  | 'tastyworks'       // Tastyworks/Tastytrade
  | 'ibkr'             // Interactive Brokers
  | 'fidelity'         // Fidelity
  | 'etrade'           // E*Trade
  | 'webull'           // Webull
  | 'robinhood'        // Robinhood
  | 'tradier'          // Tradier
  | 'csv'              // Generic CSV import
  | 'api';             // Direct API import

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

// ============================================================
// Display Constants
// ============================================================

/** Human-readable labels for position types */
export const POSITION_TYPE_LABELS: Record<PositionType, string> = {
  single: 'Single',
  vertical: 'Vertical',
  calendar: 'Calendar',
  diagonal: 'Diagonal',
  butterfly: 'Butterfly',
  bwb: 'BWB',
  condor: 'Condor',
  straddle: 'Straddle',
  strangle: 'Strangle',
  iron_fly: 'Iron Fly',
  iron_condor: 'Iron Condor',
  custom: 'Custom',
};

/** Short codes for compact display */
export const POSITION_TYPE_CODES: Record<PositionType, string> = {
  single: 'SGL',
  vertical: 'VS',
  calendar: 'CAL',
  diagonal: 'DIAG',
  butterfly: 'BF',
  bwb: 'BWB',
  condor: 'CDR',
  straddle: 'STR',
  strangle: 'STRG',
  iron_fly: 'IF',
  iron_condor: 'IC',
  custom: 'CUST',
};

/** Badge colors for position types */
export const POSITION_TYPE_COLORS: Record<PositionType, string> = {
  single: '#6b7280',      // gray
  vertical: '#3b82f6',    // blue
  calendar: '#8b5cf6',    // purple
  diagonal: '#a855f7',    // violet
  butterfly: '#22c55e',   // green
  bwb: '#eab308',         // yellow
  condor: '#06b6d4',      // cyan
  straddle: '#f97316',    // orange
  strangle: '#f59e0b',    // amber
  iron_fly: '#ec4899',    // pink
  iron_condor: '#ef4444', // red
  custom: '#9ca3af',      // gray
};
