# MarketSwarm Infrastructure & Network Architecture

Complete reference for the production deployment, networking, HTTP/2 configuration, and service topology. Use this document to understand how requests flow from browsers to backend services.

---

## 1. Network Topology

```
                                    INTERNET
                                        |
                                        v
                        +-------------------------------+
                        |     flyonthewall.io (DNS)     |
                        +-------------------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                           MiniThree (100.94.9.60)                                 |
|                                                                                   |
|   +-----------------------------------------------------------------------+       |
|   |                         NGINX (Homebrew)                              |       |
|   |   - TLS Termination (Let's Encrypt certs)                            |       |
|   |   - HTTP/2 enabled (multiplexing, no connection limits)              |       |
|   |   - Reverse proxy to backend services                                |       |
|   |   - Config: /opt/homebrew/etc/nginx/servers/marketswarm-https.conf   |       |
|   +-----------------------------------------------------------------------+       |
|                                        |                                          |
+-----------------------------------------------------------------------------------+
                                         |
                          Local Network (192.168.1.x)
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                           Mac (192.168.1.11)                                      |
|                                                                                   |
|   +-------------------+  +-------------------+  +-------------------+             |
|   | Static Frontend   |  | SSE Gateway       |  | Journal API       |             |
|   | Port 5173         |  | Port 3001         |  | Port 3002         |             |
|   | Node.js (pm2)     |  | Node.js (pm2)     |  | Python (pm2)      |             |
|   +-------------------+  +-------------------+  +-------------------+             |
|                                                                                   |
|   +-------------------+  +-------------------+  +-------------------+             |
|   | Copilot API       |  | System Redis      |  | Market Redis      |             |
|   | Port 8095         |  | Port 6379         |  | Port 6380         |             |
|   | Python (pm2)      |  | Redis             |  | Redis             |             |
|   +-------------------+  +-------------------+  +-------------------+             |
|                                                                                   |
|   +-------------------+                                                           |
|   | Intel Redis       |                                                           |
|   | Port 6381         |                                                           |
|   | Redis             |                                                           |
|   +-------------------+                                                           |
+-----------------------------------------------------------------------------------+
```

---

## 2. HTTP/2 Configuration

### Why HTTP/2?

HTTP/1.1 limits browsers to **6 concurrent connections per domain**. MarketSwarm uses multiple SSE (Server-Sent Events) streams that hold connections open:

| SSE Stream | Purpose |
|------------|---------|
| `/sse/all` | Main presence/unified stream |
| `/sse/market` | Market data (ticks, snapshots) |
| `/sse/intel` | Intel/news items |
| `/sse/alerts` | User alerts |
| `/sse/vexy` | Vexy AI responses |
| `/sse/risk-graph` | Risk graph updates |
| `/sse/trades` | Trade tracking |

With 7+ SSE connections, HTTP/1.1 exhausts all connection slots, causing API calls (trade log, journal, analytics) to queue indefinitely.

**HTTP/2 solves this** by multiplexing unlimited streams over a single TCP connection.

### Production Setup

**nginx on MiniThree** handles HTTP/2:

```nginx
# /opt/homebrew/etc/nginx/servers/marketswarm-https.conf
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;  # Enables HTTP/2 multiplexing
    server_name flyonthewall.io www.flyonthewall.io;

    ssl_certificate     /etc/letsencrypt/live/flyonthewall.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/flyonthewall.io/privkey.pem;
    # ... rest of config
}
```

**Backend services run plain HTTP** - nginx handles TLS termination:
- Browser connects to nginx via HTTPS/HTTP2
- nginx proxies to backends via HTTP/1.1 (keepalive enabled)

### Development Setup

For local development with HTTP/2, use mkcert certificates:

```bash
# Generate certs (already done in /Users/ernie/MarketSwarm/ui/)
cd ui
mkcert localhost 127.0.0.1 ::1

# Files created:
# - localhost+2.pem (certificate)
# - localhost+2-key.pem (private key)
```

