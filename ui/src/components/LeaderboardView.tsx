// src/components/LeaderboardView.tsx
import { useState, useEffect, useCallback, useMemo } from 'react';
import type { AFIScore, AFILeaderboardResponse } from '../types/afi';
import { getAFITier, getPrimaryScore } from '../types/afi';
import LeaderboardSettingsModal from './LeaderboardSettingsModal';

const JOURNAL_API = '';
const PAGE_SIZE = 10;

interface LeaderboardViewProps {
  onClose: () => void;
}

const TREND_ARROWS: Record<string, { symbol: string; className: string }> = {
  improving: { symbol: '\u2191', className: 'trend-improving' },
  stable:    { symbol: '\u2194', className: 'trend-stable' },
  decaying:  { symbol: '\u2193', className: 'trend-decaying' },
};

const COMPONENT_LABELS: Record<string, string> = {
  r_slope: 'R-Slope',
  sharpe: 'Sharpe',
  ltc: 'LTC',
  dd_containment: 'DD',
};

const COMPONENT_LABELS_V4: Record<string, string> = {
  daily_sharpe: 'Sharpe',
  drawdown_resilience: 'DD Res',
  payoff_asymmetry: 'Asym',
  recovery_velocity: 'Recov',
};

export default function LeaderboardView({ onClose }: LeaderboardViewProps) {
  const [rankings, setRankings] = useState<AFIScore[]>([]);
  const [currentUserRank, setCurrentUserRank] = useState<AFIScore | null>(null);
  const [totalParticipants, setTotalParticipants] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [hoveredUserId, setHoveredUserId] = useState<number | null>(null);

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

  const fetchLeaderboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await fetch(
        `${JOURNAL_API}/api/leaderboard?limit=200`,
        { credentials: 'include' }
      );

      if (!res.ok) {
        throw new Error('Failed to fetch leaderboard');
      }

      const data: AFILeaderboardResponse = await res.json();
      if (data.success) {
        setRankings(data.data.rankings);
        setCurrentUserRank(data.data.currentUserRank);
        setTotalParticipants(data.data.totalParticipants);
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
      setError('Failed to load leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeaderboard();
  }, [fetchLeaderboard]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  const handleRefresh = () => {
    fetchLeaderboard();
  };

  const getRankBadge = (rank: number): string => {
    if (rank === 1) return '\uD83E\uDD47';
    if (rank === 2) return '\uD83E\uDD48';
    if (rank === 3) return '\uD83E\uDD49';
    return `#${rank}`;
  };

  const isCurrentUser = (score: AFIScore): boolean => {
    return currentUserRank?.user_id === score.user_id;
  };

  const formatComponentTooltip = (score: AFIScore): string => {
    if ((score.afi_version === 4 || score.afi_version === 5) && score.components_v4) {
      return Object.entries(COMPONENT_LABELS_V4)
        .map(([key, label]) => {
          const val = score.components_v4?.[key as keyof typeof score.components_v4];
          return `${label}: ${val != null ? (val * 100).toFixed(0) + '%' : '-'}`;
        })
        .join(' | ');
    }
    return Object.entries(COMPONENT_LABELS)
      .map(([key, label]) => `${label}: ${(score.components[key as keyof typeof score.components] * 100).toFixed(0)}%`)
      .join(' | ');
  };

  const isV5 = rankings.length > 0 && rankings[0].afi_version === 5;
  const isV4 = rankings.length > 0 && rankings[0].afi_version === 4;

  const renderAFICell = (score: AFIScore, field: 'afi_r' | 'afi_m' | 'composite' | 'afi_score' = 'afi_r') => {
    const value = field === 'afi_score' ? score.afi_score
      : field === 'afi_r' ? (score.afi_r ?? score.afi_score)
      : field === 'afi_m' ? (score.afi_m ?? score.afi_score)
      : (score.composite ?? score.afi_score);
    const tier = getAFITier(value);
    const showTooltip = field === 'afi_r' || field === 'afi_score' || field === 'composite';
    return (
      <span
        className={`afi-score-value ${tier.className}`}
        onMouseEnter={() => showTooltip && setHoveredUserId(score.user_id)}
        onMouseLeave={() => showTooltip && setHoveredUserId(null)}
      >
        {Math.round(value)}
        {score.is_provisional && field === 'afi_r' && <span className="provisional-badge">P</span>}
        {showTooltip && hoveredUserId === score.user_id && (
          <span className="afi-tooltip">
            {formatComponentTooltip(score)}
            {score.confidence != null && ` | Conf: ${(score.confidence * 100).toFixed(0)}%`}
          </span>
        )}
      </span>
    );
  };

  const renderTrend = (trend: string) => {
    const t = TREND_ARROWS[trend] || TREND_ARROWS.stable;
    return <span className={`trend-arrow ${t.className}`}>{t.symbol}</span>;
  };

  const renderRow = (score: AFIScore, isSticky = false) => (
    <tr
      key={score.user_id}
      className={`${isCurrentUser(score) ? 'current-user-row' : ''} ${score.is_provisional ? 'provisional-row' : ''}`}
    >
      <td className="col-rank">
        <span className="rank-badge">{getRankBadge(score.rank)}</span>
      </td>
      <td className="col-user">
        <span className="user-name">
          {isSticky ? 'You' : (score.displayName || `User #${score.user_id}`)}
        </span>
        {!isSticky && isCurrentUser(score) && <span className="you-badge">You</span>}
      </td>
      {isV5 ? (
        <>
          <td className="col-afi col-afi-primary">{renderAFICell(score, 'composite')}</td>
          <td className="col-rb">
            <span className="rb-value">{score.robustness != null ? Math.round(score.robustness) : '-'}</span>
          </td>
          <td className="col-trend">
            <span className="m-trend-inline">
              {renderAFICell(score, 'afi_m')}
              {renderTrend(score.trend)}
            </span>
          </td>
        </>
      ) : isV4 ? (
        <>
          <td className="col-afi">{renderAFICell(score, 'afi_r')}</td>
          <td className="col-afi">{renderAFICell(score, 'afi_m')}</td>
          <td className="col-afi">{renderAFICell(score, 'composite')}</td>
          <td className="col-trend">
            {renderTrend(score.trend)}
          </td>
        </>
      ) : (
        <>
          <td className="col-afi">{renderAFICell(score, 'afi_score')}</td>
          <td className="col-rb">
            <span className="rb-value">{score.robustness.toFixed(0)}</span>
          </td>
          <td className="col-trend">
            {renderTrend(score.trend)}
          </td>
        </>
      )}
    </tr>
  );

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
              &#9881;&#65039;
            </button>
            <button
              className="btn-icon"
              onClick={handleRefresh}
              disabled={loading}
              title="Refresh"
            >
              &#128260;
            </button>
            <button className="modal-close" onClick={onClose}>&times;</button>
          </div>
        </div>

        <div className="period-info">
          <span className="period-label">Antifragile Index</span>
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
              <p>No rankings yet.</p>
              <p className="hint">Log trades with planned risk and R-multiples to appear on the leaderboard.</p>
            </div>
          ) : filteredRankings.length === 0 ? (
            <div className="empty-state">
              <p>No results for &quot;{searchQuery}&quot;</p>
            </div>
          ) : (
            <>
              <table className="leaderboard-table">
                <thead>
                  <tr>
                    <th className="col-rank">Rank</th>
                    <th className="col-user">Name</th>
                    {isV5 ? (
                      <>
                        <th className="col-afi col-afi-primary">AFI Rank</th>
                        <th className="col-rb">Robustness</th>
                        <th className="col-trend">M / Trend</th>
                      </>
                    ) : isV4 ? (
                      <>
                        <th className="col-afi">AFI-R</th>
                        <th className="col-afi">AFI-M</th>
                        <th className="col-afi">Comp</th>
                        <th className="col-trend">Trend</th>
                      </>
                    ) : (
                      <>
                        <th className="col-afi">AFI</th>
                        <th className="col-rb">RB</th>
                        <th className="col-trend">Trend</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {paginatedRankings.map((score) => renderRow(score))}
                </tbody>
              </table>

              {currentUserRank && !paginatedRankings.some(r => r.user_id === currentUserRank.user_id) && !searchQuery && (
                <div className="sticky-user-row">
                  <div className="sticky-separator">...</div>
                  <table className="leaderboard-table">
                    <tbody>
                      {renderRow(currentUserRank, true)}
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
            <span className="info-label">{isV5 ? 'AFI v5:' : isV4 ? 'AFI v4:' : 'AFI:'}</span>
            <span className="info-item">{isV5 ? '300-900 | COMP=Structural Composite | RB=Exposure Depth | M=Momentum' : isV4 ? '300-900 | R=Durability M=Momentum | Hover for breakdown' : '300-900 | Hover AFI for component breakdown'}</span>
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
          onSaved={() => fetchLeaderboard()}
        />
      )}
    </div>
  );
}
