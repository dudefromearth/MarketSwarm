/**
 * AlertCard - Individual alert display component
 *
 * Renders AlertDefinition objects from the unified alert model.
 * Displays scope, severity, lifecycle stage, and appropriate actions.
 * Supports Algo Alerts with strategy-specific information.
 * Supports ML Alerts with learned pattern insights.
 *
 * From alert-mgr v1.1 + algo-alerts.md + ml-driven-alerts.md:
 * - Lifecycle: CREATED → WATCHING → UPDATE → WARN → ACCOMPLISHED | DISMISSED | OVERRIDDEN
 * - Severity ladder determines UI behavior
 * - Algo alerts show strategy name, intent, trigger condition
 * - ML alerts show "Learned Pattern" badge, confidence, historical context
 */

import { useState, useRef, useEffect } from 'react';
import type { AlertDefinition, AlgoAlertDefinition, MLAlertDefinition } from '../../types/alerts';
import {
  getScopeStyle,
  getSeverityStyle,
  getLifecycleStageStyle,
  requiresAcknowledgment,
  requiresAttention,
  isTerminalStage,
  isAlgoAlert,
  isMLAlert,
  getAlgoClassStyle,
  getStrategyTypeInfo,
  getMLCategoryStyle,
  getMLConfidenceDisplay,
} from '../../types/alerts';

interface AlertCardProps {
  alert: AlertDefinition | AlgoAlertDefinition | MLAlertDefinition;
  onPause: () => void;
  onResume: () => void;
  onAcknowledge: () => void;
  onDismiss: () => void;
  onDelete: () => void;
}

// Format timestamp as relative time
function formatRelativeTime(timestamp: string | undefined): string {
  if (!timestamp) return 'Never';

  const ts = new Date(timestamp).getTime();
  const now = Date.now();
  const diff = now - ts;

  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return new Date(ts).toLocaleDateString();
}

