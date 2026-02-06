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

interface ActiveTrade {
  trade_id: string;
  symbol: string;
  tile_key: string;
  entry_rank: number;
  entry_time: string;
  entry_spot: number;
  entry_vix: number;
  entry_regime: string;
  // Time context
  entry_hour?: number;
  entry_day_of_week?: number;
  // GEX context
  entry_gex_flip?: number;
  entry_gex_call_wall?: number;
  entry_gex_put_wall?: number;
  // Trade params
  strategy: string;
  side: string;
  strike: number;
  width: number;
  dte: number;
  debit: number;
  max_profit_theoretical: number;
  current_pnl: number;
  max_pnl: number;
  max_pnl_time: string;
  expiration: string;
  status: string;
  params_version?: number;
}

interface TrackingStats {
  activeCount: number;
  historyCount: number;
  totalCurrentPnl: number;
  totalMaxPnl: number;
  // Historical/settled totals (pre-aggregated)
  historicalTotalPnl: number;
  historicalTotalMaxPnl: number;
  historicalTotalWins: number;
  historicalTotalCount: number;
  byRank: Record<string, {
    count: number;
    wins: number;
    totalPnl: number;
    totalMaxPnl: number;
    winRate: string;
    avgPnl: string;
    avgMaxPnl: string;
    captureRate: string;
  }>;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const PAGE_SIZE = 20;

export default function TrackingAnalyticsDashboard({ isOpen, onClose }: Props) {
  const [mode, setMode] = useState<'current' | 'historical'>('current');
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [params, setParams] = useState<SelectorParams[]>([]);
  const [activeParams, setActiveParams] = useState<SelectorParams | null>(null);
  const [activeTrades, setActiveTrades] = useState<ActiveTrade[]>([]);
  const [totalActiveCount, setTotalActiveCount] = useState<number>(0);
  const [trackingStats, setTrackingStats] = useState<TrackingStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'rank' | 'regime' | 'strategy' | 'params'>('overview');
  const [currentPage, setCurrentPage] = useState(0);

  const fetchCurrentData = useCallback(async () => {
    const [activeRes, statsRes] = await Promise.all([
      fetch('/api/models/trade_tracking/active?limit=100', { credentials: 'include' }),
      fetch('/api/models/trade_tracking/stats', { credentials: 'include' }),
    ]);

    // Check for auth errors first
    if (activeRes.status === 401 || activeRes.status === 403 ||
        statsRes.status === 401 || statsRes.status === 403) {
      throw new Error('Admin access required to view tracking data');
    }

    if (!activeRes.ok || !statsRes.ok) {
      throw new Error('Failed to fetch current tracking data');
    }

    const activeData = await activeRes.json();
    const statsData = await statsRes.json();

    if (activeData.success) {
      setActiveTrades(activeData.data.trades || []);
      setTotalActiveCount(activeData.data.total || activeData.data.count || 0);
    }

    if (statsData.success) {
      setTrackingStats(statsData.data);
    }
  }, []);

  const fetchHistoricalData = useCallback(async () => {
    try {
      // Fetch stats (pre-aggregated) and raw history (for regime/strategy breakdown)
      const [statsRes, historyRes, paramsRes, activeParamsRes] = await Promise.all([
        fetch('/api/models/trade_tracking/stats', { credentials: 'include' }),
        fetch('/api/models/trade_tracking/history?limit=500', { credentials: 'include' }),
        fetch('/api/admin/tracking/params', { credentials: 'include' }),
        fetch('/api/admin/tracking/params/active', { credentials: 'include' }),
      ]);

      // Check for auth/permission errors
      if (statsRes.status === 401 || statsRes.status === 403) {
        throw new Error('Admin access required to view historical analytics');
      }

      // Use pre-aggregated stats for overall and byRank (accurate for all trades)
      let statsData: TrackingStats | null = null;
      if (statsRes.ok) {
        const data = await statsRes.json();
        if (data.success) {
          statsData = data.data;
          setTrackingStats(data.data);
        }
      }

      // Get raw trades for regime/strategy breakdown (sample only - 500 of total)
      let trades: any[] = [];
      if (historyRes.ok) {
        const data = await historyRes.json();
        if (data.success && data.data?.trades) {
          trades = data.data.trades;
        }
      }

      if (statsData) {
        // Use pre-aggregated overall stats (accurate for ALL settled trades)
        const total = statsData.historicalTotalCount || 0;
        const winners = statsData.historicalTotalWins || 0;
        const totalPnl = statsData.historicalTotalPnl || 0;
        const totalMaxPnl = statsData.historicalTotalMaxPnl || 0;

        // Use pre-aggregated byRank stats (accurate for ALL settled trades)
        const byRankFromStats = Object.entries(statsData.byRank || {})
          .map(([rank, d]) => ({
            entry_rank: Number(rank),
            count: d.count,
            wins: d.wins,
            win_rate: d.count > 0 ? (d.wins / d.count) * 100 : 0,
            avg_pnl: d.count > 0 ? d.totalPnl / d.count : 0,
            avg_max_pnl: d.count > 0 ? d.totalMaxPnl / d.count : 0,
            avg_capture_rate: d.totalMaxPnl > 0 ? (d.totalPnl / d.totalMaxPnl) * 100 : 0,
          }))
          .sort((a, b) => a.entry_rank - b.entry_rank);

        // Calculate regime/strategy from sample trades (not fully accurate but better than nothing)
        const byRegimeMap: Record<string, { count: number; wins: number; totalPnl: number; totalCapture: number }> = {};
        const byStrategyMap: Record<string, { strategy: string; side: string; count: number; wins: number; totalPnl: number; totalCapture: number }> = {};

        trades.forEach((t: any) => {
          // By Regime
          const regime = t.entry_regime || 'unknown';
          if (!byRegimeMap[regime]) byRegimeMap[regime] = { count: 0, wins: 0, totalPnl: 0, totalCapture: 0 };
          byRegimeMap[regime].count++;
          if (t.is_winner) byRegimeMap[regime].wins++;
          byRegimeMap[regime].totalPnl += Number(t.final_pnl) || 0;
          byRegimeMap[regime].totalCapture += Number(t.pnl_captured_pct) || 0;

          // By Strategy
          const key = `${t.strategy}|${t.side}`;
          if (!byStrategyMap[key]) byStrategyMap[key] = { strategy: t.strategy, side: t.side, count: 0, wins: 0, totalPnl: 0, totalCapture: 0 };
          byStrategyMap[key].count++;
          if (t.is_winner) byStrategyMap[key].wins++;
          byStrategyMap[key].totalPnl += Number(t.final_pnl) || 0;
          byStrategyMap[key].totalCapture += Number(t.pnl_captured_pct) || 0;
        });

        setAnalytics({
          overall: {
            total_ideas: total,
            win_count: winners,
            win_rate: total > 0 ? (winners / total) * 100 : 0,
            avg_pnl: total > 0 ? totalPnl / total : 0,
            avg_max_pnl: total > 0 ? totalMaxPnl / total : 0,
            avg_capture_rate: totalMaxPnl > 0 ? (totalPnl / totalMaxPnl) * 100 : 0,
          },
          byRank: byRankFromStats,
          byRegime: Object.entries(byRegimeMap)
            .map(([regime, d]) => ({
              entry_regime: regime,
              count: d.count,
              wins: d.wins,
              win_rate: d.count > 0 ? (d.wins / d.count) * 100 : 0,
              avg_pnl: d.count > 0 ? d.totalPnl / d.count : 0,
              avg_capture_rate: d.count > 0 ? d.totalCapture / d.count : 0,
            }))
            .sort((a, b) => b.count - a.count),
          byStrategy: Object.values(byStrategyMap)
            .map((d) => ({
              strategy: d.strategy,
              side: d.side,
              count: d.count,
              wins: d.wins,
              win_rate: d.count > 0 ? (d.wins / d.count) * 100 : 0,
              avg_pnl: d.count > 0 ? d.totalPnl / d.count : 0,
              avg_capture_rate: d.count > 0 ? d.totalCapture / d.count : 0,
            }))
            .sort((a, b) => b.count - a.count),
          exitTiming: [], // Not available from Redis history
        });
      } else {
        throw new Error('Failed to load stats data');
      }

      if (paramsRes.ok) {
        const data = await paramsRes.json();
        if (data.success) setParams(data.data);
      }

      if (activeParamsRes.ok) {
        const data = await activeParamsRes.json();
        if (data.success) setActiveParams(data.data);
      }
    } catch (err) {
      console.error('[TrackingAnalytics] Historical data error:', err);
      throw err; // Re-throw so fetchData can catch and set error state
    }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (mode === 'current') {
        await fetchCurrentData();
      } else {
        await fetchHistoricalData();
      }
    } catch (err) {
      setError('Failed to fetch tracking data');
    } finally {
      setLoading(false);
    }
  }, [mode, fetchCurrentData, fetchHistoricalData]);

  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen, fetchData]);

  // Auto-refresh current data every 15 seconds (with overlap protection)
  useEffect(() => {
    if (!isOpen || mode !== 'current') return;

    let isFetching = false;
    const interval = setInterval(async () => {
      if (isFetching) return; // Skip if previous fetch still running
      isFetching = true;
      try {
        await fetchCurrentData();
      } catch (err) {
        console.error('[TrackingAnalytics] Auto-refresh error:', err);
      } finally {
        isFetching = false;
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [isOpen, mode, fetchCurrentData]);

  // Reset page when mode changes
  useEffect(() => {
    setCurrentPage(0);
  }, [mode]);

  // Clamp page if data shrinks (only when needed to avoid re-render loops)
  useEffect(() => {
    if (activeTrades.length === 0) {
      if (currentPage !== 0) setCurrentPage(0);
      return;
    }
    const maxPage = Math.ceil(activeTrades.length / PAGE_SIZE) - 1;
    if (currentPage > maxPage) {
      setCurrentPage(maxPage);
    }
  }, [activeTrades.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleActivateParams = async (version: number) => {
    try {
      const res = await fetch(`/api/admin/tracking/params/${version}/activate`, {
        method: 'POST',
        credentials: 'include',
      });
      if (res.ok) {
        fetchData();
      }
    } catch (err) {
      console.error('Failed to activate params:', err);
    }
  };

  if (!isOpen) return null;

  const formatPct = (val: number | string | null) => {
    if (val == null) return '-';
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return isNaN(num) ? '-' : `${num.toFixed(1)}%`;
  };
  const formatPnl = (val: number | string | null) => {
    if (val == null) return '-';
    const num = typeof val === 'string' ? parseFloat(val) : val;
    if (isNaN(num)) return '-';
    const color = num > 0 ? '#22c55e' : num < 0 ? '#ef4444' : '#94a3b8';
    return <span style={{ color }}>${num.toFixed(2)}</span>;
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

  const getRankColor = (rank: number) => {
    if (rank === 1) return '#fbbf24';
    if (rank === 2) return '#9ca3af';
    if (rank === 3) return '#cd7f32';
    return '#64748b';
  };

  // Use server-calculated totals from stats (includes ALL active trades, not just limited fetch)
  const totalInterimPnl = trackingStats?.totalCurrentPnl ?? 0;
  const totalMaxPnl = trackingStats?.totalMaxPnl ?? 0;
  const avgInterimPnl = totalActiveCount > 0 ? totalInterimPnl / totalActiveCount : 0;

  // Aggregate P&L by dimensions
  const pnlByRank = activeTrades.reduce((acc, t) => {
    const key = t.entry_rank;
    if (!acc[key]) acc[key] = { count: 0, totalPnl: 0, maxPnl: 0 };
    acc[key].count++;
    acc[key].totalPnl += t.current_pnl || 0;
    acc[key].maxPnl += t.max_pnl || 0;
    return acc;
  }, {} as Record<number, { count: number; totalPnl: number; maxPnl: number }>);

  const pnlByRegime = activeTrades.reduce((acc, t) => {
    const key = t.entry_regime || 'unknown';
    if (!acc[key]) acc[key] = { count: 0, totalPnl: 0, maxPnl: 0 };
    acc[key].count++;
    acc[key].totalPnl += t.current_pnl || 0;
    acc[key].maxPnl += t.max_pnl || 0;
    return acc;
  }, {} as Record<string, { count: number; totalPnl: number; maxPnl: number }>);

  const pnlByStrategy = activeTrades.reduce((acc, t) => {
    const key = `${t.strategy}/${t.side}`;
    if (!acc[key]) acc[key] = { count: 0, totalPnl: 0, maxPnl: 0 };
    acc[key].count++;
    acc[key].totalPnl += t.current_pnl || 0;
    acc[key].maxPnl += t.max_pnl || 0;
    return acc;
  }, {} as Record<string, { count: number; totalPnl: number; maxPnl: number }>);

  const pnlByParams = activeTrades.reduce((acc, t) => {
    const key = t.params_version ?? 0;
    if (!acc[key]) acc[key] = { count: 0, totalPnl: 0, maxPnl: 0 };
    acc[key].count++;
    acc[key].totalPnl += t.current_pnl || 0;
    acc[key].maxPnl += t.max_pnl || 0;
    return acc;
  }, {} as Record<number, { count: number; totalPnl: number; maxPnl: number }>);

  // Pagination for active trades
  const totalPages = Math.max(1, Math.ceil(activeTrades.length / PAGE_SIZE));
  const paginatedTrades = activeTrades.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  return (
    <div className="tracking-analytics-overlay">
      <div className="tracking-analytics-modal">
        <div className="analytics-header">
          <h2>Trade Idea Tracking Analytics</h2>
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'current' ? 'active' : ''}`}
              onClick={() => setMode('current')}
            >
              Current
            </button>
            <button
              className={`mode-btn ${mode === 'historical' ? 'active' : ''}`}
              onClick={() => setMode('historical')}
            >
              Historical
            </button>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {mode === 'current' ? (
          /* ===== CURRENT MODE ===== */
          <div className="analytics-content">
            {loading && <div className="loading">Loading data...</div>}
            {error && <div className="error">{error}</div>}

            {!loading && !error && (
              <>
                {/* Summary Stats */}
                <div className="current-summary">
                  <div className="summary-stats-grid">
                    <div className="summary-stat">
                      <div className="summary-value">{totalActiveCount}</div>
                      <div className="summary-label">Active Ideas</div>
                    </div>
                    <div className="summary-stat">
                      <div className="summary-value" style={{ color: totalInterimPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        ${totalInterimPnl.toFixed(2)}
                      </div>
                      <div className="summary-label">Total Interim P&L</div>
                    </div>
                    <div className="summary-stat">
                      <div className="summary-value" style={{ color: totalMaxPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                        ${totalMaxPnl.toFixed(2)}
                      </div>
                      <div className="summary-label">Total Max P&L</div>
                    </div>
                    <div className="summary-stat">
                      <div className="summary-value">{formatPnl(avgInterimPnl)}</div>
                      <div className="summary-label">Avg Interim P&L</div>
                    </div>
                    <div className="summary-stat">
                      <div className="summary-value">{trackingStats?.historyCount || 0}</div>
                      <div className="summary-label">Settled (Historical)</div>
                    </div>
                  </div>
                </div>

                {/* Active Ideas List */}
                <div className="current-ideas-section">
                  <div className="section-header">
                    <h3>Active Tracked Ideas</h3>
                    {activeTrades.length > PAGE_SIZE && (
                      <div className="pagination-controls">
                        <button
                          className="pagination-btn"
                          onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                          disabled={currentPage === 0}
                        >
                          ‹ Prev
                        </button>
                        <span className="pagination-info">
                          {currentPage + 1} / {totalPages}
                        </span>
                        <button
                          className="pagination-btn"
                          onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                          disabled={currentPage >= totalPages - 1}
                        >
                          Next ›
                        </button>
                      </div>
                    )}
                  </div>
                  {activeTrades.length === 0 ? (
                    <div className="no-data">No active tracked ideas</div>
                  ) : (
                    <table className="analytics-table">
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Strike</th>
                          <th>Side</th>
                          <th>Width</th>
                          <th>DTE</th>
                          <th>Debit</th>
                          <th>Current P&L</th>
                          <th>Max P&L</th>
                          <th>Regime</th>
                          <th>GEX Flip</th>
                          <th>Entry</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedTrades.map((trade) => (
                          <tr key={trade.trade_id}>
                            <td style={{ color: getRankColor(trade.entry_rank), fontWeight: 600 }}>
                              #{trade.entry_rank}
                            </td>
                            <td>{trade.strike}</td>
                            <td className={`side-${trade.side}`}>{trade.side}</td>
                            <td>{trade.width}w</td>
                            <td>{trade.dte}</td>
                            <td>${Number(trade.debit).toFixed(2)}</td>
                            <td>{formatPnl(trade.current_pnl)}</td>
                            <td>{formatPnl(trade.max_pnl)}</td>
                            <td style={{ color: getRegimeColor(trade.entry_regime) }}>
                              {trade.entry_regime}
                            </td>
                            <td style={{ fontSize: '0.85em', color: '#94a3b8' }}>
                              {trade.entry_gex_flip ? (
                                <span title={`Strike ${Number(trade.entry_gex_flip) > Number(trade.strike) ? 'below' : 'above'} GEX flip`}>
                                  {Number(trade.entry_gex_flip).toFixed(0)}
                                  {Number(trade.entry_gex_flip) > Number(trade.strike) ? ' ↑' : ' ↓'}
                                </span>
                              ) : '-'}
                            </td>
                            <td style={{ fontSize: '0.85em', color: '#94a3b8' }}>
                              {trade.entry_hour !== undefined ? (
                                <span title={`Day ${trade.entry_day_of_week ?? '?'}`}>
                                  {Math.floor(trade.entry_hour)}:{String(Math.round((trade.entry_hour % 1) * 60)).padStart(2, '0')}
                                </span>
                              ) : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* P&L Aggregations for Active Ideas */}
                {activeTrades.length > 0 && (
                  <div className="current-pnl-aggregations">
                    <h3>Active P&L by Dimension</h3>
                    <div className="aggregation-tables-grid">
                      {/* By Rank */}
                      <div className="aggregation-table">
                        <h4>By Rank</h4>
                        <table className="analytics-table compact">
                          <thead>
                            <tr>
                              <th>Rank</th>
                              <th>#</th>
                              <th>Current</th>
                              <th>Max</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(pnlByRank)
                              .sort(([a], [b]) => parseInt(a) - parseInt(b))
                              .map(([rank, data]) => (
                                <tr key={rank}>
                                  <td style={{ color: getRankColor(parseInt(rank)), fontWeight: 600 }}>#{rank}</td>
                                  <td>{data.count}</td>
                                  <td>{formatPnl(data.totalPnl)}</td>
                                  <td>{formatPnl(data.maxPnl)}</td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>

                      {/* By Regime */}
                      <div className="aggregation-table">
                        <h4>By Regime</h4>
                        <table className="analytics-table compact">
                          <thead>
                            <tr>
                              <th>Regime</th>
                              <th>#</th>
                              <th>Current</th>
                              <th>Max</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(pnlByRegime)
                              .sort(([a], [b]) => a.localeCompare(b))
                              .map(([regime, data]) => (
                                <tr key={regime}>
                                  <td style={{ color: getRegimeColor(regime) }}>{regime}</td>
                                  <td>{data.count}</td>
                                  <td>{formatPnl(data.totalPnl)}</td>
                                  <td>{formatPnl(data.maxPnl)}</td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>

                      {/* By Strategy */}
                      <div className="aggregation-table">
                        <h4>By Strategy</h4>
                        <table className="analytics-table compact">
                          <thead>
                            <tr>
                              <th>Strategy</th>
                              <th>#</th>
                              <th>Current</th>
                              <th>Max</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(pnlByStrategy)
                              .sort(([, a], [, b]) => b.totalPnl - a.totalPnl)
                              .map(([strategy, data]) => (
                                <tr key={strategy}>
                                  <td>{strategy}</td>
                                  <td>{data.count}</td>
                                  <td>{formatPnl(data.totalPnl)}</td>
                                  <td>{formatPnl(data.maxPnl)}</td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>

                      {/* By Params Version */}
                      <div className="aggregation-table">
                        <h4>By Params</h4>
                        <table className="analytics-table compact">
                          <thead>
                            <tr>
                              <th>Version</th>
                              <th>#</th>
                              <th>Current</th>
                              <th>Max</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(pnlByParams)
                              .sort(([a], [b]) => parseInt(b) - parseInt(a))
                              .map(([version, data]) => (
                                <tr key={version}>
                                  <td>v{version}</td>
                                  <td>{data.count}</td>
                                  <td>{formatPnl(data.totalPnl)}</td>
                                  <td>{formatPnl(data.maxPnl)}</td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {/* Quick Stats by Rank (from Redis) */}
                {trackingStats && Object.keys(trackingStats.byRank).length > 0 && (
                  <div className="current-rank-stats">
                    <h3>Performance by Rank (All Time)</h3>
                    <table className="analytics-table">
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Settled</th>
                          <th>Wins</th>
                          <th>Win Rate</th>
                          <th>Avg P&L</th>
                          <th>Capture</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(trackingStats.byRank)
                          .sort(([a], [b]) => parseInt(a) - parseInt(b))
                          .map(([rank, stats]) => (
                            <tr key={rank}>
                              <td style={{ color: getRankColor(parseInt(rank)), fontWeight: 600 }}>
                                #{rank}
                              </td>
                              <td>{stats.count}</td>
                              <td>{stats.wins}</td>
                              <td style={{ color: parseFloat(stats.winRate) >= 50 ? '#22c55e' : '#ef4444' }}>
                                {stats.winRate}
                              </td>
                              <td>{formatPnl(parseFloat(stats.avgPnl))}</td>
                              <td>{stats.captureRate}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        ) : (
          /* ===== HISTORICAL MODE ===== */
          <>
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

              {!loading && !error && !analytics && (
                <div className="no-data">No historical analytics data available</div>
              )}

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
                            <span className="weight-value">{(Number(val) * 100).toFixed(0)}%</span>
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
                              <td>{row.avg_days_to_max != null ? Number(row.avg_days_to_max).toFixed(1) : '-'}</td>
                              <td>{row.avg_dte_at_max != null ? Number(row.avg_dte_at_max).toFixed(1) : '-'}</td>
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
                                {key}: {(Number(val) * 100).toFixed(0)}%
                              </span>
                            ))}
                          </div>
                          {p.performance && p.performance.totalIdeas > 0 && (
                            <div className="params-performance">
                              <span>Ideas: {p.performance.totalIdeas}</span>
                              <span>Win Rate: {Number(p.performance.winRate || 0).toFixed(1)}%</span>
                              <span>Avg P&L: ${Number(p.performance.avgPnl || 0).toFixed(2)}</span>
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
          </>
        )}
      </div>
    </div>
  );
}
