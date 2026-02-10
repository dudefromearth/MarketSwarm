/**
 * DealerGravitySettings - Configuration panel for Dealer Gravity display
 *
 * Allows users to customize:
 * - Volume Profile visualization (color, width, transparency)
 * - Structural overlay visibility (Volume Nodes, Wells, Crevasses)
 * - GEX panel settings
 *
 * Uses Dealer Gravity lexicon exclusively.
 */

import { useState } from 'react';
import { useDealerGravity } from '../contexts/DealerGravityContext';
import type { DealerGravityConfigUpdate, GexPanelConfigUpdate, RowsLayoutMode } from '../types/dealerGravity';

interface DealerGravitySettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function DealerGravitySettings({ isOpen, onClose }: DealerGravitySettingsProps) {
  const {
    config,
    gexConfig,
    updateConfig,
    updateGexConfig,
    loading,
  } = useDealerGravity();

  const [saving, setSaving] = useState(false);

  if (!isOpen) return null;

  const handleDGUpdate = async (updates: DealerGravityConfigUpdate) => {
    setSaving(true);
    try {
      await updateConfig(updates);
    } finally {
      setSaving(false);
    }
  };

  const handleGexUpdate = async (updates: GexPanelConfigUpdate) => {
    setSaving(true);
    try {
      await updateGexConfig(updates);
    } finally {
      setSaving(false);
    }
  };

