// services/sse/src/routes/sse.js
// SSE streaming endpoints

import { Router } from "express";
import { getMarketRedis, getMarketRedisSub } from "../redis.js";
import { getKeys } from "../keys.js";
import { trackUserConnection, untrackUserConnection } from "./admin.js";
import { getCurrentUser } from "../auth.js";

const router = Router();

// Client connection tracking
const clients = {
  spot: new Set(),
  gex: new Map(), // symbol -> Set of clients
  heatmap: new Map(), // symbol -> Set of clients
  candles: new Map(), // symbol -> Set of clients
  vexy: new Set(),
  bias_lfi: new Set(),
  market_mode: new Set(),
  alerts: new Set(),
  all: new Set(),
};

// Model state cache (for diffing)
const modelState = {
  spot: null,
  gex: new Map(), // symbol -> data
  heatmap: new Map(), // symbol -> data
  candles: new Map(), // symbol -> { candles_5m, candles_15m, candles_1h, spot, ts }
  vexy: null, // { epoch, event } - combined latest messages
  bias_lfi: null,
  market_mode: null,
  alerts: null, // Latest alerts state
};

// SSE helper - send event to client
function sendEvent(res, event, data) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
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

// Broadcast to specific channel clients
function broadcastToChannel(channel, event, data, symbol = null) {
  let targetClients;
  if (symbol && (channel === "gex" || channel === "heatmap" || channel === "candles")) {
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

  // Also broadcast to /all clients
  for (const client of clients.all) {
    try {
      sendEvent(client, event, symbol ? { symbol, ...data } : data);
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
              spotData[symbol] = JSON.parse(val);
            } catch {
              spotData[symbol] = val;
            }
          }
        }
        if (JSON.stringify(spotData) !== JSON.stringify(modelState.spot)) {
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
        if (JSON.stringify(data) !== JSON.stringify(prev)) {
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
      if (JSON.stringify(vexyData) !== JSON.stringify(modelState.vexy)) {
        modelState.vexy = vexyData;
        broadcastToChannel("vexy", "vexy", vexyData);
      }

      // Poll bias_lfi model
      const biasLfiRaw = await redis.get(keys.biasLfiKey());
      if (biasLfiRaw) {
        try {
          const biasLfiData = JSON.parse(biasLfiRaw);
          if (JSON.stringify(biasLfiData) !== JSON.stringify(modelState.bias_lfi)) {
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
          if (JSON.stringify(marketModeData) !== JSON.stringify(modelState.market_mode)) {
            modelState.market_mode = marketModeData;
            broadcastToChannel("market_mode", "market_mode", marketModeData);
          }
        } catch {
          // Malformed JSON, skip
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
    console.log(`[sse] pub/sub message on channel: ${channel}`);
    if (channel === vexyChannel) {
      try {
        const data = JSON.parse(message);
        console.log(`[sse] vexy pub/sub received: kind=${data.kind}, clients=${clients.vexy.size}`);
        // Merge into modelState based on kind
        if (data.kind === "epoch") {
          modelState.vexy = { ...modelState.vexy, epoch: data };
        } else if (data.kind === "event") {
          modelState.vexy = { ...modelState.vexy, event: data };
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

        // Update modelState with latest
        modelState.alerts = {
          ...modelState.alerts,
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

// Stats tracking
let diffStats = {
  received: 0,
  lastReceived: null,
  errors: 0,
};

// Periodic stats logging (every 10s)
setInterval(() => {
  const allClients = clients.all.size;
  const lastAgo = diffStats.lastReceived
    ? `${((Date.now() - diffStats.lastReceived) / 1000).toFixed(1)}s ago`
    : 'never';
  console.log(`[sse] STATS: clients=${allClients} diffs=${diffStats.received} last=${lastAgo}`);
}, 10000);

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

        // Update local state with changes
        if (modelState.heatmap.has(symbol)) {
          const current = modelState.heatmap.get(symbol);
          const updatedTiles = { ...current.tiles };

          // Apply changed tiles
          if (diff.changed) {
            Object.entries(diff.changed).forEach(([key, tile]) => {
              updatedTiles[key] = tile;
            });
          }

          // Apply removed tiles
          if (diff.removed) {
            diff.removed.forEach((key) => {
              delete updatedTiles[key];
            });
          }

          modelState.heatmap.set(symbol, {
            ...current,
            ts: diff.ts,
            version: diff.version,
            tiles: updatedTiles,
            dtes_available: diff.dtes_available || current.dtes_available,
          });
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

  return {
    clients: {
      spot: clients.spot.size,
      gex: gexCount,
      heatmap: heatmapCount,
      candles: candlesCount,
      vexy: clients.vexy.size,
      bias_lfi: clients.bias_lfi.size,
      alerts: clients.alerts.size,
      all: clients.all.size,
      total: clients.spot.size + gexCount + heatmapCount + candlesCount + clients.vexy.size + clients.bias_lfi.size + clients.alerts.size + clients.all.size,
    },
  };
}

export default router;
