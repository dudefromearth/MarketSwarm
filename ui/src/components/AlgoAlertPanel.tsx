/**
 * AlgoAlertPanel — Risk Graph sidebar panel for algo alerts.
 *
 * Shows:
 * - Active algo alerts with passive filter-state visibility
 * - Pending proposals with approve/reject
 * - "New Algo-Alert" button
 *
 * Transparent cognition: filter state always visible, even when no proposal exists.
 */

import { useState, useCallback } from 'react';
import { useAlgoAlerts } from '../contexts/AlgoAlertContext';
import { usePositionsContext } from '../contexts/PositionsContext';
import AlgoAlertCreator from './AlgoAlertCreator';
import ProposalCard from './ProposalCard';
import type {
  AlgoAlert,
  CreateAlgoAlertInput,
  FilterEvaluationResult,
} from '../types/algoAlerts';
import {
  ALGO_ALERT_STATUS_STYLES,
  DATA_SOURCE_LABELS,
} from '../types/algoAlerts';
import '../styles/algo-alert.css';

interface AlgoAlertPanelProps {
  positionIds?: string[];
}

export default function AlgoAlertPanel({ positionIds }: AlgoAlertPanelProps) {
  const {
    algoAlerts,
    createAlgoAlert,
    updateAlgoAlert,
    deleteAlgoAlert,
    approveProposal,
    rejectProposal,
    getActiveProposals,
    getFilterState,
  } = useAlgoAlerts();

  const { addPosition } = usePositionsContext();

  const [showCreator, setShowCreator] = useState(false);
  const [createMgmtAlert] = useState(true);
  const activeProposals = getActiveProposals();

  const handleSave = useCallback(async (input: CreateAlgoAlertInput) => {
    await createAlgoAlert(input);
    setShowCreator(false);
  }, [createAlgoAlert]);

  const handleTogglePause = useCallback(async (alert: AlgoAlert) => {
    const newStatus = alert.status === 'active' ? 'paused' : 'active';
    await updateAlgoAlert(alert.id, { status: newStatus });
  }, [updateAlgoAlert]);

  const handleDelete = useCallback(async (id: string) => {
    await deleteAlgoAlert(id);
  }, [deleteAlgoAlert]);

  const handleApprove = useCallback(async (id: string) => {
    const proposal = await approveProposal(id);
    if (!proposal) return;

    // Mode A: create position from approved entry proposal
    if (proposal.type === 'entry' && proposal.suggestedPosition) {
      const pos = proposal.suggestedPosition;
      try {
        // Build legs from suggested position
        const right = pos.side === 'call' ? 'call' : 'put';
        const expiration = pos.expiration || '';
        const legs = buildLegsFromStrategy(pos.strategyType, pos.strike, pos.width, right, expiration);

        await addPosition({
          symbol: pos.symbol || 'SPX',
          positionType: (pos.strategyType || 'butterfly') as any,
          direction: 'long',
          legs,
          costBasis: pos.estimatedDebit || null,
          costBasisType: 'debit',
        });

        // Auto-clone entry alert as management alert (default-on)
        if (createMgmtAlert) {
          const parentAlert = algoAlerts.find(a => a.id === proposal.algoAlertId);
          if (parentAlert) {
            await createAlgoAlert({
              name: `${parentAlert.name} (Mgmt)`,
              mode: 'management',
              filters: parentAlert.filters.map(f => ({
                dataSource: f.dataSource,
                field: f.field,
                operator: f.operator,
                value: f.value,
                required: f.required,
              })),
            });
          }
        }
      } catch (err) {
        console.error('Failed to create position from approved proposal:', err);
      }
    }
  }, [approveProposal, addPosition, createMgmtAlert, algoAlerts, createAlgoAlert]);

  const handleReject = useCallback(async (id: string) => {
    await rejectProposal(id);
  }, [rejectProposal]);

  // Don't render if no alerts and no creator
  const visibleAlerts = algoAlerts.filter(a => a.status !== 'archived');

  return (
    <div className="algo-alert-panel">
      <div className="section-header">
        Algo Alerts
        <button className="btn-new-algo" onClick={() => setShowCreator(!showCreator)}>
          {showCreator ? 'Cancel' : '+ New'}
        </button>
      </div>

      {/* Creator Form */}
      {showCreator && (
        <AlgoAlertCreator
          onSave={handleSave}
          onCancel={() => setShowCreator(false)}
          positionIds={positionIds}
        />
      )}

      {/* Pending Proposals */}
      {activeProposals.length > 0 && (
        <div style={{ padding: '0 4px' }}>
          {activeProposals.map(p => (
            <ProposalCard
              key={p.id}
              proposal={p}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </div>
      )}

      {/* Alert List */}
      {visibleAlerts.map(alert => (
        <AlgoAlertItem
          key={alert.id}
          alert={alert}
          filterResults={getFilterState(alert.id)}
          onTogglePause={handleTogglePause}
          onDelete={handleDelete}
        />
      ))}

      {visibleAlerts.length === 0 && !showCreator && (
        <div className="algo-alert-empty">
          No algo alerts configured
        </div>
      )}
    </div>
  );
}

// ==================== Helpers ====================

/**
 * Build option legs from a strategy description.
 * Maps strategy type + strike/width to individual leg structures.
 */
function buildLegsFromStrategy(
  strategyType: string,
  strike: number,
  width: number,
  right: 'call' | 'put',
  expiration: string,
) {
  switch (strategyType) {
    case 'butterfly':
      return [
        { strike: strike - width, expiration, right, quantity: 1 },
        { strike, expiration, right, quantity: -2 },
        { strike: strike + width, expiration, right, quantity: 1 },
      ];
    case 'vertical':
      return [
        { strike, expiration, right, quantity: 1 },
        { strike: strike + width, expiration, right, quantity: -1 },
      ];
    default:
      // Single leg fallback
      return [
        { strike, expiration, right, quantity: 1 },
      ];
  }
}

// ==================== Alert Item ====================

interface AlgoAlertItemProps {
  alert: AlgoAlert;
  filterResults?: FilterEvaluationResult[];
  onTogglePause: (alert: AlgoAlert) => void;
  onDelete: (id: string) => void;
}

function AlgoAlertItem({ alert, filterResults, onTogglePause, onDelete }: AlgoAlertItemProps) {
  const statusStyle = ALGO_ALERT_STATUS_STYLES[alert.status];

  return (
    <div className="algo-alert-item">
      <div className="algo-alert-item-header">
        <span className="algo-alert-item-name" title={alert.name}>
          {alert.name}
        </span>
        <span className={`algo-alert-mode-badge ${alert.mode}`}>
          {alert.mode === 'entry' ? 'A' : 'B'}
        </span>
        <span
          className="algo-alert-status-badge"
          style={{ color: statusStyle.color, background: statusStyle.bgColor }}
        >
          {statusStyle.label}
        </span>
        <div className="algo-alert-item-actions">
          <button
            onClick={() => onTogglePause(alert)}
            title={alert.status === 'active' ? 'Pause' : 'Resume'}
          >
            {alert.status === 'active' ? '||' : '>'}
          </button>
          <button className="delete" onClick={() => onDelete(alert.id)} title="Delete">
            x
          </button>
        </div>
      </div>

      {/* Frozen Banner */}
      {alert.status === 'frozen' && (
        <div className="algo-alert-frozen-banner">
          Conflicting structure — standing down
          {alert.frozenReason && (
            <span style={{ opacity: 0.8 }}> ({alert.frozenReason})</span>
          )}
        </div>
      )}

      {/* Passive filter-state visibility */}
      {filterResults && filterResults.length > 0 && (
        <div className="algo-filter-state" title="Filter state: green=pass, red=fail, amber=unavailable">
          {filterResults.map((r, i) => (
            <span
              key={i}
              className={`algo-filter-dot ${r.dataAvailable ? (r.passed ? 'pass' : 'fail') : 'unavailable'}`}
              title={`${DATA_SOURCE_LABELS[r.dataSource as keyof typeof DATA_SOURCE_LABELS] || r.dataSource}.${r.field}: ${r.dataAvailable ? (r.passed ? 'pass' : 'fail') : 'unavailable'} (current: ${r.currentValue ?? 'N/A'})`}
            />
          ))}
        </div>
      )}

      {/* Filter tooltip for structural language */}
      {filterResults && filterResults.length > 0 && (
        <div className="algo-filter-tooltip">
          {filterResults.filter(r => r.passed).length}/{filterResults.length} gates passing
        </div>
      )}
    </div>
  );
}
