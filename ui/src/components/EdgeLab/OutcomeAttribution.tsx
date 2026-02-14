// ui/src/components/EdgeLab/OutcomeAttribution.tsx
import { useState, useEffect } from 'react';
import type { EdgeLabOutcome, OutcomeSuggestion } from '../../hooks/useEdgeLab';

const OUTCOME_TYPES = [
  { value: 'structural_win', label: 'Structural Win', desc: 'Thesis resolved as expected' },
  { value: 'structural_loss', label: 'Structural Loss', desc: 'Thesis failed structurally' },
  { value: 'execution_error', label: 'Execution Error', desc: 'Process breakdown in entry/exit' },
  { value: 'bias_interference', label: 'Bias Interference', desc: 'Cognitive state compromised decision' },
  { value: 'regime_mismatch', label: 'Regime Mismatch', desc: 'Structure misaligned with regime' },
];

interface OutcomeAttributionProps {
  setupId: string;
  existing?: EdgeLabOutcome | null;
  suggestion?: OutcomeSuggestion | null;
  onSuggest: (setupId: string) => Promise<void>;
  onSubmit: (data: Record<string, unknown>) => Promise<void>;
  onConfirm: (id: string) => Promise<void>;
}

export default function OutcomeAttribution({
  setupId, existing, suggestion, onSuggest, onSubmit, onConfirm,
}: OutcomeAttributionProps) {
  const [form, setForm] = useState({
    outcomeType: existing?.outcomeType || '',
    hypothesisValid: existing?.hypothesisValid ?? null as number | null,
    structureResolved: existing?.structureResolved ?? null as number | null,
    exitPerPlan: existing?.exitPerPlan ?? null as number | null,
    notes: existing?.notes || '',
    pnlResult: existing?.pnlResult ?? '' as number | string,
  });
  const [submitting, setSubmitting] = useState(false);
  const [hasSuggested, setHasSuggested] = useState(false);

  const isConfirmed = existing?.isConfirmed;

  useEffect(() => {
    if (suggestion && !hasSuggested && !existing) {
      setHasSuggested(true);
      if (suggestion.suggestion) {
        setForm(f => ({ ...f, outcomeType: suggestion.suggestion! }));
      }
    }
  }, [suggestion, hasSuggested, existing]);

  const handleSuggest = async () => {
    await onSuggest(setupId);
  };

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      await onSubmit({
        setupId,
        outcomeType: form.outcomeType,
        hypothesisValid: form.hypothesisValid,
        structureResolved: form.structureResolved,
        exitPerPlan: form.exitPerPlan,
        notes: form.notes || null,
        // pnl_result is recorded for reference ONLY — never used in Edge Score
        pnlResult: form.pnlResult !== '' ? Number(form.pnlResult) : null,
        systemSuggestion: suggestion?.suggestion || null,
        suggestionConfidence: suggestion?.confidence || null,
        suggestionReasoning: suggestion?.reasoning || null,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirm = async () => {
    if (!existing || isConfirmed) return;
    if (!window.confirm('Confirm this outcome? It cannot be changed after confirmation.')) return;
    setSubmitting(true);
    try {
      await onConfirm(existing.id);
    } finally {
      setSubmitting(false);
    }
  };

  const labelStyle: React.CSSProperties = { fontSize: 11, color: '#888', marginBottom: 4, display: 'block' };
  const radioGroupStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6 };

  return (
    <div style={{ padding: 12, background: '#0d0d1a', borderRadius: 6, border: '1px solid #333' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h4 style={{ margin: 0, color: '#e0e0e0', fontSize: 14 }}>Outcome Attribution</h4>
        {isConfirmed && (
          <span style={{ fontSize: 11, color: '#10b981', background: '#002211', padding: '2px 8px', borderRadius: 4 }}>
            Confirmed
          </span>
        )}
      </div>

      {/* System suggestion */}
      {suggestion && suggestion.suggestion && (
        <div style={{ padding: 10, background: '#111827', borderRadius: 6, border: '1px solid #374151', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>System Suggestion</div>
          <div style={{ fontSize: 13, color: '#e5e7eb' }}>
            <strong>{suggestion.suggestion.replace(/_/g, ' ')}</strong>
            <span style={{ marginLeft: 8, fontSize: 11, color: '#6b7280' }}>
              ({Math.round((suggestion.confidence || 0) * 100)}% confidence)
            </span>
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>{suggestion.reasoning}</div>
        </div>
      )}

      {!existing && !suggestion && (
        <button onClick={handleSuggest}
          style={{ padding: '6px 12px', borderRadius: 4, border: '1px solid #374151', background: 'transparent', color: '#9ca3af', cursor: 'pointer', fontSize: 12, marginBottom: 12 }}>
          Get System Suggestion
        </button>
      )}

      {/* Outcome type selection */}
      <div style={{ marginBottom: 12 }}>
        <label style={labelStyle}>Outcome Type</label>
        <div style={radioGroupStyle}>
          {OUTCOME_TYPES.map(ot => (
            <label key={ot.value} style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
              borderRadius: 4, cursor: isConfirmed ? 'default' : 'pointer',
              background: form.outcomeType === ot.value ? '#1e293b' : 'transparent',
              border: form.outcomeType === ot.value ? '1px solid #2563eb' : '1px solid transparent',
            }}>
              <input type="radio" name="outcomeType" value={ot.value}
                checked={form.outcomeType === ot.value}
                disabled={!!isConfirmed}
                onChange={e => setForm(f => ({ ...f, outcomeType: e.target.value }))} />
              <div>
                <div style={{ fontSize: 13, color: '#e0e0e0' }}>{ot.label}</div>
                <div style={{ fontSize: 11, color: '#888' }}>{ot.desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Yes/No toggles */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
        {[
          { key: 'hypothesisValid', label: 'Hypothesis Valid?' },
          { key: 'structureResolved', label: 'Structure Resolved?' },
          { key: 'exitPerPlan', label: 'Exit Per Plan?' },
        ].map(({ key, label }) => (
          <div key={key}>
            <label style={labelStyle}>{label}</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {[{ v: 1, l: 'Yes' }, { v: 0, l: 'No' }].map(opt => (
                <button key={opt.v}
                  disabled={!!isConfirmed}
                  onClick={() => setForm(f => ({ ...f, [key]: opt.v }))}
                  style={{
                    padding: '4px 12px', borderRadius: 4, fontSize: 12, cursor: isConfirmed ? 'default' : 'pointer',
                    border: (form as any)[key] === opt.v ? '1px solid #2563eb' : '1px solid #444',
                    background: (form as any)[key] === opt.v ? '#1e293b' : 'transparent',
                    color: (form as any)[key] === opt.v ? '#60a5fa' : '#888',
                  }}>
                  {opt.l}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Notes + PnL */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 12 }}>
        <div>
          <label style={labelStyle}>Notes</label>
          <textarea value={form.notes} readOnly={!!isConfirmed}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #444', background: '#1a1a2e', color: '#e0e0e0', fontSize: 13, width: '100%', minHeight: 50, resize: 'vertical' }} />
        </div>
        <div>
          <label style={labelStyle}>P&L Result (reference only)</label>
          <input type="number" step="0.01" value={form.pnlResult}
            readOnly={!!isConfirmed}
            onChange={e => setForm(f => ({ ...f, pnlResult: e.target.value }))}
            style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid #444', background: '#1a1a2e', color: '#e0e0e0', fontSize: 13, width: '100%' }}
            placeholder="$0.00" />
          <div style={{ fontSize: 10, color: '#555', marginTop: 2 }}>Not used in Edge Score</div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {!existing && (
          <button onClick={handleCreate} disabled={!form.outcomeType || submitting}
            style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: form.outcomeType ? '#2563eb' : '#333', color: '#fff', cursor: form.outcomeType ? 'pointer' : 'default', fontSize: 13 }}>
            {submitting ? 'Saving...' : 'Save Outcome'}
          </button>
        )}
        {existing && !isConfirmed && (
          <button onClick={handleConfirm} disabled={submitting}
            style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: '#10b981', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
            Confirm Outcome
          </button>
        )}
      </div>
    </div>
  );
}
