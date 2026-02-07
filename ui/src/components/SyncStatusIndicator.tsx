// components/SyncStatusIndicator.tsx
// Visual indicator for offline sync status with user-friendly explanations

import { useEffect } from 'react';
import { useSyncStatus } from '../contexts/ApiClientContext';

interface SyncStatusIndicatorProps {
  /** Show detailed text (default: true) */
  showText?: boolean;
  /** Compact mode - just the dot (default: false) */
  compact?: boolean;
  /** Additional className */
  className?: string;
}

// Tooltip messages explaining each status
const STATUS_TOOLTIPS = {
  synced: 'All changes saved to server',
  pending: (count: number) =>
    `${count} unsaved change${count > 1 ? 's' : ''} stored locally. ` +
    'Will sync automatically when online.',
  syncing: 'Saving changes to server...',
  offline: 'You are offline. Changes will be saved locally and sync when you reconnect.',
  error: 'Failed to sync some changes. Will retry automatically.',
};

export default function SyncStatusIndicator({
  showText = true,
  compact = false,
  className = '',
}: SyncStatusIndicatorProps) {
  const {
    isOnline,
    isSyncing,
    hasPendingChanges,
    pendingCount,
    hasError,
  } = useSyncStatus();

  // Warn user before leaving page with pending changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasPendingChanges) {
        const message = `You have ${pendingCount} unsaved change${pendingCount > 1 ? 's' : ''}. ` +
          'These are stored locally and will sync when you return online, ' +
          'but closing the browser may lose them.';
        e.preventDefault();
        e.returnValue = message;
        return message;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasPendingChanges, pendingCount]);

  // Determine status and styling
  let statusColor: string;
  let statusText: string;
  let tooltip: string;
  let pulseClass = '';

  if (hasError) {
    statusColor = '#ef4444'; // red
    statusText = 'Sync error';
    tooltip = STATUS_TOOLTIPS.error;
  } else if (isSyncing) {
    statusColor = '#3b82f6'; // blue
    statusText = 'Syncing...';
    tooltip = STATUS_TOOLTIPS.syncing;
    pulseClass = 'sync-pulse';
  } else if (hasPendingChanges) {
    statusColor = '#f59e0b'; // amber
    statusText = `${pendingCount} pending`;
    tooltip = STATUS_TOOLTIPS.pending(pendingCount);
  } else if (!isOnline) {
    statusColor = '#6b7280'; // gray
    statusText = 'Offline';
    tooltip = STATUS_TOOLTIPS.offline;
  } else {
    statusColor = '#22c55e'; // green
    statusText = 'Synced';
    tooltip = STATUS_TOOLTIPS.synced;
  }

  if (compact) {
    return (
      <span
        className={`sync-indicator-dot ${pulseClass} ${className}`}
        style={{ backgroundColor: statusColor }}
        title={tooltip}
      />
    );
  }

  return (
    <div className={`sync-indicator ${className}`} title={tooltip}>
      <span
        className={`sync-indicator-dot ${pulseClass}`}
        style={{ backgroundColor: statusColor }}
      />
      {showText && (
        <span className="sync-indicator-text">{statusText}</span>
      )}
      <style>{`
        .sync-indicator {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #9ca3af;
        }

        .sync-indicator-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .sync-indicator-text {
          white-space: nowrap;
        }

        .sync-pulse {
          animation: sync-pulse 1.5s ease-in-out infinite;
        }

        @keyframes sync-pulse {
          0%, 100% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.6;
            transform: scale(1.2);
          }
        }
      `}</style>
    </div>
  );
}
