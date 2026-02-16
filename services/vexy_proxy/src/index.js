import http from 'node:http';
import httpProxy from 'http-proxy';
import jwt from 'jsonwebtoken';
import Redis from 'ioredis';

// --- Config from truth (loaded at startup) ---
let APP_SESSION_SECRET = null;

const VEXY_TARGET = process.env.VEXY_TARGET || 'http://localhost:3005';
const PORT = parseInt(process.env.VEXY_PROXY_PORT || '3006', 10);
const TRUTH_REDIS_URL = process.env.TRUTH_REDIS_URL || 'redis://127.0.0.1:6379';

// AOL v2.0 — Orchestrate endpoint config
const ORCHESTRATE_TIMEOUT_MS = 2000;  // Circuit breaker timeout

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

// --- Buffer request body ---
function bufferBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString()));
    req.on('error', reject);
  });
}

// --- Fetch with timeout (circuit breaker) ---
async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } finally {
    clearTimeout(timer);
  }
}

// --- Forward request with modified body ---
function proxyWithBody(req, res, body) {
  const proxyReq = http.request(
    {
      hostname: new URL(VEXY_TARGET).hostname,
      port: new URL(VEXY_TARGET).port,
      path: req.url,
      method: req.method,
      headers: {
        ...req.headers,
        'content-type': 'application/json',
        'content-length': Buffer.byteLength(body),
      },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );
  proxyReq.on('error', (err) => {
    console.error(`[vexy_proxy] Forward error: ${err.message}`);
    if (!res.headersSent) {
      jsonReply(res, 502, { error: 'Vexy unavailable' });
    }
  });
  proxyReq.write(body);
  proxyReq.end();
}

// --- Proxy ---
const proxy = httpProxy.createProxyServer({ target: VEXY_TARGET, xfwd: true });

proxy.on('error', (err, req, res) => {
  console.error(`[vexy_proxy] Proxy error: ${err.message}`);
  if (!res.headersSent) {
    jsonReply(res, 502, { error: 'Vexy unavailable' });
  }
});

// --- STRICT fallback classification (used when orchestrate fails) ---
const STRICT_FALLBACK = {
  doctrine_mode: 'strict',
  lpd_domain: 'unknown',
  lpd_confidence: 0,
  playbook_domain: '',
  allow_overlay: false,
  fallback: true,
};

// --- Server ---
const server = http.createServer(async (req, res) => {
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
  const userId = String(decoded.wp?.id || '');
  req.headers['x-user-id'] = userId;
  req.headers['x-user-email'] = String(decoded.wp?.email || '');

  // =====================================================================
  // AOL v2.0 — Two-Phase Orchestration
  // Only intercept POST /api/vexy/interaction
  // =====================================================================
  if (req.method === 'POST' && req.url.startsWith('/api/vexy/interaction') && !req.url.includes('/cancel')) {
    try {
      const t0 = Date.now();

      // Phase 1: Buffer body and call classification endpoint
      const body = await bufferBody(req);
      let parsed;
      try {
        parsed = JSON.parse(body);
      } catch (e) {
        return jsonReply(res, 400, { error: 'Invalid JSON' });
      }

      // Call orchestrate endpoint with circuit breaker
      let classification;
      try {
        const orchestrateRes = await fetchWithTimeout(
          `${VEXY_TARGET}/api/vexy/admin/orchestrate`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: parsed.message || '',
              user_id: parseInt(userId) || 0,
            }),
          },
          ORCHESTRATE_TIMEOUT_MS,
        );
        classification = await orchestrateRes.json();
      } catch (err) {
        // FALLBACK: orchestrate failed → default to STRICT mode
        // Interaction must NEVER proceed without doctrine routing
        console.warn(`[vexy_proxy] Orchestrate failed, falling back to STRICT: ${err.message}`);
        classification = { ...STRICT_FALLBACK };
      }

      // Phase 2: Merge doctrine metadata into request body
      parsed.doctrine_meta = {
        doctrine_mode: classification.doctrine_mode || 'strict',
        lpd_domain: classification.lpd_domain || 'unknown',
        lpd_confidence: classification.lpd_confidence || 0,
        playbook_domain: classification.playbook_domain || '',
        allow_overlay: classification.allow_overlay || false,
        fallback: classification.fallback || false,
      };

      // Include overlay data if present (M5)
      if (classification.overlay_data) {
        parsed.overlay_meta = classification.overlay_data;
      }

      const latency = Date.now() - t0;
      console.log(
        `[vexy_proxy] Orchestrate: ${classification.doctrine_mode} ` +
        `domain=${classification.lpd_domain} ` +
        `conf=${classification.lpd_confidence} ` +
        `${classification.fallback ? '(FALLBACK) ' : ''}` +
        `${latency}ms`
      );

      // Forward with enriched body
      proxyWithBody(req, res, JSON.stringify(parsed));
    } catch (err) {
      console.error(`[vexy_proxy] Orchestration error: ${err.message}`);
      // If everything fails, still try to forward the original request
      proxy.web(req, res);
    }
    return;
  }

  // All other routes: pass-through as before
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
    console.log(`[vexy_proxy] AOL v2.0 two-phase orchestration active`);
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
