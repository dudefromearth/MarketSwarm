// services/sse/src/routes/models.js
// REST endpoints for initial model load

import { Router } from "express";
import { getMarketRedis } from "../redis.js";

const router = Router();

// GET /api/models/spot - Current spot prices
router.get("/spot", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const keys = await redis.keys("massive:model:spot:*");
    // Filter out :trail keys
    const filteredKeys = keys.filter((k) => !k.endsWith(":trail"));
    const result = {};

    for (const key of filteredKeys) {
      const val = await redis.get(key);
      if (val) {
        // Extract symbol from key like "massive:model:spot:I:SPX" -> "I:SPX"
        const parts = key.split(":");
        const symbol = parts.slice(3).join(":");
        try {
          result[symbol] = JSON.parse(val);
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
router.get("/candles/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const redis = getMarketRedis();
    const trailKey = `massive:model:spot:${symbol}:trail`;

    // Get last 24 hours of trail data
    const now = Math.floor(Date.now() / 1000);
    const dayAgo = now - 86400;

    const trailRaw = await redis.zrangebyscore(trailKey, dayAgo, now, 'WITHSCORES');

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
    const BUCKET_SIZES = { '5m': 5 * 60, '15m': 15 * 60, '1h': 60 * 60 };

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
    const candles_15m = aggregateCandles(trailData, BUCKET_SIZES['15m']);
    const candles_1h = aggregateCandles(trailData, BUCKET_SIZES['1h']);

    const lastPoint = trailData[trailData.length - 1];

    res.json({
      success: true,
      data: {
        symbol,
        spot: lastPoint.value,
        ts: lastPoint.ts,
        candles_5m,
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

    // GEX models are stored as massive:gex:model:SYMBOL:calls and :puts
    const [callsRaw, putsRaw] = await Promise.all([
      redis.get(`massive:gex:model:${symbol}:calls`),
      redis.get(`massive:gex:model:${symbol}:puts`),
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
    const key = `massive:heatmap:model:${symbol}:${strategy}`;
    const data = await redis.get(key);

    if (!data) {
      // Try without strategy suffix
      const fallbackKey = `massive:heatmap:model:${symbol}:latest`;
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
    const [epochRaw, eventRaw] = await Promise.all([
      redis.get("vexy:model:playbyplay:epoch:latest"),
      redis.get("vexy:model:playbyplay:event:latest"),
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

// GET /api/models/market_mode - Market mode model
router.get("/market_mode", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const data = await redis.get("massive:market_mode:model:latest");

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
    const data = await redis.get("massive:vix_regime:model:latest");

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
// Query params: min, max (optional price range in dollars)
router.get("/volume_profile", async (req, res) => {
  try {
    const redis = getMarketRedis();

    // Get all price levels from hash
    const profileData = await redis.hgetall("massive:volume_profile:spx");
    const metaData = await redis.hgetall("massive:volume_profile:spx:meta");

    if (!profileData || Object.keys(profileData).length === 0) {
      return res.status(404).json({ success: false, error: "No volume profile data found" });
    }

    // Optional price range filter (in dollars)
    const minPrice = req.query.min ? parseFloat(req.query.min) : null;
    const maxPrice = req.query.max ? parseFloat(req.query.max) : null;

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
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[models] /volume_profile error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// GET /api/models/bias_lfi - Bias/LFI model
router.get("/bias_lfi", async (req, res) => {
  try {
    const redis = getMarketRedis();
    const data = await redis.get("massive:bias_lfi:model:latest");

    if (!data) {
      return res.status(404).json({ success: false, error: "No bias/LFI model found" });
    }

    res.json({ success: true, data: JSON.parse(data), ts: Date.now() });
  } catch (err) {
    console.error("[models] /bias_lfi error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
