/**
 * Strategy Recognition for Imported Trades
 *
 * Analyzes leg structure to determine the actual strategy type.
 */

import type { ImportedLeg } from './index';

export interface RecognizedStrategy {
  type: 'single' | 'vertical' | 'butterfly' | 'iron_condor' | 'straddle' | 'strangle' | 'unknown';
  side: 'call' | 'put' | 'both';
  strike: number;        // Center strike for butterfly, long strike for vertical
  width: number;         // Wing width
  direction: 'long' | 'short';
  quantity: number;
}

/**
 * Recognize strategy from a set of legs
 */
export function recognizeStrategy(legs: ImportedLeg[]): RecognizedStrategy {
  if (!legs || legs.length === 0) {
    return { type: 'unknown', side: 'call', strike: 0, width: 0, direction: 'long', quantity: 1 };
  }

  // Single leg
  if (legs.length === 1) {
    const leg = legs[0];
    return {
      type: 'single',
      side: leg.type,
      strike: leg.strike,
      width: 0,
      direction: leg.quantity > 0 ? 'long' : 'short',
      quantity: Math.abs(leg.quantity),
    };
  }

  // Sort legs by strike
  const sorted = [...legs].sort((a, b) => a.strike - b.strike);

  // Check for butterfly (3 legs, same type, evenly spaced)
  if (legs.length === 3) {
    const butterfly = checkButterfly(sorted);
    if (butterfly) return butterfly;
  }

  // Check for vertical (2 legs, same type, different strikes)
  if (legs.length === 2) {
    const vertical = checkVertical(sorted);
    if (vertical) return vertical;
  }

  // Check for iron condor (4 legs, 2 puts + 2 calls)
  if (legs.length === 4) {
    const ironCondor = checkIronCondor(sorted);
    if (ironCondor) return ironCondor;
  }

  // Check for straddle/strangle (2 legs, 1 call + 1 put)
  if (legs.length === 2) {
    const straddleStrangle = checkStraddleStrangle(sorted);
    if (straddleStrangle) return straddleStrangle;
  }

  // Fallback: use first leg info
  return {
    type: 'unknown',
    side: sorted[0].type,
    strike: sorted[0].strike,
    width: 0,
    direction: sorted[0].quantity > 0 ? 'long' : 'short',
    quantity: Math.abs(sorted[0].quantity),
  };
}

/**
 * Check if legs form a butterfly spread
 */
function checkButterfly(sorted: ImportedLeg[]): RecognizedStrategy | null {
  if (sorted.length !== 3) return null;

  const [low, mid, high] = sorted;

  // All same type (all calls or all puts)
  if (low.type !== mid.type || mid.type !== high.type) return null;

  // All same expiration
  if (low.expiration !== mid.expiration || mid.expiration !== high.expiration) return null;

  // Evenly spaced strikes
  const lowToMid = mid.strike - low.strike;
  const midToHigh = high.strike - mid.strike;
  if (Math.abs(lowToMid - midToHigh) > 1) return null; // Allow 1 point tolerance

  // Check quantity pattern
  // Long butterfly: +1, -2, +1 (buy wings, sell body)
  // Short butterfly: -1, +2, -1 (sell wings, buy body)
  const lowQty = low.quantity;
  const midQty = mid.quantity;
  const highQty = high.quantity;

  // Wings should have same sign, body should have opposite sign
  if (Math.sign(lowQty) !== Math.sign(highQty)) return null;
  if (Math.sign(midQty) === Math.sign(lowQty)) return null;

  // Body should be 2x wings (approximately)
  const wingQty = Math.abs(lowQty);
  const bodyQty = Math.abs(midQty);
  if (bodyQty !== wingQty * 2) return null;

  // Long butterfly: long wings (+), short body (-)
  const isLong = lowQty > 0;

  return {
    type: 'butterfly',
    side: low.type,
    strike: mid.strike,  // Center strike
    width: lowToMid,
    direction: isLong ? 'long' : 'short',
    quantity: wingQty,
  };
}

/**
 * Check if legs form a vertical spread
 */
function checkVertical(sorted: ImportedLeg[]): RecognizedStrategy | null {
  if (sorted.length !== 2) return null;

  const [low, high] = sorted;

  // Same type
  if (low.type !== high.type) return null;

  // Same expiration
  if (low.expiration !== high.expiration) return null;

  // Opposite quantities
  if (Math.sign(low.quantity) === Math.sign(high.quantity)) return null;

  // Same absolute quantity
  if (Math.abs(low.quantity) !== Math.abs(high.quantity)) return null;

  const width = high.strike - low.strike;
  const isCall = low.type === 'call';

  // For calls: long lower strike = bull call spread (debit)
  // For puts: long higher strike = bear put spread (debit)
  const longLeg = low.quantity > 0 ? low : high;

  return {
    type: 'vertical',
    side: low.type,
    strike: longLeg.strike,
    width: width,
    direction: 'long', // Debit spread
    quantity: Math.abs(low.quantity),
  };
}

/**
 * Check if legs form an iron condor
 */
function checkIronCondor(sorted: ImportedLeg[]): RecognizedStrategy | null {
  if (sorted.length !== 4) return null;

  // Should have 2 puts and 2 calls
  const puts = sorted.filter(l => l.type === 'put');
  const calls = sorted.filter(l => l.type === 'call');

  if (puts.length !== 2 || calls.length !== 2) return null;

  // All same expiration
  const exp = sorted[0].expiration;
  if (!sorted.every(l => l.expiration === exp)) return null;

  // Put spread: lower strikes, Call spread: higher strikes
  const sortedPuts = puts.sort((a, b) => a.strike - b.strike);
  const sortedCalls = calls.sort((a, b) => a.strike - b.strike);

  // Check vertical structure for each side
  // Long iron condor: sell inner strikes, buy outer strikes
  const putWidth = sortedPuts[1].strike - sortedPuts[0].strike;
  const callWidth = sortedCalls[1].strike - sortedCalls[0].strike;

  return {
    type: 'iron_condor',
    side: 'both',
    strike: (sortedPuts[1].strike + sortedCalls[0].strike) / 2, // Middle
    width: Math.max(putWidth, callWidth),
    direction: sortedPuts[0].quantity > 0 ? 'long' : 'short',
    quantity: Math.abs(sortedPuts[0].quantity),
  };
}

/**
 * Check if legs form a straddle or strangle
 */
function checkStraddleStrangle(sorted: ImportedLeg[]): RecognizedStrategy | null {
  if (sorted.length !== 2) return null;

  const [leg1, leg2] = sorted;

  // One call, one put
  if (leg1.type === leg2.type) return null;

  // Same expiration
  if (leg1.expiration !== leg2.expiration) return null;

  // Same quantity sign (both long or both short)
  if (Math.sign(leg1.quantity) !== Math.sign(leg2.quantity)) return null;

  const isStraddle = leg1.strike === leg2.strike;

  return {
    type: isStraddle ? 'straddle' : 'strangle',
    side: 'both',
    strike: (leg1.strike + leg2.strike) / 2,
    width: Math.abs(leg2.strike - leg1.strike),
    direction: leg1.quantity > 0 ? 'long' : 'short',
    quantity: Math.abs(leg1.quantity),
  };
}
