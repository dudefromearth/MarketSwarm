// src/components/AlertCreationModal.tsx
import { useState, useEffect } from 'react';
import '../styles/alert-modal.css';
import type { AlertType, AlertCondition, AlertBehavior } from '../types/alerts';

// Alert types supported by this modal UI (subset of all AlertType)
type SupportedAlertType = 'price' | 'debit' | 'profit_target' | 'trailing_stop' | 'ai_theta_gamma';

// Conditions supported by this modal UI (subset of AlertCondition)
type SupportedCondition = 'above' | 'below' | 'at';

// For editing existing alerts
export interface EditingAlertData {
  id: string;
  type: AlertType;
  condition: AlertCondition;
  targetValue: number;
  color: string;
  behavior: AlertBehavior;
  minProfitThreshold?: number;
}

interface AlertCreationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (alert: {
    id?: string; // Present when editing
    type: AlertType;
    condition: AlertCondition;
    targetValue: number;
    color: string;
    behavior: AlertBehavior;
    minProfitThreshold?: number;
  }) => void;
  strategyLabel: string;
  currentSpot: number | null;
  currentDebit: number | null;
  // Pre-fill from right-click on chart
  initialPrice?: number | null;
  initialCondition?: SupportedCondition;
  // For editing existing alerts
  editingAlert?: EditingAlertData | null;
}

const ALERT_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e',
  '#14b8a6', '#3b82f6', '#8b5cf6', '#ec4899',
];

const ALERT_TYPES: { value: SupportedAlertType; label: string; description: string }[] = [
  { value: 'ai_theta_gamma', label: 'AI Theta/Gamma', description: 'Dynamic safe zone based on theta decay and gamma risk' },
  { value: 'price', label: 'Spot Price', description: 'Alert when underlying price crosses a level' },
  { value: 'profit_target', label: 'Profit Target', description: 'Alert when position profit reaches target' },
  { value: 'trailing_stop', label: 'Trailing Stop', description: 'Alert that follows profit and triggers on pullback' },
  { value: 'debit', label: 'Debit', description: 'Alert based on position debit/credit' },
];

