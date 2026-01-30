// services/sse/src/index.js
// SSE Gateway - Entry point with WordPress SSO authentication
// Config loaded from Truth (Redis) - no .env files needed

import express from "express";
import cors from "cors";
import cookieParser from "cookie-parser";
import { loadConfig, getFallbackConfig, getConfig } from "./config.js";
import { initRedis, closeRedis } from "./redis.js";
import { startHeartbeat, stopHeartbeat } from "./heartbeat.js";
import { setConfig as setKeyConfig } from "./keys.js";
import sseRoutes, { startPolling, subscribeVexyPubSub, subscribeHeatmapDiffs, stopPolling, getClientStats } from "./routes/sse.js";
import modelsRoutes from "./routes/models.js";
import authRoutes from "./routes/auth.js";
import { authMiddleware, logAuthConfig } from "./auth.js";
import { initDb, closeDb } from "./db/index.js";

const app = express();

// Parse cookies (required for auth)
app.use(cookieParser());

// CORS for React dev server - permissive for development
app.use(cors({
  origin: true, // reflect request origin
  credentials: true, // allow cookies
}));

// Explicit CORS headers for SSE (EventSource requires this)
app.use("/sse", (req, res, next) => {
  const origin = req.headers.origin || "*";
  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Credentials", "true");
  next();
});

app.use(express.json());

// Auth middleware (protects /api/* and /sse/* except auth endpoints)
app.use(authMiddleware());

// Health check (public - allowed by authMiddleware)
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
app.use("/api/auth", authRoutes);
app.use("/api", authRoutes); // Also mount for /api/profile/me
app.use("/sse", sseRoutes);
app.use("/api/models", modelsRoutes);

// Graceful shutdown
async function shutdown(signal) {
  console.log(`\n[sse] Received ${signal}, shutting down...`);
  stopPolling();
  stopHeartbeat();
  await closeRedis();
  await closeDb();
  process.exit(0);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// Main startup
async function main() {
  console.log("═══════════════════════════════════════════════════════");
  console.log(" MarketSwarm – SSE Gateway (with Auth)");
  console.log("═══════════════════════════════════════════════════════");

  // Load config from Truth FIRST (before anything else needs it)
  let config;
  try {
    config = await loadConfig();
  } catch (err) {
    console.warn(`[sse] Failed to load Truth: ${err.message}`);
    console.warn("[sse] Using fallback configuration");
    config = getFallbackConfig();
  }

  // Log auth configuration (now that config is loaded)
  logAuthConfig();

  // Initialize database (now that config is loaded with DATABASE_URL)
  await initDb();

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
    console.log(" Auth Endpoints:");
    console.log(`   GET /api/auth/me            - Check auth status`);
    console.log(`   GET /api/auth/sso?sso=<jwt> - SSO exchange`);
    console.log(`   GET /api/auth/logout        - Clear session`);
    console.log(`   GET /api/auth/debug         - Debug info (dev only)`);
    console.log(" Data Endpoints (protected):");
    console.log(`   GET /api/health             - Health check`);
    console.log(`   GET /api/models/spot        - Current spot prices`);
    console.log(`   GET /api/models/gex/:sym    - Current GEX model`);
    console.log(`   GET /api/models/heatmap/:sym - Current heatmap`);
    console.log(`   GET /api/models/vexy/latest - Latest commentary`);
    console.log(" SSE Streams (protected):");
    console.log(`   GET /sse/spot               - Stream spot prices`);
    console.log(`   GET /sse/gex/:sym           - Stream GEX updates`);
    console.log(`   GET /sse/heatmap/:sym       - Stream heatmap updates`);
    console.log(`   GET /sse/vexy               - Stream commentary`);
    console.log(`   GET /sse/all                - Combined stream`);
    console.log("═══════════════════════════════════════════════════════");

    if (config.env.PUBLIC_MODE) {
      console.log("\n⚠️  WARNING: PUBLIC_MODE is enabled - auth is disabled!");
    }
  });
}

main().catch((err) => {
  console.error("[sse] Fatal error:", err);
  process.exit(1);
});
