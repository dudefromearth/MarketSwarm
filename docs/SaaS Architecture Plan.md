# MarketSwarm SaaS Architecture Plan

## Overview

Transform MarketSwarm from a single-user local application to a multi-tenant SaaS platform supporting:

- **Web App** (existing React frontend)
- **Desktop App** (Windows, macOS, Linux)
- **Mobile App** (iOS, Android)

With unified authentication across:
- WooCommerce storefront (existing purchase flow)
- In-app purchases via Stripe (desktop/mobile)

---

## Current vs Target Architecture

```
CURRENT STATE                          TARGET STATE
─────────────────                      ─────────────────
┌─────────────┐                        ┌─────────────────────────────────────┐
│  React UI   │                        │           CLIENTS                   │
│ (localhost) │                        │  ┌───────┐ ┌───────┐ ┌───────────┐  │
└──────┬──────┘                        │  │  Web  │ │Desktop│ │  Mobile   │  │
       │                               │  │ React │ │Electron│ │React Native│ │
       ▼                               │  └───┬───┘ └───┬───┘ └─────┬─────┘  │
┌─────────────┐                        └──────┼─────────┼───────────┼────────┘
│ Journal API │                               │         │           │
│  (SQLite)   │                               ▼         ▼           ▼
└─────────────┘                        ┌─────────────────────────────────────┐
                                       │          API GATEWAY                │
                                       │    (Auth, Rate Limit, Routing)      │
                                       └──────────────┬──────────────────────┘
                                                      │
                                       ┌──────────────┼──────────────┐
                                       ▼              ▼              ▼
                                 ┌──────────┐  ┌──────────┐  ┌──────────┐
                                 │   Auth   │  │ Journal  │  │  Market  │
                                 │ Service  │  │ Service  │  │  Data    │
                                 └────┬─────┘  └────┬─────┘  └────┬─────┘
                                      │             │             │
                                      ▼             ▼             ▼
                                 ┌─────────────────────────────────────┐
                                 │         PostgreSQL Database         │
                                 │  (Multi-tenant with user_id FK)     │
                                 └─────────────────────────────────────┘
```

---

## Phase 1: Authentication Service

### 1.1 Unified Auth Model

```
┌──────────────────────────────────────────────────────────────┐
│                     AUTH SERVICE                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐    ┌─────────────────┐                  │
│  │   WooCommerce   │    │     Stripe      │                  │
│  │   Webhook       │    │    Webhook      │                  │
│  │                 │    │                 │                  │
│  │ • Order created │    │ • subscription  │                  │
│  │ • Sub renewed   │    │   .created      │                  │
│  │ • Sub cancelled │    │ • invoice.paid  │                  │
│  └────────┬────────┘    └────────┬────────┘                  │
│           │                      │                           │
│           ▼                      ▼                           │
│  ┌───────────────────────────────────────────────┐           │
│  │           SUBSCRIPTION MANAGER                │           │
│  │                                               │           │
│  │  • Unified subscription status                │           │
│  │  • Plan features/limits                       │           │
│  │  • Grace periods                              │           │
│  │  • Trial management                           │           │
│  └───────────────────────────────────────────────┘           │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────┐           │
│  │              JWT TOKEN ISSUER                 │           │
│  │                                               │           │
│  │  Token payload:                               │           │
│  │  {                                            │           │
│  │    "sub": "user-uuid",                        │           │
│  │    "email": "user@example.com",               │           │
│  │    "plan": "pro",                             │           │
│  │    "features": ["journal", "heatmap", "ai"],  │           │
│  │    "exp": 1735689600                          │           │
│  │  }                                            │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Auth Database Schema

```sql
-- Users (created on first purchase)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    password_hash TEXT,  -- NULL if OAuth-only

    -- Profile
    display_name TEXT,
    avatar_url TEXT,
    timezone TEXT DEFAULT 'UTC',

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- Subscriptions (unified from WooCommerce + Stripe)
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),

    -- Source tracking
    source TEXT NOT NULL,  -- 'woocommerce' or 'stripe'
    external_id TEXT NOT NULL,  -- WC subscription ID or Stripe subscription ID

    -- Plan details
    plan TEXT NOT NULL,  -- 'basic', 'pro', 'enterprise'
    status TEXT NOT NULL,  -- 'active', 'past_due', 'cancelled', 'expired'

    -- Billing cycle
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(source, external_id)
);

