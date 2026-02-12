// services/sse/src/routes/sse.js
// SSE streaming endpoints

import { Router } from "express";
import { getMarketRedis, getMarketRedisSub } from "../redis.js";
import { getKeys } from "../keys.js";
import { trackUserConnection, untrackUserConnection } from "./admin.js";
import { getCurrentUser } from "../auth.js";
import { getUserProfile } from "../db/userStore.js";

const router = Router();

// Resolve WordPress user ID → internal DB user ID for user-scoped SSE streams.
// Pub/sub dispatchers use the internal DB ID, so clients must register under it.
router.use(async (req, res, next) => {
  const user = getCurrentUser(req);
  const wp = user?.wp;
  if (wp?.issuer && wp?.id) {
    try {
      const profile = await getUserProfile(wp.issuer, wp.id);
      if (profile?.id) {
        req.dbUserId = String(profile.id);
      }
    } catch (e) {
      console.error("[sse] Failed to resolve user ID:", e.message);
    }
  }
  next();
});

// Client connection tracking
const clients = {
  spot: new Set(),
  gex: new Map(), // symbol -> Set of clients
  heatmap: new Map(), // symbol -> Set of clients
  candles: new Map(), // symbol -> Set of clients
  trade_selector: new Map(), // symbol -> Set of clients
  vexy: new Set(),
  bias_lfi: new Set(),
  market_mode: new Set(),
  alerts: new Set(),
  risk_graph: new Map(), // userId -> Set of clients
  trade_log: new Map(), // userId -> Set of clients
  positions: new Map(), // userId -> Set of clients
  logs: new Map(), // userId -> Set of clients (lifecycle events)
  dealer_gravity: new Set(), // Dealer Gravity artifact updates
  vexy_interaction: new Map(), // userId -> Set of clients (interaction progress)
  all: new Set(),
};

// Model state cache (for diffing)
const modelState = {
  spot: null,
  gex: new Map(), // symbol -> data
  heatmap: new Map(), // symbol -> data
  candles: new Map(), // symbol -> { candles_5m, candles_15m, candles_1h, spot, ts }
  trade_selector: new Map(), // symbol -> trade selector model
  vexy: null, // { epoch, event } - combined latest messages
  bias_lfi: null,
  market_mode: null,
  alerts: null, // Latest alerts state
  dealer_gravity: null, // Latest artifact update event
};

// Previous close cache (refreshed daily)
const prevCloseCache = {
  data: new Map(), // symbol -> { value, date }
  lastRefresh: null,
};

/**
 * Get previous trading day's close from trail data (cached)
 */
async function getPrevClose(redis, keys, symbol) {
  const today = new Date().toDateString();

  // Return cached value if from today
  const cached = prevCloseCache.data.get(symbol);
  if (cached && cached.date === today) {
    return cached.value;
  }

  // Calculate previous trading day's close time (4:00-4:20 PM ET = 21:00-21:20 UTC)
  const now = new Date();
  const closeDate = new Date(now);
  closeDate.setUTCHours(21, 0, 0, 0);
  closeDate.setDate(closeDate.getDate() - 1);

  // Skip weekends
  const day = closeDate.getUTCDay();
  if (day === 0) closeDate.setDate(closeDate.getDate() - 2); // Sunday -> Friday
  if (day === 6) closeDate.setDate(closeDate.getDate() - 1); // Saturday -> Friday

  const closeStart = Math.floor(closeDate.getTime() / 1000);
  const closeEnd = closeStart + 1200; // 20 minute window

  try {
    const trailKey = keys.spotTrailKey(symbol);
    const trailData = await redis.zrangebyscore(trailKey, closeStart, closeEnd);
    if (trailData && trailData.length > 0) {
      const lastEntry = JSON.parse(trailData[trailData.length - 1]);
      prevCloseCache.data.set(symbol, { value: lastEntry.value, date: today });
      return lastEntry.value;
    }
  } catch (err) {
    console.error(`[sse] getPrevClose error for ${symbol}:`, err.message);
  }
  return null;
}

// SSE helper - send event to client with backpressure handling
function sendEvent(res, event, data) {
  // Check if socket is writable and not backed up
  if (!res.writable || res.writableEnded) {
    return false;
  }

  // Check buffer size - if too large, skip this update (client is slow)
  const bufferSize = res.writableLength || 0;
  if (bufferSize > 1024 * 1024) { // 1MB buffer limit per client
    return false; // Skip update for slow client
  }

  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
  return true;
}

// SSE headers (including CORS for EventSource)
function sseHeaders(res) {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.flushHeaders();
}

// GET /sse/spot - Real-time spot prices
router.get("/spot", (req, res) => {
  sseHeaders(res);
  clients.spot.add(res);

  // Send current state if available
  if (modelState.spot) {
    sendEvent(res, "spot", modelState.spot);
  }

  sendEvent(res, "connected", { channel: "spot", ts: Date.now() });

  req.on("close", () => {
    clients.spot.delete(res);
  });
});

// GET /sse/gex/:symbol - GEX model updates
router.get("/gex/:symbol", (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  sseHeaders(res);

  if (!clients.gex.has(symbol)) {
    clients.gex.set(symbol, new Set());
  }
  clients.gex.get(symbol).add(res);

  // Send current state if available
  const current = modelState.gex.get(symbol);
  if (current) {
    sendEvent(res, "gex", current);
  }

  sendEvent(res, "connected", { channel: "gex", symbol, ts: Date.now() });

  req.on("close", () => {
    clients.gex.get(symbol)?.delete(res);
  });
});

