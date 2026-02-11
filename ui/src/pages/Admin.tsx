// ui/src/pages/Admin.tsx
import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import PeakUsageChart from "../components/PeakUsageChart";
import ActivityHeatmap from "../components/ActivityHeatmap";

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

interface Trade {
  id: string;
  symbol: string;
  strategy: string;
  side: string;
  strike: number;
  width: number | null;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  pnl: number | null;
  r_multiple: number | null;
  status: string;
  entry_time: string;
  exit_time: string | null;
  log_name: string;
}

interface PerformanceStats {
  summary: {
    totalTrades: number;
    closedTrades: number;
    openTrades: number;
    totalPnl: number;
    winRate: number;
    profitFactor: number;
    avgWin: number;
    avgLoss: number;
    winners: number;
    losers: number;
    breakeven: number;
  };
  strategyStats: Record<string, { count: number; pnl: number; wins: number }>;
  recentTrades: {
    id: string;
    symbol: string;
    strategy: string;
    side: string;
    pnl: number | null;
    rMultiple: number | null;
    status: string;
    entryTime: string;
    exitTime: string | null;
  }[];
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

  // Search, pagination, and sorting
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(15);
  const [sortColumn, setSortColumn] = useState<keyof User | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // User performance
  const [performance, setPerformance] = useState<PerformanceStats | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);

  // User trades (expanded view)
  const [userTrades, setUserTrades] = useState<Trade[]>([]);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesTotalPages, setTradesTotalPages] = useState(1);

  // User activity heatmap
  const [userActivity, setUserActivity] = useState<{
    heatmapData: [number, number, number][];
    totalActiveTime: { hours: number; minutes: number; formatted: string };
  } | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);


  // Handle column sort
  const handleSort = (column: keyof User) => {
    if (sortColumn === column) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  // Filtered and sorted users
  const filteredUsers = useMemo(() => {
    let result = users;

    // Apply search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(u =>
        u.display_name?.toLowerCase().includes(q) ||
        u.email?.toLowerCase().includes(q) ||
        u.subscription_tier?.toLowerCase().includes(q)
      );
    }

    // Apply sorting
    if (sortColumn) {
      result = [...result].sort((a, b) => {
        let aVal = a[sortColumn];
        let bVal = b[sortColumn];

        // Handle null/undefined
        if (aVal === null || aVal === undefined) aVal = '';
        if (bVal === null || bVal === undefined) bVal = '';

        // Handle booleans
        if (typeof aVal === 'boolean') aVal = aVal ? 1 : 0;
        if (typeof bVal === 'boolean') bVal = bVal ? 1 : 0;

        // Handle dates
        if (sortColumn === 'last_login_at' || sortColumn === 'created_at') {
          aVal = aVal ? new Date(aVal as string).getTime() : 0;
          bVal = bVal ? new Date(bVal as string).getTime() : 0;
        }

        // Compare
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          return sortDirection === 'asc'
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
        }

        if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }

    return result;
  }, [users, searchQuery, sortColumn, sortDirection]);

  const totalPages = Math.ceil(filteredUsers.length / pageSize);
  const paginatedUsers = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredUsers.slice(start, start + pageSize);
  }, [filteredUsers, currentPage, pageSize]);

  // Reset page when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

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
      setPerformance(null);
      setUserTrades([]);
      setTradesPage(1);
      setUserActivity(null);

      // Fetch performance stats, trades, and activity
      fetchUserPerformance(userId);
      fetchUserTrades(userId, 1);
      fetchUserActivity(userId);
    } catch (e) {
      console.error("Error loading user detail:", e);
    }
  };

  const fetchUserPerformance = async (userId: number) => {
    setPerformanceLoading(true);
    try {
      const res = await fetch(`/api/admin/users/${userId}/performance`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setPerformance(data);
      }
    } catch (e) {
      console.error("Error loading performance:", e);
    } finally {
      setPerformanceLoading(false);
    }
  };

  const fetchUserTrades = async (userId: number, page: number) => {
    setTradesLoading(true);
    try {
      const res = await fetch(`/api/admin/users/${userId}/trades?page=${page}&limit=10`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setUserTrades(data.trades);
        setTradesTotalPages(data.pagination.totalPages);
        setTradesPage(page);
      }
    } catch (e) {
      console.error("Error loading trades:", e);
    } finally {
      setTradesLoading(false);
    }
  };

  const fetchUserActivity = async (userId: number) => {
    setActivityLoading(true);
    try {
      const res = await fetch(`/api/admin/users/${userId}/activity?days=30`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setUserActivity({
          heatmapData: data.heatmapData,
          totalActiveTime: data.totalActiveTime,
        });
      }
    } catch (e) {
      console.error("Error loading user activity:", e);
    } finally {
      setActivityLoading(false);
    }
  };

  const formatDate = (d: string) =>
    d ? new Date(d).toLocaleString() : "—";

  const formatCurrency = (cents: number) =>
    `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

  const formatPnL = (cents: number | null) => {
    if (cents === null) return "—";
    const dollars = cents / 100;
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

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
          <div className="header-left">
            <button className="back-btn" onClick={() => navigate("/")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Dashboard
            </button>
            <h1>Admin Panel</h1>
          </div>
          <div className="header-nav">
            <button className="nav-btn" onClick={() => navigate("/admin/vexy")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              Vexy
            </button>
            <button className="nav-btn" onClick={() => navigate("/admin/ml-lab")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
              ML Lab
            </button>
            <button className="nav-btn" onClick={() => navigate("/admin/vp-editor")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 15h18M9 3v18" />
              </svg>
              VP Editor
            </button>
            <button className="nav-btn" onClick={() => navigate("/admin/economic-indicators")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 3v18h18" />
                <path d="M18 17V9M13 17V5M8 17v-3" />
              </svg>
              Indicators
            </button>
            <button className="nav-btn" onClick={() => navigate("/admin/rss-intel")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 11a9 9 0 0 1 9 9" />
                <path d="M4 4a16 16 0 0 1 16 16" />
                <circle cx="5" cy="19" r="1" />
              </svg>
              RSS Intel
            </button>
          </div>
        </div>

        {/* Stats Widgets */}
        <div className="stats-grid">
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

          <div className="stat-card">
            <div className="stat-icon users">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-value">{users.length}</div>
              <div className="stat-label">Total Users</div>
            </div>
          </div>

          <div className="stat-card wide">
            <div className="stat-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
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

        {/* Peak Usage Chart */}
        <PeakUsageChart days={7} />

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

        {/* User List with Search and Pagination */}
        <div className="users-section">
          <div className="users-header">
            <h2>All Users ({filteredUsers.length})</h2>
            <div className="search-box">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              <input
                type="text"
                placeholder="Search by name, email, or tier..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button className="clear-search" onClick={() => setSearchQuery("")}>×</button>
              )}
            </div>
          </div>

          <div className="users-table-container">
            <table className="users-table">
              <thead>
                <tr>
                  <th className="sortable" onClick={() => handleSort('is_online')}>
                    Online {sortColumn === 'is_online' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('display_name')}>
                    Name {sortColumn === 'display_name' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('email')}>
                    Email {sortColumn === 'email' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('issuer')}>
                    Platform {sortColumn === 'issuer' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('subscription_tier')}>
                    Subscription {sortColumn === 'subscription_tier' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('is_admin')}>
                    Admin {sortColumn === 'is_admin' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                  <th className="sortable" onClick={() => handleSort('last_login_at')}>
                    Last Login {sortColumn === 'last_login_at' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginatedUsers.map((user) => (
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
                        {user.issuer === "fotw" ? "FOTW" : user.issuer === "0-dte" ? "0DTE" : user.issuer}
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

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="page-btn"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(1)}
              >
                ««
              </button>
              <button
                className="page-btn"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(p => p - 1)}
              >
                «
              </button>
              <div className="page-info">
                Page {currentPage} of {totalPages}
              </div>
              <button
                className="page-btn"
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(p => p + 1)}
              >
                »
              </button>
              <button
                className="page-btn"
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(totalPages)}
              >
                »»
              </button>
            </div>
          )}
        </div>

        {/* User Detail Panel - Enhanced */}
        {selectedUser && (
          <div className="user-detail-panel">
            <div className="detail-header">
              <div className="user-avatar">
                {selectedUser.user.display_name?.charAt(0).toUpperCase() || "?"}
              </div>
              <div className="user-header-info">
                <h2>{selectedUser.user.display_name}</h2>
                <span className="user-email">{selectedUser.user.email}</span>
              </div>
              <button className="close-btn" onClick={() => setSelectedUser(null)}>×</button>
            </div>

            {/* Performance Widget */}
            {performanceLoading ? (
              <div className="performance-loading">Loading performance...</div>
            ) : performance ? (
              <div className="performance-widget">
                <h3>Trading Performance</h3>
                <div className="perf-grid">
                  <div className="perf-stat main">
                    <span className={`perf-value ${performance.summary.totalPnl >= 0 ? 'profit' : 'loss'}`}>
                      {formatPnL(performance.summary.totalPnl)}
                    </span>
                    <span className="perf-label">Total P&L</span>
                  </div>
                  <div className="perf-stat">
                    <span className="perf-value">{performance.summary.winRate}%</span>
                    <span className="perf-label">Win Rate</span>
                  </div>
                  <div className="perf-stat">
                    <span className="perf-value">{performance.summary.profitFactor}x</span>
                    <span className="perf-label">Profit Factor</span>
                  </div>
                  <div className="perf-stat">
                    <span className="perf-value">{performance.summary.totalTrades}</span>
                    <span className="perf-label">Total Trades</span>
                  </div>
                </div>

                <div className="perf-breakdown">
                  <div className="breakdown-row">
                    <span className="breakdown-label">Winners</span>
                    <span className="breakdown-value win">{performance.summary.winners}</span>
                    <span className="breakdown-avg">Avg: {formatCurrency(performance.summary.avgWin)}</span>
                  </div>
                  <div className="breakdown-row">
                    <span className="breakdown-label">Losers</span>
                    <span className="breakdown-value loss">{performance.summary.losers}</span>
                    <span className="breakdown-avg">Avg: {formatCurrency(performance.summary.avgLoss)}</span>
                  </div>
                  <div className="breakdown-row">
                    <span className="breakdown-label">Open</span>
                    <span className="breakdown-value">{performance.summary.openTrades}</span>
                  </div>
                </div>

                {/* Strategy Breakdown */}
                {Object.keys(performance.strategyStats).length > 0 && (
                  <div className="strategy-breakdown">
                    <h4>By Strategy</h4>
                    <div className="strategy-list">
                      {Object.entries(performance.strategyStats).map(([strategy, stats]) => (
                        <div key={strategy} className="strategy-item">
                          <span className="strategy-name">{strategy}</span>
                          <span className="strategy-count">{stats.count} trades</span>
                          <span className={`strategy-pnl ${stats.pnl >= 0 ? 'profit' : 'loss'}`}>
                            {formatPnL(stats.pnl)}
                          </span>
                          <span className="strategy-winrate">
                            {Math.round(stats.wins / stats.count * 100)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="no-performance">No trading data available</div>
            )}

            {/* Activity Heatmap */}
            <div className="detail-section">
              <h3>Activity Pattern (30 Days)</h3>
              {activityLoading ? (
                <div className="activity-loading">Loading activity data...</div>
              ) : userActivity && userActivity.heatmapData.some(d => d[2] > 0) ? (
                <ActivityHeatmap
                  data={userActivity.heatmapData}
                  totalActiveTime={userActivity.totalActiveTime}
                />
              ) : (
                <div className="no-activity">No activity data recorded yet</div>
              )}
            </div>

            {/* Profile Info */}
            <div className="detail-section">
              <h3>Profile</h3>
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
                <span className="value">{selectedUser.user.subscription_tier || "None"}</span>
              </div>
              <div className="detail-row">
                <span className="label">Roles</span>
                <span className="value">{selectedUser.user.roles.join(", ") || "None"}</span>
              </div>
              <div className="detail-row">
                <span className="label">Admin</span>
                <span className="value">{selectedUser.user.is_admin ? "Yes" : "No"}</span>
              </div>
              <div className="detail-row">
                <span className="label">Member Since</span>
                <span className="value">{formatDate(selectedUser.user.created_at)}</span>
              </div>
            </div>

            {/* Trade Logs */}
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

            {/* Recent Trades - Expanded View */}
            <div className="detail-section trades-section">
              <h3>Recent Trades</h3>
              {tradesLoading ? (
                <div className="trades-loading">Loading trades...</div>
              ) : userTrades.length === 0 ? (
                <p className="no-data">No trades recorded</p>
              ) : (
                <>
                  <div className="trades-list">
                    {userTrades.map((trade) => (
                      <div key={trade.id} className={`trade-item ${trade.status}`}>
                        <div className="trade-main">
                          <span className={`trade-side ${trade.side}`}>
                            {trade.side?.toUpperCase()}
                          </span>
                          <span className="trade-symbol">{trade.symbol}</span>
                          <span className="trade-strategy">{trade.strategy}</span>
                          <span className="trade-strike">{trade.strike}{trade.width ? `/${trade.width}` : ''}</span>
                        </div>
                        <div className="trade-details">
                          <span className="trade-qty">x{trade.quantity}</span>
                          <span className="trade-entry">@ ${(trade.entry_price / 100).toFixed(2)}</span>
                          {trade.exit_price && (
                            <span className="trade-exit">→ ${(trade.exit_price / 100).toFixed(2)}</span>
                          )}
                        </div>
                        <div className="trade-result">
                          {trade.pnl !== null ? (
                            <span className={`trade-pnl ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                              {formatPnL(trade.pnl)}
                            </span>
                          ) : (
                            <span className="trade-status-badge">{trade.status}</span>
                          )}
                          {trade.r_multiple !== null && (
                            <span className="trade-r">{Number(trade.r_multiple).toFixed(2)}R</span>
                          )}
                        </div>
                        <div className="trade-time">
                          {new Date(trade.entry_time).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Trades Pagination */}
                  {tradesTotalPages > 1 && (
                    <div className="trades-pagination">
                      <button
                        disabled={tradesPage === 1}
                        onClick={() => fetchUserTrades(selectedUser.user.id, tradesPage - 1)}
                      >
                        ← Prev
                      </button>
                      <span>{tradesPage} / {tradesTotalPages}</span>
                      <button
                        disabled={tradesPage === tradesTotalPages}
                        onClick={() => fetchUserTrades(selectedUser.user.id, tradesPage + 1)}
                      >
                        Next →
                      </button>
                    </div>
                  )}
                </>
              )}
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
    background: var(--bg-base);
    color: var(--text-primary);
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

  .admin-error h2 { color: #f87171; margin-bottom: 0.5rem; }
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
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .header-nav {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .nav-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: rgba(124, 58, 237, 0.15);
    border: 1px solid rgba(124, 58, 237, 0.3);
    border-radius: 0.5rem;
    color: #a78bfa;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .nav-btn:hover {
    background: rgba(124, 58, 237, 0.25);
    color: #c4b5fd;
  }

  .nav-btn svg {
    width: 1rem;
    height: 1rem;
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
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .back-btn:hover { background: var(--bg-hover); color: var(--text-bright); }
  .back-btn svg { width: 1rem; height: 1rem; }

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1.25rem;
    display: flex;
    align-items: flex-start;
    gap: 1rem;
  }

  .stat-card.wide { grid-column: span 2; }

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

  .stat-icon.live { background: rgba(34, 197, 94, 0.15); color: #22c55e; animation: pulse 2s infinite; }
  .stat-icon.users { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
  .stat-icon svg { width: 1.25rem; height: 1.25rem; }

  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

  .stat-value { font-size: 2rem; font-weight: 700; color: var(--text-primary); line-height: 1; }
  .stat-label { font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.25rem; }

  .active-list { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
  .active-user {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    background: var(--bg-hover);
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
  }

  /* Live Users */
  .live-users-section { margin-bottom: 1.5rem; }
  .live-users-section h3 {
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .live-users-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
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

  /* Users Section with Search */
  .users-section { margin-bottom: 1.5rem; }

  .users-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .users-header h2 { font-size: 1.125rem; font-weight: 600; margin: 0; }

  .search-box {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    min-width: 280px;
  }

  .search-box svg { width: 1rem; height: 1rem; color: var(--text-secondary); flex-shrink: 0; }

  .search-box input {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-primary);
    font-size: 0.875rem;
    outline: none;
  }

  .search-box input::placeholder { color: var(--text-muted); }

  .clear-search {
    background: none;
    border: none;
    color: var(--text-secondary);
    font-size: 1.25rem;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }

  .clear-search:hover { color: var(--text-primary); }

  /* Users Table */
  .users-table-container {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .users-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }

  .users-table th {
    text-align: left;
    padding: 0.875rem 1rem;
    background: var(--bg-surface-alt);
    color: var(--text-secondary);
    font-weight: 500;
    border-bottom: 1px solid var(--border-subtle);
  }

  .users-table th.sortable {
    cursor: pointer;
    user-select: none;
    transition: all 0.15s;
  }

  .users-table th.sortable:hover {
    background: var(--bg-hover);
    color: var(--text-secondary);
  }

  .sort-arrow {
    margin-left: 0.375rem;
    font-size: 0.625rem;
    color: #60a5fa;
  }

  .users-table td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-subtle); }
  .users-table tr { cursor: pointer; transition: background 0.15s; }
  .users-table tr:hover { background: var(--bg-hover); }
  .users-table tr.selected { background: rgba(99, 102, 241, 0.1); }

  .user-name { font-weight: 500; color: var(--text-primary); }
  .online-status { text-align: center; width: 60px; }

  .online-indicator { display: inline-flex; align-items: center; justify-content: center; }
  .online-dot {
    width: 0.5rem;
    height: 0.5rem;
    background: #22c55e;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.6);
    animation: pulse 2s infinite;
  }

  .offline-indicator { color: var(--text-muted); }

  .platform-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .platform-badge.fotw { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
  .platform-badge.0-dte { background: rgba(168, 85, 247, 0.15); color: #c084fc; }

  .tier-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: rgba(34, 211, 238, 0.15);
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #22d3ee;
  }

  .no-tier { color: var(--text-muted); }

  .admin-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.2), rgba(99, 102, 241, 0.2));
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #a78bfa;
    font-weight: 500;
  }

  .last-login { color: var(--text-secondary); font-size: 0.8125rem; }

  /* Pagination */
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 1rem;
    padding: 0.75rem;
  }

  .page-btn {
    padding: 0.375rem 0.75rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .page-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
  .page-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .page-info { font-size: 0.875rem; color: var(--text-secondary); padding: 0 0.5rem; }

  /* User Detail Panel - Enhanced */
  .user-detail-panel {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 520px;
    background: var(--bg-raised);
    border-left: 1px solid var(--border-default);
    padding: 1.5rem;
    overflow-y: auto;
    z-index: 100;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
  }

  .detail-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .user-avatar {
    width: 3rem;
    height: 3rem;
    border-radius: 50%;
    background: linear-gradient(135deg, #7c3aed, #6366f1);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
    font-weight: 600;
    color: white;
    flex-shrink: 0;
  }

  .user-header-info { flex: 1; }
  .user-header-info h2 { font-size: 1.25rem; margin: 0; }
  .user-email { font-size: 0.8125rem; color: var(--text-secondary); }

  .close-btn {
    width: 2rem;
    height: 2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-secondary);
    font-size: 1.25rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

  /* Performance Widget */
  .performance-widget {
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .performance-widget h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .perf-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .perf-stat {
    text-align: center;
    padding: 0.75rem 0.5rem;
    background: var(--bg-surface);
    border-radius: 0.5rem;
  }

  .perf-stat.main {
    grid-column: span 2;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(124, 58, 237, 0.1));
    border: 1px solid rgba(99, 102, 241, 0.2);
  }

  .perf-value { display: block; font-size: 1.25rem; font-weight: 700; color: var(--text-primary); }
  .perf-stat.main .perf-value { font-size: 1.5rem; }
  .perf-value.profit { color: #22c55e; }
  .perf-value.loss { color: #ef4444; }
  .perf-label { display: block; font-size: 0.6875rem; color: var(--text-secondary); margin-top: 0.25rem; }

  .perf-breakdown { border-top: 1px solid var(--border-subtle); padding-top: 0.75rem; }

  .breakdown-row {
    display: flex;
    align-items: center;
    padding: 0.375rem 0;
    font-size: 0.8125rem;
  }

  .breakdown-label { flex: 1; color: var(--text-secondary); }
  .breakdown-value { width: 3rem; font-weight: 600; }
  .breakdown-value.win { color: #22c55e; }
  .breakdown-value.loss { color: #ef4444; }
  .breakdown-avg { color: var(--text-muted); font-size: 0.75rem; }

  .strategy-breakdown { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border-subtle); }
  .strategy-breakdown h4 {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    margin: 0 0 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .strategy-list { display: flex; flex-direction: column; gap: 0.375rem; }

  .strategy-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.375rem 0.5rem;
    background: var(--bg-surface);
    border-radius: 0.375rem;
    font-size: 0.75rem;
  }

  .strategy-name { flex: 1; color: var(--text-bright); text-transform: capitalize; }
  .strategy-count { color: var(--text-secondary); }
  .strategy-pnl { font-weight: 600; width: 4rem; text-align: right; }
  .strategy-pnl.profit { color: #22c55e; }
  .strategy-pnl.loss { color: #ef4444; }
  .strategy-winrate { color: #60a5fa; width: 2.5rem; text-align: right; }

  .performance-loading, .no-performance {
    padding: 2rem;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .activity-loading, .no-activity {
    padding: 1.5rem;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.875rem;
    background: var(--bg-surface);
    border-radius: 0.5rem;
  }

  /* Detail Section */
  .detail-section { margin-bottom: 1.5rem; }

  .detail-section h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 0.8125rem;
  }

  .detail-row .label { color: var(--text-secondary); }
  .detail-row .value { color: var(--text-bright); text-align: right; }

  .no-data { color: var(--text-muted); font-size: 0.875rem; }

  .trade-logs-list { display: flex; flex-direction: column; gap: 0.5rem; }

  .trade-log-item {
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    padding: 0.75rem;
  }

  .log-name { font-weight: 500; margin-bottom: 0.25rem; font-size: 0.875rem; }
  .log-stats { display: flex; gap: 1rem; font-size: 0.75rem; color: var(--text-secondary); }
  .log-stats .active { color: #22c55e; }
  .log-stats .inactive { color: #f87171; }

  /* Trades Section */
  .trades-section { max-height: 400px; overflow-y: auto; }
  .trades-loading { padding: 1rem; text-align: center; color: var(--text-secondary); }
  .trades-list { display: flex; flex-direction: column; gap: 0.5rem; }

  .trade-item {
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    padding: 0.75rem;
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    gap: 0.75rem;
    align-items: center;
    font-size: 0.8125rem;
  }

  .trade-item.open { border-left: 3px solid #60a5fa; }
  .trade-item.closed { border-left: 3px solid #22c55e; }

  .trade-main { display: flex; align-items: center; gap: 0.5rem; }
  .trade-side { font-weight: 600; font-size: 0.6875rem; padding: 0.125rem 0.375rem; border-radius: 0.25rem; }
  .trade-side.call { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
  .trade-side.put { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

  .trade-symbol { font-weight: 600; color: var(--text-primary); }
  .trade-strategy { color: var(--text-secondary); text-transform: capitalize; }
  .trade-strike { color: var(--text-secondary); }

  .trade-details { display: flex; gap: 0.5rem; color: var(--text-secondary); font-size: 0.75rem; }

  .trade-result { text-align: right; }
  .trade-pnl { font-weight: 600; }
  .trade-pnl.profit { color: #22c55e; }
  .trade-pnl.loss { color: #ef4444; }
  .trade-r { font-size: 0.6875rem; color: var(--text-secondary); margin-left: 0.25rem; }
  .trade-status-badge { font-size: 0.6875rem; color: #60a5fa; text-transform: uppercase; }

  .trade-time { color: var(--text-muted); font-size: 0.75rem; text-align: right; }

  .trades-pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
  }

  .trades-pagination button {
    padding: 0.25rem 0.5rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.25rem;
    color: var(--text-secondary);
    font-size: 0.75rem;
    cursor: pointer;
  }

  .trades-pagination button:hover:not(:disabled) { background: var(--bg-hover); }
  .trades-pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
  .trades-pagination span { font-size: 0.75rem; color: var(--text-secondary); }

  /* Diagnostics */
  .diagnostics-section {
    margin-top: 2rem;
    padding-top: 2rem;
    border-top: 1px solid var(--border-subtle);
  }

  .section-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
  }

  .section-header-row h2 { font-size: 1.125rem; font-weight: 600; margin: 0; }

  .refresh-btn {
    padding: 0.5rem 1rem;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.5rem;
    color: #60a5fa;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .refresh-btn:hover:not(:disabled) { background: rgba(59, 130, 246, 0.25); }
  .refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .diagnostics-content { display: flex; flex-direction: column; gap: 1rem; }

  .diag-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    padding: 1rem;
  }

  .diag-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: var(--text-secondary);
    margin-bottom: 0.5rem;
  }

  .status-dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; }
  .status-dot.ok { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
  .status-dot.error { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); }

  .diag-value { font-size: 1rem; color: var(--text-primary); }

  .data-availability {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1rem;
  }

  .data-availability h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .diag-table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
  .diag-table th {
    text-align: left;
    padding: 0.5rem;
    color: var(--text-secondary);
    font-weight: 500;
    border-bottom: 1px solid var(--border-subtle);
  }
  .diag-table td { padding: 0.5rem; border-bottom: 1px solid var(--border-subtle); }
  .symbol-cell { font-weight: 600; color: var(--text-primary); }

  .data-status { display: flex; align-items: center; gap: 0.375rem; }
  .data-status.ok .status-icon { color: #22c55e; }
  .data-status.missing .status-icon { color: #ef4444; }
  .status-detail { font-size: 0.75rem; color: var(--text-secondary); }

  /* Redis Explorer */
  .redis-explorer {
    margin-top: 1.5rem;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1rem;
  }

  .redis-explorer h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .redis-search { display: flex; gap: 0.5rem; margin-bottom: 1rem; }

  .redis-search input {
    flex: 1;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.875rem;
    font-family: 'SF Mono', monospace;
  }

  .redis-search input:focus { outline: none; border-color: rgba(59, 130, 246, 0.5); }

  .redis-search button {
    padding: 0.5rem 1rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .redis-search button:hover { background: var(--bg-hover); color: var(--text-primary); }

  .redis-results { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; max-height: 400px; }

  .redis-keys-list {
    overflow-y: auto;
    max-height: 400px;
    border: 1px solid var(--border-subtle);
    border-radius: 0.375rem;
  }

  .redis-key-item {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: background 0.15s;
  }

  .redis-key-item:hover { background: var(--bg-hover); }
  .redis-key-item.selected { background: rgba(59, 130, 246, 0.15); }

  .key-name {
    display: block;
    font-family: 'SF Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-primary);
    word-break: break-all;
  }

  .key-meta { display: block; font-size: 0.6875rem; color: var(--text-muted); margin-top: 0.25rem; }

  .redis-value-panel {
    border: 1px solid var(--border-subtle);
    border-radius: 0.375rem;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .value-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-bottom: 1px solid var(--border-subtle);
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .value-header button {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 1rem;
    padding: 0;
    line-height: 1;
  }

  .value-header button:hover { color: var(--text-primary); }

  .value-content {
    flex: 1;
    overflow: auto;
    padding: 0.75rem;
    margin: 0;
    font-family: 'SF Mono', monospace;
    font-size: 0.6875rem;
    line-height: 1.5;
    color: var(--text-secondary);
    background: var(--bg-surface);
    max-height: 350px;
  }

  @media (max-width: 768px) {
    .stat-card.wide { grid-column: span 1; }
    .user-detail-panel { width: 100%; left: 0; }
    .perf-grid { grid-template-columns: repeat(2, 1fr); }
    .perf-stat.main { grid-column: span 2; }
  }
`;
