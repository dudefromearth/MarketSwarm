// src/components/TradeDetailModal.tsx
import { useState, useEffect, Component, type ReactNode } from 'react';
import type { Trade, TradeEvent } from './TradeLogPanel';

const JOURNAL_API = 'http://localhost:3002';

// Error boundary to catch render crashes
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class TradeDetailErrorBoundary extends Component<{ children: ReactNode; onClose: () => void }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode; onClose: () => void }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('TradeDetailModal crash:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="modal-overlay" onClick={this.props.onClose}>
          <div className="modal-content trade-detail-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Error</h2>
              <button className="modal-close" onClick={this.props.onClose}>&times;</button>
            </div>
            <div className="trade-detail-content">
              <div className="form-error" style={{ padding: '20px' }}>
                <p>Failed to display trade details.</p>
                <p style={{ fontSize: '11px', color: '#888', marginTop: '8px' }}>
                  {this.state.error?.message || 'Unknown error'}
                </p>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

interface TradeDetailModalProps {
  trade: Trade | null;
  isOpen: boolean;
  onClose: () => void;
  onTradeUpdated: () => void;
}

type View = 'detail' | 'adjust' | 'close';

export default function TradeDetailModal({
  trade,
  isOpen,
  onClose,
  onTradeUpdated
}: TradeDetailModalProps) {
  const [view, setView] = useState<View>('detail');
  const [events, setEvents] = useState<TradeEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Adjustment form
  const [adjPrice, setAdjPrice] = useState('');
  const [adjQuantity, setAdjQuantity] = useState('');
  const [adjNotes, setAdjNotes] = useState('');

  // Close form
  const [exitPrice, setExitPrice] = useState('');
  const [closeNotes, setCloseNotes] = useState('');

  useEffect(() => {
    if (isOpen && trade) {
      fetchTradeWithEvents();
      setView('detail');
      setError(null);
    }
  }, [isOpen, trade?.id]);

  const fetchTradeWithEvents = async () => {
    if (!trade) return;

    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${trade.id}`);
      const result = await response.json();

      if (result.success && result.data.events) {
        setEvents(result.data.events);
      }
    } catch (err) {
      console.error('Fetch trade events error:', err);
    }
  };

  const handleAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!trade) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${trade.id}/adjust`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          price: parseFloat(adjPrice),
          quantity_change: parseInt(adjQuantity),
          notes: adjNotes || undefined
        })
      });

      const result = await response.json();

      if (result.success) {
        setAdjPrice('');
        setAdjQuantity('');
        setAdjNotes('');
        setView('detail');
        fetchTradeWithEvents();
        onTradeUpdated();
      } else {
        setError(result.error || 'Failed to add adjustment');
      }
    } catch (err) {
      setError('Unable to connect to journal service');
    } finally {
      setLoading(false);
    }
  };

  const handleCloseTrade = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!trade) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${trade.id}/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exit_price: parseFloat(exitPrice),
          notes: closeNotes || undefined
        })
      });

      const result = await response.json();

      if (result.success) {
        onTradeUpdated();
        onClose();
      } else {
        setError(result.error || 'Failed to close trade');
      }
    } catch (err) {
      setError('Unable to connect to journal service');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTrade = async () => {
    if (!trade) return;
    if (!confirm('Delete this trade? This cannot be undone.')) return;

    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${trade.id}`, {
        method: 'DELETE'
      });

      const result = await response.json();

      if (result.success) {
        onTradeUpdated();
        onClose();
      }
    } catch (err) {
      console.error('Delete trade error:', err);
    }
  };

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatPrice = (cents: number | null) => {
    if (cents === null) return '-';
    return `$${(cents / 100).toFixed(2)}`;
  };

  const formatPnL = (cents: number | null) => {
    if (cents === null) return '-';
    const dollars = cents / 100;
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

  if (!isOpen || !trade) return null;

  return (
    <TradeDetailErrorBoundary onClose={onClose}>
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content trade-detail-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Trade Detail</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {view === 'detail' && (
          <div className="trade-detail-content">
            <div className="trade-detail-summary">
              <div className="trade-detail-title">
                {trade.symbol} {trade.strategy ? trade.strategy.charAt(0).toUpperCase() + trade.strategy.slice(1) : ''}{' '}
                {trade.strike}
                {trade.width ? `/${trade.width}` : ''}{' '}
                {trade.side ? trade.side.toUpperCase() : ''}
              </div>
              <div className="trade-detail-meta">
                <span>@ ${trade.entry_price != null ? (trade.entry_price / 100).toFixed(2) : '-'}</span>
                <span>x{trade.quantity ?? '-'}</span>
              </div>
            </div>

            <div className="trade-detail-info">
              <div className="info-row">
                <span className="info-label">Status:</span>
                <span className={`info-value status-${trade.status || 'unknown'}`}>
                  {trade.status ? trade.status.toUpperCase() : 'UNKNOWN'}
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Opened:</span>
                <span className="info-value">{trade.entry_time ? formatDateTime(trade.entry_time) : '-'}</span>
              </div>
              {trade.exit_time && (
                <div className="info-row">
                  <span className="info-label">Closed:</span>
                  <span className="info-value">{formatDateTime(trade.exit_time)}</span>
                </div>
              )}
              {trade.entry_spot != null && (
                <div className="info-row">
                  <span className="info-label">Spot at Entry:</span>
                  <span className="info-value">{Number(trade.entry_spot).toFixed(2)}</span>
                </div>
              )}
              {trade.pnl !== null && (
                <div className="info-row">
                  <span className="info-label">P&L:</span>
                  <span className={`info-value ${trade.pnl >= 0 ? 'profit' : 'loss'}`}>
                    {formatPnL(trade.pnl)}
                    {trade.r_multiple != null && (
                      <span className="r-multiple">({Number(trade.r_multiple).toFixed(2)}R)</span>
                    )}
                  </span>
                </div>
              )}
              {trade.planned_risk && (
                <div className="info-row">
                  <span className="info-label">Risk:</span>
                  <span className="info-value">{formatPrice(trade.planned_risk)}</span>
                </div>
              )}
            </div>

            <div className="trade-detail-events">
              <h4>Events</h4>
              <div className="events-list">
                {events.map(event => (
                  <div key={event.id} className={`event-item event-${event.event_type || 'unknown'}`}>
                    <span className="event-type">{event.event_type ? event.event_type.toUpperCase() : 'EVENT'}</span>
                    <span className="event-time">{event.event_time ? formatDateTime(event.event_time) : '-'}</span>
                    {event.price && (
                      <span className="event-price">@ {formatPrice(event.price)}</span>
                    )}
                    {event.spot != null && (
                      <span className="event-spot">(spot: {Number(event.spot).toFixed(2)})</span>
                    )}
                    {event.quantity_change && (
                      <span className="event-qty">
                        {event.quantity_change > 0 ? '+' : ''}{event.quantity_change}
                      </span>
                    )}
                    {event.notes && (
                      <span className="event-notes">{event.notes}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {trade.notes && (
              <div className="trade-detail-notes">
                <h4>Notes</h4>
                <p>{trade.notes}</p>
              </div>
            )}

            {error && <div className="form-error">{error}</div>}

            <div className="trade-detail-actions">
              {trade.status === 'open' && (
                <>
                  <button
                    className="btn-adjust"
                    onClick={() => setView('adjust')}
                  >
                    Add Adjustment
                  </button>
                  <button
                    className="btn-close-trade"
                    onClick={() => setView('close')}
                  >
                    Close Trade
                  </button>
                </>
              )}
              <button
                className="btn-delete-trade"
                onClick={handleDeleteTrade}
              >
                Delete
              </button>
            </div>
          </div>
        )}

        {view === 'adjust' && (
          <form onSubmit={handleAdjustment} className="trade-action-form">
            <h3>Add Adjustment</h3>
            {error && <div className="form-error">{error}</div>}

            <div className="form-group">
              <label htmlFor="adj-price">Price ($)</label>
              <input
                id="adj-price"
                type="number"
                value={adjPrice}
                onChange={(e) => setAdjPrice(e.target.value)}
                step="0.01"
                min="0"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="adj-quantity">Quantity Change (+/-)</label>
              <input
                id="adj-quantity"
                type="number"
                value={adjQuantity}
                onChange={(e) => setAdjQuantity(e.target.value)}
                required
              />
              <span className="form-hint">Use positive for adding, negative for reducing</span>
            </div>

            <div className="form-group">
              <label htmlFor="adj-notes">Notes</label>
              <input
                id="adj-notes"
                type="text"
                value={adjNotes}
                onChange={(e) => setAdjNotes(e.target.value)}
                placeholder="Optional"
              />
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setView('detail')}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-submit"
                disabled={loading || !adjPrice || !adjQuantity}
              >
                {loading ? 'Saving...' : 'Add Adjustment'}
              </button>
            </div>
          </form>
        )}

        {view === 'close' && (
          <form onSubmit={handleCloseTrade} className="trade-action-form">
            <h3>Close Trade</h3>
            {error && <div className="form-error">{error}</div>}

            <div className="trade-close-summary">
              <p>
                Entry: ${(trade.entry_price / 100).toFixed(2)} x {trade.quantity}
              </p>
            </div>

            <div className="form-group">
              <label htmlFor="exit-price">Exit Price ($)</label>
              <input
                id="exit-price"
                type="number"
                value={exitPrice}
                onChange={(e) => setExitPrice(e.target.value)}
                step="0.01"
                min="0"
                required
              />
            </div>

            {exitPrice && (
              <div className="trade-close-preview">
                <span className="preview-label">Estimated P&L:</span>
                <span className={`preview-value ${
                  (parseFloat(exitPrice) * 100 - trade.entry_price) * trade.quantity >= 0
                    ? 'profit'
                    : 'loss'
                }`}>
                  {formatPnL(
                    (parseFloat(exitPrice) * 100 - trade.entry_price) * trade.quantity
                  )}
                </span>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="close-notes">Notes</label>
              <input
                id="close-notes"
                type="text"
                value={closeNotes}
                onChange={(e) => setCloseNotes(e.target.value)}
                placeholder="Optional"
              />
            </div>

            <div className="form-warning">
              Closing is final. The trade cannot be reopened.
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setView('detail')}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-submit"
                disabled={loading || !exitPrice}
              >
                {loading ? 'Closing...' : 'Close Trade'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
    </TradeDetailErrorBoundary>
  );
}
