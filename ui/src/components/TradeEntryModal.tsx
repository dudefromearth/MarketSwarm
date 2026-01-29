// src/components/TradeEntryModal.tsx
import { useState, useEffect } from 'react';
import type { Trade } from './TradeLogPanel';

const JOURNAL_API = 'http://localhost:3002';

type Strategy = 'single' | 'vertical' | 'butterfly';
type Side = 'call' | 'put';

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

interface TradeEntryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
  prefillData?: TradeEntryData | null;
  editTrade?: Trade | null;
  currentSpot?: number | null;
}

const COMMON_TAGS = ['0DTE', 'Scalp', 'Swing', 'Earnings', 'News', 'Technical'];

export default function TradeEntryModal({
  isOpen,
  onClose,
  onSaved,
  prefillData,
  editTrade,
  currentSpot
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

  // For closing trades
  const [exitPrice, setExitPrice] = useState<string>('');

  // UI state
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditMode = !!editTrade;
  const isClosingTrade = isEditMode && editTrade?.status === 'open';

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
      setWidth(editTrade.width.toString());
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
    // Validation
    if (!strike || !entryPrice) {
      setError('Strike and entry price are required');
      return;
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
      } else {
        // Create new trade
        const tradeData = {
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
          max_loss: prefillData?.max_loss
        };

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
            disabled={saving}
          >
            {saving ? 'Saving...' : isClosingTrade && exitPrice ? 'Close Trade' : 'Save Trade'}
          </button>
        </div>
      </div>
    </div>
  );
}