Configure Vite for HTTPS (optional for dev):
```typescript
// vite.config.ts
import fs from 'fs';

export default defineConfig({
  server: {
    https: {
      key: fs.readFileSync('./localhost+2-key.pem'),
      cert: fs.readFileSync('./localhost+2.pem'),
    }
  }
});
```

---

## 3. Services & Ports

### Frontend Static Server (Port 5173)

**File:** `/Users/ernie/MarketSwarm/ui/serve-http2.js`

Production-grade Node.js static file server:
- Serves built React app from `dist/`
- SPA fallback (all routes serve index.html)
- Proper MIME types and caching headers
- Hashed assets cached forever, HTML revalidates

```javascript
// Key configuration
const PORT = process.env.PORT || 5173;
const DIST_DIR = path.join(__dirname, 'dist');

// Cache strategy
const cacheControl = isHtml
  ? 'no-cache, must-revalidate'      // HTML always checks for updates
  : 'public, max-age=31536000, immutable';  // Assets cached 1 year
```

**PM2 Process:** `fotw-static`
```bash
pm2 start serve-http2.js --name fotw-static
pm2 save
```

### SSE Gateway (Port 3001)

**Location:** `/Users/ernie/MarketSwarm/services/sse/`

Node.js service handling:
- Authentication (`/api/auth/*`)
- User profiles (`/api/profile/*`)
- Admin endpoints (`/api/admin/*`)
- Model data (`/api/models/*`)
- All SSE streams (`/sse/*`)

**PM2 Process:** `fotw-sse`

### Journal API (Port 3002)

**Location:** `/Users/ernie/MarketSwarm/services/journal/`

Python Flask service handling:
- Trade logs (`/api/logs`, `/api/trades`)
- Journal entries (`/api/journal/*`)
- Alerts (`/api/alerts`)
- Analytics (`/api/analytics`)
- Playbook (`/api/playbook/*`)
- Settings (`/api/settings`)

**PM2 Process:** `fotw-journal`

### Copilot API (Port 8095)

**Location:** `/Users/ernie/MarketSwarm/services/copilot/`

Python service handling:
- MEL (Model Effectiveness Layer) - `/api/mel/*`
- ADI (Analysis/Insights) - `/api/adi/*`
- Commentary generation - `/api/commentary/*`
- WebSocket streams - `/ws/mel`, `/ws/commentary`

**PM2 Process:** `fotw-copilot`

---

## 4. nginx Route Map

All routes proxied from nginx (MiniThree) to Mac (192.168.1.11):

### SSE Streams (Port 3001)
```nginx
location /sse/ {
    proxy_pass http://sse_gateway;
    proxy_buffering off;           # Critical for SSE
    proxy_read_timeout 86400s;     # 24 hours
}
```

### SSE Gateway REST (Port 3001)
```nginx
/api/models/*   -> sse_gateway
/api/auth/*     -> sse_gateway
/api/profile/*  -> sse_gateway
/api/admin/*    -> sse_gateway
/api/health     -> sse_gateway
```

### Journal API (Port 3002)
```nginx
/api/logs       -> journal_api
/api/trades     -> journal_api
/api/symbols    -> journal_api
/api/tags       -> journal_api
/api/journal/*  -> journal_api
/api/playbook/* -> journal_api
/api/alerts     -> journal_api
/api/leaderboard -> journal_api
/api/orders     -> journal_api
/api/prompt-alerts -> journal_api
/api/settings   -> journal_api
/api/analytics  -> journal_api
/api/internal/* -> journal_api
```

### Copilot API (Port 8095)
```nginx
/api/mel/*        -> copilot_api
/api/adi/*        -> copilot_api
/api/commentary/* -> copilot_api
/ws/mel           -> copilot_api (WebSocket)
/ws/commentary    -> copilot_api (WebSocket)
```

### Static Frontend (Port 5173)
```nginx
location / {
    proxy_pass http://static_frontend;
}
```

---

## 5. Redis Architecture

Three separate Redis instances for isolation:

| Redis | Port | Purpose |
|-------|------|---------|
| **System Redis** | 6379 | Control plane: heartbeats, service registry, logs, Truth document |
| **Market Redis** | 6380 | High-volume market data: ticks, snapshots, analysis results |
| **Intel Redis** | 6381 | Intel/news pipeline: RSS items, Vexy analysis |

