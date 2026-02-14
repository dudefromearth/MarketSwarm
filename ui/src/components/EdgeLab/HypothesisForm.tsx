// ui/src/components/EdgeLab/HypothesisForm.tsx
import { useState } from 'react';
import type { EdgeLabHypothesis } from '../../hooks/useEdgeLab';

interface HypothesisFormProps {
  setupId: string;
  existing?: EdgeLabHypothesis | null;
  onSubmit: (data: { setupId: string; thesis: string; convexitySource: string; failureCondition: string; maxRiskDefined: boolean }) => Promise<void>;
  onLock: (id: string) => Promise<void>;
}

export default function HypothesisForm({ setupId, existing, onSubmit, onLock }: HypothesisFormProps) {
  const [form, setForm] = useState({
    thesis: existing?.thesis || '',
    convexitySource: existing?.convexitySource || '',
    failureCondition: existing?.failureCondition || '',
    maxRiskDefined: existing?.maxRiskDefined || false,
  });
  const [submitting, setSubmitting] = useState(false);

  const isLocked = existing?.isLocked;
  const isReadOnly = !!isLocked;

  const inputStyle: React.CSSProperties = {
    padding: '6px 10px', borderRadius: 4, border: '1px solid #444',
    background: isReadOnly ? '#111' : '#1a1a2e', color: isReadOnly ? '#666' : '#e0e0e0',
    fontSize: 13, width: '100%', minHeight: 60, resize: 'vertical',
  };
  const labelStyle: React.CSSProperties = { fontSize: 11, color: '#888', marginBottom: 4, display: 'block' };

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      await onSubmit({ setupId, ...form });
    } finally {
      setSubmitting(false);
    }
  };

  const handleLock = async () => {
    if (!existing || isLocked) return;
    if (!window.confirm('Lock this hypothesis? It cannot be modified after locking.')) return;
    setSubmitting(true);
    try {
      await onLock(existing.id);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: 12, background: '#0d0d1a', borderRadius: 6, border: '1px solid #333' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h4 style={{ margin: 0, color: '#e0e0e0', fontSize: 14 }}>Hypothesis</h4>
        {isLocked && (
          <span style={{ fontSize: 11, color: '#f59e0b', background: '#332800', padding: '2px 8px', borderRadius: 4 }}>
            Locked
          </span>
        )}
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Thesis</label>
        <textarea value={form.thesis} readOnly={isReadOnly}
          onChange={e => setForm(f => ({ ...f, thesis: e.target.value }))}
          style={inputStyle} placeholder="What is the structural thesis?" />
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Convexity Source</label>
        <textarea value={form.convexitySource} readOnly={isReadOnly}
          onChange={e => setForm(f => ({ ...f, convexitySource: e.target.value }))}
          style={inputStyle} placeholder="Where does convexity come from?" />
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Failure Condition</label>
        <textarea value={form.failureCondition} readOnly={isReadOnly}
          onChange={e => setForm(f => ({ ...f, failureCondition: e.target.value }))}
          style={inputStyle} placeholder="What would invalidate this thesis?" />
      </div>

      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#aaa', marginBottom: 12 }}>
        <input type="checkbox" checked={form.maxRiskDefined} disabled={isReadOnly}
          onChange={e => setForm(f => ({ ...f, maxRiskDefined: e.target.checked }))} />
        Max risk defined before entry
      </label>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {!existing && (
          <button onClick={handleCreate} disabled={!form.thesis || !form.convexitySource || !form.failureCondition || submitting}
            style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 13 }}>
            {submitting ? 'Saving...' : 'Save Hypothesis'}
          </button>
        )}
        {existing && !isLocked && (
          <button onClick={handleLock} disabled={submitting}
            style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #f59e0b', background: 'transparent', color: '#f59e0b', cursor: 'pointer', fontSize: 13 }}>
            Lock Hypothesis
          </button>
        )}
      </div>
    </div>
  );
}
