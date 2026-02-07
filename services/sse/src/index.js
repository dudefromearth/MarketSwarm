// services/sse/src/index.js
// SSE Gateway - Entry point with WordPress SSO authentication
// Config loaded from Truth (Redis) - no .env files needed

import express from "express";
import cors from "cors";
import cookieParser from "cookie-parser";
import path from "path";
import { fileURLToPath } from "url";
import { loadConfig, getFallbackConfig, getConfig } from "./config.js";
import { initRedis, closeRedis } from "./redis.js";
import { startHeartbeat, stopHeartbeat } from "./heartbeat.js";
import { setConfig as setKeyConfig } from "./keys.js";
import sseRoutes, { startPolling, subscribeVexyPubSub, subscribeHeatmapDiffs, subscribeAlertsPubSub, subscribeRiskGraphPubSub, subscribeTradeLogPubSub, subscribeDealerGravityPubSub, stopPolling, getClientStats } from "./routes/sse.js";
import modelsRoutes from "./routes/models.js";
import authRoutes from "./routes/auth.js";
import adminRoutes, { startActivityTracking, stopActivityTracking } from "./routes/admin.js";
import dealerGravityRoutes from "./routes/dealerGravity.js";
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
app.use("/api/admin", adminRoutes);
app.use("/sse", sseRoutes);
app.use("/api/models", modelsRoutes);
app.use("/api/dealer-gravity", dealerGravityRoutes);

// Proxy journal endpoints to journal service (port 3002)
// This handles /api/logs/*, /api/trades/*, /api/playbooks/*, /api/journals/*
const JOURNAL_SERVICE = "http://localhost:3002";
const journalPaths = ["/api/logs", "/api/trades", "/api/playbooks", "/api/journals", "/api/leaderboard", "/api/orders", "/api/alerts", "/api/symbols", "/api/tags", "/api/settings", "/api/journal", "/api/playbook", "/api/risk-graph", "/api/positions", "/api/journal_entries"];

journalPaths.forEach(path => {
  app.use(path, async (req, res) => {
    const url = `${JOURNAL_SERVICE}${req.originalUrl}`;
    try {
      // Build headers, forwarding versioning/idempotency headers
      const headers = {
        "Content-Type": "application/json",
        // Forward user info for journal service
        "X-User-Id": req.user?.wp?.id || "",
        "X-User-Email": req.user?.wp?.email || "",
        "X-User-Name": req.user?.wp?.name || "",
        "X-User-Issuer": req.user?.wp?.issuer || "",
      };
      // Forward idempotency and versioning headers
      if (req.headers["idempotency-key"]) {
        headers["Idempotency-Key"] = req.headers["idempotency-key"];
      }
      if (req.headers["if-match"]) {
        headers["If-Match"] = req.headers["if-match"];
      }

      const response = await fetch(url, {
        method: req.method,
        headers,
        body: ["GET", "HEAD"].includes(req.method) ? undefined : JSON.stringify(req.body),
      });

      const contentType = response.headers.get("content-type");
      if (contentType?.includes("application/json")) {
        const data = await response.json();
        res.status(response.status).json(data);
      } else {
        const text = await response.text();
        res.status(response.status).send(text);
      }
    } catch (err) {
      console.error(`[proxy] Journal proxy error for ${req.method} ${url}:`, err.message);
      res.status(502).json({ success: false, error: "Journal service unavailable" });
    }
  });
});

// Proxy Vexy AI endpoints to vexy_ai service (port 3005)
// This handles /api/vexy/* including routine-briefing
const VEXY_SERVICE = "http://localhost:3005";

app.use("/api/vexy", async (req, res) => {
  const url = `${VEXY_SERVICE}${req.originalUrl}`;
  try {
    const headers = {
      "Content-Type": "application/json",
      "X-User-Id": req.user?.wp?.id || "",
      "X-User-Email": req.user?.wp?.email || "",
    };

    const response = await fetch(url, {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : JSON.stringify(req.body),
    });

    const contentType = response.headers.get("content-type");
    if (contentType?.includes("application/json")) {
      const data = await response.json();
      res.status(response.status).json(data);
    } else {
      const text = await response.text();
      res.status(response.status).send(text);
    }
  } catch (err) {
    console.error(`[proxy] Vexy proxy error for ${req.method} ${url}:`, err.message);
    res.status(502).json({ success: false, error: "Vexy AI service unavailable" });
  }
});

// Static file serving for production UI build
// Serves from ui/dist - run 'npm run build' in ui/ to generate
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const UI_DIST = path.resolve(__dirname, "../../../ui/dist");

// Serve static files (JS, CSS, images, etc.)
app.use(express.static(UI_DIST));

// SPA fallback - serve index.html for all non-API routes
app.get("*", (req, res) => {
  // Don't serve index.html for API or SSE routes (they should 404 if not matched)
  if (req.path.startsWith("/api/") || req.path.startsWith("/sse/")) {
    return res.status(404).json({ error: "Not found" });
  }
  res.sendFile(path.join(UI_DIST, "index.html"));
});

// Graceful shutdown
async function shutdown(signal) {
  console.log(`\n[sse] Received ${signal}, shutting down...`);
  stopPolling();
  stopHeartbeat();
  stopActivityTracking();
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

  // Start activity tracking (after db is ready)
  console.log("[sse] About to call startActivityTracking...");
  startActivityTracking();
  console.log("[sse] startActivityTracking returned");

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
  subscribeAlertsPubSub();
  subscribeRiskGraphPubSub();
  subscribeTradeLogPubSub();
  subscribeDealerGravityPubSub();

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
    console.log(`   GET /sse/alerts             - Stream alert events`);
    console.log(`   GET /sse/risk-graph         - Stream risk graph sync`);
    console.log(`   GET /sse/trade-log          - Stream trade log events`);
    console.log(`   GET /sse/dealer-gravity     - Stream DG artifact updates`);
    console.log(`   GET /sse/all                - Combined stream`);
    console.log(" Dealer Gravity Endpoints:");
    console.log(`   GET /api/dealer-gravity/artifact  - Visualization artifact`);
    console.log(`   GET /api/dealer-gravity/context   - ML-ready context`);
    console.log(`   GET /api/dealer-gravity/configs   - User DG configs`);
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
