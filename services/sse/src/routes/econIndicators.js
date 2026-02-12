// services/sse/src/routes/econIndicators.js
// Admin CRUD API for Economic Indicators Registry

import { Router } from "express";
import { randomUUID } from "crypto";
import { getPool, isDbAvailable } from "../db/index.js";
import { getMarketRedis } from "../redis.js";
import { requireAdmin } from "./admin.js";
import { buildRollingSchedule } from "../econ/scheduleBuilder.js";

const router = Router();

/**
 * Compute tier from rating (server-authoritative)
 */
function ratingToTier(rating) {
  if (rating >= 9) return "critical";
  if (rating >= 7) return "high";
  if (rating >= 5) return "medium";
  return "low";
}

/**
 * Publish cache invalidation event so Vexy reloads
 */
async function publishRefresh() {
  try {
    const redis = getMarketRedis();
    if (redis) {
      await redis.publish("vexy:econ-indicators:refresh", "updated");
    }
  } catch (e) {
    console.error("[econ-indicators] Failed to publish refresh:", e.message);
  }
}

/**
 * GET /api/admin/economic-indicators
 * List all indicators with aliases, sorted by rating desc
 */
router.get("/", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database unavailable" });
  }
  const pool = getPool();

  try {
    const [indicators] = await pool.execute(`
      SELECT id, \`key\`, name, rating, tier, description, is_active,
             release_time_et, cadence, rule_json,
             created_at, updated_at
      FROM economic_indicators
      ORDER BY rating DESC, name ASC
    `);

    // Fetch all aliases in one query
    const [aliases] = await pool.execute(`
      SELECT id, indicator_id, alias
      FROM economic_indicator_aliases
      ORDER BY alias ASC
    `);

    // Group aliases by indicator_id
    const aliasMap = {};
    for (const a of aliases) {
      if (!aliasMap[a.indicator_id]) aliasMap[a.indicator_id] = [];
      aliasMap[a.indicator_id].push(a.alias);
    }

    const data = indicators.map(ind => ({
      ...ind,
      is_active: !!ind.is_active,
      aliases: aliasMap[ind.id] || [],
    }));

    res.json({ success: true, data, ts: Date.now() });
  } catch (err) {
    console.error("[econ-indicators] List error:", err);
    res.status(500).json({ success: false, error: "Failed to list indicators" });
  }
});

/**
 * POST /api/admin/economic-indicators
 * Create a new indicator + aliases
 */
router.post("/", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database unavailable" });
  }
  const pool = getPool();
  const { key, name, rating, description, aliases, release_time_et, cadence, rule_json } = req.body;

  if (!key || !name || rating === undefined) {
    return res.status(400).json({ success: false, error: "key, name, and rating are required" });
  }

  const VALID_CADENCES = ["fixed_dates", "first_friday", "nth_weekday", "weekly", "manual"];
  if (cadence && !VALID_CADENCES.includes(cadence)) {
    return res.status(400).json({ success: false, error: `cadence must be one of: ${VALID_CADENCES.join(", ")}` });
  }

  const numRating = Math.round(Number(rating));
  if (numRating < 1 || numRating > 10) {
    return res.status(400).json({ success: false, error: "rating must be between 1 and 10" });
  }

  const tier = ratingToTier(numRating);
  const id = randomUUID();
  const ruleJsonStr = rule_json ? (typeof rule_json === "string" ? rule_json : JSON.stringify(rule_json)) : null;

  const conn = await pool.getConnection();
  try {
    await conn.beginTransaction();

    await conn.execute(
      `INSERT INTO economic_indicators (id, \`key\`, name, rating, tier, description, is_active, release_time_et, cadence, rule_json)
       VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)`,
      [id, key, name, numRating, tier, description || null, release_time_et || null, cadence || null, ruleJsonStr]
    );

    if (aliases && Array.isArray(aliases)) {
      for (const alias of aliases) {
        if (alias && alias.trim()) {
          await conn.execute(
            `INSERT INTO economic_indicator_aliases (id, indicator_id, alias) VALUES (?, ?, ?)`,
            [randomUUID(), id, alias.trim()]
          );
        }
      }
    }

    await conn.commit();

    console.log(`[econ-indicators] Created: ${key} (rating=${numRating}, tier=${tier})`);
    await publishRefresh();

    res.json({
      success: true,
      data: { id, key, name, rating: numRating, tier, description, is_active: true, aliases: aliases || [] },
      ts: Date.now(),
    });
  } catch (err) {
    await conn.rollback();
    if (err.code === "ER_DUP_ENTRY") {
      return res.status(409).json({ success: false, error: `Indicator with key '${key}' already exists` });
    }
    console.error("[econ-indicators] Create error:", err);
    res.status(500).json({ success: false, error: "Failed to create indicator" });
  } finally {
    conn.release();
  }
});

