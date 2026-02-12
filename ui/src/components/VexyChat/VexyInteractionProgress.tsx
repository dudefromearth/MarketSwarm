/**
 * VexyInteractionProgress — Replaces typing-dots spinner.
 *
 * Renders stage-based progress during async interaction:
 * - Acknowledged: ACK message text + subtle shimmer line
 * - Working: Current stage text + thin progress bar
 * - Failed: Error message in muted style
 * - Cancel link always visible
 */

import type { InteractionPhase, InteractionStage } from '../../types/vexyInteraction';

interface VexyInteractionProgressProps {
  phase: InteractionPhase;
  ackMessage: string | null;
  currentStage: InteractionStage | null;
  error: string | null;
  onCancel: () => void;
}

export default function VexyInteractionProgress({
  phase,
  ackMessage,
  currentStage,
  error,
  onCancel,
}: VexyInteractionProgressProps) {
  if (phase === 'idle' || phase === 'result' || phase === 'silent_result') {
    return null;
  }

  return (
    <div className="vexy-interaction-progress">
      {/* Stage text */}
      <div className="vexy-progress-stage">
        {phase === 'acknowledged' && (
          <span>{ackMessage || 'Reflecting...'}</span>
        )}
        {phase === 'working' && currentStage && (
          <span>{currentStage.message}</span>
        )}
        {phase === 'refused' && (
          <span>{ackMessage || 'Unable to reflect on this.'}</span>
        )}
        {phase === 'failed' && (
          <span>{error || 'Something went wrong.'}</span>
        )}
      </div>

      {/* Progress line */}
      {(phase === 'acknowledged' || phase === 'working') && (
        <div className="vexy-progress-line">
          <div
            className="vexy-progress-fill"
            style={{
              width: currentStage ? `${currentStage.pct}%` : '15%',
            }}
          />
        </div>
      )}

      {/* Cancel link */}
      {(phase === 'acknowledged' || phase === 'working') && (
        <button className="vexy-progress-cancel" onClick={onCancel}>
          cancel
        </button>
      )}
    </div>
  );
}
