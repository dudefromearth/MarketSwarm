/**
 * Import Batches Routes - Reversible batch import management
 *
 * Provides endpoints for:
 * - Creating import batches
 * - Listing import history
 * - Reverting/undoing imports
 *
 * All imported entities carry a nullable import_batch_id that links to
 * the import_batches table. Manual trades have import_batch_id = NULL.
 */

import { Router } from "express";
import { getPool, isDbAvailable } from "../db/index.js";
import { v4 as uuidv4 } from "uuid";
import { getUserProfile, upsertUserFromWpToken } from "../db/userStore.js";

const router = Router();

// Resolve WordPress user ID → internal DB user ID for all import routes.
router.use(async (req, res, next) => {
  const wp = req.user?.wp;
  if (!wp?.issuer || !wp?.id) return next();

  try {
    let profile = await getUserProfile(wp.issuer, wp.id);
    if (!profile) {
      profile = await upsertUserFromWpToken({
        iss: wp.issuer,
        sub: wp.id,
        email: wp.email || "",
        name: wp.name || "",
        roles: wp.roles || [],
      });
    }
    if (profile?.id) {
      req.dbUserId = profile.id;
    }
  } catch (e) {
    console.error("[imports] Failed to resolve user ID:", e.message);
  }
  next();
});

/**
 * Transform database row to API response format
 */
function rowToBatch(row) {
  // MySQL JSON columns may return parsed objects or strings
  let sourceMetadata = row.source_metadata;
  if (typeof sourceMetadata === 'string') {
    try {
      sourceMetadata = JSON.parse(sourceMetadata || 'null');
    } catch {
      sourceMetadata = null;
    }
  }

  return {
    id: row.id,
    userId: row.user_id,
    source: row.source,
    sourceLabel: row.source_label,
    sourceMetadata,
    tradeCount: row.trade_count,
    positionCount: row.position_count,
    status: row.status,
    createdAt: row.created_at,
    revertedAt: row.reverted_at,
  };
}

// ===========================================================================
// Import Batch CRUD APIs
// ===========================================================================

/**
 * GET /api/imports
 *
 * List all import batches for the authenticated user.
 * Query params:
 *   - status: Filter by status ('active', 'reverted') (default: all)
 *   - limit: Max results (default: 50)
 *   - offset: Pagination offset (default: 0)
 */
