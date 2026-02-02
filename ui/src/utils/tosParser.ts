/**
 * ToS (ThinkOrSwim) Script Parser
 *
 * Parses ToS order scripts into strategy objects.
 * Supports: Butterfly, Vertical, Single options on SPX.
 */

export interface ParsedStrategy {
  strategy: 'butterfly' | 'vertical' | 'single';
  side: 'call' | 'put';
  strike: number;
  width: number;
  expiration: string;  // ISO format: YYYY-MM-DD
  debit: number | null;
  dte: number;
}

export interface ParseResult {
  success: boolean;
  strategy?: ParsedStrategy;
  error?: string;
}

// Month name to number mapping
const MONTHS: Record<string, number> = {
  'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
  'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
};

/**
 * Parse a ToS order script into a strategy object.
 *
 * Supported formats:
 * - Single: BUY +1 SPX 100 (Weeklys) 31 JAN 26 5000 CALL @10.50
 * - Vertical: BUY +1 VERTICAL SPX 100 (Weeklys) 31 JAN 26 5000/5010 CALL @5.00
 * - Butterfly: BUY +1 BUTTERFLY SPX 100 (Weeklys) 31 JAN 26 4990/5000/5010 CALL @2.50
 */
export function parseTosScript(script: string): ParseResult {
  const normalized = script.trim().toUpperCase();

  if (!normalized) {
    return { success: false, error: 'Empty script' };
  }

  // Determine strategy type
  let strategyType: 'butterfly' | 'vertical' | 'single';

  if (normalized.includes('BUTTERFLY')) {
    strategyType = 'butterfly';
  } else if (normalized.includes('VERTICAL')) {
    strategyType = 'vertical';
  } else {
    strategyType = 'single';
  }

  // Extract side (CALL or PUT)
  let side: 'call' | 'put';
  if (normalized.includes('CALL')) {
    side = 'call';
  } else if (normalized.includes('PUT')) {
    side = 'put';
  } else {
    return { success: false, error: 'Could not determine option type (CALL/PUT)' };
  }

  // Extract price (debit) - optional, format: @XX.XX
  let debit: number | null = null;
  const priceMatch = normalized.match(/@\s*([\d.]+)/);
  if (priceMatch) {
    debit = parseFloat(priceMatch[1]);
    if (isNaN(debit)) debit = null;
  }

  // Extract expiration date - format: DD MMM YY (e.g., 31 JAN 26)
  const dateMatch = normalized.match(/(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{2})/);
  if (!dateMatch) {
    return { success: false, error: 'Could not parse expiration date (expected: DD MMM YY)' };
  }

  const day = parseInt(dateMatch[1]);
  const month = MONTHS[dateMatch[2]];
  const year = 2000 + parseInt(dateMatch[3]);  // Assumes 20XX

  // Format as ISO date
  const expiration = `${year}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`;

  // Calculate DTE
  const expirationDate = new Date(year, month - 1, day);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dte = Math.max(0, Math.ceil((expirationDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)));

  // Extract strikes based on strategy type
  let strike: number;
  let width: number = 0;

  if (strategyType === 'butterfly') {
    // Butterfly format: 4990/5000/5010
    const strikesMatch = normalized.match(/(\d+)\s*\/\s*(\d+)\s*\/\s*(\d+)/);
    if (!strikesMatch) {
      return { success: false, error: 'Could not parse butterfly strikes (expected: lower/middle/upper)' };
    }
    const lower = parseInt(strikesMatch[1]);
    const middle = parseInt(strikesMatch[2]);
    const upper = parseInt(strikesMatch[3]);

    // Validate butterfly structure
    if (middle - lower !== upper - middle) {
      return { success: false, error: 'Invalid butterfly: wings must be equidistant from center' };
    }

    strike = middle;
    width = middle - lower;

  } else if (strategyType === 'vertical') {
    // Vertical format: 5000/5010
    const strikesMatch = normalized.match(/(\d+)\s*\/\s*(\d+)/);
    if (!strikesMatch) {
      return { success: false, error: 'Could not parse vertical strikes (expected: long/short)' };
    }
    const strike1 = parseInt(strikesMatch[1]);
    const strike2 = parseInt(strikesMatch[2]);

    // For calls: long lower, short higher (bull call spread)
    // For puts: long higher, short lower (bear put spread)
    if (side === 'call') {
      strike = Math.min(strike1, strike2);
      width = Math.abs(strike2 - strike1);
    } else {
      strike = Math.max(strike1, strike2);
      width = Math.abs(strike2 - strike1);
    }

  } else {
    // Single option - find a standalone number that looks like a strike
    // Must be after the date and before CALL/PUT
    // Look for a 4-digit number that's not part of a date or other pattern
    const singleStrikeMatch = normalized.match(/\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{2}\s+(\d{3,5})\s+(?:CALL|PUT)/);
    if (!singleStrikeMatch) {
      return { success: false, error: 'Could not parse strike price for single option' };
    }
    strike = parseInt(singleStrikeMatch[1]);
    width = 0;
  }

  // Validate strike
  if (isNaN(strike) || strike <= 0) {
    return { success: false, error: 'Invalid strike price' };
  }

  return {
    success: true,
    strategy: {
      strategy: strategyType,
      side,
      strike,
      width,
      expiration,
      debit,
      dte,
    },
  };
}

/**
 * Validate that a parsed strategy has all required fields.
 */
export function validateStrategy(strategy: ParsedStrategy): string | null {
  if (!strategy.strategy || !['butterfly', 'vertical', 'single'].includes(strategy.strategy)) {
    return 'Invalid strategy type';
  }
  if (!strategy.side || !['call', 'put'].includes(strategy.side)) {
    return 'Invalid side (must be call or put)';
  }
  if (!strategy.strike || strategy.strike <= 0) {
    return 'Invalid strike price';
  }
  if (strategy.strategy !== 'single' && (!strategy.width || strategy.width <= 0)) {
    return 'Width required for vertical and butterfly strategies';
  }
  if (!strategy.expiration) {
    return 'Missing expiration date';
  }
  return null;
}
