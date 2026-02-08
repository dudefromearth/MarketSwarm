// ui/src/hooks/useLogLifecycle.ts
// SSE subscription for log lifecycle events

import { useEffect, useRef, useCallback } from 'react';

export interface LogLifecycleEvent {
  type: string;
  timestamp: string;
  user_id: number;
  payload: {
    log_id: string;
    lifecycle_state?: 'active' | 'archived' | 'retired';
    archived_at?: string;
    reactivated_at?: string;
    retire_scheduled_at?: string;
    retired_at?: string;
    ml_included?: boolean;
    active_log_count?: number;
    cap_state?: 'ok' | 'soft_warning' | 'hard_warning';
    grace_days_remaining?: number;
  };
}

interface UseLogLifecycleOptions {
  enabled?: boolean;
  onArchived?: (event: LogLifecycleEvent) => void;
  onReactivated?: (event: LogLifecycleEvent) => void;
  onRetireScheduled?: (event: LogLifecycleEvent) => void;
  onRetireCancelled?: (event: LogLifecycleEvent) => void;
  onRetired?: (event: LogLifecycleEvent) => void;
  onAnyEvent?: (event: LogLifecycleEvent) => void;
}

/**
 * Hook to subscribe to log lifecycle SSE events.
 *
 * Usage:
 * ```tsx
 * useLogLifecycle({
 *   onArchived: (e) => console.log('Log archived:', e.payload.log_id),
 *   onReactivated: (e) => refetchLogs(),
 *   onAnyEvent: (e) => dispatchCustomEvent(e)
 * });
 * ```
 */
export function useLogLifecycle({
  enabled = true,
  onArchived,
  onReactivated,
  onRetireScheduled,
  onRetireCancelled,
  onRetired,
  onAnyEvent,
}: UseLogLifecycleOptions = {}) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttempts = useRef(0);

  const connect = useCallback(() => {
    if (!enabled) return;

    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const es = new EventSource('/sse/logs', { withCredentials: true });
      eventSourceRef.current = es;

      es.onopen = () => {
        console.log('[useLogLifecycle] Connected to /sse/logs');
        reconnectAttempts.current = 0;
      };

      es.onerror = (error) => {
        console.error('[useLogLifecycle] SSE error:', error);
        es.close();

        // Exponential backoff reconnect
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current++;

        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = window.setTimeout(connect, delay);
      };

      // Listen for specific event types
      const handleEvent = (eventType: string, callback?: (e: LogLifecycleEvent) => void) => {
        es.addEventListener(eventType, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data) as LogLifecycleEvent;
            callback?.(data);
            onAnyEvent?.(data);

            // Also dispatch as window event for global listeners
            window.dispatchEvent(new CustomEvent('log-lifecycle', { detail: data }));
          } catch (err) {
            console.error('[useLogLifecycle] Parse error:', err);
          }
        });
      };

      handleEvent('log.lifecycle.archived', onArchived);
      handleEvent('log.lifecycle.reactivated', onReactivated);
      handleEvent('log.lifecycle.retire_scheduled', onRetireScheduled);
      handleEvent('log.lifecycle.retire_cancelled', onRetireCancelled);
      handleEvent('log.lifecycle.retired', onRetired);

      // Also listen for generic 'connected' event
      es.addEventListener('connected', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          console.log('[useLogLifecycle] Connected:', data);
        } catch {
          // Ignore parse errors on connected event
        }
      });

    } catch (err) {
      console.error('[useLogLifecycle] Failed to create EventSource:', err);
    }
  }, [enabled, onArchived, onReactivated, onRetireScheduled, onRetireCancelled, onRetired, onAnyEvent]);

  useEffect(() => {
    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [connect]);

  return {
    isConnected: eventSourceRef.current?.readyState === EventSource.OPEN,
  };
}

/**
 * Utility to listen for log lifecycle events globally.
 *
 * Usage in any component:
 * ```tsx
 * useEffect(() => {
 *   const handler = (e: CustomEvent<LogLifecycleEvent>) => {
 *     if (e.detail.payload.log_id === currentLogId) {
 *       refetchData();
 *     }
 *   };
 *   window.addEventListener('log-lifecycle', handler);
 *   return () => window.removeEventListener('log-lifecycle', handler);
 * }, [currentLogId]);
 * ```
 */
export function useLogLifecycleListener(
  callback: (event: LogLifecycleEvent) => void,
  deps: React.DependencyList = []
) {
  useEffect(() => {
    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<LogLifecycleEvent>;
      callback(customEvent.detail);
    };

    window.addEventListener('log-lifecycle', handler);
    return () => window.removeEventListener('log-lifecycle', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
