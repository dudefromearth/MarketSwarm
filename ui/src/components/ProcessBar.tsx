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
import '../styles/process-bar.css';

// Phase IDs that can be active
export type ProcessPhase = 'routine' | 'structure' | 'selection' | 'analysis' | 'action' | 'process';

// Map PathContext stages to display phases
type Stage = 'discovery' | 'analysis' | 'action' | 'reflection' | 'distillation';

interface ProcessBarProps {
  stagesVisited: Stage[];
  activePhase?: ProcessPhase;
  cueMode?: 'off' | 'subtle' | 'guided';
}

const PHASES: { id: ProcessPhase; label: string; stages: Stage[]; color: string }[] = [
  { id: 'routine', label: 'Routine', stages: ['discovery'], color: 'warm' },
  { id: 'structure', label: 'Structure', stages: [], color: 'neutral' },
  { id: 'selection', label: 'Selection', stages: [], color: 'neutral' },
  { id: 'analysis', label: 'Analysis', stages: ['analysis'], color: 'neutral' },
  { id: 'action', label: 'Action', stages: ['action'], color: 'neutral' },
  { id: 'process', label: 'Process', stages: ['reflection', 'distillation'], color: 'cool' },
];

export default function ProcessBar({
  stagesVisited,
  activePhase,
  cueMode = 'subtle'
}: ProcessBarProps) {
  // Calculate which phases have been visited and which is active
  const phaseState = useMemo(() => {
    return PHASES.map(phase => {
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
          {PHASES.map((phase, index) => (
            <div key={phase.id} className="process-bar-phase-wrapper">
              <div className={`process-bar-phase process-bar-phase--${phase.color}`}>
                <span className="process-bar-phase-dot" />
                <span className="process-bar-phase-label">{phase.label}</span>
              </div>
              {index < PHASES.length - 1 && (
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
            {index < PHASES.length - 1 && (
              <span className={`process-bar-connector ${phase.visited ? 'visited' : ''}`} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
