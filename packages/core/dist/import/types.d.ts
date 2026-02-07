/**
 * Import Types
 *
 * Types for importing positions from various platforms.
 */
import type { PositionLeg, CostBasisType } from '../position/types.js';
/** Supported script formats */
export type ScriptFormat = 'tos' | 'tradier' | 'unknown';
/** Result of parsing a script */
export interface ParsedPosition {
    /** Option symbol */
    symbol: string;
    /** Parsed legs */
    legs: PositionLeg[];
    /** Cost basis amount */
    costBasis?: number;
    /** Cost basis type */
    costBasisType?: CostBasisType;
    /** Original script text */
    rawScript: string;
    /** Detected format */
    format: ScriptFormat;
    /** Any warnings during parsing */
    warnings?: string[];
}
/** Result of format detection */
export interface FormatDetectionResult {
    /** Detected format */
    format: ScriptFormat;
    /** Confidence level 0-1 */
    confidence: number;
    /** Detection hints */
    hints: string[];
}
/** Format display names */
export declare const SCRIPT_FORMAT_NAMES: Record<ScriptFormat, string>;
//# sourceMappingURL=types.d.ts.map