// src/components/TradeLogPanel.tsx
import { useState, useEffect, useCallback } from 'react';
import LogSelector from './LogSelector';
import type { TradeLog } from './LogSelector';

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

export interface TradeReflectionContext {
  trade: Trade;
  log: TradeLog;
  // Flattened trade properties for convenience in JournalView
  closeDate?: string;
  strategy?: string;
  side?: string;
  strike?: number;
  width?: number | null;
  symbol?: string;
}

interface TradeLogPanelProps {
  onOpenTradeEntry: (logId: string) => void;
  onEditTrade: (trade: Trade) => void;
  onViewReporting: (logId: string) => void;
  onManageLogs: () => void;
onOpenJournal: (context?: TradeReflectionContext) => void;
  onOpenPlaybook: () => void;
  selectedLogId: string | null;
  selectedLog: TradeLog | null;
  onSelectLog: (log: TradeLog) => void;
  refreshTrigger?: number;
}

type StatusFilter = 'all' | 'open' | 'closed';
type PageSize = 10 | 25 | 50;
type SortOrder = 'recent' | 'oldest';

export default function TradeLogPanel({
  onOpenTradeEntry,
  onEditTrade,
  onViewReporting,
  onManageLogs,
  onOpenJournal,
  onOpenPlaybook,
  selectedLogId,
  selectedLog,
  onSelectLog,
  refreshTrigger = 0
}: TradeLogPanelProps) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(25);
  const [sortOrder, setSortOrder] = useState<SortOrder>('recent');

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
      params.set('limit', '10000'); // Fetch all trades for client-side pagination
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

  // Reset to page 1 when filter or log changes
  useEffect(() => {
    setCurrentPage(1);
  }, [statusFilter, selectedLogId]);

  // Sort and paginate trades
  const sortedTrades = [...trades].sort((a, b) => {
    const dateA = new Date(a.entry_time).getTime();
    const dateB = new Date(b.entry_time).getTime();
    return sortOrder === 'recent' ? dateB - dateA : dateA - dateB;
  });

  const totalTrades = sortedTrades.length;
  const totalPages = Math.ceil(totalTrades / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const paginatedTrades = sortedTrades.slice(startIndex, endIndex);

  const handlePageSizeChange = (newSize: PageSize) => {
    setPageSize(newSize);
    setCurrentPage(1);
  };

  const goToPage = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  const handleExport = async (format: 'csv' | 'excel') => {
    if (!selectedLogId || trades.length === 0) return;

    try {
      const response = await fetch(
        `${JOURNAL_API}/api/logs/${selectedLogId}/export?format=${format}`
      );

      if (!response.ok) {
        throw new Error('Export failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trades-${selectedLogId}.${format === 'csv' ? 'csv' : 'xlsx'}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export error:', err);
      setError('Failed to export trades');
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedLogId) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(
        `${JOURNAL_API}/api/logs/${selectedLogId}/import`,
        {
          method: 'POST',
          body: formData,
        }
      );

      const result = await response.json();

      if (result.success) {
        fetchTrades();
      } else {
        setError(result.error || 'Failed to import trades');
      }
    } catch (err) {
      console.error('Import error:', err);
      setError('Failed to import trades');
    }

    // Reset file input
    e.target.value = '';
  };

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades, refreshTrigger]);

  // Auto-refresh every 30 seconds (only when tab is visible)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchTrades();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchTrades]);

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatPnL = (pnl: number | null) => {
    if (pnl === null) return '-';
    const dollars = pnl / 100;
    return `$${Math.abs(dollars).toFixed(2)}`;
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

  const formatDuration = (entryTime: string, exitTime: string | null): string => {
    const start = new Date(entryTime).getTime();
    const end = exitTime ? new Date(exitTime).getTime() : Date.now();
    const diffMs = end - start;

    const minutes = Math.floor(diffMs / (1000 * 60));
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
      return `${days}d`;
    } else if (hours > 0) {
      return `${hours}h`;
    } else {
      return `${minutes}m`;
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
          <button
            className="btn-journal"
            onClick={() => onOpenJournal()}
            title="Journal"
          >
            Journal
          </button>
          <button
            className="btn-playbook"
            onClick={onOpenPlaybook}
            title="Playbook"
          >
            Playbook
          </button>
          {selectedLogId && (
            <button
              className="btn-reporting"
              onClick={() => onViewReporting(selectedLogId)}
              title="View Performance Report"
            >
              Report
            </button>
          )}
        </div>
      </div>

      {selectedLog && (
        <div className="trade-log-status-bar">
          <span className="status-bar-item">
            <span className="status-bar-label">P&L:</span>
            <span className={`status-bar-value ${selectedLog.total_pnl >= 0 ? 'profit' : 'loss'}`}>
              {selectedLog.total_pnl >= 0 ? '+' : ''}${(selectedLog.total_pnl / 100).toFixed(0)}
            </span>
          </span>
          <span className="status-bar-item">
            <span className="status-bar-label">Trades:</span>
            <span className="status-bar-value">{selectedLog.total_trades}</span>
          </span>
          <span className="status-bar-item">
            <span className="status-bar-label">Open:</span>
            <span className="status-bar-value">{selectedLog.open_trades}</span>
          </span>
          <span className="status-bar-item">
            <span className="status-bar-label">Closed:</span>
            <span className="status-bar-value">{selectedLog.closed_trades}</span>
          </span>
        </div>
      )}

      {/* Loop Indicator - The Trade Log is the hinge between Action and Reflection */}
      <div className="improvement-loop-indicator">
        <span className="loop-stage">Discovery</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Analysis</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage current">Action</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Reflection</span>
        <span className="loop-arrow">→</span>
        <span className="loop-stage">Distillation</span>
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
        <div className="trade-log-tools">
          <button
            className="btn-add-trade"
            onClick={() => selectedLogId && onOpenTradeEntry(selectedLogId)}
            disabled={!selectedLogId}
          >
            + Add Trade
          </button>
          <label className="btn-tool btn-tool-label" title="Import trades">
            Import
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={handleImport}
              disabled={!selectedLogId}
              style={{ display: 'none' }}
            />
          </label>
          <span className="tools-separator" />
          <span className="tools-label">Export:</span>
          <button
            className="btn-tool"
            onClick={() => handleExport('csv')}
            disabled={!selectedLogId || trades.length === 0}
            title="Export to CSV"
          >
            CSV
          </button>
          <button
            className="btn-tool"
            onClick={() => handleExport('excel')}
            disabled={!selectedLogId || trades.length === 0}
            title="Export to Excel"
          >
            Excel
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
          <>
            <table className="trade-log-table">
              <thead>
                <tr>
                  <th className="sortable" onClick={() => setSortOrder(sortOrder === 'recent' ? 'oldest' : 'recent')}>
                    Date/Time {sortOrder === 'recent' ? '↓' : '↑'}
                  </th>
                  <th>Symbol</th>
                  <th>DTE</th>
                  <th>Strategy</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>P&L</th>
                  <th>Dur</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {paginatedTrades.map(trade => (
                  <tr
                    key={trade.id}
                    className={`trade-row ${trade.status}`}
                    onClick={() => onEditTrade(trade)}
                  >
                    <td className="trade-datetime">{formatDateTime(trade.entry_time)}</td>
                    <td className="trade-symbol">{trade.symbol}</td>
                    <td className="trade-dte">
                      <span className={`dte-badge ${trade.dte === 0 ? 'dte-0' : trade.dte === 1 ? 'dte-1' : ''}`}>
                        {trade.dte !== null ? trade.dte : '-'}
                      </span>
                    </td>
                    <td className="trade-strategy">
                      <span className={`strategy-badge ${trade.strategy || ''}`}>
                        {getStrategyLabel(trade.strategy || '')}
                      </span>
                      <span className={`side-badge ${trade.side || ''}`}>
                        {trade.side ? trade.side.charAt(0).toUpperCase() : '-'}
                      </span>
                    </td>
                    <td className="trade-qty">{trade.quantity}</td>
                    <td className="trade-entry">
                      {(trade.entry_price / 100).toFixed(2)}
                    </td>
                    <td className="trade-exit">
                      {trade.exit_price !== null
                        ? (trade.exit_price / 100).toFixed(2)
                        : '-'
                      }
                    </td>
                    <td className={`trade-pnl ${
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
                    <td className="trade-duration">{formatDuration(trade.entry_time, trade.exit_time)}</td>
                    <td className="trade-reflect">
                      {trade.status === 'closed' && (
                        <button
                          className="reflect-hook"
                          title="Capture a thought?"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenJournal({
                              tradeId: trade.id,
                              symbol: trade.symbol,
                              strategy: trade.strategy,
                              side: trade.side,
                              strike: trade.strike,
                              width: trade.width,
                              closeDate: trade.exit_time || trade.entry_time,
                            });
                          }}
                        >
                          📝
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="trade-log-pagination">
              <div className="pagination-info">
                Showing {startIndex + 1}-{Math.min(endIndex, totalTrades)} of {totalTrades}
              </div>

              <div className="pagination-controls">
                <button
                  className="pagination-btn"
                  onClick={() => goToPage(1)}
                  disabled={currentPage === 1}
                  title="First page"
                >
                  &laquo;
                </button>
                <button
                  className="pagination-btn"
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  title="Previous page"
                >
                  &lsaquo;
                </button>
                <span className="pagination-current">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  className="pagination-btn"
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  title="Next page"
                >
                  &rsaquo;
                </button>
                <button
                  className="pagination-btn"
                  onClick={() => goToPage(totalPages)}
                  disabled={currentPage === totalPages}
                  title="Last page"
                >
                  &raquo;
                </button>
              </div>

              <div className="pagination-size">
                <span>Per page:</span>
                {([10, 25, 50] as PageSize[]).map(size => (
                  <button
                    key={size}
                    className={`size-btn ${pageSize === size ? 'active' : ''}`}
                    onClick={() => handlePageSizeChange(size)}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
