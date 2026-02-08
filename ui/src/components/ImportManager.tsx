/**
 * ImportManager - Manage and reverse trade imports
 *
 * Goals:
 * - Reversible: Undo entire imports safely
 * - Auditable: Clear provenance of import source
 * - Non-destructive: Never entangles manual trades
 * - Compatible: Works with ML, Alerts, Process
 *
 * Uses the /api/imports endpoint for batch management.
 */

import { useState, useEffect, useCallback } from 'react';

interface ImportBatch {
  id: string;
  userId: number;
  source: string;
  sourceLabel: string | null;
  sourceMetadata: {
    fileName?: string;
    originalRows?: number;
    parsedTrades?: number;
    skippedRows?: number;
    aiAssisted?: boolean;
    logId?: string;
  } | null;
  tradeCount: number;
  positionCount: number;
  status: 'active' | 'reverted';
  createdAt: string;
  revertedAt: string | null;
}

interface ImportManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onImportDeleted: () => void;
  currentLogId?: string | null;
}

export default function ImportManager({
  isOpen,
  onClose,
  onImportDeleted,
  currentLogId,
}: ImportManagerProps) {
  const [imports, setImports] = useState<ImportBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'current'>('current');

  // Load imports from API
  const loadImports = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/imports?status=active', {
        credentials: 'include',
      });
      const result = await response.json();

      if (result.success) {
        setImports(result.data);
      } else {
        // Fall back to localStorage for legacy imports
        const history = JSON.parse(localStorage.getItem('tradeImportHistory') || '[]');
        const mapped: ImportBatch[] = history.map((h: any, i: number) => ({
          id: h.batchId || `legacy-${i}`,
          userId: 0,
          source: h.platform || 'unknown',
          sourceLabel: null,
          sourceMetadata: {
            fileName: h.metadata?.fileName,
            logId: h.logId,
          },
          tradeCount: h.count || h.tradeIds?.length || 0,
          positionCount: 0,
          status: 'active' as const,
          createdAt: h.importTime,
          revertedAt: null,
        }));
        setImports(mapped);
      }
    } catch (err) {
      console.error('Failed to load imports:', err);
      // Fall back to localStorage
      try {
        const history = JSON.parse(localStorage.getItem('tradeImportHistory') || '[]');
        const mapped: ImportBatch[] = history.map((h: any, i: number) => ({
          id: h.batchId || `legacy-${i}`,
          userId: 0,
          source: h.platform || 'unknown',
          sourceLabel: null,
          sourceMetadata: {
            fileName: h.metadata?.fileName,
            logId: h.logId,
          },
          tradeCount: h.count || h.tradeIds?.length || 0,
          positionCount: 0,
          status: 'active' as const,
          createdAt: h.importTime,
          revertedAt: null,
        }));
        setImports(mapped);
      } catch {
        setError('Failed to load import history');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadImports();
    }
  }, [isOpen, loadImports]);

  // Revert an entire import batch
  const handleDeleteImport = async (batch: ImportBatch) => {
    const confirmMsg = `Revert this ${batch.source.toUpperCase()} import?\n\nThis will remove ${batch.tradeCount} trades${batch.positionCount > 0 ? ` and ${batch.positionCount} positions` : ''}.\n\nImported: ${new Date(batch.createdAt).toLocaleString()}\n\nManual trades will not be affected.`;

    if (!confirm(confirmMsg)) return;

    setDeleting(batch.id);
    setError(null);

    try {
      // Use the new revert API endpoint
      const response = await fetch(`/api/imports/${batch.id}/revert`, {
        method: 'POST',
        credentials: 'include',
      });
      const result = await response.json();

      if (result.success) {
        // Also remove from localStorage if it exists there (legacy support)
        try {
          const history = JSON.parse(localStorage.getItem('tradeImportHistory') || '[]');
          const updated = history.filter((h: any) => h.batchId !== batch.id);
          localStorage.setItem('tradeImportHistory', JSON.stringify(updated));
        } catch {
          // Ignore localStorage errors
        }

        loadImports();
        onImportDeleted();
      } else {
        setError(result.error || 'Failed to revert import');
      }
    } catch (err) {
      console.error('Revert error:', err);
      setError('Failed to revert import. Please try again.');
    } finally {
      setDeleting(null);
    }
  };

  // Filter imports by current log if metadata contains logId
  const filteredImports = filter === 'current' && currentLogId
    ? imports.filter(i => i.sourceMetadata?.logId === currentLogId)
    : imports;

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (!isOpen) return null;

  return (
    <div className="import-manager-overlay" onClick={onClose}>
      <div className="import-manager-modal" onClick={e => e.stopPropagation()}>
        <div className="import-manager-header">
          <h3>Import Manager</h3>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="import-manager-toolbar">
          <div className="filter-tabs">
            <button
              className={`filter-tab ${filter === 'current' ? 'active' : ''}`}
              onClick={() => setFilter('current')}
            >
              Current Log
            </button>
            <button
              className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All Logs
            </button>
          </div>
          <div className="import-count">
            {filteredImports.length} import{filteredImports.length !== 1 ? 's' : ''}
          </div>
        </div>

        {error && (
          <div className="import-manager-error">
            {error}
            <button onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        <div className="import-manager-body">
          {loading ? (
            <div className="import-manager-loading">Loading imports...</div>
          ) : filteredImports.length === 0 ? (
            <div className="import-manager-empty">
              <div className="empty-icon">📥</div>
              <div className="empty-text">No imports found</div>
              <div className="empty-hint">
                Import trades from brokers to see them here
              </div>
            </div>
          ) : (
            <div className="import-list">
              {filteredImports.map(batch => (
                <div
                  key={batch.id}
                  className={`import-item ${deleting === batch.id ? 'deleting' : ''}`}
                >
                  <div className="import-item-header">
                    <span className={`platform-badge ${batch.source}`}>
                      {batch.source.toUpperCase()}
                    </span>
                    <span className="import-date">{formatDate(batch.createdAt)}</span>
                  </div>

                  <div className="import-item-details">
                    <div className="detail-row">
                      <span className="detail-label">Trades:</span>
                      <span className="detail-value">{batch.tradeCount}</span>
                    </div>
                    {batch.positionCount > 0 && (
                      <div className="detail-row">
                        <span className="detail-label">Positions:</span>
                        <span className="detail-value">{batch.positionCount}</span>
                      </div>
                    )}
                    {batch.sourceLabel && (
                      <div className="detail-row">
                        <span className="detail-label">Label:</span>
                        <span className="detail-value">{batch.sourceLabel}</span>
                      </div>
                    )}
                    {batch.sourceMetadata?.fileName && (
                      <div className="detail-row">
                        <span className="detail-label">File:</span>
                        <span className="detail-value file">{batch.sourceMetadata.fileName}</span>
                      </div>
                    )}
                    {batch.sourceMetadata?.aiAssisted && (
                      <div className="ai-badge">AI Assisted</div>
                    )}
                  </div>

                  <div className="import-item-actions">
                    <button
                      className="btn-delete-import"
                      onClick={() => handleDeleteImport(batch)}
                      disabled={deleting !== null}
                    >
                      {deleting === batch.id ? 'Reverting...' : 'Revert Import'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="import-manager-footer">
          <div className="footer-info">
            Deleting an import removes all trades from that batch.
            Manual trades are never affected.
          </div>
          <button className="btn-close" onClick={onClose}>Close</button>
        </div>
      </div>

      <style>{`
        .import-manager-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .import-manager-modal {
          background: #1a1a2e;
          border: 1px solid #333;
          border-radius: 8px;
          width: 500px;
          max-width: 90vw;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
        }

        .import-manager-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid #333;
        }

        .import-manager-header h3 {
          margin: 0;
          font-size: 18px;
          color: #e2e8f0;
        }

        .close-btn {
          background: none;
          border: none;
          color: #666;
          font-size: 24px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
        }

        .close-btn:hover {
          color: #fff;
        }

        .import-manager-toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 20px;
          border-bottom: 1px solid #333;
          background: #0f0f1a;
        }

        .filter-tabs {
          display: flex;
          gap: 4px;
        }

        .filter-tab {
          background: transparent;
          border: 1px solid #333;
          color: #9ca3af;
          padding: 6px 12px;
          border-radius: 4px;
          font-size: 12px;
          cursor: pointer;
          transition: all 0.15s;
        }

        .filter-tab:hover {
          border-color: #555;
          color: #e2e8f0;
        }

        .filter-tab.active {
          background: #3b82f6;
          border-color: #3b82f6;
          color: #fff;
        }

        .import-count {
          font-size: 12px;
          color: #666;
        }

        .import-manager-error {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 20px;
          background: rgba(239, 68, 68, 0.1);
          border-bottom: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
          font-size: 13px;
        }

        .import-manager-error button {
          background: none;
          border: none;
          color: #f87171;
          cursor: pointer;
          font-size: 16px;
        }

        .import-manager-body {
          flex: 1;
          overflow-y: auto;
          padding: 16px 20px;
        }

        .import-manager-loading,
        .import-manager-empty {
          text-align: center;
          padding: 40px 20px;
          color: #666;
        }

        .empty-icon {
          font-size: 48px;
          margin-bottom: 12px;
        }

        .empty-text {
          font-size: 16px;
          color: #9ca3af;
          margin-bottom: 8px;
        }

        .empty-hint {
          font-size: 13px;
          color: #666;
        }

        .import-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .import-item {
          background: #0f0f1a;
          border: 1px solid #333;
          border-radius: 6px;
          padding: 16px;
          transition: all 0.2s;
        }

        .import-item:hover {
          border-color: #444;
        }

        .import-item.deleting {
          opacity: 0.5;
          pointer-events: none;
        }

        .import-item-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }

        .platform-badge {
          font-size: 11px;
          font-weight: 700;
          padding: 3px 10px;
          border-radius: 4px;
          background: #333;
          color: #9ca3af;
        }

        .platform-badge.tos {
          background: rgba(59, 130, 246, 0.2);
          color: #60a5fa;
        }

        .platform-badge.custom {
          background: rgba(139, 92, 246, 0.2);
          color: #a78bfa;
        }

        .platform-badge.ai {
          background: rgba(139, 92, 246, 0.2);
          color: #a78bfa;
        }

        .import-date {
          font-size: 12px;
          color: #666;
        }

        .import-item-details {
          margin-bottom: 12px;
        }

        .detail-row {
          display: flex;
          gap: 8px;
          font-size: 12px;
          margin-bottom: 4px;
        }

        .detail-label {
          color: #666;
          min-width: 60px;
        }

        .detail-value {
          color: #e2e8f0;
        }

        .detail-value.source {
          font-family: monospace;
          color: #9ca3af;
        }

        .detail-value.file {
          color: #9ca3af;
          max-width: 200px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .ai-badge {
          display: inline-block;
          font-size: 10px;
          padding: 2px 8px;
          border-radius: 10px;
          background: rgba(139, 92, 246, 0.2);
          color: #a78bfa;
          margin-top: 8px;
        }

        .import-item-actions {
          display: flex;
          justify-content: flex-end;
        }

        .btn-delete-import {
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
          padding: 6px 12px;
          border-radius: 4px;
          font-size: 12px;
          cursor: pointer;
          transition: all 0.15s;
        }

        .btn-delete-import:hover:not(:disabled) {
          background: rgba(239, 68, 68, 0.2);
          border-color: rgba(239, 68, 68, 0.5);
        }

        .btn-delete-import:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .import-manager-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-top: 1px solid #333;
          background: #0f0f1a;
        }

        .footer-info {
          font-size: 11px;
          color: #666;
          max-width: 280px;
        }

        .btn-close {
          background: #333;
          border: none;
          color: #e2e8f0;
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 13px;
        }

        .btn-close:hover {
          background: #444;
        }
      `}</style>
    </div>
  );
}
