/**
 * Vexy Interaction Types — Shared types for the two-layer interaction system.
 */

// ─── Phases ─────────────────────────────────────────────────────────────────

export type InteractionPhase =
  | 'idle'
  | 'acknowledged'
  | 'working'
  | 'result'
  | 'silent_result'
  | 'refused'
  | 'failed';

// ─── Stage Progress ─────────────────────────────────────────────────────────

export interface InteractionStage {
  name: string;
  index: number;
  count: number;
  message: string;
  pct: number; // 0-100
}

// ─── Dialog Layer ACK ───────────────────────────────────────────────────────

export interface DialogNext {
  action: 'stream' | 'done' | 'none';
  job_id?: string;
  channel?: string;
}

export interface InteractionAck {
  interaction_id: string;
  status: 'proceed' | 'clarify' | 'refuse' | 'silence';
  message?: string;
  next?: DialogNext;
  ui_hints?: Record<string, unknown>;
  tier: string;
  remaining_today: number;
}

// ─── SSE Events ─────────────────────────────────────────────────────────────

export interface InteractionStageEvent {
  event: 'stage';
  job_id: string;
  stage: string;
  stage_index: number;
  stage_count: number;
  message: string;
  ts: number;
}

export interface InteractionResultEvent {
  event: 'result';
  job_id: string;
  interaction_id: string;
  text: string;
  agent: string;
  agent_blend: string[];
  tokens_used: number;
  elevation_hint?: string;
  remaining_today: number;
  ts: number;
}

export interface InteractionErrorEvent {
  event: 'error';
  job_id: string;
  interaction_id: string;
  error: string;
  recoverable: boolean;
  ts: number;
}

export type InteractionSSEEvent =
  | InteractionStageEvent
  | InteractionResultEvent
  | InteractionErrorEvent;

// ─── State Machine ──────────────────────────────────────────────────────────

export interface InteractionState {
  phase: InteractionPhase;
  interactionId: string | null;
  jobId: string | null;
  channel: string | null;
  ackMessage: string | null;
  currentStage: InteractionStage | null;
  result: InteractionResultEvent | null;
  error: string | null;
  tier: string;
  remainingToday: number;
}

// ─── Reducer Actions ────────────────────────────────────────────────────────

export type InteractionAction =
  | { type: 'SEND' }
  | { type: 'ACK_RECEIVED'; payload: InteractionAck }
  | { type: 'ACK_REFUSED'; payload: InteractionAck }
  | { type: 'ACK_SILENCE'; payload: InteractionAck }
  | { type: 'STAGE_RECEIVED'; payload: InteractionStageEvent }
  | { type: 'RESULT_RECEIVED'; payload: InteractionResultEvent }
  | { type: 'ERROR_RECEIVED'; payload: InteractionErrorEvent }
  | { type: 'TIMEOUT' }
  | { type: 'CANCEL' }
  | { type: 'RESET' };
