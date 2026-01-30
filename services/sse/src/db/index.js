// services/sse/src/db/index.js
// MySQL database connection and initialization

import mysql from "mysql2/promise";
import { getConfig } from "../config.js";

let pool = null;

/**
 * Parse DATABASE_URL into connection config
 * Format: mysql://user:pass@host:port/database
 */
function parseDbUrl(url) {
  if (!url) return null;

  // Handle mysql+pymysql:// format (Python SQLAlchemy style)
  url = url.replace("mysql+pymysql://", "mysql://");

  try {
    const parsed = new URL(url);
    return {
      host: parsed.hostname,
      port: parseInt(parsed.port, 10) || 3306,
      user: parsed.username,
      password: decodeURIComponent(parsed.password),
      database: parsed.pathname.slice(1), // remove leading /
    };
  } catch (e) {
    console.error("[db] Failed to parse DATABASE_URL:", e.message);
    return null;
  }
}

/**
 * Initialize database connection pool
 * Gets DATABASE_URL from truth config
 */
export async function initDb() {
  const appConfig = getConfig();
  const dbUrl = appConfig?.env?.DATABASE_URL || "";

  if (!dbUrl) {
    console.warn("[db] DATABASE_URL not set - user persistence disabled");
    return false;
  }

  const config = parseDbUrl(dbUrl);
  if (!config) {
    console.warn("[db] Invalid DATABASE_URL - user persistence disabled");
    return false;
  }

  try {
    pool = mysql.createPool({
      ...config,
      waitForConnections: true,
      connectionLimit: 10,
      queueLimit: 0,
    });

    // Test connection
    const conn = await pool.getConnection();
    conn.release();

    console.log(`[db] Connected to MySQL: ${config.host}:${config.port}/${config.database}`);

    // Create tables if they don't exist
    await createTables();

    return true;
  } catch (e) {
    console.error("[db] Failed to connect to MySQL:", e.message);
    pool = null;
    return false;
  }
}

/**
 * Create users table if it doesn't exist
 */
async function createTables() {
  if (!pool) return;

  const createUsersTable = `
    CREATE TABLE IF NOT EXISTS users (
      id INT AUTO_INCREMENT PRIMARY KEY,
      issuer VARCHAR(32) NOT NULL,
      wp_user_id VARCHAR(64) NOT NULL,
      email VARCHAR(255) NOT NULL,
      display_name VARCHAR(255),
      roles_json TEXT NOT NULL DEFAULT '[]',
      is_admin BOOLEAN NOT NULL DEFAULT FALSE,
      subscription_tier VARCHAR(128) DEFAULT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uq_users_issuer_wp_user_id (issuer, wp_user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  try {
    await pool.execute(createUsersTable);

    // Add subscription_tier column if table already exists without it
    try {
      await pool.execute(`
        ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(128) DEFAULT NULL
      `);
      console.log("[db] Added subscription_tier column");
    } catch (alterErr) {
      // Column likely already exists, ignore duplicate column error
      if (!alterErr.message.includes("Duplicate column")) {
        // Only log if it's not a duplicate column error
      }
    }

    console.log("[db] Users table ready");
  } catch (e) {
    console.error("[db] Failed to create tables:", e.message);
  }
}

/**
 * Get database pool (null if not connected)
 */
export function getPool() {
  return pool;
}

/**
 * Check if database is available
 */
export function isDbAvailable() {
  return pool !== null;
}

/**
 * Close database connection
 */
export async function closeDb() {
  if (pool) {
    await pool.end();
    pool = null;
    console.log("[db] Connection closed");
  }
}
