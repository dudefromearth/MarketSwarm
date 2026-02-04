// services/sse/src/routes/auth.js
// Auth routes for WordPress SSO integration

import { Router } from "express";
import {
  verifyWpSsoToken,
  issueAppSession,
  getCurrentUser,
  setSessionCookie,
  clearSessionCookie,
} from "../auth.js";
import { upsertUserFromWpToken, getUserProfile, getLeaderboardSettings, updateLeaderboardSettings } from "../db/userStore.js";
import { isDbAvailable } from "../db/index.js";

const router = Router();

/**
 * GET /api/auth/me
 * Frontend calls this on boot to check if authenticated
 * - 200 => user is logged in, return session data
 * - 401 => not authenticated, show login page
 */
router.get("/me", (req, res) => {
  const user = getCurrentUser(req);
  if (!user) {
    return res.status(401).json({ detail: "Not authenticated" });
  }
  return res.json(user);
});

/**
 * GET /api/auth/sso
 * WordPress redirects the browser here with ?sso=<jwt>
 * Verifies the SSO token, creates app session, sets cookie, redirects to app
 */
router.get("/sso", async (req, res) => {
  const { sso, next = "/" } = req.query;

  if (!sso) {
    return res.status(400).json({ detail: "Missing sso parameter" });
  }

  try {
    // 1) Verify incoming WordPress SSO token
    const wpUser = verifyWpSsoToken(sso);

    // 2) Persist/update user in database (if DB available)
    if (isDbAvailable()) {
      await upsertUserFromWpToken(wpUser);
    }

    // 3) Issue app session JWT
    const sessionJwt = issueAppSession(wpUser);

    // 4) Set cookie and redirect to app
    setSessionCookie(res, sessionJwt, req);

    // Log successful login
    console.log(`[auth] SSO login successful: ${wpUser.email || wpUser.sub} (issuer: ${wpUser.iss})`);

    return res.redirect(302, next);
  } catch (err) {
    console.error(`[auth] SSO verification failed: ${err.message}`);
    return res.status(401).json({ detail: err.message });
  }
});

/**
 * GET /api/profile/me
 * Returns persisted user profile from database
 */
router.get("/profile/me", async (req, res) => {
  const session = getCurrentUser(req);
  if (!session) {
    return res.status(401).json({ detail: "Not authenticated" });
  }

  if (!isDbAvailable()) {
    // Return session data if DB not available
    return res.json({
      email: session.wp?.email,
      display_name: session.wp?.name,
      issuer: session.wp?.issuer,
      roles: session.wp?.roles || [],
      is_admin: (session.wp?.roles || []).includes("administrator") || (session.wp?.roles || []).includes("admin"),
    });
  }

  const profile = await getUserProfile(session.wp?.issuer, session.wp?.id);
  if (!profile) {
    return res.status(404).json({ detail: "Profile not found" });
  }

  // Also check session roles for admin (in case DB record is stale)
  const sessionRoles = session.wp?.roles || [];
  const sessionIsAdmin = sessionRoles.includes("administrator") || sessionRoles.includes("admin");

  return res.json({
    ...profile,
    // Use session's admin status if it says admin (freshest source)
    is_admin: profile.is_admin || sessionIsAdmin,
  });
});

/**
 * GET /api/auth/logout
 * Clears session cookie and redirects to login or specified URL
 */
router.get("/logout", (req, res) => {
  const { next = "/" } = req.query;

  const user = getCurrentUser(req);
  if (user) {
    console.log(`[auth] Logout: ${user.wp?.email || user.wp?.id || "unknown"}`);
  }

  clearSessionCookie(res);
  return res.redirect(302, next);
});

/**
 * GET /api/profile/leaderboard-settings
 * Get leaderboard display settings for the current user
 */
router.get("/profile/leaderboard-settings", async (req, res) => {
  const session = getCurrentUser(req);
  if (!session) {
    return res.status(401).json({ detail: "Not authenticated" });
  }

  if (!isDbAvailable()) {
    return res.status(503).json({ detail: "Database not available" });
  }

  const settings = await getLeaderboardSettings(session.wp?.issuer, session.wp?.id);
  if (!settings) {
    return res.status(404).json({ detail: "Settings not found" });
  }

  return res.json(settings);
});

/**
 * PATCH /api/profile/leaderboard-settings
 * Update leaderboard display settings for the current user
 */
router.patch("/profile/leaderboard-settings", async (req, res) => {
  const session = getCurrentUser(req);
  if (!session) {
    return res.status(401).json({ detail: "Not authenticated" });
  }

  if (!isDbAvailable()) {
    return res.status(503).json({ detail: "Database not available" });
  }

  try {
    const { screenName, showScreenName } = req.body;
    const updated = await updateLeaderboardSettings(session.wp?.issuer, session.wp?.id, {
      screenName,
      showScreenName,
    });

    if (!updated) {
      return res.status(404).json({ detail: "User not found" });
    }

    return res.json(updated);
  } catch (e) {
    return res.status(400).json({ detail: e.message });
  }
});

/**
 * GET /api/auth/debug
 * Debug endpoint (only in development)
 * Shows auth configuration status without exposing secrets
 */
router.get("/debug", (req, res) => {
  if (process.env.NODE_ENV === "production") {
    return res.status(404).json({ detail: "Not found" });
  }

  const user = getCurrentUser(req);

  res.json({
    authenticated: !!user,
    user: user ? {
      issuer: user.wp?.issuer,
      email: user.wp?.email,
      name: user.wp?.name,
      roles: user.wp?.roles,
      exp: user.exp,
      iat: user.iat,
    } : null,
    config: {
      SSO_0DTE_SECRET: !!process.env.SSO_0DTE_SECRET,
      SSO_FOTW_SECRET: !!process.env.SSO_FOTW_SECRET,
      APP_SESSION_SECRET: process.env.APP_SESSION_SECRET !== "change-me",
      DATABASE_URL: !!process.env.DATABASE_URL,
      DB_CONNECTED: isDbAvailable(),
      PUBLIC_MODE: process.env.PUBLIC_MODE === "1",
    },
  });
});

export default router;
