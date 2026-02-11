// services/sse/src/routes/admin.js
// Admin API endpoints for user management, stats, and diagnostics

import { Router } from "express";
import { getPool, isDbAvailable } from "../db/index.js";
import { getCurrentUser, isAdmin as checkIsAdmin } from "../auth.js";
import { getMarketRedis, getIntelRedis } from "../redis.js";
import { getKeys } from "../keys.js";

const router = Router();

// Track connected clients with user info
const connectedUsers = new Map(); // sessionId -> { displayName, email, connectedAt }

// Activity tracking interval
const SNAPSHOT_INTERVAL_MS = 15 * 60 * 1000; // 15 minutes
const CLEANUP_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24 hours
const SNAPSHOT_RETENTION_DAYS = 90;

let activitySnapshotInterval = null;
let cleanupInterval = null;

/**
 * Register a connected user (called from SSE routes)
 */
export function trackUserConnection(sessionId, displayName, email = null) {
  connectedUsers.set(sessionId, {
    displayName,
    email,
    connectedAt: new Date(),
  });
  console.log(`[admin] User connected: ${displayName} (${email || sessionId}) - Total: ${connectedUsers.size}`);
}

/**
 * Check if a user is currently online by email
 */
export function isUserOnline(email) {
  if (!email) return false;
  for (const user of connectedUsers.values()) {
    if (user.email === email) return true;
  }
  return false;
}

/**
 * Get list of online emails
 */
export function getOnlineEmails() {
  const emails = new Set();
  for (const user of connectedUsers.values()) {
    if (user.email) emails.add(user.email);
  }
  return emails;
}

/**
 * Unregister a disconnected user
 */
export function untrackUserConnection(sessionId) {
  connectedUsers.delete(sessionId);
  console.log(`[admin] User disconnected: ${sessionId} - Total: ${connectedUsers.size}`);
}

/**
 * Get count of currently connected users
 */
export function getLiveUserCount() {
  return connectedUsers.size;
}

/**
 * Get list of currently connected users
 */
export function getLiveUsers() {
  return Array.from(connectedUsers.values());
}

/**
 * DEBUG ENDPOINT - Test admin without auth
 * GET /api/admin/_debug/test
 * TODO: Remove in production
 */
router.get("/_debug/test", async (req, res) => {
  const startTime = Date.now();
  const results = {
    timestamp: new Date().toISOString(),
    tests: {},
  };

  // Test 1: Database availability
  results.tests.database = { status: "checking" };
  try {
    if (!isDbAvailable()) {
      results.tests.database = { status: "unavailable", error: "Database not available" };
    } else {
      const pool = getPool();
      const [rows] = await pool.execute("SELECT 1 as test");
      results.tests.database = { status: "ok", latencyMs: Date.now() - startTime };
    }
  } catch (err) {
    results.tests.database = { status: "error", error: err.message };
  }

  // Test 2: Stats query
  const statsStart = Date.now();
  results.tests.statsQuery = { status: "checking" };
  try {
    if (isDbAvailable()) {
      const pool = getPool();
      const [last24h] = await pool.execute(`
        SELECT COUNT(DISTINCT id) as count
        FROM users
        WHERE last_login_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
      `);
      results.tests.statsQuery = {
        status: "ok",
        latencyMs: Date.now() - statsStart,
        result: last24h[0]?.count || 0
      };
    } else {
      results.tests.statsQuery = { status: "skipped", reason: "database unavailable" };
    }
  } catch (err) {
    results.tests.statsQuery = { status: "error", error: err.message, latencyMs: Date.now() - statsStart };
  }

  // Test 3: Users query
  const usersStart = Date.now();
  results.tests.usersQuery = { status: "checking" };
  try {
    if (isDbAvailable()) {
      const pool = getPool();
      const [users] = await pool.execute(`SELECT COUNT(*) as count FROM users`);
      results.tests.usersQuery = {
        status: "ok",
        latencyMs: Date.now() - usersStart,
        userCount: users[0]?.count || 0
      };
    } else {
      results.tests.usersQuery = { status: "skipped", reason: "database unavailable" };
    }
  } catch (err) {
    results.tests.usersQuery = { status: "error", error: err.message, latencyMs: Date.now() - usersStart };
  }

  // Test 4: Activity hourly query
  const activityStart = Date.now();
  results.tests.activityQuery = { status: "checking" };
  try {
    if (isDbAvailable()) {
      const pool = getPool();
      const [rows] = await pool.execute(`
        SELECT COUNT(*) as count FROM hourly_activity_aggregates
      `);
      results.tests.activityQuery = {
        status: "ok",
        latencyMs: Date.now() - activityStart,
        rowCount: rows[0]?.count || 0
      };
    } else {
      results.tests.activityQuery = { status: "skipped", reason: "database unavailable" };
    }
  } catch (err) {
    // Table might not exist
    if (err.code === "ER_NO_SUCH_TABLE") {
      results.tests.activityQuery = { status: "ok", latencyMs: Date.now() - activityStart, rowCount: 0, note: "table does not exist yet" };
    } else {
      results.tests.activityQuery = { status: "error", error: err.message, latencyMs: Date.now() - activityStart };
    }
  }

  // Test 5: Live users (memory)
  results.tests.liveUsers = {
    status: "ok",
    count: connectedUsers.size,
    latencyMs: 0
  };

  results.totalLatencyMs = Date.now() - startTime;
  res.json(results);
});

/**
 * DEBUG ENDPOINT - Get stats without auth
 * GET /api/admin/_debug/stats
 */