// GET /sse/heatmap/:symbol - Heatmap tiles
router.get("/heatmap/:symbol", (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  sseHeaders(res);

  if (!clients.heatmap.has(symbol)) {
    clients.heatmap.set(symbol, new Set());
  }
  clients.heatmap.get(symbol).add(res);

  // Send current state if available
  const current = modelState.heatmap.get(symbol);
  if (current) {
    sendEvent(res, "heatmap", current);
  }

  sendEvent(res, "connected", { channel: "heatmap", symbol, ts: Date.now() });

  req.on("close", () => {
    clients.heatmap.get(symbol)?.delete(res);
  });
});

// GET /sse/vexy - Live commentary
router.get("/vexy", (req, res) => {
  sseHeaders(res);
  clients.vexy.add(res);

  // Send current state if available
  if (modelState.vexy) {
    sendEvent(res, "vexy", modelState.vexy);
  }

  sendEvent(res, "connected", { channel: "vexy", ts: Date.now() });

  req.on("close", () => {
    clients.vexy.delete(res);
  });
});

// GET /sse/bias_lfi - Bias/LFI model updates
router.get("/bias_lfi", (req, res) => {
  sseHeaders(res);
  clients.bias_lfi.add(res);

  // Send current state if available
  if (modelState.bias_lfi) {
    sendEvent(res, "bias_lfi", modelState.bias_lfi);
  }

  sendEvent(res, "connected", { channel: "bias_lfi", ts: Date.now() });

  req.on("close", () => {
    clients.bias_lfi.delete(res);
  });
});

// GET /sse/candles/:symbol - OHLC candles for Dealer Gravity chart
router.get("/candles/:symbol", (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  sseHeaders(res);

  if (!clients.candles.has(symbol)) {
    clients.candles.set(symbol, new Set());
  }
  clients.candles.get(symbol).add(res);

  // Send current state if available
  const current = modelState.candles.get(symbol);
  if (current) {
    sendEvent(res, "candles", { symbol, ...current });
  }

  sendEvent(res, "connected", { channel: "candles", symbol, ts: Date.now() });

  req.on("close", () => {
    clients.candles.get(symbol)?.delete(res);
  });
});

// GET /sse/trade_selector/:symbol - Trade recommendations
router.get("/trade_selector/:symbol", (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  sseHeaders(res);

  if (!clients.trade_selector.has(symbol)) {
    clients.trade_selector.set(symbol, new Set());
  }
  clients.trade_selector.get(symbol).add(res);

  // Send current state if available
  const current = modelState.trade_selector.get(symbol);
  if (current) {
    sendEvent(res, "trade_selector", { symbol, ...current });
  }

  sendEvent(res, "connected", { channel: "trade_selector", symbol, ts: Date.now() });

  req.on("close", () => {
    clients.trade_selector.get(symbol)?.delete(res);
  });
});

// GET /sse/all - Combined stream
router.get("/all", (req, res) => {
  sseHeaders(res);
  clients.all.add(res);

  // Track user connection for admin stats
  const sessionId = req.cookies?.ms_session || `anon_${Date.now()}`;
  const user = getCurrentUser(req);
  const displayName = user?.wp?.name || "Anonymous";
  const email = user?.wp?.email || null;
  trackUserConnection(sessionId, displayName, email);

  // Send all current states
  if (modelState.spot) {
    sendEvent(res, "spot", modelState.spot);
  }
  for (const [symbol, data] of modelState.gex) {
    sendEvent(res, "gex", { symbol, ...data });
  }
  for (const [symbol, data] of modelState.heatmap) {
    sendEvent(res, "heatmap", { symbol, ...data });
  }
  for (const [symbol, data] of modelState.candles) {
    sendEvent(res, "candles", { symbol, ...data });
  }
  for (const [symbol, data] of modelState.trade_selector) {
    sendEvent(res, "trade_selector", { symbol, ...data });
  }
  if (modelState.vexy) {
    sendEvent(res, "vexy", modelState.vexy);
  }
  if (modelState.bias_lfi) {
    sendEvent(res, "bias_lfi", modelState.bias_lfi);
  }
  if (modelState.market_mode) {
    sendEvent(res, "market_mode", modelState.market_mode);
  }

  sendEvent(res, "connected", { channel: "all", ts: Date.now() });

  req.on("close", () => {
    clients.all.delete(res);
    untrackUserConnection(sessionId);
  });
});

// GET /sse/alerts - Real-time alert updates
router.get("/alerts", (req, res) => {
  sseHeaders(res);
  clients.alerts.add(res);

  // Send current alerts state if available
  if (modelState.alerts) {
    sendEvent(res, "alerts", modelState.alerts);
  }

  sendEvent(res, "connected", { channel: "alerts", ts: Date.now() });

  req.on("close", () => {
    clients.alerts.delete(res);
  });
});

// GET /sse/risk-graph - User-scoped real-time risk graph updates
router.get("/risk-graph", (req, res) => {
  const userId = req.dbUserId;
  if (!userId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }
  sseHeaders(res);

  // Track this client for user-scoped broadcasting
  if (!clients.risk_graph.has(userId)) {
    clients.risk_graph.set(userId, new Set());
  }
  clients.risk_graph.get(userId).add(res);

  sendEvent(res, "connected", { channel: "risk-graph", userId, ts: Date.now() });

  req.on("close", () => {
    clients.risk_graph.get(userId)?.delete(res);
    // Clean up empty user entry
    if (clients.risk_graph.get(userId)?.size === 0) {
      clients.risk_graph.delete(userId);
    }
  });
});

