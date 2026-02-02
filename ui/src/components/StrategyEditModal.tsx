/**
 * StrategyEditModal - Edit existing risk graph strategies
 *
 * Form-based editor for strategy parameters:
 * - Symbol (from available symbols in settings)
 * - Strategy type (butterfly, vertical, single)
 * - Side (call/put)
 * - Strike, Width, DTE, Expiration, Debit
 */

import { useState, useCallback, useEffect } from 'react';

const JOURNAL_API = 'http://localhost:3002';

interface AvailableSymbol {
  symbol: string;
  name: string;
  enabled: boolean;
}

export interface StrategyData {
  id: string;
  strategy: 'butterfly' | 'vertical' | 'single';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
  symbol?: string;
}

interface StrategyEditModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (strategy: StrategyData) => void;
  strategy: StrategyData | null;
}

export default function StrategyEditModal({ isOpen, onClose, onSave, strategy }: StrategyEditModalProps) {
  const [availableSymbols, setAvailableSymbols] = useState<AvailableSymbol[]>([]);
  const [symbol, setSymbol] = useState<string>('SPX');
  const [strategyType, setStrategyType] = useState<'butterfly' | 'vertical' | 'single'>('butterfly');
  const [side, setSide] = useState<'call' | 'put'>('call');
  const [strike, setStrike] = useState<string>('');
  const [width, setWidth] = useState<string>('');
  const [dte, setDte] = useState<string>('');
  const [debit, setDebit] = useState<string>('');

  // Fetch available symbols when modal opens
  useEffect(() => {
    if (isOpen) {
      fetch(`${JOURNAL_API}/api/symbols`, { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data) {
            // Only show enabled symbols
            const enabled = data.data.filter((s: AvailableSymbol) => s.enabled);
            setAvailableSymbols(enabled);
          }
        })
        .catch(err => console.error('Failed to fetch symbols:', err));
    }
  }, [isOpen]);

  // Populate form when strategy changes
  useEffect(() => {
    if (strategy) {
      setSymbol(strategy.symbol || 'SPX');
      setStrategyType(strategy.strategy);
      setSide(strategy.side);
      setStrike(strategy.strike.toString());
      setWidth(strategy.width.toString());
      setDte(strategy.dte.toString());
      setDebit(strategy.debit !== null ? strategy.debit.toString() : '');
    }
  }, [strategy]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  const handleSave = useCallback(() => {
    if (!strategy) return;

    const strikeNum = parseFloat(strike);
    const widthNum = parseFloat(width) || 0;
    const dteNum = parseInt(dte) || 0;
    const debitNum = debit ? parseFloat(debit) : null;

    if (isNaN(strikeNum) || strikeNum <= 0) return;
    if (strategyType !== 'single' && widthNum <= 0) return;

    // Calculate expiration from DTE
    const expDate = new Date();
    expDate.setDate(expDate.getDate() + dteNum);
    const expiration = expDate.toISOString().split('T')[0];

    onSave({
      id: strategy.id,
      symbol,
      strategy: strategyType,
      side,
      strike: strikeNum,
      width: strategyType === 'single' ? 0 : widthNum,
      dte: dteNum,
      expiration,
      debit: debitNum,
    });

    onClose();
  }, [strategy, symbol, strategyType, side, strike, width, dte, debit, onSave, onClose]);

  const isValid = () => {
    const strikeNum = parseFloat(strike);
    const widthNum = parseFloat(width);
    const dteNum = parseInt(dte);

    if (!symbol) return false;
    if (isNaN(strikeNum) || strikeNum <= 0) return false;
    if (strategyType !== 'single' && (isNaN(widthNum) || widthNum <= 0)) return false;
    if (isNaN(dteNum) || dteNum < 0) return false;

    return true;
  };

  if (!isOpen || !strategy) return null;

  return (
    <div className="strategy-edit-overlay" onClick={handleClose}>
      <div className="strategy-edit-modal" onClick={e => e.stopPropagation()}>
        <div className="strategy-edit-header">
          <h3>Edit Strategy</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        <div className="strategy-edit-body">
          {/* Symbol */}
          <div className="form-group">
            <label>Symbol</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="symbol-select"
            >
              {/* Always include current symbol even if not in list */}
              {symbol && !availableSymbols.find(s => s.symbol === symbol) && (
                <option value={symbol}>{symbol}</option>
              )}
              {availableSymbols.map(s => (
                <option key={s.symbol} value={s.symbol}>
                  {s.symbol} - {s.name}
                </option>
              ))}
            </select>
          </div>

          {/* Strategy Type */}
          <div className="form-group">
            <label>Strategy Type</label>
            <div className="button-group">
              <button
                className={`btn-option ${strategyType === 'butterfly' ? 'active' : ''}`}
                onClick={() => setStrategyType('butterfly')}
              >
                Butterfly
              </button>
              <button
                className={`btn-option ${strategyType === 'vertical' ? 'active' : ''}`}
                onClick={() => setStrategyType('vertical')}
              >
                Vertical
              </button>
              <button
                className={`btn-option ${strategyType === 'single' ? 'active' : ''}`}
                onClick={() => setStrategyType('single')}
              >
                Single
              </button>
            </div>
          </div>

          {/* Side */}
          <div className="form-group">
            <label>Side</label>
            <div className="button-group">
              <button
                className={`btn-option side-call ${side === 'call' ? 'active' : ''}`}
                onClick={() => setSide('call')}
              >
                Call
              </button>
              <button
                className={`btn-option side-put ${side === 'put' ? 'active' : ''}`}
                onClick={() => setSide('put')}
              >
                Put
              </button>
            </div>
          </div>

          {/* Strike */}
          <div className="form-group">
            <label>Strike</label>
            <input
              type="number"
              value={strike}
              onChange={e => setStrike(e.target.value)}
              placeholder="6000"
              min="0"
              step="5"
            />
          </div>

          {/* Width (disabled for single) */}
          <div className="form-group">
            <label>Width {strategyType === 'single' && <span className="hint">(N/A for single)</span>}</label>
            <input
              type="number"
              value={strategyType === 'single' ? '' : width}
              onChange={e => setWidth(e.target.value)}
              placeholder="10"
              min="0"
              step="5"
              disabled={strategyType === 'single'}
            />
          </div>

          {/* DTE */}
          <div className="form-group">
            <label>Days to Expiration</label>
            <input
              type="number"
              value={dte}
              onChange={e => setDte(e.target.value)}
              placeholder="0"
              min="0"
              step="1"
            />
          </div>

          {/* Debit */}
          <div className="form-group">
            <label>Debit <span className="hint">(optional)</span></label>
            <input
              type="number"
              value={debit}
              onChange={e => setDebit(e.target.value)}
              placeholder="2.50"
              min="0"
              step="0.05"
            />
          </div>

          {/* Preview */}
          <div className="strategy-preview-mini">
            <span className="preview-label">Preview:</span>
            <span className="preview-value">
              {symbol}
              {' '}{strategyType === 'butterfly' ? 'BF' : strategyType === 'vertical' ? 'VS' : 'SGL'}
              {' '}{strike || '—'}
              {strategyType !== 'single' && width && `/${width}w`}
              {' '}{side.charAt(0).toUpperCase()}
              {' '}{dte || '0'}d
              {debit && ` @$${debit}`}
            </span>
          </div>
        </div>

        <div className="strategy-edit-footer">
          <button className="btn btn-cancel" onClick={handleClose}>
            Cancel
          </button>
          <button
            className="btn btn-save"
            onClick={handleSave}
            disabled={!isValid()}
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
