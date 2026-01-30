// services/sse/src/auth.js
// WordPress SSO authentication layer for MarketSwarm

import jwt from "jsonwebtoken";
import crypto from "crypto";

// Environment variables (loaded from .env or shell)
const APP_SESSION_SECRET = process.env.APP_SESSION_SECRET || "change-me";
const APP_SESSION_TTL_SECONDS = parseInt(process.env.APP_SESSION_TTL_SECONDS || "86400", 10);

const SSO_0DTE_SECRET = process.env.SSO_0DTE_SECRET || "";
const SSO_FOTW_SECRET = process.env.SSO_FOTW_SECRET || "";

// Cookie name for app session
const SESSION_COOKIE = "ms_session";

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
  console.log("[auth] Configuration:");
  console.log(`  SSO_0DTE_SECRET: ${SSO_0DTE_SECRET ? `set (fp: ${fingerprint(SSO_0DTE_SECRET)})` : "NOT SET"}`);
  console.log(`  SSO_FOTW_SECRET: ${SSO_FOTW_SECRET ? `set (fp: ${fingerprint(SSO_FOTW_SECRET)})` : "NOT SET"}`);
  console.log(`  APP_SESSION_SECRET: ${APP_SESSION_SECRET !== "change-me" ? `set (fp: ${fingerprint(APP_SESSION_SECRET)})` : "NOT SET (using default)"}`);
  console.log(`  APP_SESSION_TTL_SECONDS: ${APP_SESSION_TTL_SECONDS}`);
}

/**
 * Verify WordPress SSO JWT token
 * Returns decoded payload if valid, throws error otherwise
 */
export function verifyWpSsoToken(token) {
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
    secret = SSO_0DTE_SECRET;
    secretName = "SSO_0DTE_SECRET";
  } else if (issuer === "fotw") {
    secret = SSO_FOTW_SECRET;
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
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iat: now,
    exp: now + APP_SESSION_TTL_SECONDS,
    wp: {
      issuer: user.iss,
      id: user.sub,
      email: user.email,
      name: user.name,
      roles: user.roles || [],
    },
  };
  return jwt.sign(payload, APP_SESSION_SECRET, { algorithm: "HS256" });
}

/**
 * Read and verify app session from request cookies
 * Returns session payload if valid, null otherwise
 */
export function readAppSession(req) {
  const token = req.cookies?.[SESSION_COOKIE];
  if (!token) {
    return null;
  }

  try {
    return jwt.verify(token, APP_SESSION_SECRET, {
      algorithms: ["HS256"],
    });
  } catch (e) {
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
  return Array.isArray(roles) && roles.includes("administrator");
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
    const path = req.path;

    // Emergency public mode (turns off auth)
    if (publicMode || process.env.PUBLIC_MODE === "1") {
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
      path === "/api/health";

    if (needsAuth && !allowUnauth) {
      const user = getCurrentUser(req);
      if (!user) {
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
  const isHttps = isHttpsRequest(req);
  const secureCookie = isHttps && process.env.APP_COOKIE_SECURE !== "0";
  const cookieDomain = process.env.APP_COOKIE_DOMAIN || undefined;

  res.cookie(SESSION_COOKIE, sessionJwt, {
    httpOnly: true,
    secure: secureCookie,
    sameSite: "lax",
    path: "/",
    domain: cookieDomain,
    maxAge: APP_SESSION_TTL_SECONDS * 1000,
  });
}

/**
 * Clear session cookie on response
 */
export function clearSessionCookie(res) {
  const cookieDomain = process.env.APP_COOKIE_DOMAIN || undefined;
  res.clearCookie(SESSION_COOKIE, {
    path: "/",
    domain: cookieDomain,
  });
}

export { SESSION_COOKIE };