// GET /sse/trade-log - User-scoped real-time trade log updates
// Supports ?last_seq=N for reconnection to resume from last seen event
router.get("/trade-log", (req, res) => {
  const userId = req.dbUserId;
  if (!userId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }
  const lastSeq = req.query.last_seq ? parseInt(req.query.last_seq, 10) : null;
  sseHeaders(res);

  // Track this client for user-scoped broadcasting
  if (!clients.trade_log.has(userId)) {
    clients.trade_log.set(userId, new Set());
  }
  clients.trade_log.get(userId).add(res);

  sendEvent(res, "connected", {
    channel: "trade-log",
    userId,
    lastSeq,
    ts: Date.now(),
  });

  req.on("close", () => {
    clients.trade_log.get(userId)?.delete(res);
    // Clean up empty user entry
    if (clients.trade_log.get(userId)?.size === 0) {
      clients.trade_log.delete(userId);
    }
  });
});

// GET /sse/positions - User-scoped real-time position updates
// Receives events when positions are created, updated, or deleted
router.get("/positions", (req, res) => {
  const userId = req.dbUserId;
  if (!userId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }
  sseHeaders(res);

  // Track this client for user-scoped broadcasting
  if (!clients.positions.has(userId)) {
    clients.positions.set(userId, new Set());
  }
  clients.positions.get(userId).add(res);

  sendEvent(res, "connected", { channel: "positions", userId, ts: Date.now() });

  req.on("close", () => {
    clients.positions.get(userId)?.delete(res);
    // Clean up empty user entry
    if (clients.positions.get(userId)?.size === 0) {
      clients.positions.delete(userId);
    }
  });
});

// GET /sse/dealer-gravity - Dealer Gravity artifact update events
// Subscribes to artifact_version changes for live UI updates
router.get("/dealer-gravity", (req, res) => {
  sseHeaders(res);
  clients.dealer_gravity.add(res);

  // Send current state if available
  if (modelState.dealer_gravity) {
    sendEvent(res, "dealer_gravity_artifact_updated", modelState.dealer_gravity);
  }

  sendEvent(res, "connected", { channel: "dealer-gravity", ts: Date.now() });

  req.on("close", () => {
    clients.dealer_gravity.delete(res);
  });
});

// GET /sse/logs - User-scoped log lifecycle events
// Receives events when logs are archived, reactivated, retired, etc.
router.get("/logs", (req, res) => {
  const userId = req.dbUserId;
  if (!userId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }
  sseHeaders(res);

  // Track this client for user-scoped broadcasting
  if (!clients.logs.has(userId)) {
    clients.logs.set(userId, new Set());
  }
  clients.logs.get(userId).add(res);

  sendEvent(res, "connected", { channel: "logs", userId, ts: Date.now() });

  req.on("close", () => {
    clients.logs.get(userId)?.delete(res);
    // Clean up empty user entry
    if (clients.logs.get(userId)?.size === 0) {
      clients.logs.delete(userId);
    }
  });
});

// GET /sse/vexy-interaction - User-scoped Vexy interaction progress + results
router.get("/vexy-interaction", (req, res) => {
  const userId = req.dbUserId;
  if (!userId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }
  sseHeaders(res);

  // Track this client for user-scoped broadcasting
  if (!clients.vexy_interaction.has(userId)) {
    clients.vexy_interaction.set(userId, new Set());
  }
  clients.vexy_interaction.get(userId).add(res);

  sendEvent(res, "connected", { channel: "vexy-interaction", userId, ts: Date.now() });

  req.on("close", () => {
    clients.vexy_interaction.get(userId)?.delete(res);
    // Clean up empty user entry
    if (clients.vexy_interaction.get(userId)?.size === 0) {
      clients.vexy_interaction.delete(userId);
    }
  });
});

// Broadcast to specific channel clients
function broadcastToChannel(channel, event, data, symbol = null) {
  let targetClients;
  if (symbol && (channel === "gex" || channel === "heatmap" || channel === "candles" || channel === "trade_selector")) {
    targetClients = clients[channel].get(symbol) || new Set();
  } else {
    targetClients = clients[channel];
  }

  for (const client of targetClients) {
    try {
      sendEvent(client, event, data);
    } catch (err) {
      targetClients.delete(client);
    }
  }

  // Also broadcast to /all clients - create combined object ONCE, not per client
  const allData = symbol ? { symbol, ...data } : data;
  for (const client of clients.all) {
    try {
      sendEvent(client, event, allData);
    } catch (err) {
      clients.all.delete(client);
    }
  }
}

// Candle aggregation helpers
const BUCKET_SIZES = {
  '5m': 5 * 60,
  '15m': 15 * 60,
  '1h': 60 * 60,
};

