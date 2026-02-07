// components/SyncStatusIndicator.tsx
// Visual indicator for offline sync status

import { useSyncStatus } from '../contexts/ApiClientContext';

interface SyncStatusIndicatorProps {
  /** Show detailed text (default: true) */
  showText?: boolean;
  /** Compact mode - just the dot (default: false) */
  compact?: boolean;
  /** Additional className */
  className?: string;
}

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

  // Determine status and styling
  let statusColor: string;
  let statusText: string;
  let pulseClass = '';

  if (hasError) {
    statusColor = '#ef4444'; // red
    statusText = 'Sync error';
  } else if (isSyncing) {
    statusColor = '#3b82f6'; // blue
    statusText = 'Syncing...';
    pulseClass = 'sync-pulse';
  } else if (hasPendingChanges) {
    statusColor = '#f59e0b'; // amber
    statusText = `${pendingCount} pending`;
  } else if (!isOnline) {
    statusColor = '#6b7280'; // gray
    statusText = 'Offline';
  } else {
    statusColor = '#22c55e'; // green
    statusText = 'Synced';
  }

  if (compact) {
    return (
      <span
        className={`sync-indicator-dot ${pulseClass} ${className}`}
        style={{ backgroundColor: statusColor }}
        title={statusText}
      />
    );
  }

  return (
    <div className={`sync-indicator ${className}`}>
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
