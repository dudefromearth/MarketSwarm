/**
 * ThinkOrSwim Script Parser
 *
 * Parses ToS strategy notation into PositionLeg[].
 *
 * Examples:
 * BUY +1 BUTTERFLY SPX 100 17 JAN 25 5880/5900/5920 CALL @1.20
 * SELL -1 VERTICAL SPX 100 17 JAN 25 5900/5920 PUT @2.50
 * BUY +1 IRON CONDOR SPX 100 19 JAN 25 5800/5850/5950/6000 CALL/PUT @3.80
 */
import type { ParsedPosition } from './types.js';
/**
 * Parse ThinkOrSwim strategy script
 */
export declare function parseTosScript(script: string): ParsedPosition | null;
/**
 * Get example ToS scripts for testing/demo
 */
export declare function getTosExamples(): string[];
//# sourceMappingURL=tos.d.ts.map