function aggregateCandles(trailData, bucketSec) {
  // trailData is array of { value, ts } sorted by ts ascending
  if (!trailData || trailData.length === 0) return [];

  const buckets = new Map(); // bucketStart -> { o, h, l, c, t }

  for (const point of trailData) {
    const ts = Math.floor(new Date(point.ts).getTime() / 1000);
    const value = point.value;
    if (typeof value !== 'number' || isNaN(value)) continue;

    const bucketStart = Math.floor(ts / bucketSec) * bucketSec;

    if (!buckets.has(bucketStart)) {
      buckets.set(bucketStart, {
        t: bucketStart,
        o: value,
        h: value,
        l: value,
        c: value,
      });
    } else {
      const bucket = buckets.get(bucketStart);
      bucket.h = Math.max(bucket.h, value);
      bucket.l = Math.min(bucket.l, value);
      bucket.c = value; // Last value becomes close
    }
  }

  // Sort by time and return
  return Array.from(buckets.values()).sort((a, b) => a.t - b.t);
}

async function fetchAndAggregateCandles(redis, symbol) {
  const keys = getKeys();
  const trailKey = keys.spotTrailKey(symbol);

  // Get last 24 hours of trail data (86400 seconds)
  const now = Math.floor(Date.now() / 1000);
  const dayAgo = now - 86400;

  try {
    // ioredis: zrangebyscore returns array with alternating [member, score, member, score...]
    const trailRaw = await redis.zrangebyscore(trailKey, dayAgo, now, 'WITHSCORES');

    if (!trailRaw || trailRaw.length === 0) {
      return null;
    }

    // Parse trail data - ioredis returns [member1, score1, member2, score2, ...]
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

    if (trailData.length === 0) return null;

    // Aggregate into different timeframes
    const candles_5m = aggregateCandles(trailData, BUCKET_SIZES['5m']);
    const candles_15m = aggregateCandles(trailData, BUCKET_SIZES['15m']);
    const candles_1h = aggregateCandles(trailData, BUCKET_SIZES['1h']);

    // Get current spot
    const lastPoint = trailData[trailData.length - 1];

    return {
      spot: lastPoint.value,
      ts: lastPoint.ts,
      candles_5m,
      candles_15m,
      candles_1h,
    };
  } catch (err) {
    console.error(`[sse] Candle aggregation error for ${symbol}:`, err.message);
    return null;
  }
}

// Polling loop for model updates (spot, gex, vexy only - heatmap is event-driven)
let pollingInterval = null;
let candlePollingInterval = null;

// One-time initial fetch for heatmap (called at startup)
async function fetchInitialHeatmap(redis) {
  const keys = getKeys();
  console.log("[sse] Fetching initial heatmap state...");
  try {
    const heatmapKeys = await redis.keys(keys.heatmapPattern());
    for (const key of heatmapKeys) {
      const val = await redis.get(key);
      if (val) {
        try {
          const data = JSON.parse(val);
          const parts = key.split(":");
          parts.pop(); // remove "latest"
          const symbol = parts.slice(3).join(":");
          modelState.heatmap.set(symbol, data);
          console.log(`[sse] Loaded heatmap for ${symbol} (${Object.keys(data.tiles || {}).length} tiles)`);
        } catch (err) {
          // Malformed JSON, skip
        }
      }
    }
  } catch (err) {
    console.error("[sse] Initial heatmap fetch error:", err.message);
  }
}

