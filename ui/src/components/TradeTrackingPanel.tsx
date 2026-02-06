// ui/src/components/TradeTrackingPanel.tsx
// Trade Idea Tracking - P&L instrumentation display

import { useState, useEffect, useCallback, useRef } from 'react';

interface TrackingStats {
  activeCount: number;
  historyCount: number;
  byRank: Record<number, RankStats>;
}

interface RankStats {
  count: number;
  wins: number;
  winRate: string;
  avgPnl: string;
  avgMaxPnl: string;
  captureRate: string;
}

interface TrackedTrade {
  trade_id: string;
  symbol: string;
  tile_key: string;
  entry_rank: number;
  entry_time: string;
  entry_spot: number;
  entry_vix: number;
  entry_regime: string;
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
  max_pnl_spot: number;
  expiration: string;
  status: string;
  // Settlement fields (for history)
  final_pnl?: number;
  is_winner?: boolean;
  settlement_spot?: number;
  pnl_captured_pct?: number;
}

interface Props {
  isOpen?: boolean;
}

export default function TradeTrackingPanel({ isOpen = true }: Props) {
  const [stats, setStats] = useState<TrackingStats | null>(null);
  const [activeTrades, setActiveTrades] = useState<TrackedTrade[]>([]);
  const [historyTrades, setHistoryTrades] = useState<TrackedTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'stats' | 'active' | 'history'>('stats');
  const isFetchingRef = useRef(false);

  const fetchData = useCallback(async () => {
    // Prevent overlapping requests
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    try {
      const [statsRes, activeRes, historyRes] = await Promise.all([
        fetch('/api/models/trade_tracking/stats', { credentials: 'include' }),
        fetch('/api/models/trade_tracking/active', { credentials: 'include' }),
        fetch('/api/models/trade_tracking/history?limit=50', { credentials: 'include' }),
      ]);

      // Check for auth errors
      if (statsRes.status === 401 || statsRes.status === 403) {
        setError('Admin access required');
        setLoading(false);
        isFetchingRef.current = false;
        return;
      }

      if (statsRes.ok) {
        const statsData = await statsRes.json();
        if (statsData.success) setStats(statsData.data);
      } else {
        console.warn('[TradeTrackingPanel] Stats fetch failed:', statsRes.status);
      }

      if (activeRes.ok) {
        const activeData = await activeRes.json();
        if (activeData.success) setActiveTrades(activeData.data.trades || []);
      }

      if (historyRes.ok) {
        const historyData = await historyRes.json();
        if (historyData.success) setHistoryTrades(historyData.data.trades || []);
      }

      setError(null);
    } catch (err) {
      setError('Failed to fetch tracking data');
      console.error('[TradeTrackingPanel] Error:', err);
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [isOpen, fetchData]);

  if (!isOpen) return null;

  const formatTime = (isoString: string) => {
    // Ensure UTC parsing: append 'Z' if no timezone indicator present
    const normalizedIso = isoString.includes('Z') || isoString.includes('+') || isoString.includes('-', 10)
      ? isoString
      : isoString + 'Z';
    const date = new Date(normalizedIso);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const getPnlColor = (pnl: number) => {
    if (pnl > 0) return '#22c55e';
    if (pnl < 0) return '#ef4444';
    return '#94a3b8';
  };

  const getRankColor = (rank: number) => {
    if (rank === 1) return '#fbbf24';
    if (rank === 2) return '#9ca3af';
    if (rank === 3) return '#cd7f32';
    return '#64748b';
  };

  return (
    <div className="trade-tracking-panel">
      <div className="tracking-header">
        <h3>Trade Idea Tracking</h3>
        <div className="tracking-tabs">
          <button
            className={`tracking-tab ${activeTab === 'stats' ? 'active' : ''}`}
            onClick={() => setActiveTab('stats')}
          >
            Stats
          </button>
          <button
            className={`tracking-tab ${activeTab === 'active' ? 'active' : ''}`}
            onClick={() => setActiveTab('active')}
          >
            Active ({stats?.activeCount || 0})
          </button>
          <button
            className={`tracking-tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            History ({stats?.historyCount || 0})
          </button>
        </div>
      </div>

      {loading && <div className="tracking-loading">Loading...</div>}
      {error && <div className="tracking-error">{error}</div>}

      {!loading && !error && activeTab === 'stats' && stats && (
        <div className="tracking-stats">
          <div className="stats-summary">
            <div className="stat-box">
              <div className="stat-value">{stats.activeCount}</div>
              <div className="stat-label">Active</div>
            </div>
            <div className="stat-box">
              <div className="stat-value">{stats.historyCount}</div>
              <div className="stat-label">Settled</div>
            </div>
          </div>

          {Object.keys(stats.byRank).length > 0 ? (
            <table className="rank-stats-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Trades</th>
                  <th>Win %</th>
                  <th>Avg P&L</th>
                  <th>Avg Max</th>
                  <th>Capture</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stats.byRank)
                  .sort(([a], [b]) => parseInt(a) - parseInt(b))
                  .map(([rank, rs]) => (
                    <tr key={rank}>
                      <td style={{ color: getRankColor(parseInt(rank)) }}>#{rank}</td>
                      <td>{rs.count}</td>
                      <td style={{ color: parseFloat(rs.winRate) >= 50 ? '#22c55e' : '#ef4444' }}>
                        {rs.winRate}
                      </td>
                      <td style={{ color: getPnlColor(parseFloat(rs.avgPnl)) }}>
                        ${rs.avgPnl}
                      </td>
                      <td>${rs.avgMaxPnl}</td>
                      <td>{rs.captureRate}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : (
            <div className="no-data">No settled trades yet. Stats will appear after trades expire.</div>
          )}
        </div>
      )}

      {!loading && !error && activeTab === 'active' && (
        <div className="tracking-active">
          {activeTrades.length === 0 ? (
            <div className="no-data">No active tracked trades</div>
          ) : (
            <div className="active-trades-list">
              {activeTrades.map((trade) => (
                <div key={trade.trade_id} className="tracked-trade-card">
                  <div className="trade-card-header">
                    <span
                      className="trade-rank"
                      style={{ backgroundColor: getRankColor(trade.entry_rank) }}
                    >
                      #{trade.entry_rank}
                    </span>
                    <span className={`trade-side ${trade.side}`}>
                      {trade.side.toUpperCase()}
                    </span>
                    <span className="trade-strike">{trade.strike}</span>
                    <span className="trade-width">{trade.width}w</span>
                    <span className="trade-dte">{trade.dte}DTE</span>
                  </div>

                  <div className="trade-card-pnl">
                    <div className="pnl-current">
                      <span className="pnl-label">Current</span>
                      <span className="pnl-value" style={{ color: getPnlColor(trade.current_pnl) }}>
                        ${trade.current_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div className="pnl-max">
                      <span className="pnl-label">Max</span>
                      <span className="pnl-value" style={{ color: getPnlColor(trade.max_pnl) }}>
                        ${trade.max_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div className="pnl-theoretical">
                      <span className="pnl-label">Target</span>
                      <span className="pnl-value">${trade.max_profit_theoretical.toFixed(2)}</span>
                    </div>
                  </div>

                  <div className="trade-card-meta">
                    <span className="trade-symbol">{trade.symbol.replace('I:', '')}</span>
                    <span className="trade-entry">Entry: {formatTime(trade.entry_time)}</span>
                    <span className="trade-debit">${trade.debit.toFixed(2)} debit</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && !error && activeTab === 'history' && (
        <div className="tracking-history">
          {historyTrades.length === 0 ? (
            <div className="no-data">No settled trades yet</div>
          ) : (
            <div className="history-trades-list">
              {historyTrades.map((trade) => (
                <div
                  key={trade.trade_id}
                  className={`tracked-trade-card settled ${trade.is_winner ? 'winner' : 'loser'}`}
                >
                  <div className="trade-card-header">
                    <span
                      className="trade-rank"
                      style={{ backgroundColor: getRankColor(trade.entry_rank) }}
                    >
                      #{trade.entry_rank}
                    </span>
                    <span className={`trade-side ${trade.side}`}>
                      {trade.side.toUpperCase()}
                    </span>
                    <span className="trade-strike">{trade.strike}</span>
                    <span className="trade-width">{trade.width}w</span>
                    <span className={`trade-result ${trade.is_winner ? 'win' : 'loss'}`}>
                      {trade.is_winner ? 'WIN' : 'LOSS'}
                    </span>
                  </div>

                  <div className="trade-card-pnl">
                    <div className="pnl-final">
                      <span className="pnl-label">Final</span>
                      <span className="pnl-value" style={{ color: getPnlColor(trade.final_pnl || 0) }}>
                        ${(trade.final_pnl || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="pnl-max">
                      <span className="pnl-label">Max</span>
                      <span className="pnl-value" style={{ color: getPnlColor(trade.max_pnl) }}>
                        ${trade.max_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div className="pnl-capture">
                      <span className="pnl-label">Captured</span>
                      <span className="pnl-value">
                        {(trade.pnl_captured_pct || 0).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  <div className="trade-card-meta">
                    <span className="trade-symbol">{trade.symbol.replace('I:', '')}</span>
                    <span className="trade-debit">${trade.debit.toFixed(2)} debit</span>
                    <span className="trade-settlement">
                      Settled @ {(trade.settlement_spot || 0).toFixed(0)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
