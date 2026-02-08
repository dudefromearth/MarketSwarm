// src/components/LogManagerModal.tsx
import { useState, useEffect, useMemo, useCallback } from 'react';
import type { TradeLog } from './LogSelector';
import { useLogLifecycleListener } from '../hooks/useLogLifecycle';

const JOURNAL_API = '';

interface LogManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLogId: string | null;
  onSelectLog: (log: TradeLog) => void;
  onLogCreated: () => void;
}

type View = 'list' | 'create';
type FilterTab = 'active' | 'archived' | 'all';

// Lifecycle caps
const SOFT_CAP = 5;
const HARD_CAP = 10;

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
  const [filterTab, setFilterTab] = useState<FilterTab>('active');

  // Create form state
  const [formName, setFormName] = useState('');
  const [formCapital, setFormCapital] = useState('25000');
  const [formRisk, setFormRisk] = useState('');
  const [formIntent, setFormIntent] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lifecycle action state
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [retireConfirmId, setRetireConfirmId] = useState<string | null>(null);
  const [retireConfirmName, setRetireConfirmName] = useState('');

  useEffect(() => {
    if (isOpen) {
      fetchLogs();
      setView('list');
      setRetireConfirmId(null);
      setRetireConfirmName('');
    }
  }, [isOpen]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch active and archived logs (exclude retired)
      const response = await fetch(`${JOURNAL_API}/api/logs?state=active,archived`);
      const result = await response.json();
      if (result.success) {
        setLogs(result.data);
      }
    } catch (err) {
      console.error('LogManagerModal fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Listen for lifecycle events and auto-refresh
  useLogLifecycleListener(() => {
    if (isOpen) {
      fetchLogs();
    }
  }, [isOpen, fetchLogs]);

  // Computed counts
  const activeCount = useMemo(() =>
    logs.filter(l => l.lifecycle_state === 'active').length, [logs]);
  const archivedCount = useMemo(() =>
    logs.filter(l => l.lifecycle_state === 'archived').length, [logs]);
  const atSoftCap = activeCount >= SOFT_CAP;
  const atHardCap = activeCount >= HARD_CAP;

  // Filtered logs
  const filteredLogs = useMemo(() => {
    switch (filterTab) {
      case 'active':
        return logs.filter(l => l.lifecycle_state === 'active');
      case 'archived':
        return logs.filter(l => l.lifecycle_state === 'archived');
      default:
        return logs.filter(l => l.lifecycle_state !== 'retired');
    }
  }, [logs, filterTab]);

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

  // Lifecycle actions
  const handleArchive = async (log: TradeLog) => {
    // Check preconditions
    if ((log.open_positions ?? log.open_trades) > 0) {
      alert('Cannot archive: This log has open positions. Close them first.');
      return;
    }
    if ((log.pending_alerts ?? 0) > 0) {
      alert('Cannot archive: This log has pending alerts. Dismiss them first.');
      return;
    }

    if (!confirm(`Archive "${log.name}"? It will become read-only and excluded from ML/alerts.`)) {
      return;
    }

    setActionLoading(log.id);
    try {
      const response = await fetch(`${JOURNAL_API}/api/logs/${log.id}/archive`, {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        fetchLogs();
        onLogCreated();
      } else {
        alert(result.error || 'Failed to archive log');
      }
    } catch (err) {
      console.error('Archive error:', err);
      alert('Failed to archive log');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReactivate = async (log: TradeLog) => {
    if (atHardCap) {
      alert(`Cannot reactivate: You have ${activeCount} active logs (maximum ${HARD_CAP}). Archive one first.`);
      return;
    }

    const warningMsg = atSoftCap
      ? `You have ${activeCount} active logs. Reactivating "${log.name}" will exceed the recommended limit of ${SOFT_CAP}. Continue?`
      : `Reactivate "${log.name}"? It will be editable and included in ML/alerts.`;

    if (!confirm(warningMsg)) {
      return;
    }

    setActionLoading(log.id);
    try {
      const response = await fetch(`${JOURNAL_API}/api/logs/${log.id}/reactivate`, {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        fetchLogs();
        onLogCreated();
      } else {
        alert(result.error || 'Failed to reactivate log');
      }
    } catch (err) {
      console.error('Reactivate error:', err);
      alert('Failed to reactivate log');
    } finally {
      setActionLoading(null);
    }
  };

  const handleScheduleRetire = async (log: TradeLog) => {
    // Verify name confirmation matches
    if (retireConfirmName !== log.name) {
      alert('Log name does not match. Please type the exact name to confirm.');
      return;
    }

    setActionLoading(log.id);
    try {
      const response = await fetch(`${JOURNAL_API}/api/logs/${log.id}/retire`, {
        method: 'POST'
      });
      const result = await response.json();
      if (result.success) {
        setRetireConfirmId(null);
        setRetireConfirmName('');
        fetchLogs();
        onLogCreated();
      } else {
        alert(result.error || 'Failed to schedule retirement');
      }
    } catch (err) {
      console.error('Retire error:', err);
      alert('Failed to schedule retirement');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelRetire = async (log: TradeLog) => {
    if (!confirm(`Cancel retirement of "${log.name}"?`)) {
      return;
    }

    setActionLoading(log.id);
    try {
      const response = await fetch(`${JOURNAL_API}/api/logs/${log.id}/retire`, {
        method: 'DELETE'
      });
      const result = await response.json();
      if (result.success) {
        fetchLogs();
        onLogCreated();
      } else {
        alert(result.error || 'Failed to cancel retirement');
      }
    } catch (err) {
      console.error('Cancel retire error:', err);
      alert('Failed to cancel retirement');
    } finally {
      setActionLoading(null);
    }
  };

  // Helper to calculate days until retirement
  const getDaysUntilRetirement = (retireScheduledAt: string | null): number | null => {
    if (!retireScheduledAt) return null;
    const scheduled = new Date(retireScheduledAt);
    const now = new Date();
    const diffMs = scheduled.getTime() - now.getTime();
    return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  };

  // Render lifecycle badge
  const renderLifecycleBadge = (log: TradeLog) => {
    switch (log.lifecycle_state) {
      case 'active':
        return <span className="lifecycle-badge active">Active</span>;
      case 'archived':
        if (log.retire_scheduled_at) {
          const days = getDaysUntilRetirement(log.retire_scheduled_at);
          return (
            <span className="lifecycle-badge retiring">
              Retiring in {days}d
            </span>
          );
        }
        return <span className="lifecycle-badge archived">Archived</span>;
      case 'retired':
        return <span className="lifecycle-badge retired">Retired</span>;
      default:
        return null;
    }
  };

  // Render action buttons based on state
  const renderActions = (log: TradeLog) => {
    const isLoading = actionLoading === log.id;

    if (log.lifecycle_state === 'active') {
      const canArchive = (log.open_positions ?? log.open_trades) === 0 && (log.pending_alerts ?? 0) === 0;
      return (
        <button
          className="btn-lifecycle archive"
          onClick={(e) => {
            e.stopPropagation();
            handleArchive(log);
          }}
          disabled={isLoading || !canArchive}
          title={canArchive ? 'Archive this log' : 'Close positions and dismiss alerts first'}
        >
          {isLoading ? '...' : 'Archive'}
        </button>
      );
    }

    if (log.lifecycle_state === 'archived') {
      // Show retire confirmation if this is the log being confirmed
      if (retireConfirmId === log.id) {
        return (
          <div className="retire-confirm" onClick={e => e.stopPropagation()}>
            <input
              type="text"
              placeholder="Type log name to confirm"
              value={retireConfirmName}
              onChange={e => setRetireConfirmName(e.target.value)}
              className="retire-confirm-input"
            />
            <button
              className="btn-lifecycle retire-confirm-btn"
              onClick={() => handleScheduleRetire(log)}
              disabled={isLoading || retireConfirmName !== log.name}
            >
              {isLoading ? '...' : 'Confirm'}
            </button>
            <button
              className="btn-lifecycle cancel"
              onClick={() => {
                setRetireConfirmId(null);
                setRetireConfirmName('');
              }}
            >
              ✕
            </button>
          </div>
        );
      }

      // If retirement is scheduled, show cancel button
      if (log.retire_scheduled_at) {
        return (
          <button
            className="btn-lifecycle cancel-retire"
            onClick={(e) => {
              e.stopPropagation();
              handleCancelRetire(log);
            }}
            disabled={isLoading}
            title="Cancel scheduled retirement"
          >
            {isLoading ? '...' : 'Cancel Retire'}
          </button>
        );
      }

      // Normal archived state - show reactivate and retire buttons
      return (
        <div className="action-buttons" onClick={e => e.stopPropagation()}>
          <button
            className="btn-lifecycle reactivate"
            onClick={() => handleReactivate(log)}
            disabled={isLoading || atHardCap}
            title={atHardCap ? `Maximum ${HARD_CAP} active logs reached` : 'Reactivate this log'}
          >
            {isLoading ? '...' : 'Reactivate'}
          </button>
          <button
            className="btn-lifecycle retire"
            onClick={() => setRetireConfirmId(log.id)}
            disabled={isLoading}
            title="Permanently retire (7-day grace period)"
          >
            Retire
          </button>
        </div>
      );
    }

    return null;
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
            {/* Filter tabs */}
            <div className="log-filter-tabs">
              <button
                className={`filter-tab ${filterTab === 'active' ? 'active' : ''}`}
                onClick={() => setFilterTab('active')}
              >
                Active ({activeCount})
              </button>
              <button
                className={`filter-tab ${filterTab === 'archived' ? 'active' : ''}`}
                onClick={() => setFilterTab('archived')}
              >
                Archived ({archivedCount})
              </button>
              <button
                className={`filter-tab ${filterTab === 'all' ? 'active' : ''}`}
                onClick={() => setFilterTab('all')}
              >
                All
              </button>
              {atSoftCap && (
                <span className="cap-warning" title={`Recommended max: ${SOFT_CAP}, Hard limit: ${HARD_CAP}`}>
                  {activeCount}/{HARD_CAP} active
                </span>
              )}
            </div>

            <div className="log-list">
              {loading ? (
                <div className="log-list-loading">Loading logs...</div>
              ) : filteredLogs.length === 0 ? (
                <div className="log-list-empty">
                  {logs.length === 0 ? (
                    <>
                      <p className="empty-title">No trade logs yet</p>
                      <p className="empty-hint">
                        Create a log to begin your practice. Logs help you separate
                        strategies, timeframes, or experiments.
                      </p>
                    </>
                  ) : filterTab === 'active' ? (
                    <>
                      <p>No active logs.</p>
                      <p className="empty-hint">Reactivate an archived log or create a new one.</p>
                    </>
                  ) : filterTab === 'archived' ? (
                    <p>No archived logs.</p>
                  ) : (
                    <p>No logs found.</p>
                  )}
                </div>
              ) : (
                filteredLogs.map(log => {
                  const isRetiring = log.lifecycle_state === 'archived' && !!log.retire_scheduled_at;
                  const isSelectable = log.lifecycle_state === 'active';

                  return (
                  <div
                    key={log.id}
                    className={`log-list-item ${log.id === selectedLogId ? 'selected' : ''} ${log.lifecycle_state} ${isRetiring ? 'retiring' : ''}`}
                    onClick={() => {
                      if (isSelectable) {
                        onSelectLog(log);
                        onClose();
                      }
                    }}
                    style={{ cursor: isSelectable ? 'pointer' : 'default' }}
                  >
                    <div className="log-item-main">
                      <span className="log-item-indicator">
                        {log.id === selectedLogId ? '●' : ''}
                      </span>
                      <span className="log-item-name">{log.name}</span>
                      {renderLifecycleBadge(log)}
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
                    <div className="log-item-meta">
                      {log.lifecycle_state === 'active' && (log.open_positions ?? log.open_trades) > 0 && (
                        <span className="log-meta-tag open">
                          {log.open_positions ?? log.open_trades} open
                        </span>
                      )}
                      {log.lifecycle_state !== 'active' && (
                        <span className="log-meta-tag read-only" title="Archived logs are read-only">
                          Read-only
                        </span>
                      )}
                      {log.lifecycle_state === 'archived' && !log.retire_scheduled_at && (
                        <span className="log-meta-tag ml-excluded" title="Excluded from ML training (archived)">
                          ML excluded
                        </span>
                      )}
                      {log.lifecycle_state === 'active' && log.ml_included === 0 && (
                        <span className="log-meta-tag ml-excluded" title="Manually excluded from ML training">
                          ML off
                        </span>
                      )}
                    </div>
                    <div className="log-item-actions">
                      {renderActions(log)}
                    </div>
                  </div>
                  );
                })
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn-create-log"
                onClick={() => setView('create')}
                disabled={atHardCap}
                title={atHardCap ? `Maximum ${HARD_CAP} active logs reached` : 'Create a new log'}
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