export async function startPolling(config) {
  const redis = getMarketRedis();
  const pollMs = config.env.SSE_POLL_INTERVAL_MS;

  // Fetch initial heatmap state once (pub/sub handles updates after this)
  await fetchInitialHeatmap(redis);

  console.log(`[sse] Starting model polling for spot/gex/vexy (interval=${pollMs}ms)`);
  console.log(`[sse] Heatmap is event-driven via pub/sub (no polling)`);

  const poll = async () => {
    const keys = getKeys();
    try {
      // Poll spot prices (massive:model:spot:SYMBOL, not :trail keys)
      const spotKeys = await redis.keys(keys.spotPattern());
      const filteredSpotKeys = spotKeys.filter((k) => !k.endsWith(":trail"));
      if (filteredSpotKeys.length > 0) {
        const spotData = {};
        for (const key of filteredSpotKeys) {
          const val = await redis.get(key);
          if (val) {
            const parts = key.split(":");
            const symbol = parts.slice(3).join(":");
            try {
              const parsed = JSON.parse(val);

              // Add change from previous close
              const prevClose = await getPrevClose(redis, keys, symbol);
              if (prevClose && parsed.value) {
                parsed.prevClose = prevClose;
                parsed.change = parsed.value - prevClose;
                parsed.changePercent = ((parsed.value - prevClose) / prevClose) * 100;
              }

              spotData[symbol] = parsed;
            } catch {
              spotData[symbol] = val;
            }
          }
        }
        // Use timestamp check instead of full JSON comparison to reduce memory churn
        const spotChanged = !modelState.spot ||
          Object.keys(spotData).some(sym =>
            !modelState.spot[sym] || modelState.spot[sym].ts !== spotData[sym]?.ts
          );
        if (spotChanged) {
          modelState.spot = spotData;
          broadcastToChannel("spot", "spot", spotData);
        }
      }

      // Poll GEX models (per symbol) - keys like massive:gex:model:I:SPX:calls
      const gexKeys = await redis.keys(keys.gexPattern());
      const gexBySymbol = new Map();
      for (const key of gexKeys) {
        const val = await redis.get(key);
        if (val) {
          try {
            const data = JSON.parse(val);
            const parts = key.split(":");
            const type = parts.pop(); // "calls" or "puts"
            const symbol = parts.slice(3).join(":");
            if (!gexBySymbol.has(symbol)) {
              gexBySymbol.set(symbol, { symbol });
            }
            gexBySymbol.get(symbol)[type] = data;
          } catch (err) {
            // Malformed JSON, skip
          }
        }
      }
      for (const [symbol, data] of gexBySymbol) {
        const prev = modelState.gex.get(symbol);
        // Use timestamp check instead of full JSON comparison
        const gexChanged = !prev ||
          prev.calls?.ts !== data.calls?.ts ||
          prev.puts?.ts !== data.puts?.ts;
        if (gexChanged) {
          modelState.gex.set(symbol, data);
          broadcastToChannel("gex", "gex", data, symbol);
        }
      }

      // Poll vexy (epoch + event latest)
      const vexyEpoch = await redis.get(keys.vexyEpochKey());
      const vexyEvent = await redis.get(keys.vexyEventKey());
      const vexyData = {
        epoch: vexyEpoch ? JSON.parse(vexyEpoch) : null,
        event: vexyEvent ? JSON.parse(vexyEvent) : null,
      };
      // Use timestamp check instead of full JSON comparison
      const vexyChanged = !modelState.vexy ||
        modelState.vexy.epoch?.ts !== vexyData.epoch?.ts ||
        modelState.vexy.event?.ts !== vexyData.event?.ts;
      if (vexyChanged) {
        modelState.vexy = vexyData;
        broadcastToChannel("vexy", "vexy", vexyData);
      }

      // Poll bias_lfi model
      const biasLfiRaw = await redis.get(keys.biasLfiKey());
      if (biasLfiRaw) {
        try {
          const biasLfiData = JSON.parse(biasLfiRaw);
          // Use timestamp check instead of full JSON comparison
          if (!modelState.bias_lfi || modelState.bias_lfi.ts !== biasLfiData.ts) {
            modelState.bias_lfi = biasLfiData;
            broadcastToChannel("bias_lfi", "bias_lfi", biasLfiData);
          }
        } catch {
          // Malformed JSON, skip
        }
      }

      // Poll market_mode model
      const marketModeRaw = await redis.get(keys.marketModeKey());
      if (marketModeRaw) {
        try {
          const marketModeData = JSON.parse(marketModeRaw);
          // Use timestamp check instead of full JSON comparison
          if (!modelState.market_mode || modelState.market_mode.ts !== marketModeData.ts) {
            modelState.market_mode = marketModeData;
            broadcastToChannel("market_mode", "market_mode", marketModeData);
          }
        } catch {
          // Malformed JSON, skip
        }
      }

      // Poll trade_selector models (per symbol)
      const selectorKeys = await redis.keys(keys.tradeSelectorPattern());
      for (const key of selectorKeys) {
        const val = await redis.get(key);
        if (val) {
          try {
            const data = JSON.parse(val);
            const symbol = data.symbol;
            if (symbol) {
              const prev = modelState.trade_selector.get(symbol);
              // Use timestamp check instead of full JSON comparison
              if (!prev || prev.ts !== data.ts) {
                modelState.trade_selector.set(symbol, data);
                broadcastToChannel("trade_selector", "trade_selector", data, symbol);
              }
            }
          } catch {
            // Malformed JSON, skip
          }
        }
      }
    } catch (err) {
      console.error("[sse] Polling error:", err.message);
    }
  };

  // Initial poll
  await poll();

  // Schedule recurring polls
  pollingInterval = setInterval(poll, pollMs);

  // Candle polling (less frequent - every 5 seconds)
  const candlePollMs = config.env.SSE_CANDLE_POLL_INTERVAL_MS || 5000;
  const candleSymbols = ['I:SPX', 'I:NDX', 'SPX', 'NDX']; // Support both formats

  const pollCandles = async () => {
    try {
      for (const symbol of candleSymbols) {
        const candleData = await fetchAndAggregateCandles(redis, symbol);
        if (candleData) {
          // Check if data changed (compare candle counts as quick check)
          const prev = modelState.candles.get(symbol);
          const changed = !prev ||
            prev.candles_5m?.length !== candleData.candles_5m?.length ||
            prev.spot !== candleData.spot;

          if (changed) {
            modelState.candles.set(symbol, candleData);
            broadcastToChannel("candles", "candles", { symbol, ...candleData }, symbol);
          }
        }
      }
    } catch (err) {
      console.error("[sse] Candle polling error:", err.message);
    }
  };

  // Initial candle poll
  await pollCandles();
  console.log(`[sse] Starting candle polling (interval=${candlePollMs}ms)`);

  // Schedule recurring candle polls
  candlePollingInterval = setInterval(pollCandles, candlePollMs);
}

// Subscribe to vexy:playbyplay pub/sub for real-time updates
export function subscribeVexyPubSub() {
  const sub = getMarketRedisSub();
  const keys = getKeys();
  const vexyChannel = keys.vexyChannel();

  console.log(`[sse] Attempting to subscribe to ${vexyChannel} on market-redis...`);
  sub.subscribe(vexyChannel, (err, count) => {
    if (err) {
      console.error(`[sse] Failed to subscribe to ${vexyChannel}:`, err.message);
    } else {
      console.log(`[sse] Subscribed to ${vexyChannel} (${count} total subscriptions)`);
    }
  });

  sub.on("message", (channel, message) => {
    if (channel === vexyChannel) {
      try {
        const data = JSON.parse(message);
        console.log(`[sse] vexy pub/sub received: kind=${data.kind}, clients=${clients.vexy.size}`);
        // Update modelState in place based on kind (avoid object spread)
        if (!modelState.vexy) {
          modelState.vexy = { epoch: null, event: null };
        }
        if (data.kind === "epoch") {
          modelState.vexy.epoch = data;
        } else if (data.kind === "event") {
          modelState.vexy.event = data;
        }
        // Broadcast the updated state
        broadcastToChannel("vexy", "vexy", modelState.vexy);
      } catch (err) {
        console.error("[sse] vexy:playbyplay parse error:", err.message);
      }
    }
  });
}