  const handleResetToDefaults = async () => {
    setSaving(true);
    try {
      await updateConfig({
        enabled: true,
        mode: 'tv',
        widthPercent: 15,
        rowsLayout: 'number_of_rows',
        rowSize: 24,
        cappingSigma: 2.0,
        color: '#9333ea',
        transparency: 50,
        showVolumeNodes: true,
        showVolumeWells: true,
        showCrevasses: true,
      });
      await updateGexConfig({
        enabled: true,
        mode: 'combined',
        callsColor: '#22c55e',
        putsColor: '#ef4444',
        widthPx: 60,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content dg-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Dealer Gravity Settings</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="loading-state">Loading settings...</div>
          ) : (
            <>
              {/* Volume Profile Section */}
              <section className="settings-section">
                <h3>Volume Profile</h3>

                <div className="setting-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={config?.enabled ?? true}
                      onChange={(e) => handleDGUpdate({ enabled: e.target.checked })}
                      disabled={saving}
                    />
                    Enabled
                  </label>
                </div>

                <div className="setting-row">
                  <label>Mode</label>
                  <select
                    value={config?.mode ?? 'tv'}
                    onChange={(e) => handleDGUpdate({ mode: e.target.value as 'raw' | 'tv' })}
                    disabled={saving}
                  >
                    <option value="tv">TV (Smoothed)</option>
                    <option value="raw">Raw</option>
                  </select>
                </div>

                <div className="setting-row">
                  <label>Rows Layout</label>
                  <select
                    value={config?.rowsLayout ?? 'number_of_rows'}
                    onChange={(e) => handleDGUpdate({ rowsLayout: e.target.value as RowsLayoutMode })}
                    disabled={saving}
                  >
                    <option value="number_of_rows">Number of Rows</option>
                    <option value="ticks_per_row">Ticks per Row</option>
                  </select>
                </div>

                <div className="setting-row">
                  <label>
                    Row Size
                    <span className="setting-hint-inline">
                      {config?.rowsLayout === 'ticks_per_row' ? '(ticks)' : '(rows)'}
                    </span>
                  </label>
                  <input
                    type="number"
                    min={config?.rowsLayout === 'ticks_per_row' ? 1 : 10}
                    max={config?.rowsLayout === 'ticks_per_row' ? 100 : 200}
                    value={config?.rowSize ?? 24}
                    onChange={(e) => handleDGUpdate({ rowSize: parseInt(e.target.value) || 24 })}
                    disabled={saving}
                    className="setting-number-input"
                  />
                </div>

                <div className="setting-row">
                  <label>Color</label>
                  <input
                    type="color"
                    value={config?.color ?? '#9333ea'}
                    onChange={(e) => handleDGUpdate({ color: e.target.value })}
                    disabled={saving}
                  />
                </div>

                <div className="setting-row">
                  <label>Width: {config?.widthPercent ?? 15}%</label>
                  <input
                    type="range"
                    min="5"
                    max="40"
                    value={config?.widthPercent ?? 15}
                    onChange={(e) => handleDGUpdate({ widthPercent: parseInt(e.target.value) })}
                    disabled={saving}
                  />
                </div>

                <div className="setting-row">
                  <label>Transparency: {config?.transparency ?? 50}%</label>
                  <input
                    type="range"
                    min="10"
                    max="90"
                    value={config?.transparency ?? 50}
                    onChange={(e) => handleDGUpdate({ transparency: parseInt(e.target.value) })}
                    disabled={saving}
                  />
                </div>
              </section>

              {/* Structural Overlays Section */}
              <section className="settings-section">
                <h3>Structural Overlays</h3>

                <div className="setting-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={config?.showVolumeNodes ?? true}
                      onChange={(e) => handleDGUpdate({ showVolumeNodes: e.target.checked })}
                      disabled={saving}
                    />
                    Volume Nodes
                  </label>
                  <span className="setting-hint">Zones of concentrated attention</span>
                </div>

                <div className="setting-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={config?.showVolumeWells ?? true}
                      onChange={(e) => handleDGUpdate({ showVolumeWells: e.target.checked })}
                      disabled={saving}
                    />
                    Volume Wells
                  </label>
                  <span className="setting-hint">Zones of neglect (acceleration)</span>
                </div>

                <div className="setting-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={config?.showCrevasses ?? true}
                      onChange={(e) => handleDGUpdate({ showCrevasses: e.target.checked })}
                      disabled={saving}
                    />
                    Crevasses
                  </label>
                  <span className="setting-hint">Extended scarcity regions</span>
                </div>
              </section>

              {/* GEX Panel Section */}
              <section className="settings-section">
                <h3>GEX Panel</h3>

                <div className="setting-row">
                  <label>
                    <input
                      type="checkbox"
                      checked={gexConfig?.enabled ?? true}
                      onChange={(e) => handleGexUpdate({ enabled: e.target.checked })}
                      disabled={saving}
                    />
                    Enabled
                  </label>
                </div>

                <div className="setting-row">
                  <label>Mode</label>
                  <select
                    value={gexConfig?.mode ?? 'combined'}
                    onChange={(e) => handleGexUpdate({ mode: e.target.value as 'combined' | 'net' })}
                    disabled={saving}
                  >
                    <option value="combined">Combined</option>
                    <option value="net">Net</option>
                  </select>
                </div>

                <div className="setting-row">
                  <label>Calls Color</label>
                  <input
                    type="color"
                    value={gexConfig?.callsColor ?? '#22c55e'}
                    onChange={(e) => handleGexUpdate({ callsColor: e.target.value })}
                    disabled={saving}
                  />
                </div>

                <div className="setting-row">
                  <label>Puts Color</label>
                  <input
                    type="color"
                    value={gexConfig?.putsColor ?? '#ef4444'}
                    onChange={(e) => handleGexUpdate({ putsColor: e.target.value })}
                    disabled={saving}
                  />
                </div>

                <div className="setting-row">
                  <label>Width: {gexConfig?.widthPx ?? 60}px</label>
                  <input
                    type="range"
                    min="30"
                    max="120"
                    value={gexConfig?.widthPx ?? 60}
                    onChange={(e) => handleGexUpdate({ widthPx: parseInt(e.target.value) })}
                    disabled={saving}
                  />
                </div>
              </section>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button
            className="btn-secondary"
            onClick={handleResetToDefaults}
            disabled={saving || loading}
          >
            Reset to Defaults
          </button>
          <button
            className="btn-primary"
            onClick={onClose}
            disabled={saving}
          >
            Done
          </button>
        </div>
      </div>

      <style>{`
        .dg-settings-modal {
          max-width: 480px;
          width: 90%;
          background: #1a1a1a;
          border: 1px solid #333;
          border-radius: 8px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }

        .dg-settings-modal .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid #333;
        }

        .dg-settings-modal .modal-header h2 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
          color: #fff;
        }

        .dg-settings-modal .modal-close {
          background: none;
          border: none;
          color: #888;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
        }

        .dg-settings-modal .modal-close:hover {
          color: #fff;
        }

        .dg-settings-modal .modal-body {
          padding: 20px;
          max-height: 60vh;
          overflow-y: auto;
        }

        .dg-settings-modal .modal-footer {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          padding: 16px 20px;
          border-top: 1px solid #333;
        }

        .dg-settings-modal .btn-primary {
          background: #3b82f6;
          color: #fff;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 13px;
        }

        .dg-settings-modal .btn-primary:hover {
          background: #2563eb;
        }

        .dg-settings-modal .btn-secondary {
          background: #333;
          color: #fff;
          border: none;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 13px;
        }

        .dg-settings-modal .btn-secondary:hover {
          background: #444;
        }

        .settings-section {
          margin-bottom: 24px;
        }

        .settings-section h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary, #fff);
          margin-bottom: 12px;
          padding-bottom: 8px;
          border-bottom: 1px solid var(--border-color, #333);
        }

        .setting-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
          gap: 12px;
        }

        .setting-row label {
          display: flex;
          align-items: center;
          gap: 8px;
          color: var(--text-secondary, #aaa);
          font-size: 13px;
        }

        .setting-row input[type="checkbox"] {
          /* inherits global Apple toggle */
        }

        .setting-row input[type="range"] {
          flex: 1;
          max-width: 150px;
        }

        .setting-row input[type="color"] {
          width: 32px;
          height: 24px;
          padding: 0;
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
          cursor: pointer;
        }

        .setting-row select {
          background: var(--input-bg, #1a1a1a);
          color: var(--text-primary, #fff);
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
          padding: 4px 8px;
          font-size: 13px;
        }

        .setting-hint {
          font-size: 11px;
          color: var(--text-muted, #666);
          margin-left: auto;
        }

        .setting-hint-inline {
          font-size: 11px;
          color: var(--text-muted, #666);
          margin-left: 4px;
        }

        .setting-number-input {
          width: 70px;
          background: var(--input-bg, #1a1a1a);
          color: var(--text-primary, #fff);
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
          padding: 4px 8px;
          font-size: 13px;
          text-align: center;
        }

        .setting-number-input::-webkit-inner-spin-button,
        .setting-number-input::-webkit-outer-spin-button {
          opacity: 1;
        }

        .loading-state {
          text-align: center;
          padding: 40px;
          color: var(--text-muted, #666);
        }
      `}</style>
    </div>
  );
}
