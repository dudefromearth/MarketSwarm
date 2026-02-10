// components/NotificationCenter.tsx
// System notification bell with badge and popup list
//
// Shows system-level alerts: connectivity, errors, process status, etc.
// This is SEPARATE from trading alerts which are handled by AlertContext.

import { useState, useRef, useEffect } from 'react';
import {
  useSystemNotifications,
  type SystemNotification,
  type NotificationSeverity,
  type NotificationCategory,
} from '../contexts/SystemNotificationsContext';

interface NotificationCenterProps {
  className?: string;
}

// Format time ago
function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Severity colors
const SEVERITY_COLORS: Record<NotificationSeverity, string> = {
  info: '#3b82f6',    // blue
  success: '#22c55e', // green
  warning: '#f59e0b', // amber
  error: '#ef4444',   // red
};

// Category icons
const CATEGORY_ICONS: Record<NotificationCategory, string> = {
  connectivity: '📡',
  api: '🔌',
  sync: '🔄',
  process: '⚙️',
  validation: '⚠️',
  system: '💻',
};

// Severity icons
const SEVERITY_ICONS: Record<NotificationSeverity, string> = {
  info: 'ℹ️',
  success: '✓',
  warning: '⚠',
  error: '✕',
};

export default function NotificationCenter({ className = '' }: NotificationCenterProps) {
  const {
    unreadCount,
    getActive,
    markRead,
    markAllRead,
    dismiss,
    dismissAll,
  } = useSystemNotifications();

  const [isOpen, setIsOpen] = useState(false);
  const [hasNewSinceOpen, setHasNewSinceOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const lastCountRef = useRef(0);

  // Get active (not dismissed) notifications, sorted by time
  const activeNotifications = getActive()
    .sort((a, b) => b.timestamp - a.timestamp);

  const count = unreadCount;

  // Track new notifications arriving
  useEffect(() => {
    if (count > lastCountRef.current && !isOpen) {
      setHasNewSinceOpen(true);
    }
    lastCountRef.current = count;
  }, [count, isOpen]);

  // Clear "new" indicator and mark as read when opening
  useEffect(() => {
    if (isOpen) {
      setHasNewSinceOpen(false);
      // Mark visible ones as read after a short delay
      const timer = setTimeout(() => {
        markAllRead();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [isOpen, markAllRead]);

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

  // Dismiss a single notification
  const handleDismiss = (notification: SystemNotification, e: React.MouseEvent) => {
    e.stopPropagation();
    dismiss(notification.id);
  };

  // Handle action button click
  const handleAction = (notification: SystemNotification, e: React.MouseEvent) => {
    e.stopPropagation();
    if (notification.actionCallback) {
      notification.actionCallback();
    }
    dismiss(notification.id);
  };

  // Dismiss all
  const handleDismissAll = () => {
    dismissAll();
  };

  // Determine bell color based on highest severity
  const hasSevereIssue = activeNotifications.some(n => n.severity === 'error');
  const hasWarning = activeNotifications.some(n => n.severity === 'warning');

  let bellColor = '#9ca3af'; // gray default
  if (count > 0) {
    if (hasSevereIssue) {
      bellColor = '#ef4444'; // red
    } else if (hasWarning) {
      bellColor = '#f59e0b'; // amber
    } else {
      bellColor = '#3b82f6'; // blue
    }
  }

  return (
    <div className={`notification-center ${className}`} ref={containerRef}>
      <button
        className={`notification-bell ${count > 0 ? 'has-notifications' : ''} ${hasNewSinceOpen ? 'pulse' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title={count > 0 ? `${count} system notification${count > 1 ? 's' : ''}` : 'No notifications'}
        style={{ color: bellColor }}
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
          <span className="notification-badge" style={{ background: bellColor }}>
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="notification-dropdown">
          <div className="notification-header">
            <span className="notification-title">System Notifications</span>
            {activeNotifications.length > 0 && (
              <button
                className="notification-clear-all"
                onClick={handleDismissAll}
              >
                Clear all
              </button>
            )}
          </div>

          <div className="notification-list">
            {activeNotifications.length === 0 ? (
              <div className="notification-empty">
                <span className="empty-icon">✓</span>
                <span className="empty-text">All systems operational</span>
              </div>
            ) : (
              activeNotifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`notification-item ${notification.read ? 'read' : 'unread'}`}
                  style={{ borderLeftColor: SEVERITY_COLORS[notification.severity] }}
                  onClick={() => markRead(notification.id)}
                >
                  <div className="notification-icon-col">
                    <span className="category-icon">
                      {CATEGORY_ICONS[notification.category]}
                    </span>
                    <span
                      className={`severity-dot severity-${notification.severity}`}
                      title={notification.severity}
                    />
                  </div>

                  <div className="notification-content">
                    <div className="notification-title-row">
                      <span className="notification-title-text">{notification.title}</span>
                      {!notification.read && <span className="unread-dot" />}
                    </div>
                    <div className="notification-message">{notification.message}</div>
                    {notification.details && (
                      <details className="notification-details">
                        <summary>Details</summary>
                        <pre>{notification.details}</pre>
                      </details>
                    )}
                    <div className="notification-meta">
                      <span className="notification-category">{notification.category}</span>
                      {notification.source && (
                        <span className="notification-source">{notification.source}</span>
                      )}
                      <span className="notification-time">
                        {formatTimeAgo(notification.timestamp)}
                      </span>
                    </div>
                    {notification.actionLabel && (
                      <button
                        className="notification-action"
                        onClick={(e) => handleAction(notification, e)}
                      >
                        {notification.actionLabel}
                      </button>
                    )}
                  </div>

                  <button
                    className="notification-dismiss"
                    onClick={(e) => handleDismiss(notification, e)}
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
          transition: color 0.2s;
          position: relative;
        }

        .notification-bell:hover {
          filter: brightness(1.2);
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
          width: 380px;
          max-height: 480px;
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
          background: #111827;
        }

        .notification-title {
          font-weight: 600;
          color: #e5e7eb;
          font-size: 14px;
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
          max-height: 420px;
        }

        .notification-empty {
          padding: 32px;
          text-align: center;
          color: #22c55e;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
        }

        .empty-icon {
          font-size: 24px;
          opacity: 0.8;
        }

        .empty-text {
          font-size: 14px;
        }

        .notification-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px 16px;
          border-bottom: 1px solid #374151;
          border-left: 3px solid;
          cursor: pointer;
          transition: background 0.2s;
        }

        .notification-item:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .notification-item.unread {
          background: rgba(59, 130, 246, 0.05);
        }

        .notification-item:last-child {
          border-bottom: none;
        }

        .notification-icon-col {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          flex-shrink: 0;
        }

        .category-icon {
          font-size: 18px;
        }

        .severity-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .severity-dot.severity-info { background: #3b82f6; }
        .severity-dot.severity-success { background: #22c55e; }
        .severity-dot.severity-warning { background: #f59e0b; }
        .severity-dot.severity-error { background: #ef4444; }

        .notification-content {
          flex: 1;
          min-width: 0;
        }

        .notification-title-row {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 4px;
        }

        .notification-title-text {
          color: #e5e7eb;
          font-size: 13px;
          font-weight: 500;
        }

        .unread-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #3b82f6;
          flex-shrink: 0;
        }

        .notification-message {
          color: #9ca3af;
          font-size: 12px;
          line-height: 1.4;
          margin-bottom: 6px;
        }

        .notification-details {
          margin: 8px 0;
          font-size: 11px;
        }

        .notification-details summary {
          cursor: pointer;
          color: #6b7280;
        }

        .notification-details pre {
          margin: 8px 0 0;
          padding: 8px;
          background: #111827;
          border-radius: 4px;
          font-size: 10px;
          color: #9ca3af;
          overflow-x: auto;
          white-space: pre-wrap;
          word-break: break-all;
        }

        .notification-meta {
          display: flex;
          gap: 8px;
          font-size: 10px;
          color: #6b7280;
        }

        .notification-category {
          text-transform: capitalize;
          background: rgba(107, 114, 128, 0.2);
          padding: 1px 6px;
          border-radius: 3px;
        }

        .notification-source {
          font-family: monospace;
        }

        .notification-action {
          margin-top: 8px;
          background: #3b82f6;
          border: none;
          color: white;
          font-size: 11px;
          padding: 4px 12px;
          border-radius: 4px;
          cursor: pointer;
        }

        .notification-action:hover {
          background: #2563eb;
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
          opacity: 0.5;
          transition: opacity 0.2s, color 0.2s;
        }

        .notification-item:hover .notification-dismiss {
          opacity: 1;
        }

        .notification-dismiss:hover {
          color: #ef4444;
        }

        /* --- Light Theme --- */
        [data-theme="light"] .notification-dropdown {
          background: #ffffff;
          border-color: #d1d1d6;
          box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }

        [data-theme="light"] .notification-header {
          background: #f5f5f7;
          border-bottom-color: #e5e5ea;
        }

        [data-theme="light"] .notification-title {
          color: #1d1d1f;
        }

        [data-theme="light"] .notification-clear-all {
          color: #007aff;
        }

        [data-theme="light"] .notification-clear-all:hover {
          background: rgba(0, 122, 255, 0.08);
        }

        [data-theme="light"] .notification-empty {
          color: #34c759;
        }

        [data-theme="light"] .notification-item {
          border-bottom-color: #e5e5ea;
        }

        [data-theme="light"] .notification-item:hover {
          background: #f5f5f7;
        }

        [data-theme="light"] .notification-item.unread {
          background: rgba(0, 122, 255, 0.04);
        }

        [data-theme="light"] .notification-title-text {
          color: #1d1d1f;
        }

        [data-theme="light"] .unread-dot {
          background: #007aff;
        }

        [data-theme="light"] .notification-message {
          color: #6e6e73;
        }

        [data-theme="light"] .notification-details summary {
          color: #86868b;
        }

        [data-theme="light"] .notification-details pre {
          background: #f0f0f2;
          color: #48484a;
        }

        [data-theme="light"] .notification-meta {
          color: #aeaeb2;
        }

        [data-theme="light"] .notification-category {
          background: rgba(0, 0, 0, 0.04);
          color: #86868b;
        }

        [data-theme="light"] .notification-action {
          background: #007aff;
        }

        [data-theme="light"] .notification-action:hover {
          background: #0062cc;
        }

        [data-theme="light"] .notification-dismiss {
          color: #aeaeb2;
        }

        [data-theme="light"] .notification-dismiss:hover {
          color: #ff3b30;
        }

        [data-theme="light"] .notification-list::-webkit-scrollbar {
          width: 4px;
        }
        [data-theme="light"] .notification-list::-webkit-scrollbar-track {
          background: transparent;
        }
        [data-theme="light"] .notification-list::-webkit-scrollbar-thumb {
          background: #d1d1d6;
          border-radius: 2px;
        }
      `}</style>
    </div>
  );
}
