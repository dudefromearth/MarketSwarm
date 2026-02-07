/**
 * DailyOnboarding - First Entry State for the Trading Day
 *
 * From ltr-concept.md Section 4:
 * - Entire application slightly grayed out
 * - Horizontal process bar displayed prominently
 * - Non-interactive (informational only)
 * - Click anywhere to activate and fade away
 * - Creates a moment of intentional entry into the trading day
 */

import { useState, useCallback } from 'react';
import '../styles/daily-onboarding.css';

interface DailyOnboardingProps {
  onActivate: () => void;
}

const PHASES = [
  { id: 'routine', label: 'Routine', icon: '1' },
  { id: 'analysis', label: 'Structural Analysis', icon: '2' },
  { id: 'selection', label: 'Selection', icon: '3' },
  { id: 'decision', label: 'Decision', icon: '4' },
  { id: 'process', label: 'Process', icon: '5' },
];

export default function DailyOnboarding({ onActivate }: DailyOnboardingProps) {
  const [fading, setFading] = useState(false);

  const handleClick = useCallback(() => {
    if (fading) return;
    setFading(true);

    // Wait for fade animation to complete before calling onActivate
    setTimeout(() => {
      onActivate();
    }, 400);
  }, [fading, onActivate]);

  return (
    <div
      className={`daily-onboarding-overlay ${fading ? 'fading' : ''}`}
      onClick={handleClick}
    >
      <div className="daily-onboarding-content">
        {/* Subtle heading */}
        <div className="daily-onboarding-heading">
          <span className="heading-line" />
          <span className="heading-text">Today's Path</span>
          <span className="heading-line" />
        </div>

        {/* Horizontal process bar */}
        <div className="daily-process-bar">
          {PHASES.map((phase, index) => (
            <div key={phase.id} className="process-phase-wrapper">
              <div className={`process-phase process-phase-${phase.id}`}>
                <span className="phase-number">{phase.icon}</span>
                <span className="phase-label">{phase.label}</span>
              </div>
              {index < PHASES.length - 1 && (
                <div className="phase-connector">
                  <span className="connector-arrow" />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Subtle instruction */}
        <div className="daily-onboarding-hint">
          Click anywhere to begin
        </div>
      </div>
    </div>
  );
}
