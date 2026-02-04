// src/components/ButterflyEntryAlertCreator.tsx
/**
 * Component for creating butterfly entry detection alerts.
 * Allows configuration of support types to monitor, market mode thresholds,
 * and LFI score thresholds for OTM butterfly entry detection.
 */

import { useState } from 'react';
import type { SupportType, AlertBehavior } from '../types/alerts';
import '../styles/alert-modal.css';

interface ButterflyEntryAlertCreatorProps {
  onSave: (config: {
    supportTypes: SupportType[];
    minMarketModeScore: number;
    minLfiScore: number;
    behavior: AlertBehavior;
    color: string;
    label?: string;
  }) => void;
  onCancel: () => void;
  strategyLabel?: string;
}

const SUPPORT_TYPE_INFO: { value: SupportType; label: string; description: string }[] = [
  { value: 'gex', label: 'GEX Wall', description: 'High positive gamma = dealers buy dips' },
  { value: 'poc', label: 'Volume POC', description: 'Point of control = highest volume acceptance' },
  { value: 'val', label: 'Value Area Low', description: 'VAL = lower boundary of value range' },
  { value: 'hvn', label: 'High Volume Nodes', description: 'HVNs = secondary support zones' },
  { value: 'zero_gamma', label: 'Zero Gamma', description: 'GEX pivot point / inflection level' },
];

const ALERT_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e',
  '#14b8a6', '#3b82f6', '#8b5cf6', '#ec4899',
];

export default function ButterflyEntryAlertCreator({
  onSave,
  onCancel,
  strategyLabel,
}: ButterflyEntryAlertCreatorProps) {
  const [supportTypes, setSupportTypes] = useState<SupportType[]>(['gex', 'poc', 'val']);
  const [minMarketModeScore, setMinMarketModeScore] = useState(50);
  const [minLfiScore, setMinLfiScore] = useState(50);
  const [behavior, setBehavior] = useState<AlertBehavior>('once_only');
  const [color, setColor] = useState(ALERT_COLORS[3]); // Green default
  const [label, setLabel] = useState('');

  const toggleSupportType = (type: SupportType) => {
    setSupportTypes(prev =>
      prev.includes(type)
        ? prev.filter(t => t !== type)
        : [...prev, type]
    );
  };

  const handleSave = () => {
    if (supportTypes.length === 0) {
      return; // Require at least one support type
    }
    onSave({
      supportTypes,
      minMarketModeScore,
      minLfiScore,
      behavior,
      color,
      label: label || undefined,
    });
  };

  return (
    <div className="alert-modal-body">
      {strategyLabel && (
        <div className="alert-settings-section">
          <span className="alert-modal-strategy">{strategyLabel}</span>
        </div>
      )}

      {/* Support Types Selection */}
      <div className="alert-settings-section">
        <label className="alert-label">Support Types to Monitor</label>
        <p className="alert-help" style={{ marginBottom: '8px' }}>
          Select which support levels should trigger entry alerts
        </p>
        <div className="alert-type-grid" style={{ gridTemplateColumns: '1fr' }}>
          {SUPPORT_TYPE_INFO.map(info => (
            <button
              key={info.value}
              className={`alert-type-btn ${supportTypes.includes(info.value) ? 'selected' : ''}`}
              onClick={() => toggleSupportType(info.value)}
              style={{ textAlign: 'left' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{
                  width: '16px',
                  height: '16px',
                  border: '2px solid currentColor',
                  borderRadius: '3px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '12px',
                }}>
                  {supportTypes.includes(info.value) ? '✓' : ''}
                </span>
                <span className="alert-type-name">{info.label}</span>
              </div>
              <span className="alert-type-desc">{info.description}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Market Mode Threshold */}
      <div className="alert-settings-section">
        <label className="alert-label">Max Market Mode Score</label>
        <div className="alert-threshold-row">
          <input
            type="range"
            min="0"
            max="100"
            value={minMarketModeScore}
            onChange={(e) => setMinMarketModeScore(parseInt(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ minWidth: '40px', textAlign: 'right' }}>{minMarketModeScore}</span>
        </div>
        <p className="alert-help">
          Only alert when market mode is below this (0-33 = compression, ideal for butterflies)
        </p>
      </div>

      {/* LFI Score Threshold */}
      <div className="alert-settings-section">
        <label className="alert-label">Min LFI Score (Absorbing)</label>
        <div className="alert-threshold-row">
          <input
            type="range"
            min="0"
            max="100"
            value={minLfiScore}
            onChange={(e) => setMinLfiScore(parseInt(e.target.value))}
            style={{ flex: 1 }}
          />
          <span style={{ minWidth: '40px', textAlign: 'right' }}>{minLfiScore}</span>
        </div>
        <p className="alert-help">
          Require absorbing regime (LFI &gt; 50) for mean reversion setups
        </p>
      </div>

      {/* Optional Label */}
      <div className="alert-settings-section">
        <label className="alert-label">Label (optional)</label>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g., Morning bounce watch"
          className="alert-input full-width"
        />
      </div>

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
          <option value="repeat">Alert on each new entry setup</option>
        </select>
      </div>

      {/* Action Buttons */}
      <div className="alert-modal-footer" style={{ marginTop: '16px', padding: 0, borderTop: 'none' }}>
        <button className="alert-btn-cancel" onClick={onCancel}>Cancel</button>
        <button
          className="alert-btn-save"
          onClick={handleSave}
          disabled={supportTypes.length === 0}
        >
          Create Entry Alert
        </button>
      </div>
    </div>
  );
}
