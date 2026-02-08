/**
 * PersonalReadiness - Acknowledge trader's human state without judgment
 *
 * Purpose: Awareness of friction, not self-improvement.
 * All selections are optional. No scoring, no "good/bad" labels.
 * Friction markers are atmospheric conditions, not problems.
 *
 * Design Rules:
 * - Click to select, click again to deselect
 * - Muted chip-style buttons, no borders when unselected
 * - Selected state: subtle gold background, not bold
 */

import DayQuality from './DayQuality';
import type {
  PersonalReadinessState,
  FrictionMarkers,
  SleepQuality,
  FocusQuality,
  DistractionLevel,
  BodyState,
} from '../../hooks/useRoutineState';

interface PersonalReadinessProps {
  personalReadiness: PersonalReadinessState;
  friction: FrictionMarkers;
  onToggleQuality: <K extends keyof PersonalReadinessState>(
    key: K,
    value: PersonalReadinessState[K]
  ) => void;
  onToggleFriction: (key: keyof FrictionMarkers) => void;
}

// Option configurations
const SLEEP_OPTIONS: { value: SleepQuality; label: string }[] = [
  { value: 'short', label: 'Short' },
  { value: 'adequate', label: 'Adequate' },
  { value: 'strong', label: 'Strong' },
];

const FOCUS_OPTIONS: { value: FocusQuality; label: string }[] = [
  { value: 'scattered', label: 'Scattered' },
  { value: 'centered', label: 'Centered' },
];

const DISTRACTION_OPTIONS: { value: DistractionLevel; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];

const BODY_OPTIONS: { value: BodyState; label: string }[] = [
  { value: 'tight', label: 'Tight' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'energized', label: 'Energized' },
];

const FRICTION_OPTIONS: { key: keyof FrictionMarkers; label: string }[] = [
  { key: 'carryover', label: 'Carryover' },
  { key: 'noise', label: 'Noise' },
  { key: 'tension', label: 'Tension' },
  { key: 'timePressure', label: 'Time pressure' },
];

export default function PersonalReadiness({
  personalReadiness,
  friction,
  onToggleQuality,
  onToggleFriction,
}: PersonalReadinessProps) {
  return (
    <div className="personal-readiness">
      <div className="routine-lens-header">Personal Readiness</div>

      <div className="personal-readiness-qualities">
        <DayQuality
          label="Sleep felt:"
          options={SLEEP_OPTIONS}
          value={personalReadiness.sleep}
          onChange={(value) => onToggleQuality('sleep', value)}
        />

        <DayQuality
          label="Focus feels:"
          options={FOCUS_OPTIONS}
          value={personalReadiness.focus}
          onChange={(value) => onToggleQuality('focus', value)}
        />

        <DayQuality
          label="Distractions:"
          options={DISTRACTION_OPTIONS}
          value={personalReadiness.distractions}
          onChange={(value) => onToggleQuality('distractions', value)}
        />

        <DayQuality
          label="Body state:"
          options={BODY_OPTIONS}
          value={personalReadiness.bodyState}
          onChange={(value) => onToggleQuality('bodyState', value)}
        />
      </div>

      <div className="personal-readiness-friction">
        <div className="day-quality-row">
          <span className="day-quality-label">Friction present:</span>
          <div className="day-quality-options">
            {FRICTION_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                className={`day-quality-chip friction ${friction[opt.key] ? 'selected' : ''}`}
                onClick={() => onToggleFriction(opt.key)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
