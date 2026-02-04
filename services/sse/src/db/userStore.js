// services/sse/src/db/userStore.js
// User persistence operations

import { getPool, isDbAvailable } from "./index.js";

/**
 * Safely parse roles from WP token
 */
function safeRoles(roles) {
  if (Array.isArray(roles)) return roles;
  if (typeof roles === "string") {
    return roles.split(",").map((r) => r.trim()).filter(Boolean);
  }
  return [];
}

/**
 * Upsert user from WordPress SSO token payload
 * Creates new user or updates existing one on each login
 */
export async function upsertUserFromWpToken(wpTokenPayload) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  const issuer = (wpTokenPayload.iss || "").trim();
  const wpUserId = String(wpTokenPayload.sub || "").trim();
  const email = (wpTokenPayload.email || "").trim();
  const displayName = (wpTokenPayload.name || "").trim();
  const roles = safeRoles(wpTokenPayload.roles);
  const isAdmin = wpTokenPayload.is_admin === true || roles.includes("administrator") || roles.includes("admin");
  const subscriptionTier = (wpTokenPayload.subscription_tier || "").trim() || null;

  if (!issuer || !wpUserId || !email) {
    console.warn("[userStore] Missing required fields:", { issuer, wpUserId, email });
    return null;
  }

  try {
    // Check if user exists
    const [rows] = await pool.execute(
      "SELECT id FROM users WHERE issuer = ? AND wp_user_id = ?",
      [issuer, wpUserId]
    );

    if (rows.length > 0) {
      // Update existing user
      await pool.execute(
        `UPDATE users SET
          email = ?,
          display_name = ?,
          roles_json = ?,
          is_admin = ?,
          subscription_tier = ?,
          last_login_at = NOW()
        WHERE issuer = ? AND wp_user_id = ?`,
        [email, displayName, JSON.stringify(roles), isAdmin, subscriptionTier, issuer, wpUserId]
      );
      console.log(`[userStore] Updated user: ${email} (${issuer}) tier: ${subscriptionTier || 'none'}`);
    } else {
      // Insert new user
      await pool.execute(
        `INSERT INTO users (issuer, wp_user_id, email, display_name, roles_json, is_admin, subscription_tier, created_at, last_login_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, NOW(), NOW())`,
        [issuer, wpUserId, email, displayName, JSON.stringify(roles), isAdmin, subscriptionTier]
      );
      console.log(`[userStore] Created user: ${email} (${issuer}) tier: ${subscriptionTier || 'none'}`);
    }

    // Return the user
    return await getUserProfile(issuer, wpUserId);
  } catch (e) {
    console.error("[userStore] Failed to upsert user:", e.message);
    return null;
  }
}

/**
 * Get user profile by issuer and WP user ID
 */
export async function getUserProfile(issuer, wpUserId) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  try {
    const [rows] = await pool.execute(
      "SELECT * FROM users WHERE issuer = ? AND wp_user_id = ?",
      [issuer, String(wpUserId)]
    );

    if (rows.length === 0) {
      return null;
    }

    const user = rows[0];
    return {
      id: user.id,
      issuer: user.issuer,
      wp_user_id: user.wp_user_id,
      email: user.email,
      display_name: user.display_name,
      roles: JSON.parse(user.roles_json || "[]"),
      is_admin: Boolean(user.is_admin),
      subscription_tier: user.subscription_tier || null,
      timezone: user.timezone || null,
      created_at: user.created_at?.toISOString(),
      last_login_at: user.last_login_at?.toISOString(),
    };
  } catch (e) {
    console.error("[userStore] Failed to get user:", e.message);
    return null;
  }
}

/**
 * Update user timezone preference
 */
