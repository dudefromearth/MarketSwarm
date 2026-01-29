// src/components/TradeLogPanel.tsx
import { useState, useEffect, useCallback } from 'react';

const JOURNAL_API = 'http://localhost:3002';

export interface Trade {
  id: string;
  user_id: string;
  symbol: string;
  underlying: string;
  strategy: string;
  side: string;
  dte: number | null;
  strike: number;
  width: number;
  quantity: number;
  entry_time: string;
  entry_price: number;
  entry_spot: number | null;
  exit_time: string | null;
  exit_price: number | null;
  exit_spot: number | null;
  pnl: number | null;
  pnl_percent: number | null;
  max_profit: number | null;
  max_loss: number | null;
  status: string;
  notes: string | null;
  tags: string;
  playbook_id: string | null;
  source: string;
  created_at: string;
  updated_at: string;
}

interface TradeLogPanelProps {
  onOpenTradeEntry: (prefill?: Partial<Trade>) => void;
  onEditTrade: (trade: Trade) => void;
  refreshTrigger?: number;
}

type StatusFilter = 'all' | 'open' | 'closed';
type TimeFilter = 'today' | 'week' | 'month' | 'all';

export default function TradeLogPanel({
  onOpenTradeEntry,
  onEditTrade,
  refreshTrigger = 0
}: TradeLogPanelProps) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('today');

  // Stats
  const [openCount, setOpenCount] = useState(0);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Build query params
      const params = new URLSearchParams();
      if (statusFilter !== 'all') {
        params.set('status', statusFilter);
      }

      // Time filter
      if (timeFilter !== 'all') {
        const now = new Date();
        let fromDate: Date;

        switch (timeFilter) {
          case 'today':
            fromDate = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            break;
          case 'week':
            fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
          case 'month':
            fromDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            break;
          default:
            fromDate = new Date(0);
        }

        params.set('from', fromDate.toISOString());
      }

      const response = await fetch(`${JOURNAL_API}/api/trades?${params}`);
      const result = await response.json();

      if (result.success) {
        setTrades(result.data);
        // Count open trades
        const open = result.data.filter((t: Trade) => t.status === 'open').length;
        setOpenCount(open);
      } else {
        setError(result.error || 'Failed to fetch trades');
      }
    } catch (err) {
      setError('Unable to connect to journal service');
      console.error('TradeLogPanel fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, timeFilter]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades, refreshTrigger]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchTrades, 30000);
    return () => clearInterval(interval);
  }, [fetchTrades]);

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatPnL = (pnl: number | null) => {
    if (pnl === null) return '-';
    const formatted = Math.abs(pnl / 100).toFixed(2);
    return pnl >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

  const getStrategyLabel = (strategy: string) => {
    switch (strategy) {
      case 'butterfly': return 'BF';
      case 'vertical': return 'VS';
      case 'single': return 'SGL';
      default: return strategy.toUpperCase().slice(0, 3);
    }
  };

  return (
    <div className="trade-log-panel">
      <div className="trade-log-header">
        <h3>Trade Log</h3>
        <button
          className="btn-add-trade"
          onClick={() => onOpenTradeEntry()}
        >
          + Add Trade
        </button>
      </div>

      <div className="trade-log-filters">
        <div className="filter-group">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          >
            <option value="all">All Status</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div className="filter-group">
          <select
            value={timeFilter}
            onChange={(e) => setTimeFilter(e.target.value as TimeFilter)}
          >
            <option value="today">Today</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>
            <option value="all">All Time</option>
          </select>
        </div>

        <div className="trade-log-stats">
          <span className="stat-badge open">Open: {openCount}</span>
        </div>
      </div>

      <div className="trade-log-table-container">
        {loading && trades.length === 0 ? (
          <div className="trade-log-loading">Loading trades...</div>
        ) : error ? (
          <div className="trade-log-error">{error}</div>
        ) : trades.length === 0 ? (
          <div className="trade-log-empty">
            <p>No trades found.</p>
            <p className="hint">Click "+ Add Trade" or log from heatmap tiles.</p>
          </div>
        ) : (
          <table className="trade-log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Strike</th>
                <th>Entry</th>
                <th>P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(trade => (
                <tr
                  key={trade.id}
                  className={`trade-row ${trade.status}`}
                  onClick={() => onEditTrade(trade)}
                >
                  <td className="trade-time">{formatTime(trade.entry_time)}</td>
                  <td className="trade-symbol">{trade.symbol}</td>
                  <td className="trade-strategy">
                    <span className={`strategy-badge ${trade.strategy}`}>
                      {getStrategyLabel(trade.strategy)}
                    </span>
                    <span className={`side-badge ${trade.side}`}>
                      {trade.side.charAt(0).toUpperCase()}
                    </span>
                  </td>
                  <td className="trade-strike">
                    {trade.strike}
                    {trade.width > 0 && <span className="trade-width">/{trade.width}</span>}
                  </td>
                  <td className="trade-entry">${trade.entry_price.toFixed(2)}</td>
                  <td className={`trade-pnl ${trade.status === 'open' ? 'open' : trade.pnl && trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                    {trade.status === 'open' ? 'OPEN' : formatPnL(trade.pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
