// ui/src/pages/Profile.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppLayout from "../components/AppLayout";

interface Profile {
  display_name: string;
  email: string;
  issuer: string;
  wp_user_id: number;
  is_admin: boolean;
  roles: string[];
  subscription_tier: string | null;
  last_login_at: string;
  created_at: string;
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/profile/me", { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load profile");
        return res.json();
      })
      .then(setProfile)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const formatDate = (d: string) =>
    d ? new Date(d).toLocaleString() : "—";

  return (
    <AppLayout>
      <div className="profile-page">
        <div className="profile-container">
          {/* Page Title */}
          <div className="profile-page-header">
            <button className="back-btn" onClick={() => navigate("/")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Back
            </button>
            <h1>Profile</h1>
            {profile?.is_admin && <span className="admin-badge">Admin</span>}
          </div>

          {loading && (
            <div className="profile-loading">
              <div className="spinner" />
            </div>
          )}

          {error && <div className="profile-error">{error}</div>}

          {profile && !loading && (
            <div className="profile-grid">
              {/* User Info Card */}
              <div className="profile-card user-card">
                <div className="card-header">
                  <svg className="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  <h2>User Information</h2>
                </div>
                <div className="card-content">
                  <div className="avatar-section">
                    <div className="avatar">
                      {profile.display_name?.charAt(0).toUpperCase() || "?"}
                    </div>
                    <div className="avatar-info">
                      <div className="user-name">{profile.display_name}</div>
                      <div className="user-email">{profile.email}</div>
                    </div>
                  </div>
                  <div className="info-rows">
                    <InfoRow
                      icon={<GlobeIcon />}
                      label="Platform"
                      value={profile.issuer === "fotw" ? "Fly On The Wall" : profile.issuer === "0-dte" ? "0-DTE" : profile.issuer}
                    />
                    <InfoRow
                      icon={<IdIcon />}
                      label="User ID"
                      value={`#${profile.wp_user_id}`}
                    />
                    <InfoRow
                      icon={<ShieldIcon />}
                      label="Roles"
                      value={profile.roles?.join(", ") || "Member"}
                    />
                  </div>
                </div>
              </div>

              {/* Subscription Card */}
              <div className="profile-card subscription-card">
                <div className="card-header">
                  <svg className="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                  </svg>
                  <h2>Subscription</h2>
                </div>
                <div className="card-content">
                  <div className="subscription-tier-display">
                    {profile.subscription_tier ? (
                      <>
                        <span className="tier-badge">{profile.subscription_tier}</span>
                        <span className="tier-status active">Active</span>
                      </>
                    ) : (
                      <>
                        <span className="tier-none">No active subscription</span>
                        <span className="tier-status inactive">Inactive</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Activity Card */}
              <div className="profile-card activity-card">
                <div className="card-header">
                  <svg className="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <h2>Activity</h2>
                </div>
                <div className="card-content">
                  <div className="info-rows">
                    <InfoRow
                      icon={<CalendarIcon />}
                      label="Member Since"
                      value={formatDate(profile.created_at)}
                    />
                    <InfoRow
                      icon={<ClockIcon />}
                      label="Last Login"
                      value={formatDate(profile.last_login_at)}
                    />
                  </div>
                </div>
              </div>

              {/* Coming Soon Cards */}
              <div className="profile-card coming-soon-card">
                <div className="card-header">
                  <svg className="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 3v18h18" />
                    <path d="M18 17V9" />
                    <path d="M13 17V5" />
                    <path d="M8 17v-3" />
                  </svg>
                  <h2>Trade Log</h2>
                  <span className="soon-badge">Coming Soon</span>
                </div>
                <div className="card-content">
                  <p className="coming-soon-text">
                    Track your trades and analyze performance metrics.
                  </p>
                </div>
              </div>

              <div className="profile-card coming-soon-card">
                <div className="card-header">
                  <svg className="card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                  </svg>
                  <h2>Broker Integration</h2>
                  <span className="soon-badge">Coming Soon</span>
                </div>
                <div className="card-content">
                  <p className="coming-soon-text">
                    Connect your brokerage account for seamless trading.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Logout */}
          {profile && (
            <div className="profile-actions">
              <a href="/api/auth/logout?next=/" className="logout-btn">
                Sign Out
              </a>
            </div>
          )}
        </div>

        <style>{`
          .profile-page {
            min-height: calc(100vh - 50px);
            background: #09090b;
            color: #f1f5f9;
            padding: 1.5rem;
          }

          .profile-container {
            max-width: 1200px;
            margin: 0 auto;
          }

          .profile-page-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
          }

          .back-btn {
            display: flex;
            align-items: center;
            gap: 0.375rem;
            padding: 0.5rem 0.875rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 0.5rem;
            color: #a1a1aa;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
          }

          .back-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            color: #e4e4e7;
          }

          .back-btn svg {
            width: 1rem;
            height: 1rem;
          }

          .profile-page-header h1 {
            font-size: 1.5rem;
            font-weight: 600;
            margin: 0;
            color: #f1f5f9;
          }

          .admin-badge {
            background: linear-gradient(135deg, #22d3ee, #10b981);
            color: #09090b;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
          }

          .profile-loading {
            display: flex;
            justify-content: center;
            padding: 4rem;
          }

          .spinner {
            width: 2rem;
            height: 2rem;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #22d3ee;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
          }

          @keyframes spin {
            to { transform: rotate(360deg); }
          }

          .profile-error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
            padding: 1rem;
            border-radius: 0.75rem;
            text-align: center;
          }

          .profile-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
          }

          @media (max-width: 768px) {
            .profile-grid {
              grid-template-columns: 1fr;
            }
          }

          .profile-card {
            background: rgba(24, 24, 27, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 0.75rem;
            overflow: hidden;
          }

          .card-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.875rem 1rem;
            background: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          }

          .card-header h2 {
            font-size: 0.875rem;
            font-weight: 600;
            margin: 0;
            color: #e4e4e7;
            flex: 1;
          }

          .card-icon {
            width: 1.125rem;
            height: 1.125rem;
            color: #71717a;
          }

          .soon-badge {
            font-size: 0.65rem;
            background: rgba(99, 102, 241, 0.2);
            color: #a5b4fc;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-weight: 500;
          }

          .card-content {
            padding: 1rem;
          }

          .avatar-section {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
          }

          .avatar {
            width: 3.5rem;
            height: 3.5rem;
            border-radius: 50%;
            background: linear-gradient(135deg, #22d3ee, #6366f1);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            font-weight: 700;
            color: #fff;
          }

          .avatar-info {
            flex: 1;
          }

          .user-name {
            font-size: 1.125rem;
            font-weight: 600;
            color: #f1f5f9;
          }

          .user-email {
            font-size: 0.8125rem;
            color: #71717a;
          }

          .info-rows {
            display: flex;
            flex-direction: column;
            gap: 0.625rem;
          }

          .info-row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.625rem 0.75rem;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 0.5rem;
          }

          .info-row-icon {
            width: 1rem;
            height: 1rem;
            color: #52525b;
          }

          .info-row-content {
            flex: 1;
          }

          .info-row-label {
            font-size: 0.7rem;
            color: #52525b;
            text-transform: uppercase;
            letter-spacing: 0.05em;
          }

          .info-row-value {
            font-size: 0.875rem;
            color: #e4e4e7;
          }

          .coming-soon-text {
            color: #71717a;
            font-size: 0.875rem;
            margin: 0;
          }

          .subscription-tier-display {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
          }

          .tier-badge {
            font-size: 1.125rem;
            font-weight: 600;
            color: #f1f5f9;
            background: linear-gradient(135deg, rgba(34, 211, 238, 0.15), rgba(99, 102, 241, 0.15));
            border: 1px solid rgba(34, 211, 238, 0.3);
            padding: 0.5rem 1rem;
            border-radius: 0.5rem;
          }

          .tier-none {
            font-size: 0.875rem;
            color: #71717a;
          }

          .tier-status {
            font-size: 0.75rem;
            font-weight: 500;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
          }

          .tier-status.active {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
          }

          .tier-status.inactive {
            background: rgba(113, 113, 122, 0.15);
            color: #a1a1aa;
            border: 1px solid rgba(113, 113, 122, 0.3);
          }

          .profile-actions {
            margin-top: 1.5rem;
            display: flex;
            justify-content: flex-end;
          }

          .logout-btn {
            display: inline-block;
            padding: 0.625rem 1.25rem;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #f87171;
            border-radius: 0.5rem;
            text-decoration: none;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.15s;
          }

          .logout-btn:hover {
            background: rgba(239, 68, 68, 0.15);
            border-color: rgba(239, 68, 68, 0.3);
          }
        `}</style>
      </div>
    </AppLayout>
  );
}

// Info Row Component
function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="info-row">
      <span className="info-row-icon">{icon}</span>
      <div className="info-row-content">
        <div className="info-row-label">{label}</div>
        <div className="info-row-value">{value}</div>
      </div>
    </div>
  );
}

// SVG Icons
function GlobeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function IdIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <line x1="2" y1="10" x2="22" y2="10" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}
