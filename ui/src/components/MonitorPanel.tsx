// src/components/MonitorPanel.tsx
// Pure display component - receives data as props from App.tsx

import { useState } from 'react';

interface Trade {
  id: string;
  symbol: string;
  side: string;
  strategy?: string;
  strike?: number;
  width?: number;
  dte?: number;
  entry_price: number;
  entry_time: string;
  status: string;
}

interface Order {
  id: number;
  symbol: string;
  direction: string;
  order_type: string;
  limit_price: number;
  quantity: number;
}

interface MonitorPanelProps {
  trades: Trade[];
  orders: Order[];
  onClose: () => void;
  onCloseTrade?: (tradeId: string) => void;
  onCancelOrder?: (orderId: number) => void;
}

export default function MonitorPanel({
  trades,
  orders,
  onClose,
  onCloseTrade,
  onCancelOrder,
}: MonitorPanelProps) {
  const [activeTab, setActiveTab] = useState<'trades' | 'orders'>('trades');
  const [error, setError] = useState<string | null>(null);

  const handleCloseTrade = async (tradeId: string) => {
    if (!confirm('Close this trade?')) return;
    try {
      const res = await fetch(`/api/trades/${tradeId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ status: 'closed', exit_time: new Date().toISOString() })
      });
      const data = await res.json();
      if (data.success) {
        onCloseTrade?.(tradeId);
      } else {
        setError(data.error || 'Failed to close');
      }
    } catch {
      setError('Failed to close trade');
    }
  };

  const handleCancelOrder = async (orderId: number) => {
    if (!confirm('Cancel this order?')) return;
    try {
      const res = await fetch(`/api/orders/${orderId}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      const data = await res.json();
      if (data.success) {
        onCancelOrder?.(orderId);
      } else {
        setError(data.error || 'Failed to cancel');
      }
    } catch {
      setError('Failed to cancel order');
    }
  };

  return (
    <div className="monitor-panel-overlay" onClick={onClose}>
      <div className="monitor-panel" onClick={e => e.stopPropagation()}>
        <div className="monitor-header">
          <div className="monitor-title"><h3>Position Monitor</h3></div>
          <button className="monitor-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="monitor-error">{error}</div>}

        <div className="monitor-tabs">
          <button
            className={`monitor-tab ${activeTab === 'trades' ? 'active' : ''}`}
            onClick={() => setActiveTab('trades')}
          >
            Open Trades {trades.length > 0 && <span className="tab-badge">{trades.length}</span>}
          </button>
          <button
            className={`monitor-tab ${activeTab === 'orders' ? 'active' : ''}`}
            onClick={() => setActiveTab('orders')}
          >
            Pending Orders {orders.length > 0 && <span className="tab-badge">{orders.length}</span>}
          </button>
        </div>

        <div className="monitor-content">
          {activeTab === 'trades' ? (
            trades.length === 0 ? (
              <div className="monitor-empty">No open trades</div>
            ) : (
              <div className="monitor-list">
                {trades.map(t => (
                  <div key={t.id} className="monitor-item">
                    <div className="monitor-item-main">
                      <span className="monitor-symbol">{t.symbol}</span>
                      <span className="monitor-strategy">{t.strategy || 'single'} {t.side}</span>
                      {t.strike && <span className="monitor-strike">{t.strike}</span>}
                    </div>
                    <div className="monitor-item-details">
                      <span>Entry: ${(t.entry_price / 100).toFixed(2)}</span>
                    </div>
                    <div className="monitor-item-actions">
                      <button className="monitor-btn close" onClick={() => handleCloseTrade(t.id)}>
                        Close
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : (
            orders.length === 0 ? (
              <div className="monitor-empty">No pending orders</div>
            ) : (
              <div className="monitor-list">
                {orders.map(o => (
                  <div key={o.id} className="monitor-item">
                    <div className="monitor-item-main">
                      <span className="monitor-symbol">{o.symbol}</span>
                      <span className="monitor-direction">{o.direction}</span>
                      <span className="monitor-type">{o.order_type}</span>
                    </div>
                    <div className="monitor-item-details">
                      <span>Limit: ${o.limit_price.toFixed(2)}</span>
                      <span>Qty: {o.quantity}</span>
                    </div>
                    <div className="monitor-item-actions">
                      <button className="monitor-btn cancel" onClick={() => handleCancelOrder(o.id)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