router.get("/_debug/stats", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }
  const pool = getPool();
  const startTime = Date.now();

  try {
    const [last24h] = await pool.execute(`
      SELECT COUNT(DISTINCT id) as count
      FROM users
      WHERE last_login_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    `);

    const liveUsers = getLiveUsers();
    const liveCount = liveUsers.length;

    const [mostActive] = await pool.execute(`
      SELECT id, display_name, last_login_at
      FROM users
      ORDER BY last_login_at DESC
      LIMIT 5
    `);

    res.json({
      _debug: { latencyMs: Date.now() - startTime },
      loginsLast24h: last24h[0]?.count || 0,
      liveUserCount: liveCount,
      liveUsers: liveUsers.map(u => ({ displayName: u.displayName, connectedAt: u.connectedAt })),
      mostActiveUsers: mostActive,
    });
  } catch (err) {
    console.error("[admin] Error fetching stats:", err);
    res.status(500).json({ error: "Failed to fetch stats", details: err.message });
  }
});

/**
 * DEBUG ENDPOINT - Get users without auth
 * GET /api/admin/_debug/users
 */
router.get("/_debug/users", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }
  const pool = getPool();
  const startTime = Date.now();

  try {
    const [users] = await pool.execute(`
      SELECT
        id, issuer, wp_user_id, email, display_name,
        roles_json, is_admin, subscription_tier,
        created_at, last_login_at
      FROM users
      ORDER BY last_login_at DESC
    `);

    const onlineEmails = getOnlineEmails();
    const parsed = users.map(u => ({
      ...u,
      roles: JSON.parse(u.roles_json || "[]"),
      is_online: onlineEmails.has(u.email),
    }));

    res.json({ _debug: { latencyMs: Date.now() - startTime }, users: parsed, count: parsed.length });
  } catch (err) {
    console.error("[admin] Error fetching users:", err);
    res.status(500).json({ error: "Failed to fetch users", details: err.message });
  }
});

/**
 * DEBUG ENDPOINT - Get activity hourly without auth
 * GET /api/admin/_debug/activity/hourly
 */
router.get("/_debug/activity/hourly", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }
  const pool = getPool();
  const startTime = Date.now();
  const days = parseInt(req.query.days) || 7;

  try {
    const [rows] = await pool.execute(
      `SELECT hour_start, user_count
       FROM hourly_activity_aggregates
       WHERE hour_start >= DATE_SUB(NOW(), INTERVAL ? DAY)
       ORDER BY hour_start ASC`,
      [days]
    );

    const hourlyTotals = {};
    for (let i = 0; i < 24; i++) {
      hourlyTotals[i] = { count: 0, total: 0 };
    }

    rows.forEach((row) => {
      const hour = new Date(row.hour_start).getHours();
      hourlyTotals[hour].count++;
      hourlyTotals[hour].total += row.user_count;
    });

    const busiestHours = Object.entries(hourlyTotals)
      .map(([hour, data]) => ({
        hour: parseInt(hour),
        avgUsers: data.count > 0 ? data.total / data.count : 0,
      }))
      .sort((a, b) => b.avgUsers - a.avgUsers)
      .slice(0, 3);

    res.json({
      _debug: { latencyMs: Date.now() - startTime },
      data: rows.map((r) => ({
        hour_start: r.hour_start,
        user_count: r.user_count,
      })),
      busiestHours,
      days,
    });
  } catch (err) {
    if (err.code === "ER_NO_SUCH_TABLE") {
      return res.json({ _debug: { latencyMs: Date.now() - startTime }, data: [], busiestHours: [], days });
    }
    console.error("[admin] Error fetching hourly activity:", err);
    res.status(500).json({ error: "Failed to fetch activity data", details: err.message });
  }
});

/**
 * Admin middleware - require is_admin = true
 * Exported for use in other route files
 */
export async function requireAdmin(req, res, next) {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }

  // Get user from auth middleware
  const sessionUser = getCurrentUser(req);
  if (!sessionUser) {
    return res.status(401).json({ error: "Not authenticated" });
  }

  // Check admin from session first (fast path)
  if (checkIsAdmin(sessionUser)) {
    return next();
  }

  // Double-check against database
  const pool = getPool();
  try {
    const wpId = sessionUser.wp?.id;
    const issuer = sessionUser.wp?.issuer;

    if (!wpId || !issuer) {
      return res.status(401).json({ error: "Invalid session" });
    }

    const [rows] = await pool.execute(
      "SELECT is_admin FROM users WHERE issuer = ? AND wp_user_id = ?",
      [issuer, wpId]
    );

    if (!rows.length || !rows[0].is_admin) {
      return res.status(403).json({ error: "Admin access required" });
    }

    next();
  } catch (err) {
    console.error("[admin] Error checking admin status:", err);
    res.status(500).json({ error: "Internal server error" });
  }
}

/**
 * GET /api/admin/stats
 * Returns dashboard stats: logins last 24h, live users, most active
 */
