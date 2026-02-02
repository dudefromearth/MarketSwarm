// services/sse/src/routes/admin.js
// Admin API endpoints for user management and stats

import { Router } from "express";
import { getPool, isDbAvailable } from "../db/index.js";
import { getCurrentUser, isAdmin as checkIsAdmin } from "../auth.js";

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
 */
async function requireAdmin(req, res, next) {
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

export default router;
