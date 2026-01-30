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
  const isAdmin = wpTokenPayload.is_admin === true || roles.includes("administrator");

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
          last_login_at = NOW()
        WHERE issuer = ? AND wp_user_id = ?`,
        [email, displayName, JSON.stringify(roles), isAdmin, issuer, wpUserId]
      );
      console.log(`[userStore] Updated user: ${email} (${issuer})`);
    } else {
      // Insert new user
      await pool.execute(
        `INSERT INTO users (issuer, wp_user_id, email, display_name, roles_json, is_admin, created_at, last_login_at)
         VALUES (?, ?, ?, ?, ?, ?, NOW(), NOW())`,
        [issuer, wpUserId, email, displayName, JSON.stringify(roles), isAdmin]
      );
      console.log(`[userStore] Created user: ${email} (${issuer})`);
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
      created_at: user.created_at?.toISOString(),
      last_login_at: user.last_login_at?.toISOString(),
    };
  } catch (e) {
    console.error("[userStore] Failed to get user:", e.message);
    return null;
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
      created_at: user.created_at?.toISOString(),
      last_login_at: user.last_login_at?.toISOString(),
    };
  } catch (e) {
    console.error("[userStore] Failed to get user by ID:", e.message);
    return null;
  }
}
