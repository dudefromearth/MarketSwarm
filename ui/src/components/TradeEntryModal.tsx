// src/components/TradeEntryModal.tsx
import { useState, useEffect, useMemo } from 'react';
import type { Trade } from './TradeLogPanel';

const JOURNAL_API = 'http://localhost:3002';

type Strategy = 'single' | 'vertical' | 'butterfly';
type Side = 'call' | 'put';
type EntryMode = 'instant' | 'freeform' | 'simulated';

export interface TradeEntryData {
  symbol?: string;
  underlying?: string;
  strategy?: Strategy;
  side?: Side;
  strike?: number;
  width?: number;
  dte?: number;
  entry_price?: number;
  entry_spot?: number;
  max_profit?: number;
  max_loss?: number;
  source?: string;
  notes?: string;
  tags?: string[];
}

interface MarketQuote {
  bid?: number;
  ask?: number;
  spread?: number;
  spreadPct?: number;
}

interface TradeEntryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
  prefillData?: TradeEntryData | null;
  editTrade?: Trade | null;
  currentSpot?: number | null;
  marketQuote?: MarketQuote | null;
  isMarketOpen?: boolean;
}

const COMMON_TAGS = ['0DTE', 'Scalp', 'Swing', 'Earnings', 'News', 'Technical'];