/**
 * PUT /api/admin/economic-indicators/:id
 * Update name, rating, description, is_active, aliases
 * Key is immutable after creation
 */
router.put("/:id", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database unavailable" });
  }
  const pool = getPool();
  const { id } = req.params;
  const { name, rating, description, is_active, aliases, release_time_et, cadence, rule_json } = req.body;

  const VALID_CADENCES = ["fixed_dates", "first_friday", "nth_weekday", "weekly", "manual"];
  if (cadence !== undefined && cadence !== null && !VALID_CADENCES.includes(cadence)) {
    return res.status(400).json({ success: false, error: `cadence must be one of: ${VALID_CADENCES.join(", ")}` });
  }

  const conn = await pool.getConnection();
  try {
    await conn.beginTransaction();

    const [existing] = await conn.execute(
      `SELECT id, \`key\`, name, rating, tier, description, is_active FROM economic_indicators WHERE id = ?`,
      [id]
    );

    if (!existing.length) {
      await conn.rollback();
      return res.status(404).json({ success: false, error: "Indicator not found" });
    }

    const before = existing[0];
    const updates = {};
    const setClauses = [];
    const params = [];

    if (name !== undefined) {
      setClauses.push("name = ?");
      params.push(name);
      updates.name = name;
    }

    if (rating !== undefined) {
      const numRating = Math.round(Number(rating));
      if (numRating < 1 || numRating > 10) {
        await conn.rollback();
        return res.status(400).json({ success: false, error: "rating must be between 1 and 10" });
      }
      const tier = ratingToTier(numRating);
      setClauses.push("rating = ?", "tier = ?");
      params.push(numRating, tier);
      updates.rating = numRating;
      updates.tier = tier;
    }

    if (description !== undefined) {
      setClauses.push("description = ?");
      params.push(description);
      updates.description = description;
    }

    if (is_active !== undefined) {
      setClauses.push("is_active = ?");
      params.push(is_active ? 1 : 0);
      updates.is_active = !!is_active;
    }

    if (release_time_et !== undefined) {
      setClauses.push("release_time_et = ?");
      params.push(release_time_et || null);
      updates.release_time_et = release_time_et;
    }

    if (cadence !== undefined) {
      setClauses.push("cadence = ?");
      params.push(cadence || null);
      updates.cadence = cadence;
    }

    if (rule_json !== undefined) {
      const ruleJsonStr = rule_json ? (typeof rule_json === "string" ? rule_json : JSON.stringify(rule_json)) : null;
      setClauses.push("rule_json = ?");
      params.push(ruleJsonStr);
      updates.rule_json = rule_json;
    }

    if (setClauses.length > 0) {
      params.push(id);
      await conn.execute(
        `UPDATE economic_indicators SET ${setClauses.join(", ")} WHERE id = ?`,
        params
      );
    }

    if (aliases !== undefined && Array.isArray(aliases)) {
      await conn.execute(
        `DELETE FROM economic_indicator_aliases WHERE indicator_id = ?`,
        [id]
      );
      for (const alias of aliases) {
        if (alias && alias.trim()) {
          await conn.execute(
            `INSERT INTO economic_indicator_aliases (id, indicator_id, alias) VALUES (?, ?, ?)`,
            [randomUUID(), id, alias.trim()]
          );
        }
      }
      updates.aliases = aliases;
    }

    await conn.commit();

    console.log(`[econ-indicators] Updated ${before.key}: ${JSON.stringify(updates)}`);
    await publishRefresh();

    const [updated] = await pool.execute(
      `SELECT id, \`key\`, name, rating, tier, description, is_active,
              release_time_et, cadence, rule_json,
              created_at, updated_at
       FROM economic_indicators WHERE id = ?`,
      [id]
    );

    const [updatedAliases] = await pool.execute(
      `SELECT alias FROM economic_indicator_aliases WHERE indicator_id = ? ORDER BY alias`,
      [id]
    );

    res.json({
      success: true,
      data: {
        ...updated[0],
        is_active: !!updated[0].is_active,
        aliases: updatedAliases.map(a => a.alias),
      },
      ts: Date.now(),
    });
  } catch (err) {
    await conn.rollback();
    console.error("[econ-indicators] Update error:", err);
    res.status(500).json({ success: false, error: "Failed to update indicator" });
  } finally {
    conn.release();
  }
});

