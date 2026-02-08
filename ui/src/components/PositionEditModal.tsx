/**
 * PositionEditModal - Edit existing risk graph positions with leg-based editing
 *
 * Features:
 * - Individual leg editing (strike, expiration, quantity)
 * - Real-time position type recognition as legs change
 * - Warning for asymmetric structures
 * - Symbol selection from available symbols
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useDraggable } from '../hooks/useDraggable';
import type { PositionLeg, PositionType, PositionDirection, CostBasisType } from '../types/riskGraph';
import { recognizePositionType, strategyToLegs } from '../utils/positionRecognition';
import { formatLegsDisplay, formatPositionLabel } from '../utils/positionFormatting';

const JOURNAL_API = '';

interface AvailableSymbol {
  symbol: string;
  name: string;
  enabled: boolean;
}

// Legacy strategy data format (for backward compatibility)
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
  // New leg-based fields
  legs?: PositionLeg[];
  positionType?: PositionType;
  direction?: PositionDirection;
  // Cost basis (debit = you paid, credit = you received)
  costBasis?: number | null;
  costBasisType?: CostBasisType;
}

interface PositionEditModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (strategy: StrategyData) => void;
  strategy: StrategyData | null;
}

export default function PositionEditModal({ isOpen, onClose, onSave, strategy }: PositionEditModalProps) {
  const [availableSymbols, setAvailableSymbols] = useState<AvailableSymbol[]>([]);
  const [symbol, setSymbol] = useState<string>('SPX');

  // Draggable modal
  const { dragHandleProps, containerStyle, isDragging } = useDraggable({
    handleSelector: '.position-edit-header',
    initialCentered: true,
  });

  // Leg-based state
  const [legs, setLegs] = useState<PositionLeg[]>([]);
  const [costBasis, setCostBasis] = useState<string>('');
  const [costBasisType, setCostBasisType] = useState<CostBasisType>('debit');

  // Fetch available symbols when modal opens
  useEffect(() => {
    if (isOpen) {
      fetch(`${JOURNAL_API}/api/symbols`, { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data) {
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

      // Set cost basis (prefer new fields, fall back to legacy debit)
      const basis = strategy.costBasis ?? strategy.debit ?? null;
      setCostBasis(basis !== null ? basis.toString() : '');
      setCostBasisType(strategy.costBasisType || 'debit');

      // Convert legacy strategy to legs if needed
      if (strategy.legs && strategy.legs.length > 0) {
        setLegs([...strategy.legs]);
      } else {
        const derivedLegs = strategyToLegs(
          strategy.strategy,
          strategy.side,
          strategy.strike,
          strategy.width,
          strategy.expiration
        );
        setLegs(derivedLegs);
      }
    }
  }, [strategy]);

  // Recognize position type from current legs
  const recognition = useMemo(() => {
    if (legs.length === 0) {
      return { type: 'custom' as PositionType, direction: 'long' as PositionDirection, isSymmetric: true };
    }
    return recognizePositionType(legs);
  }, [legs]);

  const positionType = recognition.type;
  const direction = recognition.direction;
  const isAsymmetric = recognition.isSymmetric === false;

  // Get formatted position label
  const positionLabel = useMemo(() => {
    return formatPositionLabel(positionType, direction, legs);
  }, [positionType, direction, legs]);

  // Get formatted legs display
  const legsNotation = useMemo(() => {
    return formatLegsDisplay(legs);
  }, [legs]);

  // Calculate DTE from primary expiration
  const dte = useMemo(() => {
    if (legs.length === 0) return 0;
    const expirations = legs.map(l => l.expiration);
    expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    const primaryExp = expirations[0];
    const expDate = new Date(primaryExp + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffTime = expDate.getTime() - today.getTime();
    return Math.max(0, Math.ceil(diffTime / (1000 * 60 * 60 * 24)));
  }, [legs]);

  // Update a specific leg
  const updateLeg = useCallback((index: number, updates: Partial<PositionLeg>) => {
    setLegs(prev => {
      const newLegs = [...prev];
      newLegs[index] = { ...newLegs[index], ...updates };
      return newLegs;
    });
  }, []);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  const handleSave = useCallback(() => {
    if (!strategy || legs.length === 0) return;

    const costBasisNum = costBasis ? parseFloat(costBasis) : null;

    // Calculate center strike and width for legacy compatibility
    const sortedLegs = [...legs].sort((a, b) => a.strike - b.strike);
    const strikes = sortedLegs.map(l => l.strike);

    let centerStrike = strikes[0];
    let width = 0;

    if (legs.length === 3) {
      // Butterfly: center is middle strike
      centerStrike = strikes[1];
      width = strikes[1] - strikes[0];
    } else if (legs.length === 2) {
      // Vertical: first strike is the anchor
      centerStrike = strikes[0];
      width = strikes[1] - strikes[0];
    } else if (legs.length === 4) {
      // Condor/Iron: use average of inner strikes
      centerStrike = Math.round((strikes[1] + strikes[2]) / 2);
      width = strikes[1] - strikes[0];
    }

    // Get primary expiration
    const expirations = legs.map(l => l.expiration);
    expirations.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
    const primaryExpiration = expirations[0];

    // Determine side from dominant leg type
    const calls = legs.filter(l => l.right === 'call').length;
    const puts = legs.filter(l => l.right === 'put').length;
    const side: 'call' | 'put' = calls >= puts ? 'call' : 'put';

    // Map position type back to legacy strategy type
    let legacyStrategy: 'butterfly' | 'vertical' | 'single' = 'single';
    if (['butterfly', 'bwb'].includes(positionType)) {
      legacyStrategy = 'butterfly';
    } else if (['vertical', 'calendar', 'diagonal'].includes(positionType)) {
      legacyStrategy = 'vertical';
    }

    onSave({
      id: strategy.id,
      symbol,
      strategy: legacyStrategy,
      side,
      strike: centerStrike,
      width,
      dte,
      expiration: primaryExpiration,
      debit: costBasisNum,  // Legacy field
      costBasis: costBasisNum,
      costBasisType,
      legs,
      positionType,
      direction,
    });

    onClose();
  }, [strategy, symbol, legs, costBasis, costBasisType, dte, positionType, direction, onSave, onClose]);

  const isValid = () => {
    if (!symbol) return false;
    if (legs.length === 0) return false;
    // All legs must have valid strikes
    return legs.every(leg => leg.strike > 0 && leg.expiration);
  };

  if (!isOpen || !strategy) return null;

  return (
    <div className="strategy-edit-overlay" onClick={handleClose}>
      <div
        className={`strategy-edit-modal position-edit-modal floating-modal ${isDragging ? 'is-dragging' : ''}`}
        onClick={e => e.stopPropagation()}
        ref={dragHandleProps.ref}
        onMouseDown={dragHandleProps.onMouseDown}
        style={containerStyle}
      >
        <div className="strategy-edit-header position-edit-header draggable-handle">
          <h3>Edit Position</h3>
          <button className="close-btn" onClick={handleClose}>&times;</button>
        </div>

        <div className="strategy-edit-body position-edit-body">
          {/* Symbol */}
          <div className="form-group">
            <label>Symbol</label>
            <select
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              className="symbol-select"
            >
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

          {/* Position Type (derived, read-only) */}
          <div className="form-group">
            <label>Position Type</label>
            <div className="position-type-display">
              <span className={`position-type-badge ${positionType}`}>
                {positionLabel}
              </span>
              {isAsymmetric && (
                <span className="position-asym-warning">
                  Asymmetric wing widths
                </span>
              )}
            </div>
          </div>

          {/* Legs Editor */}
          <div className="form-group legs-editor">
            <label>Legs</label>
            <div className="legs-list">
              {legs.map((leg, index) => (
                <div key={index} className="leg-row">
                  <span className="leg-index">Leg {index + 1}:</span>

                  {/* Quantity */}
                  <select
                    className="leg-quantity"
                    value={leg.quantity}
                    onChange={e => updateLeg(index, { quantity: parseInt(e.target.value) })}
                  >
                    <option value="2">+2</option>
                    <option value="1">+1</option>
                    <option value="-1">-1</option>
                    <option value="-2">-2</option>
                  </select>

                  {/* Strike */}
                  <input
                    type="number"
                    className="leg-strike"
                    value={leg.strike}
                    onChange={e => updateLeg(index, { strike: parseFloat(e.target.value) || 0 })}
                    step="5"
                    min="0"
                  />

                  {/* Right (Call/Put) */}
                  <select
                    className="leg-right"
                    value={leg.right}
                    onChange={e => updateLeg(index, { right: e.target.value as 'call' | 'put' })}
                  >
                    <option value="call">Call</option>
                    <option value="put">Put</option>
                  </select>

                  {/* Expiration */}
                  <input
                    type="date"
                    className="leg-expiration"
                    value={leg.expiration}
                    onChange={e => updateLeg(index, { expiration: e.target.value })}
                  />
                </div>
              ))}
            </div>

            {/* Type change warning */}
            {positionType === 'custom' && legs.length > 1 && (
              <div className="type-change-warning">
                Structure not recognized. Adjust legs to match a known pattern.
              </div>
            )}
          </div>

          {/* Cost Basis (Debit/Credit) */}
          <div className="form-group cost-basis-group">
            <label>Cost Basis <span className="hint">(optional)</span></label>
            <div className="cost-basis-input-row">
              {/* Debit/Credit Toggle */}
              <div className="cost-type-toggle">
                <button
                  type="button"
                  className={`cost-type-btn debit ${costBasisType === 'debit' ? 'active' : ''}`}
                  onClick={() => setCostBasisType('debit')}
                >
                  DR
                </button>
                <button
                  type="button"
                  className={`cost-type-btn credit ${costBasisType === 'credit' ? 'active' : ''}`}
                  onClick={() => setCostBasisType('credit')}
                >
                  CR
                </button>
              </div>
              <span className="cost-basis-dollar">$</span>
              <input
                type="number"
                className="cost-basis-value"
                value={costBasis}
                onChange={e => setCostBasis(e.target.value)}
                placeholder="0.00"
                min="0"
                step="0.05"
              />
            </div>
            <div className="cost-basis-hint">
              {costBasisType === 'debit' ? 'Debit = You paid to open' : 'Credit = You received to open'}
            </div>
          </div>

          {/* Preview */}
          <div className="strategy-preview-mini position-preview">
            <span className="preview-label">Preview:</span>
            <div className="preview-content">
              <div className="preview-header">
                <span className="preview-symbol">{symbol}</span>
                <span className="preview-type">{positionLabel}</span>
                <span className="preview-dte">{dte}d</span>
                {costBasis && (
                  <span className={`preview-cost-basis ${costBasisType}`}>
                    {costBasisType === 'credit' ? 'CR' : 'DR'} ${costBasis}
                  </span>
                )}
              </div>
              <div className="preview-legs">{legsNotation}</div>
            </div>
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
