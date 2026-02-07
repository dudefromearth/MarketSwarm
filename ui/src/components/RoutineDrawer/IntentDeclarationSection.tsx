/**
 * IntentDeclarationSection - Intent type selection + optional note
 *
 * "Create constraint layer before analysis"
 */

import type { IntentDeclarationData, IntentType } from '../../hooks/useRoutineState';

interface IntentDeclarationSectionProps {
  data: IntentDeclarationData;
  onChange: (update: Partial<IntentDeclarationData>) => void;
}

const INTENT_OPTIONS: { value: IntentType; label: string; description: string }[] = [
  {
    value: 'observe_only',
    label: 'Observe Only',
    description: 'Watch and learn, no trades today',
  },
  {
    value: 'manage_existing',
    label: 'Manage Existing',
    description: 'Focus on open positions only',
  },
  {
    value: 'one_trade_max',
    label: 'One Trade Max',
    description: 'Single new entry if conditions align',
  },
  {
    value: 'full_participation',
    label: 'Full Participation',
    description: 'Open to multiple opportunities',
  },
  {
    value: 'test_hypothesis',
    label: 'Test Hypothesis',
    description: 'Small size to validate an idea',
  },
];

export default function IntentDeclarationSection({ data, onChange }: IntentDeclarationSectionProps) {
  return (
    <div className="routine-intent-declaration">
      <div className="routine-radio-group">
        {INTENT_OPTIONS.map((opt) => (
          <div
            key={opt.value}
            className={`routine-radio-option ${data.intent === opt.value ? 'selected' : ''}`}
            onClick={() => onChange({ intent: data.intent === opt.value ? null : opt.value })}
          >
            <div className="routine-radio-dot">
              <div className="routine-radio-dot-inner" />
            </div>
            <div>
              <div className="routine-radio-label">{opt.label}</div>
              <div className="routine-radio-description" style={{ fontSize: '9px', color: 'var(--routine-text-dim)', marginTop: '2px' }}>
                {opt.description}
              </div>
            </div>
          </div>
        ))}
      </div>

      <textarea
        className="routine-text-input"
        placeholder="Additional notes on today's intent... (optional)"
        value={data.note}
        onChange={(e) => onChange({ note: e.target.value })}
        rows={2}
      />
    </div>
  );
}
