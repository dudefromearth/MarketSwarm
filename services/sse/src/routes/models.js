// services/sse/src/routes/models.js
// REST endpoints for initial model load

import { Router } from "express";
import { getMarketRedis } from "../redis.js";
import { getKeys } from "../keys.js";
import { requireAdmin } from "./admin.js";

const router = Router();

/**
 * Get previous trading day's close from trail data
 * Returns the spot value around 4:00-4:20 PM ET from the previous trading day
 */
async function getPreviousClose(redis, symbol) {
  const keys = getKeys();
  const trailKey = keys.spotTrailKey(symbol);

  // Calculate previous trading day's close time (4:00-4:20 PM ET = 21:00-21:20 UTC)
  const now = new Date();
  const today = new Date(now);
  today.setUTCHours(21, 0, 0, 0); // 4 PM ET in UTC

  // If market hasn't closed yet today, look at yesterday
  // If it's before 4 PM ET, use yesterday. If after, could use today but safer to use yesterday
  let closeDate = new Date(today);
  closeDate.setDate(closeDate.getDate() - 1);

  // Skip weekends (go back to Friday)
  const day = closeDate.getUTCDay();
  if (day === 0) closeDate.setDate(closeDate.getDate() - 2); // Sunday -> Friday
  if (day === 6) closeDate.setDate(closeDate.getDate() - 1); // Saturday -> Friday

  const closeStart = Math.floor(closeDate.getTime() / 1000);
  const closeEnd = closeStart + 1200; // 20 minute window

  try {
    // Get values around market close
    const trailData = await redis.zrangebyscore(trailKey, closeStart, closeEnd);
    if (trailData && trailData.length > 0) {
      // Get the last value in the range (closest to 4:20 PM)
      const lastEntry = JSON.parse(trailData[trailData.length - 1]);
      return lastEntry.value;
    }
  } catch (err) {
    console.error(`[models] getPreviousClose error for ${symbol}:`, err.message);
  }
  return null;
}