export async function updateUserTimezone(issuer, wpUserId, timezone) {
  if (!isDbAvailable()) {
    return false;
  }

  const pool = getPool();

  try {
    await pool.execute(
      "UPDATE users SET timezone = ? WHERE issuer = ? AND wp_user_id = ?",
      [timezone, issuer, String(wpUserId)]
    );
    console.log(`[userStore] Updated timezone for ${issuer}/${wpUserId}: ${timezone}`);
    return true;
  } catch (e) {
    console.error("[userStore] Failed to update timezone:", e.message);
    return false;
  }
}

/**
 * Get user by internal ID
 */
export async function getUserById(id) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  try {
    const [rows] = await pool.execute(
      "SELECT * FROM users WHERE id = ?",
      [id]
    );

    if (rows.length === 0) {
      return null;
    }

    const user = rows[0];
    return {
      id: user.id,
      issuer: user.issuer,
      wp_user_id: user.wp_user_id,
      email: user.email,
      display_name: user.display_name,
      roles: JSON.parse(user.roles_json || "[]"),
      is_admin: Boolean(user.is_admin),
      subscription_tier: user.subscription_tier || null,
      timezone: user.timezone || null,
      created_at: user.created_at?.toISOString(),
      last_login_at: user.last_login_at?.toISOString(),
    };
  } catch (e) {
    console.error("[userStore] Failed to get user by ID:", e.message);
    return null;
  }
}

/**
 * Get leaderboard settings for a user
 */
export async function getLeaderboardSettings(issuer, wpUserId) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  try {
    const [rows] = await pool.execute(
      "SELECT id, screen_name, show_screen_name, display_name FROM users WHERE issuer = ? AND wp_user_id = ?",
      [issuer, String(wpUserId)]
    );

    if (rows.length === 0) {
      return null;
    }

    const user = rows[0];
    return {
      userId: user.id,
      screenName: user.screen_name || null,
      showScreenName: Boolean(user.show_screen_name),
      displayName: user.display_name || null,
    };
  } catch (e) {
    console.error("[userStore] Failed to get leaderboard settings:", e.message);
    return null;
  }
}

/**
 * Update leaderboard settings for a user
 */
export async function updateLeaderboardSettings(issuer, wpUserId, settings) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  try {
    const updates = [];
    const params = [];

    if (settings.screenName !== undefined) {
      updates.push("screen_name = ?");
      // Validate screen name: alphanumeric, underscores, max 100 chars
      const screenName = settings.screenName?.trim() || null;
      if (screenName && (screenName.length > 100 || !/^[a-zA-Z0-9_\-\s]+$/.test(screenName))) {
        throw new Error("Invalid screen name. Use letters, numbers, underscores, hyphens, or spaces (max 100 chars).");
      }
      params.push(screenName);
    }

    if (settings.showScreenName !== undefined) {
      updates.push("show_screen_name = ?");
      params.push(settings.showScreenName ? 1 : 0);
    }

    if (updates.length === 0) {
      return await getLeaderboardSettings(issuer, wpUserId);
    }

    params.push(issuer, String(wpUserId));

    await pool.execute(
      `UPDATE users SET ${updates.join(", ")} WHERE issuer = ? AND wp_user_id = ?`,
      params
    );

    console.log(`[userStore] Updated leaderboard settings for ${issuer}/${wpUserId}`);
    return await getLeaderboardSettings(issuer, wpUserId);
  } catch (e) {
    console.error("[userStore] Failed to update leaderboard settings:", e.message);
    throw e;
  }
}

/**
 * Get display name for leaderboard (respects show_screen_name preference)
 */
export async function getLeaderboardDisplayName(userId) {
  if (!isDbAvailable()) {
    return null;
  }

  const pool = getPool();

  try {
    const [rows] = await pool.execute(
      "SELECT display_name, screen_name, show_screen_name FROM users WHERE id = ?",
      [userId]
    );

    if (rows.length === 0) {
      return null;
    }

    const user = rows[0];
    if (user.show_screen_name && user.screen_name) {
      return user.screen_name;
    }
    return user.display_name || "Anonymous";
  } catch (e) {
    console.error("[userStore] Failed to get leaderboard display name:", e.message);
    return null;
  }
}