-- API Keys (for programmatic access)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    key_hash TEXT NOT NULL,  -- SHA-256 of the key
    name TEXT NOT NULL,
    scopes TEXT[],  -- ['read:trades', 'write:trades']
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions (for web/app sessions)
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    token_hash TEXT NOT NULL,
    device_info JSONB,
    ip_address INET,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- OAuth connections (if adding social login later)
CREATE TABLE oauth_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    provider TEXT NOT NULL,  -- 'google', 'apple', 'github'
    provider_user_id TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(provider, provider_user_id)
);
```

### 1.3 Auth API Endpoints

```
POST   /auth/login              Email/password login
POST   /auth/logout             Invalidate session
POST   /auth/refresh            Refresh JWT token
POST   /auth/forgot-password    Send password reset email
POST   /auth/reset-password     Reset password with token

GET    /auth/me                 Get current user profile
PUT    /auth/me                 Update profile
GET    /auth/subscription       Get subscription status

POST   /auth/woocommerce/webhook   WooCommerce subscription events
POST   /auth/stripe/webhook        Stripe subscription events

GET    /auth/api-keys           List API keys
POST   /auth/api-keys           Create API key
DELETE /auth/api-keys/:id       Revoke API key
```

### 1.4 WooCommerce Integration

```python
# Webhook handler for WooCommerce subscription events
async def handle_woocommerce_webhook(request):
    event = await request.json()
    signature = request.headers.get('X-WC-Webhook-Signature')

    # Verify signature
    if not verify_wc_signature(signature, event, WC_SECRET):
        return web.Response(status=401)

    topic = request.headers.get('X-WC-Webhook-Topic')

    if topic == 'subscription.created':
        # Create/update user and subscription
        user = await get_or_create_user(event['billing']['email'])
        await create_subscription(
            user_id=user.id,
            source='woocommerce',
            external_id=str(event['id']),
            plan=map_wc_product_to_plan(event['line_items']),
            status='active',
            period_end=parse_date(event['next_payment_date'])
        )

    elif topic == 'subscription.updated':
        await update_subscription_status(
            source='woocommerce',
            external_id=str(event['id']),
            status=map_wc_status(event['status'])
        )

    elif topic == 'subscription.deleted':
        await cancel_subscription(
            source='woocommerce',
            external_id=str(event['id'])
        )

    return web.Response(status=200)
```

### 1.5 Stripe Integration

```python
# Webhook handler for Stripe subscription events
async def handle_stripe_webhook(request):
    payload = await request.read()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return web.Response(status=401)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user = await get_or_create_user(session['customer_email'])

        # Create subscription from checkout
        await create_subscription(
            user_id=user.id,
            source='stripe',
            external_id=session['subscription'],
            plan=get_plan_from_price(session['line_items']),
            status='active'
        )

    elif event['type'] == 'invoice.paid':
        # Subscription renewed
        sub = event['data']['object']
        await update_subscription_period(
            source='stripe',
            external_id=sub['subscription'],
            period_end=datetime.fromtimestamp(sub['period_end'])
        )

    elif event['type'] == 'customer.subscription.deleted':
        sub = event['data']['object']
        await cancel_subscription(
            source='stripe',
            external_id=sub['id']
        )

    return web.Response(status=200)
```

---

## Phase 2: Multi-Tenant Journal Service

### 2.1 Database Migration

Add `user_id` to all tables:

```sql
-- Add user_id to trade_logs
ALTER TABLE trade_logs ADD COLUMN user_id UUID REFERENCES users(id);
CREATE INDEX idx_trade_logs_user ON trade_logs(user_id);

