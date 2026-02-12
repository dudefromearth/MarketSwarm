/**
 * useVexyInteraction — State machine hook for the two-layer interaction system.
 *
 * State flow:
 *   idle -> SEND -> (fetch /api/vexy/interaction)
 *     -> ACK_RECEIVED -> acknowledged -> STAGE_RECEIVED -> working
 *       -> working (accumulates stages) -> RESULT_RECEIVED -> result
 *                                       -> ERROR_RECEIVED -> failed
 *                                       -> TIMEOUT -> failed
 *     -> ACK_REFUSED -> refused
 *   any -> CANCEL/RESET -> idle
 *
 * Usage:
 *   const { state, phase, send, cancel, reset, isIdle, isWorking, hasResult } =
 *     useVexyInteraction({ origin: 'chat' });
 */

import { useReducer, useCallback, useRef, useEffect } from 'react';
import { subscribeVexyInteraction } from '../services/vexyInteractionSSE';
import type {
  InteractionPhase,
  InteractionState,
  InteractionAction,
  InteractionAck,
  InteractionStage,
  InteractionStageEvent,
  InteractionResultEvent,
  InteractionErrorEvent,
} from '../types/vexyInteraction';

// ─── Reducer ────────────────────────────────────────────────────────────────

const INITIAL_STATE: InteractionState = {
  phase: 'idle',
  interactionId: null,
  jobId: null,
  channel: null,
  ackMessage: null,
  currentStage: null,
  result: null,
  error: null,
  tier: 'observer',
  remainingToday: -1,
};

function reducer(state: InteractionState, action: InteractionAction): InteractionState {
  switch (action.type) {
    case 'SEND':
      return { ...INITIAL_STATE, phase: 'idle' }; // Reset while sending

    case 'ACK_RECEIVED': {
      const ack = action.payload;
      return {
        ...state,
        phase: 'acknowledged',
        interactionId: ack.interaction_id,
        jobId: ack.next?.job_id ?? null,
        channel: ack.next?.channel ?? null,
        ackMessage: ack.message ?? null,
        tier: ack.tier,
        remainingToday: ack.remaining_today,
      };
    }

    case 'ACK_REFUSED': {
      const ack = action.payload;
      return {
        ...state,
        phase: 'refused',
        interactionId: ack.interaction_id,
        ackMessage: ack.message ?? null,
        tier: ack.tier,
        remainingToday: ack.remaining_today,
      };
    }

    case 'ACK_SILENCE': {
      const ack = action.payload;
      return {
        ...state,
        phase: 'silent_result',
        interactionId: ack.interaction_id,
        tier: ack.tier,
        remainingToday: ack.remaining_today,
      };
    }

    case 'STAGE_RECEIVED': {
      const evt = action.payload;
      const stage: InteractionStage = {
        name: evt.stage,
        index: evt.stage_index,
        count: evt.stage_count,
        message: evt.message,
        pct: Math.round(((evt.stage_index + 1) / evt.stage_count) * 100),
      };
      return { ...state, phase: 'working', currentStage: stage };
    }

    case 'RESULT_RECEIVED':
      return {
        ...state,
        phase: 'result',
        result: action.payload,
        remainingToday: action.payload.remaining_today,
        currentStage: null,
      };

    case 'ERROR_RECEIVED':
      return {
        ...state,
        phase: 'failed',
        error: action.payload.error,
        currentStage: null,
      };

    case 'TIMEOUT':
      return {
        ...state,
        phase: 'failed',
        error: 'Request timed out. Please try again.',
        currentStage: null,
      };

    case 'CANCEL':
    case 'RESET':
      return INITIAL_STATE;

    default:
      return state;
  }
}

// ─── Hook Options ───────────────────────────────────────────────────────────

interface UseVexyInteractionOptions {
  origin: string; // "chat" | "routine" | "journal" | "playbook"
  reflectionDial?: number;
  marketContext?: Record<string, unknown>;
  userProfile?: Record<string, unknown>;
  context?: Record<string, unknown>;
  timeoutMs?: number;
}