// Format date for display
function formatDate(timestamp: string): string {
  return new Date(timestamp).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

// Get scope display label
function getScopeLabel(scope: AlertDefinition['scope']): string {
  const labels: Record<AlertDefinition['scope'], string> = {
    position: 'Position',
    symbol: 'Symbol',
    portfolio: 'Portfolio',
    workflow: 'Workflow',
    behavioral: 'Behavioral',
  };
  return labels[scope];
}

// Get severity display label
function getSeverityLabel(severity: AlertDefinition['severity']): string {
  const labels: Record<AlertDefinition['severity'], string> = {
    inform: 'Inform',
    notify: 'Notify',
    warn: 'Warn',
    block: 'Block',
  };
  return labels[severity];
}

/**
 * ML Alert Info Component - displays learned pattern details
 * Shows badge, confidence meter, historical context, Vexy narrative
 */
function MLAlertInfo({ alert }: { alert: MLAlertDefinition }) {
  const [showWhy, setShowWhy] = useState(false);
  const categoryStyle = getMLCategoryStyle(alert.mlCategory);
  const confidenceDisplay = getMLConfidenceDisplay(alert.finding.confidence);

  return (
    <div className="ml-alert-info">
      {/* Header with badge and category */}
      <div className="ml-header">
        <span className="ml-learned-badge">
          <span className="ml-badge-icon">🎓</span>
          Learned Pattern
        </span>
        <span
          className="ml-category-badge"
          style={{
            color: categoryStyle.color,
            background: categoryStyle.bgColor,
          }}
        >
          <span className="ml-category-icon">{categoryStyle.icon}</span>
          {categoryStyle.label}
        </span>
      </div>

      {/* Finding summary */}
      <div className="ml-finding-summary">{alert.finding.summary}</div>

      {/* Confidence meter */}
      <div className="ml-confidence-row">
        <span className="ml-confidence-label">Confidence:</span>
        <div className="ml-confidence-meter">
          <div
            className="ml-confidence-fill"
            style={{
              width: `${Math.round(alert.finding.confidence * 100)}%`,
              background: confidenceDisplay.color,
            }}
          />
        </div>
        <span
          className="ml-confidence-value"
          style={{ color: confidenceDisplay.color }}
        >
          {Math.round(alert.finding.confidence * 100)}%
        </span>
      </div>

      {/* Vexy narrative (if present) */}
      {alert.vexyNarrative && (
        <div className="ml-vexy-narrative">
          <span className="vexy-icon">💬</span>
          <span className="vexy-text">{alert.vexyNarrative}</span>
        </div>
      )}

      {/* Historical context (collapsible) */}
      {alert.historicalContext && (
        <div className="ml-historical">
          <button
            className="ml-why-toggle"
            onClick={() => setShowWhy(!showWhy)}
          >
            {showWhy ? '▼' : '▶'} Why?
          </button>
          {showWhy && (
            <div className="ml-historical-details">
              {alert.historicalContext.winRate !== undefined && (
                <div className="ml-stat">
                  <span className="ml-stat-label">Win Rate:</span>
                  <span className="ml-stat-value">
                    {Math.round(alert.historicalContext.winRate * 100)}%
                  </span>
                </div>
              )}
              {alert.historicalContext.sampleSize !== undefined && (
                <div className="ml-stat">
                  <span className="ml-stat-label">Sample Size:</span>
                  <span className="ml-stat-value">
                    {alert.historicalContext.sampleSize} trades
                  </span>
                </div>
              )}
              {alert.historicalContext.avgReturn !== undefined && (
                <div className="ml-stat">
                  <span className="ml-stat-label">Avg Return:</span>
                  <span
                    className="ml-stat-value"
                    style={{
                      color: alert.historicalContext.avgReturn >= 0 ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {alert.historicalContext.avgReturn >= 0 ? '+' : ''}
                    {(alert.historicalContext.avgReturn * 100).toFixed(1)}%
                  </span>
                </div>
              )}
              {alert.historicalContext.outcomeDistribution && (
                <div className="ml-outcome-dist">
                  <div
                    className="ml-outcome-bar profitable"
                    style={{
                      width: `${alert.historicalContext.outcomeDistribution.profitable}%`,
                    }}
                    title={`Profitable: ${alert.historicalContext.outcomeDistribution.profitable}%`}
                  />
                  <div
                    className="ml-outcome-bar breakeven"
                    style={{
                      width: `${alert.historicalContext.outcomeDistribution.breakeven}%`,
                    }}
                    title={`Breakeven: ${alert.historicalContext.outcomeDistribution.breakeven}%`}
                  />
                  <div
                    className="ml-outcome-bar loss"
                    style={{
                      width: `${alert.historicalContext.outcomeDistribution.loss}%`,
                    }}
                    title={`Loss: ${alert.historicalContext.outcomeDistribution.loss}%`}
                  />
                </div>
              )}
              {alert.historicalContext.lastOccurrence && (
                <div className="ml-stat">
                  <span className="ml-stat-label">Last seen:</span>
                  <span className="ml-stat-value">
                    {formatRelativeTime(alert.historicalContext.lastOccurrence)}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Override tracking badge */}
      {alert.wasOverridden && (
        <div className="ml-override-badge">
          <span className="override-icon">⚡</span>
          Overridden
          {alert.overrideOutcome && (
            <span
              className={`override-outcome ${alert.overrideOutcome}`}
              style={{
                color:
                  alert.overrideOutcome === 'validated'
                    ? '#22c55e'
                    : alert.overrideOutcome === 'regretted'
                    ? '#ef4444'
                    : '#f59e0b',
              }}
            >
              ({alert.overrideOutcome})
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// Get status display based on lifecycle stage and status
function getStatusDisplay(alert: AlertDefinition): { label: string; color: string; dotColor: string; pulse: boolean } {
  // Paused takes precedence
  if (alert.status === 'paused') {
    return {
      label: 'Paused',
      color: '#6b7280',
      dotColor: '#6b7280',
      pulse: false,
    };
  }

  // Use lifecycle stage styling
  const stageStyle = getLifecycleStageStyle(alert.lifecycleStage);

  // Warn stage gets pulse animation
  const pulse = alert.lifecycleStage === 'warn';

  return {
    label: stageStyle.label,
    color: stageStyle.color,
    dotColor: stageStyle.color,
    pulse,
  };
}

export default function AlertCard({
  alert,
  onPause,
  onResume,
  onAcknowledge,
  onDismiss,
  onDelete,
}: AlertCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [menuOpen]);

  const scopeStyle = getScopeStyle(alert.scope);
  const severityStyle = getSeverityStyle(alert.severity);
  const lifecycleStyle = getLifecycleStageStyle(alert.lifecycleStage);
  const statusDisplay = getStatusDisplay(alert);

  // Lifecycle-based state checks
  const needsAttentionNow = requiresAttention(alert.lifecycleStage);
  const isWarnStage = alert.lifecycleStage === 'warn';
  const isTerminal = isTerminalStage(alert.lifecycleStage);
  const needsAck = requiresAcknowledgment(alert.severity) && needsAttentionNow;
  const isPaused = alert.status === 'paused';

  return (
    <div
      className={`alert-card ${isPaused ? 'paused' : ''} ${needsAttentionNow ? 'needs-attention' : ''} ${isTerminal ? 'terminal' : ''}`}
      style={isWarnStage ? { borderColor: severityStyle.color } : undefined}
    >
      <div className="alert-card-header">
        {/* Status dot */}
        <div className="alert-status">
          <span
            className={`status-dot ${statusDisplay.pulse ? 'pulse' : ''}`}
            style={{ background: statusDisplay.dotColor }}
          />
        </div>

        {/* Scope badge */}
        <span
          className="alert-scope-badge"
          style={{
            background: scopeStyle.bgColor,
            color: scopeStyle.color,
          }}
        >
          {getScopeLabel(alert.scope)}
        </span>

        {/* Severity badge */}
        <span
          className="alert-severity-badge"
          style={{
            background: severityStyle.bgColor,
            color: severityStyle.color,
          }}
        >
          {getSeverityLabel(alert.severity)}
        </span>

        {/* Lifecycle stage badge */}
        <span
          className="alert-lifecycle-badge"
          style={{
            background: lifecycleStyle.bgColor,
            color: lifecycleStyle.color,
          }}
        >
          <span className="lifecycle-icon">{lifecycleStyle.icon}</span>
          {lifecycleStyle.label}
        </span>

        {/* Title if present */}
        {alert.title && <span className="alert-title">{alert.title}</span>}

        {/* Actions menu */}
        <div className="alert-actions" ref={menuRef}>
          <button className="alert-menu-btn" onClick={() => setMenuOpen(!menuOpen)}>
            <span className="menu-dots">⋮</span>
          </button>
          {menuOpen && (
            <div className="alert-menu">
              {isPaused ? (
                <button
                  onClick={() => {
                    onResume();
                    setMenuOpen(false);
                  }}
                >
                  Resume
                </button>
              ) : (
                <button
                  onClick={() => {
                    onPause();
                    setMenuOpen(false);
                  }}
                >
                  Pause
                </button>
              )}
              {needsAttentionNow && (
                <>
                  <button
                    onClick={() => {
                      onAcknowledge();
                      setMenuOpen(false);
                    }}
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => {
                      onDismiss();
                      setMenuOpen(false);
                    }}
                  >
                    Dismiss
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  onDelete();
                  setMenuOpen(false);
                }}
                className="delete"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="alert-card-body">
        {/* Algo Alert Info - strategy details */}
        {isAlgoAlert(alert) && (
          <div className="algo-alert-info">
            <div className="algo-header">
              <span className="strategy-badge">
                <span className="strategy-icon">
                  {getStrategyTypeInfo(alert.strategyType).icon}
                </span>
                {getStrategyTypeInfo(alert.strategyType).label}
              </span>
              <span
                className="algo-class-badge"
                style={{
                  color: getAlgoClassStyle(alert.algoConfig.algoClass).color,
                }}
              >
                {getAlgoClassStyle(alert.algoConfig.algoClass).icon}{' '}
                {getAlgoClassStyle(alert.algoConfig.algoClass).label}
              </span>
            </div>
            <div className="algo-intent">{alert.intentSummary}</div>
            {alert.triggerCondition && (
              <div className="algo-trigger">
                <span className="trigger-label">Trigger:</span> {alert.triggerCondition}
              </div>
            )}
            {alert.algoConfig.suggestedAction && (
              <div className="algo-suggestion">
                Suggested: <strong>{alert.algoConfig.suggestedAction}</strong>
              </div>
            )}
            {alert.confidence !== undefined && (
              <div className="algo-confidence">
                Confidence: {Math.round(alert.confidence * 100)}%
              </div>
            )}
          </div>
        )}

        {/* ML Alert Info - learned pattern details */}
        {isMLAlert(alert) && (
          <MLAlertInfo alert={alert} />
        )}

        {/* Prompt text - the canonical alert definition */}
        <p className="alert-prompt">{alert.prompt}</p>

        {/* Target reference info */}
        {alert.targetRef && (
          <div className="alert-target">
            {alert.targetRef.symbol && (
              <span className="target-item">
                <span className="target-label">Symbol</span>
                <span className="target-value">{alert.targetRef.symbol}</span>
              </span>
            )}
            {alert.targetRef.positionId && (
              <span className="target-item">
                <span className="target-label">Position</span>
                <span className="target-value">#{alert.targetRef.positionId}</span>
              </span>
            )}
          </div>
        )}

        {/* Acknowledgment required banner */}
        {needsAck && (
          <div
            className="alert-ack-required"
            style={{
              background: severityStyle.bgColor,
              borderColor: severityStyle.color,
            }}
          >
            <span style={{ color: severityStyle.color }}>
              {alert.severity === 'block' ? 'Action blocked - ' : 'Attention required - '}
              Acknowledgment needed
            </span>
            <button
              className="ack-btn"
              onClick={onAcknowledge}
              style={{
                background: severityStyle.color,
                color: '#0f0f1a',
              }}
            >
              Acknowledge
            </button>
          </div>
        )}
      </div>

      <div className="alert-card-footer">
        <span className="meta-item">Created: {formatDate(alert.createdAt)}</span>
        {alert.triggerCount > 0 && (
          <span className="meta-item trigger-count">Triggered {alert.triggerCount}x</span>
        )}
        {alert.lastTriggeredAt && (
          <span className="meta-item">Last: {formatRelativeTime(alert.lastTriggeredAt)}</span>
        )}
      </div>
    </div>
  );
}
