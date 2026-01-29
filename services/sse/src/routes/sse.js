// services/sse/src/routes/sse.js
// SSE streaming endpoints

import { Router } from "express";
import { getMarketRedis, getMarketRedisSub } from "../redis.js";

const router = Router();

// Client connection tracking
const clients = {
  spot: new Set(),
  gex: new Map(), // symbol -> Set of clients
  heatmap: new Map(), // symbol -> Set of clients
  vexy: new Set(),
  all: new Set(),
};

// Model state cache (for diffing)
const modelState = {
  spot: null,
  gex: new Map(), // symbol -> data
  heatmap: new Map(), // symbol -> data
  vexy: null,
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

// GET /sse/all - Combined stream
router.get("/all", (req, res) => {
  sseHeaders(res);
  clients.all.add(res);

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
  if (modelState.vexy) {
    sendEvent(res, "vexy", modelState.vexy);
  }

  sendEvent(res, "connected", { channel: "all", ts: Date.now() });

  req.on("close", () => {
    clients.all.delete(res);
  });
});

// Broadcast to specific channel clients
function broadcastToChannel(channel, event, data, symbol = null) {
  let targetClients;
  if (symbol && (channel === "gex" || channel === "heatmap")) {
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

// Polling loop for model updates (spot, gex, vexy only - heatmap is event-driven)
let pollingInterval = null;

// One-time initial fetch for heatmap (called at startup)
async function fetchInitialHeatmap(redis) {
  console.log("[sse] Fetching initial heatmap state...");
  try {
    const heatmapKeys = await redis.keys("massive:heatmap:model:*:latest");
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
    try {
      // Poll spot prices (massive:model:spot:SYMBOL, not :trail keys)
      const spotKeys = await redis.keys("massive:model:spot:*");
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
      const gexKeys = await redis.keys("massive:gex:model:*");
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

      // Poll vexy latest (epoch + event)
      const vexyEpoch = await redis.get("vexy:model:playbyplay:epoch:latest");
      const vexyEvent = await redis.get("vexy:model:playbyplay:event:latest");
      const vexyData = {
        epoch: vexyEpoch ? JSON.parse(vexyEpoch) : null,
        event: vexyEvent ? JSON.parse(vexyEvent) : null,
      };
      if (JSON.stringify(vexyData) !== JSON.stringify(modelState.vexy)) {
        modelState.vexy = vexyData;
        broadcastToChannel("vexy", "vexy", vexyData);
      }
    } catch (err) {
      console.error("[sse] Polling error:", err.message);
    }
  };

  // Initial poll
  await poll();

  // Schedule recurring polls
  pollingInterval = setInterval(poll, pollMs);
}

// Subscribe to vexy:playbyplay pub/sub for real-time updates
export function subscribeVexyPubSub() {
  const sub = getMarketRedisSub();

  sub.subscribe("vexy:playbyplay", (err) => {
    if (err) {
      console.error("[sse] Failed to subscribe to vexy:playbyplay:", err.message);
    } else {
      console.log("[sse] Subscribed to vexy:playbyplay");
    }
  });

  sub.on("message", (channel, message) => {
    if (channel === "vexy:playbyplay") {
      try {
        const data = JSON.parse(message);
        // Update state and broadcast
        if (data.kind === "epoch") {
          modelState.vexy = { ...modelState.vexy, epoch: data };
        } else if (data.kind === "event") {
          modelState.vexy = { ...modelState.vexy, event: data };
        }
        broadcastToChannel("vexy", "vexy", modelState.vexy);
      } catch (err) {
        console.error("[sse] vexy:playbyplay parse error:", err.message);
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

  const channels = symbols.map((s) => `massive:heatmap:diff:${s}`);

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

  return {
    clients: {
      spot: clients.spot.size,
      gex: gexCount,
      heatmap: heatmapCount,
      vexy: clients.vexy.size,
      all: clients.all.size,
      total: clients.spot.size + gexCount + heatmapCount + clients.vexy.size + clients.all.size,
    },
  };
}

export default router;
