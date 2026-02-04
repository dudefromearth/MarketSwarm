// services/sse/src/routes/admin.js
// Admin API endpoints for user management, stats, and diagnostics

import { Router } from "express";
import { getPool, isDbAvailable } from "../db/index.js";
import { getCurrentUser, isAdmin as checkIsAdmin } from "../auth.js";
import { getMarketRedis } from "../redis.js";
import { getKeys } from "../keys.js";

const router = Router();

// Track connected clients with user info
const connectedUsers = new Map(); // sessionId -> { displayName, email, connectedAt }

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

export default router;
