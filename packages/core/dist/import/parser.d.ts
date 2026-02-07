/**
 * Script Parser
 *
 * Auto-detects format and parses strategy scripts from various platforms.
 */
import type { ParsedPosition, FormatDetectionResult, ScriptFormat } from './types.js';
/**
 * Detect the format of a strategy script
 */
export declare function detectScriptFormat(script: string): FormatDetectionResult;
/**
 * Parse Tradier format (placeholder for future implementation)
 */
export declare function parseTradierScript(_script: string): ParsedPosition | null;
/**
 * Auto-detect format and parse script
 */
export declare function parseScript(script: string): ParsedPosition | null;
/**
 * Get example scripts for each format
 */
export declare function getExampleScripts(): Record<ScriptFormat, string[]>;
//# sourceMappingURL=parser.d.ts.map