// services/sse/src/routes/auth.js
// Auth routes for WordPress SSO integration

import { Router } from "express";
import {
  verifyWpSsoToken,
  issueAppSession,
  getCurrentUser,
  setSessionCookie,
  clearSessionCookie,
  getAuthConfig,
} from "../auth.js";
import { upsertUserFromWpToken, getUserProfile, updateUserTimezone, getLeaderboardSettings, updateLeaderboardSettings } from "../db/userStore.js";
import { isDbAvailable } from "../db/index.js";
import { getTierGates, tierFromRoles } from "../tierGates.js";

const router = Router();

/**
 * Build the styled "wrong membership tier" HTML page.
 * Matches the login page aurora theme. Served as a standalone HTML document
 * since the user isn't authenticated and can't access React components.
 *
 * @param {string} redirectUrl - URL to the correct dashboard for this tier
 * @param {string} userTier - The user's detected tier (for display context)
 * @returns {string} Complete HTML document
 */
function buildWrongTierPage(redirectUrl, userTier) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Wrong Dashboard | Fly On The Wall</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #09090b;
      color: #f1f5f9;
      min-height: 100vh;
      overflow: hidden;
    }

    /* Aurora background (matches login page) */
    .aurora-bg {
      pointer-events: none;
      position: fixed;
      inset: 0;
    }

    .vignette {
      position: absolute;
      inset: 0;
      background: radial-gradient(1200px 600px at 50% 20%, rgba(255,255,255,0.06), transparent 60%);
    }

    .aurora {
      position: absolute;
      inset: -40%;
      background:
        radial-gradient(60% 50% at 20% 30%, rgba(34, 211, 238, 0.55), transparent 60%),
        radial-gradient(55% 45% at 80% 20%, rgba(16, 185, 129, 0.45), transparent 65%),
        radial-gradient(60% 55% at 55% 75%, rgba(99, 102, 241, 0.35), transparent 60%),
        radial-gradient(50% 50% at 25% 80%, rgba(14, 165, 233, 0.35), transparent 60%);
      transform: translate3d(0,0,0);
      filter: blur(60px);
    }

    .aurora-a {
      opacity: 0.7;
      animation: auroraDriftA 12s ease-in-out infinite alternate;
    }

    .aurora-b {
      inset: -45%;
      opacity: 0.6;
      animation: auroraDriftB 16s ease-in-out infinite alternate;
    }

    .aurora-c {
      inset: -50%;
      opacity: 0.5;
      animation: auroraDriftC 20s ease-in-out infinite alternate;
    }

    @keyframes auroraDriftA {
      0%   { transform: translate(-6%, -4%) rotate(0deg) scale(1.02); }
      100% { transform: translate(6%,  3%) rotate(8deg) scale(1.08); }
    }

    @keyframes auroraDriftB {
      0%   { transform: translate(5%, -3%) rotate(-6deg) scale(1.00); }
      100% { transform: translate(-7%, 4%) rotate(10deg) scale(1.10); }
    }

    @keyframes auroraDriftC {
      0%   { transform: translate(-3%, 6%) rotate(4deg) scale(1.02); }
      100% { transform: translate(4%, -6%) rotate(-8deg) scale(1.12); }
    }

    .aurora-grain {
      position: absolute;
      inset: 0;
      opacity: 0.07;
      mix-blend-mode: overlay;
      background-image:
        repeating-linear-gradient(0deg, rgba(255,255,255,0.35) 0 1px, transparent 1px 2px),
        repeating-linear-gradient(90deg, rgba(255,255,255,0.22) 0 1px, transparent 1px 3px);
      filter: blur(0.2px);
    }

    /* Content layout */
    .content {
      position: relative;
      z-index: 10;
      display: flex;
      width: 100%;
      min-height: 100vh;
      align-items: center;
      justify-content: center;
      padding: 3rem 1.5rem;
    }

    .card {
      width: 100%;
      max-width: 28rem;
      margin: 0 auto;
      border-radius: 1.5rem;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(24,24,27,0.3);
      box-shadow: 0 20px 80px rgba(0,0,0,0.6);
      backdrop-filter: blur(24px);
    }

    .card-inner {
      padding: 2rem 2.5rem;
    }

    /* Header */
    .header {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .logo-box {
      display: flex;
      height: 3rem;
      width: 3rem;
      align-items: center;
      justify-content: center;
      border-radius: 1rem;
      background: rgba(255,255,255,0.9);
      box-shadow: 0 1px 2px rgba(0,0,0,0.1);
      flex-shrink: 0;
    }

    .logo-box img {
      height: 2rem;
      width: 2rem;
      object-fit: contain;
    }

    .title {
      font-size: 1.5rem;
      font-weight: 600;
      letter-spacing: -0.025em;
      line-height: 1.2;
    }

    .subtitle {
      margin-top: 0.25rem;
      font-size: 0.875rem;
      color: rgba(203,213,225,0.8);
    }

    /* Warning section */
    .warning-section {
      margin-top: 2rem;
      text-align: center;
    }

    .warning-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 4rem;
      height: 4rem;
      border-radius: 50%;
      background: rgba(251, 191, 36, 0.1);
      border: 1px solid rgba(251, 191, 36, 0.2);
      margin-bottom: 1.25rem;
    }

    .warning-icon svg {
      width: 2rem;
      height: 2rem;
      color: #fbbf24;
    }

    .warning-title {
      font-size: 1.125rem;
      font-weight: 600;
      color: #fbbf24;
      margin-bottom: 0.5rem;
    }

    .warning-message {
      font-size: 0.9rem;
      color: rgba(203,213,225,0.9);
      line-height: 1.5;
      max-width: 22rem;
      margin: 0 auto;
    }

    .warning-detail {
      margin-top: 0.75rem;
      font-size: 0.8rem;
      color: rgba(148,163,184,0.8);
      line-height: 1.5;
    }

    /* Action buttons */
    .actions {
      margin-top: 2rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }

    .btn-primary {
      display: flex;
      width: 100%;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      border-radius: 1rem;
      padding: 1rem 1.25rem;
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 600;
      background: rgba(255,255,255,0.9);
      color: #09090b;
      box-shadow: 0 1px 2px rgba(0,0,0,0.1);
      transition: all 0.15s ease;
    }

    .btn-primary:hover {
      background: #fff;
      transform: translateY(-1px);
    }

    .btn-primary .arrow {
      transition: transform 0.15s ease;
    }

    .btn-primary:hover .arrow {
      transform: translateX(4px);
    }

    .btn-secondary {
      display: flex;
      width: 100%;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      border-radius: 1rem;
      padding: 0.875rem 1.25rem;
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 500;
      background: rgba(9,9,11,0.3);
      color: rgba(241,245,249,0.9);
      border: 1px solid rgba(255,255,255,0.12);
      backdrop-filter: blur(8px);
      transition: all 0.15s ease;
    }

    .btn-secondary:hover {
      background: rgba(9,9,11,0.4);
      transform: translateY(-1px);
    }

    /* Footer */
    .footer {
      margin-top: 1.25rem;
      font-size: 0.75rem;
      color: rgba(148,163,184,0.8);
      text-align: center;
      line-height: 1.5;
    }

    .footer a {
      font-weight: 600;
      color: rgba(255,255,255,0.9);
      text-decoration: underline;
      text-underline-offset: 4px;
      transition: color 0.15s ease;
    }

    .footer a:hover {
      color: #fff;
    }
  </style>