/**
 * DELETE /api/admin/economic-indicators/:id
 * Soft delete (set is_active = 0)
 */
router.delete("/:id", requireAdmin, async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database unavailable" });
  }
  const pool = getPool();
  const { id } = req.params;

  try {
    const [existing] = await pool.execute(
      `SELECT id, \`key\`, name FROM economic_indicators WHERE id = ?`,
      [id]
    );

    if (!existing.length) {
      return res.status(404).json({ success: false, error: "Indicator not found" });
    }

    await pool.execute(
      `UPDATE economic_indicators SET is_active = 0 WHERE id = ?`,
      [id]
    );

    console.log(`[econ-indicators] Soft-deleted: ${existing[0].key}`);
    await publishRefresh();

    res.json({ success: true, data: { id, key: existing[0].key, is_active: false }, ts: Date.now() });
  } catch (err) {
    console.error("[econ-indicators] Delete error:", err);
    res.status(500).json({ success: false, error: "Failed to delete indicator" });
  }
});

/**
 * POST /api/admin/economic-indicators/result
 * Enter a post-release report outcome (actual vs expected)
 */
router.post("/result", requireAdmin, async (req, res) => {
  const { date, key, actual, expected } = req.body;

  if (!date || !key || actual === undefined || expected === undefined) {
    return res.status(400).json({ success: false, error: "date, key, actual, and expected are required" });
  }

  const parseNumeric = (val) => {
    if (typeof val === "number") return val;
    const str = String(val).replace(/[%KMBkmb,]/g, "").trim();
    return parseFloat(str);
  };

  const actualNum = parseNumeric(actual);
  const expectedNum = parseNumeric(expected);

  let status;
  if (isNaN(actualNum) || isNaN(expectedNum)) {
    status = "met";
  } else if (actualNum > expectedNum) {
    status = "beat";
  } else if (actualNum < expectedNum) {
    status = "missed";
  } else {
    status = "met";
  }

  const redisKey = `massive:econ:result:${date}:${key}`;
  const value = JSON.stringify({ actual: String(actual), expected: String(expected), status });

  try {
    const redis = getMarketRedis();
    await redis.set(redisKey, value, "EX", 86400 * 7);

    console.log(`[econ-indicators] Result recorded: ${date}/${key} = ${status} (actual=${actual}, expected=${expected})`);

    res.json({
      success: true,
      data: { date, key, actual: String(actual), expected: String(expected), status },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[econ-indicators] Result error:", err);
    res.status(500).json({ success: false, error: "Failed to store result" });
  }
});

/**
 * POST /api/admin/economic-indicators/build-rolling
 * Trigger on-demand build of the rolling schedule artifact
 */
router.post("/build-rolling", requireAdmin, async (req, res) => {
  const { window_days } = req.body;

  try {
    const result = await buildRollingSchedule({ windowDays: window_days || 7 });
    console.log(`[econ-indicators] Rolling schedule built: ${result.event_count} events`);
    res.json({ success: true, ...result });
  } catch (err) {
    console.error("[econ-indicators] Build-rolling error:", err);
    res.status(500).json({ success: false, error: "Failed to build rolling schedule" });
  }
});

/**
 * GET /api/admin/economic-indicators/rolling-schedule
 * Inspect the current rolling schedule artifact from Redis
 */
router.get("/rolling-schedule", requireAdmin, async (req, res) => {
  try {
    const redis = getMarketRedis();
    if (!redis) {
      return res.status(503).json({ success: false, error: "Redis unavailable" });
    }

    const raw = await redis.get("massive:econ:schedule:rolling:v1");
    if (!raw) {
      return res.json({ success: true, data: null, message: "No rolling schedule artifact exists yet" });
    }

    res.json({ success: true, data: JSON.parse(raw), ts: Date.now() });
  } catch (err) {
    console.error("[econ-indicators] Rolling-schedule read error:", err);
    res.status(500).json({ success: false, error: "Failed to read rolling schedule" });
  }
});

export default router;
