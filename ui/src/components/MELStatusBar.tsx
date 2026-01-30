/**
 * MELStatusBar - Compact MEL status display for header.
 *
 * Shows global integrity and individual model states in a compact format:
 * MEL: 42% │ Γ:84✓ │ VP:62⚠ │ LIQ:35✗ │ VOL:28✗ │ SES:57⚠ │ [FOMC]
 */

import { useState } from 'react';
import type { MELSnapshot, ModelState } from '../hooks/useMEL';
import { getStateIndicator, getStateColor, getTrendArrow } from '../hooks/useMEL';
import MELDashboard from './MELDashboard';

interface MELStatusBarProps {
  snapshot: MELSnapshot | null;
  connected: boolean;
  onOpenDashboard?: () => void;
}

export default function MELStatusBar({ snapshot, connected, onOpenDashboard }: MELStatusBarProps) {
  const [showDashboard, setShowDashboard] = useState(false);

  if (!connected || !snapshot) {
    return (
      <div className="mel-status-bar mel-disconnected">
        <span className="mel-label">MEL</span>
        <span className="mel-offline">Offline</span>
      </div>
    );
  }

  const { global_structure_integrity, event_flags } = snapshot;

  // Determine global state
  const globalState: ModelState =
    global_structure_integrity >= 70 ? 'VALID' :
    global_structure_integrity >= 50 ? 'DEGRADED' : 'REVOKED';

  const handleClick = () => {
    if (onOpenDashboard) {
      onOpenDashboard();
    } else {
      setShowDashboard(true);
    }
  };

  return (
    <>
      <div
        className={`mel-status-bar mel-${globalState.toLowerCase()}`}
        onClick={handleClick}
        title="Click to open MEL Dashboard"
      >
        {/* Global Integrity */}
        <span className="mel-global">
          <span className="mel-label">MEL:</span>
          <span className="mel-value" style={{ color: getStateColor(globalState) }}>
            {global_structure_integrity.toFixed(0)}%
          </span>
        </span>

        <span className="mel-separator">│</span>

        {/* Gamma */}
        <ModelIndicator
          label="Γ"
          score={snapshot.gamma}
        />

        <span className="mel-separator">│</span>

        {/* Volume Profile */}
        <ModelIndicator
          label="VP"
          score={snapshot.volume_profile}
        />

        <span className="mel-separator">│</span>

        {/* Liquidity */}
        <ModelIndicator
          label="LIQ"
          score={snapshot.liquidity}
        />

        <span className="mel-separator">│</span>

        {/* Volatility */}
        <ModelIndicator
          label="VOL"
          score={snapshot.volatility}
        />

        <span className="mel-separator">│</span>

        {/* Session */}
        <ModelIndicator
          label="SES"
          score={snapshot.session_structure}
        />

        {/* Coherence */}
        {snapshot.coherence_state !== 'STABLE' && (
          <>
            <span className="mel-separator">│</span>
            <span className={`mel-coherence mel-coherence-${snapshot.coherence_state.toLowerCase()}`}>
              {snapshot.coherence_state}
            </span>
          </>
        )}

        {/* Event Flags */}
        {event_flags.length > 0 && (
          <>
            <span className="mel-separator">│</span>
            <span className="mel-events">
              [{event_flags.join(', ')}]
            </span>
          </>
        )}
      </div>

      {showDashboard && (
        <MELDashboard
          snapshot={snapshot}
          onClose={() => setShowDashboard(false)}
        />
      )}
    </>
  );
}

interface ModelIndicatorProps {
  label: string;
  score: {
    effectiveness: number;
    state: ModelState;
    trend: 'improving' | 'stable' | 'degrading';
  };
}

function ModelIndicator({ label, score }: ModelIndicatorProps) {
  const indicator = getStateIndicator(score.state);
  const color = getStateColor(score.state);
  const trend = getTrendArrow(score.trend);

  return (
    <span className="mel-model" title={`${label}: ${score.effectiveness.toFixed(0)}% ${score.state}`}>
      <span className="mel-model-label">{label}:</span>
      <span className="mel-model-value" style={{ color }}>
        {score.effectiveness.toFixed(0)}
      </span>
      <span className="mel-model-indicator" style={{ color }}>
        {indicator}
      </span>
      {score.trend !== 'stable' && (
        <span className="mel-model-trend">{trend}</span>
      )}
    </span>
  );
}