-- Add user_id to trades (denormalized for query efficiency)
ALTER TABLE trades ADD COLUMN user_id UUID REFERENCES users(id);
CREATE INDEX idx_trades_user ON trades(user_id);

-- Add user_id to symbols (per-user custom symbols)
ALTER TABLE symbols ADD COLUMN user_id UUID REFERENCES users(id);
-- NULL user_id = system default, non-NULL = user custom

-- Add user_id to settings
ALTER TABLE settings ADD COLUMN user_id UUID REFERENCES users(id);
```

### 2.2 API Middleware

```python
async def auth_middleware(request, handler):
    """Extract and validate JWT, attach user to request."""

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return web.json_response({'error': 'Unauthorized'}, status=401)

    token = auth_header.split(' ')[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        request['user_id'] = payload['sub']
        request['user_plan'] = payload.get('plan', 'free')
        request['user_features'] = payload.get('features', [])
    except jwt.ExpiredSignatureError:
        return web.json_response({'error': 'Token expired'}, status=401)
    except jwt.InvalidTokenError:
        return web.json_response({'error': 'Invalid token'}, status=401)

    return await handler(request)
```

### 2.3 Tenant-Scoped Queries

```python
# Before (single-user)
def list_logs(self):
    cursor = self.conn.execute("SELECT * FROM trade_logs WHERE is_active = 1")
    return cursor.fetchall()

# After (multi-tenant)
def list_logs(self, user_id: str):
    cursor = self.conn.execute(
        "SELECT * FROM trade_logs WHERE user_id = ? AND is_active = 1",
        (user_id,)
    )
    return cursor.fetchall()
```

### 2.4 Plan-Based Feature Limits

```python
PLAN_LIMITS = {
    'free': {
        'max_logs': 1,
        'max_trades_per_log': 100,
        'features': ['journal'],
        'export_formats': ['csv'],
    },
    'basic': {
        'max_logs': 3,
        'max_trades_per_log': 1000,
        'features': ['journal', 'heatmap'],
        'export_formats': ['csv', 'xlsx'],
    },
    'pro': {
        'max_logs': 10,
        'max_trades_per_log': None,  # Unlimited
        'features': ['journal', 'heatmap', 'ai_commentary', 'playbooks'],
        'export_formats': ['csv', 'xlsx', 'json'],
    },
    'enterprise': {
        'max_logs': None,
        'max_trades_per_log': None,
        'features': ['*'],
        'export_formats': ['*'],
        'api_access': True,
    }
}

def check_feature(user_plan: str, feature: str) -> bool:
    limits = PLAN_LIMITS.get(user_plan, PLAN_LIMITS['free'])
    features = limits.get('features', [])
    return '*' in features or feature in features

def check_limit(user_plan: str, resource: str, current_count: int) -> bool:
    limits = PLAN_LIMITS.get(user_plan, PLAN_LIMITS['free'])
    max_allowed = limits.get(resource)
    return max_allowed is None or current_count < max_allowed
```

---

## Phase 3: API Gateway

### 3.1 Gateway Architecture

```
                    ┌─────────────────────────────────────┐
                    │           API GATEWAY               │
                    │         (api.marketswarm.io)        │
                    ├─────────────────────────────────────┤
                    │                                     │
                    │  ┌───────────────────────────────┐  │
                    │  │       Rate Limiting           │  │
                    │  │  • 100 req/min (free)         │  │
                    │  │  • 1000 req/min (pro)         │  │
                    │  │  • 10000 req/min (enterprise) │  │
                    │  └───────────────────────────────┘  │
                    │                                     │
                    │  ┌───────────────────────────────┐  │
                    │  │       Authentication          │  │
                    │  │  • JWT validation             │  │
                    │  │  • API key validation         │  │
                    │  │  • Subscription check         │  │
                    │  └───────────────────────────────┘  │
                    │                                     │
                    │  ┌───────────────────────────────┐  │
                    │  │         Routing               │  │
                    │  │  /api/v1/auth/* → Auth Svc    │  │
                    │  │  /api/v1/journal/* → Journal  │  │
                    │  │  /api/v1/market/* → Market    │  │
                    │  └───────────────────────────────┘  │
                    │                                     │
                    └─────────────────────────────────────┘
```

### 3.2 API Versioning

```
/api/v1/logs          Current version
/api/v2/logs          Future version (when breaking changes needed)
```

### 3.3 CORS Configuration

```python
CORS_CONFIG = {
    'allow_origins': [
        'https://app.marketswarm.io',      # Web app
        'https://marketswarm.io',          # Marketing site
        'capacitor://localhost',           # iOS app
        'http://localhost',                # Android app
        'tauri://localhost',               # Desktop app
    ],
    'allow_methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    'allow_headers': ['Authorization', 'Content-Type', 'X-API-Key'],
    'allow_credentials': True,
    'max_age': 86400,
}
```

---

## Phase 4: Client Applications

### 4.1 Web App (Existing React)

**Changes needed:**
- Add authentication flow (login/logout)
- Store JWT in secure cookie or localStorage
- Add token refresh logic
- Update API calls to include Authorization header

```typescript
// api/client.ts
const API_BASE = import.meta.env.VITE_API_URL || 'https://api.marketswarm.io';

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('jwt', token);
  }

  async fetch(path: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers);

    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Token expired, try refresh
      const refreshed = await this.refreshToken();
      if (refreshed) {
        return this.fetch(path, options);
      }
      // Redirect to login
      window.location.href = '/login';
    }

    return response;
  }

  async refreshToken(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (response.ok) {
        const { token } = await response.json();
        this.setToken(token);
        return true;
      }
    } catch {}
    return false;
  }
}

export const api = new ApiClient();
```

### 4.2 Desktop App (Tauri)

**Why Tauri over Electron:**
- Smaller binary size (~10MB vs ~150MB)
- Better performance (native webview)
- Rust backend for secure operations
- Lower memory usage

**Structure:**
```
desktop/
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── src/
│       ├── main.rs
│       └── commands.rs      # Rust commands for native features
├── src/                     # Shared React code (symlink or copy)
├── package.json
└── vite.config.ts
```

**Native features via Tauri:**
- Secure token storage (OS keychain)
- System tray integration
- Auto-updater
- Deep linking (marketswarm://open-trade/123)
- Native notifications

```rust
// src-tauri/src/commands.rs
use tauri::Manager;
use keyring::Entry;

#[tauri::command]
async fn store_token(token: String) -> Result<(), String> {
    let entry = Entry::new("marketswarm", "jwt_token")
        .map_err(|e| e.to_string())?;
    entry.set_password(&token)
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
async fn get_token() -> Result<Option<String>, String> {
    let entry = Entry::new("marketswarm", "jwt_token")
        .map_err(|e| e.to_string())?;
    match entry.get_password() {
        Ok(token) => Ok(Some(token)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}
```

### 4.3 Mobile App (React Native)

**Why React Native:**
- Shares React knowledge from web
- Single codebase for iOS + Android
- Good performance for this type of app
- Expo for easier development

**Structure:**
```
mobile/
├── app/                     # Expo Router pages
│   ├── (tabs)/
│   │   ├── index.tsx        # Dashboard
│   │   ├── trades.tsx       # Trade log
│   │   └── settings.tsx     # Settings
│   ├── login.tsx
│   └── _layout.tsx
├── components/              # Shared with web where possible
├── hooks/
├── api/
├── app.json
└── package.json
```

**Platform-specific considerations:**
- Secure storage: `expo-secure-store`
- In-app purchases: `expo-in-app-purchases` or `react-native-iap`
- Push notifications: `expo-notifications`
- Biometric auth: `expo-local-authentication`

```typescript
// api/auth.ts (React Native)
import * as SecureStore from 'expo-secure-store';

export async function storeToken(token: string) {
  await SecureStore.setItemAsync('jwt', token);
}

export async function getToken(): Promise<string | null> {
  return await SecureStore.getItemAsync('jwt');
}
```

---

## Phase 5: In-App Purchases

### 5.1 Purchase Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     PURCHASE FLOWS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WEB (WooCommerce)                                              │
│  ─────────────────                                              │
│  1. User clicks "Subscribe" on marketswarm.io                   │
│  2. WooCommerce checkout                                        │
│  3. Payment processed                                           │
│  4. Webhook → Auth Service creates subscription                 │
│  5. Redirect to app.marketswarm.io with token                   │
│                                                                 │
│  DESKTOP (Stripe Checkout)                                      │
│  ─────────────────────────                                      │
│  1. User clicks "Upgrade" in app                                │
│  2. Open Stripe Checkout in browser                             │
│  3. Payment processed                                           │
│  4. Webhook → Auth Service creates subscription                 │
│  5. Deep link back to app (marketswarm://subscription-success)  │
│                                                                 │
│  iOS (App Store)                                                │
│  ──────────────                                                 │
│  1. User taps "Subscribe" in app                                │
│  2. StoreKit purchase flow                                      │
│  3. Apple processes payment                                     │
│  4. App receives receipt                                        │
│  5. Send receipt to Auth Service for validation                 │
│  6. Auth Service validates with Apple, creates subscription     │
│                                                                 │
│  ANDROID (Google Play)                                          │
│  ────────────────────                                           │
│  1. User taps "Subscribe" in app                                │
│  2. Google Play purchase flow                                   │
│  3. Google processes payment                                    │
│  4. App receives purchase token                                 │
│  5. Send token to Auth Service for validation                   │
│  6. Auth Service validates with Google, creates subscription    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Receipt Validation

```python
# Auth service endpoints for mobile receipt validation

async def validate_apple_receipt(request):
    """Validate iOS App Store receipt."""
    body = await request.json()
    receipt_data = body['receipt_data']
    user_id = request['user_id']

    # Validate with Apple
    response = await httpx.post(
        'https://buy.itunes.apple.com/verifyReceipt',
        json={
            'receipt-data': receipt_data,
            'password': APPLE_SHARED_SECRET,
        }
    )

    result = response.json()
    if result['status'] != 0:
        return web.json_response({'error': 'Invalid receipt'}, status=400)

    # Extract subscription info
    latest_receipt = result['latest_receipt_info'][0]

    await create_subscription(
        user_id=user_id,
        source='apple',
        external_id=latest_receipt['original_transaction_id'],
        plan=map_apple_product_to_plan(latest_receipt['product_id']),
        status='active',
        period_end=datetime.fromtimestamp(
            int(latest_receipt['expires_date_ms']) / 1000
        )
    )

    return web.json_response({'success': True})


async def validate_google_purchase(request):
    """Validate Android Google Play purchase."""
    body = await request.json()
    purchase_token = body['purchase_token']
    product_id = body['product_id']
    user_id = request['user_id']

    # Validate with Google
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE
    )
    service = build('androidpublisher', 'v3', credentials=credentials)

    result = service.purchases().subscriptions().get(
        packageName=ANDROID_PACKAGE_NAME,
        subscriptionId=product_id,
        token=purchase_token
    ).execute()

    if result['paymentState'] != 1:  # 1 = received
        return web.json_response({'error': 'Invalid purchase'}, status=400)

    await create_subscription(
        user_id=user_id,
        source='google',
        external_id=result['orderId'],
        plan=map_google_product_to_plan(product_id),
        status='active',
        period_end=datetime.fromtimestamp(
            int(result['expiryTimeMillis']) / 1000
        )
    )

    return web.json_response({'success': True})
```

---

## Phase 6: Infrastructure

### 6.1 Cloud Architecture (AWS Example)

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS INFRASTRUCTURE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────────────────────────────┐    │
│  │  CloudFront │────▶│  S3 (Static Web App)                │    │
│  │    (CDN)    │     │  app.marketswarm.io                 │    │
│  └─────────────┘     └─────────────────────────────────────┘    │
│                                                                 │
│  ┌─────────────┐     ┌─────────────────────────────────────┐    │
│  │   Route 53  │────▶│  Application Load Balancer          │    │
│  │    (DNS)    │     │  api.marketswarm.io                 │    │
│  └─────────────┘     └──────────────┬──────────────────────┘    │
│                                     │                           │
│                      ┌──────────────┼──────────────┐            │
│                      ▼              ▼              ▼            │
│               ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│               │   ECS    │  │   ECS    │  │   ECS    │          │
│               │  (Auth)  │  │(Journal) │  │ (Market) │          │
│               └────┬─────┘  └────┬─────┘  └────┬─────┘          │
│                    │             │             │                │
│                    ▼             ▼             ▼                │
│               ┌─────────────────────────────────────┐           │
│               │         RDS PostgreSQL              │           │
│               │      (Multi-AZ, encrypted)          │           │
│               └─────────────────────────────────────┘           │
│                                                                 │
│               ┌─────────────────────────────────────┐           │
│               │         ElastiCache Redis           │           │
│               │    (Sessions, rate limiting)        │           │
│               └─────────────────────────────────────┘           │
│                                                                 │
│               ┌─────────────────────────────────────┐           │
│               │              SES                    │           │
│               │    (Transactional emails)           │           │
│               └─────────────────────────────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Docker Containers

```dockerfile
# services/auth/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.3 Environment Configuration

```bash
# .env.production
DATABASE_URL=postgresql://user:pass@rds-host:5432/marketswarm
REDIS_URL=redis://elasticache-host:6379

JWT_SECRET=your-256-bit-secret
JWT_EXPIRY=3600

STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

WC_CONSUMER_KEY=ck_...
WC_CONSUMER_SECRET=cs_...
WC_WEBHOOK_SECRET=...

APPLE_SHARED_SECRET=...
GOOGLE_SERVICE_ACCOUNT_FILE=/secrets/google-sa.json

CORS_ORIGINS=https://app.marketswarm.io,capacitor://localhost
```

---

## Implementation Timeline

| Phase | Description | Estimated Effort |
|-------|-------------|------------------|
| **Phase 1** | Auth Service + WooCommerce/Stripe integration | 2-3 weeks |
| **Phase 2** | Multi-tenant Journal Service | 1-2 weeks |
| **Phase 3** | API Gateway + Rate Limiting | 1 week |
| **Phase 4a** | Web App auth integration | 1 week |
| **Phase 4b** | Desktop App (Tauri) | 2-3 weeks |
| **Phase 4c** | Mobile App (React Native) | 3-4 weeks |
| **Phase 5** | In-App Purchases (iOS + Android) | 2 weeks |
| **Phase 6** | Cloud Infrastructure + Deployment | 1-2 weeks |

**Total: 13-18 weeks** for full SaaS platform

---

## Security Considerations

1. **Data Encryption**
   - TLS 1.3 for all API traffic
   - AES-256 encryption at rest (database, backups)
   - JWT tokens signed with RS256 (asymmetric)

2. **Authentication**
   - Bcrypt for password hashing (cost factor 12)
   - Rate limiting on auth endpoints (5 attempts/minute)
   - Session invalidation on password change

3. **API Security**
   - CORS properly configured
   - CSRF protection for cookie-based auth
   - Input validation on all endpoints
   - SQL injection prevention (parameterized queries)

4. **Compliance**
   - GDPR: Data export, deletion endpoints
   - PCI DSS: No card data stored (Stripe handles)
   - SOC 2: Audit logging, access controls

---

## Next Steps

1. **Decision**: Confirm architecture approach
2. **Setup**: Create new repo structure for SaaS services
3. **Phase 1**: Build Auth Service with WooCommerce webhook
4. **Test**: Integration testing with existing WooCommerce store
5. **Iterate**: Add Stripe, then clients