export default function AlertCreationModal({
  isOpen,
  onClose,
  onSave,
  strategyLabel,
  currentSpot,
  currentDebit: _currentDebit,
  initialPrice,
  initialCondition,
  editingAlert,
}: AlertCreationModalProps) {
  const [type, setType] = useState<SupportedAlertType>('ai_theta_gamma');
  const [condition, setCondition] = useState<SupportedCondition>('below');
  const [targetValue, setTargetValue] = useState('');
  const [color, setColor] = useState(ALERT_COLORS[5]); // Blue default
  const [behavior, setBehavior] = useState<AlertBehavior>('once_only');
  const [minProfitThreshold, setMinProfitThreshold] = useState('50');

  // Supported types/conditions for this modal UI
  const isSupportedType = (t: AlertType): t is SupportedAlertType =>
    ['price', 'debit', 'profit_target', 'trailing_stop', 'ai_theta_gamma'].includes(t);
  const isSupportedCondition = (c: AlertCondition): c is SupportedCondition =>
    ['above', 'below', 'at'].includes(c);

  // Reset form when opened
  useEffect(() => {
    if (isOpen) {
      // If editing an existing alert, pre-fill all fields
      if (editingAlert) {
        // Default to supported types if editing an unsupported alert type
        setType(isSupportedType(editingAlert.type) ? editingAlert.type : 'price');
        setCondition(isSupportedCondition(editingAlert.condition) ? editingAlert.condition : 'below');
        setTargetValue(editingAlert.targetValue.toString());
        setColor(editingAlert.color);
        setBehavior(editingAlert.behavior);
        setMinProfitThreshold(editingAlert.minProfitThreshold !== undefined
          ? (editingAlert.minProfitThreshold * 100).toString()
          : '50');
      }
      // If opened from right-click with price, default to 'price' type
      else if (initialPrice !== undefined && initialPrice !== null) {
        setType('price');
        setTargetValue(initialPrice.toFixed(0));
        setCondition(initialCondition || 'below');
        setColor(ALERT_COLORS[5]);
        setBehavior('once_only');
        setMinProfitThreshold('50');
      } else {
        setType('ai_theta_gamma');
        setTargetValue(currentSpot?.toFixed(0) || '');
        setCondition('below');
        setColor(ALERT_COLORS[5]);
        setBehavior('once_only');
        setMinProfitThreshold('50');
      }
    }
  }, [isOpen, currentSpot, initialPrice, initialCondition, editingAlert]);

  if (!isOpen) return null;

  const handleSave = () => {
    const value = type === 'ai_theta_gamma' ? 0 : parseFloat(targetValue);
    if (type === 'ai_theta_gamma' || !isNaN(value)) {
      onSave({
        id: editingAlert?.id, // Include id when editing
        type,
        condition,
        targetValue: value,
        color,
        behavior,
        minProfitThreshold: type === 'ai_theta_gamma' ? parseFloat(minProfitThreshold) / 100 : undefined,
      });
      onClose();
    }
  };

  const isEditing = !!editingAlert;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="alert-modal-backdrop" onClick={handleBackdropClick}>
      <div className="alert-modal">
        <div className="alert-modal-header">
          <h3>{isEditing ? 'Edit Alert' : 'Create Alert'}</h3>
          <span className="alert-modal-strategy">{strategyLabel}</span>
          <button className="alert-modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="alert-modal-body">
          {/* Alert Type Selection */}
          <div className="alert-type-section">
            <label className="alert-label">Alert Type</label>
            <div className="alert-type-grid">
              {ALERT_TYPES.map(alertType => (
                <button
                  key={alertType.value}
                  className={`alert-type-btn ${type === alertType.value ? 'selected' : ''}`}
                  onClick={() => setType(alertType.value)}
                >
                  <span className="alert-type-name">{alertType.label}</span>
                  <span className="alert-type-desc">{alertType.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Type-specific settings */}
          {type === 'ai_theta_gamma' ? (
            <div className="alert-settings-section">
              <label className="alert-label">Activation Threshold</label>
              <div className="alert-threshold-row">
                <input
                  type="number"
                  value={minProfitThreshold}
                  onChange={(e) => setMinProfitThreshold(e.target.value)}
                  min="10"
                  max="200"
                  step="5"
                  className="alert-input"
                />
                <span className="alert-input-suffix">% of debit profit to activate zone</span>
              </div>
              <p className="alert-help">
                Zone appears when profit exceeds this threshold. Alerts when price exits the safe zone.
              </p>
            </div>
          ) : (
            <div className="alert-settings-section">
              <label className="alert-label">Condition</label>
              <div className="alert-condition-row">
                <select
                  value={condition}
                  onChange={(e) => setCondition(e.target.value as SupportedCondition)}
                  className="alert-select"
                >
                  <option value="above">Price rises above</option>
                  <option value="below">Price falls below</option>
                  <option value="at">Price reaches</option>
                </select>
                <input
                  type="number"
                  value={targetValue}
                  onChange={(e) => setTargetValue(e.target.value)}
                  placeholder={currentSpot?.toFixed(0) || '0'}
                  step="0.01"
                  className="alert-input"
                />
              </div>
              {currentSpot && (
                <p className="alert-help">Current spot: {currentSpot.toFixed(2)}</p>
              )}
            </div>
          )}

          {/* Color Selection */}
          <div className="alert-settings-section">
            <label className="alert-label">Color</label>
            <div className="alert-color-grid">
              {ALERT_COLORS.map(c => (
                <button
                  key={c}
                  className={`alert-color-btn ${color === c ? 'selected' : ''}`}
                  style={{ backgroundColor: c }}
                  onClick={() => setColor(c)}
                />
              ))}
            </div>
          </div>

          {/* Behavior Selection */}
          <div className="alert-settings-section">
            <label className="alert-label">When Triggered</label>
            <select
              value={behavior}
              onChange={(e) => setBehavior(e.target.value as AlertBehavior)}
              className="alert-select full-width"
            >
              <option value="remove_on_hit">Remove alert after triggered</option>
              <option value="once_only">Alert once, keep visible</option>
              <option value="repeat">Alert every time price crosses</option>
            </select>
          </div>
        </div>

        <div className="alert-modal-footer">
          <button className="alert-btn-cancel" onClick={onClose}>Cancel</button>
          <button className="alert-btn-save" onClick={handleSave}>{isEditing ? 'Save Alert' : 'Create Alert'}</button>
        </div>
      </div>
    </div>
  );
}
