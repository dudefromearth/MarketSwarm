/**
 * AlertToastContainer - Toast notifications for alert triggers
 *
 * From alert-mgr v1.1 spec section 7:
 * - inform: passive awareness (no toast, just badge)
 * - notify: toast + log (ephemeral)
 * - warn: persistent banner until acknowledged
 * - block: prevents action (handled by BlockDialog)
 *
 * Toasts stack in bottom-right, auto-dismiss based on severity.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAlerts } from '../contexts/AlertContext';
import type { AlertSeverity, AlertDefinition } from '../types/alerts';
import { getSeverityStyle } from '../types/alerts';

interface Toast {
  id: string;
  alertId: string;
  prompt: string;
  severity: AlertSeverity;
  timestamp: number;
  acknowledged: boolean;
}

// Auto-dismiss delays by severity (ms)
const DISMISS_DELAYS: Record<AlertSeverity, number> = {
  inform: 0,     // No toast shown
  notify: 5000,  // 5 seconds
  warn: 0,       // Manual dismiss only
  block: 0,      // Manual dismiss only
};

export default function AlertToastContainer() {
  const { alertDefinitions, acknowledgeDefinition, dismissDefinition } = useAlerts();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const prevDefinitionsRef = useRef<AlertDefinition[]>([]);

  // Watch for new alerts entering update/warn stage
  useEffect(() => {
    const prevDefs = prevDefinitionsRef.current;
    const newToasts: Toast[] = [];

    alertDefinitions.forEach((def) => {
      // Check if this alert just entered update or warn stage
      const prevDef = prevDefs.find((p) => p.id === def.id);
      const justTriggered =
        (def.lifecycleStage === 'update' || def.lifecycleStage === 'warn') &&
        (!prevDef || (prevDef.lifecycleStage !== 'update' && prevDef.lifecycleStage !== 'warn'));

      // Don't show toast for inform severity
      if (justTriggered && def.severity !== 'inform') {
        // Check if we already have a toast for this alert
        const existingToast = toasts.find((t) => t.alertId === def.id);
        if (!existingToast) {
          newToasts.push({
            id: `toast-${def.id}-${Date.now()}`,
            alertId: def.id,
            prompt: def.prompt,
            severity: def.severity,
            timestamp: Date.now(),
            acknowledged: false,
          });
        }
      }
    });

    if (newToasts.length > 0) {
      setToasts((prev) => [...prev, ...newToasts]);
    }

    prevDefinitionsRef.current = alertDefinitions;
  }, [alertDefinitions, toasts]);

  // Auto-dismiss notify toasts
  useEffect(() => {
    const timers: number[] = [];

    toasts.forEach((toast) => {
      if (toast.severity === 'notify' && !toast.acknowledged) {
        const delay = DISMISS_DELAYS.notify;
        const timer = window.setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== toast.id));
        }, delay);
        timers.push(timer);
      }
    });

    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, [toasts]);

  // Handle acknowledge
  const handleAcknowledge = useCallback(async (toast: Toast) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === toast.id ? { ...t, acknowledged: true } : t))
    );
    await acknowledgeDefinition(toast.alertId);
    // Remove after animation
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 300);
  }, [acknowledgeDefinition]);

  // Handle dismiss
  const handleDismiss = useCallback(async (toast: Toast) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === toast.id ? { ...t, acknowledged: true } : t))
    );
    await dismissDefinition(toast.alertId);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 300);
  }, [dismissDefinition]);

  if (toasts.length === 0) return null;

  return (
    <div className="alert-toast-container">
      {toasts.map((toast) => {
        const style = getSeverityStyle(toast.severity);
        return (
          <div
            key={toast.id}
            className={`alert-toast severity-${toast.severity} ${toast.acknowledged ? 'dismissed' : ''}`}
            style={{
              borderLeftColor: style.color,
              background: style.bgColor,
            }}
          >
            <div className="toast-icon" style={{ color: style.color }}>
              {style.icon}
            </div>
            <div className="toast-content">
              <div className="toast-severity" style={{ color: style.color }}>
                {style.label}
              </div>
              <div className="toast-message">{toast.prompt}</div>
            </div>
            <div className="toast-actions">
              {(toast.severity === 'warn' || toast.severity === 'block') && (
                <button
                  className="toast-ack-btn"
                  onClick={() => handleAcknowledge(toast)}
                  style={{ background: style.color }}
                >
                  Acknowledge
                </button>
              )}
              <button
                className="toast-dismiss-btn"
                onClick={() => handleDismiss(toast)}
                title="Dismiss"
              >
                ×
              </button>
            </div>
          </div>
        );
      })}

      <style>{`
        .alert-toast-container {
          position: fixed;
          bottom: 60px;
          right: 20px;
          display: flex;
          flex-direction: column-reverse;
          gap: 10px;
          z-index: 1100;
          max-width: 400px;
        }

        .alert-toast {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 14px 16px;
          background: #1f2937;
          border-radius: 8px;
          border-left: 4px solid;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
          animation: toast-slide-in 0.3s ease-out;
        }

        .alert-toast.dismissed {
          animation: toast-slide-out 0.3s ease-out forwards;
        }

        @keyframes toast-slide-in {
          from {
            opacity: 0;
            transform: translateX(100%);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        @keyframes toast-slide-out {
          from {
            opacity: 1;
            transform: translateX(0);
          }
          to {
            opacity: 0;
            transform: translateX(100%);
          }
        }

        .toast-icon {
          font-size: 18px;
          flex-shrink: 0;
        }

        .toast-content {
          flex: 1;
          min-width: 0;
        }

        .toast-severity {
          font-size: 11px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 4px;
        }

        .toast-message {
          color: #e5e7eb;
          font-size: 13px;
          line-height: 1.4;
          word-wrap: break-word;
        }

        .toast-actions {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          flex-shrink: 0;
        }

        .toast-ack-btn {
          border: none;
          color: #0f0f1a;
          font-size: 11px;
          font-weight: 600;
          padding: 6px 12px;
          border-radius: 4px;
          cursor: pointer;
          transition: opacity 0.15s;
        }

        .toast-ack-btn:hover {
          opacity: 0.9;
        }

        .toast-dismiss-btn {
          background: transparent;
          border: none;
          color: #6b7280;
          font-size: 20px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
          transition: color 0.15s;
        }

        .toast-dismiss-btn:hover {
          color: #e5e7eb;
        }

        /* Severity-specific hover effects */
        .alert-toast.severity-warn:hover,
        .alert-toast.severity-block:hover {
          box-shadow: 0 6px 25px rgba(0, 0, 0, 0.5);
        }
      `}</style>
    </div>
  );
}
