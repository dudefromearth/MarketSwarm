/**
 * scriptParsers.ts - Re-exports from @market-swarm/core
 *
 * This file now re-exports script parsing utilities from the
 * shared core package. Kept for backward compatibility with existing imports.
 *
 * @deprecated Import directly from '@market-swarm/core' instead
 */

export {
  // Types
  type ScriptFormat,
  type ParsedPosition,
  type FormatDetectionResult,

  // Constants
  SCRIPT_FORMAT_NAMES,

  // Functions
  detectScriptFormat,
  parseTosScript,
  parseTradierScript,
  parseScript,
  getExampleScripts,
  getTosExamples,
} from '@market-swarm/core';
