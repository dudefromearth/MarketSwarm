// services/sse/src/heartbeat.js
// Heartbeat publisher for SSE service

import { getSystemRedis } from "./redis.js";

let heartbeatInterval = null;

export function startHeartbeat(config, getStats) {
  const redis = getSystemRedis();
  const key = `${config.serviceName}:heartbeat`;
  const intervalMs = config.heartbeat.interval_sec * 1000;
  const ttl = config.heartbeat.ttl_sec;

  console.log(`[heartbeat] Starting (key=${key}, interval=${config.heartbeat.interval_sec}s, ttl=${ttl}s)`);

  const publish = async () => {
    try {
      const payload = {
        service: config.serviceName,
        ts: Date.now() / 1000,
        ...getStats(),
      };
      await redis.set(key, JSON.stringify(payload), "EX", ttl);
    } catch (err) {
      console.error("[heartbeat] publish failed:", err.message);
    }
  };

  // Initial heartbeat
  publish();

  // Schedule recurring heartbeats
  heartbeatInterval = setInterval(publish, intervalMs);

  return heartbeatInterval;
}

export function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    console.log("[heartbeat] Stopped");
  }
}
