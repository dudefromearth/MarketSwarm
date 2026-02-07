// services/sse/src/routes/positions.js
// Positions API Routes - Leg-based multi-leg option positions
//
// Supports 12+ strategy types:
//   Singles, Verticals, Calendars, Diagonals,
//   Butterflies, BWBs, Condors,
//   Straddles, Strangles,
//   Iron Flies, Iron Condors, Custom
//
// Legs stored as JSON: { strike, expiration, right, quantity, fillPrice?, fillDate? }

import { Router } from "express";
import { getPool, isDbAvailable } from "../db/index.js";
import { getSystemRedis } from "../redis.js";

const router = Router();

// Redis pub/sub channel for position updates
const POSITIONS_PUBSUB_CHANNEL = "positions:updates";

/**
 * Publish position update to Redis for SSE broadcast
 */
async function publishPositionUpdate(userId, action, position) {
  try {
    const redis = getSystemRedis();
    if (!redis) return;

    const event = {
      type: "position",
      action, // "created" | "updated" | "deleted"
      userId,
      position,
      timestamp: Date.now(),
    };

    await redis.publish(POSITIONS_PUBSUB_CHANNEL, JSON.stringify(event));
  } catch (err) {
    console.error("[positions] Failed to publish update:", err.message);
  }
}

/**
 * Transform database row to API response format
 */