// GET /api/models/spot - Current spot prices with change from previous close
router.get("/spot", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const spotKeys = await redis.keys(keys.spotPattern());
    // Filter out :trail keys
    const filteredKeys = spotKeys.filter((k) => !k.endsWith(":trail"));
    const result = {};

    for (const key of filteredKeys) {
      const val = await redis.get(key);
      if (val) {
        // Extract symbol from key like "massive:model:spot:I:SPX" -> "I:SPX"
        const parts = key.split(":");
        const symbol = parts.slice(3).join(":");
        try {
          const spotData = JSON.parse(val);

          // Get previous close and calculate change
          const prevClose = await getPreviousClose(redis, symbol);
          if (prevClose && spotData.value) {
            spotData.prevClose = prevClose;
            spotData.change = spotData.value - prevClose;
            spotData.changePercent = ((spotData.value - prevClose) / prevClose) * 100;
          }

          result[symbol] = spotData;
        } catch {
          result[symbol] = val;
        }
      }
    }

    res.json({ success: true, data: result, ts: Date.now() });
  } catch (err) {
    console.error("[models] /spot error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/candles/:symbol - OHLC candles for Dealer Gravity chart
// Query params: days (default 1, max 7)
router.get("/candles/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const days = Math.min(Math.max(parseInt(req.query.days) || 1, 1), 7); // 1-7 days
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const trailKey = keys.spotTrailKey(symbol);

    // Get trail data for requested number of days
    const now = Math.floor(Date.now() / 1000);
    const startTime = now - (days * 86400);

    const trailRaw = await redis.zrangebyscore(trailKey, startTime, now, 'WITHSCORES');

    if (!trailRaw || trailRaw.length === 0) {
      return res.status(404).json({ success: false, error: `No trail data found for ${symbol}` });
    }

    // Parse trail data
    const trailData = [];
    for (let i = 0; i < trailRaw.length; i += 2) {
      const member = trailRaw[i];
      const score = parseFloat(trailRaw[i + 1]);
      try {
        const data = JSON.parse(member);
        trailData.push({
          value: data.value,
          ts: data.ts || new Date(score * 1000).toISOString(),
        });
      } catch {
        // Skip malformed entries
      }
    }

    if (trailData.length === 0) {
      return res.status(404).json({ success: false, error: `No valid trail data for ${symbol}` });
    }

    // Aggregate into candles
    const BUCKET_SIZES = { '5m': 5 * 60, '10m': 10 * 60, '15m': 15 * 60, '1h': 60 * 60 };

    function aggregateCandles(data, bucketSec) {
      const buckets = new Map();
      for (const point of data) {
        const ts = Math.floor(new Date(point.ts).getTime() / 1000);
        const value = point.value;
        if (typeof value !== 'number' || isNaN(value)) continue;

        const bucketStart = Math.floor(ts / bucketSec) * bucketSec;

        if (!buckets.has(bucketStart)) {
          buckets.set(bucketStart, { t: bucketStart, o: value, h: value, l: value, c: value });
        } else {
          const bucket = buckets.get(bucketStart);
          bucket.h = Math.max(bucket.h, value);
          bucket.l = Math.min(bucket.l, value);
          bucket.c = value;
        }
      }
      return Array.from(buckets.values()).sort((a, b) => a.t - b.t);
    }

    const candles_5m = aggregateCandles(trailData, BUCKET_SIZES['5m']);
    const candles_10m = aggregateCandles(trailData, BUCKET_SIZES['10m']);
    const candles_15m = aggregateCandles(trailData, BUCKET_SIZES['15m']);
    const candles_1h = aggregateCandles(trailData, BUCKET_SIZES['1h']);

    const lastPoint = trailData[trailData.length - 1];

    res.json({
      success: true,
      data: {
        symbol,
        spot: lastPoint.value,
        ts: lastPoint.ts,
        days,
        candles_5m,
        candles_10m,
        candles_15m,
        candles_1h,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error(`[models] /candles/${symbol} error:`, err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/gex/:symbol - Current GEX model
router.get("/gex/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const redis = getMarketRedis();
    const keys = getKeys();

    // GEX models are stored as massive:gex:model:SYMBOL:calls and :puts
    const [callsRaw, putsRaw] = await Promise.all([
      redis.get(keys.gexCallsKey(symbol)),
      redis.get(keys.gexPutsKey(symbol)),
    ]);

    if (!callsRaw && !putsRaw) {
      return res.status(404).json({ success: false, error: `No GEX model found for ${symbol}` });
    }

    const data = {
      symbol,
      calls: callsRaw ? JSON.parse(callsRaw) : null,
      puts: putsRaw ? JSON.parse(putsRaw) : null,
    };

    res.json({ success: true, data, ts: Date.now() });
  } catch (err) {
    console.error(`[models] /gex/${symbol} error:`, err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/heatmap/:symbol/:strategy? - Current heatmap
router.get("/heatmap/:symbol/:strategy?", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  const strategy = req.params.strategy || "latest";
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const key = keys.heatmapKey(symbol, strategy);
    const data = await redis.get(key);

    if (!data) {
      // Try latest as fallback
      const fallbackKey = keys.heatmapLatestKey(symbol);
      const fallbackData = await redis.get(fallbackKey);
      if (!fallbackData) {
        return res.status(404).json({
          success: false,
          error: `No heatmap found for ${symbol}`,
        });
      }
      return res.json({ success: true, data: JSON.parse(fallbackData), ts: Date.now() });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error(`[models] /heatmap/${symbol} error:`, err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/vexy/latest - Latest commentary
router.get("/vexy/latest", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const [epochRaw, eventRaw] = await Promise.all([
      redis.get(keys.vexyEpochKey()),
      redis.get(keys.vexyEventKey()),
    ]);

    const data = {
      epoch: epochRaw ? JSON.parse(epochRaw) : null,
      event: eventRaw ? JSON.parse(eventRaw) : null,
    };

    res.json({ success: true, data, ts: Date.now() });
  } catch (err) {
    console.error("[models] /vexy/latest error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/vexy/history - Today's message history
router.get("/vexy/history", async (req, res) => {
  try {
    const redis = getMarketRedis();

    // Get today's date in UTC
    const today = new Date().toISOString().split('T')[0];
    const historyKey = `vexy:messages:${today}`;

    // Get all messages from today's list
    const messagesRaw = await redis.lrange(historyKey, 0, -1);

    const messages = messagesRaw.map(m => {
      try {
        return JSON.parse(m);
      } catch {
        return null;
      }
    }).filter(Boolean);

    res.json({ success: true, data: messages, ts: Date.now() });
  } catch (err) {
    console.error("[models] /vexy/history error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// DELETE /api/models/vexy/clear - Clear today's messages (admin only)
router.delete("/vexy/clear", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();

    // Get today's date in UTC
    const today = new Date().toISOString().split('T')[0];
    const historyKey = `vexy:messages:${today}`;

    // Clear all vexy keys
    await Promise.all([
      redis.del(historyKey),
      redis.del(keys.vexyEpochKey()),
      redis.del(keys.vexyEventKey()),
    ]);

    console.log("[models] Vexy messages cleared");
    res.json({ success: true, message: "Messages cleared", ts: Date.now() });
  } catch (err) {
    console.error("[models] /vexy/clear error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/market_mode - Market mode model
router.get("/market_mode", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const data = await redis.get(keys.marketModeKey());

    if (!data) {
      return res.status(404).json({ success: false, error: "No market mode model found" });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error("[models] /market_mode error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/vix_regime - VIX regime model
router.get("/vix_regime", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const data = await redis.get(keys.vixRegimeKey());

    if (!data) {
      return res.status(404).json({ success: false, error: "No VIX regime model found" });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error("[models] /vix_regime error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/volume_profile - Volume profile (SPX price levels)
// Query params:
//   min, max: optional price range in dollars
//   mode: "raw" (default, VWAP-based) or "tv" (TradingView distributed smoothing)
router.get("/volume_profile", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();

    // Mode selection: raw (default) or tv (TradingView smoothed)
    const mode = req.query.mode === "tv" ? "tv" : "raw";

    // Get all price levels from hash
    const profileData = await redis.hgetall(keys.volumeProfileKey("spx", mode));
    const metaData = await redis.hgetall(keys.volumeProfileMetaKey());

    if (!profileData || Object.keys(profileData).length === 0) {
      // Try fallback to the other mode if requested mode has no data
      const fallbackMode = mode === "tv" ? "raw" : "tv";
      const fallbackData = await redis.hgetall(keys.volumeProfileKey("spx", fallbackMode));

      if (!fallbackData || Object.keys(fallbackData).length === 0) {
        return res.status(404).json({ success: false, error: "No volume profile data found" });
      }

      // Use fallback data
      console.log(`[models] /volume_profile: ${mode} not found, using ${fallbackMode}`);
      return processVolumeProfile(res, fallbackData, metaData, req.query, fallbackMode);
    }

    return processVolumeProfile(res, profileData, metaData, req.query, mode);
  } catch (err) {
    console.error("[models] /volume_profile error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// Helper function to process and return volume profile data
function processVolumeProfile(res, profileData, metaData, query, mode) {
  // Optional price range filter (in dollars)
  const minPrice = query.min ? parseFloat(query.min) : null;
  const maxPrice = query.max ? parseFloat(query.max) : null;

  // Convert to array format: [{price, volume}, ...]
  // Price is stored as cents, convert to dollars
  const levels = [];
  let maxVolume = 0;

  for (const [priceCents, volume] of Object.entries(profileData)) {
    const priceDollars = parseInt(priceCents) / 100;
    const vol = parseInt(volume);

    // Apply optional filter
    if (minPrice !== null && priceDollars < minPrice) continue;
    if (maxPrice !== null && priceDollars > maxPrice) continue;

    levels.push({ price: priceDollars, volume: vol });
    maxVolume = Math.max(maxVolume, vol);
  }

  // Sort by price descending
  levels.sort((a, b) => b.price - a.price);

  res.json({
    success: true,
    data: {
      levels,
      maxVolume,
      meta: metaData || {},
      count: levels.length,
      mode,
    },
    ts: Date.now(),
  });
}

// GET /api/models/bias_lfi - Bias/LFI model
router.get("/bias_lfi", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const data = await redis.get(keys.biasLfiKey());

    if (!data) {
      return res.status(404).json({ success: false, error: "No bias/LFI model found" });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error("[models] /bias_lfi error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/trade_selector/:symbol - Trade selector recommendations
router.get("/trade_selector/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const redis = getMarketRedis();
    const keys = getKeys();
    const data = await redis.get(keys.tradeSelectorKey(symbol));

    if (!data) {
      return res.status(404).json({ success: false, error: `No trade selector model found for ${symbol}` });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error(`[models] /trade_selector/${symbol} error:`, err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ===========================================================================
// Trade Idea Tracking Endpoints (Admin Only)
// ===========================================================================

// GET /api/models/trade_tracking/stats - Aggregated stats by rank
router.get("/trade_tracking/stats", requireAdmin, async (req, res) => {
  try {
    const redis = getMarketRedis();
    const rawStats = await redis.hgetall("massive:selector:tracking:stats");
    const activeCount = await redis.hlen("massive:selector:tracking:active");
    const historyCount = await redis.llen("massive:selector:tracking:history");

    // Try to get cached totals from massive (fast path)
    let totalCurrentPnl = 0;
    let totalMaxPnl = 0;
    const cachedTotals = await redis.hgetall("massive:selector:tracking:totals");

    if (cachedTotals && cachedTotals.total_current_pnl) {
      // Use cached totals from massive (fast - no parsing needed)
      totalCurrentPnl = parseFloat(cachedTotals.total_current_pnl) || 0;
      totalMaxPnl = parseFloat(cachedTotals.total_max_pnl) || 0;
    } else {
      // Fallback: Calculate from all active trades (slower but works before massive restart)
      const activeRaw = await redis.hgetall("massive:selector:tracking:active");
      for (const tradeJson of Object.values(activeRaw)) {
        try {
          const trade = JSON.parse(tradeJson);
          totalCurrentPnl += parseFloat(trade.current_pnl) || 0;
          totalMaxPnl += parseFloat(trade.max_pnl) || 0;
        } catch {
          // Skip malformed entries
        }
      }
    }

    // Parse stats by rank and calculate historical totals
    const byRank = {};
    let historicalTotalPnl = 0;
    let historicalTotalMaxPnl = 0;
    let historicalTotalWins = 0;
    let historicalTotalCount = 0;

    for (let rank = 1; rank <= 10; rank++) {
      const count = parseInt(rawStats[`rank${rank}:count`] || "0");
      if (count === 0) continue;

      const wins = parseInt(rawStats[`rank${rank}:wins`] || "0");
      const totalPnl = parseFloat(rawStats[`rank${rank}:total_pnl`] || "0");
      const totalMaxPnlRank = parseFloat(rawStats[`rank${rank}:total_max_pnl`] || "0");

      // Accumulate historical totals
      historicalTotalCount += count;
      historicalTotalWins += wins;
      historicalTotalPnl += totalPnl;
      historicalTotalMaxPnl += totalMaxPnlRank;

      byRank[rank] = {
        count,
        wins,
        totalPnl,
        totalMaxPnl: totalMaxPnlRank,
        winRate: count > 0 ? (wins / count * 100).toFixed(1) + "%" : "0%",
        avgPnl: count > 0 ? (totalPnl / count).toFixed(2) : "0.00",
        avgMaxPnl: count > 0 ? (totalMaxPnlRank / count).toFixed(2) : "0.00",
        captureRate: totalMaxPnlRank > 0 ? (totalPnl / totalMaxPnlRank * 100).toFixed(1) + "%" : "0%",
      };
    }

    res.json({
      success: true,
      data: {
        activeCount,
        historyCount,
        // Current/active totals
        totalCurrentPnl,
        totalMaxPnl,
        // Historical/settled totals (from pre-aggregated stats)
        historicalTotalPnl,
        historicalTotalMaxPnl,
        historicalTotalWins,
        historicalTotalCount,
        byRank,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[models] /trade_tracking/stats error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/trade_tracking/active - List of active tracked trades
// Query params: limit (default 100, max 500)
router.get("/trade_tracking/active", requireAdmin, async (req, res) => {
  try {
    const limit = Math.min(Math.max(parseInt(req.query.limit) || 100, 1), 500);
    const redis = getMarketRedis();
    const activeRaw = await redis.hgetall("massive:selector:tracking:active");

    const trades = [];
    for (const [tradeId, tradeJson] of Object.entries(activeRaw)) {
      try {
        const trade = JSON.parse(tradeJson);
        trades.push(trade);
      } catch {
        // Skip malformed entries
      }
    }

    // Sort by entry time descending (newest first)
    trades.sort((a, b) => (b.entry_ts || 0) - (a.entry_ts || 0));

    // Apply limit after sorting
    const limitedTrades = trades.slice(0, limit);

    res.json({
      success: true,
      data: {
        count: limitedTrades.length,
        total: trades.length,
        trades: limitedTrades,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[models] /trade_tracking/active error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/trade_tracking/history - List of settled trades
// Query params: limit (default 100, max 500)
router.get("/trade_tracking/history", requireAdmin, async (req, res) => {
  try {
    const limit = Math.min(Math.max(parseInt(req.query.limit) || 100, 1), 500);
    const redis = getMarketRedis();
    const historyRaw = await redis.lrange("massive:selector:tracking:history", 0, limit - 1);

    const trades = [];
    for (const tradeJson of historyRaw) {
      try {
        const trade = JSON.parse(tradeJson);
        trades.push(trade);
      } catch {
        // Skip malformed entries
      }
    }

    res.json({
      success: true,
      data: {
        count: trades.length,
        trades,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[models] /trade_tracking/history error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
