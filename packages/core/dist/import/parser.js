/**
 * Script Parser
 *
 * Auto-detects format and parses strategy scripts from various platforms.
 */
import { parseTosScript, getTosExamples } from './tos.js';
/**
 * Detect the format of a strategy script
 */
export function detectScriptFormat(script) {
    const trimmed = script.trim();
    // ToS format patterns
    const tosPatterns = [
        /^(BUY|SELL)\s+[+-]?\d+\s+(BUTTERFLY|VERTICAL|SINGLE|IRON\s*CONDOR|CONDOR|STRADDLE|STRANGLE|CALENDAR|DIAGONAL)/i,
        /\d+\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d+/i,
        /(CALL|PUT)\s*@\s*[\d.]+$/i,
        /\d+\/\d+(\/\d+)*/, // Strike notation like 5900/5920 or 5880/5900/5920
    ];
    let tosScore = 0;
    const tosHints = [];
    for (const pattern of tosPatterns) {
        if (pattern.test(trimmed)) {
            tosScore += 0.25;
            tosHints.push(`Matched: ${pattern.source.slice(0, 30)}...`);
        }
    }
    // Tradier format patterns (placeholder)
    const tradierPatterns = [
        /option_symbol/i,
        /class.*option/i,
    ];
    let tradierScore = 0;
    const tradierHints = [];
    for (const pattern of tradierPatterns) {
        if (pattern.test(trimmed)) {
            tradierScore += 0.5;
            tradierHints.push(`Matched Tradier pattern`);
        }
    }
    // Determine best match
    if (tosScore >= 0.5) {
        return { format: 'tos', confidence: Math.min(tosScore, 1), hints: tosHints };
    }
    if (tradierScore >= 0.5) {
        return { format: 'tradier', confidence: Math.min(tradierScore, 1), hints: tradierHints };
    }
    return { format: 'unknown', confidence: 0, hints: ['No recognized format detected'] };
}
/**
 * Parse Tradier format (placeholder for future implementation)
 */
export function parseTradierScript(_script) {
    // TODO: Implement Tradier format parsing
    return null;
}
/**
 * Auto-detect format and parse script
 */
export function parseScript(script) {
    const detection = detectScriptFormat(script);
    switch (detection.format) {
        case 'tos':
            return parseTosScript(script);
        case 'tradier':
            return parseTradierScript(script);
        default:
            // Try ToS as fallback
            const tosResult = parseTosScript(script);
            if (tosResult) {
                tosResult.warnings = tosResult.warnings || [];
                tosResult.warnings.unshift('Format auto-detected as ToS');
                return tosResult;
            }
            return null;
    }
}
/**
 * Get example scripts for each format
 */
export function getExampleScripts() {
    return {
        tos: getTosExamples(),
        tradier: [
            '// Tradier format examples coming soon',
        ],
        unknown: [],
    };
}
//# sourceMappingURL=parser.js.map