function rowToPosition(row) {
  return {
    id: row.id,
    userId: row.user_id,
    symbol: row.symbol,
    positionType: row.position_type,
    direction: row.direction,
    legs: JSON.parse(row.legs_json || "[]"),
    primaryExpiration: row.primary_expiration,
    dte: row.dte,
    costBasis: row.cost_basis ? parseFloat(row.cost_basis) : null,
    costBasisType: row.cost_basis_type,
    visible: !!row.visible,
    sortOrder: row.sort_order,
    color: row.color,
    label: row.label,
    addedAt: row.added_at,
    version: row.version,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Calculate DTE from primary expiration date
 */
function calculateDte(expirationDate) {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const exp = new Date(expirationDate);
  exp.setHours(0, 0, 0, 0);
  return Math.max(0, Math.ceil((exp - now) / (1000 * 60 * 60 * 24)));
}

/**
 * Get primary (earliest) expiration from legs
 */
function getPrimaryExpiration(legs) {
  if (!legs || legs.length === 0) return null;
  const expirations = legs.map((l) => l.expiration).filter(Boolean);
  if (expirations.length === 0) return null;
  return expirations.sort()[0];
}

// ===========================================================================
// Position CRUD APIs
// ===========================================================================

/**
 * GET /api/positions
 *
 * List all positions for the authenticated user.
 * Query params:
 *   - symbol: Filter by symbol (default: all)
 *   - visible: Filter by visibility (default: all)
 *   - includeExpired: Include expired positions (default: false)
 */
router.get("/", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Build query with optional filters
    let query = `
      SELECT id, user_id, symbol, position_type, direction, legs_json,
             primary_expiration, dte, cost_basis, cost_basis_type,
             visible, sort_order, color, label, added_at, version,
             created_at, updated_at
      FROM positions
      WHERE user_id = ?
    `;
    const params = [userId];

    // Symbol filter
    if (req.query.symbol) {
      query += " AND symbol = ?";
      params.push(req.query.symbol);
    }

    // Visibility filter
    if (req.query.visible === "true") {
      query += " AND visible = TRUE";
    } else if (req.query.visible === "false") {
      query += " AND visible = FALSE";
    }

    // Expired filter (default: exclude expired)
    if (req.query.includeExpired !== "true") {
      query += " AND primary_expiration >= CURDATE()";
    }

    query += " ORDER BY sort_order ASC, primary_expiration ASC, added_at DESC";

    const [rows] = await pool.execute(query, params);

    const positions = rows.map(rowToPosition);

    res.json({
      success: true,
      data: positions,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] GET / error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/positions/:id
 *
 * Get a single position by ID.
 */
router.get("/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const positionId = parseInt(req.params.id);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [rows] = await pool.execute(
      `SELECT id, user_id, symbol, position_type, direction, legs_json,
              primary_expiration, dte, cost_basis, cost_basis_type,
              visible, sort_order, color, label, added_at, version,
              created_at, updated_at
       FROM positions
       WHERE id = ? AND user_id = ?`,
      [positionId, userId]
    );

    if (rows.length === 0) {
      return res.status(404).json({ success: false, error: "Position not found" });
    }

    const position = rowToPosition(rows[0]);

    res.json({
      success: true,
      data: position,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] GET /:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/positions
 *
 * Create a new position.
 *
 * Request body:
 * {
 *   symbol: string,
 *   positionType: string,
 *   direction: "long" | "short",
 *   legs: Array<{ strike, expiration, right, quantity, fillPrice?, fillDate? }>,
 *   costBasis?: number,
 *   costBasisType?: "debit" | "credit" | "net",
 *   visible?: boolean,
 *   sortOrder?: number,
 *   color?: string,
 *   label?: string
 * }
 */
router.post("/", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const {
      symbol = "SPX",
      positionType = "single",
      direction = "long",
      legs = [],
      costBasis = null,
      costBasisType = "debit",
      visible = true,
      sortOrder = 0,
      color = null,
      label = null,
    } = req.body;

    // Validate legs
    if (!Array.isArray(legs) || legs.length === 0) {
      return res.status(400).json({
        success: false,
        error: "At least one leg is required",
      });
    }

    // Validate each leg
    for (const leg of legs) {
      if (!leg.strike || !leg.expiration || !leg.right || !leg.quantity) {
        return res.status(400).json({
          success: false,
          error: "Each leg must have strike, expiration, right, and quantity",
        });
      }
      if (!["call", "put"].includes(leg.right)) {
        return res.status(400).json({
          success: false,
          error: "Leg right must be 'call' or 'put'",
        });
      }
    }

    // Calculate derived fields
    const primaryExpiration = getPrimaryExpiration(legs);
    if (!primaryExpiration) {
      return res.status(400).json({
        success: false,
        error: "Could not determine primary expiration from legs",
      });
    }
    const dte = calculateDte(primaryExpiration);
    const addedAt = Date.now();

    const [result] = await pool.execute(
      `INSERT INTO positions
       (user_id, symbol, position_type, direction, legs_json,
        primary_expiration, dte, cost_basis, cost_basis_type,
        visible, sort_order, color, label, added_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        userId,
        symbol,
        positionType,
        direction,
        JSON.stringify(legs),
        primaryExpiration,
        dte,
        costBasis,
        costBasisType,
        visible,
        sortOrder,
        color,
        label,
        addedAt,
      ]
    );

    // Fetch the created position
    const [rows] = await pool.execute(
      `SELECT id, user_id, symbol, position_type, direction, legs_json,
              primary_expiration, dte, cost_basis, cost_basis_type,
              visible, sort_order, color, label, added_at, version,
              created_at, updated_at
       FROM positions WHERE id = ?`,
      [result.insertId]
    );

    const position = rowToPosition(rows[0]);

    // Publish update for SSE
    await publishPositionUpdate(userId, "created", position);

    res.status(201).json({
      success: true,
      data: position,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] POST / error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * PATCH /api/positions/:id
 *
 * Update a position. Supports partial updates.
 * Uses optimistic locking via version field.
 *
 * Headers:
 *   If-Match: version number for optimistic locking
 */
router.patch("/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const positionId = parseInt(req.params.id);
    const expectedVersion = req.headers["if-match"]
      ? parseInt(req.headers["if-match"])
      : null;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Fetch current position
    const [current] = await pool.execute(
      `SELECT id, version, legs_json FROM positions WHERE id = ? AND user_id = ?`,
      [positionId, userId]
    );

    if (current.length === 0) {
      return res.status(404).json({ success: false, error: "Position not found" });
    }

    // Check optimistic lock
    if (expectedVersion !== null && current[0].version !== expectedVersion) {
      return res.status(409).json({
        success: false,
        error: "Conflict - position was modified",
        currentVersion: current[0].version,
      });
    }

    // Build dynamic update query
    const updates = [];
    const values = [];

    const fieldMap = {
      symbol: "symbol",
      positionType: "position_type",
      direction: "direction",
      costBasis: "cost_basis",
      costBasisType: "cost_basis_type",
      visible: "visible",
      sortOrder: "sort_order",
      color: "color",
      label: "label",
    };

    for (const [key, column] of Object.entries(fieldMap)) {
      if (req.body[key] !== undefined) {
        updates.push(`${column} = ?`);
        values.push(req.body[key]);
      }
    }

    // Handle legs update specially (recalculate derived fields)
    if (req.body.legs !== undefined) {
      const legs = req.body.legs;
      if (!Array.isArray(legs) || legs.length === 0) {
        return res.status(400).json({
          success: false,
          error: "At least one leg is required",
        });
      }

      updates.push("legs_json = ?");
      values.push(JSON.stringify(legs));

      // Recalculate derived fields
      const primaryExpiration = getPrimaryExpiration(legs);
      if (primaryExpiration) {
        updates.push("primary_expiration = ?");
        values.push(primaryExpiration);

        updates.push("dte = ?");
        values.push(calculateDte(primaryExpiration));
      }
    }

    if (updates.length === 0) {
      return res.status(400).json({ success: false, error: "No fields to update" });
    }

    // Increment version for optimistic locking
    updates.push("version = version + 1");

    values.push(positionId, userId);

    const [result] = await pool.execute(
      `UPDATE positions SET ${updates.join(", ")} WHERE id = ? AND user_id = ?`,
      values
    );

    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, error: "Position not found" });
    }

    // Fetch updated position
    const [rows] = await pool.execute(
      `SELECT id, user_id, symbol, position_type, direction, legs_json,
              primary_expiration, dte, cost_basis, cost_basis_type,
              visible, sort_order, color, label, added_at, version,
              created_at, updated_at
       FROM positions WHERE id = ?`,
      [positionId]
    );

    const position = rowToPosition(rows[0]);

    // Publish update for SSE
    await publishPositionUpdate(userId, "updated", position);

    res.json({
      success: true,
      data: position,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] PATCH /:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * DELETE /api/positions/:id
 *
 * Delete a position.
 */
router.delete("/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const positionId = parseInt(req.params.id);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Get position before deleting (for SSE event)
    const [existing] = await pool.execute(
      `SELECT id, symbol, position_type FROM positions WHERE id = ? AND user_id = ?`,
      [positionId, userId]
    );

    if (existing.length === 0) {
      return res.status(404).json({ success: false, error: "Position not found" });
    }

    const [result] = await pool.execute(
      `DELETE FROM positions WHERE id = ? AND user_id = ?`,
      [positionId, userId]
    );

    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, error: "Position not found" });
    }

    // Publish delete event for SSE
    await publishPositionUpdate(userId, "deleted", { id: positionId });

    res.json({
      success: true,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] DELETE /:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/positions/batch
 *
 * Create multiple positions at once.
 * Useful for importing from TOS or other platforms.
 */
router.post("/batch", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const { positions = [] } = req.body;

    if (!Array.isArray(positions) || positions.length === 0) {
      return res.status(400).json({
        success: false,
        error: "Positions array is required",
      });
    }

    if (positions.length > 50) {
      return res.status(400).json({
        success: false,
        error: "Maximum 50 positions per batch",
      });
    }

    const createdIds = [];
    const errors = [];

    for (let i = 0; i < positions.length; i++) {
      const pos = positions[i];
      try {
        const {
          symbol = "SPX",
          positionType = "single",
          direction = "long",
          legs = [],
          costBasis = null,
          costBasisType = "debit",
          visible = true,
          sortOrder = i,
          color = null,
          label = null,
        } = pos;

        if (!Array.isArray(legs) || legs.length === 0) {
          errors.push({ index: i, error: "At least one leg is required" });
          continue;
        }

        const primaryExpiration = getPrimaryExpiration(legs);
        if (!primaryExpiration) {
          errors.push({ index: i, error: "Could not determine primary expiration" });
          continue;
        }

        const dte = calculateDte(primaryExpiration);
        const addedAt = Date.now();

        const [result] = await pool.execute(
          `INSERT INTO positions
           (user_id, symbol, position_type, direction, legs_json,
            primary_expiration, dte, cost_basis, cost_basis_type,
            visible, sort_order, color, label, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            userId,
            symbol,
            positionType,
            direction,
            JSON.stringify(legs),
            primaryExpiration,
            dte,
            costBasis,
            costBasisType,
            visible,
            sortOrder,
            color,
            label,
            addedAt,
          ]
        );

        createdIds.push(result.insertId);
      } catch (err) {
        errors.push({ index: i, error: err.message });
      }
    }

    // Publish batch update for SSE
    if (createdIds.length > 0) {
      await publishPositionUpdate(userId, "batch_created", { ids: createdIds });
    }

    res.status(201).json({
      success: true,
      data: {
        created: createdIds.length,
        ids: createdIds,
        errors: errors.length > 0 ? errors : undefined,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] POST /batch error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * PATCH /api/positions/reorder
 *
 * Update sort order for multiple positions.
 *
 * Request body:
 * {
 *   order: Array<{ id: number, sortOrder: number }>
 * }
 */
router.patch("/reorder", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const { order = [] } = req.body;

    if (!Array.isArray(order) || order.length === 0) {
      return res.status(400).json({
        success: false,
        error: "Order array is required",
      });
    }

    // Update each position's sort order
    for (const item of order) {
      if (typeof item.id !== "number" || typeof item.sortOrder !== "number") {
        continue;
      }

      await pool.execute(
        `UPDATE positions SET sort_order = ? WHERE id = ? AND user_id = ?`,
        [item.sortOrder, item.id, userId]
      );
    }

    // Publish reorder event for SSE
    await publishPositionUpdate(userId, "reordered", { order });

    res.json({
      success: true,
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[positions] PATCH /reorder error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
