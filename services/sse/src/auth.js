// services/sse/src/auth.js
// WordPress SSO authentication layer for MarketSwarm

import jwt from "jsonwebtoken";
import crypto from "crypto";
import { getConfig } from "./config.js";

// Cookie name for app session
const SESSION_COOKIE = "ms_session";

/**
 * Get auth config from truth (via getConfig)
 */
function getAuthConfig() {
  const config = getConfig();
  if (!config) {
    // Fallback if config not loaded yet
    return {
      SSO_0DTE_SECRET: "",
      SSO_FOTW_SECRET: "",
      APP_SESSION_SECRET: "change-me",
      APP_SESSION_TTL_SECONDS: 86400,
      PUBLIC_MODE: false,
    };
  }
  return config.env;
}

/**
 * Safe fingerprint for debugging (first 10 chars of sha256)
 */
function fingerprint(secret) {
  if (!secret) return "—";
  return crypto.createHash("sha256").update(secret).digest("hex").slice(0, 10);
}

/**
 * Log auth config on startup (without exposing secrets)
 */
export function logAuthConfig() {
  const env = getAuthConfig();
  console.log("[auth] Configuration:");
  console.log(`  SSO_0DTE_SECRET: ${env.SSO_0DTE_SECRET ? `set (fp: ${fingerprint(env.SSO_0DTE_SECRET)})` : "NOT SET"}`);
  console.log(`  SSO_FOTW_SECRET: ${env.SSO_FOTW_SECRET ? `set (fp: ${fingerprint(env.SSO_FOTW_SECRET)})` : "NOT SET"}`);
  console.log(`  APP_SESSION_SECRET: ${env.APP_SESSION_SECRET !== "change-me" ? `set (fp: ${fingerprint(env.APP_SESSION_SECRET)})` : "NOT SET (using default)"}`);
  console.log(`  APP_SESSION_TTL_SECONDS: ${env.APP_SESSION_TTL_SECONDS}`);
  console.log(`  PUBLIC_MODE: ${env.PUBLIC_MODE}`);
}

/**
 * Verify WordPress SSO JWT token
 * Returns decoded payload if valid, throws error otherwise
 */
export function verifyWpSsoToken(token) {
  const env = getAuthConfig();

  if (!token) {
    throw new Error("No token provided");
  }

  token = token.trim();
  const now = Math.floor(Date.now() / 1000);

  // 1) Parse token without verifying to inspect claims
  let unverified;
  try {
    unverified = jwt.decode(token, { complete: false });
  } catch (e) {
    throw new Error(`JWT parse failed: ${e.message}`);
  }

  if (!unverified) {
    throw new Error("JWT decode returned null");
  }

  const issuer = unverified.iss;
  const exp = unverified.exp;
  const iat = unverified.iat;

  // 2) Choose secret by issuer
  let secret;
  let secretName;

  if (issuer === "0-dte") {
    secret = env.SSO_0DTE_SECRET;
    secretName = "SSO_0DTE_SECRET";
  } else if (issuer === "fotw") {
    secret = env.SSO_FOTW_SECRET;
    secretName = "SSO_FOTW_SECRET";
  } else {
    throw new Error(`Invalid SSO issuer: ${issuer}`);
  }

  if (!secret) {
    throw new Error(`Missing secret for issuer ${issuer} (${secretName})`);
  }

  // 3) Verify signature + exp for real
  try {
    return jwt.verify(token, secret, {
      algorithms: ["HS256"],
      clockTolerance: 10, // allow small clock skew (seconds)
    });
  } catch (e) {
    if (e.name === "TokenExpiredError") {
      throw new Error(
        `SSO token expired (now=${now}, exp=${exp}, iat=${iat}, issuer=${issuer}, using=${secretName}, fp=${fingerprint(secret)})`
      );
    }
    throw new Error(
      `Invalid SSO token (${e.name}: ${e.message}) (now=${now}, exp=${exp}, iat=${iat}, issuer=${issuer}, using=${secretName}, fp=${fingerprint(secret)})`
    );
  }
}