export default function TradeEntryModal({
  isOpen,
  onClose,
  onSaved,
  prefillData,
  editTrade,
  currentSpot,
  marketQuote,
  isMarketOpen = true
}: TradeEntryModalProps) {
  // Form state
  const [symbol, setSymbol] = useState('SPX');
  const [underlying, setUnderlying] = useState('I:SPX');
  const [strategy, setStrategy] = useState<Strategy>('butterfly');
  const [side, setSide] = useState<Side>('call');
  const [strike, setStrike] = useState<string>('');
  const [width, setWidth] = useState<string>('20');
  const [dte, setDte] = useState<string>('0');
  const [entryPrice, setEntryPrice] = useState<string>('');
  const [quantity, setQuantity] = useState<string>('1');
  const [notes, setNotes] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [customTag, setCustomTag] = useState('');

  // Entry mode state
  const [entryMode, setEntryMode] = useState<EntryMode>('instant');
  const [entryTime, setEntryTime] = useState<string>('');
  const [exitTime, setExitTime] = useState<string>('');
  const [limitPrice, setLimitPrice] = useState<string>('');
  const [direction, setDirection] = useState<'long' | 'short'>('long');

  // For closing trades
  const [exitPrice, setExitPrice] = useState<string>('');

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditMode = !!editTrade;
  const isClosingTrade = isEditMode && editTrade?.status === 'open';

  // Check if this is a locked simulated trade (core fields immutable)
  const isLockedSimTrade = useMemo(() => {
    if (!editTrade) return false;
    const trade = editTrade as unknown as { entry_mode?: string; immutable_at?: string };
    return trade.entry_mode === 'simulated' && trade.immutable_at != null;
  }, [editTrade]);

  // Computed spread display for simulated mode
  const spreadDisplay = useMemo(() => {
    if (!marketQuote?.bid || !marketQuote?.ask) return null;
    const spread = marketQuote.ask - marketQuote.bid;
    const spreadPct = (spread / marketQuote.ask) * 100;
    return {
      bid: marketQuote.bid.toFixed(2),
      ask: marketQuote.ask.toFixed(2),
      spread: spread.toFixed(2),
      spreadPct: spreadPct.toFixed(3)
    };
  }, [marketQuote]);

  // Reset/populate form when modal opens or data changes
  useEffect(() => {
    if (!isOpen) return;

    if (editTrade) {
      // Edit mode - populate from existing trade
      setSymbol(editTrade.symbol);
      setUnderlying(editTrade.underlying);
      setStrategy(editTrade.strategy as Strategy);
      setSide(editTrade.side as Side);
      setStrike(editTrade.strike.toString());
      setWidth(editTrade.width?.toString() || '0');
      setDte(editTrade.dte?.toString() || '0');
      setEntryPrice(editTrade.entry_price.toString());
      setQuantity(editTrade.quantity.toString());
      setNotes(editTrade.notes || '');
      // Parse tags from JSON string
      try {
        const tags = typeof editTrade.tags === 'string'
          ? JSON.parse(editTrade.tags)
          : editTrade.tags;
        setSelectedTags(Array.isArray(tags) ? tags : []);
      } catch {
        setSelectedTags([]);
      }
      setExitPrice(editTrade.exit_price?.toString() || '');
      // Entry mode from trade (if available)
      setEntryMode(((editTrade as unknown as { entry_mode?: EntryMode }).entry_mode) || 'instant');
    } else if (prefillData) {
      // New trade with prefill from heatmap
      setSymbol(prefillData.symbol || 'SPX');
      setUnderlying(prefillData.underlying || 'I:SPX');
      setStrategy(prefillData.strategy || 'butterfly');
      setSide(prefillData.side || 'call');
      setStrike(prefillData.strike?.toString() || '');
      setWidth(prefillData.width?.toString() || '20');
      setDte(prefillData.dte?.toString() || '0');
      setEntryPrice(prefillData.entry_price?.toString() || '');
      setQuantity('1');
      setNotes(prefillData.notes || '');
      setSelectedTags(prefillData.tags || []);
      setExitPrice('');
      setEntryMode('instant');
      setEntryTime('');
      setExitTime('');
      setLimitPrice('');
      setDirection('long');
    } else {
      // New trade - reset to defaults
      setSymbol('SPX');
      setUnderlying('I:SPX');
      setStrategy('butterfly');
      setSide('call');
      setStrike('');
      setWidth('20');
      setDte('0');
      setEntryPrice('');
      setQuantity('1');
      setNotes('');
      setSelectedTags([]);
      setExitPrice('');
      setEntryMode('instant');
      setEntryTime('');
      setExitTime('');
      setLimitPrice('');
      setDirection('long');
    }

    setError(null);
  }, [isOpen, editTrade, prefillData]);

  const toggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag)
        ? prev.filter(t => t !== tag)
        : [...prev, tag]
    );
  };

  const addCustomTag = () => {
    if (customTag && !selectedTags.includes(customTag)) {
      setSelectedTags(prev => [...prev, customTag]);
      setCustomTag('');
    }
  };

  const handleSave = async () => {
    // Validation based on entry mode
    if (entryMode === 'simulated') {
      if (!strike || !limitPrice) {
        setError('Strike and limit price are required for simulated orders');
        return;
      }
    } else if (entryMode === 'freeform') {
      if (!strike || !entryPrice || !entryTime) {
        setError('Strike, entry price, and entry time are required for freeform trades');
        return;
      }
    } else {
      if (!strike || !entryPrice) {
        setError('Strike and entry price are required');
        return;
      }
    }

    setSaving(true);
    setError(null);

    try {
      if (isEditMode && editTrade) {
        // Update existing trade
        const updates: Record<string, unknown> = {
          notes,
          tags: selectedTags
        };

        // If closing the trade
        if (isClosingTrade && exitPrice) {
          const closeResponse = await fetch(`${JOURNAL_API}/api/trades/${editTrade.id}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              exit_price: parseFloat(exitPrice),
              exit_spot: currentSpot
            })
          });

          const closeResult = await closeResponse.json();
          if (!closeResult.success) {
            throw new Error(closeResult.error || 'Failed to close trade');
          }
        } else {
          // Just update metadata
          const updateResponse = await fetch(`${JOURNAL_API}/api/trades/${editTrade.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
          });

          const updateResult = await updateResponse.json();
          if (!updateResult.success) {
            throw new Error(updateResult.error || 'Failed to update trade');
          }
        }
      } else if (entryMode === 'simulated') {
        // Create a limit order instead of immediate trade
        const orderData = {
          order_type: 'entry',
          symbol,
          direction,
          limit_price: parseFloat(limitPrice),
          quantity: parseInt(quantity) || 1,
          strategy,
          notes
        };

        const response = await fetch(`${JOURNAL_API}/api/orders`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(orderData)
        });

        const result = await response.json();
        if (!result.success) {
          throw new Error(result.error || 'Failed to create order');
        }
      } else {
        // Create new trade (instant or freeform)
        const tradeData: Record<string, unknown> = {
          symbol,
          underlying,
          strategy,
          side,
          strike: parseFloat(strike),
          width: parseInt(width) || 0,
          dte: parseInt(dte) || 0,
          entry_price: parseFloat(entryPrice),
          entry_spot: currentSpot,
          quantity: parseInt(quantity) || 1,
          notes,
          tags: selectedTags,
          source: prefillData?.source || 'manual',
          max_profit: prefillData?.max_profit,
          max_loss: prefillData?.max_loss,
          entry_mode: entryMode
        };

        // Freeform mode: include entry_time and optional exit details
        if (entryMode === 'freeform') {
          tradeData.entry_time = entryTime;
          if (exitTime && exitPrice) {
            tradeData.exit_time = exitTime;
            tradeData.exit_price = parseFloat(exitPrice);
            tradeData.exit_spot = currentSpot;
          }
        }

        const response = await fetch(`${JOURNAL_API}/api/trades`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(tradeData)
        });

        const result = await response.json();
        if (!result.success) {
          throw new Error(result.error || 'Failed to create trade');
        }
      }

      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!editTrade || !confirm('Are you sure you want to delete this trade?')) return;

    setSaving(true);
    try {
      const response = await fetch(`${JOURNAL_API}/api/trades/${editTrade.id}`, {
        method: 'DELETE'
      });

      const result = await response.json();
      if (!result.success) {
        throw new Error(result.error || 'Failed to delete trade');
      }

      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="trade-entry-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{isEditMode ? 'Edit Trade' : 'New Trade'}</h3>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          {error && <div className="modal-error">{error}</div>}

          {/* Locked Sim Trade Notice */}
          {isLockedSimTrade && (
            <div className="locked-sim-notice">
              <span className="lock-icon">🔒</span>
              <div className="lock-text">
                <strong>Time-anchored position</strong>
                <span>Core fields are locked to preserve trade truth. Notes and tags remain editable.</span>
              </div>
            </div>
          )}

          {/* Entry Mode Toggle */}
          {!isEditMode && (
            <div className="entry-mode-toggle">
              <button
                type="button"
                className={`mode-btn ${entryMode === 'instant' ? 'active' : ''}`}
                onClick={() => setEntryMode('instant')}
              >
                Instant
              </button>
              <button
                type="button"
                className={`mode-btn ${entryMode === 'freeform' ? 'active' : ''}`}
                onClick={() => setEntryMode('freeform')}
              >
                Freeform
              </button>
              <button
                type="button"
                className={`mode-btn ${entryMode === 'simulated' ? 'active' : ''} ${!isMarketOpen ? 'disabled' : ''}`}
                onClick={() => isMarketOpen && setEntryMode('simulated')}
                disabled={!isMarketOpen}
                title={!isMarketOpen ? 'Available during market hours (9:30 AM - 4:00 PM ET)' : 'Simulated trading with limit orders'}
              >
                Simulated
              </button>
            </div>
          )}

          {/* Market Hours Notice for Simulated Mode */}
          {entryMode === 'simulated' && !isMarketOpen && (
            <div className="market-hours-notice">
              Simulated trading is only available during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
            </div>
          )}

          {/* Simulated Mode: Direction Selector */}
          {entryMode === 'simulated' && (
            <div className="form-row">
              <div className="form-group direction-group">
                <label>Direction</label>
                <div className="radio-group">
                  <label className={`radio-option ${direction === 'long' ? 'active call' : ''}`}>
                    <input
                      type="radio"
                      name="direction"
                      value="long"
                      checked={direction === 'long'}
                      onChange={() => setDirection('long')}
                    />
                    Long
                  </label>
                  <label className={`radio-option ${direction === 'short' ? 'active put' : ''}`}>
                    <input
                      type="radio"
                      name="direction"
                      value="short"
                      checked={direction === 'short'}
                      onChange={() => setDirection('short')}
                    />
                    Short
                  </label>
                </div>
              </div>
            </div>
          )}

          <div className="form-row">
            <div className="form-group">
              <label>Symbol</label>
              <select
                value={underlying}
                onChange={(e) => {
                  setUnderlying(e.target.value);
                  setSymbol(e.target.value === 'I:SPX' ? 'SPX' : 'NDX');
                }}
                disabled={isEditMode}
              >
                <option value="I:SPX">SPX</option>
                <option value="I:NDX">NDX</option>
              </select>
            </div>

            <div className="form-group">
              <label>DTE</label>
              <input
                type="number"
                value={dte}
                onChange={(e) => setDte(e.target.value)}
                min="0"
                disabled={isEditMode}
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group strategy-group">
              <label>Strategy</label>
              <div className="radio-group">
                {(['single', 'vertical', 'butterfly'] as Strategy[]).map(s => (
                  <label key={s} className={`radio-option ${strategy === s ? 'active' : ''}`}>
                    <input
                      type="radio"
                      name="strategy"
                      value={s}
                      checked={strategy === s}
                      onChange={() => setStrategy(s)}
                      disabled={isEditMode}
                    />
                    {s === 'single' ? 'Single' : s === 'vertical' ? 'Vertical' : 'Butterfly'}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group side-group">
              <label>Side</label>
              <div className="radio-group">
                <label className={`radio-option ${side === 'call' ? 'active call' : ''}`}>
                  <input
                    type="radio"
                    name="side"
                    value="call"
                    checked={side === 'call'}
                    onChange={() => setSide('call')}
                    disabled={isEditMode}
                  />
                  Call
                </label>
                <label className={`radio-option ${side === 'put' ? 'active put' : ''}`}>
                  <input
                    type="radio"
                    name="side"
                    value="put"
                    checked={side === 'put'}
                    onChange={() => setSide('put')}
                    disabled={isEditMode}
                  />
                  Put
                </label>
              </div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Strike</label>
              <input
                type="number"
                value={strike}
                onChange={(e) => setStrike(e.target.value)}
                placeholder={currentSpot ? currentSpot.toFixed(0) : ''}
                step={underlying === 'I:SPX' ? 5 : 50}
                disabled={isEditMode}
              />
            </div>

            {strategy !== 'single' && (
              <div className="form-group">
                <label>Width</label>
                <input
                  type="number"
                  value={width}
                  onChange={(e) => setWidth(e.target.value)}
                  step={underlying === 'I:SPX' ? 5 : 50}
                  disabled={isEditMode}
                />
              </div>
            )}
          </div>

          {/* Price Fields - vary by entry mode */}
          {entryMode === 'simulated' ? (
            <>
              <div className="form-row">
                <div className="form-group">
                  <label>Limit Price ($)</label>
                  <input
                    type="number"
                    value={limitPrice}
                    onChange={(e) => setLimitPrice(e.target.value)}
                    step="0.01"
                    min="0"
                    placeholder={currentSpot ? currentSpot.toFixed(2) : ''}
                  />
                </div>

                <div className="form-group">
                  <label>Quantity</label>
                  <input
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    min="1"
                  />
                </div>
              </div>

              {/* Spread Indicator for Simulated Mode */}
              {spreadDisplay && (
                <div className="spread-indicator">
                  <span className="spread-label">Market:</span>
                  <span className="spread-bid">Bid: ${spreadDisplay.bid}</span>
                  <span className="spread-divider">|</span>
                  <span className="spread-ask">Ask: ${spreadDisplay.ask}</span>
                  <span className="spread-divider">|</span>
                  <span className="spread-value">Spread: ${spreadDisplay.spread} ({spreadDisplay.spreadPct}%)</span>
                </div>
              )}

              <div className="simulated-note">
                Orders auto-expire at market close (4:00 PM ET). Trades auto-close at EOD.
              </div>
            </>
          ) : entryMode === 'freeform' ? (
            <>
              <div className="form-row">
                <div className="form-group">
                  <label>Entry Time</label>
                  <input
                    type="datetime-local"
                    value={entryTime}
                    onChange={(e) => setEntryTime(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Entry Price ($)</label>
                  <input
                    type="number"
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    step="0.01"
                    min="0"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Exit Time (optional)</label>
                  <input
                    type="datetime-local"
                    value={exitTime}
                    onChange={(e) => setExitTime(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Exit Price ($) {exitTime ? '' : '(optional)'}</label>
                  <input
                    type="number"
                    value={exitPrice}
                    onChange={(e) => setExitPrice(e.target.value)}
                    step="0.01"
                    min="0"
                    placeholder={exitTime ? 'Required if exit time set' : ''}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Quantity</label>
                  <input
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    min="1"
                  />
                </div>
              </div>

              {exitTime && exitPrice && (
                <div className="freeform-preview">
                  This trade will be created as CLOSED with P&L: {(() => {
                    const pnl = (parseFloat(exitPrice) - parseFloat(entryPrice)) * 100 * parseInt(quantity || '1');
                    const formatted = Math.abs(pnl).toFixed(2);
                    return pnl >= 0
                      ? <span className="profit">+${formatted}</span>
                      : <span className="loss">-${formatted}</span>;
                  })()}
                </div>
              )}
            </>
          ) : (
            /* Instant mode - current behavior */
            <div className="form-row">
              <div className="form-group">
                <label>Entry Price ($)</label>
                <input
                  type="number"
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)}
                  step="0.01"
                  min="0"
                  disabled={isEditMode}
                />
              </div>

              <div className="form-group">
                <label>Quantity</label>
                <input
                  type="number"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  min="1"
                  disabled={isEditMode}
                />
              </div>
            </div>
          )}

          {isClosingTrade && (
            <div className="form-row close-trade-section">
              <div className="form-group">
                <label>Exit Price ($)</label>
                <input
                  type="number"
                  value={exitPrice}
                  onChange={(e) => setExitPrice(e.target.value)}
                  step="0.01"
                  min="0"
                  placeholder="Enter to close trade"
                />
              </div>
              {exitPrice && (
                <div className="close-preview">
                  P&L: {(() => {
                    const pnl = (parseFloat(exitPrice) - parseFloat(entryPrice)) * 100 * parseInt(quantity);
                    const formatted = Math.abs(pnl).toFixed(2);
                    return pnl >= 0
                      ? <span className="profit">+${formatted}</span>
                      : <span className="loss">-${formatted}</span>;
                  })()}
                </div>
              )}
            </div>
          )}

          <div className="form-group">
            <label>Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Trade rationale, setup, etc..."
              rows={2}
            />
          </div>

          <div className="form-group">
            <label>Tags</label>
            <div className="tags-container">
              {COMMON_TAGS.map(tag => (
                <button
                  key={tag}
                  type="button"
                  className={`tag-btn ${selectedTags.includes(tag) ? 'active' : ''}`}
                  onClick={() => toggleTag(tag)}
                >
                  {tag}
                </button>
              ))}
              {selectedTags.filter(t => !COMMON_TAGS.includes(t)).map(tag => (
                <button
                  key={tag}
                  type="button"
                  className="tag-btn active custom"
                  onClick={() => toggleTag(tag)}
                >
                  {tag} &times;
                </button>
              ))}
              <div className="tag-input-group">
                <input
                  type="text"
                  value={customTag}
                  onChange={(e) => setCustomTag(e.target.value)}
                  placeholder="+"
                  className="tag-input"
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCustomTag())}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          {isEditMode && (
            <button
              type="button"
              className="btn btn-danger"
              onClick={handleDelete}
              disabled={saving}
            >
              Delete
            </button>
          )}
          <div className="footer-spacer" />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || (entryMode === 'simulated' && !isMarketOpen)}
          >
            {saving
              ? 'Saving...'
              : isClosingTrade && exitPrice
                ? 'Close Trade'
                : entryMode === 'simulated'
                  ? 'Place Order'
                  : 'Save Trade'}
          </button>
        </div>
      </div>
    </div>
  );
}
