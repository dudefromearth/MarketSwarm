import { useState, useMemo } from 'react';
import FloatingDialog from './FloatingDialog';
import type { AlertIntent } from '../types/alerts';

interface AlertInfo {
  id: string;
  label: string;
  type: string;
  intent: AlertIntent;
}

interface PositionOption {
  id: string;
  label: string;
}

interface Props {
  isOpen: boolean;
  positionLabel: string;
  alerts: AlertInfo[];
  availablePositions: PositionOption[];
  onReassign: (targetPositionId: string) => void;
  onDeleteAlerts: () => void;
  onCancel: () => void;
}

type Action = 'move' | 'remove' | 'create';

export default function OrphanedAlertDialog({
  isOpen,
  positionLabel,
  alerts,
  availablePositions,
  onReassign,
  onDeleteAlerts,
  onCancel,
}: Props) {
  // Default selection: if any alert is strategy_general, default to move; otherwise remove
  const defaultAction = useMemo<Action>(() => {
    const hasGeneral = alerts.some(a => a.intent === 'strategy_general');
    return hasGeneral ? 'move' : 'remove';
  }, [alerts]);

  const [selectedAction, setSelectedAction] = useState<Action>(defaultAction);
  const [targetPositionId, setTargetPositionId] = useState<string>('');

  const canConfirm =
    selectedAction === 'remove' ||
    (selectedAction === 'move' && targetPositionId !== '');

  const handleConfirm = () => {
    if (selectedAction === 'move' && targetPositionId) {
      onReassign(targetPositionId);
    } else if (selectedAction === 'remove') {
      onDeleteAlerts();
    }
  };

  if (!isOpen) return null;

  return (
    <FloatingDialog
      isOpen={isOpen}
      onClose={onCancel}
      title={`Position "${positionLabel}" has ${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`}
      width={460}
      closeOnBackdropClick={false}
    >
      <div className="orphan-dialog">
        <ul className="orphan-alert-list">
          {alerts.map(a => (
            <li key={a.id}>{a.label}</li>
          ))}
        </ul>

        <div className="orphan-options">
          <label className={`orphan-option ${selectedAction === 'move' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="orphan-action"
              value="move"
              checked={selectedAction === 'move'}
              onChange={() => setSelectedAction('move')}
            />
            <span className="orphan-option-text">Move alerts to another position</span>
          </label>
          {selectedAction === 'move' && (
            <div className="orphan-dropdown-wrap">
              <select
                value={targetPositionId}
                onChange={e => setTargetPositionId(e.target.value)}
                className="orphan-dropdown"
              >
                <option value="">Select a position...</option>
                {availablePositions.map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            </div>
          )}

          <label className={`orphan-option ${selectedAction === 'remove' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="orphan-action"
              value="remove"
              checked={selectedAction === 'remove'}
              onChange={() => setSelectedAction('remove')}
            />
            <span className="orphan-option-text">Remove alerts along with this position</span>
          </label>

          <label className="orphan-option disabled">
            <input
              type="radio"
              name="orphan-action"
              value="create"
              disabled
            />
            <span className="orphan-option-text">
              Create a new position for these alerts
              <span className="orphan-coming-soon">Coming soon</span>
            </span>
          </label>
        </div>

        <div className="orphan-actions">
          <button className="orphan-btn orphan-btn-cancel" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="orphan-btn orphan-btn-confirm"
            disabled={!canConfirm}
            onClick={handleConfirm}
          >
            Confirm
          </button>
        </div>
      </div>

      <style>{`
        .orphan-dialog {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .orphan-alert-list {
          margin: 0;
          padding: 0 0 0 20px;
          list-style: disc;
          color: #d1d5db;
          font-size: 14px;
          line-height: 1.6;
        }
        .orphan-options {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .orphan-option {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 12px;
          border-radius: 8px;
          cursor: pointer;
          border: 1px solid transparent;
          transition: background 0.15s, border-color 0.15s;
        }
        .orphan-option:hover:not(.disabled) {
          background: rgba(255, 255, 255, 0.04);
        }
        .orphan-option.selected {
          background: rgba(59, 130, 246, 0.08);
          border-color: rgba(59, 130, 246, 0.3);
        }
        .orphan-option.disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }
        .orphan-option input[type="radio"] {
          accent-color: #3b82f6;
          margin: 0;
        }
        .orphan-option-text {
          font-size: 14px;
          color: #e5e7eb;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .orphan-coming-soon {
          font-size: 11px;
          color: #6b7280;
          background: rgba(107, 114, 128, 0.15);
          padding: 2px 6px;
          border-radius: 4px;
        }
        .orphan-dropdown-wrap {
          padding: 0 12px 4px 34px;
        }
        .orphan-dropdown {
          width: 100%;
          padding: 8px 10px;
          border-radius: 6px;
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: #111114;
          color: #e5e7eb;
          font-size: 13px;
          outline: none;
        }
        .orphan-dropdown:focus {
          border-color: #3b82f6;
        }
        .orphan-actions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
          padding-top: 8px;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
        }
        .orphan-btn {
          padding: 8px 18px;
          border-radius: 6px;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          border: none;
          transition: background 0.15s, opacity 0.15s;
        }
        .orphan-btn-cancel {
          background: rgba(255, 255, 255, 0.06);
          color: #9ca3af;
        }
        .orphan-btn-cancel:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #d1d5db;
        }
        .orphan-btn-confirm {
          background: #3b82f6;
          color: #fff;
        }
        .orphan-btn-confirm:hover:not(:disabled) {
          background: #2563eb;
        }
        .orphan-btn-confirm:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        /* Light theme */
        [data-theme="light"] .orphan-alert-list {
          color: #374151;
        }
        [data-theme="light"] .orphan-option:hover:not(.disabled) {
          background: rgba(0, 0, 0, 0.03);
        }
        [data-theme="light"] .orphan-option.selected {
          background: rgba(59, 130, 246, 0.06);
          border-color: rgba(59, 130, 246, 0.25);
        }
        [data-theme="light"] .orphan-option-text {
          color: #1f2937;
        }
        [data-theme="light"] .orphan-dropdown {
          background: #f9fafb;
          border-color: #d1d5db;
          color: #1f2937;
        }
        [data-theme="light"] .orphan-actions {
          border-top-color: #e5e7eb;
        }
        [data-theme="light"] .orphan-btn-cancel {
          background: #f3f4f6;
          color: #6b7280;
        }
        [data-theme="light"] .orphan-btn-cancel:hover {
          background: #e5e7eb;
          color: #374151;
        }
      `}</style>
    </FloatingDialog>
  );
}