router.get("/stats", requireAdmin, async (req, res) => {
  const pool = getPool();

  try {
    // Users logged in last 24 hours
    const [last24h] = await pool.execute(`
      SELECT COUNT(DISTINCT id) as count
      FROM users
      WHERE last_login_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    `);

    // Currently live users (from SSE connections)
    const liveUsers = getLiveUsers();
    const liveCount = liveUsers.length;

    // Most active users (by login count - we'd need a login_count column for real tracking)
    // For now, show users with most recent activity
    const [mostActive] = await pool.execute(`
      SELECT id, display_name, last_login_at
      FROM users
      ORDER BY last_login_at DESC
      LIMIT 5
    `);

    res.json({
      loginsLast24h: last24h[0]?.count || 0,
      liveUserCount: liveCount,
      liveUsers: liveUsers.map(u => ({ displayName: u.displayName, connectedAt: u.connectedAt })),
      mostActiveUsers: mostActive,
    });
  } catch (err) {
    console.error("[admin] Error fetching stats:", err);
    res.status(500).json({ error: "Failed to fetch stats" });
  }
});

/**
 * GET /api/admin/users
 * Returns list of all users with online status
 */
router.get("/users", requireAdmin, async (req, res) => {
  const pool = getPool();

  try {
    const [users] = await pool.execute(`
      SELECT
        id, issuer, wp_user_id, email, display_name,
        roles_json, is_admin, subscription_tier,
        created_at, last_login_at
      FROM users
      ORDER BY last_login_at DESC
    `);

    // Get list of online emails for efficient lookup
    const onlineEmails = getOnlineEmails();

    // Parse roles_json and add online status for each user
    const parsed = users.map(u => ({
      ...u,
      roles: JSON.parse(u.roles_json || "[]"),
      is_online: onlineEmails.has(u.email),
    }));

    res.json({ users: parsed, count: parsed.length });
  } catch (err) {
    console.error("[admin] Error fetching users:", err);
    res.status(500).json({ error: "Failed to fetch users" });
  }
});

/**
 * GET /api/admin/users/:id
 * Returns detailed user info including trade logs
 */
router.get("/users/:id", requireAdmin, async (req, res) => {
  const pool = getPool();
  const userId = req.params.id;

  try {
    // Get user info
    const [users] = await pool.execute(`
      SELECT
        id, issuer, wp_user_id, email, display_name,
        roles_json, is_admin, subscription_tier,
        created_at, last_login_at
      FROM users
      WHERE id = ?
    `, [userId]);

    if (!users.length) {
      return res.status(404).json({ error: "User not found" });
    }

    const user = {
      ...users[0],
      roles: JSON.parse(users[0].roles_json || "[]"),
    };

    // Get user's trade logs (if trade_logs table exists)
    let tradeLogs = [];
    try {
      const [logs] = await pool.execute(`
        SELECT id, name, starting_capital, is_active, created_at, updated_at
        FROM trade_logs
        WHERE user_id = ?
        ORDER BY created_at DESC
      `, [userId]);
      tradeLogs = logs;
    } catch (e) {
      // Table might not exist, that's ok
      console.log("[admin] trade_logs table not accessible:", e.message);
    }

    // Get trade count per log
    for (const log of tradeLogs) {
      try {
        const [countResult] = await pool.execute(`
          SELECT COUNT(*) as count FROM trades WHERE log_id = ?
        `, [log.id]);
        log.tradeCount = countResult[0]?.count || 0;
      } catch (e) {
        log.tradeCount = 0;
      }
    }

    res.json({ user, tradeLogs });
  } catch (err) {
    console.error("[admin] Error fetching user detail:", err);
    res.status(500).json({ error: "Failed to fetch user" });
  }
});

/**
 * GET /api/admin/users/:id/performance
 * Returns user trading performance stats
 */
router.get("/users/:id/performance", requireAdmin, async (req, res) => {
  const pool = getPool();
  const userId = req.params.id;

  try {
    // Get all closed trades for this user
    const [trades] = await pool.execute(`
      SELECT t.id, t.symbol, t.strategy, t.side, t.entry_price, t.exit_price,
             t.quantity, t.pnl, t.r_multiple, t.status, t.entry_time, t.exit_time
      FROM trades t
      JOIN trade_logs tl ON t.log_id = tl.id
      WHERE tl.user_id = ?
      ORDER BY t.entry_time DESC
    `, [userId]);

    const closedTrades = trades.filter(t => t.status === 'closed');
    const openTrades = trades.filter(t => t.status === 'open');

    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const winners = closedTrades.filter(t => t.pnl > 0);
    const losers = closedTrades.filter(t => t.pnl < 0);
    const winRate = closedTrades.length > 0 ? (winners.length / closedTrades.length * 100) : 0;

    const grossProfit = winners.reduce((sum, t) => sum + t.pnl, 0);
    const grossLoss = Math.abs(losers.reduce((sum, t) => sum + t.pnl, 0));
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

    const avgWin = winners.length > 0 ? grossProfit / winners.length : 0;
    const avgLoss = losers.length > 0 ? grossLoss / losers.length : 0;

    // Strategy breakdown
    const strategyStats = {};
    for (const t of closedTrades) {
      const key = t.strategy || 'unknown';
      if (!strategyStats[key]) {
        strategyStats[key] = { count: 0, pnl: 0, wins: 0 };
      }
      strategyStats[key].count++;
      strategyStats[key].pnl += t.pnl || 0;
      if (t.pnl > 0) strategyStats[key].wins++;
    }

    // Recent trades (last 10)
    const recentTrades = trades.slice(0, 10).map(t => ({
      id: t.id,
      symbol: t.symbol,
      strategy: t.strategy,
      side: t.side,
      pnl: t.pnl,
      rMultiple: t.r_multiple,
      status: t.status,
      entryTime: t.entry_time,
      exitTime: t.exit_time,
    }));

    res.json({
      summary: {
        totalTrades: trades.length,
        closedTrades: closedTrades.length,
        openTrades: openTrades.length,
        totalPnl,
        winRate: Math.round(winRate * 10) / 10,
        profitFactor: Math.round(profitFactor * 100) / 100,
        avgWin: Math.round(avgWin),
        avgLoss: Math.round(avgLoss),
        winners: winners.length,
        losers: losers.length,
        breakeven: closedTrades.length - winners.length - losers.length,
      },
      strategyStats,
      recentTrades,
    });
  } catch (err) {
    console.error("[admin] Error fetching user performance:", err);
    res.status(500).json({ error: "Failed to fetch performance" });
  }
});

