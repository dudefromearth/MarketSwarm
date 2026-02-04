// ui/src/components/TrackingAnalyticsDashboard.tsx
// Admin dashboard for Trade Idea Tracking analytics and feedback optimization

import { useState, useEffect, useCallback } from 'react';

interface OverallStats {
  total_ideas: number;
  win_count: number;
  win_rate: number;
  avg_pnl: number;
  avg_max_pnl: number;
  avg_capture_rate: number;
}

interface RankStats {
  entry_rank: number;
  count: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
  avg_max_pnl: number;
  avg_capture_rate: number;
}

interface RegimeStats {
  entry_regime: string;
  count: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
  avg_capture_rate: number;
}

interface StrategyStats {
  strategy: string;
  side: string;
  count: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
  avg_capture_rate: number;
}

interface ExitTiming {
  entry_rank: number;
  avg_days_to_max: number;
  avg_dte_at_max: number;
}

interface AnalyticsData {
  overall: OverallStats;
  byRank: RankStats[];
  byRegime: RegimeStats[];
  byStrategy: StrategyStats[];
  exitTiming: ExitTiming[];
}

interface SelectorParams {
  id: number;
  version: number;
  status: string;
  name: string;
  description: string;
  weights: Record<string, number>;
  regimeThresholds: Record<string, number>;
  performance: {
    totalIdeas: number;
    winCount: number;
    winRate: number;
    avgPnl: number;
    avgCaptureRate: number;
  };
  createdAt: string;
  activatedAt: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function TrackingAnalyticsDashboard({ isOpen, onClose }: Props) {
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [params, setParams] = useState<SelectorParams[]>([]);
  const [activeParams, setActiveParams] = useState<SelectorParams | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'rank' | 'regime' | 'strategy' | 'params'>('overview');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [analyticsRes, paramsRes, activeParamsRes] = await Promise.all([
        fetch('/api/admin/tracking/analytics', { credentials: 'include' }),
        fetch('/api/admin/tracking/params', { credentials: 'include' }),
        fetch('/api/admin/tracking/params/active', { credentials: 'include' }),
      ]);

      if (analyticsRes.ok) {
        const data = await analyticsRes.json();
        if (data.success) setAnalytics(data.data);
      }

      if (paramsRes.ok) {
        const data = await paramsRes.json();
        if (data.success) setParams(data.data);
      }

      if (activeParamsRes.ok) {
        const data = await activeParamsRes.json();
        if (data.success) setActiveParams(data.data);
      }

      setError(null);
    } catch (err) {
      setError('Failed to fetch tracking analytics');
      console.error('[TrackingAnalytics] Error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen, fetchData]);

  const handleActivateParams = async (version: number) => {
    try {
      const res = await fetch(`/api/admin/tracking/params/${version}/activate`, {
        method: 'POST',
        credentials: 'include',
      });
      if (res.ok) {
        fetchData(); // Refresh
      }
    } catch (err) {
      console.error('Failed to activate params:', err);
    }
  };

  if (!isOpen) return null;

  const formatPct = (val: number | null) => val != null ? `${val.toFixed(1)}%` : '-';
  const formatPnl = (val: number | null) => {
    if (val == null) return '-';
    const color = val > 0 ? '#22c55e' : val < 0 ? '#ef4444' : '#94a3b8';
    return <span style={{ color }}>${val.toFixed(2)}</span>;
  };

  const getRegimeColor = (regime: string) => {
    switch (regime) {
      case 'chaos': return '#ef4444';
      case 'goldilocks_2': return '#f59e0b';
      case 'goldilocks_1': return '#22c55e';
      case 'zombieland': return '#3b82f6';
      default: return '#94a3b8';
    }
  };

  return (
    <div className="tracking-analytics-overlay">
      <div className="tracking-analytics-modal">
        <div className="analytics-header">
          <h2>Trade Idea Tracking Analytics</h2>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="analytics-tabs">
          <button
            className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button
            className={`tab ${activeTab === 'rank' ? 'active' : ''}`}
            onClick={() => setActiveTab('rank')}
          >
            By Rank
          </button>
          <button
            className={`tab ${activeTab === 'regime' ? 'active' : ''}`}
            onClick={() => setActiveTab('regime')}
          >
            By Regime
          </button>
          <button
            className={`tab ${activeTab === 'strategy' ? 'active' : ''}`}
            onClick={() => setActiveTab('strategy')}
          >
            By Strategy
          </button>
          <button
            className={`tab ${activeTab === 'params' ? 'active' : ''}`}
            onClick={() => setActiveTab('params')}
          >
            Parameters
          </button>
        </div>

        <div className="analytics-content">
          {loading && <div className="loading">Loading analytics...</div>}
          {error && <div className="error">{error}</div>}

          {!loading && !error && activeTab === 'overview' && analytics?.overall && (
            <div className="overview-tab">
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-value">{analytics.overall.total_ideas || 0}</div>
                  <div className="stat-label">Total Ideas Tracked</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value" style={{ color: (analytics.overall.win_rate || 0) >= 50 ? '#22c55e' : '#ef4444' }}>
                    {formatPct(analytics.overall.win_rate)}
                  </div>
                  <div className="stat-label">Win Rate</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{formatPnl(analytics.overall.avg_pnl)}</div>
                  <div className="stat-label">Avg P&L</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{formatPnl(analytics.overall.avg_max_pnl)}</div>
                  <div className="stat-label">Avg Max P&L</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{formatPct(analytics.overall.avg_capture_rate)}</div>
                  <div className="stat-label">Avg Capture Rate</div>
                </div>
                <div className="stat-card">
                  <div className="stat-value">{analytics.overall.win_count || 0}</div>
                  <div className="stat-label">Total Wins</div>
                </div>
              </div>

              {activeParams && (
                <div className="active-params-summary">
                  <h4>Active Scoring Parameters</h4>
                  <div className="params-info">
                    <span className="params-name">{activeParams.name || `Version ${activeParams.version}`}</span>
                    <span className="params-version">v{activeParams.version}</span>
                  </div>
                  <div className="weights-grid">
                    {Object.entries(activeParams.weights || {}).map(([key, val]) => (
                      <div key={key} className="weight-item">
                        <span className="weight-label">{key}</span>
                        <span className="weight-value">{((val as number) * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && !error && activeTab === 'rank' && analytics?.byRank && (
            <div className="rank-tab">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Count</th>
                    <th>Wins</th>
                    <th>Win Rate</th>
                    <th>Avg P&L</th>
                    <th>Avg Max</th>
                    <th>Capture</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.byRank.map((row) => (
                    <tr key={row.entry_rank}>
                      <td className="rank-cell">#{row.entry_rank}</td>
                      <td>{row.count}</td>
                      <td>{row.wins}</td>
                      <td style={{ color: (row.win_rate || 0) >= 50 ? '#22c55e' : '#ef4444' }}>
                        {formatPct(row.win_rate)}
                      </td>
                      <td>{formatPnl(row.avg_pnl)}</td>
                      <td>{formatPnl(row.avg_max_pnl)}</td>
                      <td>{formatPct(row.avg_capture_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {analytics.exitTiming && analytics.exitTiming.length > 0 && (
                <div className="exit-timing-section">
                  <h4>Optimal Exit Timing</h4>
                  <table className="analytics-table">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Days to Max P&L</th>
                        <th>DTE at Max</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.exitTiming.map((row) => (
                        <tr key={row.entry_rank}>
                          <td>#{row.entry_rank}</td>
                          <td>{row.avg_days_to_max?.toFixed(1) || '-'}</td>
                          <td>{row.avg_dte_at_max?.toFixed(1) || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {!loading && !error && activeTab === 'regime' && analytics?.byRegime && (
            <div className="regime-tab">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Regime</th>
                    <th>Count</th>
                    <th>Wins</th>
                    <th>Win Rate</th>
                    <th>Avg P&L</th>
                    <th>Capture</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.byRegime.map((row) => (
                    <tr key={row.entry_regime}>
                      <td style={{ color: getRegimeColor(row.entry_regime) }}>
                        {row.entry_regime}
                      </td>
                      <td>{row.count}</td>
                      <td>{row.wins}</td>
                      <td style={{ color: (row.win_rate || 0) >= 50 ? '#22c55e' : '#ef4444' }}>
                        {formatPct(row.win_rate)}
                      </td>
                      <td>{formatPnl(row.avg_pnl)}</td>
                      <td>{formatPct(row.avg_capture_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && !error && activeTab === 'strategy' && analytics?.byStrategy && (
            <div className="strategy-tab">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Side</th>
                    <th>Count</th>
                    <th>Wins</th>
                    <th>Win Rate</th>
                    <th>Avg P&L</th>
                    <th>Capture</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.byStrategy.map((row, i) => (
                    <tr key={i}>
                      <td>{row.strategy}</td>
                      <td className={`side-${row.side}`}>{row.side}</td>
                      <td>{row.count}</td>
                      <td>{row.wins}</td>
                      <td style={{ color: (row.win_rate || 0) >= 50 ? '#22c55e' : '#ef4444' }}>
                        {formatPct(row.win_rate)}
                      </td>
                      <td>{formatPnl(row.avg_pnl)}</td>
                      <td>{formatPct(row.avg_capture_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && !error && activeTab === 'params' && (
            <div className="params-tab">
              <div className="params-header">
                <h4>Scoring Parameter Versions</h4>
              </div>
              <div className="params-list">
                {params.map((p) => (
                  <div key={p.version} className={`params-card ${p.status}`}>
                    <div className="params-card-header">
                      <span className="params-name">{p.name || `Version ${p.version}`}</span>
                      <span className={`params-status ${p.status}`}>{p.status}</span>
                    </div>
                    <div className="params-card-body">
                      <div className="params-description">{p.description || 'No description'}</div>
                      <div className="params-weights">
                        {Object.entries(p.weights || {}).map(([key, val]) => (
                          <span key={key} className="weight-badge">
                            {key}: {((val as number) * 100).toFixed(0)}%
                          </span>
                        ))}
                      </div>
                      {p.performance && p.performance.totalIdeas > 0 && (
                        <div className="params-performance">
                          <span>Ideas: {p.performance.totalIdeas}</span>
                          <span>Win Rate: {p.performance.winRate?.toFixed(1) || 0}%</span>
                          <span>Avg P&L: ${p.performance.avgPnl?.toFixed(2) || '0.00'}</span>
                        </div>
                      )}
                    </div>
                    {p.status !== 'active' && p.status !== 'retired' && (
                      <div className="params-card-actions">
                        <button
                          className="activate-btn"
                          onClick={() => handleActivateParams(p.version)}
                        >
                          Activate
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
