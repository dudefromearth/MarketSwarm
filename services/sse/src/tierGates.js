// services/sse/src/tierGates.js
// Tier-based feature gating — reads config from Redis, caches in memory,
// listens for pub/sub updates for instant propagation.

import { getSystemRedis } from "./redis.js";
import Redis from "ioredis";

let gatesConfig = null;
let subConnection = null;

/**
 * Initialize tier gates: load config from Redis, subscribe to updates.
 * Call after initRedis() in main().
 */
export async function initTierGates(config) {
  await loadGatesConfig();

  // Subscribe to update notifications via dedicated connection
  const systemUrl =
    config?.buses?.["system-redis"]?.url || "redis://127.0.0.1:6379";
  subConnection = new Redis(systemUrl, {
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });

  subConnection.subscribe("tier_gates:updated");
  subConnection.on("message", (channel) => {
    if (channel === "tier_gates:updated") {
      console.log("[tier-gates] Config update received, reloading...");
      loadGatesConfig();
    }
  });

  console.log("[tier-gates] Initialized, mode:", gatesConfig?.mode || "unknown");
}

/**
 * Load gates config from Redis key `tier_gates`.
 */
async function loadGatesConfig() {
  try {
    const redis = getSystemRedis();
    if (!redis) return;
    const raw = await redis.get("tier_gates");
    if (raw) {
      gatesConfig = JSON.parse(raw);
    }
  } catch (err) {
    console.error("[tier-gates] Failed to load config:", err.message);
  }
}

/**
 * Determine user tier from WordPress roles array and/or subscription_tier.
 *
 * When subscription_tier is provided (from the JWT's subscription_tier field),
 * it takes precedence over role-based inference. This is because the WordPress
 * "subscriber" role is a generic WP role shared by observers AND activators,
 * making role-based detection ambiguous.
 *
 * Mirrors Python tier_from_roles() in tier_config.py.
 *
 * @param {string[]} roles - WordPress roles array
 * @param {string} [subscriptionTier] - Explicit subscription tier from JWT (e.g. "Observer Access", "Activator", etc.)
 */
export function tierFromRoles(roles, subscriptionTier) {
  // If we have an explicit subscription_tier from the JWT, use it as primary source
  if (subscriptionTier && typeof subscriptionTier === "string") {
    const tierLower = subscriptionTier.toLowerCase().trim();

    if (tierLower.includes("administrator") || tierLower.includes("admin"))
      return "administrator";
    if (tierLower.includes("coaching"))
      return "coaching";
    if (tierLower.includes("navigator"))
      return "navigator";
    if (tierLower.includes("activator"))
      return "activator";
    if (tierLower.includes("observer"))
      return "observer";
  }

  // Fall back to role-based detection
  if (!roles || !Array.isArray(roles)) return "observer";

  const lower = roles.map((r) => r.toLowerCase());

  if (lower.includes("administrator") || lower.includes("admin"))
    return "administrator";
  if (lower.includes("coaching") || lower.includes("fotw_coaching"))
    return "coaching";
  if (lower.includes("navigator") || lower.includes("fotw_navigator"))
    return "navigator";
  if (
    lower.includes("activator") ||
    lower.includes("fotw_activator")
  )
    return "activator";

  // NOTE: "subscriber" is WordPress's default role and does NOT imply "activator".
  // Observers also have the "subscriber" role. Without an explicit subscription_tier,
  // a user with only the "subscriber" role defaults to "observer".
  return "observer";
}

/**
 * Check whether a feature is allowed for a given tier.
 *
 * @param {string} userTier - e.g. "observer", "activator", "navigator"
 * @param {string} featureKey - e.g. "journal_access", "vexy_chat_rate"
 * @returns {{ allowed: boolean, limit: number|null }}
 *   - For booleans: { allowed: true/false, limit: null }
 *   - For numbers: { allowed: true, limit: N } where -1 = unlimited
 *   - If full_production mode or no config: { allowed: true, limit: null }
 */
export function checkGate(userTier, featureKey) {
  // No config loaded or full_production = everything allowed
  if (!gatesConfig || gatesConfig.mode === "full_production") {
    return { allowed: true, limit: null };
  }

  // Administrator and coaching always bypass
  if (userTier === "administrator" || userTier === "coaching") {
    return { allowed: true, limit: null };
  }

  const defaults = gatesConfig.defaults || {};
  const tierOverrides = gatesConfig.tiers?.[userTier] || {};
  const featureDef = defaults[featureKey];

  if (!featureDef) {
    // Unknown feature — allow by default
    return { allowed: true, limit: null };
  }

  // Get the value: tier override > default
  const val =
    tierOverrides[featureKey] !== undefined
      ? tierOverrides[featureKey]
      : featureDef.value;

  if (featureDef.type === "boolean") {
    return { allowed: !!val, limit: null };
  }

  // Number type — -1 means unlimited (allowed), otherwise it's a cap
  return { allowed: true, limit: val };
}

/**
 * Get the full gates config (for the frontend API endpoint).
 */
export function getTierGates() {
  return gatesConfig;
}

/**
 * Express middleware factory: blocks requests when a boolean gate is off.
 *
 * Usage: app.use("/api/journals", gateMiddleware("journal_access"), ...)
 */
export function gateMiddleware(featureKey) {
  return (req, res, next) => {
    const roles = req.user?.wp?.roles || [];
    const tier = tierFromRoles(roles, req.user?.wp?.subscription_tier);
    const { allowed } = checkGate(tier, featureKey);

    if (!allowed) {
      return res.status(403).json({
        error: "feature_gated",
        feature: featureKey,
        tier,
        message: `This feature is not available for the ${tier} tier.`,
      });
    }

    next();
  };
}
