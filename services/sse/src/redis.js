// services/sse/src/redis.js
// Redis connections for market-redis, system-redis, and intel-redis

import Redis from "ioredis";

let systemRedis = null;
let marketRedis = null;
let marketRedisSub = null;
let intelRedis = null;

export function initRedis(config) {
  const systemUrl = config.buses["system-redis"]?.url || "redis://127.0.0.1:6379";
  const marketUrl = config.buses["market-redis"]?.url || "redis://127.0.0.1:6380";

  console.log(`[redis] Connecting to system-redis: ${systemUrl}`);
  console.log(`[redis] Connecting to market-redis: ${marketUrl}`);

  systemRedis = new Redis(systemUrl, {
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });

  marketRedis = new Redis(marketUrl, {
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });

  // Separate connection for pub/sub (ioredis requires dedicated connection)
  marketRedisSub = new Redis(marketUrl, {
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });

  const intelUrl = config.buses["intel-redis"]?.url || "redis://127.0.0.1:6381";
  console.log(`[redis] Connecting to intel-redis: ${intelUrl}`);

  intelRedis = new Redis(intelUrl, {
    retryStrategy: (times) => Math.min(times * 100, 3000),
    maxRetriesPerRequest: 3,
  });

  systemRedis.on("connect", () => console.log("[redis] system-redis connected"));
  systemRedis.on("error", (err) => console.error("[redis] system-redis error:", err.message));

  marketRedis.on("connect", () => console.log("[redis] market-redis connected"));
  marketRedis.on("error", (err) => console.error("[redis] market-redis error:", err.message));

  marketRedisSub.on("connect", () => console.log("[redis] market-redis (sub) connected"));
  marketRedisSub.on("error", (err) => console.error("[redis] market-redis (sub) error:", err.message));

  intelRedis.on("connect", () => console.log("[redis] intel-redis connected"));
  intelRedis.on("error", (err) => console.error("[redis] intel-redis error:", err.message));

  return { systemRedis, marketRedis, marketRedisSub, intelRedis };
}

export function getSystemRedis() {
  return systemRedis;
}

export function getMarketRedis() {
  return marketRedis;
}

export function getMarketRedisSub() {
  return marketRedisSub;
}

export function getIntelRedis() {
  return intelRedis;
}

export async function closeRedis() {
  const promises = [];
  if (systemRedis) promises.push(systemRedis.quit());
  if (marketRedis) promises.push(marketRedis.quit());
  if (marketRedisSub) promises.push(marketRedisSub.quit());
  if (intelRedis) promises.push(intelRedis.quit());
  await Promise.all(promises);
  console.log("[redis] All connections closed");
}
