// services/sse/src/config.js
// Truth loader from Redis - loads SSE component configuration

import Redis from "ioredis";

const TRUTH_REDIS_URL = process.env.TRUTH_REDIS_URL || "redis://127.0.0.1:6379";
const TRUTH_KEY = process.env.TRUTH_REDIS_KEY || "truth";

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

    const config = {
      serviceName: "sse",
      meta: component.meta || {},
      heartbeat: component.heartbeat || { interval_sec: 5, ttl_sec: 15 },
      models: component.models || {},
      buses: truth.buses || {},
      env: {
        SSE_PORT: parseInt(process.env.SSE_PORT || component.env?.SSE_PORT || "3001", 10),
        SSE_POLL_INTERVAL_MS: parseInt(
          process.env.SSE_POLL_INTERVAL_MS || component.env?.SSE_POLL_INTERVAL_MS || "250",
          10
        ),
      },
    };

    console.log("[config] Truth loaded successfully");
    console.log(`[config] Port: ${config.env.SSE_PORT}, Poll interval: ${config.env.SSE_POLL_INTERVAL_MS}ms`);

    return config;
  } finally {
    await redis.quit();
  }
}

export function getFallbackConfig() {
  return {
    serviceName: "sse",
    meta: { name: "SSE UI Gateway" },
    heartbeat: { interval_sec: 5, ttl_sec: 15 },
    models: { produces: [], consumes: [] },
    buses: {
      "system-redis": { url: "redis://127.0.0.1:6379" },
      "market-redis": { url: "redis://127.0.0.1:6380" },
    },
    env: {
      SSE_PORT: parseInt(process.env.SSE_PORT || "3001", 10),
      SSE_POLL_INTERVAL_MS: parseInt(process.env.SSE_POLL_INTERVAL_MS || "250", 10),
    },
  };
}
