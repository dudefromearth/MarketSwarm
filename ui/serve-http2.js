#!/usr/bin/env node
/**
 * Production Static File Server
 * - Plain HTTP for nginx reverse proxy (nginx handles HTTP/2 + TLS to browsers)
 * - Serves static files from dist/
 * - SPA fallback to index.html
 * - Proper MIME types and caching
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configuration
const PORT = process.env.PORT || 5173;
const DIST_DIR = path.join(__dirname, 'dist');

// MIME types
const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
  '.map': 'application/json',
  '.webp': 'image/webp',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml',
  '.pdf': 'application/pdf',
};

// Check dist directory exists
if (!fs.existsSync(DIST_DIR)) {
  console.error('ERROR: dist/ directory not found!');
  console.error('Run: npm run build');
  process.exit(1);
}

// Create HTTP server
const server = http.createServer((req, res) => {
  const method = req.method;
  const reqPath = req.url || '/';

  // Only handle GET/HEAD
  if (method !== 'GET' && method !== 'HEAD') {
    res.writeHead(405);
    res.end('Method Not Allowed');
    return;
  }

  // Parse path (remove query string)
  let urlPath = reqPath.split('?')[0];

  // Security: prevent directory traversal
  urlPath = path.normalize(urlPath).replace(/^(\.\.[\/\\])+/, '');

  // Map to file path
  let filePath = path.join(DIST_DIR, urlPath);

  // Try to serve the file
  serveFile(res, filePath, urlPath);
});

function serveFile(res, filePath, urlPath) {
  fs.stat(filePath, (err, stats) => {
    if (err || !stats) {
      // File not found - SPA fallback to index.html
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

    // If directory, try index.html
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

    // Serve the file
    const ext = path.extname(filePath).toLowerCase();
    sendFile(res, filePath, stats, ext);
  });
}

function sendFile(res, filePath, stats, ext) {
  const mimeType = MIME_TYPES[ext] || 'application/octet-stream';

  // Cache headers (assets are hashed, so cache forever; html should revalidate)
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

  // Add security headers for HTML
  if (isHtml) {
    headers['X-Frame-Options'] = 'SAMEORIGIN';
    headers['X-XSS-Protection'] = '1; mode=block';
  }

  res.writeHead(200, headers);

  // Stream the file
  const fileStream = fs.createReadStream(filePath);
  fileStream.pipe(res);

  fileStream.on('error', (err) => {
    console.error(`Error streaming ${filePath}:`, err.message);
    if (!res.writableEnded) {
      res.end();
    }
  });
}

// Error handling
server.on('error', (err) => {
  console.error('Server error:', err);
});

// Start server
server.listen(PORT, () => {
  console.log(`Static Server running on http://localhost:${PORT}`);
  console.log(`Serving files from: ${DIST_DIR}`);
  console.log('Press Ctrl+C to stop');
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('Received SIGTERM, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('\nReceived SIGINT, shutting down gracefully...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});