// Subscribe to alerts:events pub/sub for real-time alert updates
export function subscribeAlertsPubSub() {
  const sub = getMarketRedisSub();
  const keys = getKeys();
  const alertsChannel = keys.alertsChannel();

  sub.subscribe(alertsChannel, (err) => {
    if (err) {
      console.error(`[sse] Failed to subscribe to ${alertsChannel}:`, err.message);
    } else {
      console.log(`[sse] Subscribed to ${alertsChannel}`);
    }
  });

  sub.on("message", (channel, message) => {
    if (channel === alertsChannel) {
      try {
        const event = JSON.parse(message);
        // Events: alert_triggered, alert_updated, alert_added, ai_evaluation
        const eventType = event.type || "alert_update";
        const eventData = event.data || event;

        // Update modelState with latest (overwrite, don't accumulate)
        modelState.alerts = {
          lastEvent: event,
          ts: Date.now(),
        };

        // Broadcast to alert subscribers
        broadcastToChannel("alerts", eventType, eventData);
      } catch (err) {
        console.error("[sse] alerts:events parse error:", err.message);
      }
    }
  });
}

// Subscribe to risk_graph_updates pub/sub for user-scoped real-time sync
export function subscribeRiskGraphPubSub() {
  const sub = getMarketRedisSub();

  // Subscribe to pattern for all user channels
  sub.psubscribe("risk_graph_updates:*", (err, count) => {
    if (err) {
      console.error("[sse] Failed to subscribe to risk_graph_updates:*:", err.message);
    } else {
      console.log(`[sse] Subscribed to risk_graph_updates:* (${count} patterns)`);
    }
  });

  sub.on("pmessage", (pattern, channel, message) => {
    if (pattern === "risk_graph_updates:*") {
      try {
        // Extract userId from channel (risk_graph_updates:123)
        const userId = channel.split(":")[1];
        const event = JSON.parse(message);

        // Get event type and data
        const eventType = event.type || "risk_graph_update";
        const eventData = event.data || event;

        // Broadcast only to this user's connected clients
        const userClients = clients.risk_graph.get(userId);
        if (userClients && userClients.size > 0) {
          for (const client of userClients) {
            try {
              sendEvent(client, eventType, eventData);
            } catch (err) {
              userClients.delete(client);
            }
          }
        }
      } catch (err) {
        console.error("[sse] risk_graph_updates parse error:", err.message);
      }
    }
  });
}

// Subscribe to trade_log_updates pub/sub for user-scoped real-time sync
// Events follow deterministic envelope: { event_id, event_seq, type, aggregate_type, aggregate_id, aggregate_version, occurred_at, payload }
export function subscribeTradeLogPubSub() {
  const sub = getMarketRedisSub();

  // Subscribe to pattern for all user channels
  sub.psubscribe("trade_log_updates:*", (err, count) => {
    if (err) {
      console.error("[sse] Failed to subscribe to trade_log_updates:*:", err.message);
    } else {
      console.log(`[sse] Subscribed to trade_log_updates:* (${count} patterns)`);
    }
  });

  sub.on("pmessage", (pattern, channel, message) => {
    if (pattern === "trade_log_updates:*") {
      try {
        // Extract userId from channel (trade_log_updates:123)
        const userId = channel.split(":")[1];
        const event = JSON.parse(message);

        // Use the event type from the envelope (PositionCreated, FillRecorded, etc.)
        const eventType = event.type || "trade_log_update";

        // Broadcast only to this user's connected clients
        const userClients = clients.trade_log.get(userId);
        if (userClients && userClients.size > 0) {
          for (const client of userClients) {
            try {
              // Send with the specific event type so frontend can use addEventListener
              sendEvent(client, eventType, event);
            } catch (err) {
              userClients.delete(client);
            }
          }
        }
      } catch (err) {
        console.error("[sse] trade_log_updates parse error:", err.message);
      }
    }
  });
}

// Subscribe to dealer_gravity_updated pub/sub for artifact refresh notifications
export function subscribeDealerGravityPubSub() {
  const sub = getMarketRedisSub();
  const channel = "dealer_gravity_updated";

  sub.subscribe(channel, (err) => {
    if (err) {
      console.error(`[sse] Failed to subscribe to ${channel}:`, err.message);
    } else {
      console.log(`[sse] Subscribed to ${channel}`);
    }
  });

  sub.on("message", (ch, message) => {
    if (ch === channel) {
      try {
        const event = JSON.parse(message);
        // Event format: { type, symbol, artifact_version, occurred_at }

        // Update modelState
        modelState.dealer_gravity = event;

        // Broadcast to dealer_gravity subscribers
        for (const client of clients.dealer_gravity) {
          try {
            sendEvent(client, "dealer_gravity_artifact_updated", event);
          } catch (err) {
            clients.dealer_gravity.delete(client);
          }
        }

        // Also broadcast to /all clients
        for (const client of clients.all) {
          try {
            sendEvent(client, "dealer_gravity_artifact_updated", event);
          } catch (err) {
            clients.all.delete(client);
          }
        }

        console.log(`[sse] Dealer Gravity artifact updated: ${event.artifact_version}`);
      } catch (err) {
        console.error("[sse] dealer_gravity_updated parse error:", err.message);
      }
    }
  });
}