/**
 * GET /api/admin/users/:id/trades
 * Returns paginated trades for a user
 */
router.get("/users/:id/trades", requireAdmin, async (req, res) => {
  const pool = getPool();
  const userId = req.params.id;
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 20;
  const offset = (page - 1) * limit;

  try {
    // Get total count
    const [countResult] = await pool.execute(`
      SELECT COUNT(*) as total
      FROM trades t
      JOIN trade_logs tl ON t.log_id = tl.id
      WHERE tl.user_id = ?
    `, [userId]);

    const total = countResult[0]?.total || 0;

    // Get trades with pagination
    const [trades] = await pool.execute(`
      SELECT t.*, tl.name as log_name
      FROM trades t
      JOIN trade_logs tl ON t.log_id = tl.id
      WHERE tl.user_id = ?
      ORDER BY t.entry_time DESC
      LIMIT ? OFFSET ?
    `, [userId, limit, offset]);

    res.json({
      trades,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (err) {
    // If table doesn't exist, return empty data
    if (err.code === "ER_NO_SUCH_TABLE") {
      return res.json({
        trades: [],
        pagination: { page, limit, total: 0, totalPages: 0 },
      });
    }
    console.error("[admin] Error fetching user trades:", err);
    res.status(500).json({ error: "Failed to fetch trades" });
  }
});

// =============================================================================
// Diagnostics Endpoints
// =============================================================================

/**
 * GET /api/admin/diagnostics
 * Returns overall system health and data availability
 */
router.get("/diagnostics", requireAdmin, async (req, res) => {
  const redis = getMarketRedis();
  const keys = getKeys();
  const symbols = ["SPX", "NDX"];

  try {
    const results = {
      ts: Date.now(),
      redis: { connected: false },
      data: {},
      services: {},
    };

    // Check Redis connection
    try {
      await redis.ping();
      results.redis.connected = true;
    } catch (e) {
      results.redis.error = e.message;
    }

    // Check data availability for each symbol
    for (const symbol of symbols) {
      const symbolData = {
        spot: { exists: false, ts: null, value: null },
        heatmap: { exists: false, ts: null, tileCount: null },
        gex: { exists: false, ts: null },
        trade_selector: { exists: false, ts: null, recommendationCount: null },
      };

      // Check spot
      try {
        const spotRaw = await redis.get(`massive:model:spot:${symbol}`);
        if (spotRaw) {
          const spot = JSON.parse(spotRaw);
          symbolData.spot = {
            exists: true,
            ts: spot.ts,
            value: spot.value,
            age_sec: spot.ts ? Math.floor((Date.now() - spot.ts) / 1000) : null,
          };
        }
      } catch (e) {
        symbolData.spot.error = e.message;
      }

      // Check heatmap
      try {
        const heatmapRaw = await redis.get(`massive:heatmap:model:${symbol}:latest`);
        if (heatmapRaw) {
          const heatmap = JSON.parse(heatmapRaw);
          symbolData.heatmap = {
            exists: true,
            ts: heatmap.ts,
            tileCount: heatmap.tiles ? Object.keys(heatmap.tiles).length : 0,
            age_sec: heatmap.ts ? Math.floor((Date.now() - heatmap.ts) / 1000) : null,
          };
        }
      } catch (e) {
        symbolData.heatmap.error = e.message;
      }

      // Check GEX
      try {
        const gexRaw = await redis.get(keys.gexKey(symbol));
        if (gexRaw) {
          const gex = JSON.parse(gexRaw);
          symbolData.gex = {
            exists: true,
            ts: gex.ts,
            age_sec: gex.ts ? Math.floor((Date.now() - gex.ts) / 1000) : null,
          };
        }
      } catch (e) {
        symbolData.gex.error = e.message;
      }

      // Check trade_selector
      try {
        const selectorRaw = await redis.get(`massive:selector:model:${symbol}:latest`);
        if (selectorRaw) {
          const selector = JSON.parse(selectorRaw);
          symbolData.trade_selector = {
            exists: true,
            ts: selector.ts,
            recommendationCount: selector.recommendations ? Object.keys(selector.recommendations).length : 0,
            vix_regime: selector.vix_regime,
            age_sec: selector.ts ? Math.floor((Date.now() - selector.ts) / 1000) : null,
          };
        }
      } catch (e) {
        symbolData.trade_selector.error = e.message;
      }

      results.data[symbol] = symbolData;
    }

    // Check global data
    results.data.global = {};

    // VIX from vexy_ai
    try {
      const vixRaw = await redis.get("vexy_ai:signals:latest");
      if (vixRaw) {
        const vix = JSON.parse(vixRaw);
        results.data.global.vix = {
          exists: true,
          value: vix.vix,
          ts: vix.ts,
          age_sec: vix.ts ? Math.floor((Date.now() - vix.ts) / 1000) : null,
        };
      } else {
        results.data.global.vix = { exists: false };
      }
    } catch (e) {
      results.data.global.vix = { exists: false, error: e.message };
    }

    // Market mode
    try {
      const modeRaw = await redis.get(keys.marketModeKey());
      if (modeRaw) {
        const mode = JSON.parse(modeRaw);
        results.data.global.market_mode = {
          exists: true,
          mode: mode.mode,
          ts: mode.ts,
        };
      } else {
        results.data.global.market_mode = { exists: false };
      }
    } catch (e) {
      results.data.global.market_mode = { exists: false, error: e.message };
    }

    // Vexy latest
    try {
      const vexyRaw = await redis.get(keys.vexyEpochKey());
      if (vexyRaw) {
        const vexy = JSON.parse(vexyRaw);
        results.data.global.vexy = {
          exists: true,
          ts: vexy.ts,
          age_sec: vexy.ts ? Math.floor((Date.now() - vexy.ts) / 1000) : null,
        };
      } else {
        results.data.global.vexy = { exists: false };
      }
    } catch (e) {
      results.data.global.vexy = { exists: false, error: e.message };
    }

    res.json(results);
  } catch (err) {
    console.error("[admin] Diagnostics error:", err);
    res.status(500).json({ error: "Failed to run diagnostics" });
  }
});

/**
 * GET /api/admin/diagnostics/redis
 * Query Redis keys by pattern
 * Query params: pattern (default: "*"), limit (default: 100)
 */
router.get("/diagnostics/redis", requireAdmin, async (req, res) => {
  const redis = getMarketRedis();
  const pattern = req.query.pattern || "*";
  const limit = Math.min(parseInt(req.query.limit) || 100, 500);

  try {
    // Get matching keys
    const allKeys = await redis.keys(pattern);
    const keys = allKeys.slice(0, limit);

    // Get values for each key (with size info)
    const results = [];
    for (const key of keys) {
      try {
        const type = await redis.type(key);
        let info = { key, type };

        if (type === "string") {
          const val = await redis.get(key);
          info.size = val ? val.length : 0;
          // Try to parse as JSON and get ts
          try {
            const parsed = JSON.parse(val);
            if (parsed.ts) {
              info.ts = parsed.ts;
              info.age_sec = Math.floor((Date.now() - parsed.ts) / 1000);
            }
          } catch {
            // Not JSON, that's ok
          }
        } else if (type === "list") {
          info.size = await redis.llen(key);
        } else if (type === "set") {
          info.size = await redis.scard(key);
        } else if (type === "hash") {
          info.size = await redis.hlen(key);
        } else if (type === "zset") {
          info.size = await redis.zcard(key);
        }

        // Get TTL
        const ttl = await redis.ttl(key);
        if (ttl > 0) info.ttl = ttl;

        results.push(info);
      } catch (e) {
        results.push({ key, error: e.message });
      }
    }

    res.json({
      pattern,
      total: allKeys.length,
      returned: results.length,
      keys: results,
    });
  } catch (err) {
    console.error("[admin] Redis query error:", err);
    res.status(500).json({ error: "Failed to query Redis" });
  }
});

/**
 * GET /api/admin/diagnostics/redis/:key
 * Get full value of a specific Redis key
 */
router.get("/diagnostics/redis/:key(*)", requireAdmin, async (req, res) => {
  const redis = getMarketRedis();
  const key = req.params.key;

  try {
    const type = await redis.type(key);

    if (type === "none") {
      return res.status(404).json({ error: "Key not found", key });
    }

    let value;
    if (type === "string") {
      const raw = await redis.get(key);
      try {
        value = JSON.parse(raw);
      } catch {
        value = raw;
      }
    } else if (type === "list") {
      value = await redis.lrange(key, 0, 100);
    } else if (type === "set") {
      value = await redis.smembers(key);
    } else if (type === "hash") {
      value = await redis.hgetall(key);
    } else if (type === "zset") {
      value = await redis.zrange(key, 0, 100, "WITHSCORES");
    }

    const ttl = await redis.ttl(key);

    res.json({
      key,
      type,
      ttl: ttl > 0 ? ttl : null,
      value,
    });
  } catch (err) {
    console.error("[admin] Redis key fetch error:", err);
    res.status(500).json({ error: "Failed to fetch key" });
  }
});

// ===========================================================================
// Trade Idea Tracking Analytics (Feedback Optimization Loop)
// ===========================================================================

const JOURNAL_API_URL = process.env.JOURNAL_API_URL || "http://localhost:3002";

/**
 * GET /api/admin/tracking/analytics
 * Get aggregated analytics for tracked ideas
 */
router.get("/tracking/analytics", requireAdmin, async (req, res) => {
  try {
    const params = new URLSearchParams();
    if (req.query.params_version) params.append("params_version", req.query.params_version);
    if (req.query.start_date) params.append("start_date", req.query.start_date);
    if (req.query.end_date) params.append("end_date", req.query.end_date);

    const url = `${JOURNAL_API_URL}/api/internal/tracked-ideas/analytics?${params}`;
    const response = await fetch(url);
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] tracking analytics error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/admin/tracking/ideas
 * List tracked ideas with filters
 */
router.get("/tracking/ideas", requireAdmin, async (req, res) => {
  try {
    const params = new URLSearchParams();
    if (req.query.limit) params.append("limit", req.query.limit);
    if (req.query.offset) params.append("offset", req.query.offset);
    if (req.query.regime) params.append("regime", req.query.regime);
    if (req.query.strategy) params.append("strategy", req.query.strategy);
    if (req.query.rank) params.append("rank", req.query.rank);
    if (req.query.is_winner) params.append("is_winner", req.query.is_winner);
    if (req.query.params_version) params.append("params_version", req.query.params_version);
    if (req.query.start_date) params.append("start_date", req.query.start_date);
    if (req.query.end_date) params.append("end_date", req.query.end_date);

    const url = `${JOURNAL_API_URL}/api/internal/tracked-ideas?${params}`;
    const response = await fetch(url);
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] tracking ideas error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/admin/tracking/params
 * List selector parameter versions
 */
router.get("/tracking/params", requireAdmin, async (req, res) => {
  try {
    const params = new URLSearchParams();
    if (req.query.include_retired) params.append("include_retired", req.query.include_retired);

    const url = `${JOURNAL_API_URL}/api/internal/selector-params?${params}`;
    const response = await fetch(url);
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] tracking params error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/admin/tracking/params/active
 * Get currently active selector parameters
 */
router.get("/tracking/params/active", requireAdmin, async (req, res) => {
  try {
    const url = `${JOURNAL_API_URL}/api/internal/selector-params/active`;
    const response = await fetch(url);
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] active params error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/admin/tracking/params
 * Create new parameter version
 */
router.post("/tracking/params", requireAdmin, async (req, res) => {
  try {
    const url = `${JOURNAL_API_URL}/api/internal/selector-params`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] create params error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/admin/tracking/params/:version/activate
 * Activate a parameter version
 */
router.post("/tracking/params/:version/activate", requireAdmin, async (req, res) => {
  try {
    const { version } = req.params;
    const url = `${JOURNAL_API_URL}/api/internal/selector-params/${version}/activate`;
    const response = await fetch(url, { method: "POST" });
    const data = await response.json();

    res.json(data);
  } catch (err) {
    console.error("[admin] activate params error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// =============================================================================
// RSS Intel Review
// =============================================================================

/**
 * GET /api/admin/rss-articles
 * Browse enriched RSS articles from intel-redis
 * Query params: hours (default 24), limit (default 200)
 */
router.get("/rss-articles", requireAdmin, async (req, res) => {
  const redis = getIntelRedis();
  if (!redis) {
    return res.status(503).json({ error: "Intel-redis not available" });
  }

  const hours = parseInt(req.query.hours) || 24;
  const limit = Math.min(parseInt(req.query.limit) || 200, 500);

  try {
    const nowSec = Date.now() / 1000;
    const minScore = nowSec - hours * 60 * 60;

    // Get UIDs from the enriched index (sorted set, newest first)
    const uids = await redis.zrevrangebyscore(
      "rss:article_enriched_index",
      "+inf",
      minScore,
      "LIMIT",
      0,
      limit
    );

    if (!uids.length) {
      return res.json({ articles: [], count: 0, hours });
    }

    // Fetch each article hash in parallel
    const pipeline = redis.pipeline();
    for (const uid of uids) {
      pipeline.hgetall(`rss:article_enriched:${uid}`);
    }
    const results = await pipeline.exec();

    const articles = [];
    for (let i = 0; i < results.length; i++) {
      const [err, hash] = results[i];
      if (err || !hash || !hash.title) continue;

      // Parse JSON fields safely
      const parseJSON = (val) => {
        if (!val) return null;
        try { return JSON.parse(val); } catch { return null; }
      };

      const enrichedTs = parseFloat(hash.enriched_ts) || parseFloat(hash.published_ts) || 0;
      const ageMinutes = enrichedTs ? Math.round((nowSec - enrichedTs) / 60) : null;

      articles.push({
        uid: uids[i],
        title: hash.title,
        url: hash.url || null,
        source: hash.source || null,
        category: hash.category || null,
        summary: hash.summary || null,
        sentiment: hash.sentiment || null,
        quality_score: parseFloat(hash.quality_score) || 0,
        entities: parseJSON(hash.entities),
        tickers: parseJSON(hash.tickers),
        takeaways: parseJSON(hash.takeaways),
        enriched_ts: enrichedTs * 1000,
        published_ts: (parseFloat(hash.published_ts) || 0) * 1000,
        age_minutes: ageMinutes,
      });
    }

    // Already sorted newest-first by zrevrangebyscore
    res.json({ articles, count: articles.length, hours });
  } catch (err) {
    console.error("[admin] RSS articles error:", err);
    res.status(500).json({ error: "Failed to fetch RSS articles" });
  }
});

// =============================================================================
// Activity Tracking
// =============================================================================

/**
 * Record a snapshot of currently online users
 */
async function recordActivitySnapshot() {
  if (!isDbAvailable()) {
    console.log("[admin] Activity snapshot skipped: database unavailable");
    return;
  }

  const pool = getPool();
  const onlineEmails = getOnlineEmails();

  console.log(`[admin] Activity snapshot: ${onlineEmails.size} online emails detected`);

  if (onlineEmails.size === 0) return;

  const now = new Date();
  const snapshotTime = now.toISOString().slice(0, 19).replace("T", " ");

  try {
    // Get user IDs for online emails
    const emailList = Array.from(onlineEmails);
    const placeholders = emailList.map(() => "?").join(",");
    const [users] = await pool.execute(
      `SELECT id FROM users WHERE email IN (${placeholders})`,
      emailList
    );

    if (users.length === 0) return;

    // Insert snapshot records
    const values = users.map((u) => [snapshotTime, u.id]);
    const insertPlaceholders = values.map(() => "(?, ?)").join(",");
    const flatValues = values.flat();

    await pool.execute(
      `INSERT INTO user_activity_snapshots (snapshot_time, user_id) VALUES ${insertPlaceholders}`,
      flatValues
    );

    // Update hourly aggregate
    const hourStart = new Date(now);
    hourStart.setMinutes(0, 0, 0);
    const hourStartStr = hourStart.toISOString().slice(0, 19).replace("T", " ");

    await pool.execute(
      `INSERT INTO hourly_activity_aggregates (hour_start, user_count)
       VALUES (?, ?)
       ON DUPLICATE KEY UPDATE user_count = GREATEST(user_count, ?)`,
      [hourStartStr, users.length, users.length]
    );

    console.log(`[admin] Activity snapshot recorded: ${users.length} users at ${snapshotTime}`);
  } catch (err) {
    console.error("[admin] Error recording activity snapshot:", err.message);
    console.error("[admin] Full error:", err);
  }
}

/**
 * Clean up old activity snapshots
 */
async function cleanupOldSnapshots() {
  if (!isDbAvailable()) return;

  const pool = getPool();

  try {
    const [result] = await pool.execute(
      `DELETE FROM user_activity_snapshots
       WHERE snapshot_time < DATE_SUB(NOW(), INTERVAL ? DAY)`,
      [SNAPSHOT_RETENTION_DAYS]
    );

    if (result.affectedRows > 0) {
      console.log(`[admin] Cleaned up ${result.affectedRows} old activity snapshots`);
    }

    // Also clean up old hourly aggregates
    const [aggResult] = await pool.execute(
      `DELETE FROM hourly_activity_aggregates
       WHERE hour_start < DATE_SUB(NOW(), INTERVAL ? DAY)`,
      [SNAPSHOT_RETENTION_DAYS]
    );

    if (aggResult.affectedRows > 0) {
      console.log(`[admin] Cleaned up ${aggResult.affectedRows} old hourly aggregates`);
    }
  } catch (err) {
    console.error("[admin] Error cleaning up old snapshots:", err.message);
  }
}

/**
 * Start activity tracking (called from index.js after initDb)
 */
export function startActivityTracking() {
  console.log("[admin] startActivityTracking() called");
  if (activitySnapshotInterval) {
    console.log("[admin] Activity tracking already running, skipping");
    return;
  }

  // Delay initial snapshot by 30 seconds to let users reconnect after restart
  setTimeout(() => {
    recordActivitySnapshot();
    console.log("[admin] Initial activity snapshot taken");
  }, 30 * 1000);

  // Schedule regular snapshots
  activitySnapshotInterval = setInterval(recordActivitySnapshot, SNAPSHOT_INTERVAL_MS);
  console.log(`[admin] Activity tracking started (every ${SNAPSHOT_INTERVAL_MS / 60000} min, first snapshot in 30s)`);

  // Schedule daily cleanup
  cleanupInterval = setInterval(cleanupOldSnapshots, CLEANUP_INTERVAL_MS);

  // Run initial cleanup
  cleanupOldSnapshots();
}

/**
 * Stop activity tracking (called from index.js on shutdown)
 */
export function stopActivityTracking() {
  if (activitySnapshotInterval) {
    clearInterval(activitySnapshotInterval);
    activitySnapshotInterval = null;
  }
  if (cleanupInterval) {
    clearInterval(cleanupInterval);
    cleanupInterval = null;
  }
  console.log("[admin] Activity tracking stopped");
}

/**
 * GET /api/admin/activity/hourly
 * Returns peak usage data over the specified number of days
 */
router.get("/activity/hourly", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }

  const pool = getPool();
  const days = parseInt(req.query.days) || 7;

  try {
    const [rows] = await pool.execute(
      `SELECT hour_start, user_count
       FROM hourly_activity_aggregates
       WHERE hour_start >= DATE_SUB(NOW(), INTERVAL ? DAY)
       ORDER BY hour_start ASC`,
      [days]
    );

    // Calculate busiest hours
    const hourlyTotals = {};
    for (let i = 0; i < 24; i++) {
      hourlyTotals[i] = { count: 0, total: 0 };
    }

    rows.forEach((row) => {
      const hour = new Date(row.hour_start).getHours();
      hourlyTotals[hour].count++;
      hourlyTotals[hour].total += row.user_count;
    });

    const busiestHours = Object.entries(hourlyTotals)
      .map(([hour, data]) => ({
        hour: parseInt(hour),
        avgUsers: data.count > 0 ? data.total / data.count : 0,
      }))
      .sort((a, b) => b.avgUsers - a.avgUsers)
      .slice(0, 3);

    res.json({
      data: rows.map((r) => ({
        hour_start: r.hour_start,
        user_count: r.user_count,
      })),
      busiestHours,
      days,
    });
  } catch (err) {
    // If table doesn't exist, return empty data instead of error
    if (err.code === "ER_NO_SUCH_TABLE") {
      return res.json({ data: [], busiestHours: [], days });
    }
    console.error("[admin] Error fetching hourly activity:", err);
    res.status(500).json({ error: "Failed to fetch activity data" });
  }
});

/**
 * GET /api/admin/users/:id/activity
 * Returns activity heatmap data for a specific user
 */
router.get("/users/:id/activity", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ error: "Database unavailable" });
  }

  const pool = getPool();
  const userId = req.params.id;
  const days = parseInt(req.query.days) || 30;

  try {
    // Get activity counts by day of week and hour
    const [rows] = await pool.execute(
      `SELECT
         DAYOFWEEK(snapshot_time) as day_of_week,
         HOUR(snapshot_time) as hour_of_day,
         COUNT(*) as session_count
       FROM user_activity_snapshots
       WHERE user_id = ?
         AND snapshot_time >= DATE_SUB(NOW(), INTERVAL ? DAY)
       GROUP BY DAYOFWEEK(snapshot_time), HOUR(snapshot_time)`,
      [userId, days]
    );

    // Build heatmap data (7 days x 24 hours)
    // Initialize with zeros
    const heatmapData = [];
    for (let day = 0; day < 7; day++) {
      for (let hour = 0; hour < 24; hour++) {
        heatmapData.push([hour, day, 0]);
      }
    }

    // Fill in actual values
    // MySQL DAYOFWEEK: 1=Sunday, 2=Monday, ..., 7=Saturday
    // We want: 0=Sunday, 1=Monday, ..., 6=Saturday
    rows.forEach((row) => {
      const dayIndex = row.day_of_week - 1; // Convert to 0-indexed
      const hourIndex = row.hour_of_day;
      const index = dayIndex * 24 + hourIndex;
      if (index >= 0 && index < heatmapData.length) {
        heatmapData[index][2] = row.session_count;
      }
    });

    // Calculate total active time (each snapshot = 15 min)
    const totalSnapshots = rows.reduce((sum, r) => sum + r.session_count, 0);
    const totalMinutes = totalSnapshots * 15;
    const totalHours = Math.floor(totalMinutes / 60);
    const remainingMinutes = totalMinutes % 60;

    res.json({
      heatmapData,
      totalActiveTime: {
        hours: totalHours,
        minutes: remainingMinutes,
        formatted: `${totalHours}h ${remainingMinutes}m`,
      },
      days,
    });
  } catch (err) {
    // If table doesn't exist, return empty data instead of error
    if (err.code === "ER_NO_SUCH_TABLE") {
      const emptyHeatmap = [];
      for (let day = 0; day < 7; day++) {
        for (let hour = 0; hour < 24; hour++) {
          emptyHeatmap.push([hour, day, 0]);
        }
      }
      return res.json({
        heatmapData: emptyHeatmap,
        totalActiveTime: { hours: 0, minutes: 0, formatted: "0h 0m" },
        days,
      });
    }
    console.error("[admin] Error fetching user activity:", err);
    res.status(500).json({ error: "Failed to fetch user activity" });
  }
});

// =============================================================================
// ML Lab API Proxy Routes
// =============================================================================

// Helper to proxy requests to Journal service ML endpoints
async function proxyToJournalML(req, res, path, method = "GET", body = null) {
  try {
    const url = `${JOURNAL_API_URL}/api/internal/ml${path}`;
    const options = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body) {
      options.body = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    console.error(`[admin] ML proxy error (${path}):`, err);
    res.status(500).json({ error: "Failed to connect to ML service" });
  }
}

// Circuit Breakers
router.get("/ml/circuit-breakers", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/circuit-breakers");
});

router.post("/ml/circuit-breakers/check", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/circuit-breakers/check", "POST");
});

router.post("/ml/circuit-breakers/disable-ml", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/circuit-breakers/disable-ml", "POST");
});

router.post("/ml/circuit-breakers/enable-ml", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/circuit-breakers/enable-ml", "POST");
});

// Models
router.get("/ml/models", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/models${params ? `?${params}` : ""}`);
});

router.get("/ml/models/champion", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/models/champion");
});

router.get("/ml/models/:id", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/models/${req.params.id}`);
});

router.post("/ml/models", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/models", "POST", req.body);
});

router.post("/ml/models/:id/deploy", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/models/${req.params.id}/deploy`, "POST", req.body);
});

router.post("/ml/models/:id/retire", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/models/${req.params.id}/retire`, "POST");
});

// Experiments
router.get("/ml/experiments", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/experiments${params ? `?${params}` : ""}`);
});

router.get("/ml/experiments/:id", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/experiments/${req.params.id}`);
});

