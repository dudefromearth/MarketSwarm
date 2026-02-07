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

  // Activity tracking tables
  const createActivitySnapshotsTable = `
    CREATE TABLE IF NOT EXISTS user_activity_snapshots (
      id INT AUTO_INCREMENT PRIMARY KEY,
      snapshot_time DATETIME NOT NULL,
      user_id INT NOT NULL,
      INDEX idx_user_snapshot (user_id, snapshot_time),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  const createHourlyAggregatesTable = `
    CREATE TABLE IF NOT EXISTS hourly_activity_aggregates (
      id INT AUTO_INCREMENT PRIMARY KEY,
      hour_start DATETIME NOT NULL,
      user_count INT NOT NULL DEFAULT 0,
      UNIQUE KEY uq_hour (hour_start)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  try {
    await pool.execute(createUsersTable);

    // Create activity tracking tables (separate try-catch so users table still works if these fail)
    try {
      await pool.execute(createActivitySnapshotsTable);
      await pool.execute(createHourlyAggregatesTable);
      console.log("[db] Activity tracking tables ready");
    } catch (activityErr) {
      console.error("[db] Failed to create activity tracking tables:", activityErr.message);
      console.log("[db] Activity tracking will be disabled");
    }

    // Add subscription_tier column if table already exists without it
    try {
      await pool.execute(`
        ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(128) DEFAULT NULL
      `);
      console.log("[db] Added subscription_tier column");
    } catch (alterErr) {
      // Column likely already exists, ignore duplicate column error
    }

    // Add timezone column for user preference (defaults to browser-detected)
    try {
      await pool.execute(`
        ALTER TABLE users ADD COLUMN timezone VARCHAR(64) DEFAULT NULL
      `);
      console.log("[db] Added timezone column");
    } catch (alterErr) {
      // Column likely already exists, ignore duplicate column error
    }

    // Add leaderboard columns (screen_name, show_screen_name) if they don't exist
    try {
      await pool.execute(`
        ALTER TABLE users ADD COLUMN screen_name VARCHAR(100) DEFAULT NULL
      `);
      console.log("[db] Added screen_name column");
    } catch (alterErr) {
      // Column likely already exists
    }

    try {
      await pool.execute(`
        ALTER TABLE users ADD COLUMN show_screen_name TINYINT DEFAULT 1
      `);
      console.log("[db] Added show_screen_name column");
    } catch (alterErr) {
      // Column likely already exists
    }

    console.log("[db] Users table ready");

    // Dealer Gravity config tables
    await createDealerGravityTables();

    // Positions table (leg-based model)
    await createPositionsTables();
  } catch (e) {
    console.error("[db] Failed to create tables:", e.message);
  }
}

/**
 * Create Dealer Gravity configuration tables
 */
async function createDealerGravityTables() {
  if (!pool) return;

  // User Dealer Gravity display configurations
  const createDGConfigsTable = `
    CREATE TABLE IF NOT EXISTS dealer_gravity_configs (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      name VARCHAR(100) NOT NULL DEFAULT 'Default',

      -- Display settings
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      mode ENUM('raw', 'tv') NOT NULL DEFAULT 'tv',
      width_percent INT NOT NULL DEFAULT 15,
      rows_layout ENUM('number_of_rows', 'ticks_per_row') NOT NULL DEFAULT 'number_of_rows',
      row_size INT NOT NULL DEFAULT 24,
      capping_sigma DECIMAL(3,2) NOT NULL DEFAULT 2.00,
      color VARCHAR(7) NOT NULL DEFAULT '#9333ea',
      transparency INT NOT NULL DEFAULT 50,
      show_volume_nodes BOOLEAN NOT NULL DEFAULT TRUE,
      show_volume_wells BOOLEAN NOT NULL DEFAULT TRUE,
      show_crevasses BOOLEAN NOT NULL DEFAULT TRUE,

      is_default BOOLEAN NOT NULL DEFAULT FALSE,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

      UNIQUE KEY uq_user_name (user_id, name),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  // GEX panel configurations
  const createGexConfigsTable = `
    CREATE TABLE IF NOT EXISTS gex_panel_configs (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      mode ENUM('combined', 'net') NOT NULL DEFAULT 'combined',
      calls_color VARCHAR(7) NOT NULL DEFAULT '#22c55e',
      puts_color VARCHAR(7) NOT NULL DEFAULT '#ef4444',
      width_px INT NOT NULL DEFAULT 60,

      is_default BOOLEAN NOT NULL DEFAULT FALSE,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  // AI analysis history (using Dealer Gravity lexicon)
  const createDGAnalysesTable = `
    CREATE TABLE IF NOT EXISTS dealer_gravity_analyses (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',
      spot_price DECIMAL(10,2),

      -- Structural results (Dealer Gravity terminology)
      volume_nodes JSON,
      volume_wells JSON,
      crevasses JSON,
      market_memory_strength DECIMAL(3,2),
      bias ENUM('bullish', 'bearish', 'neutral'),
      analysis_text TEXT,

      -- Metadata
      provider VARCHAR(20),
      model VARCHAR(100),
      tokens_used INT,
      latency_ms INT,

      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

      INDEX idx_user_created (user_id, created_at),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  try {
    await pool.execute(createDGConfigsTable);
    console.log("[db] dealer_gravity_configs table ready");

    await pool.execute(createGexConfigsTable);
    console.log("[db] gex_panel_configs table ready");

    await pool.execute(createDGAnalysesTable);
    console.log("[db] dealer_gravity_analyses table ready");
  } catch (e) {
    console.error("[db] Failed to create Dealer Gravity tables:", e.message);
  }
}

/**
 * Create Positions table (leg-based model)
 * Supports 12+ strategy types with individual contract legs
 */
async function createPositionsTables() {
  if (!pool) return;

  // Positions table - stores multi-leg option positions
  const createPositionsTable = `
    CREATE TABLE IF NOT EXISTS positions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      user_id INT NOT NULL,
      symbol VARCHAR(20) NOT NULL DEFAULT 'SPX',

      -- Position type (derived from legs, but cached for queries)
      position_type ENUM(
        'single', 'vertical', 'calendar', 'diagonal',
        'butterfly', 'bwb', 'condor',
        'straddle', 'strangle',
        'iron_fly', 'iron_condor',
        'custom'
      ) NOT NULL DEFAULT 'single',
      direction ENUM('long', 'short') NOT NULL DEFAULT 'long',

      -- Legs stored as JSON array
      -- Each leg: { strike, expiration, right, quantity, fillPrice?, fillDate? }
      legs_json JSON NOT NULL,

      -- Computed convenience fields (derived from legs)
      primary_expiration DATE NOT NULL,
      dte INT NOT NULL DEFAULT 0,

      -- Cost basis
      cost_basis DECIMAL(10,2) DEFAULT NULL,
      cost_basis_type ENUM('debit', 'credit', 'net') DEFAULT 'debit',

      -- Display settings
      visible BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INT NOT NULL DEFAULT 0,
      color VARCHAR(7) DEFAULT NULL,
      label VARCHAR(100) DEFAULT NULL,

      -- Timestamps
      added_at BIGINT NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

      -- Optimistic locking version
      version INT NOT NULL DEFAULT 1,

      INDEX idx_user_positions (user_id),
      INDEX idx_user_symbol (user_id, symbol),
      INDEX idx_user_expiration (user_id, primary_expiration),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `;

  try {
    await pool.execute(createPositionsTable);
    console.log("[db] positions table ready");
  } catch (e) {
    console.error("[db] Failed to create positions table:", e.message);
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
