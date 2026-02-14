// services/sse/src/routes/options.js
// REST endpoints for option chain data (read-only from market-redis)

import { Router } from "express";
import { getMarketRedis } from "../redis.js";
import { getKeys } from "../keys.js";

const router = Router();

// Ticker root → canonical symbol mapping (matches snapshot_worker.py)
const TICKER_ROOT_MAP = {
  SPX: "I:SPX",
  SPXW: "I:SPX",
  SPXM: "I:SPX",
  NDX: "I:NDX",
  NDXP: "I:NDX",
};

/**
 * Extract the ticker root from an OCC-style option ticker.
 * e.g. "O:SPXW260213C06870000" → "SPXW"
 */
function extractRoot(ticker) {
  // Strip "O:" prefix if present
  const bare = ticker.startsWith("O:") ? ticker.slice(2) : ticker;
  // Root is the alphabetic prefix before the date digits
  const match = bare.match(/^([A-Z]+)/);
  return match ? match[1] : null;
}

/**
 * Extract strike price from the last 8 digits of a ticker.
 * e.g. "O:SPXW260213C06870000" → 6870.0
 */
function extractStrike(ticker) {
  const raw = ticker.slice(-8);
  return parseInt(raw, 10) / 1000;
}

// GET /strikes/:symbol - Get available strikes from the option chain
router.get("/strikes/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const raw = await redis.get(keys.chainLatestKey());

    if (!raw) {
      return res.status(404).json({
        success: false,
        error: "No chain data available",
      });
    }

    const chain = JSON.parse(raw);
    const contracts = chain.contracts;

    if (!contracts || typeof contracts !== "object") {
      return res.status(404).json({
        success: false,
        error: "Chain data has no contracts",
      });
    }

    // Collect strikes for the requested symbol
    const strikeSet = new Set();
    const tickers = Object.keys(contracts);

    for (const ticker of tickers) {
      const root = extractRoot(ticker);
      if (!root) continue;
      const mapped = TICKER_ROOT_MAP[root];
      if (mapped !== symbol) continue;
      const strike = extractStrike(ticker);
      if (strike > 0) strikeSet.add(strike);
    }

    if (strikeSet.size === 0) {
      return res.json({
        success: true,
        symbol,
        strikes: [],
        ts: chain.ts || Date.now(),
      });
    }

    const strikes = Array.from(strikeSet).sort((a, b) => a - b);

    res.json({
      success: true,
      symbol,
      strikes,
      ts: chain.ts || Date.now(),
    });
  } catch (err) {
    console.error(`[options] /strikes/${symbol} error:`, err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