### Truth System

Configuration loaded into System Redis:
```bash
# Load truth into Redis
./admin load-truth

# Keys created:
# truth:doc     - merged JSON config
# truth:version - version string
# truth:ts      - load timestamp
```

**Truth files:**
- `scripts/truth.json` - compiled from `truth/components/*.json`
- `scripts/truth_secrets.json` - API keys (never committed)

---

## 6. PM2 Process Management

All services managed by PM2 for auto-restart and logging.

```bash
# View all processes
pm2 status

# View logs
pm2 logs [process-name]

# Restart a service
pm2 restart [process-name]

# Save config for startup persistence
pm2 save

# Startup script (run once)
pm2 startup
```

### Current Processes

| Name | Script | Port |
|------|--------|------|
| `fotw-static` | `ui/serve-http2.js` | 5173 |
| `fotw-sse` | `services/sse/src/index.js` | 3001 |
| `fotw-journal` | `services/journal/app.py` | 3002 |
| `fotw-copilot` | `services/copilot/main.py` | 8095 |

---

## 7. SSL/TLS Certificates

### Production (Let's Encrypt)

Located on MiniThree:
```
/etc/letsencrypt/live/flyonthewall.io/fullchain.pem
/etc/letsencrypt/live/flyonthewall.io/privkey.pem
```

Auto-renewal via certbot.

### Development (mkcert)

Located in UI directory:
```
/Users/ernie/MarketSwarm/ui/localhost+2.pem
/Users/ernie/MarketSwarm/ui/localhost+2-key.pem
```

To trust locally:
```bash
mkcert -install  # Requires sudo, adds CA to system trust store
```

---

## 8. Troubleshooting

### 502 Bad Gateway

nginx can't reach backend. Check:
1. Backend service running? `pm2 status`
2. Correct port? Check nginx upstream config
3. Backend serving HTTP (not HTTPS)? Backends should be plain HTTP

### Slow Loading / Stuck on "Loading..."

Usually connection exhaustion (pre-HTTP/2). Verify:
```bash
# Check HTTP/2 is active
curl -sI --http2 https://flyonthewall.io | head -1
# Should show: HTTP/2 200
```

### SSE Not Connecting

Check nginx SSE config has:
```nginx
proxy_buffering off;
proxy_read_timeout 86400s;
```

### Service Won't Start

Check logs:
```bash
pm2 logs [service-name] --lines 50
```

---

## 9. Key File Locations

| Purpose | Path |
|---------|------|
| nginx config | `/opt/homebrew/etc/nginx/servers/marketswarm-https.conf` (MiniThree) |
| Static server | `/Users/ernie/MarketSwarm/ui/serve-http2.js` |
| SSE Gateway | `/Users/ernie/MarketSwarm/services/sse/` |
| Journal API | `/Users/ernie/MarketSwarm/services/journal/` |
| Copilot | `/Users/ernie/MarketSwarm/services/copilot/` |
| Truth config | `/Users/ernie/MarketSwarm/scripts/truth.json` |
| Truth components | `/Users/ernie/MarketSwarm/truth/components/*.json` |
| PM2 dump | `~/.pm2/dump.pm2` |
| Dev SSL certs | `/Users/ernie/MarketSwarm/ui/localhost+2*.pem` |

---

## 10. Quick Commands

```bash
# Reload nginx (on MiniThree)
sudo /opt/homebrew/opt/nginx/bin/nginx -s reload

# Restart all PM2 services
pm2 restart all

# Rebuild UI
cd /Users/ernie/MarketSwarm/ui && npm run build

# Check HTTP/2
curl -sI --http2 https://flyonthewall.io | grep -i http

# View nginx error log (on MiniThree)
tail -f /opt/homebrew/var/log/nginx/error.log

# SSH to MiniThree
ssh conor@100.94.9.60
```

---

*Last updated: February 2026*
*HTTP/2 enabled: February 6, 2026*
