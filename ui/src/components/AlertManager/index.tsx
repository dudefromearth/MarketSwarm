/**
 * AlertManager - Unified Workflow Awareness System
 *
 * The awareness layer that spans the entire FOTW workflow (left-to-right).
 * Prompt-first alert creation with support for:
 * - Market thresholds (price, levels, time)
 * - Position/risk thresholds (PnL, Greeks, risk graph events)
 * - Discipline rules (daily loss, max trades, edge guardrails)
 * - Workflow triggers (journal after close, routine checklist)
 * - AI alerts (pattern matching, behavioral detection)
 * - ML alerts (learned patterns from Trade Tracking ML system)
 *
 * From alert-mgr v1.1 spec + ml-driven-alerts.md
 */

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useAlerts } from '../../contexts/AlertContext';
import type {
  AlertDefinition,
  AlertScope,
  AlertSeverity,
  AlertStatus,
} from '../../types/alerts';
import AlertFilters from './AlertFilters';
import AlertCard from './AlertCard';
import PromptInput from './PromptInput';
import './AlertManager.css';

// View filter type - includes 'algo' for strategy-aware alerts, 'ml' for learned patterns
type ViewFilter = 'all' | 'algo' | 'ml' | 'position' | 'symbol' | 'portfolio' | 'workflow' | 'behavioral' | 'triggered';

interface AlertManagerProps {
  open: boolean;
  onClose: () => void;
  onCreateAlert?: () => void;  // Legacy callback for external alert creation
}

