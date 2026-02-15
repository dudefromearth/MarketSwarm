#!/usr/bin/env node
/**
 * MarketSwarm Dev/Production Server
 * - Serves static files from dist/ with SPA fallback
 * - Proxies API/SSE/WebSocket routes to backend services
 * - Matches production nginx routing (deploy/marketswarm-https.conf)
 * - Zero external dependencies (Node.js built-ins only)
 *
 * Route priority (matches nginx):
 *   /sse/*                    → SSE Gateway    (3001) — no buffering
 *   /ws/*                     → Copilot        (8095) — WebSocket upgrade
 *   /api/mel/*                → Copilot        (8095)
 *   /api/adi/*                → Copilot        (8095)
 *   /api/commentary/*         → Copilot        (8095)
 *   /api/vexy/interaction     → Vexy AI        (3005) — direct in dev
 *   /api/vexy/chat            → Vexy AI        (3005) — direct in dev
 *   /api/*                    → SSE Gateway    (3001) — catch-all
 *   /*                        → Static dist/   — SPA fallback
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import net from 'node:net';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─── Configuration ───────────────────────────────────────────
const PORT = process.env.PORT || 5174;
const DIST_DIR = path.join(__dirname, 'dist');

// Backend service targets (override with env vars if needed)
const SSE_GATEWAY   = process.env.SSE_GATEWAY   || 'localhost:3001';
const COPILOT       = process.env.COPILOT        || 'localhost:8095';
const VEXY_AI       = process.env.VEXY_AI        || 'localhost:3005';

// ─── Route Table ─────────────────────────────────────────────
// Order matters: first match wins (like nginx location blocks)
const PROXY_ROUTES = [
  // SSE streams — special handling (no buffering, long timeout)
  { prefix: '/sse/',                target: SSE_GATEWAY, sse: true },
  // WebSocket — handled via 'upgrade' event, but also proxy HTTP
  { prefix: '/ws/',                 target: COPILOT,     ws: true },
  // Copilot direct routes (bypass SSE Gateway)
  { prefix: '/api/mel/',            target: COPILOT },
  { prefix: '/api/adi/',            target: COPILOT },
  { prefix: '/api/commentary/',     target: COPILOT },
  // Vexy latency-sensitive paths (direct to Vexy in dev, bypasses gateway)
  { prefix: '/api/vexy/interaction', target: VEXY_AI },
  { prefix: '/api/vexy/chat',       target: VEXY_AI },
  // SSE Gateway catch-all for all other API routes
  { prefix: '/api/',                target: SSE_GATEWAY },
];

// ─── MIME Types ──────────────────────────────────────────────
const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
  '.ttf':  'font/ttf',
  '.eot':  'application/vnd.ms-fontobject',
  '.map':  'application/json',
  '.webp': 'image/webp',
  '.webm': 'video/webm',
  '.mp4':  'video/mp4',
  '.txt':  'text/plain; charset=utf-8',
  '.xml':  'application/xml',
  '.pdf':  'application/pdf',
};

// ─── Proxy Logic ─────────────────────────────────────────────

function matchRoute(urlPath) {
  for (const route of PROXY_ROUTES) {
    if (urlPath.startsWith(route.prefix)) return route;
    // Exact match for paths without trailing slash
    if (urlPath === route.prefix.replace(/\/$/, '')) return route;
  }
  return null;
}

function proxyRequest(req, res, route) {
  const [targetHost, targetPort] = route.target.split(':');
  const options = {
    hostname: targetHost,
    port: parseInt(targetPort),
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `${targetHost}:${targetPort}` },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    // For SSE, disable buffering
    if (route.sse) {
      res.writeHead(proxyRes.statusCode, {
        ...proxyRes.headers,
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
      });
      // Pipe directly with no buffering
      proxyRes.pipe(res, { end: true });
    } else {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    }
  });

  proxyReq.on('error', (err) => {
    const targetName = route.target;
    console.error(`[proxy] ${targetName} error: ${err.message} (${req.method} ${req.url})`);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: `Backend unavailable: ${targetName}` }));
    }
  });

  // Set timeout (longer for SSE)
  proxyReq.setTimeout(route.sse ? 86400000 : 120000, () => {
    proxyReq.destroy();
  });

  // Pipe request body to proxy
  req.pipe(proxyReq, { end: true });
}

function proxyWebSocket(req, socket, head, route) {
  const [targetHost, targetPort] = route.target.split(':');
  const proxySocket = net.connect(parseInt(targetPort), targetHost, () => {
    // Reconstruct the HTTP upgrade request
    const reqLine = `${req.method} ${req.url} HTTP/1.1\r\n`;
    const headers = Object.entries(req.headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\r\n');
    proxySocket.write(reqLine + headers + '\r\n\r\n');
    if (head.length > 0) proxySocket.write(head);
    // Bidirectional pipe
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });

  proxySocket.on('error', (err) => {
    console.error(`[ws-proxy] ${route.target} error: ${err.message}`);
    socket.end();
  });

  socket.on('error', (err) => {
    console.error(`[ws-proxy] Client socket error: ${err.message}`);
    proxySocket.end();
  });
}

// ─── Static File Serving ─────────────────────────────────────

function serveStatic(req, res) {
  const reqPath = (req.url || '/').split('?')[0];
  let urlPath = path.normalize(reqPath).replace(/^(\.\.[\/\\])+/, '');
  let filePath = path.join(DIST_DIR, urlPath);

  fs.stat(filePath, (err, stats) => {
    if (err || !stats) {
      // SPA fallback — serve index.html for unmatched paths
      const indexPath = path.join(DIST_DIR, 'index.html');
      fs.stat(indexPath, (err2, stats2) => {
        if (err2 || !stats2) {
          res.writeHead(404);
          res.end('Not Found');
          return;
        }
        sendFile(res, indexPath, stats2, '.html');
      });
      return;
    }

    if (stats.isDirectory()) {
      filePath = path.join(filePath, 'index.html');
      fs.stat(filePath, (err2, stats2) => {
        if (err2 || !stats2) {
          res.writeHead(404);
          res.end('Not Found');
          return;
        }
        sendFile(res, filePath, stats2, '.html');
      });
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    sendFile(res, filePath, stats, ext);
  });
}

function sendFile(res, filePath, stats, ext) {
  const mimeType = MIME_TYPES[ext] || 'application/octet-stream';
  const isHtml = ext === '.html';
  const cacheControl = isHtml
    ? 'no-cache, must-revalidate'
    : 'public, max-age=31536000, immutable';

  const headers = {
    'Content-Type': mimeType,
    'Content-Length': stats.size,
    'Cache-Control': cacheControl,
    'X-Content-Type-Options': 'nosniff',
  };

  if (isHtml) {
    headers['X-Frame-Options'] = 'SAMEORIGIN';
    headers['X-XSS-Protection'] = '1; mode=block';
  }

  res.writeHead(200, headers);
  const fileStream = fs.createReadStream(filePath);
  fileStream.pipe(res);
  fileStream.on('error', (err) => {
    console.error(`Error streaming ${filePath}:`, err.message);
    if (!res.writableEnded) res.end();
  });
}

// ─── Server Setup ────────────────────────────────────────────

// Check dist exists
if (!fs.existsSync(DIST_DIR)) {
  console.error('ERROR: dist/ directory not found!');
  console.error('Run: npx vite build');
  process.exit(1);
}

const server = http.createServer((req, res) => {
  const urlPath = (req.url || '/').split('?')[0];

  // Check proxy routes first
  const route = matchRoute(urlPath);
  if (route) {
    proxyRequest(req, res, route);
    return;
  }

  // Static files (only GET/HEAD)
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405);
    res.end('Method Not Allowed');
    return;
  }

  serveStatic(req, res);
});

// WebSocket upgrade handling
server.on('upgrade', (req, socket, head) => {
  const urlPath = (req.url || '/').split('?')[0];
  const route = matchRoute(urlPath);

  if (route) {
    proxyWebSocket(req, socket, head, route);
  } else {
    socket.end('HTTP/1.1 404 Not Found\r\n\r\n');
  }
});

server.on('error', (err) => {
  console.error('Server error:', err);
});

server.listen(PORT, () => {
  console.log('═══════════════════════════════════════════════════════');
  console.log(' MarketSwarm Dev Server (with proxy routing)');
  console.log('═══════════════════════════════════════════════════════');
  console.log(` Listening:  http://localhost:${PORT}`);
  console.log(` Static:     ${DIST_DIR}`);
  console.log('');
  console.log(' Proxy Routes:');
  console.log(`   /sse/*                    → ${SSE_GATEWAY}  (SSE streams)`);
  console.log(`   /ws/*                     → ${COPILOT}  (WebSocket)`);
  console.log(`   /api/mel/*                → ${COPILOT}  (Copilot)`);
  console.log(`   /api/adi/*                → ${COPILOT}  (Copilot)`);
  console.log(`   /api/commentary/*         → ${COPILOT}  (Copilot)`);
  console.log(`   /api/vexy/interaction     → ${VEXY_AI}  (Vexy direct)`);
  console.log(`   /api/vexy/chat            → ${VEXY_AI}  (Vexy direct)`);
  console.log(`   /api/*                    → ${SSE_GATEWAY}  (Gateway catch-all)`);
  console.log(`   /*                        → dist/  (SPA fallback)`);
  console.log('═══════════════════════════════════════════════════════');
});

// Graceful shutdown
function shutdown(signal) {
  console.log(`\nReceived ${signal}, shutting down...`);
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
