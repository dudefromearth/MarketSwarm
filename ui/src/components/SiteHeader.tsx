// ui/src/components/SiteHeader.tsx
import { Link } from "react-router-dom";

type Props = {
  displayName?: string | null;
};

export default function SiteHeader({ displayName }: Props) {
  return (
    <div className="site-header">
      {/* Left — greeting */}
      <div className="site-header-left">
        {displayName ? (
          <>
            Hi,{" "}
            <span className="site-header-name">{displayName}</span>
          </>
        ) : (
          <span className="site-header-placeholder">&nbsp;</span>
        )}
      </div>

      {/* Center — logo */}
      <div className="site-header-center">
        <a
          href="https://flyonthewall.ai"
          aria-label="Go to FlyOnTheWall.ai"
          className="site-header-logo-link"
        >
          <img
            src="/fotw-logo.png"
            alt="FOTW"
            className="site-header-logo"
            draggable="false"
          />
        </a>
      </div>

      {/* Right — Workbench + Profile + My Account */}
      <div className="site-header-right">
        <Link to="/workbench" className="site-header-btn">
          Workbench
        </Link>
        <Link to="/profile" className="site-header-btn">
          Profile
        </Link>
        <a
          href="https://flyonthewall.ai/my-account/"
          className="site-header-btn"
          target="_blank"
          rel="noopener noreferrer"
        >
          My Account
        </a>
      </div>

      <style>{`
        .site-header {
          position: sticky;
          top: 0;
          z-index: 50;
          display: grid;
          grid-template-columns: 1fr auto 1fr;
          align-items: center;
          padding: 0.625rem 1.5rem;
          background: #f4f4f5;
          border-bottom: 1px solid #e4e4e7;
        }

        .site-header-left {
          font-size: 0.875rem;
          color: #52525b;
        }

        .site-header-name {
          font-weight: 500;
          color: #18181b;
          text-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
        }

        .site-header-placeholder {
          color: transparent;
        }

        .site-header-center {
          display: flex;
          justify-content: center;
        }

        .site-header-logo-link {
          display: inline-block;
          transition: opacity 0.15s;
        }

        .site-header-logo-link:hover {
          opacity: 0.75;
        }

        .site-header-logo {
          height: 2rem;
          user-select: none;
        }

        .site-header-right {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          gap: 0.5rem;
        }

        .site-header-btn {
          font-size: 0.8125rem;
          color: #3f3f46;
          padding: 0.375rem 0.75rem;
          border-radius: 0.5rem;
          background: #fff;
          border: 1px solid #d4d4d8;
          text-decoration: none;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
          transition: all 0.15s;
        }

        .site-header-btn:hover {
          background: #fafafa;
          border-color: #a1a1aa;
          color: #18181b;
        }
      `}</style>
    </div>
  );
}
