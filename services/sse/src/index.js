// services/sse/src/index.js
// SSE Gateway - Entry point

import express from "express";
import cors from "cors";
import { loadConfig, getFallbackConfig } from "./config.js";
import { initRedis, closeRedis } from "./redis.js";
import { startHeartbeat, stopHeartbeat } from "./heartbeat.js";
import { setConfig as setKeyConfig } from "./keys.js";
import sseRoutes, { startPolling, subscribeVexyPubSub, subscribeHeatmapDiffs, stopPolling, getClientStats } from "./routes/sse.js";
import modelsRoutes from "./routes/models.js";

const app = express();

// CORS for React dev server - permissive for development
app.use(cors());

// Explicit CORS headers for SSE (EventSource requires this)
app.use("/sse", (req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  next();
});

app.use(express.json());

// Health check
app.get("/api/health", (req, res) => {
  const stats = getClientStats();
  res.json({
    status: "healthy",
    service: "sse-gateway",
    ts: Date.now(),
    uptime: process.uptime(),
    ...stats,
  });
});

// Mount routes
app.use("/sse", sseRoutes);
app.use("/api/models", modelsRoutes);

// Graceful shutdown
async function shutdown(signal) {
  console.log(`\n[sse] Received ${signal}, shutting down...`);
  stopPolling();
  stopHeartbeat();
  await closeRedis();
  process.exit(0);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// Main startup
async function main() {
  console.log("═══════════════════════════════════════════════════════");
  console.log(" MarketSwarm – SSE Gateway");
  console.log("═══════════════════════════════════════════════════════");

  let config;
  try {
    config = await loadConfig();
  } catch (err) {
    console.warn(`[sse] Failed to load Truth: ${err.message}`);
    console.warn("[sse] Using fallback configuration");
    config = getFallbackConfig();
  }

  // Initialize key resolver from config
  setKeyConfig(config);

  // Initialize Redis connections
  initRedis(config);

  // Start heartbeat
  startHeartbeat(config, getClientStats);

  // Start polling and pub/sub
  await startPolling(config);
  subscribeVexyPubSub();
  subscribeHeatmapDiffs(["I:SPX", "I:NDX"]);

  // Start server
  const port = config.env.SSE_PORT;
  app.listen(port, () => {
    console.log("═══════════════════════════════════════════════════════");
    console.log(` SSE Gateway listening on http://localhost:${port}`);
    console.log(" Endpoints:");
    console.log(`   GET /api/health           - Health check`);
    console.log(`   GET /api/models/spot      - Current spot prices`);
    console.log(`   GET /api/models/gex/:sym  - Current GEX model`);
    console.log(`   GET /api/models/heatmap/:sym - Current heatmap`);
    console.log(`   GET /api/models/vexy/latest - Latest commentary`);
    console.log(`   GET /sse/spot             - Stream spot prices`);
    console.log(`   GET /sse/gex/:sym         - Stream GEX updates`);
    console.log(`   GET /sse/heatmap/:sym     - Stream heatmap updates`);
    console.log(`   GET /sse/vexy             - Stream commentary`);
    console.log(`   GET /sse/all              - Combined stream`);
    console.log("═══════════════════════════════════════════════════════");
  });
}

main().catch((err) => {
  console.error("[sse] Fatal error:", err);
  process.exit(1);
});
