import http from 'node:http';
import httpProxy from 'http-proxy';
import jwt from 'jsonwebtoken';
import Redis from 'ioredis';

// --- Config from truth (loaded at startup) ---
let APP_SESSION_SECRET = null;

const VEXY_TARGET = process.env.VEXY_TARGET || 'http://localhost:3005';
const PORT = parseInt(process.env.VEXY_PROXY_PORT || '3006', 10);
const TRUTH_REDIS_URL = process.env.TRUTH_REDIS_URL || 'redis://127.0.0.1:6379';

// --- Load secret from truth in Redis ---
async function loadSecret() {
  const redis = new Redis(TRUTH_REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 2 });
  try {
    await redis.connect();
    const raw = await redis.get('truth');
    if (!raw) throw new Error('No truth key in Redis');
    const truth = JSON.parse(raw);
    const secret = truth?.components?.sse?.env?.APP_SESSION_SECRET;
    if (!secret) throw new Error('APP_SESSION_SECRET not found in truth');
    APP_SESSION_SECRET = secret;
    console.log('[vexy_proxy] Secret loaded from truth');
  } finally {
    redis.disconnect();
  }
}

// --- Cookie parser (no deps) ---
function parseCookies(cookieHeader) {
  const cookies = {};
  if (!cookieHeader) return cookies;
  for (const pair of cookieHeader.split('; ')) {
    const idx = pair.indexOf('=');
    if (idx < 1) continue;
    cookies[pair.slice(0, idx).trim()] = pair.slice(idx + 1).trim();
  }
  return cookies;
}

// --- JSON response helper ---
function jsonReply(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

// --- Proxy ---
const proxy = httpProxy.createProxyServer({ target: VEXY_TARGET, xfwd: true });

proxy.on('error', (err, req, res) => {
  console.error(`[vexy_proxy] Proxy error: ${err.message}`);
  if (!res.headersSent) {
    jsonReply(res, 502, { error: 'Vexy unavailable' });
  }
});

// --- Server ---
const server = http.createServer((req, res) => {
  // Health check
  if (req.url === '/health' && req.method === 'GET') {
    return jsonReply(res, 200, { status: 'ok' });
  }

  // Auth: extract ms_session cookie
  const cookies = parseCookies(req.headers.cookie);
  const token = cookies.ms_session;

  if (!token) {
    return jsonReply(res, 401, { error: 'No session' });
  }

  // Verify JWT
  let decoded;
  try {
    decoded = jwt.verify(token, APP_SESSION_SECRET, { algorithms: ['HS256'] });
  } catch (err) {
    return jsonReply(res, 401, { error: 'Invalid session' });
  }

  // Set user headers for Vexy
  req.headers['x-user-id'] = String(decoded.wp?.id || '');
  req.headers['x-user-email'] = String(decoded.wp?.email || '');

  // Forward to Vexy
  proxy.web(req, res);
});

// --- Heartbeat ---
let heartbeatInterval = null;

async function startHeartbeat() {
  const redis = new Redis(TRUTH_REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 1 });
  try {
    await redis.connect();
  } catch (err) {
    console.error('[vexy_proxy] Heartbeat Redis connect failed:', err.message);
    return;
  }

  heartbeatInterval = setInterval(async () => {
    try {
      await redis.set('vexy_proxy:heartbeat', JSON.stringify({
        status: 'alive',
        ts: Date.now(),
        port: PORT
      }), 'EX', 30);
    } catch (err) {
      console.error('[vexy_proxy] Heartbeat write failed:', err.message);
    }
  }, 10_000);

  // Also keep secret fresh (handles rotation without restart)
  setInterval(async () => {
    try {
      const raw = await redis.get('truth');
      if (raw) {
        const truth = JSON.parse(raw);
        const secret = truth?.components?.sse?.env?.APP_SESSION_SECRET;
        if (secret) APP_SESSION_SECRET = secret;
      }
    } catch (err) {
      console.error('[vexy_proxy] Secret refresh failed:', err.message);
    }
  }, 5 * 60_000);

  // Store redis ref for shutdown
  server._heartbeatRedis = redis;
}

// --- Startup ---
async function main() {
  await loadSecret();

  server.listen(PORT, () => {
    console.log(`[vexy_proxy] Listening on :${PORT} → ${VEXY_TARGET}`);
  });

  await startHeartbeat();
}

// --- Graceful shutdown ---
function shutdown(signal) {
  console.log(`[vexy_proxy] ${signal} received, shutting down`);
  if (heartbeatInterval) clearInterval(heartbeatInterval);
  if (server._heartbeatRedis) server._heartbeatRedis.disconnect();
  server.close(() => {
    console.log('[vexy_proxy] Server closed');
    process.exit(0);
  });
  // Force exit after 5s
  setTimeout(() => process.exit(1), 5000);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

main().catch((err) => {
  console.error('[vexy_proxy] Fatal:', err.message);
  process.exit(1);
});
