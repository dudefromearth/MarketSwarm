/**
 * Position Factory
 *
 * Creates Position objects from various inputs (legs, parsed scripts, legacy formats).
 * Handles all derived field computation.
 */
import type { Position, PositionLeg, CostBasisType, ImportMetadata } from './types.js';
/** Input for creating a new position */
export interface CreatePositionInput {
    /** User ID */
    userId: number;
    /** Option symbol (e.g., "SPX") */
    symbol: string;
    /** Underlying instrument (e.g., "I:SPX") */
    underlying?: string;
    /** Individual contract legs */
    legs: PositionLeg[];
    /** Cost basis (absolute value) */
    costBasis?: number;
    /** Cost basis type */
    costBasisType?: CostBasisType;
    /** Whether position is visible in risk graph */
    visible?: boolean;
    /** Sort order in list */
    sortOrder?: number;
    /** Custom color */
    color?: string | null;
    /** Custom label */
    label?: string | null;
    /** Import metadata */
    importMetadata?: ImportMetadata;
}
/** Options for position creation */
export interface CreatePositionOptions {
    /** Custom ID generator (defaults to crypto.randomUUID) */
    generateId?: () => string;
    /** Custom timestamp (defaults to Date.now) */
    now?: number;
}
/**
 * Create a Position from legs
 *
 * This is the primary factory function. It:
 * 1. Recognizes the position type from the legs
 * 2. Computes derived fields (strike, width, dte, expiration)
 * 3. Sets timestamps
 * 4. Returns a complete Position object
 */
export declare function createPosition(input: CreatePositionInput, options?: CreatePositionOptions): Position;
/** Input for legacy strategy format */
export interface LegacyStrategyInput {
    userId: number;
    symbol: string;
    underlying?: string;
    strategy: 'single' | 'vertical' | 'butterfly';
    side: 'call' | 'put';
    strike: number;
    width: number;
    expiration: string;
    debit?: number | null;
    visible?: boolean;
    sortOrder?: number;
    color?: string | null;
    label?: string | null;
}
/**
 * Create a Position from legacy strategy format
 *
 * Converts strike/width format to legs, then creates a Position.
 */
export declare function createPositionFromLegacy(input: LegacyStrategyInput, options?: CreatePositionOptions): Position;
/**
 * Update derived fields after legs change
 *
 * Call this when modifying legs to recompute type, strike, width, etc.
 */
export declare function updateDerivedFields(position: Position, now?: number): Position;
/**
 * Clone a position with new legs
 *
 * Creates a copy with updated legs and recomputed derived fields.
 */
export declare function cloneWithLegs(position: Position, legs: PositionLeg[], now?: number): Position;
/**
 * Convert Position back to legacy format
 *
 * For backward compatibility with existing systems.
 */
export interface LegacyStrategy {
    id: string;
    strategy: 'single' | 'vertical' | 'butterfly';
    side: 'call' | 'put';
    strike: number;
    width: number;
    dte: number;
    expiration: string;
    debit: number | null;
    visible: boolean;
    addedAt: number;
    symbol?: string;
}
export declare function toLegacyFormat(position: Position): LegacyStrategy;
//# sourceMappingURL=factory.d.ts.map