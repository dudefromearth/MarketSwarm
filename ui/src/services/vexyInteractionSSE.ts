/**
 * vexyInteractionSSE — Singleton EventSource for /sse/vexy-interaction.
 *
 * Follows the alertSSEManager.ts pattern:
 * - Opens on first subscriber, closes on last unsubscribe
 * - Fans out SSE events to subscribers with jobId filtering
 * - Auto-reconnect with exponential backoff
 *
 * Events listened for:
 *   vexy_interaction_stage  → InteractionStageEvent
 *   vexy_interaction_result → InteractionResultEvent
 *   vexy_interaction_error  → InteractionErrorEvent
 */

import type {
  InteractionStageEvent,
  InteractionResultEvent,
  InteractionErrorEvent,
} from '../types/vexyInteraction';

type StageHandler = (event: InteractionStageEvent) => void;
type ResultHandler = (event: InteractionResultEvent) => void;
type ErrorHandler = (event: InteractionErrorEvent) => void;

interface Subscriber {
  jobId: string;
  onStage?: StageHandler;
  onResult?: ResultHandler;
  onError?: ErrorHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

let eventSource: EventSource | null = null;
let subscribers: Subscriber[] = [];
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;

const MAX_RECONNECT_DELAY = 30_000;
const BASE_DELAY = 2_000;

function connect() {
  if (eventSource) {
    eventSource.close();
  }

  const es = new EventSource('/sse/vexy-interaction', { withCredentials: true });

  es.onopen = () => {
    reconnectAttempts = 0;
    subscribers.forEach((s) => s.onConnect?.());
  };

  es.onerror = () => {
    es.close();
    eventSource = null;
    subscribers.forEach((s) => s.onDisconnect?.());
    scheduleReconnect();
  };

  // Listen for interaction events
  es.addEventListener('vexy_interaction_stage', (e: MessageEvent) => {
    try {
      const data: InteractionStageEvent = JSON.parse(e.data);
      subscribers.forEach((s) => {
        if (s.jobId === data.job_id) {
          s.onStage?.(data);
        }
      });
    } catch (err) {
      console.error('[vexy-interaction-sse] stage parse error:', err);
    }
  });

  es.addEventListener('vexy_interaction_result', (e: MessageEvent) => {
    try {
      const data: InteractionResultEvent = JSON.parse(e.data);
      subscribers.forEach((s) => {
        if (s.jobId === data.job_id) {
          s.onResult?.(data);
        }
      });
    } catch (err) {
      console.error('[vexy-interaction-sse] result parse error:', err);
    }
  });

  es.addEventListener('vexy_interaction_error', (e: MessageEvent) => {
    try {
      const data: InteractionErrorEvent = JSON.parse(e.data);
      subscribers.forEach((s) => {
        if (s.jobId === data.job_id) {
          s.onError?.(data);
        }
      });
    } catch (err) {
      console.error('[vexy-interaction-sse] error parse error:', err);
    }
  });

  eventSource = es;
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (subscribers.length === 0) return;

  const delay = Math.min(
    BASE_DELAY * Math.pow(2, reconnectAttempts) + Math.random() * 1000,
    MAX_RECONNECT_DELAY,
  );
  reconnectAttempts++;

  reconnectTimer = setTimeout(connect, delay);
}

/**
 * Subscribe to interaction events for a specific job.
 * Opens the SSE connection on first subscriber, closes on last unsubscribe.
 *
 * @returns unsubscribe function
 */
export function subscribeVexyInteraction(opts: {
  jobId: string;
  onStage?: StageHandler;
  onResult?: ResultHandler;
  onError?: ErrorHandler;
  onConnect?: () => void;
  onDisconnect?: () => void;
}): () => void {
  const subscriber: Subscriber = {
    jobId: opts.jobId,
    onStage: opts.onStage,
    onResult: opts.onResult,
    onError: opts.onError,
    onConnect: opts.onConnect,
    onDisconnect: opts.onDisconnect,
  };
  subscribers.push(subscriber);

  // First subscriber opens the connection
  if (subscribers.length === 1) {
    connect();
  } else if (eventSource?.readyState === EventSource.OPEN) {
    opts.onConnect?.();
  }

  // Return unsubscribe function
  return () => {
    subscribers = subscribers.filter((s) => s !== subscriber);

    // Last subscriber — close connection
    if (subscribers.length === 0) {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      reconnectAttempts = 0;
    }
  };
}
