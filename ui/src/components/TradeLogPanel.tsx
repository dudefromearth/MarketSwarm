// src/components/TradeLogPanel.tsx
import { useState, useEffect, useCallback } from 'react';
import LogSelector, { TradeLog } from './LogSelector';

const JOURNAL_API = 'http://localhost:3002';

export interface Trade {
  id: string;
  log_id: string;
  symbol: string;
  underlying: string;
  strategy: string;
  side: string;
  dte: number | null;
  strike: number;
  width: number | null;
  quantity: number;
  entry_time: string;
  entry_price: number;
  entry_price_dollars: number;
  entry_spot: number | null;
  entry_iv: number | null;
  exit_time: string | null;
  exit_price: number | null;
  exit_price_dollars?: number;
  exit_spot: number | null;
  planned_risk: number | null;
  planned_risk_dollars?: number;
  max_profit: number | null;
  max_profit_dollars?: number;
  max_loss: number | null;
  max_loss_dollars?: number;
  pnl: number | null;
  pnl_dollars?: number;
  r_multiple: number | null;
  status: string;
  notes: string | null;
  tags: string[] | string;
  source: string;
  playbook_id: string | null;
  created_at: string;
  updated_at: string;
  events?: TradeEvent[];
}

export interface TradeEvent {
  id: string;
  trade_id: string;
  event_type: string;
  event_time: string;
  price: number | null;
  price_dollars?: number;
  spot: number | null;
  quantity_change: number | null;
  notes: string | null;
  created_at: string;
}

interface TradeLogPanelProps {
  onOpenTradeEntry: (logId: string) => void;
  onEditTrade: (trade: Trade) => void;
  onViewReporting: (logId: string) => void;
  onManageLogs: () => void;
  selectedLogId: string | null;
  onSelectLog: (log: TradeLog) => void;
  refreshTrigger?: number;
}

type StatusFilter = 'all' | 'open' | 'closed';

export default function TradeLogPanel({
  onOpenTradeEntry,
  onEditTrade,
  onViewReporting,
  onManageLogs,
  selectedLogId,
  onSelectLog,
  refreshTrigger = 0
}: TradeLogPanelProps) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  // Counts
  const [openCount, setOpenCount] = useState(0);
  const [closedCount, setClosedCount] = useState(0);

  const fetchTrades = useCallback(async () => {
    if (!selectedLogId) {
      setTrades([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') {
        params.set('status', statusFilter);
      }

      const response = await fetch(
        `${JOURNAL_API}/api/logs/${selectedLogId}/trades?${params}`
      );
      const result = await response.json();

      if (result.success) {
        setTrades(result.data);

        // Count by status
        const open = result.data.filter((t: Trade) => t.status === 'open').length;
        const closed = result.data.filter((t: Trade) => t.status === 'closed').length;
        setOpenCount(open);
        setClosedCount(closed);
      } else {
        setError(result.error || 'Failed to fetch trades');
      }
    } catch (err) {
      setError('Unable to connect to journal service');
      console.error('TradeLogPanel fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedLogId, statusFilter]);

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
    const dollars = pnl / 100;
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

  const getStrategyLabel = (strategy: string) => {
    switch (strategy) {
      case 'butterfly': return 'BF';
      case 'vertical': return 'VS';
      case 'single': return 'SGL';
      case 'iron_condor': return 'IC';
      default: return strategy.toUpperCase().slice(0, 3);
    }
  };

  return (
    <div className="trade-log-panel">
      <div className="trade-log-header">
        <LogSelector
          selectedLogId={selectedLogId}
          onSelectLog={onSelectLog}
          onManageLogs={onManageLogs}
          refreshTrigger={refreshTrigger}
        />
        <div className="trade-log-actions">
          {selectedLogId && (
            <button
              className="btn-reporting"
              onClick={() => onViewReporting(selectedLogId)}
              title="View Performance Report"
            >
              Report
            </button>
          )}
          <button
            className="btn-add-trade"
            onClick={() => selectedLogId && onOpenTradeEntry(selectedLogId)}
            disabled={!selectedLogId}
          >
            + Add Trade
          </button>
        </div>
      </div>

      <div className="trade-log-filters">
        <div className="status-tabs">
          <button
            className={`status-tab ${statusFilter === 'open' ? 'active' : ''}`}
            onClick={() => setStatusFilter('open')}
          >
            Open: {openCount}
          </button>
          <button
            className={`status-tab ${statusFilter === 'closed' ? 'active' : ''}`}
            onClick={() => setStatusFilter('closed')}
          >
            Closed: {closedCount}
          </button>
          <button
            className={`status-tab ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            All
          </button>
        </div>
      </div>

      <div className="trade-log-table-container">
        {!selectedLogId ? (
          <div className="trade-log-empty">
            <p>No trade log selected.</p>
            <p className="hint">Create a log to start tracking trades.</p>
          </div>
        ) : loading && trades.length === 0 ? (
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
                <th>Status</th>
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
                    {trade.width && trade.width > 0 && (
                      <span className="trade-width">/{trade.width}</span>
                    )}
                  </td>
                  <td className="trade-entry">
                    ${(trade.entry_price / 100).toFixed(2)}
                  </td>
                  <td className={`trade-status ${
                    trade.status === 'open'
                      ? 'open'
                      : trade.pnl && trade.pnl >= 0
                        ? 'profit'
                        : 'loss'
                  }`}>
                    {trade.status === 'open' ? (
                      <span className="status-open">OPEN</span>
                    ) : (
                      formatPnL(trade.pnl)
                    )}
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
