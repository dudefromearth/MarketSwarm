// ui/src/pages/Admin.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

interface AdminStats {
  loginsLast24h: number;
  liveUserCount: number;
  liveUsers: { displayName: string; connectedAt: string }[];
  mostActiveUsers: { id: number; display_name: string; last_login_at: string }[];
}

interface User {
  id: number;
  issuer: string;
  wp_user_id: string;
  email: string;
  display_name: string;
  roles: string[];
  is_admin: boolean;
  is_online: boolean;
  subscription_tier: string | null;
  created_at: string;
  last_login_at: string;
}

interface TradeLog {
  id: string;
  name: string;
  starting_capital: number;
  is_active: number;
  created_at: string;
  updated_at: string;
  tradeCount: number;
}

interface UserDetail {
  user: User;
  tradeLogs: TradeLog[];
}

export default function AdminPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUser, setSelectedUser] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch stats and users on mount
  useEffect(() => {
    Promise.all([
      fetch("/api/admin/stats", { credentials: "include" }).then((r) =>
        r.ok ? r.json() : Promise.reject("Failed to load stats")
      ),
      fetch("/api/admin/users", { credentials: "include" }).then((r) =>
        r.ok ? r.json() : Promise.reject("Failed to load users")
      ),
    ])
      .then(([statsData, usersData]) => {
        setStats(statsData);
        setUsers(usersData.users);
      })
      .catch((e) => setError(typeof e === "string" ? e : e.message))
      .finally(() => setLoading(false));
  }, []);

  // Fetch user detail when clicking on a user
  const handleUserClick = async (userId: number) => {
    try {
      const res = await fetch(`/api/admin/users/${userId}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to load user");
      const data = await res.json();
      setSelectedUser(data);
    } catch (e) {
      console.error("Error loading user detail:", e);
    }
  };

  const formatDate = (d: string) =>
    d ? new Date(d).toLocaleString() : "—";

  const formatCurrency = (cents: number) =>
    `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-loading">Loading...</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-page">
        <div className="admin-error">
          <h2>Access Denied</h2>
          <p>{error}</p>
          <button onClick={() => navigate("/")}>Back to Dashboard</button>
        </div>
        <style>{styles}</style>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-container">
        {/* Header */}
        <div className="admin-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Dashboard
          </button>
          <h1>Admin Panel</h1>
        </div>

        {/* Stats Widgets */}
        <div className="stats-grid">
          {/* Logins Last 24h */}
          <div className="stat-card">
            <div className="stat-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
                <path d="M12 6v6l4 2" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-value">{stats?.loginsLast24h || 0}</div>
              <div className="stat-label">Logins (24h)</div>
            </div>
          </div>

          {/* Live Users */}
          <div className="stat-card">
            <div className="stat-icon live">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <circle cx="12" cy="12" r="3" fill="currentColor" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-value">{stats?.liveUserCount || 0}</div>
              <div className="stat-label">Live Now</div>
            </div>
          </div>

          {/* Most Active */}
          <div className="stat-card wide">
            <div className="stat-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-label">Most Active Users</div>
              <div className="active-list">
                {stats?.mostActiveUsers?.map((u, i) => (
                  <span key={u.id} className="active-user">
                    {i + 1}. {u.display_name}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Live Users List */}
        {stats?.liveUsers && stats.liveUsers.length > 0 && (
          <div className="live-users-section">
            <h3>Currently Online</h3>
            <div className="live-users-list">
              {stats.liveUsers.map((u, i) => (
                <div key={i} className="live-user-tag">
                  <span className="live-dot" />
                  {u.displayName}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* User List */}
        <div className="users-section">
          <h2>All Users ({users.length})</h2>
          <div className="users-table-container">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Online</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Platform</th>
                  <th>Subscription</th>
                  <th>Admin</th>
                  <th>Last Login</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr
                    key={user.id}
                    className={selectedUser?.user.id === user.id ? "selected" : ""}
                    onClick={() => handleUserClick(user.id)}
                  >
                    <td className="online-status">
                      {user.is_online ? (
                        <span className="online-indicator">
                          <span className="online-dot" />
                        </span>
                      ) : (
                        <span className="offline-indicator">—</span>
                      )}
                    </td>
                    <td className="user-name">{user.display_name}</td>
                    <td>{user.email}</td>
                    <td>
                      <span className={`platform-badge ${user.issuer}`}>
                        {user.issuer === "fotw" ? "FOTW" : user.issuer}
                      </span>
                    </td>
                    <td>
                      {user.subscription_tier ? (
                        <span className="tier-badge">{user.subscription_tier}</span>
                      ) : (
                        <span className="no-tier">—</span>
                      )}
                    </td>
                    <td>
                      {user.is_admin ? (
                        <span className="admin-badge">Admin</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="last-login">{formatDate(user.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* User Detail Panel */}
        {selectedUser && (
          <div className="user-detail-panel">
            <div className="detail-header">
              <h2>{selectedUser.user.display_name}</h2>
              <button
                className="close-btn"
                onClick={() => setSelectedUser(null)}
              >
                ×
              </button>
            </div>

            <div className="detail-grid">
              <div className="detail-section">
                <h3>Profile</h3>
                <div className="detail-row">
                  <span className="label">Email</span>
                  <span className="value">{selectedUser.user.email}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Platform</span>
                  <span className="value">{selectedUser.user.issuer}</span>
                </div>
                <div className="detail-row">
                  <span className="label">WP User ID</span>
                  <span className="value">{selectedUser.user.wp_user_id}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Subscription</span>
                  <span className="value">
                    {selectedUser.user.subscription_tier || "None"}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="label">Roles</span>
                  <span className="value">
                    {selectedUser.user.roles.join(", ") || "None"}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="label">Admin</span>
                  <span className="value">
                    {selectedUser.user.is_admin ? "Yes" : "No"}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="label">Member Since</span>
                  <span className="value">
                    {formatDate(selectedUser.user.created_at)}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="label">Last Login</span>
                  <span className="value">
                    {formatDate(selectedUser.user.last_login_at)}
                  </span>
                </div>
              </div>

              <div className="detail-section">
                <h3>Trade Logs ({selectedUser.tradeLogs.length})</h3>
                {selectedUser.tradeLogs.length === 0 ? (
                  <p className="no-data">No trade logs</p>
                ) : (
                  <div className="trade-logs-list">
                    {selectedUser.tradeLogs.map((log) => (
                      <div key={log.id} className="trade-log-item">
                        <div className="log-name">{log.name}</div>
                        <div className="log-stats">
                          <span>Capital: {formatCurrency(log.starting_capital)}</span>
                          <span>Trades: {log.tradeCount}</span>
                          <span className={log.is_active ? "active" : "inactive"}>
                            {log.is_active ? "Active" : "Inactive"}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .admin-page {
    min-height: 100vh;
    background: #09090b;
    color: #f1f5f9;
    padding: 1.5rem;
  }

  .admin-container {
    max-width: 1400px;
    margin: 0 auto;
  }

  .admin-loading,
  .admin-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
    text-align: center;
  }

  .admin-error h2 {
    color: #f87171;
    margin-bottom: 0.5rem;
  }

  .admin-error button {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    border: none;
    border-radius: 0.5rem;
    color: white;
    cursor: pointer;
  }

  .admin-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .admin-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    background: linear-gradient(135deg, #7c3aed, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
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

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 1.25rem;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }

  .stat-card.wide {
    grid-column: span 2;
  }

  .stat-icon {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 0.5rem;
    background: rgba(99, 102, 241, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #818cf8;
    flex-shrink: 0;
  }

  .stat-icon.live {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  .stat-icon svg {
    width: 1.25rem;
    height: 1.25rem;
  }

  .stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: #f1f5f9;
    line-height: 1;
  }

  .stat-label {
    font-size: 0.8125rem;
    color: #71717a;
    margin-top: 0.25rem;
  }

  .active-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .active-user {
    font-size: 0.8125rem;
    color: #a1a1aa;
    background: rgba(255, 255, 255, 0.05);
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
  }

  /* Live Users */
  .live-users-section {
    margin-bottom: 1.5rem;
  }

  .live-users-section h3 {
    font-size: 0.875rem;
    color: #71717a;
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .live-users-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .live-user-tag {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.75rem;
    background: rgba(34, 197, 94, 0.1);
    border: 1px solid rgba(34, 197, 94, 0.2);
    border-radius: 9999px;
    font-size: 0.8125rem;
    color: #22c55e;
  }

  .live-dot {
    width: 0.5rem;
    height: 0.5rem;
    background: #22c55e;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  /* Users Table */
  .users-section {
    margin-bottom: 1.5rem;
  }

  .users-section h2 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0 0 1rem;
  }

  .users-table-container {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .users-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }

  .users-table th {
    text-align: left;
    padding: 0.875rem 1rem;
    background: rgba(255, 255, 255, 0.03);
    color: #71717a;
    font-weight: 500;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .users-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .users-table tr {
    cursor: pointer;
    transition: background 0.15s;
  }

  .users-table tr:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .users-table tr.selected {
    background: rgba(99, 102, 241, 0.1);
  }

  .user-name {
    font-weight: 500;
    color: #f1f5f9;
  }

  .online-status {
    text-align: center;
    width: 60px;
  }

  .online-indicator {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .online-dot {
    width: 0.5rem;
    height: 0.5rem;
    background: #22c55e;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
    animation: pulse 2s infinite;
  }

  .offline-indicator {
    color: #52525b;
  }

  .platform-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .platform-badge.fotw {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
  }

  .tier-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: rgba(34, 211, 238, 0.15);
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #22d3ee;
  }

  .no-tier {
    color: #52525b;
  }

  .admin-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.2), rgba(99, 102, 241, 0.2));
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #a78bfa;
    font-weight: 500;
  }

  .last-login {
    color: #71717a;
    font-size: 0.8125rem;
  }

  /* User Detail Panel */
  .user-detail-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 450px;
    background: #18181b;
    border-left: 1px solid rgba(255, 255, 255, 0.1);
    padding: 1.5rem;
    overflow-y: auto;
    z-index: 100;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
  }

  .detail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  .detail-header h2 {
    font-size: 1.25rem;
    margin: 0;
  }

  .close-btn {
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #71717a;
    font-size: 1.25rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .close-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #f1f5f9;
  }

  .detail-section {
    margin-bottom: 1.5rem;
  }

  .detail-section h3 {
    font-size: 0.875rem;
    color: #71717a;
    margin: 0 0 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 0.625rem 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .detail-row .label {
    color: #71717a;
    font-size: 0.875rem;
  }

  .detail-row .value {
    color: #e4e4e7;
    font-size: 0.875rem;
    text-align: right;
  }

  .no-data {
    color: #52525b;
    font-size: 0.875rem;
  }

  .trade-logs-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .trade-log-item {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0.5rem;
    padding: 0.75rem;
  }

  .log-name {
    font-weight: 500;
    margin-bottom: 0.375rem;
  }

  .log-stats {
    display: flex;
    gap: 1rem;
    font-size: 0.75rem;
    color: #71717a;
  }

  .log-stats .active {
    color: #22c55e;
  }

  .log-stats .inactive {
    color: #f87171;
  }

  @media (max-width: 768px) {
    .stat-card.wide {
      grid-column: span 1;
    }

    .user-detail-panel {
      width: 100%;
      left: 0;
    }
  }
`;
