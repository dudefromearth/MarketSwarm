// src/components/LeaderboardView.tsx
import { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  LeaderboardPeriod,
  LeaderboardScore,
  LeaderboardResponse,
} from '../types/leaderboard';
import LeaderboardSettingsModal from './LeaderboardSettingsModal';

const JOURNAL_API = '';
const PAGE_SIZE = 10;

interface LeaderboardViewProps {
  onClose: () => void;
}

export default function LeaderboardView({ onClose }: LeaderboardViewProps) {
  const [period, setPeriod] = useState<LeaderboardPeriod>('weekly');
  const [rankings, setRankings] = useState<LeaderboardScore[]>([]);
  const [currentUserRank, setCurrentUserRank] = useState<LeaderboardScore | null>(null);
  const [totalParticipants, setTotalParticipants] = useState(0);
  const [periodKey, setPeriodKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const filteredRankings = useMemo(() => {
    if (!searchQuery.trim()) return rankings;
    const q = searchQuery.toLowerCase();
    return rankings.filter(s =>
      (s.displayName || `User #${s.user_id}`).toLowerCase().includes(q)
    );
  }, [rankings, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredRankings.length / PAGE_SIZE));
  const paginatedRankings = filteredRankings.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const fetchLeaderboard = useCallback(async (selectedPeriod: LeaderboardPeriod) => {
    try {
      setLoading(true);
      setError(null);

      const res = await fetch(
        `${JOURNAL_API}/api/leaderboard?period=${selectedPeriod}&limit=200`,
        { credentials: 'include' }
      );

      if (!res.ok) {
        throw new Error('Failed to fetch leaderboard');
      }

      const data: LeaderboardResponse = await res.json();
      if (data.success) {
        setRankings(data.data.rankings);
        setCurrentUserRank(data.data.currentUserRank);
        setTotalParticipants(data.data.totalParticipants);
        setPeriodKey(data.data.periodKey);
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
      setError('Failed to load leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeaderboard(period);
  }, [period, fetchLeaderboard]);

  // Reset page when period or search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [period, searchQuery]);

  const handleRefresh = () => {
    fetchLeaderboard(period);
  };

  const formatPnl = (pnl: number): string => {
    const dollars = pnl / 100;
    const sign = dollars >= 0 ? '+' : '';
    return `${sign}$${dollars.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const getPeriodLabel = (pt: LeaderboardPeriod, key: string): string => {
    if (pt === 'weekly') {
      // Parse 2026-W06 format
      return `Week ${key.split('-W')[1]}, ${key.split('-W')[0]}`;
    } else if (pt === 'monthly') {
      // Parse 2026-02 format
      const [year, month] = key.split('-');
      const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return `${monthNames[parseInt(month) - 1]} ${year}`;
    }
    return 'All Time';
  };

  const getRankBadge = (rank: number): string => {
    if (rank === 1) return '🥇';
    if (rank === 2) return '🥈';
    if (rank === 3) return '🥉';
    return `#${rank}`;
  };

  const isCurrentUser = (score: LeaderboardScore): boolean => {
    return currentUserRank?.user_id === score.user_id;
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content leaderboard-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Leaderboard</h2>
          <div className="header-actions">
            <button
              className="btn-icon"
              onClick={() => setShowSettings(true)}
              title="Leaderboard Settings"
            >
              ⚙️
            </button>
            <button
              className="btn-icon"
              onClick={handleRefresh}
              disabled={loading}
              title="Refresh"
            >
              🔄
            </button>
            <button className="modal-close" onClick={onClose}>&times;</button>
          </div>
        </div>

        <div className="leaderboard-tabs">
          <button
            className={`tab-btn ${period === 'weekly' ? 'active' : ''}`}
            onClick={() => setPeriod('weekly')}
          >
            Weekly
          </button>
          <button
            className={`tab-btn ${period === 'monthly' ? 'active' : ''}`}
            onClick={() => setPeriod('monthly')}
          >
            Monthly
          </button>
          <button
            className={`tab-btn ${period === 'all_time' ? 'active' : ''}`}
            onClick={() => setPeriod('all_time')}
          >
            All-Time
          </button>
        </div>

        <div className="period-info">
          <span className="period-label">{getPeriodLabel(period, periodKey)}</span>
          <span className="participant-count">{totalParticipants} participants</span>
        </div>

        <div className="leaderboard-search">
          <input
            type="text"
            className="leaderboard-search-input"
            placeholder="Search by name..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="leaderboard-search-clear" onClick={() => setSearchQuery('')}>
              &times;
            </button>
          )}
        </div>

        <div className="modal-body leaderboard-body">
          {loading ? (
            <div className="loading-state">Loading rankings...</div>
          ) : error ? (
            <div className="error-state">{error}</div>
          ) : rankings.length === 0 ? (
            <div className="empty-state">
              <p>No rankings yet for this period.</p>
              <p className="hint">Log trades, write journal entries, and use tags to earn points!</p>
            </div>
          ) : filteredRankings.length === 0 ? (
            <div className="empty-state">
              <p>No results for "{searchQuery}"</p>
            </div>
          ) : (
            <>
              <table className="leaderboard-table">
                <thead>
                  <tr>
                    <th className="col-rank">Rank</th>
                    <th className="col-user">User</th>
                    <th className="col-score">Total</th>
                    <th className="col-activity">Activity</th>
                    <th className="col-performance">Performance</th>
                    <th className="col-stats">Stats</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedRankings.map((score) => (
                    <tr
                      key={score.user_id}
                      className={isCurrentUser(score) ? 'current-user-row' : ''}
                    >
                      <td className="col-rank">
                        <span className="rank-badge">{getRankBadge(score.rank)}</span>
                      </td>
                      <td className="col-user">
                        <span className="user-name">
                          {score.displayName || `User #${score.user_id}`}
                        </span>
                        {isCurrentUser(score) && <span className="you-badge">You</span>}
                      </td>
                      <td className="col-score">
                        <span className="total-score">{score.total_score.toFixed(1)}</span>
                      </td>
                      <td className="col-activity">
                        <div className="score-breakdown">
                          <span className="score-value">{score.activity_score.toFixed(1)}</span>
                          <span className="score-detail">
                            {score.trades_logged}T / {score.journal_entries}J / {score.tags_used}🏷️
                          </span>
                        </div>
                      </td>
                      <td className="col-performance">
                        <div className="score-breakdown">
                          <span className="score-value">{score.performance_score.toFixed(1)}</span>
                          <span className="score-detail">
                            {score.win_rate.toFixed(0)}% / {score.avg_r_multiple.toFixed(2)}R
                          </span>
                        </div>
                      </td>
                      <td className="col-stats">
                        <span className={`pnl-value ${score.total_pnl >= 0 ? 'positive' : 'negative'}`}>
                          {formatPnl(score.total_pnl)}
                        </span>
                        <span className="trades-count">{score.closed_trades} closed</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Sticky current user row if not visible on current page */}
              {currentUserRank && !paginatedRankings.some(r => r.user_id === currentUserRank.user_id) && !searchQuery && (
                <div className="sticky-user-row">
                  <div className="sticky-separator">...</div>
                  <table className="leaderboard-table">
                    <tbody>
                      <tr className="current-user-row">
                        <td className="col-rank">
                          <span className="rank-badge">#{currentUserRank.rank}</span>
                        </td>
                        <td className="col-user">
                          <span className="user-name">You</span>
                        </td>
                        <td className="col-score">
                          <span className="total-score">{currentUserRank.total_score.toFixed(1)}</span>
                        </td>
                        <td className="col-activity">
                          <div className="score-breakdown">
                            <span className="score-value">{currentUserRank.activity_score.toFixed(1)}</span>
                            <span className="score-detail">
                              {currentUserRank.trades_logged}T / {currentUserRank.journal_entries}J / {currentUserRank.tags_used}🏷️
                            </span>
                          </div>
                        </td>
                        <td className="col-performance">
                          <div className="score-breakdown">
                            <span className="score-value">{currentUserRank.performance_score.toFixed(1)}</span>
                            <span className="score-detail">
                              {currentUserRank.win_rate.toFixed(0)}% / {currentUserRank.avg_r_multiple.toFixed(2)}R
                            </span>
                          </div>
                        </td>
                        <td className="col-stats">
                          <span className={`pnl-value ${currentUserRank.total_pnl >= 0 ? 'positive' : 'negative'}`}>
                            {formatPnl(currentUserRank.total_pnl)}
                          </span>
                          <span className="trades-count">{currentUserRank.closed_trades} closed</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        <div className="leaderboard-footer">
          {totalPages > 1 && (
            <div className="leaderboard-pagination">
              <button
                className="pagination-btn"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage(p => p - 1)}
              >
                Prev
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                <button
                  key={page}
                  className={`pagination-btn ${page === currentPage ? 'active' : ''}`}
                  onClick={() => setCurrentPage(page)}
                >
                  {page}
                </button>
              ))}
              <button
                className="pagination-btn"
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
          <div className="scoring-info">
            <span className="info-label">Scoring:</span>
            <span className="info-item">Activity (0-50) + Performance (0-50) = Total (0-100)</span>
            {searchQuery && (
              <span className="info-item search-count">
                {filteredRankings.length} of {rankings.length} shown
              </span>
            )}
          </div>
        </div>
      </div>

      {showSettings && (
        <LeaderboardSettingsModal
          onClose={() => setShowSettings(false)}
          onSaved={() => fetchLeaderboard(period)}
        />
      )}
    </div>
  );
}