router.post("/ml/experiments", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/experiments", "POST", req.body);
});

router.post("/ml/experiments/:id/evaluate", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/experiments/${req.params.id}/evaluate`, "POST");
});

router.post("/ml/experiments/:id/conclude", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/experiments/${req.params.id}/conclude`, "POST", req.body);
});

router.post("/ml/experiments/:id/abort", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/experiments/${req.params.id}/abort`, "POST");
});

// Decisions
router.get("/ml/decisions", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/decisions${params ? `?${params}` : ""}`);
});

router.get("/ml/decisions/stats", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/decisions/stats`);
});

router.get("/ml/decisions/:id", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/decisions/${req.params.id}`);
});

// P&L Events
router.get("/ml/pnl-events", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/pnl-events${params ? `?${params}` : ""}`);
});

// Equity Curve
router.get("/ml/equity-curve", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/equity-curve${params ? `?${params}` : ""}`);
});

// Daily Performance
router.get("/ml/daily-performance", requireAdmin, async (req, res) => {
  const params = new URLSearchParams(req.query).toString();
  await proxyToJournalML(req, res, `/daily-performance${params ? `?${params}` : ""}`);
});

router.post("/ml/daily-performance/materialize", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, "/daily-performance/materialize", "POST");
});

// Feature Snapshots
router.get("/ml/feature-snapshots/:id", requireAdmin, async (req, res) => {
  await proxyToJournalML(req, res, `/feature-snapshots/${req.params.id}`);
});

export default router;
