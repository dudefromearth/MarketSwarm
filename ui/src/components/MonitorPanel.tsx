// src/components/MonitorPanel.tsx
/**
 * MonitorPanel - Position truth layer for simulated trading.
 *
 * Per trade-sim.md spec:
 * - Shows pending orders waiting to fill
 * - Shows trades with status: OPEN, CLOSED, CANCELED
 * - This is STATE, not evaluation - no analytics or narratives
 *
 * The Monitor answers one question only:
 * "What positions and orders do I currently have?"
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const JOURNAL_API = '';

interface Order {
  id: number;
  order_type: 'entry' | 'exit';
  symbol: string;
  direction: 'long' | 'short';
  limit_price: number;
  quantity: number;
  strategy?: string;
  trade_id?: string;
  status: 'pending' | 'filled' | 'cancelled' | 'expired';
  created_at: string;
  expires_at: string | null;
  filled_at: string | null;
  filled_price: number | null;
  notes?: string;
}

interface Trade {
  id: string;
  symbol: string;
  side: 'call' | 'put';  // API returns 'side' not 'direction'
  strategy?: string;
  strike?: number;
  width?: number;
  entry_price: number;  // In cents from API
  entry_time: string;
  exit_price?: number;
  exit_time?: string;
  status: 'open' | 'closed' | 'canceled';
  entry_mode?: 'instant' | 'freeform' | 'simulated';
  pnl?: number;
  log_id?: string;
}

interface MonitorPanelProps {
  onClose: () => void;
  onCloseTrade?: (tradeId: string) => void;
  onCancelOrder?: (orderId: number) => void;
  refreshTrigger?: number;
}

export default function MonitorPanel({
  onClose,
  onCloseTrade,
  onCancelOrder,
  refreshTrigger = 0
}: MonitorPanelProps) {
  const [pendingOrders, setPendingOrders] = useState<Order[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'orders' | 'trades'>('trades');
  const hasLoadedRef = useRef(false);

  const fetchData = useCallback(async () => {
    // Only show loading spinner on initial fetch
    if (!hasLoadedRef.current) {
      setLoading(true);
    }
    setError(null);

    try {
      // Fetch pending orders
      const ordersResponse = await fetch(`${JOURNAL_API}/api/orders/active`, {
        credentials: 'include'
      });

      if (ordersResponse.ok) {
        const text = await ordersResponse.text();
        try {
          const ordersResult = JSON.parse(text);
          if (ordersResult.success) {
            const allPending = [
              ...(ordersResult.data.pending_entries || []),
              ...(ordersResult.data.pending_exits || [])
            ];
            setPendingOrders(allPending);
            console.log('[MonitorPanel] Orders fetched:', allPending.length);
          } else {
            console.warn('[MonitorPanel] Orders API returned success=false');
          }
        } catch {
          console.warn('[MonitorPanel] Orders response not JSON:', text.slice(0, 100));
        }
      } else {
        console.warn('[MonitorPanel] Orders fetch failed:', ordersResponse.status);
      }

      // Fetch trades - get all open trades
      const tradesResponse = await fetch(`${JOURNAL_API}/api/trades?status=open`, {
        credentials: 'include'
      });

      if (tradesResponse.ok) {
        const text = await tradesResponse.text();
        try {
          const tradesResult = JSON.parse(text);
          console.log('[MonitorPanel] Trades response:', { success: tradesResult.success, count: tradesResult.data?.length });
          if (tradesResult.success) {
            // Only update if we got valid data (even if empty array)
            setTrades(tradesResult.data || []);
          } else {
            console.warn('[MonitorPanel] Trades API returned success=false:', tradesResult.error);
          }
        } catch (parseErr) {
          console.warn('[MonitorPanel] Trades response not JSON:', text.slice(0, 100));
        }
      } else {
        console.warn('[MonitorPanel] Trades fetch failed:', tradesResponse.status);
      }
    } catch (err) {
      console.error('[MonitorPanel] fetch error:', err);
      // Don't clear existing data on network errors
    } finally {
      setLoading(false);
      hasLoadedRef.current = true;
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchData();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleCancelOrder = async (orderId: number) => {
    if (!confirm('Cancel this order?')) return;

    try {
      const response = await fetch(`${JOURNAL_API}/api/orders/${orderId}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      const result = await response.json();

      if (result.success) {
        fetchData();
        onCancelOrder?.(orderId);
      } else {
        setError(result.error || 'Failed to cancel order');
      }
    } catch (err) {
      setError('Failed to cancel order');
    }
  };

  const handleCloseTrade = async (tradeId: string) => {
    if (!confirm('Close this trade at current market price?')) return;

    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${tradeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          status: 'closed',
          exit_time: new Date().toISOString()
        })
      });
      const result = await response.json();

      if (result.success) {
        fetchData();
        onCloseTrade?.(tradeId);
      } else {
        setError(result.error || 'Failed to close trade');
      }
    } catch (err) {
      setError('Failed to close trade');
    }
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const getTimeUntilExpiry = (expiresAt: string | null): string => {
    if (!expiresAt) return 'EOD';

    const now = new Date();
    const expiry = new Date(expiresAt);
    const diffMs = expiry.getTime() - now.getTime();

    if (diffMs <= 0) return 'Expired';

    const minutes = Math.floor(diffMs / (1000 * 60));
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    }
    return `${minutes}m`;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'open':
        return <span className="monitor-status-badge open">OPEN</span>;
      case 'closed':
        return <span className="monitor-status-badge closed">CLOSED</span>;
      case 'canceled':
        return <span className="monitor-status-badge canceled">CANCELED</span>;
      case 'pending':
        return <span className="monitor-status-badge pending">PENDING</span>;
      default:
        return <span className="monitor-status-badge">{status.toUpperCase()}</span>;
    }
  };

  const openTrades = trades.filter(t => t.status === 'open');
  const closedTrades = trades.filter(t => t.status !== 'open');

  return (
    <div className="monitor-panel-overlay" onClick={onClose}>
      <div className="monitor-panel" onClick={e => e.stopPropagation()}>
        <div className="monitor-header">
          <div className="monitor-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            <h3>Position Monitor</h3>
          </div>
          <button className="btn-close-monitor" onClick={onClose}>&times;</button>
        </div>

        <div className="monitor-tabs">
          <button
            className={`monitor-tab ${activeTab === 'trades' ? 'active' : ''}`}
            onClick={() => setActiveTab('trades')}
          >
            Trades
            {openTrades.length > 0 && <span className="tab-badge open">{openTrades.length}</span>}
          </button>
          <button
            className={`monitor-tab ${activeTab === 'orders' ? 'active' : ''}`}
            onClick={() => setActiveTab('orders')}
          >
            Pending Orders
            {pendingOrders.length > 0 && <span className="tab-badge">{pendingOrders.length}</span>}
          </button>
        </div>

        <div className="monitor-content">
          {loading && trades.length === 0 && pendingOrders.length === 0 ? (
            <div className="monitor-loading">Loading...</div>
          ) : error ? (
            <div className="monitor-error">{error}</div>
          ) : activeTab === 'trades' ? (
            <>
              {trades.length === 0 ? (
                <div className="monitor-empty">
                  <p>No simulated trades</p>
                  <p className="hint">Use Live mode to place trades that appear here</p>
                </div>
              ) : (
                <>
                  {/* Open Trades */}
                  {openTrades.length > 0 && (
                    <div className="monitor-section">
                      <div className="section-header">Open Positions ({openTrades.length})</div>
                      <div className="trades-list">
                        {openTrades.map(trade => (
                          <div key={trade.id} className="trade-card open">
                            <div className="trade-card-main">
                              <div className="trade-card-left">
                                <span className={`side-badge ${trade.side || 'call'}`}>
                                  {(trade.side || 'C').charAt(0).toUpperCase()}
                                </span>
                                <span className="trade-symbol">{trade.symbol}</span>
                                {trade.strategy && (
                                  <span className="trade-strategy">{trade.strategy}</span>
                                )}
                                {trade.strike && (
                                  <span className="trade-strike">{trade.strike}</span>
                                )}
                              </div>
                              <div className="trade-card-right">
                                {getStatusBadge(trade.status)}
                                <span className="trade-entry-price">
                                  ${(trade.entry_price / 100).toFixed(2)}
                                </span>
                              </div>
                            </div>
                            <div className="trade-card-footer">
                              <span className="trade-time">
                                {formatDateTime(trade.entry_time)}
                              </span>
                              <button
                                className="btn-close-trade"
                                onClick={() => handleCloseTrade(trade.id)}
                              >
                                Close
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Closed/Canceled Trades */}
                  {closedTrades.length > 0 && (
                    <div className="monitor-section">
                      <div className="section-header">History ({closedTrades.length})</div>
                      <div className="trades-list history">
                        {closedTrades.slice(0, 10).map(trade => (
                          <div key={trade.id} className={`trade-card ${trade.status}`}>
                            <div className="trade-card-main">
                              <div className="trade-card-left">
                                <span className={`side-badge small ${trade.side || 'call'}`}>
                                  {(trade.side || 'C').charAt(0).toUpperCase()}
                                </span>
                                <span className="trade-symbol">{trade.symbol}</span>
                                {trade.strategy && (
                                  <span className="trade-strategy">{trade.strategy}</span>
                                )}
                              </div>
                              <div className="trade-card-right">
                                {getStatusBadge(trade.status)}
                                {trade.pnl != null && (
                                  <span className={`trade-pnl ${Number(trade.pnl) >= 0 ? 'profit' : 'loss'}`}>
                                    {Number(trade.pnl) >= 0 ? '+' : ''}${(Number(trade.pnl) / 100).toFixed(2)}
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="trade-card-footer">
                              <span className="trade-time">
                                {trade.exit_time ? formatDateTime(trade.exit_time) : formatDateTime(trade.entry_time)}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          ) : (
            /* Orders Tab */
            <>
              {pendingOrders.length === 0 ? (
                <div className="monitor-empty">
                  <p>No pending orders</p>
                  <p className="hint">Create limit orders to see them here</p>
                </div>
              ) : (
                <div className="orders-list">
                  {pendingOrders.map(order => (
                    <div key={order.id} className={`order-card ${order.order_type}`}>
                      <div className="order-card-main">
                        <div className="order-card-left">
                          <span className={`direction-badge ${order.direction}`}>
                            {order.direction.toUpperCase()}
                          </span>
                          <span className="order-symbol">{order.symbol}</span>
                          <span className="order-type-label">{order.order_type}</span>
                          {order.strategy && (
                            <span className="order-strategy">{order.strategy}</span>
                          )}
                        </div>
                        <div className="order-card-right">
                          <span className="order-limit-price">
                            Limit: ${order.limit_price.toFixed(2)}
                          </span>
                          <span className="order-qty">x{order.quantity}</span>
                        </div>
                      </div>
                      <div className="order-card-footer">
                        <span className="order-time">
                          Created {formatTime(order.created_at)}
                        </span>
                        <span className="order-expiry">
                          Expires: {getTimeUntilExpiry(order.expires_at)}
                        </span>
                        <button
                          className="btn-cancel-order"
                          onClick={() => handleCancelOrder(order.id)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="monitor-footer">
          <span className="monitor-help">
            Live mode shows what <em>did</em> happen. What-If shows what <em>could</em> happen.
          </span>
        </div>
      </div>
    </div>
  );
}
