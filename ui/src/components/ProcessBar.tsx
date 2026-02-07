/**
 * ProcessBar - Persistent Process Phase Indicator
 *
 * From pr-spec.md:
 * - Always visible
 * - Displays the phases of the trading loop
 * - Informational only
 * - Not interactive
 * - Cannot be disabled
 *
 * This bar is the "anchor of orientation."
 * It reinforces the left-to-right flow:
 * Routine → Structure → Selection → Analysis → Action → Process
 *
 * Note: "Action" phase is transient - it only highlights momentarily (3-5s)
 * when a user commits capital (saves trade, creates alert, sends to broker).
 * It does NOT activate when merely opening modals.
 */

import { useMemo } from 'react';
import { type Stage } from '../constants/pathContent';
import { type ProcessPhase, PROCESS_PHASES } from '../constants/processPhases';
import '../styles/process-bar.css';

// Re-export for convenience
export type { ProcessPhase };

interface ProcessBarProps {
  stagesVisited: Stage[];
  activePhase?: ProcessPhase;
  cueMode?: 'off' | 'subtle' | 'guided';
}

export default function ProcessBar({
  stagesVisited,
  activePhase,
  cueMode = 'subtle'
}: ProcessBarProps) {
  // Calculate which phases have been visited and which is active
  const phaseState = useMemo(() => {
    return PROCESS_PHASES.map(phase => {
      const visited = phase.stages.some(s => stagesVisited.includes(s));
      const active = activePhase === phase.id;
      return { ...phase, visited, active };
    });
  }, [stagesVisited, activePhase]);

  // If cueMode is 'off', show minimal static version
  if (cueMode === 'off') {
    return (
      <div className="process-bar process-bar--static">
        <div className="process-bar-inner">
          {PROCESS_PHASES.map((phase, index) => (
            <div key={phase.id} className="process-bar-phase-wrapper">
              <div className={`process-bar-phase process-bar-phase--${phase.color}`}>
                <span className="process-bar-phase-dot" />
                <span className="process-bar-phase-label">{phase.label}</span>
              </div>
              {index < PROCESS_PHASES.length - 1 && (
                <span className="process-bar-connector" />
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`process-bar process-bar--${cueMode}`}>
      <div className="process-bar-inner">
        {phaseState.map((phase, index) => (
          <div key={phase.id} className="process-bar-phase-wrapper">
            <div
              className={[
                'process-bar-phase',
                `process-bar-phase--${phase.color}`,
                phase.visited ? 'visited' : '',
                phase.active ? 'active' : '',
              ].filter(Boolean).join(' ')}
            >
              <span className="process-bar-phase-dot" />
              <span className="process-bar-phase-label">{phase.label}</span>
            </div>
            {index < PROCESS_PHASES.length - 1 && (
              <span className={`process-bar-connector ${phase.visited ? 'visited' : ''}`} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
