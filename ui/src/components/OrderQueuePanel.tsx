// src/components/OrderQueuePanel.tsx
/**
 * OrderQueuePanel - View and manage pending orders for simulated trading.
 *
 * Displays:
 * - Pending entry orders (waiting to open new positions)
 * - Pending exit orders (waiting to close existing positions)
 * - Order details: symbol, direction, limit price, quantity
 * - Time until expiration
 * - Cancel functionality
 */

import { useState, useEffect, useCallback } from 'react';

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

interface OrderQueuePanelProps {
  onClose: () => void;
  onOrderFilled?: () => void;
  refreshTrigger?: number;
}

export default function OrderQueuePanel({
  onClose,
  onOrderFilled: _onOrderFilled,
  refreshTrigger = 0
}: OrderQueuePanelProps) {
  const [pendingEntries, setPendingEntries] = useState<Order[]>([]);
  const [pendingExits, setPendingExits] = useState<Order[]>([]);
  const [recentOrders, setRecentOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'pending' | 'recent'>('pending');

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch active orders
      const activeResponse = await fetch(`${JOURNAL_API}/api/orders/active`);
      const activeResult = await activeResponse.json();

      if (activeResult.success) {
        setPendingEntries(activeResult.data.pending_entries);
        setPendingExits(activeResult.data.pending_exits);
      }

      // Fetch recent orders (filled, cancelled, expired)
      const recentResponse = await fetch(`${JOURNAL_API}/api/orders`);
      const recentResult = await recentResponse.json();

      if (recentResult.success) {
        const nonPending = recentResult.data.filter(
          (o: Order) => o.status !== 'pending'
        ).slice(0, 20); // Last 20 non-pending orders
        setRecentOrders(nonPending);
      }
    } catch (err) {
      setError('Failed to fetch orders');
      console.error('OrderQueuePanel fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders, refreshTrigger]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchOrders();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchOrders]);

  const handleCancelOrder = async (orderId: number) => {
    if (!confirm('Cancel this order?')) return;

    try {
      const response = await fetch(`${JOURNAL_API}/api/orders/${orderId}`, {
        method: 'DELETE'
      });
      const result = await response.json();

      if (result.success) {
        fetchOrders();
      } else {
        setError(result.error || 'Failed to cancel order');
      }
    } catch (err) {
      setError('Failed to cancel order');
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
      case 'filled':
        return <span className="order-status-badge filled">Filled</span>;
      case 'cancelled':
        return <span className="order-status-badge cancelled">Cancelled</span>;
      case 'expired':
        return <span className="order-status-badge expired">Expired</span>;
      default:
        return <span className="order-status-badge pending">Pending</span>;
    }
  };

  const totalPending = pendingEntries.length + pendingExits.length;

  return (
    <div className="order-queue-panel">
      <div className="order-queue-header">
        <h3>Order Queue</h3>
        <button className="btn-close" onClick={onClose}>&times;</button>
      </div>

      <div className="order-queue-tabs">
        <button
          className={`tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          Pending {totalPending > 0 && <span className="tab-count">{totalPending}</span>}
        </button>
        <button
          className={`tab-btn ${activeTab === 'recent' ? 'active' : ''}`}
          onClick={() => setActiveTab('recent')}
        >
          Recent
        </button>
      </div>

      <div className="order-queue-content">
        {loading ? (
          <div className="order-queue-loading">Loading orders...</div>
        ) : error ? (
          <div className="order-queue-error">{error}</div>
        ) : activeTab === 'pending' ? (
          <>
            {totalPending === 0 ? (
              <div className="order-queue-empty">
                <p>No pending orders</p>
                <p className="hint">Create simulated trades to place limit orders</p>
              </div>
            ) : (
              <>
                {/* Entry Orders */}
                {pendingEntries.length > 0 && (
                  <div className="order-group">
                    <div className="order-group-header">
                      Entry Orders ({pendingEntries.length})
                    </div>
                    {pendingEntries.map(order => (
                      <div key={order.id} className="order-card entry">
                        <div className="order-card-main">
                          <div className="order-card-left">
                            <span className={`direction-badge ${order.direction}`}>
                              {order.direction.toUpperCase()}
                            </span>
                            <span className="order-symbol">{order.symbol}</span>
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
                            Expires in {getTimeUntilExpiry(order.expires_at)}
                          </span>
                          <button
                            className="btn-cancel"
                            onClick={() => handleCancelOrder(order.id)}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Exit Orders */}
                {pendingExits.length > 0 && (
                  <div className="order-group">
                    <div className="order-group-header">
                      Exit Orders ({pendingExits.length})
                    </div>
                    {pendingExits.map(order => (
                      <div key={order.id} className="order-card exit">
                        <div className="order-card-main">
                          <div className="order-card-left">
                            <span className={`direction-badge ${order.direction}`}>
                              {order.direction.toUpperCase()}
                            </span>
                            <span className="order-symbol">{order.symbol}</span>
                            <span className="order-trade-ref">
                              Trade #{order.trade_id?.slice(-6)}
                            </span>
                          </div>
                          <div className="order-card-right">
                            <span className="order-limit-price">
                              TP: ${order.limit_price.toFixed(2)}
                            </span>
                          </div>
                        </div>
                        <div className="order-card-footer">
                          <span className="order-time">
                            Created {formatTime(order.created_at)}
                          </span>
                          <span className="order-expiry">
                            Expires in {getTimeUntilExpiry(order.expires_at)}
                          </span>
                          <button
                            className="btn-cancel"
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
          </>
        ) : (
          /* Recent Orders Tab */
          <>
            {recentOrders.length === 0 ? (
              <div className="order-queue-empty">
                <p>No recent orders</p>
              </div>
            ) : (
              <div className="recent-orders-list">
                {recentOrders.map(order => (
                  <div key={order.id} className={`recent-order-item ${order.status}`}>
                    <div className="recent-order-info">
                      <span className={`direction-badge small ${order.direction}`}>
                        {order.direction.charAt(0).toUpperCase()}
                      </span>
                      <span className="order-symbol">{order.symbol}</span>
                      <span className="order-type-label">{order.order_type}</span>
                      <span className="order-price">
                        {order.status === 'filled'
                          ? `@$${order.filled_price?.toFixed(2)}`
                          : `limit $${order.limit_price.toFixed(2)}`
                        }
                      </span>
                    </div>
                    <div className="recent-order-meta">
                      {getStatusBadge(order.status)}
                      <span className="order-time">
                        {formatDateTime(order.filled_at || order.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
