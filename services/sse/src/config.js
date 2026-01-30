// services/sse/src/config.js
// Truth loader from Redis - loads SSE component configuration

import Redis from "ioredis";

const TRUTH_REDIS_URL = process.env.TRUTH_REDIS_URL || "redis://127.0.0.1:6379";
const TRUTH_KEY = process.env.TRUTH_REDIS_KEY || "truth";

// Global config reference for modules that need it
let _config = null;

export async function loadConfig() {
  const redis = new Redis(TRUTH_REDIS_URL);

  try {
    const raw = await redis.get(TRUTH_KEY);
    if (!raw) {
      throw new Error(`Truth key '${TRUTH_KEY}' not found or empty`);
    }

    const truth = JSON.parse(raw);
    const component = truth.components?.sse;

    if (!component) {
      throw new Error("SSE component not found in Truth");
    }

    const componentEnv = component.env || {};

    const config = {
      serviceName: "sse",
      meta: component.meta || {},
      heartbeat: component.heartbeat || { interval_sec: 5, ttl_sec: 15 },
      models: component.models || {},
      buses: truth.buses || {},
      env: {
        // Server
        SSE_PORT: parseInt(componentEnv.SSE_PORT || "3001", 10),
        SSE_POLL_INTERVAL_MS: parseInt(componentEnv.SSE_POLL_INTERVAL_MS || "250", 10),

        // Database
        DATABASE_URL: componentEnv.DATABASE_URL || "",

        // Auth - SSO secrets
        SSO_0DTE_SECRET: componentEnv.SSO_0DTE_SECRET || "",
        SSO_FOTW_SECRET: componentEnv.SSO_FOTW_SECRET || "",

        // Auth - App session
        APP_SESSION_SECRET: componentEnv.APP_SESSION_SECRET || "change-me",
        APP_SESSION_TTL_SECONDS: parseInt(componentEnv.APP_SESSION_TTL_SECONDS || "86400", 10),

        // Auth - Public mode (bypasses auth)
        PUBLIC_MODE: componentEnv.PUBLIC_MODE === "1",
      },
    };

    // Store globally for getConfig()
    _config = config;

    console.log("[config] Truth loaded successfully");
    console.log(`[config] Port: ${config.env.SSE_PORT}, Poll interval: ${config.env.SSE_POLL_INTERVAL_MS}ms`);
    console.log(`[config] Database: ${config.env.DATABASE_URL ? "configured" : "not configured"}`);
    console.log(`[config] Auth: SSO_0DTE=${config.env.SSO_0DTE_SECRET ? "set" : "not set"}, SSO_FOTW=${config.env.SSO_FOTW_SECRET ? "set" : "not set"}`);

    return config;
  } finally {
    await redis.quit();
  }
}

export function getFallbackConfig() {
  const config = {
    serviceName: "sse",
    meta: { name: "SSE UI Gateway" },
    heartbeat: { interval_sec: 5, ttl_sec: 15 },
    models: { produces: [], consumes: [] },
    buses: {
      "system-redis": { url: "redis://127.0.0.1:6379" },
      "market-redis": { url: "redis://127.0.0.1:6380" },
    },
    env: {
      SSE_PORT: 3001,
      SSE_POLL_INTERVAL_MS: 250,
      DATABASE_URL: "",
      SSO_0DTE_SECRET: "",
      SSO_FOTW_SECRET: "",
      APP_SESSION_SECRET: "change-me",
      APP_SESSION_TTL_SECONDS: 86400,
      PUBLIC_MODE: false,
    },
  };

  _config = config;
  return config;
}

/**
 * Get the loaded config (must call loadConfig() or getFallbackConfig() first)
 */
export function getConfig() {
  return _config;
}
