/**
 * StateResetSection - Focus / Energy / Emotional Load selection
 *
 * "Shift from life mode → market mode"
 */

import type { StateResetData } from '../../hooks/useRoutineState';

interface StateResetSectionProps {
  data: StateResetData;
  onChange: (update: Partial<StateResetData>) => void;
}

type Level = 'low' | 'medium' | 'high';
type EmotionalState = 'calm' | 'charged' | 'distracted';

const FOCUS_OPTIONS: { value: Level; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Med' },
  { value: 'high', label: 'High' },
];

const ENERGY_OPTIONS: { value: Level; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Med' },
  { value: 'high', label: 'High' },
];

const EMOTIONAL_OPTIONS: { value: EmotionalState; label: string }[] = [
  { value: 'calm', label: 'Calm' },
  { value: 'charged', label: 'Charged' },
  { value: 'distracted', label: 'Distracted' },
];

export default function StateResetSection({ data, onChange }: StateResetSectionProps) {
  return (
    <div className="routine-state-reset">
      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Focus</span>
        <div className="routine-toggle-options">
          {FOCUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.focus === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ focus: data.focus === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Energy</span>
        <div className="routine-toggle-options">
          {ENERGY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.energy === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ energy: data.energy === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Emotional Load</span>
        <div className="routine-toggle-options">
          {EMOTIONAL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.emotionalLoad === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ emotionalLoad: data.emotionalLoad === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <textarea
        className="routine-text-input"
        placeholder="Anything on your mind? (optional)"
        value={data.freeText}
        onChange={(e) => onChange({ freeText: e.target.value })}
        rows={2}
      />
    </div>
  );
}