// Subscribe to positions:updates pub/sub for user-scoped real-time sync
// Events: position created, updated, deleted, batch_created, reordered
export function subscribePositionsPubSub() {
  const sub = getMarketRedisSub();
  const channel = "positions:updates";

  sub.subscribe(channel, (err) => {
    if (err) {
      console.error(`[sse] Failed to subscribe to ${channel}:`, err.message);
    } else {
      console.log(`[sse] Subscribed to ${channel}`);
    }
  });

  sub.on("message", (ch, message) => {
    if (ch === channel) {
      try {
        const event = JSON.parse(message);
        // Event format: { type: "position", action, userId, position, timestamp }

        const userId = String(event.userId);
        const action = event.action || "updated";
        const eventType = `position_${action}`;

        // Broadcast only to this user's connected clients
        const userClients = clients.positions.get(userId);
        if (userClients && userClients.size > 0) {
          for (const client of userClients) {
            try {
              sendEvent(client, eventType, event);
            } catch (err) {
              userClients.delete(client);
            }
          }
        }
      } catch (err) {
        console.error("[sse] positions:updates parse error:", err.message);
      }
    }
  });
}

// Subscribe to log_lifecycle_updates pub/sub for user-scoped lifecycle events
// Events: log.lifecycle.archived, log.lifecycle.reactivated, log.lifecycle.retire_scheduled,
//         log.lifecycle.retire_cancelled, log.lifecycle.retired
export function subscribeLogLifecyclePubSub() {
  const sub = getMarketRedisSub();
  const channel = "log_lifecycle_updates";

  sub.subscribe(channel, (err) => {
    if (err) {
      console.error(`[sse] Failed to subscribe to ${channel}:`, err.message);
    } else {
      console.log(`[sse] Subscribed to ${channel}`);
    }
  });

  sub.on("message", (ch, message) => {
    if (ch === channel) {
      try {
        const event = JSON.parse(message);
        // Event format: { type, timestamp, user_id, payload }
        // Types: log.lifecycle.archived, log.lifecycle.reactivated, etc.

        const userId = String(event.user_id);
        const eventType = event.type || "log.lifecycle.updated";

        // Broadcast only to this user's connected clients
        const userClients = clients.logs.get(userId);
        if (userClients && userClients.size > 0) {
          console.log(`[sse] Broadcasting ${eventType} to ${userClients.size} clients for user ${userId}`);
          for (const client of userClients) {
            try {
              sendEvent(client, eventType, event);
            } catch (err) {
              userClients.delete(client);
            }
          }
        }
      } catch (err) {
        console.error("[sse] log_lifecycle_updates parse error:", err.message);
      }
    }
  });
}

// Subscribe to vexy_interaction pub/sub for user-scoped interaction progress + results
// Uses psubscribe pattern: vexy_interaction:* (where * is userId)
export function subscribeVexyInteractionPubSub() {
  const sub = getMarketRedisSub();

  sub.psubscribe("vexy_interaction:*", (err, count) => {
    if (err) {
      console.error("[sse] Failed to subscribe to vexy_interaction:*:", err.message);
    } else {
      console.log(`[sse] Subscribed to vexy_interaction:* (${count} patterns)`);
    }
  });

  sub.on("pmessage", (pattern, channel, message) => {
    if (pattern === "vexy_interaction:*") {
      try {
        // Extract userId from channel (vexy_interaction:123)
        const userId = channel.split(":")[1];
        const event = JSON.parse(message);

        // Event types: stage, result, error
        const eventType = `vexy_interaction_${event.event || "update"}`;

        // Broadcast only to this user's connected clients
        const userClients = clients.vexy_interaction.get(userId);
        if (userClients && userClients.size > 0) {
          for (const client of userClients) {
            try {
              sendEvent(client, eventType, event);
            } catch (err) {
              userClients.delete(client);
            }
          }
        }
      } catch (err) {
        console.error("[sse] vexy_interaction parse error:", err.message);
      }
    }
  });
}

// Stats tracking
let diffStats = {
  received: 0,
  lastReceived: null,
  errors: 0,
};

// Max tiles per symbol to prevent unbounded growth
const MAX_TILES_PER_SYMBOL = 5000;

// Periodic stats logging (every 10s)
setInterval(() => {
  const allClients = clients.all.size;
  const lastAgo = diffStats.lastReceived
    ? `${((Date.now() - diffStats.lastReceived) / 1000).toFixed(1)}s ago`
    : 'never';

  // Count tiles for memory monitoring
  let totalTiles = 0;
  for (const [, data] of modelState.heatmap) {
    totalTiles += Object.keys(data.tiles || {}).length;
  }

  const memMB = Math.round(process.memoryUsage().heapUsed / 1024 / 1024);
  console.log(`[sse] STATS: clients=${allClients} diffs=${diffStats.received} tiles=${totalTiles} mem=${memMB}MB last=${lastAgo}`);

  // Reset diff counter periodically to prevent number overflow
  if (diffStats.received > 1000000) {
    diffStats.received = 0;
  }
}, 10000);