</head>
<body>
  <!-- Aurora background -->
  <div class="aurora-bg">
    <div class="vignette"></div>
    <div class="aurora aurora-a"></div>
    <div class="aurora aurora-b"></div>
    <div class="aurora aurora-c"></div>
    <div class="aurora-grain"></div>
  </div>

  <!-- Content -->
  <div class="content">
    <div class="card">
      <div class="card-inner">
        <!-- Logo & Header -->
        <div class="header">
          <div class="logo-box">
            <img src="/fotw-logo.png" alt="Fly On The Wall" />
          </div>
          <div>
            <h1 class="title">Wrong Dashboard</h1>
            <p class="subtitle">Membership tier mismatch</p>
          </div>
        </div>

        <!-- Warning message -->
        <div class="warning-section">
          <div class="warning-icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <h2 class="warning-title">Your membership tier doesn't have access to this dashboard</h2>
          <p class="warning-message">
            This dashboard is reserved for a different membership level.
            Please use the Observer dashboard that matches your subscription.
          </p>
          <p class="warning-detail">
            If you recently upgraded your membership, it may take a few minutes to take effect.
            Try logging in again or contact support if the issue persists.
          </p>
        </div>

        <!-- Action buttons -->
        <div class="actions">
          <a href="${redirectUrl}" class="btn-primary">
            Go to Your Dashboard <span class="arrow">&rarr;</span>
          </a>
          <a href="/api/auth/logout?next=/" class="btn-secondary">
            Sign Out
          </a>
        </div>

        <!-- Footer -->
        <div class="footer">
          <p>
            Need help? Contact
            <a href="https://flyonthewall.ai/support" target="_blank" rel="noopener noreferrer">support</a>.
          </p>
        </div>
      </div>
    </div>
  </div>
