/**
 * RiskOrientationSection - Width / Capital / Optionality Posture selection
 *
 * "Frame how risk should be treated today"
 */

import type { RiskOrientationData } from '../../hooks/useRoutineState';

interface RiskOrientationSectionProps {
  data: RiskOrientationData;
  onChange: (update: Partial<RiskOrientationData>) => void;
}

type WidthPosture = 'narrow' | 'normal' | 'wide';
type CapitalPosture = 'defensive' | 'neutral' | 'offensive';
type OptionalityPosture = 'patience' | 'speed' | 'observation';

const WIDTH_OPTIONS: { value: WidthPosture; label: string }[] = [
  { value: 'narrow', label: 'Narrow' },
  { value: 'normal', label: 'Normal' },
  { value: 'wide', label: 'Wide' },
];

const CAPITAL_OPTIONS: { value: CapitalPosture; label: string }[] = [
  { value: 'defensive', label: 'Defensive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'offensive', label: 'Offensive' },
];

const OPTIONALITY_OPTIONS: { value: OptionalityPosture; label: string }[] = [
  { value: 'patience', label: 'Patience' },
  { value: 'speed', label: 'Speed' },
  { value: 'observation', label: 'Observe' },
];

export default function RiskOrientationSection({ data, onChange }: RiskOrientationSectionProps) {
  return (
    <div className="routine-risk-orientation">
      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Width Posture</span>
        <div className="routine-toggle-options">
          {WIDTH_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.widthPosture === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ widthPosture: data.widthPosture === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Capital Posture</span>
        <div className="routine-toggle-options">
          {CAPITAL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.capitalPosture === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ capitalPosture: data.capitalPosture === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="routine-toggle-group">
        <span className="routine-toggle-label">Optionality Posture</span>
        <div className="routine-toggle-options">
          {OPTIONALITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`routine-toggle-btn ${data.optionalityPosture === opt.value ? 'selected' : ''}`}
              onClick={() => onChange({ optionalityPosture: data.optionalityPosture === opt.value ? null : opt.value })}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
