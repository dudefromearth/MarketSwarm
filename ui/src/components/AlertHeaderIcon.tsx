/**
 * AlertHeaderIcon - Header alert indicator with badge and dropdown preview
 *
 * Shows trading alerts needing attention from the v1.1 Alert Manager.
 * - Badge shows count of alerts in update/warn lifecycle stages
 * - Clicking opens AlertManager drawer
 * - Color indicates highest severity
 *
 * From alert-mgr v1.1 spec section 10.1
 */

import { useMemo } from 'react';
import { useAlerts } from '../contexts/AlertContext';
import type { AlertSeverity } from '../types/alerts';

interface AlertHeaderIconProps {
  onClick: () => void;
  className?: string;
}

// Severity color mapping (highest priority first)
const SEVERITY_COLORS: Record<AlertSeverity, string> = {
  block: '#ef4444',  // red
  warn: '#f59e0b',   // amber
  notify: '#3b82f6', // blue
  inform: '#9ca3af', // gray
};

export default function AlertHeaderIcon({ onClick, className = '' }: AlertHeaderIconProps) {
  const { alerts, alertDefinitions, getDefinitionsNeedingAttention } = useAlerts();

  // Get alerts needing attention
  const attentionAlerts = useMemo(() => {
    // Try v1.1 definitions first
    const definitions = getDefinitionsNeedingAttention();
    if (definitions.length > 0) {
      return definitions;
    }
    // Fall back to legacy alerts
    return alerts.filter((a) => a.triggered);
  }, [alerts, alertDefinitions, getDefinitionsNeedingAttention]);

  const count = attentionAlerts.length;

  // Determine icon color based on highest severity
  const iconColor = useMemo(() => {
    if (count === 0) return '#6b7280'; // gray

    // Check for highest severity alert
    const hasBlock = attentionAlerts.some((a) =>
      'severity' in a ? a.severity === 'block' : a.priority === 'critical'
    );
    if (hasBlock) return SEVERITY_COLORS.block;

    const hasWarn = attentionAlerts.some((a) =>
      'severity' in a ? a.severity === 'warn' : a.priority === 'high'
    );
    if (hasWarn) return SEVERITY_COLORS.warn;

    const hasNotify = attentionAlerts.some((a) =>
      'severity' in a ? a.severity === 'notify' : a.priority === 'medium'
    );
    if (hasNotify) return SEVERITY_COLORS.notify;

    return SEVERITY_COLORS.inform;
  }, [attentionAlerts, count]);

  return (
    <button
      className={`alert-header-icon ${count > 0 ? 'has-alerts' : ''} ${className}`}
      onClick={onClick}
      title={count > 0 ? `${count} alert${count > 1 ? 's' : ''} need attention` : 'No alerts'}
      style={{ color: iconColor }}
    >
      {/* Alert bell/warning icon */}
      <svg
        className="alert-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>

      {/* Badge */}
      {count > 0 && (
        <span className="alert-badge" style={{ background: iconColor }}>
          {count > 99 ? '99+' : count}
        </span>
      )}

      <style>{`
        .alert-header-icon {
          background: transparent;
          border: none;
          padding: 6px;
          cursor: pointer;
          transition: color 0.2s, transform 0.2s;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .alert-header-icon:hover {
          filter: brightness(1.2);
          transform: scale(1.05);
        }

        .alert-header-icon.has-alerts {
          animation: alert-pulse 2s ease-in-out infinite;
        }

        @keyframes alert-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }

        .alert-icon {
          width: 20px;
          height: 20px;
        }

        .alert-badge {
          position: absolute;
          top: 0;
          right: 0;
          color: white;
          font-size: 10px;
          font-weight: 600;
          min-width: 16px;
          height: 16px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 0 4px;
          line-height: 1;
        }
      `}</style>
    </button>
  );
}