</body>
</html>`;
}

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

  // Check if this user's tier is allowed
  const gatesConfig = getTierGates();
  if (gatesConfig && gatesConfig.allowed_tiers) {
    const roles = user.wp?.roles || [];
    const userTier = tierFromRoles(roles, user.wp?.subscription_tier);
    const isAdmin = roles.some(r => ["administrator", "admin"].includes(r.toLowerCase()));
    if (!isAdmin && user.wp?.issuer !== "0-dte" && gatesConfig.allowed_tiers[userTier] === false) {
      clearSessionCookie(res, req);
      return res.status(403).json({
        error: "tier_blocked",
        tier: userTier,
        message: `The ${userTier} tier is not currently allowed on this server.`,
      });
    }
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
  const env = getAuthConfig();

  // PUBLIC_MODE: Create dev session without SSO verification
  if (env.PUBLIC_MODE) {
    const devUser = {
      sub: "dev-user",
      email: "dev@localhost",
      name: "Dev User",
      iss: "dev",
    };
    const sessionJwt = issueAppSession(devUser);
    setSessionCookie(res, sessionJwt, req);
    console.log("[auth] PUBLIC_MODE: Created dev session");
    return res.redirect(302, next);
  }

  if (!sso) {
    return res.status(400).json({ detail: "Missing sso parameter" });
  }

  try {
    // 1) Verify incoming WordPress SSO token
    const wpUser = verifyWpSsoToken(sso);

    // 2) Check if this tier is allowed on this machine (always enforced, regardless of mode)
    const gatesConfig = getTierGates();
    if (gatesConfig && gatesConfig.allowed_tiers) {
      const roles = Array.isArray(wpUser.roles) ? wpUser.roles : [];
      const userTier = tierFromRoles(roles, wpUser.subscription_tier);
      const isAdmin = roles.some(r => ["administrator", "admin"].includes(r.toLowerCase()));
      const isZeroDte = wpUser.iss === "0-dte";

      // Admins and 0-dte members always bypass
      if (!isAdmin && !isZeroDte) {
        const allowed = gatesConfig.allowed_tiers[userTier];
        if (allowed === false) {
          console.log(`[auth] Tier rejected: ${wpUser.email} is ${userTier}, not allowed on this machine`);

          // Clear any existing session cookie so they get a fresh login next time
          clearSessionCookie(res, req);

          // Configurable redirect URL for the correct dashboard
          const mvpDashboardUrl = process.env.TIER_REDIRECT_URL || "https://mvp.flyonthewall.io";

          return res.status(403).send(buildWrongTierPage(mvpDashboardUrl, userTier));
        }
      }
    }

    // 3) Persist/update user in database (if DB available)
    if (isDbAvailable()) {
      await upsertUserFromWpToken(wpUser);
    }

    // 4) Issue app session JWT
    const sessionJwt = issueAppSession(wpUser);

    // 5) Set cookie and redirect to app
    setSessionCookie(res, sessionJwt, req);

    // Log successful login
    const userTierForLog = tierFromRoles(Array.isArray(wpUser.roles) ? wpUser.roles : [], wpUser.subscription_tier);
    console.log(`[auth] SSO login successful: ${wpUser.email || wpUser.sub} (issuer: ${wpUser.iss}, tier: ${userTierForLog}, subscription_tier: ${wpUser.subscription_tier || 'none'})`);

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
 * PUT /api/profile/timezone
 * Update user's timezone preference
 */
router.put("/profile/timezone", async (req, res) => {
  const session = getCurrentUser(req);
  if (!session) {
    return res.status(401).json({ detail: "Not authenticated" });
  }

  if (!isDbAvailable()) {
    return res.status(503).json({ detail: "Database not available" });
  }

  const { timezone } = req.body;

  // Allow null/empty to reset to auto-detect (browser default)
  const tzValue = timezone || null;

  // Validate timezone string if provided (should be IANA timezone like "America/New_York")
  if (tzValue) {
    try {
      Intl.DateTimeFormat(undefined, { timeZone: tzValue });
    } catch (e) {
      return res.status(400).json({ detail: "Invalid timezone" });
    }
  }

  const success = await updateUserTimezone(session.wp?.issuer, session.wp?.id, tzValue);
  if (!success) {
    return res.status(500).json({ detail: "Failed to update timezone" });
  }

  return res.json({ success: true, timezone: tzValue });
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

  clearSessionCookie(res, req);
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