// ─── Hook ───────────────────────────────────────────────────────────────────

export function useVexyInteraction(options: UseVexyInteractionOptions) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const unsubRef = useRef<(() => void) | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const timeoutMs = options.timeoutMs ?? 30_000;

  // Clean up SSE subscription and timeout on unmount
  useEffect(() => {
    return () => {
      unsubRef.current?.();
      unsubRef.current = null;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, []);

  // Subscribe to SSE when jobId becomes available
  useEffect(() => {
    if (!state.jobId) return;

    // Clear any previous subscription
    unsubRef.current?.();

    const unsub = subscribeVexyInteraction({
      jobId: state.jobId,
      onStage: (evt: InteractionStageEvent) => {
        dispatch({ type: 'STAGE_RECEIVED', payload: evt });
      },
      onResult: (evt: InteractionResultEvent) => {
        dispatch({ type: 'RESULT_RECEIVED', payload: evt });
        // Clear timeout on success
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
          timeoutRef.current = null;
        }
      },
      onError: (evt: InteractionErrorEvent) => {
        dispatch({ type: 'ERROR_RECEIVED', payload: evt });
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
          timeoutRef.current = null;
        }
      },
    });

    unsubRef.current = unsub;

    // Start timeout
    timeoutRef.current = setTimeout(() => {
      dispatch({ type: 'TIMEOUT' });
      unsub();
      unsubRef.current = null;
    }, timeoutMs);

    return () => {
      unsub();
      unsubRef.current = null;
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [state.jobId, timeoutMs]);

  // ─── Actions ──────────────────────────────────────────────────────────

  const send = useCallback(async (content: string) => {
    dispatch({ type: 'SEND' });

    try {
      const opts = optionsRef.current;
      const response = await fetch('/api/vexy/interaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          surface: opts.origin,
          message: content,
          reflection_dial: opts.reflectionDial ?? 0.6,
          context: opts.context ?? {},
          user_profile: opts.userProfile ?? {},
          market_context: opts.marketContext ?? {},
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed: ${response.status}`);
      }

      const ack: InteractionAck = await response.json();

      switch (ack.status) {
        case 'proceed':
          dispatch({ type: 'ACK_RECEIVED', payload: ack });
          break;
        case 'refuse':
          dispatch({ type: 'ACK_REFUSED', payload: ack });
          break;
        case 'clarify':
          dispatch({ type: 'ACK_REFUSED', payload: ack });
          break;
        case 'silence':
          dispatch({ type: 'ACK_SILENCE', payload: ack });
          break;
        default:
          dispatch({ type: 'ACK_RECEIVED', payload: ack });
      }
    } catch (err) {
      dispatch({
        type: 'ERROR_RECEIVED',
        payload: {
          event: 'error',
          job_id: '',
          interaction_id: '',
          error: err instanceof Error ? err.message : 'Failed to send',
          recoverable: true,
          ts: Date.now(),
        },
      });
    }
  }, []);

  const cancel = useCallback(async () => {
    if (state.jobId) {
      try {
        await fetch(`/api/vexy/interaction/cancel/${state.jobId}`, {
          method: 'POST',
          credentials: 'include',
        });
      } catch {
        // Best-effort cancel
      }
    }
    unsubRef.current?.();
    unsubRef.current = null;
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    dispatch({ type: 'CANCEL' });
  }, [state.jobId]);

  const reset = useCallback(() => {
    unsubRef.current?.();
    unsubRef.current = null;
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    dispatch({ type: 'RESET' });
  }, []);

  return {
    state,
    phase: state.phase,
    isIdle: state.phase === 'idle',
    isWorking: state.phase === 'acknowledged' || state.phase === 'working',
    hasResult: state.phase === 'result',
    isRefused: state.phase === 'refused',
    isFailed: state.phase === 'failed',
    currentStage: state.currentStage,
    result: state.result,
    error: state.error,
    ackMessage: state.ackMessage,
    tier: state.tier,
    remainingToday: state.remainingToday,
    send,
    cancel,
    reset,
  };
}
