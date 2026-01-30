// ui/src/pages/Profile.tsx
// Profile page with MarketSwarm aurora styling

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface Profile {
  display_name: string;
  email: string;
  issuer: string;
  wp_user_id: number;
  is_admin: boolean;
  roles: string[];
  last_login_at: string;
  created_at: string;
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/profile/me', { credentials: 'include' })
      .then(res => {
        if (!res.ok) throw new Error('Failed to load profile');
        return res.json();
      })
      .then(setProfile)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const formatDate = (d: string) => d ? new Date(d).toLocaleString() : '—';

  return (
    <div className="profile-page">
      {/* Aurora background */}
      <div className="profile-aurora-bg">
        <div className="profile-vignette" />
        <div className="aurora aurora-a" />
        <div className="aurora aurora-b" />
        <div className="aurora aurora-c" />
        <div className="aurora-grain" />
      </div>

      {/* Content */}
      <div className="profile-content">
        <div className="profile-card">
          <div className="profile-card-inner">
            {/* Header */}
            <div className="profile-header">
              <button className="back-btn" onClick={() => navigate('/')}>
                <span className="back-arrow">←</span> Dashboard
              </button>
              <h1 className="profile-title">Your Profile</h1>
              {profile?.is_admin && <span className="admin-badge">Admin</span>}
            </div>

            {loading && <div className="profile-loading"><div className="spinner" /></div>}
            {error && <div className="profile-error">{error}</div>}

            {profile && !loading && (
              <>
                {/* Avatar & Name */}
                <div className="profile-avatar-section">
                  <div className="avatar-glow">
                    <div className="avatar">
                      {profile.display_name?.charAt(0).toUpperCase() || '?'}
                    </div>
                  </div>
                  <div className="profile-name">{profile.display_name}</div>
                  <div className="profile-email">{profile.email}</div>
                </div>

                {/* Info Grid */}
                <div className="info-grid">
                  <InfoRow label="Issuer" value={profile.issuer} icon="🌐" />
                  <InfoRow label="User ID" value={`#${profile.wp_user_id}`} icon="🆔" />
                  <InfoRow label="Roles" value={profile.roles?.join(', ') || 'Member'} icon="🎭" />
                  <InfoRow label="Member Since" value={formatDate(profile.created_at)} icon="📅" />
                  <InfoRow label="Last Login" value={formatDate(profile.last_login_at)} icon="🕐" />
                </div>

                {/* Coming Soon Tiles */}
                <div className="coming-soon-section">
                  <h2 className="section-title">Coming Soon</h2>
                  <div className="tiles-grid">
                    <ComingSoonTile title="Trade Log" desc="View your trade history & performance" icon="📊" />
                    <ComingSoonTile title="Broker Link" desc="Connect your brokerage account" icon="🔗" />
                  </div>
                </div>

                {/* Logout */}
                <a href="/api/auth/logout?next=/" className="logout-btn">
                  Sign Out
                </a>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .profile-page {
          position: relative;
          min-height: 100vh;
          overflow: hidden;
          background: #09090b;
          color: #f1f5f9;
        }
        .profile-aurora-bg {
          pointer-events: none;
          position: absolute;
          inset: 0;
        }
        .profile-vignette {
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
        .aurora-a { opacity: 0.7; animation: auroraDriftA 12s ease-in-out infinite alternate; }
        .aurora-b { inset: -45%; opacity: 0.6; animation: auroraDriftB 16s ease-in-out infinite alternate; }
        .aurora-c { inset: -50%; opacity: 0.5; animation: auroraDriftC 20s ease-in-out infinite alternate; }
        @keyframes auroraDriftA { 0% { transform: translate(-6%, -4%) rotate(0deg) scale(1.02); } 100% { transform: translate(6%, 3%) rotate(8deg) scale(1.08); } }
        @keyframes auroraDriftB { 0% { transform: translate(5%, -3%) rotate(-6deg) scale(1.00); } 100% { transform: translate(-7%, 4%) rotate(10deg) scale(1.10); } }
        @keyframes auroraDriftC { 0% { transform: translate(-3%, 6%) rotate(4deg) scale(1.02); } 100% { transform: translate(4%, -6%) rotate(-8deg) scale(1.12); } }
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
        .profile-content {
          position: relative;
          z-index: 10;
          display: flex;
          width: 100%;
          min-height: 100vh;
          align-items: center;
          justify-content: center;
          padding: 2rem 1rem;
          box-sizing: border-box;
        }
        .profile-card {
          width: 100%;
          max-width: 32rem;
          margin: 0 auto;
          border-radius: 1.5rem;
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(24,24,27,0.4);
          box-shadow: 0 20px 80px rgba(0,0,0,0.6);
          backdrop-filter: blur(24px);
        }
        .profile-card-inner { padding: 2rem; }
        .profile-header {
          display: flex;
          align-items: center;
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .back-btn {
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.12);
          color: #94a3b8;
          padding: 0.5rem 1rem;
          border-radius: 0.75rem;
          font-size: 0.875rem;
          cursor: pointer;
          transition: all 0.15s;
        }
        .back-btn:hover { background: rgba(255,255,255,0.12); color: #f1f5f9; }
        .back-arrow { margin-right: 0.25rem; }
        .profile-title {
          flex: 1;
          font-size: 1.5rem;
          font-weight: 600;
          margin: 0;
          letter-spacing: -0.025em;
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
        .profile-loading, .profile-error {
          display: flex;
          justify-content: center;
          padding: 3rem;
        }
        .profile-error { color: #f87171; }
        .spinner {
          width: 2rem;
          height: 2rem;
          border: 3px solid rgba(255,255,255,0.1);
          border-top-color: #22d3ee;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .profile-avatar-section {
          display: flex;
          flex-direction: column;
          align-items: center;
          margin-bottom: 2rem;
        }
        .avatar-glow {
          padding: 4px;
          border-radius: 50%;
          background: linear-gradient(135deg, #22d3ee, #6366f1, #10b981);
          animation: glowPulse 3s ease-in-out infinite;
        }
        @keyframes glowPulse {
          0%, 100% { box-shadow: 0 0 20px rgba(34,211,238,0.4), 0 0 40px rgba(99,102,241,0.2); }
          50% { box-shadow: 0 0 30px rgba(34,211,238,0.6), 0 0 60px rgba(99,102,241,0.3); }
        }
        .avatar {
          width: 5rem;
          height: 5rem;
          border-radius: 50%;
          background: #18181b;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 2rem;
          font-weight: 700;
          color: #22d3ee;
        }
        .profile-name {
          margin-top: 1rem;
          font-size: 1.25rem;
          font-weight: 600;
        }
        .profile-email {
          color: #64748b;
          font-size: 0.875rem;
        }
        .info-grid {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          margin-bottom: 2rem;
        }
        .info-row {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.875rem 1rem;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 0.875rem;
          transition: all 0.15s;
        }
        .info-row:hover {
          background: rgba(255,255,255,0.06);
          border-color: rgba(255,255,255,0.12);
        }
        .info-icon {
          font-size: 1.25rem;
          width: 2rem;
          text-align: center;
        }
        .info-label {
          color: #64748b;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .info-value {
          color: #f1f5f9;
          font-size: 0.9rem;
        }
        .coming-soon-section {
          margin-bottom: 1.5rem;
        }
        .section-title {
          font-size: 0.875rem;
          color: #64748b;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin: 0 0 0.75rem;
        }
        .tiles-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
        }
        .tile {
          position: relative;
          padding: 1.25rem;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 1rem;
          text-align: center;
          overflow: hidden;
        }
        .tile::before {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, rgba(34,211,238,0.1), rgba(99,102,241,0.1));
          opacity: 0;
          transition: opacity 0.3s;
        }
        .tile:hover::before { opacity: 1; }
        .tile-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
        .tile-title { font-weight: 600; font-size: 0.9rem; margin-bottom: 0.25rem; }
        .tile-desc { font-size: 0.75rem; color: #64748b; }
        .tile-badge {
          position: absolute;
          top: 0.5rem;
          right: 0.5rem;
          font-size: 0.6rem;
          background: rgba(99,102,241,0.3);
          color: #a5b4fc;
          padding: 0.15rem 0.4rem;
          border-radius: 4px;
        }
        .logout-btn {
          display: block;
          width: 100%;
          text-align: center;
          padding: 0.875rem;
          background: rgba(239,68,68,0.1);
          border: 1px solid rgba(239,68,68,0.2);
          color: #f87171;
          border-radius: 0.875rem;
          text-decoration: none;
          font-weight: 500;
          transition: all 0.15s;
        }
        .logout-btn:hover {
          background: rgba(239,68,68,0.2);
          border-color: rgba(239,68,68,0.3);
        }
      `}</style>
    </div>
  );
}

function InfoRow({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className="info-row">
      <span className="info-icon">{icon}</span>
      <div>
        <div className="info-label">{label}</div>
        <div className="info-value">{value}</div>
      </div>
    </div>
  );
}

function ComingSoonTile({ title, desc, icon }: { title: string; desc: string; icon: string }) {
  return (
    <div className="tile">
      <span className="tile-badge">Soon</span>
      <div className="tile-icon">{icon}</div>
      <div className="tile-title">{title}</div>
      <div className="tile-desc">{desc}</div>
    </div>
  );
}