/**
 * Issue an app session JWT from verified WordPress user data
 */
export function issueAppSession(user) {
  const env = getAuthConfig();
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iat: now,
    exp: now + env.APP_SESSION_TTL_SECONDS,
    wp: {
      issuer: user.iss,
      id: user.sub,
      email: user.email,
      name: user.name,
      roles: user.roles || [],
    },
  };
  return jwt.sign(payload, env.APP_SESSION_SECRET, { algorithm: "HS256" });
}

/**
 * Read and verify app session from request cookies
 * Returns session payload if valid, null otherwise
 */
export function readAppSession(req) {
  const env = getAuthConfig();
  const token = req.cookies?.[SESSION_COOKIE];

  // Debug: log all /api/orders and /api/trades requests
  if (req.path?.includes('orders') || req.path?.includes('trades')) {
    console.log(`[auth] ${req.path}: hasCookie=${!!token} cookieKeys=${Object.keys(req.cookies || {}).join(',')}`);
  }

  if (!token) {
    return null;
  }

  try {
    const result = jwt.verify(token, env.APP_SESSION_SECRET, {
      algorithms: ["HS256"],
    });
    if (req.path?.includes('orders') || req.path?.includes('trades')) {
      console.log(`[auth] verify SUCCESS for ${req.path}: user=${result?.wp?.email}`);
    }
    return result;
  } catch (e) {
    console.log(`[auth] Session verify failed for ${req.path}: ${e.message}`);
    return null;
  }
}

/**
 * Get current user from request (async compatible)
 */
export function getCurrentUser(req) {
  return readAppSession(req);
}

/**
 * Check if user has admin role
 */
export function isAdmin(user) {
  if (!user) return false;
  if (user.is_admin === true) return true;
  const roles = user?.wp?.roles || user?.roles || [];
  return Array.isArray(roles) && (roles.includes("administrator") || roles.includes("admin"));
}

/**
 * Determine if request is HTTPS (honors reverse proxies)
 */
function isHttpsRequest(req) {
  const xfProto = req.headers["x-forwarded-proto"];
  if (xfProto) {
    return xfProto.toLowerCase() === "https";
  }
  return req.protocol === "https";
}

/**
 * Auth middleware factory
 * Protects routes under /api/* and /sse/* (except auth endpoints)
 */
export function authMiddleware(options = {}) {
  const { publicMode = false } = options;

  return (req, res, next) => {
    const env = getAuthConfig();
    const path = req.path;

    // Emergency public mode (turns off auth)
    if (publicMode || env.PUBLIC_MODE) {
      return next();
    }

    // Check if route needs auth
    const needsAuth =
      path.startsWith("/api/") ||
      path.startsWith("/sse/") ||
      path === "/sse";

    // Allow these auth endpoints without session
    const allowUnauth =
      path === "/api/auth/me" ||
      path === "/api/auth/sso" ||
      path === "/api/auth/logout" ||
      path === "/api/auth/debug" ||
      path === "/api/health" ||
      path.startsWith("/api/admin/_debug");  // Debug endpoints for testing

    if (needsAuth && !allowUnauth) {
      const user = getCurrentUser(req);
      if (!user) {
        console.log(`[auth] 401 for ${req.method} ${req.path} - no valid session`);
        return res.status(401).json({ detail: "Not authenticated" });
      }
      req.user = user;
    }

    next();
  };
}

/**
 * Set session cookie on response
 */
export function setSessionCookie(res, sessionJwt, req) {
  const env = getAuthConfig();
  const isHttps = isHttpsRequest(req);
  const secureCookie = isHttps;

  res.cookie(SESSION_COOKIE, sessionJwt, {
    httpOnly: true,
    secure: secureCookie,
    sameSite: "lax",
    path: "/",
    maxAge: env.APP_SESSION_TTL_SECONDS * 1000,
  });
}

/**
 * Clear session cookie on response
 */
export function clearSessionCookie(res) {
  res.clearCookie(SESSION_COOKIE, {
    path: "/",
  });
}

export { SESSION_COOKIE };
