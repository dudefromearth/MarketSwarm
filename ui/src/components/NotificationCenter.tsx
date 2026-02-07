// components/NotificationCenter.tsx
// Notification bell with badge and popup list of triggered alerts

import { useState, useRef, useEffect } from 'react';
import { useAlerts } from '../contexts/AlertContext';
import type { Alert } from '../types/alerts';

interface NotificationCenterProps {
  className?: string;
}

// Format time ago string
function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Get alert description for display
function getAlertDescription(alert: Alert): string {
  switch (alert.type) {
    case 'price':
      return `${alert.condition} ${alert.targetValue}`;
    case 'debit':
      return `Debit ${alert.condition} $${alert.targetValue}`;
    case 'profit_target':
      return `Profit target ${alert.targetValue}%`;
    case 'trailing_stop':
      return 'Trailing stop triggered';
    case 'ai_theta_gamma':
      return 'Theta/Gamma zone exit';
    case 'ai_sentiment':
      return `Sentiment ${alert.direction}`;
    case 'ai_risk_zone':
      return `Risk zone: ${alert.zoneType}`;
    default:
      return alert.label || 'Alert triggered';
  }
}

// Get icon for alert type
function getAlertIcon(alert: Alert): string {
  switch (alert.type) {
    case 'price':
      return '📊';
    case 'debit':
    case 'profit_target':
      return '💰';
    case 'trailing_stop':
      return '🛑';
    case 'ai_theta_gamma':
    case 'ai_sentiment':
    case 'ai_risk_zone':
      return '🤖';
    default:
      return '🔔';
  }
}

export default function NotificationCenter({ className = '' }: NotificationCenterProps) {
  const { alerts, getTriggeredAlerts, clearTriggeredAlerts, updateAlert } = useAlerts();
  const [isOpen, setIsOpen] = useState(false);
  const [hasNewSinceOpen, setHasNewSinceOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const lastCountRef = useRef(0);

  // Get triggered alerts sorted by time (newest first)
  const triggeredAlerts = getTriggeredAlerts()
    .sort((a, b) => (b.triggeredAt || 0) - (a.triggeredAt || 0));

  const count = triggeredAlerts.length;

  // Track new alerts arriving
  useEffect(() => {
    if (count > lastCountRef.current && !isOpen) {
      setHasNewSinceOpen(true);
    }
    lastCountRef.current = count;
  }, [count, isOpen]);

  // Clear "new" indicator when opening
  useEffect(() => {
    if (isOpen) {
      setHasNewSinceOpen(false);
    }
  }, [isOpen]);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  // Dismiss a single alert
  const handleDismiss = (alert: Alert, e: React.MouseEvent) => {
    e.stopPropagation();
    updateAlert({ id: alert.id, triggered: false });
  };

  // Dismiss all
  const handleDismissAll = () => {
    clearTriggeredAlerts();
    setIsOpen(false);
  };

  return (
    <div className={`notification-center ${className}`} ref={containerRef}>
      <button
        className={`notification-bell ${count > 0 ? 'has-notifications' : ''} ${hasNewSinceOpen ? 'pulse' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title={count > 0 ? `${count} triggered alert${count > 1 ? 's' : ''}` : 'No alerts'}
      >
        <svg
          className="bell-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {count > 0 && (
          <span className="notification-badge">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="notification-dropdown">
          <div className="notification-header">
            <span className="notification-title">Alerts</span>
            {count > 0 && (
              <button
                className="notification-clear-all"
                onClick={handleDismissAll}
              >
                Clear all
              </button>
            )}
          </div>

          <div className="notification-list">
            {triggeredAlerts.length === 0 ? (
              <div className="notification-empty">
                No triggered alerts
              </div>
            ) : (
              triggeredAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="notification-item"
                  style={{ borderLeftColor: alert.color || '#3b82f6' }}
                >
                  <span className="notification-icon">
                    {getAlertIcon(alert)}
                  </span>
                  <div className="notification-content">
                    <div className="notification-label">
                      {alert.label || getAlertDescription(alert)}
                    </div>
                    <div className="notification-meta">
                      <span className="notification-type">{alert.type}</span>
                      <span className="notification-time">
                        {alert.triggeredAt ? formatTimeAgo(alert.triggeredAt) : ''}
                      </span>
                    </div>
                  </div>
                  <button
                    className="notification-dismiss"
                    onClick={(e) => handleDismiss(alert, e)}
                    title="Dismiss"
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <style>{`
        .notification-center {
          position: relative;
          display: inline-flex;
          align-items: center;
        }

        .notification-bell {
          background: transparent;
          border: none;
          padding: 6px;
          cursor: pointer;
          color: #9ca3af;
          transition: color 0.2s;
          position: relative;
        }

        .notification-bell:hover {
          color: #e5e7eb;
        }

        .notification-bell.has-notifications {
          color: #f59e0b;
        }

        .notification-bell.pulse .bell-icon {
          animation: bell-ring 0.5s ease-in-out;
        }

        @keyframes bell-ring {
          0%, 100% { transform: rotate(0); }
          25% { transform: rotate(15deg); }
          50% { transform: rotate(-15deg); }
          75% { transform: rotate(10deg); }
        }

        .bell-icon {
          width: 20px;
          height: 20px;
        }

        .notification-badge {
          position: absolute;
          top: 0;
          right: 0;
          background: #ef4444;
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

        .notification-dropdown {
          position: absolute;
          top: calc(100% + 8px);
          right: 0;
          width: 320px;
          max-height: 400px;
          background: #1f2937;
          border: 1px solid #374151;
          border-radius: 8px;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
          z-index: 1000;
          overflow: hidden;
        }

        .notification-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          border-bottom: 1px solid #374151;
        }

        .notification-title {
          font-weight: 600;
          color: #e5e7eb;
        }

        .notification-clear-all {
          background: transparent;
          border: none;
          color: #3b82f6;
          font-size: 12px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 4px;
        }

        .notification-clear-all:hover {
          background: rgba(59, 130, 246, 0.1);
        }

        .notification-list {
          overflow-y: auto;
          max-height: 340px;
        }

        .notification-empty {
          padding: 24px;
          text-align: center;
          color: #6b7280;
          font-size: 14px;
        }

        .notification-item {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 12px 16px;
          border-bottom: 1px solid #374151;
          border-left: 3px solid;
          transition: background 0.2s;
        }

        .notification-item:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .notification-item:last-child {
          border-bottom: none;
        }

        .notification-icon {
          font-size: 16px;
          flex-shrink: 0;
        }

        .notification-content {
          flex: 1;
          min-width: 0;
        }

        .notification-label {
          color: #e5e7eb;
          font-size: 13px;
          margin-bottom: 4px;
          word-break: break-word;
        }

        .notification-meta {
          display: flex;
          gap: 8px;
          font-size: 11px;
          color: #6b7280;
        }

        .notification-type {
          text-transform: capitalize;
        }

        .notification-dismiss {
          background: transparent;
          border: none;
          color: #6b7280;
          font-size: 18px;
          cursor: pointer;
          padding: 0 4px;
          line-height: 1;
          flex-shrink: 0;
        }

        .notification-dismiss:hover {
          color: #ef4444;
        }
      `}</style>
    </div>
  );
}