router.get("/", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.dbUserId;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const status = req.query.status;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = parseInt(req.query.offset) || 0;

    let query = `
      SELECT id, user_id, source, source_label, source_metadata,
             trade_count, position_count, status, created_at, reverted_at
      FROM import_batches
      WHERE user_id = ?
    `;
    const params = [userId];

    if (status && ['active', 'reverted'].includes(status)) {
      query += " AND status = ?";
      params.push(status);
    }

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?";
    params.push(limit, offset);

    const [rows] = await pool.execute(query, params);
    const batches = rows.map(rowToBatch);

    res.json({
      success: true,
      data: batches,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[imports] GET / error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/imports/:id
 *
 * Get a single import batch by ID.
 */
router.get("/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.dbUserId;
    const batchId = req.params.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [rows] = await pool.execute(
      `SELECT id, user_id, source, source_label, source_metadata,
              trade_count, position_count, status, created_at, reverted_at
       FROM import_batches
       WHERE id = ? AND user_id = ?`,
      [batchId, userId]
    );

    if (rows.length === 0) {
      return res.status(404).json({ success: false, error: "Import batch not found" });
    }

    res.json({
      success: true,
      data: rowToBatch(rows[0]),
    });
  } catch (err) {
    console.error("[imports] GET /:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/imports
 *
 * Create a new import batch.
 * Body:
 *   - source: Required. One of 'tos', 'tastytrade', 'ibkr', 'custom', 'ai', 'ml_backfill', 'simulator'
 *   - sourceLabel: Optional human-readable label
 *   - sourceMetadata: Optional JSON metadata (filename, date range, etc.)
 */
router.post("/", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.dbUserId;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const { source, sourceLabel, sourceMetadata } = req.body;

    if (!source) {
      return res.status(400).json({ success: false, error: "source is required" });
    }

    const batchId = uuidv4();
    const metadataJson = sourceMetadata ? JSON.stringify(sourceMetadata) : null;

    await pool.execute(
      `INSERT INTO import_batches (id, user_id, source, source_label, source_metadata)
       VALUES (?, ?, ?, ?, ?)`,
      [batchId, userId, source, sourceLabel || null, metadataJson]
    );

    // Fetch the created batch
    const [rows] = await pool.execute(
      `SELECT id, user_id, source, source_label, source_metadata,
              trade_count, position_count, status, created_at, reverted_at
       FROM import_batches WHERE id = ?`,
      [batchId]
    );

    res.status(201).json({
      success: true,
      data: rowToBatch(rows[0]),
    });
  } catch (err) {
    console.error("[imports] POST / error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * PATCH /api/imports/:id/counts
 *
 * Update the counts on an import batch (called after import completes).
 * Body:
 *   - tradeCount: Number of trades imported
 *   - positionCount: Number of positions imported
 */
router.patch("/:id/counts", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.dbUserId;
    const batchId = req.params.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const { tradeCount, positionCount } = req.body;

    // Verify ownership
    const [check] = await pool.execute(
      "SELECT id FROM import_batches WHERE id = ? AND user_id = ?",
      [batchId, userId]
    );

    if (check.length === 0) {
      return res.status(404).json({ success: false, error: "Import batch not found" });
    }

    await pool.execute(
      `UPDATE import_batches SET trade_count = ?, position_count = ? WHERE id = ?`,
      [tradeCount || 0, positionCount || 0, batchId]
    );

    res.json({ success: true });
  } catch (err) {
    console.error("[imports] PATCH /:id/counts error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/imports/:id/revert
 *
 * Revert an import batch - deletes all associated trades and positions.
 *
 * This is a destructive operation that:
 * 1. Deletes all trades with this import_batch_id
 * 2. Deletes all positions with this import_batch_id
 * 3. Marks the batch as 'reverted'
 *
 * Manual trades (import_batch_id = NULL) are never affected.
 */
router.post("/:id/revert", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  const pool = getPool();
  const conn = await pool.getConnection();

  try {
    const userId = req.dbUserId;
    const batchId = req.params.id;

    if (!userId) {
      conn.release();
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Verify batch exists and belongs to user
    const [check] = await conn.execute(
      "SELECT id, status FROM import_batches WHERE id = ? AND user_id = ?",
      [batchId, userId]
    );

    if (check.length === 0) {
      conn.release();
      return res.status(404).json({ success: false, error: "Import batch not found" });
    }

    if (check[0].status === 'reverted') {
      conn.release();
      return res.status(400).json({ success: false, error: "Batch already reverted" });
    }

    // Start transaction
    await conn.beginTransaction();

    try {
      // Delete trades associated with this batch
      const [tradeResult] = await conn.execute(
        "DELETE FROM trades WHERE import_batch_id = ?",
        [batchId]
      );
      const tradesDeleted = tradeResult.affectedRows;

      // Delete positions associated with this batch
      // Note: This may cascade to legs and fills depending on FK constraints
      const [positionResult] = await conn.execute(
        "DELETE FROM positions WHERE import_batch_id = ?",
        [batchId]
      );
      const positionsDeleted = positionResult.affectedRows;

      // Mark batch as reverted
      await conn.execute(
        `UPDATE import_batches SET status = 'reverted', reverted_at = NOW() WHERE id = ?`,
        [batchId]
      );

      await conn.commit();

      res.json({
        success: true,
        data: {
          tradesReverted: tradesDeleted,
          positionsReverted: positionsDeleted,
          batchId,
          status: 'reverted',
        },
      });
    } catch (txErr) {
      await conn.rollback();
      throw txErr;
    }
  } catch (err) {
    console.error("[imports] POST /:id/revert error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  } finally {
    conn.release();
  }
});

/**
 * GET /api/imports/:id/trades
 *
 * List all trades associated with an import batch.
 */
router.get("/:id/trades", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.dbUserId;
    const batchId = req.params.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Verify batch ownership
    const [check] = await pool.execute(
      "SELECT id FROM import_batches WHERE id = ? AND user_id = ?",
      [batchId, userId]
    );

    if (check.length === 0) {
      return res.status(404).json({ success: false, error: "Import batch not found" });
    }

    const [rows] = await pool.execute(
      `SELECT * FROM trades WHERE import_batch_id = ? ORDER BY entry_time DESC`,
      [batchId]
    );

    res.json({
      success: true,
      data: rows,
    });
  } catch (err) {
    console.error("[imports] GET /:id/trades error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
