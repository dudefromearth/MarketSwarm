// src/components/LogManagerModal.tsx
import { useState, useEffect } from 'react';
import type { TradeLog } from './LogSelector';

const JOURNAL_API = '';

interface LogManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLogId: string | null;
  onSelectLog: (log: TradeLog) => void;
  onLogCreated: () => void;
}

type View = 'list' | 'create';

export default function LogManagerModal({
  isOpen,
  onClose,
  selectedLogId,
  onSelectLog,
  onLogCreated
}: LogManagerModalProps) {
  const [view, setView] = useState<View>('list');
  const [logs, setLogs] = useState<TradeLog[]>([]);
  const [loading, setLoading] = useState(true);

  // Create form state
  const [formName, setFormName] = useState('');
  const [formCapital, setFormCapital] = useState('25000');
  const [formRisk, setFormRisk] = useState('');
  const [formIntent, setFormIntent] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchLogs();
      setView('list');
    }
  }, [isOpen]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${JOURNAL_API}/api/logs`);
      const result = await response.json();
      if (result.success) {
        setLogs(result.data);
      }
    } catch (err) {
      console.error('LogManagerModal fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateLog = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreating(true);

    try {
      const body: Record<string, unknown> = {
        name: formName,
        starting_capital: parseFloat(formCapital),
        intent: formIntent || undefined,
        notes: formNotes || undefined
      };

      if (formRisk) {
        body.risk_per_trade = parseFloat(formRisk);
      }

      const response = await fetch(`${JOURNAL_API}/api/logs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      const result = await response.json();

      if (result.success) {
        // Reset form
        setFormName('');
        setFormCapital('25000');
        setFormRisk('');
        setFormIntent('');
        setFormNotes('');

        // Select the new log
        onSelectLog(result.data);
        onLogCreated();

        // Go back to list
        fetchLogs();
        setView('list');
      } else {
        setError(result.error || 'Failed to create log');
      }
    } catch (err) {
      setError('Unable to connect to journal service');
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteLog = async (logId: string) => {
    if (!confirm('Archive this trade log? You can still view it later.')) {
      return;
    }

    try {
      const response = await fetch(`${JOURNAL_API}/api/logs/${logId}`, {
        method: 'DELETE'
      });

      const result = await response.json();
      if (result.success) {
        fetchLogs();
        onLogCreated();
      }
    } catch (err) {
      console.error('Delete log error:', err);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content log-manager-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{view === 'list' ? 'Trade Logs' : 'Create Trade Log'}</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {view === 'list' ? (
          <>
            <div className="log-list">
              {loading ? (
                <div className="log-list-loading">Loading logs...</div>
              ) : logs.length === 0 ? (
                <div className="log-list-empty">
                  <p>No trade logs yet.</p>
                  <p>Create one to start tracking trades.</p>
                </div>
              ) : (
                logs.map(log => (
                  <div
                    key={log.id}
                    className={`log-list-item ${log.id === selectedLogId ? 'selected' : ''}`}
                    onClick={() => {
                      onSelectLog(log);
                      onClose();
                    }}
                  >
                    <div className="log-item-main">
                      <span className="log-item-indicator">
                        {log.id === selectedLogId ? '*' : ''}
                      </span>
                      <span className="log-item-name">{log.name}</span>
                      <span className="log-item-capital">
                        ${(log.starting_capital / 100).toLocaleString()}
                      </span>
                      <span className="log-item-trades">
                        {log.total_trades} trades
                      </span>
                      <span className={`log-item-pnl ${log.total_pnl >= 0 ? 'profit' : 'loss'}`}>
                        {log.total_pnl >= 0 ? '+' : ''}${(log.total_pnl / 100).toFixed(2)}
                      </span>
                    </div>
                    <div className="log-item-actions">
                      <button
                        className="btn-delete-log"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteLog(log.id);
                        }}
                        title="Archive log"
                      >
                        Archive
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn-create-log"
                onClick={() => setView('create')}
              >
                + New Log
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleCreateLog} className="log-create-form">
            {error && <div className="form-error">{error}</div>}

            <div className="form-group">
              <label htmlFor="log-name">Name *</label>
              <input
                id="log-name"
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g., 0DTE Income, Fat Tail Probes"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="log-capital">Starting Capital ($) *</label>
              <input
                id="log-capital"
                type="number"
                value={formCapital}
                onChange={(e) => setFormCapital(e.target.value)}
                min="100"
                step="100"
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="log-risk">Risk per Trade ($)</label>
              <input
                id="log-risk"
                type="number"
                value={formRisk}
                onChange={(e) => setFormRisk(e.target.value)}
                min="0"
                step="10"
                placeholder="Optional"
              />
            </div>

            <div className="form-group">
              <label htmlFor="log-intent">Intent</label>
              <input
                id="log-intent"
                type="text"
                value={formIntent}
                onChange={(e) => setFormIntent(e.target.value)}
                placeholder="Why this log exists..."
              />
            </div>

            <div className="form-group">
              <label htmlFor="log-notes">Notes</label>
              <textarea
                id="log-notes"
                value={formNotes}
                onChange={(e) => setFormNotes(e.target.value)}
                placeholder="Additional notes..."
                rows={3}
              />
            </div>

            <div className="form-warning">
              Starting capital and risk per trade cannot be changed after creation.
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn-cancel"
                onClick={() => setView('list')}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-submit"
                disabled={creating || !formName || !formCapital}
              >
                {creating ? 'Creating...' : 'Create Log'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
