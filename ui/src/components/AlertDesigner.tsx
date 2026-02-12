/**
 * AlertDesigner — Rich alert configuration panel
 *
 * Replaces AlertCreationModal with a proper designer surface.
 * Handles threshold alerts: Price, Profit, Delta, Gamma, Theta.
 *
 * Features:
 * - Type selector (segmented buttons)
 * - Condition + Value
 * - Scope selector (single/group/any/all)
 * - Position binding
 * - Goal text input
 * - Live preview (current value vs threshold)
 * - Mode toggle (observe/active)
 * - Color picker
 */

import { useState, useEffect, useMemo } from 'react';
import { useDraggable } from '../hooks/useDraggable';
import type {
  Alert,
  AlertType,
  AlertCondition,
  AlertBehavior,
  AlertMode,
  ThresholdScope,
  GreekName,
} from '../types/alerts';

// Threshold types supported by this designer
type ThresholdType = 'price' | 'profit_target' | 'greeks_threshold';
type GreekSubType = 'delta' | 'gamma' | 'theta';

interface DesignerType {
  key: string;
  label: string;
  alertType: ThresholdType;
  greekName?: GreekSubType;
}

const DESIGNER_TYPES: DesignerType[] = [
  { key: 'price', label: 'Price', alertType: 'price' },
  { key: 'profit', label: 'Profit', alertType: 'profit_target' },
  { key: 'delta', label: 'Delta', alertType: 'greeks_threshold', greekName: 'delta' },
  { key: 'gamma', label: 'Gamma', alertType: 'greeks_threshold', greekName: 'gamma' },
  { key: 'theta', label: 'Theta', alertType: 'greeks_threshold', greekName: 'theta' },
];

const ALERT_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e',
  '#3b82f6', '#8b5cf6', '#ffffff', '#9ca3af',
];

interface StrategyInfo {
  id: string;
  label: string;
}

export interface AlertDesignerProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (alert: {
    id?: string;
    type: AlertType;
    condition: AlertCondition;
    targetValue: number;
    color: string;
    behavior: AlertBehavior;
    goal?: string;
    thresholdScope?: ThresholdScope;
    strategyIds?: string[];
    mode?: AlertMode;
    greekName?: GreekName;
    label?: string;
    strategyId?: string;
  }) => void;

  // Available strategies for position binding
  strategies: StrategyInfo[];

  // Live values for preview
  spotPrice: number;
  totalPnL: number;
  delta: number;
  gamma: number;
  theta: number;
  strategyPnLAtSpot: Record<string, number>;

  // Pre-fill from context
  initialType?: string;       // 'price', 'profit', 'delta', etc.
  initialValue?: number;
  initialCondition?: 'above' | 'below' | 'at';
  initialStrategyId?: string;

  // Editing existing alert
  editingAlert?: Alert | null;
}