export default function AlertManager({ open, onClose, onCreateAlert: _onCreateAlert }: AlertManagerProps) {
  const {
    alerts,
    alertDefinitions: contextDefinitions,
    deleteAlert: _deleteAlert,
    // v1.1 operations
    createDefinition,
    pauseDefinition,
    resumeDefinition,
    acknowledgeDefinition,
    dismissDefinition,
    deleteDefinition,
  } = useAlerts();
  // Suppress unused warnings - these will be used when legacy support is removed
  void _onCreateAlert;
  void _deleteAlert;
  const [viewFilter, setViewFilter] = useState<ViewFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Convert legacy alerts to AlertDefinition format for display
  // Merge with context definitions (which include ML and algo alerts)
  const alertDefinitions: AlertDefinition[] = useMemo(() => {
    // Start with any definitions from context (ML alerts, algo alerts, etc.)
    const fromContext = contextDefinitions || [];

    // Convert legacy alerts
    const legacyConverted: AlertDefinition[] = alerts.map((alert) => {
      // Determine lifecycle stage from legacy state
      let lifecycleStage: AlertDefinition['lifecycleStage'] = 'watching';
      if (alert.triggered && !alert.enabled) {
        lifecycleStage = 'dismissed';
      } else if (alert.triggered) {
        lifecycleStage = 'warn';
      }

      const hasStrategyId = 'strategyId' in alert;

      return {
        id: alert.id,
        userId: 0,
        prompt: alert.label || `${alert.type} alert: ${alert.condition} ${alert.targetValue}`,
        scope: hasStrategyId ? 'position' as AlertScope : 'symbol' as AlertScope,
        severity: alert.priority === 'critical' ? 'block' as AlertSeverity :
                  alert.priority === 'high' ? 'warn' as AlertSeverity :
                  alert.priority === 'medium' ? 'notify' as AlertSeverity : 'inform' as AlertSeverity,
        status: alert.enabled ? 'active' as AlertStatus : 'paused' as AlertStatus,
        lifecycleStage,
        bindingState: hasStrategyId ? 'position_bound' : 'symbol_bound',
        bindingPolicy: 'manual' as AlertDefinition['bindingPolicy'],
        targetRef: {
          positionId: hasStrategyId ? (alert as any).strategyId : undefined,
          symbol: 'SPX',
        },
        originTool: alert.source?.type,
        cooldownSeconds: 300,
        budgetClass: 'standard' as AlertDefinition['budgetClass'],
        createdAt: new Date(alert.createdAt).toISOString(),
        updatedAt: new Date(alert.updatedAt).toISOString(),
        lastTriggeredAt: alert.triggeredAt ? new Date(alert.triggeredAt).toISOString() : undefined,
        triggerCount: alert.triggerCount,
      };
    });

    // Merge: context definitions (ML, algo) + legacy converted
    return [...fromContext, ...legacyConverted];
  }, [alerts, contextDefinitions]);

  // Helper to check if alert needs attention (update or warn stage)
  const needsAttention = (a: AlertDefinition) =>
    a.lifecycleStage === 'update' || a.lifecycleStage === 'warn';

  // Helper to check if alert is an algo alert
  const isAlgo = (a: AlertDefinition) =>
    'category' in a && (a as any).category === 'algo';

  // Helper to check if alert is an ML alert
  const isML = (a: AlertDefinition) =>
    'category' in a && (a as any).category === 'ml';

  // Filter alerts by view and search
  const filteredAlerts = useMemo(() => {
    let filtered = alertDefinitions;

    // Apply view filter
    if (viewFilter === 'triggered') {
      // Show alerts in update or warn lifecycle stages
      filtered = filtered.filter(needsAttention);
    } else if (viewFilter === 'algo') {
      // Show only algo alerts
      filtered = filtered.filter(isAlgo);
    } else if (viewFilter === 'ml') {
      // Show only ML alerts (learned patterns)
      filtered = filtered.filter(isML);
    } else if (viewFilter !== 'all') {
      filtered = filtered.filter((a) => a.scope === viewFilter);
    }

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((a) =>
        a.prompt.toLowerCase().includes(query) ||
        a.title?.toLowerCase().includes(query)
      );
    }

    return filtered;
  }, [alertDefinitions, viewFilter, searchQuery]);

  // Count alerts by view filter for badges
  const filterCounts = useMemo(() => {
    const counts: Record<ViewFilter, number> = {
      all: alertDefinitions.length,
      algo: alertDefinitions.filter(isAlgo).length,
      ml: alertDefinitions.filter(isML).length,
      position: alertDefinitions.filter((a) => a.scope === 'position').length,
      symbol: alertDefinitions.filter((a) => a.scope === 'symbol').length,
      portfolio: alertDefinitions.filter((a) => a.scope === 'portfolio').length,
      workflow: alertDefinitions.filter((a) => a.scope === 'workflow').length,
      behavioral: alertDefinitions.filter((a) => a.scope === 'behavioral').length,
      triggered: alertDefinitions.filter(needsAttention).length,
    };
    return counts;
  }, [alertDefinitions]);

  // Handle alert creation from prompt (uses context)
  const handleCreateAlert = useCallback(async (
    prompt: string,
    scope: AlertScope,
    severity: AlertSeverity
  ) => {
    setIsCreating(true);
    try {
      await createDefinition({
        prompt,
        scope,
        severity,
      });
      // Alert added to state by context
    } catch (err) {
      console.error('Failed to create alert:', err);
    } finally {
      setIsCreating(false);
    }
  }, [createDefinition]);

  // Handle alert actions (all use context methods for optimistic updates)
  const handlePause = useCallback(async (id: string) => {
    await pauseDefinition(id);
  }, [pauseDefinition]);

  const handleResume = useCallback(async (id: string) => {
    await resumeDefinition(id);
  }, [resumeDefinition]);

  const handleAcknowledge = useCallback(async (id: string) => {
    await acknowledgeDefinition(id);
  }, [acknowledgeDefinition]);

  const handleDismiss = useCallback(async (id: string) => {
    await dismissDefinition(id);
  }, [dismissDefinition]);

  const handleDelete = useCallback(async (id: string) => {
    await deleteDefinition(id);
  }, [deleteDefinition]);

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  // Count of warn/block severity alerts needing attention (based on lifecycle stage)
  // This is exported via AlertManagerTab for the bottom tab badge
  const _urgentCount = alertDefinitions.filter(
    (a) => (a.severity === 'warn' || a.severity === 'block') &&
           (a.lifecycleStage === 'update' || a.lifecycleStage === 'warn')
  ).length;
  void _urgentCount; // Will be used when AlertManagerTab is refactored

  return (
    <>
      {/* Overlay */}
      {open && <div className="alert-manager-overlay" onClick={onClose} />}

      {/* Drawer */}
      <div className={`alert-manager-drawer ${open ? 'open' : ''}`}>
        {/* Header */}
        <div className="alert-manager-header">
          <h2>Alert Manager</h2>
          <button className="alert-manager-close" onClick={onClose}>
            &times;
          </button>
        </div>

        {/* Prompt Input - Primary Creation Interface */}
        <PromptInput
          onSubmit={handleCreateAlert}
          isCreating={isCreating}
        />

        {/* Filters */}
        <div className="alert-manager-filters">
          <AlertFilters
            active={viewFilter}
            onChange={setViewFilter}
            counts={filterCounts}
          />
          <div className="alert-manager-search">
            <input
              type="text"
              placeholder="Search alerts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Alert List */}
        <div className="alert-manager-content">
          {filteredAlerts.length === 0 ? (
            <div className="alert-manager-empty">
              {searchQuery ? (
                <span>No alerts match your search</span>
              ) : viewFilter === 'triggered' ? (
                <span>No alerts need attention</span>
              ) : (
                <span>No alerts in this category</span>
              )}
            </div>
          ) : (
            filteredAlerts.map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onPause={() => handlePause(alert.id)}
                onResume={() => handleResume(alert.id)}
                onAcknowledge={() => handleAcknowledge(alert.id)}
                onDismiss={() => handleDismiss(alert.id)}
                onDelete={() => handleDelete(alert.id)}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}

// Export the bottom tab component for use in App.tsx
interface AlertManagerTabProps {
  onClick: () => void;
  triggeredCount: number;
}

export function AlertManagerTab({ onClick, triggeredCount }: AlertManagerTabProps) {
  return (
    <div className="alert-manager-tab" onClick={onClick}>
      <span>Alert Manager</span>
      {triggeredCount > 0 && <span className="badge urgent">{triggeredCount}</span>}
    </div>
  );
}
