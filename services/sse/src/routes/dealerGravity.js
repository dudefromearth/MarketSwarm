// services/sse/src/routes/dealerGravity.js
// Dealer Gravity Service Layer API Routes
//
// Tier 1: Visualization Artifact API (passthrough from Redis)
// Tier 2: Context Snapshot API (passthrough from Redis)
// Configuration CRUD APIs
// AI Analysis APIs
//
// IMPORTANT: This service is a DELIVERY layer.
// All computation happens in the Massive service (Python).
// Redis contains ONLY final, render-ready artifacts.
//
// Dealer Gravity Lexicon (REQUIRED):
//   - Volume Node: Price level with concentrated attention
//   - Volume Well: Price level with neglect
//   - Crevasse: Extended region of persistent volume scarcity
//   - Market Memory: Persistent topology across long horizons
//
// BANNED TERMS: POC, VAH, VAL, Value Area, HVN, LVN

import { Router } from "express";
import { getSystemRedis, getMarketRedis } from "../redis.js";
import { getPool, isDbAvailable } from "../db/index.js";

const router = Router();

// Redis keys - using existing massive volume profile data
// VP Admin stores JSON string at massive:volume_profile
const VP_JSON_KEY = "massive:volume_profile";
// Legacy hash-based keys (for backwards compatibility)
const VP_DATA_KEY = "massive:volume_profile:spx";
const VP_META_KEY = "massive:volume_profile:spx:meta";
// Pre-computed artifact keys
const ARTIFACT_KEY = "dealer_gravity:artifact:spx";
const CONTEXT_KEY = "dealer_gravity:context:spx";

// ===========================================================================
// Rate Limiting for AI Analysis
// ===========================================================================

// Rate limit: 5 requests per minute per user
const RATE_LIMIT_WINDOW_MS = 60 * 1000; // 1 minute
const RATE_LIMIT_MAX_REQUESTS = 5;

// In-memory rate limit tracker: userId -> { count, windowStart }
const rateLimitTracker = new Map();

/**
 * Check if user is rate limited for AI analysis
 * @param {number|string} userId
 * @returns {{ limited: boolean, remaining: number, resetIn: number }}
 */
function checkRateLimit(userId) {
  const now = Date.now();
  const userKey = String(userId);

  let tracker = rateLimitTracker.get(userKey);

  // Initialize or reset window if expired
  if (!tracker || now - tracker.windowStart > RATE_LIMIT_WINDOW_MS) {
    tracker = { count: 0, windowStart: now };
    rateLimitTracker.set(userKey, tracker);
  }

  const remaining = Math.max(0, RATE_LIMIT_MAX_REQUESTS - tracker.count);
  const resetIn = Math.max(0, RATE_LIMIT_WINDOW_MS - (now - tracker.windowStart));

  return {
    limited: tracker.count >= RATE_LIMIT_MAX_REQUESTS,
    remaining,
    resetIn,
  };
}

/**
 * Increment rate limit counter for user
 * @param {number|string} userId
 */
function incrementRateLimit(userId) {
  const userKey = String(userId);
  const tracker = rateLimitTracker.get(userKey);
  if (tracker) {
    tracker.count++;
  }
}

// Cleanup old rate limit entries every 5 minutes
setInterval(() => {
  const now = Date.now();
  for (const [key, tracker] of rateLimitTracker.entries()) {
    if (now - tracker.windowStart > RATE_LIMIT_WINDOW_MS * 2) {
      rateLimitTracker.delete(key);
    }
  }
}, 5 * 60 * 1000);

// ===========================================================================
// Tier 1: Visualization Artifact API
// ===========================================================================

/**
 * GET /api/dealer-gravity/artifact
 *
 * Returns the volume profile artifact from Redis.
 * Reads from massive:volume_profile:spx (hash) and transforms to artifact format.
 *
 * Response format:
 * {
 *   profile: { min, step, bins, levels },
 *   structures: { volume_nodes, volume_wells, crevasses },
 *   meta: { spot, algorithm, artifact_version, last_update, min_price, max_price }
 * }
 */