export default function AlertDesigner({
  isOpen,
  onClose,
  onSave,
  strategies,
  spotPrice,
  totalPnL,
  delta,
  gamma,
  theta,
  strategyPnLAtSpot,
  initialType,
  initialValue,
  initialCondition,
  initialStrategyId,
  editingAlert,
}: AlertDesignerProps) {
  // Form state
  const [selectedType, setSelectedType] = useState<string>('price');
  const [condition, setCondition] = useState<'above' | 'below' | 'at'>('above');
  const [targetValue, setTargetValue] = useState('');
  const [scope, setScope] = useState<ThresholdScope>('single');
  const [boundStrategyIds, setBoundStrategyIds] = useState<string[]>([]);
  const [goal, setGoal] = useState('');
  const [mode, setMode] = useState<AlertMode>('observe');
  const [color, setColor] = useState(ALERT_COLORS[4]); // blue

  // Draggable panel
  const { dragHandleProps, containerStyle, isDragging } = useDraggable({
    handleSelector: '.alert-designer-header',
    initialCentered: true,
  });

  // Reset form on open
  useEffect(() => {
    if (!isOpen) return;

    if (editingAlert) {
      // Editing — populate from existing alert
      const typeKey = resolveTypeKey(editingAlert);
      setSelectedType(typeKey);
      setCondition((editingAlert.condition as 'above' | 'below' | 'at') || 'above');
      setTargetValue(editingAlert.targetValue.toString());
      setScope((editingAlert as any).thresholdScope || 'single');
      setBoundStrategyIds((editingAlert as any).strategyIds || ('strategyId' in editingAlert && editingAlert.strategyId ? [editingAlert.strategyId] : []));
      setGoal((editingAlert as any).goal || '');
      setMode((editingAlert as any).mode || 'observe');
      setColor(editingAlert.color || ALERT_COLORS[4]);
    } else {
      // New alert — use initial values
      setSelectedType(initialType || 'price');
      setCondition(initialCondition || 'above');
      setTargetValue(initialValue != null ? initialValue.toString() : '');
      setScope(initialStrategyId ? 'single' : 'all');
      setBoundStrategyIds(initialStrategyId ? [initialStrategyId] : []);
      setGoal('');
      setMode('observe');
      setColor(ALERT_COLORS[4]);
    }
  }, [isOpen, editingAlert, initialType, initialValue, initialCondition, initialStrategyId]);

  // Resolve the designer type key from an alert
  function resolveTypeKey(alert: Alert): string {
    if (alert.type === 'greeks_threshold') {
      const gn = (alert as any).greekName || alert.label || 'delta';
      return gn;
    }
    if (alert.type === 'profit_target') return 'profit';
    return alert.type;
  }

  // Current designer type config
  const typeConfig = useMemo(() =>
    DESIGNER_TYPES.find(t => t.key === selectedType) || DESIGNER_TYPES[0],
    [selectedType]
  );

  // Get current live value for preview
  const currentValue = useMemo(() => {
    switch (selectedType) {
      case 'price': return spotPrice;
      case 'profit': {
        if (scope === 'all') return totalPnL;
        if (scope === 'single' && boundStrategyIds.length === 1) {
          return strategyPnLAtSpot[boundStrategyIds[0]] ?? 0;
        }
        if (scope === 'group') {
          return boundStrategyIds.reduce((sum, id) => sum + (strategyPnLAtSpot[id] ?? 0), 0);
        }
        return totalPnL;
      }
      case 'delta': return delta;
      case 'gamma': return gamma;
      case 'theta': return theta;
      default: return 0;
    }
  }, [selectedType, scope, boundStrategyIds, spotPrice, totalPnL, delta, gamma, theta, strategyPnLAtSpot]);

  // Distance to threshold
  const targetNum = parseFloat(targetValue);
  const distance = !isNaN(targetNum) ? currentValue - targetNum : null;
  const conditionMet = !isNaN(targetNum) && (() => {
    switch (condition) {
      case 'above': return currentValue >= targetNum;
      case 'below': return currentValue <= targetNum;
      case 'at': return Math.abs(currentValue - targetNum) < 0.5;
      default: return false;
    }
  })();

  // Format values for display
  const formatValue = (val: number) => {
    switch (selectedType) {
      case 'price': return val.toFixed(0);
      case 'profit': return `$${val.toFixed(0)}`;
      case 'delta': return val.toFixed(1);
      case 'gamma': return val.toFixed(2);
      case 'theta': return `$${val.toFixed(0)}/day`;
      default: return val.toString();
    }
  };

  const handleSave = () => {
    const value = parseFloat(targetValue);
    if (isNaN(value)) return;

    onSave({
      id: editingAlert?.id,
      type: typeConfig.alertType,
      condition,
      targetValue: value,
      color,
      behavior: 'once_only',
      goal: goal.trim() || undefined,
      thresholdScope: scope,
      strategyIds: scope === 'group' ? boundStrategyIds : undefined,
      mode,
      greekName: typeConfig.greekName,
      label: typeConfig.greekName,
      strategyId: scope === 'single' && boundStrategyIds.length === 1 ? boundStrategyIds[0] : undefined,
    });
    onClose();
  };

  // Toggle a strategy in group selection
  const toggleStrategyBound = (id: string) => {
    setBoundStrategyIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  if (!isOpen) return null;

  const isEditing = !!editingAlert;
  const conditionSymbol = condition === 'above' ? '≥' : condition === 'below' ? '≤' : '≈';

  return (
    <div className="alert-designer-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div
        className={`alert-designer ${isDragging ? 'is-dragging' : ''}`}
        ref={dragHandleProps.ref}
        onMouseDown={dragHandleProps.onMouseDown}
        style={containerStyle}
      >
        {/* Header */}
        <div className="alert-designer-header draggable-handle">
          <span className="alert-designer-title">
            {isEditing ? 'Edit Alert' : 'Threshold Alert'}
          </span>
          <button className="alert-designer-close" onClick={onClose}>&times;</button>
        </div>

        {/* Body */}
        <div className="alert-designer-body">
          {/* Type Selector */}
          <div className="designer-section">
            <div className="designer-type-selector">
              {DESIGNER_TYPES.map(dt => (
                <button
                  key={dt.key}
                  className={`designer-type-btn ${selectedType === dt.key ? 'active' : ''}`}
                  onClick={() => setSelectedType(dt.key)}
                >
                  {dt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Condition + Value */}
          <div className="designer-section designer-condition-row">
            <select
              className="designer-select"
              value={condition}
              onChange={e => setCondition(e.target.value as 'above' | 'below' | 'at')}
            >
              <option value="above">Above {conditionSymbol}</option>
              <option value="below">Below {conditionSymbol}</option>
              <option value="at">At {conditionSymbol}</option>
            </select>
            <input
              type="number"
              className="designer-value-input"
              value={targetValue}
              onChange={e => setTargetValue(e.target.value)}
              placeholder={formatValue(currentValue)}
              step={selectedType === 'gamma' ? '0.1' : selectedType === 'delta' ? '1' : '1'}
            />
          </div>

          {/* Scope Selector */}
          <div className="designer-section">
            <label className="designer-label">Scope</label>
            <div className="designer-scope-selector">
              {(['single', 'group', 'any', 'all'] as ThresholdScope[]).map(s => (
                <button
                  key={s}
                  className={`designer-scope-btn ${scope === s ? 'active' : ''}`}
                  onClick={() => setScope(s)}
                >
                  {s === 'single' ? 'Position' : s === 'group' ? 'Group' : s === 'any' ? 'Any' : 'All'}
                </button>
              ))}
            </div>

            {/* Position binding for single/group */}
            {(scope === 'single' || scope === 'group') && strategies.length > 0 && (
              <div className="designer-position-list">
                {strategies.map(s => (
                  <label key={s.id} className="designer-position-item">
                    <input
                      type={scope === 'single' ? 'radio' : 'checkbox'}
                      name="bound-strategy"
                      checked={boundStrategyIds.includes(s.id)}
                      onChange={() => {
                        if (scope === 'single') {
                          setBoundStrategyIds([s.id]);
                        } else {
                          toggleStrategyBound(s.id);
                        }
                      }}
                    />
                    <span>{s.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Goal */}
          <div className="designer-section">
            <label className="designer-label">Goal</label>
            <input
              type="text"
              className="designer-goal-input"
              value={goal}
              onChange={e => setGoal(e.target.value)}
              placeholder='e.g. "Exit if price reaches upper target"'
            />
          </div>

          {/* Live Preview */}
          <div className="designer-section designer-preview">
            <div className="designer-preview-header">Live Preview</div>
            <div className="designer-preview-values">
              <span className="preview-current">
                Current: <strong>{formatValue(currentValue)}</strong>
              </span>
              {distance !== null && (
                <span className="preview-distance">
                  Distance: <strong>{distance >= 0 ? '+' : ''}{selectedType === 'price' ? distance.toFixed(0) + ' pts' : formatValue(distance)}</strong>
                </span>
              )}
            </div>
            <div className={`designer-preview-status ${conditionMet ? 'met' : 'not-met'}`}>
              <span className={`preview-dot ${conditionMet ? 'active' : ''}`} />
              {conditionMet ? 'Condition met' : 'Not triggered'}
            </div>
          </div>

          {/* Mode + Color Row */}
          <div className="designer-section designer-bottom-row">
            <div className="designer-mode-control">
              <label className="designer-label">Mode</label>
              <div className="designer-mode-toggle">
                <button
                  className={`designer-mode-btn ${mode === 'observe' ? 'active' : ''}`}
                  onClick={() => setMode('observe')}
                >
                  Observe
                </button>
                <button
                  className={`designer-mode-btn ${mode === 'active' ? 'active' : ''}`}
                  onClick={() => setMode('active')}
                >
                  Active
                </button>
              </div>
            </div>
            <div className="designer-color-control">
              <label className="designer-label">Color</label>
              <div className="designer-color-grid">
                {ALERT_COLORS.map(c => (
                  <button
                    key={c}
                    className={`designer-color-btn ${color === c ? 'selected' : ''}`}
                    style={{ backgroundColor: c }}
                    onClick={() => setColor(c)}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="alert-designer-footer">
          <button className="designer-btn-cancel" onClick={onClose}>Cancel</button>
          <button
            className="designer-btn-save"
            onClick={handleSave}
            disabled={isNaN(parseFloat(targetValue))}
          >
            {isEditing ? 'Save' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}