// Periodic tile cleanup (every 5 minutes) - remove old/expired tiles
setInterval(() => {
  for (const [symbol, data] of modelState.heatmap) {
    if (data.tiles) {
      const tileCount = Object.keys(data.tiles).length;
      if (tileCount > MAX_TILES_PER_SYMBOL) {
        // Keep only most recent tiles (by DTE - lower DTE = more recent)
        const entries = Object.entries(data.tiles);
        entries.sort((a, b) => (a[1].dte || 999) - (b[1].dte || 999));
        const toKeep = entries.slice(0, MAX_TILES_PER_SYMBOL);
        data.tiles = Object.fromEntries(toKeep);
        console.log(`[sse] Cleaned up ${symbol} tiles: ${tileCount} -> ${toKeep.length}`);
      }
    }
  }

  // Force garbage collection hint (if available)
  if (global.gc) {
    global.gc();
    console.log('[sse] Forced garbage collection');
  }
}, 300000); // 5 minutes

// Subscribe to heatmap diffs for real-time updates
export function subscribeHeatmapDiffs(symbols = ["I:SPX", "I:NDX"]) {
  const sub = getMarketRedisSub();
  const keys = getKeys();

  const channels = symbols.map((s) => keys.heatmapDiffChannel(s));

  sub.subscribe(...channels, (err, count) => {
    if (err) {
      console.error("[sse] Failed to subscribe to heatmap diffs:", err.message);
    } else {
      console.log(`[sse] Subscribed to heatmap diffs: ${channels.join(", ")} (${count} channels)`);
    }
  });

  sub.on("message", (channel, message) => {
    if (channel.startsWith("massive:heatmap:diff:")) {
      diffStats.received++;
      diffStats.lastReceived = Date.now();
      try {
        const diff = JSON.parse(message);
        const symbol = diff.symbol;

        // Update local state with changes - MUTATE IN PLACE to avoid memory churn
        if (modelState.heatmap.has(symbol)) {
          const current = modelState.heatmap.get(symbol);

          // Apply changed tiles directly (no copy)
          if (diff.changed) {
            for (const key in diff.changed) {
              current.tiles[key] = diff.changed[key];
            }
          }

          // Apply removed tiles directly
          if (diff.removed) {
            for (const key of diff.removed) {
              delete current.tiles[key];
            }
          }

          // Update metadata in place
          current.ts = diff.ts;
          current.version = diff.version;
          if (diff.dtes_available) {
            current.dtes_available = diff.dtes_available;
          }
        }

        // Broadcast diff event to clients
        broadcastToChannel("heatmap", "heatmap_diff", diff, symbol);
      } catch (err) {
        console.error("[sse] heatmap diff parse error:", err.message);
      }
    }
  });
}

export function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
    console.log("[sse] Polling stopped");
  }
  if (candlePollingInterval) {
    clearInterval(candlePollingInterval);
    candlePollingInterval = null;
    console.log("[sse] Candle polling stopped");
  }
}

export function getClientStats() {
  let gexCount = 0;
  for (const set of clients.gex.values()) {
    gexCount += set.size;
  }
  let heatmapCount = 0;
  for (const set of clients.heatmap.values()) {
    heatmapCount += set.size;
  }
  let candlesCount = 0;
  for (const set of clients.candles.values()) {
    candlesCount += set.size;
  }
  let tradeSelectorCount = 0;
  for (const set of clients.trade_selector.values()) {
    tradeSelectorCount += set.size;
  }
  let riskGraphCount = 0;
  for (const set of clients.risk_graph.values()) {
    riskGraphCount += set.size;
  }
  let tradeLogCount = 0;
  for (const set of clients.trade_log.values()) {
    tradeLogCount += set.size;
  }
  let positionsCount = 0;
  for (const set of clients.positions.values()) {
    positionsCount += set.size;
  }
  let vexyInteractionCount = 0;
  for (const set of clients.vexy_interaction.values()) {
    vexyInteractionCount += set.size;
  }

  return {
    clients: {
      spot: clients.spot.size,
      gex: gexCount,
      heatmap: heatmapCount,
      candles: candlesCount,
      trade_selector: tradeSelectorCount,
      vexy: clients.vexy.size,
      bias_lfi: clients.bias_lfi.size,
      alerts: clients.alerts.size,
      risk_graph: riskGraphCount,
      trade_log: tradeLogCount,
      positions: positionsCount,
      dealer_gravity: clients.dealer_gravity.size,
      vexy_interaction: vexyInteractionCount,
      all: clients.all.size,
      total: clients.spot.size + gexCount + heatmapCount + candlesCount + tradeSelectorCount + clients.vexy.size + clients.bias_lfi.size + clients.alerts.size + riskGraphCount + tradeLogCount + clients.dealer_gravity.size + vexyInteractionCount + clients.all.size,
    },
  };
}

// Internal endpoint: UI publishes aggregate Greeks for copilot alert evaluation
router.post("/greeks-update", async (req, res) => {
  try {
    const { delta, gamma, theta } = req.body || {};
    if (delta == null && gamma == null && theta == null) {
      return res.status(400).json({ error: "At least one Greek value required" });
    }
    const redis = getMarketRedis();
    const data = JSON.stringify({
      delta: delta ?? 0,
      gamma: gamma ?? 0,
      theta: theta ?? 0,
      ts: Date.now(),
    });
    await redis.set("copilot:greeks:aggregate", data, "EX", 300); // 5 min TTL
    res.json({ ok: true });
  } catch (err) {
    console.error("greeks-update error:", err);
    res.status(500).json({ error: "Failed to publish Greeks" });
  }
});

export default router;