router.get("/artifact", async (req, res) => {
  try {
    // Volume profile data is on system-redis (massive:volume_profile)
    const redis = getSystemRedis();

    // First check for pre-computed artifact (on system-redis)
    const precomputed = await redis.get(ARTIFACT_KEY);
    if (precomputed) {
      const data = JSON.parse(precomputed);
      return res.json({ success: true, data, ts: Date.now() });
    }

    // Try reading VP Admin JSON format (massive:volume_profile)
    const vpJson = await redis.get(VP_JSON_KEY);
    if (vpJson) {
      const vpData = JSON.parse(vpJson);

      // Use TV smoothed buckets (preferred) or fall back to RAW
      const buckets = vpData.buckets_tv || vpData.buckets_raw || {};
      const minPrice = vpData.min_price || 2000;
      const maxPrice = vpData.max_price || 7000;
      const step = vpData.bin_size || 1;

      // Build bins array from buckets (sparse → dense)
      const bins = [];
      let maxVolume = 0;
      for (let price = minPrice; price <= maxPrice; price += step) {
        const vol = parseFloat(buckets[String(price)] || 0);
        bins.push(vol);
        if (vol > maxVolume) maxVolume = vol;
      }

      // Normalize to 0-1000 scale
      const normalizedScale = 1000;
      const normalizedBins = bins.map(v =>
        maxVolume > 0 ? Math.round((v / maxVolume) * normalizedScale) : 0
      );

      // Get structures from VP Admin analysis
      const structures = vpData.structures || {};

      const artifact = {
        profile: {
          min: minPrice,
          max: maxPrice,
          step: step,
          bins: normalizedBins,
          maxVolume,
          normalizedScale,
        },
        structures: {
          volume_nodes: structures.volume_nodes || [],
          volume_wells: structures.volume_wells || [],
          crevasses: structures.crevasses || [],
        },
        meta: {
          spot: null, // Would come from live spot price
          algorithm: "tv_microbins_30",
          artifact_version: vpData.last_updated || "v1",
          last_update: vpData.last_updated || new Date().toISOString(),
          min_price: minPrice,
          max_price: maxPrice,
          bin_count: vpData.bin_count || bins.length,
        },
      };

      return res.json({ success: true, data: artifact, ts: Date.now() });
    }

    // Fall back to reading from massive:volume_profile:spx hash (legacy)
    const [vpData, metaData] = await Promise.all([
      redis.hgetall(VP_DATA_KEY),
      redis.hgetall(VP_META_KEY),
    ]);

    if (!vpData || Object.keys(vpData).length === 0) {
      return res.status(503).json({
        success: false,
        error: "Volume profile data not available",
      });
    }

    // Transform hash data to artifact format
    // Hash keys are price * 100 (cents), values are volumes
    const minPrice = parseFloat(metaData?.min_price) || 0;
    const maxPrice = parseFloat(metaData?.max_price) || Infinity;

    const levels = [];
    for (const [priceKey, volume] of Object.entries(vpData)) {
      const price = parseFloat(priceKey) / 100; // Convert from cents
      // Filter to relevant price range (skip old historical data)
      if (price >= minPrice && price <= maxPrice) {
        levels.push({ price, volume: parseInt(volume, 10) });
      }
    }

    // Sort by price
    levels.sort((a, b) => a.price - b.price);

    // Calculate bins (normalized to 0-1000 scale)
    const maxVolume = Math.max(...levels.map(l => l.volume));
    const normalizedScale = 1000;

    // Build artifact response
    const artifact = {
      profile: {
        min: parseFloat(metaData?.min_price) || levels[0]?.price || 0,
        max: parseFloat(metaData?.max_price) || levels[levels.length - 1]?.price || 0,
        step: levels.length > 1 ? (levels[1].price - levels[0].price) : 0.1,
        levels: levels.map(l => ({
          price: l.price,
          volume: l.volume,
          normalized: Math.round((l.volume / maxVolume) * normalizedScale),
        })),
        maxVolume,
        normalizedScale,
      },
      structures: {
        // Structures are added by Node Admin AI analysis
        // Return empty arrays if not yet analyzed
        volume_nodes: [],
        volume_wells: [],
        crevasses: [],
      },
      meta: {
        algorithm: "massive_vp",
        artifact_version: "live",
        last_update: metaData?.last_updated || new Date().toISOString(),
        min_price: parseFloat(metaData?.min_price) || 0,
        max_price: parseFloat(metaData?.max_price) || 0,
        total_volume: parseInt(metaData?.total_volume, 10) || 0,
        levels_count: parseInt(metaData?.levels, 10) || levels.length,
        days_processed: parseInt(metaData?.days_processed, 10) || 0,
      },
    };

    res.json({ success: true, data: artifact, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] /artifact error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ===========================================================================
// Tier 2: Context Snapshot API
// ===========================================================================

/**
 * GET /api/dealer-gravity/context
 *
 * Passthrough from Redis - returns the pre-computed context snapshot.
 * For Trade Selector, RiskGraph, ML systems.
 * Extremely small (~200 bytes), deterministic, ML-ready.
 *
 * Response format:
 * {
 *   symbol, spot, nearest_volume_node_dist, volume_well_proximity,
 *   in_crevasse, market_memory_strength, gamma_alignment, timestamp
 * }
 */
router.get("/context", async (req, res) => {
  try {
    const redis = getSystemRedis();

    // First check for pre-computed context
    const precomputed = await redis.get(CONTEXT_KEY);
    if (precomputed) {
      const data = JSON.parse(precomputed);
      return res.json({ success: true, data, ts: Date.now() });
    }

    // Compute basic context from VP data
    const vpJson = await redis.get(VP_JSON_KEY);
    if (!vpJson) {
      return res.status(503).json({
        success: false,
        error: "Context not ready - volume profile data not available",
      });
    }

    const vpData = JSON.parse(vpJson);
    const structures = vpData.structures || {};
    const volumeNodes = structures.volume_nodes || [];
    const volumeWells = structures.volume_wells || [];
    const crevasses = structures.crevasses || [];

    // Get current spot price (from market-redis if available)
    let spot = null;
    try {
      const marketRedis = getMarketRedis();
      const spotData = await marketRedis.get("massive:model:spot:I:SPX");
      if (spotData) {
        const parsed = JSON.parse(spotData);
        spot = parsed.value || parsed.spot || null;
      }
    } catch (e) {
      // Spot not available
    }

    // Compute context metrics
    let nearestVolumeNode = null;
    let nearestVolumeNodeDist = null;
    let volumeWellProximity = null;
    let inCrevasse = false;

    if (spot && volumeNodes.length > 0) {
      // Find nearest volume node
      let minDist = Infinity;
      for (const node of volumeNodes) {
        const dist = Math.abs(spot - node);
        if (dist < minDist) {
          minDist = dist;
          nearestVolumeNode = node;
        }
      }
      nearestVolumeNodeDist = (nearestVolumeNode - spot) / spot; // Relative distance
    }

    if (spot && volumeWells.length > 0) {
      // Find proximity to nearest volume well
      let minDist = Infinity;
      for (const well of volumeWells) {
        const dist = Math.abs(spot - well);
        if (dist < minDist) {
          minDist = dist;
        }
      }
      volumeWellProximity = spot > 0 ? minDist / spot : null;
    }

    if (spot && crevasses.length > 0) {
      // Check if spot is in any crevasse
      for (const [start, end] of crevasses) {
        if (spot >= start && spot <= end) {
          inCrevasse = true;
          break;
        }
      }
    }

    const context = {
      symbol: vpData.synthetic_symbol || "SPX",
      spot,
      nearestVolumeNode,
      nearestVolumeNodeDist,
      volumeWellProximity,
      inCrevasse,
      marketMemoryStrength: 0.85, // Default - would be computed from volume distribution
      gammaAlignment: null, // Would come from GEX data
      artifactVersion: vpData.last_updated || "v1",
      timestamp: new Date().toISOString(),
    };

    res.json({ success: true, data: context, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] /context error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ===========================================================================
// Configuration APIs
// ===========================================================================

/**
 * GET /api/dealer-gravity/configs
 *
 * List user's Dealer Gravity display configurations.
 */
router.get("/configs", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [rows] = await pool.execute(
      `SELECT id, name, enabled, mode, width_percent, num_bins, capping_sigma,
              color, transparency, show_volume_nodes, show_volume_wells,
              show_crevasses, is_default, created_at, updated_at
       FROM dealer_gravity_configs
       WHERE user_id = ?
       ORDER BY is_default DESC, name ASC`,
      [userId]
    );

    // Convert MySQL booleans
    const configs = rows.map((row) => ({
      id: row.id,
      name: row.name,
      enabled: !!row.enabled,
      mode: row.mode,
      widthPercent: row.width_percent,
      numBins: row.num_bins,
      cappingSigma: parseFloat(row.capping_sigma),
      color: row.color,
      transparency: row.transparency,
      showVolumeNodes: !!row.show_volume_nodes,
      showVolumeWells: !!row.show_volume_wells,
      showCrevasses: !!row.show_crevasses,
      isDefault: !!row.is_default,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    }));

    res.json({ success: true, data: configs, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] /configs error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/dealer-gravity/configs
 *
 * Create a new Dealer Gravity configuration.
 */
router.post("/configs", async (req, res) => {
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
      name = "Default",
      enabled = true,
      mode = "tv",
      widthPercent = 15,
      numBins = 50,
      cappingSigma = 2.0,
      color = "#9333ea",
      transparency = 50,
      showVolumeNodes = true,
      showVolumeWells = true,
      showCrevasses = true,
      isDefault = false,
    } = req.body;

    // If this is default, unset other defaults
    if (isDefault) {
      await pool.execute(
        `UPDATE dealer_gravity_configs SET is_default = FALSE WHERE user_id = ?`,
        [userId]
      );
    }

    const [result] = await pool.execute(
      `INSERT INTO dealer_gravity_configs
       (user_id, name, enabled, mode, width_percent, num_bins, capping_sigma,
        color, transparency, show_volume_nodes, show_volume_wells, show_crevasses, is_default)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        userId,
        name,
        enabled,
        mode,
        widthPercent,
        numBins,
        cappingSigma,
        color,
        transparency,
        showVolumeNodes,
        showVolumeWells,
        showCrevasses,
        isDefault,
      ]
    );

    res.json({
      success: true,
      data: { id: result.insertId },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[dealer-gravity] POST /configs error:", err.message);

    if (err.code === "ER_DUP_ENTRY") {
      return res.status(409).json({
        success: false,
        error: "Configuration with this name already exists",
      });
    }

    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * PATCH /api/dealer-gravity/configs/:id
 *
 * Update a Dealer Gravity configuration.
 */
router.patch("/configs/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const configId = parseInt(req.params.id);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Build dynamic update query
    const updates = [];
    const values = [];

    const fieldMap = {
      name: "name",
      enabled: "enabled",
      mode: "mode",
      widthPercent: "width_percent",
      numBins: "num_bins",
      cappingSigma: "capping_sigma",
      color: "color",
      transparency: "transparency",
      showVolumeNodes: "show_volume_nodes",
      showVolumeWells: "show_volume_wells",
      showCrevasses: "show_crevasses",
      isDefault: "is_default",
    };

    for (const [key, column] of Object.entries(fieldMap)) {
      if (req.body[key] !== undefined) {
        updates.push(`${column} = ?`);
        values.push(req.body[key]);
      }
    }

    if (updates.length === 0) {
      return res.status(400).json({ success: false, error: "No fields to update" });
    }

    // If setting as default, unset other defaults
    if (req.body.isDefault) {
      await pool.execute(
        `UPDATE dealer_gravity_configs SET is_default = FALSE WHERE user_id = ?`,
        [userId]
      );
    }

    values.push(configId, userId);

    const [result] = await pool.execute(
      `UPDATE dealer_gravity_configs SET ${updates.join(", ")} WHERE id = ? AND user_id = ?`,
      values
    );

    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, error: "Configuration not found" });
    }

    res.json({ success: true, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] PATCH /configs/:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * DELETE /api/dealer-gravity/configs/:id
 *
 * Delete a Dealer Gravity configuration.
 */
router.delete("/configs/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const configId = parseInt(req.params.id);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [result] = await pool.execute(
      `DELETE FROM dealer_gravity_configs WHERE id = ? AND user_id = ?`,
      [configId, userId]
    );

    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, error: "Configuration not found" });
    }

    res.json({ success: true, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] DELETE /configs/:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ===========================================================================
// GEX Panel Configuration APIs
// ===========================================================================

/**
 * GET /api/dealer-gravity/gex-configs
 *
 * List user's GEX panel configurations.
 */
router.get("/gex-configs", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [rows] = await pool.execute(
      `SELECT id, enabled, mode, calls_color, puts_color, width_px, is_default, created_at, updated_at
       FROM gex_panel_configs
       WHERE user_id = ?
       ORDER BY is_default DESC, created_at ASC`,
      [userId]
    );

    const configs = rows.map((row) => ({
      id: row.id,
      enabled: !!row.enabled,
      mode: row.mode,
      callsColor: row.calls_color,
      putsColor: row.puts_color,
      widthPx: row.width_px,
      isDefault: !!row.is_default,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    }));

    res.json({ success: true, data: configs, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] /gex-configs error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * POST /api/dealer-gravity/gex-configs
 *
 * Create a GEX panel configuration.
 */
router.post("/gex-configs", async (req, res) => {
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
      enabled = true,
      mode = "combined",
      callsColor = "#22c55e",
      putsColor = "#ef4444",
      widthPx = 60,
      isDefault = false,
    } = req.body;

    if (isDefault) {
      await pool.execute(
        `UPDATE gex_panel_configs SET is_default = FALSE WHERE user_id = ?`,
        [userId]
      );
    }

    const [result] = await pool.execute(
      `INSERT INTO gex_panel_configs
       (user_id, enabled, mode, calls_color, puts_color, width_px, is_default)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [userId, enabled, mode, callsColor, putsColor, widthPx, isDefault]
    );

    res.json({
      success: true,
      data: { id: result.insertId },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[dealer-gravity] POST /gex-configs error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * PATCH /api/dealer-gravity/gex-configs/:id
 *
 * Update a GEX panel configuration.
 */
router.patch("/gex-configs/:id", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const configId = parseInt(req.params.id);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const updates = [];
    const values = [];

    const fieldMap = {
      enabled: "enabled",
      mode: "mode",
      callsColor: "calls_color",
      putsColor: "puts_color",
      widthPx: "width_px",
      isDefault: "is_default",
    };

    for (const [key, column] of Object.entries(fieldMap)) {
      if (req.body[key] !== undefined) {
        updates.push(`${column} = ?`);
        values.push(req.body[key]);
      }
    }

    if (updates.length === 0) {
      return res.status(400).json({ success: false, error: "No fields to update" });
    }

    if (req.body.isDefault) {
      await pool.execute(
        `UPDATE gex_panel_configs SET is_default = FALSE WHERE user_id = ?`,
        [userId]
      );
    }

    values.push(configId, userId);

    const [result] = await pool.execute(
      `UPDATE gex_panel_configs SET ${updates.join(", ")} WHERE id = ? AND user_id = ?`,
      values
    );

    if (result.affectedRows === 0) {
      return res.status(404).json({ success: false, error: "Configuration not found" });
    }

    res.json({ success: true, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] PATCH /gex-configs/:id error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ===========================================================================
// AI Analysis APIs
// ===========================================================================

/**
 * POST /api/dealer-gravity/analyze
 *
 * Request AI visual analysis of the current Dealer Gravity chart.
 * Rate limited to prevent abuse.
 *
 * Request body:
 * {
 *   imageBase64: string,  // Chart screenshot
 *   spotPrice: number     // Current spot price
 * }
 */
router.post("/analyze", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const userId = req.user?.wp?.id || req.user?.id;

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    // Rate limiting check
    const rateLimit = checkRateLimit(userId);
    if (rateLimit.limited) {
      return res.status(429).json({
        success: false,
        error: "Rate limit exceeded",
        retryAfter: Math.ceil(rateLimit.resetIn / 1000),
        message: `AI analysis is limited to ${RATE_LIMIT_MAX_REQUESTS} requests per minute. Try again in ${Math.ceil(rateLimit.resetIn / 1000)} seconds.`,
      });
    }

    // Increment rate limit counter
    incrementRateLimit(userId);

    const { imageBase64, spotPrice } = req.body;

    if (!imageBase64) {
      return res.status(400).json({ success: false, error: "Image data required" });
    }

    // TODO: Implement actual AI analysis via Copilot service
    // For now, return a placeholder response

    const analysis = {
      volumeNodes: [],
      volumeWells: [],
      crevasses: [],
      marketMemoryStrength: 0.75,
      bias: "neutral",
      summary: "AI analysis integration pending - connect to Copilot service",
    };

    // Store analysis in database
    const pool = getPool();
    const [result] = await pool.execute(
      `INSERT INTO dealer_gravity_analyses
       (user_id, symbol, spot_price, volume_nodes, volume_wells, crevasses,
        market_memory_strength, bias, analysis_text, provider, model)
       VALUES (?, 'SPX', ?, ?, ?, ?, ?, ?, ?, 'anthropic', 'claude-sonnet')`,
      [
        userId,
        spotPrice || null,
        JSON.stringify(analysis.volumeNodes),
        JSON.stringify(analysis.volumeWells),
        JSON.stringify(analysis.crevasses),
        analysis.marketMemoryStrength,
        analysis.bias,
        analysis.summary,
      ]
    );

    res.json({
      success: true,
      data: {
        id: result.insertId,
        ...analysis,
      },
      ts: Date.now(),
    });
  } catch (err) {
    console.error("[dealer-gravity] POST /analyze error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

/**
 * GET /api/dealer-gravity/analyses
 *
 * Get analysis history for the current user.
 * Query params: limit (default 10, max 50)
 */
router.get("/analyses", async (req, res) => {
  if (!isDbAvailable()) {
    return res.status(503).json({ success: false, error: "Database not available" });
  }

  try {
    const pool = getPool();
    const userId = req.user?.id;
    const limit = Math.min(Math.max(parseInt(req.query.limit) || 10, 1), 50);

    if (!userId) {
      return res.status(401).json({ success: false, error: "Not authenticated" });
    }

    const [rows] = await pool.execute(
      `SELECT id, symbol, spot_price, volume_nodes, volume_wells, crevasses,
              market_memory_strength, bias, analysis_text, provider, model,
              tokens_used, latency_ms, created_at
       FROM dealer_gravity_analyses
       WHERE user_id = ?
       ORDER BY created_at DESC
       LIMIT ?`,
      [userId, limit]
    );

    const analyses = rows.map((row) => ({
      id: row.id,
      symbol: row.symbol,
      spotPrice: parseFloat(row.spot_price),
      volumeNodes: JSON.parse(row.volume_nodes || "[]"),
      volumeWells: JSON.parse(row.volume_wells || "[]"),
      crevasses: JSON.parse(row.crevasses || "[]"),
      marketMemoryStrength: parseFloat(row.market_memory_strength),
      bias: row.bias,
      summary: row.analysis_text,
      provider: row.provider,
      model: row.model,
      tokensUsed: row.tokens_used,
      latencyMs: row.latency_ms,
      createdAt: row.created_at,
    }));

    res.json({ success: true, data: analyses, ts: Date.now() });
  } catch (err) {
    console.error("[dealer-gravity] /analyses error:", err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

export default router;
