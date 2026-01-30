// ui/src/components/LoginPage.tsx
// WordPress SSO Login Page for MarketSwarm

export default function LoginPage() {
  // Build redirect URL for SSO callback
  const nextPath = encodeURIComponent(window.location.pathname + window.location.search);
  const redirect = encodeURIComponent(`${window.location.origin}/api/auth/sso?next=${nextPath}`);

  // WordPress SSO endpoints (can be overridden via env vars)
  const login0dte =
    import.meta.env.VITE_WP_0DTE_LOGIN_URL ||
    `https://0-dte.com/fotw-sso?redirect=${redirect}`;

  const loginFOTW =
    import.meta.env.VITE_WP_FOTW_LOGIN_URL ||
    `https://flyonthewall.ai/fotw-sso?redirect=${redirect}`;

  return (
    <div className="login-page">
      {/* Aurora background */}
      <div className="login-aurora-bg">
        <div className="login-vignette" />
        <div className="aurora aurora-a" />
        <div className="aurora aurora-b" />
        <div className="aurora aurora-c" />
        <div className="aurora-grain" />
      </div>

      {/* Content */}
      <div className="login-content">
        <div className="login-card">
          <div className="login-card-inner">
            {/* Logo & Header */}
            <div className="login-header">
              <div className="login-logo-box">
                <img
                  src="/fotw-logo.png"
                  alt="Fly On The Wall"
                  className="login-logo"
                />
              </div>
              <div>
                <h1 className="login-title">Sign in to continue</h1>
                <p className="login-subtitle">
                  Choose where your membership is hosted.
                </p>
              </div>
            </div>

            {/* Login Buttons */}
            <div className="login-buttons">
              {/* FlyOnTheWall */}
              <a href={loginFOTW} className="login-btn login-btn-primary">
                <div className="login-btn-content">
                  <div className="login-btn-icon login-btn-icon-primary">
                    <img
                      src="/fotw-logo.png"
                      alt=""
                      className="login-btn-logo"
                    />
                  </div>
                  <div className="login-btn-text">
                    <div className="login-btn-label">Continue with FlyOnTheWall</div>
                    <div className="login-btn-hint">flyonthewall.ai membership</div>
                  </div>
                </div>
                <span className="login-btn-arrow">
                  Login <span className="arrow">→</span>
                </span>
              </a>

              {/* 0-DTE */}
              <a href={login0dte} className="login-btn login-btn-secondary">
                <div className="login-btn-content">
                  <div className="login-btn-icon login-btn-icon-secondary">
                    <img
                      src="/0-dte-logo.png"
                      alt="0-DTE"
                      className="login-btn-logo"
                    />
                  </div>
                  <div className="login-btn-text">
                    <div className="login-btn-label">Continue with 0-DTE</div>
                    <div className="login-btn-hint-light">0-dte.com membership</div>
                  </div>
                </div>
                <span className="login-btn-arrow-light">
                  Login <span className="arrow">→</span>
                </span>
              </a>
            </div>

            {/* Signup link */}
            <div className="login-footer">
              <p>
                If not a member, please{" "}
                <a
                  href="https://flyonthewall.ai/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="login-link"
                >
                  sign up here
                </a>
                .
              </p>
              <p className="login-tip">
                Tip: if you're already signed into the membership site, you'll be
                dropped straight into the dashboard.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Inline styles for aurora animation */}
      <style>{`
        .login-page {
          position: relative;
          min-height: 100vh;
          overflow: hidden;
          background: #09090b;
          color: #f1f5f9;
        }

        .login-aurora-bg {
          pointer-events: none;
          position: absolute;
          inset: 0;
        }

        .login-vignette {
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

        .login-content {
          position: relative;
          z-index: 10;
          display: flex;
          width: 100%;
          min-height: 100vh;
          align-items: center;
          justify-content: center;
          padding: 3rem 1.5rem;
          box-sizing: border-box;
        }

        .login-card {
          width: 100%;
          max-width: 28rem;
          margin: 0 auto;
          border-radius: 1.5rem;
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(24,24,27,0.3);
          box-shadow: 0 20px 80px rgba(0,0,0,0.6);
          backdrop-filter: blur(24px);
        }

        .login-card-inner {
          padding: 2rem 2.5rem;
        }

        .login-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .login-logo-box {
          display: flex;
          height: 3rem;
          width: 3rem;
          align-items: center;
          justify-content: center;
          border-radius: 1rem;
          background: rgba(255,255,255,0.9);
          box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .login-logo {
          height: 2rem;
          width: 2rem;
          object-fit: contain;
        }

        .login-logo-fallback {
          font-size: 1rem;
          font-weight: 700;
          color: #09090b;
        }

        .login-title {
          font-size: 1.5rem;
          font-weight: 600;
          letter-spacing: -0.025em;
          margin: 0;
        }

        .login-subtitle {
          margin-top: 0.25rem;
          font-size: 0.875rem;
          color: rgba(203,213,225,0.8);
        }

        .login-buttons {
          margin-top: 2rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .login-btn {
          display: flex;
          width: 100%;
          align-items: center;
          justify-content: space-between;
          border-radius: 1rem;
          padding: 1rem 1.25rem;
          text-decoration: none;
          transition: all 0.15s ease;
        }

        .login-btn:hover {
          transform: translateY(-1px);
        }

        .login-btn-primary {
          background: rgba(255,255,255,0.9);
          color: #09090b;
          box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .login-btn-primary:hover {
          background: #fff;
        }

        .login-btn-secondary {
          background: rgba(9,9,11,0.3);
          color: #f1f5f9;
          border: 1px solid rgba(255,255,255,0.12);
          backdrop-filter: blur(8px);
        }

        .login-btn-secondary:hover {
          background: rgba(9,9,11,0.4);
        }

        .login-btn-content {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .login-btn-icon {
          display: flex;
          height: 2.5rem;
          width: 2.5rem;
          align-items: center;
          justify-content: center;
          border-radius: 0.75rem;
        }

        .login-btn-icon-primary {
          background: rgba(9,9,11,0.05);
          border: 1px solid rgba(0,0,0,0.05);
        }

        .login-btn-icon-secondary {
          background: rgba(255,255,255,0.1);
          border: 1px solid rgba(255,255,255,0.1);
        }

        .login-btn-logo {
          height: 1.5rem;
          width: 1.5rem;
          object-fit: contain;
        }

        .login-btn-logo-fallback {
          font-size: 0.75rem;
          font-weight: 700;
        }

        .login-btn-text {
          text-align: left;
        }

        .login-btn-label {
          font-size: 0.875rem;
          font-weight: 600;
          line-height: 1.25;
        }

        .login-btn-hint {
          font-size: 0.75rem;
          color: #52525b;
        }

        .login-btn-hint-light {
          font-size: 0.75rem;
          color: rgba(203,213,225,0.7);
        }

        .login-btn-arrow {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.875rem;
          font-weight: 600;
          color: #27272a;
        }

        .login-btn-arrow-light {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.875rem;
          font-weight: 600;
          color: rgba(241,245,249,0.9);
        }

        .login-btn:hover .arrow {
          transform: translateX(4px);
        }

        .arrow {
          transition: transform 0.15s ease;
        }

        .login-footer {
          margin-top: 1.25rem;
          font-size: 0.75rem;
          color: rgba(203,213,225,0.8);
        }

        .login-footer p {
          margin: 0;
        }

        .login-link {
          font-weight: 600;
          color: rgba(255,255,255,0.9);
          text-decoration: underline;
          text-underline-offset: 4px;
          transition: color 0.15s ease;
        }

        .login-link:hover {
          color: #fff;
        }

        .login-tip {
          margin-top: 0.75rem !important;
          color: rgba(148,163,184,0.8);
        }
      `}</style>
    </div>
  );
}
