// ui/src/components/EdgeLab/SetupForm.tsx
import { useState } from 'react';

interface SetupFormProps {
  onSubmit: (data: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}

const REGIME_OPTIONS = ['trending', 'range_bound', 'volatile', 'transitional', 'compressed'];
const GEX_OPTIONS = ['positive', 'negative', 'neutral', 'flip_zone'];
const VOL_OPTIONS = ['low', 'elevated', 'high', 'compressed', 'expanding'];
const TIME_OPTIONS = ['morning', 'midday', 'power_hour', 'close', 'overnight'];
const HEATMAP_OPTIONS = ['green', 'red', 'yellow', 'mixed'];
const STRUCTURE_OPTIONS = ['long_fly', 'bwb', 'vertical', 'iron_condor', 'calendar', 'diagonal', 'naked', 'straddle', 'strangle'];
const WIDTH_OPTIONS = ['narrow', 'standard', 'wide'];
const BIAS_OPTIONS = ['bullish', 'bearish', 'neutral'];

export default function SetupForm({ onSubmit, onCancel }: SetupFormProps) {
  const [form, setForm] = useState({
    setupDate: new Date().toISOString().split('T')[0],
    regime: '',
    gexPosture: '',
    volState: '',
    timeStructure: '',
    heatmapColor: '',
    positionStructure: '',
    widthBucket: '',
    directionalBias: '',
    entryLogic: '',
    exitLogic: '',
    entryDefined: false,
    exitDefined: false,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await onSubmit(form);
    } finally {
      setSubmitting(false);
    }
  };

  const isValid = form.regime && form.gexPosture && form.volState &&
    form.timeStructure && form.heatmapColor && form.positionStructure &&
    form.widthBucket && form.directionalBias;

  const selectStyle: React.CSSProperties = {
    padding: '6px 10px', borderRadius: 4, border: '1px solid #444',
    background: '#1a1a2e', color: '#e0e0e0', fontSize: 13, width: '100%',
  };
  const labelStyle: React.CSSProperties = {
    fontSize: 11, color: '#888', marginBottom: 4, display: 'block',
  };
  const fieldStyle: React.CSSProperties = { marginBottom: 12 };

  return (
    <div style={{ padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333' }}>
      <h3 style={{ margin: '0 0 16px', color: '#e0e0e0', fontSize: 16 }}>New Structural Setup</h3>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>Date</label>
          <input type="date" value={form.setupDate}
            onChange={e => setForm(f => ({ ...f, setupDate: e.target.value }))}
            style={selectStyle} />
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Regime</label>
          <select value={form.regime} onChange={e => setForm(f => ({ ...f, regime: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {REGIME_OPTIONS.map(o => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>GEX Posture</label>
          <select value={form.gexPosture} onChange={e => setForm(f => ({ ...f, gexPosture: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {GEX_OPTIONS.map(o => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Vol State</label>
          <select value={form.volState} onChange={e => setForm(f => ({ ...f, volState: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {VOL_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Time Structure</label>
          <select value={form.timeStructure} onChange={e => setForm(f => ({ ...f, timeStructure: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {TIME_OPTIONS.map(o => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Heatmap Color</label>
          <select value={form.heatmapColor} onChange={e => setForm(f => ({ ...f, heatmapColor: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {HEATMAP_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Position Structure</label>
          <select value={form.positionStructure} onChange={e => setForm(f => ({ ...f, positionStructure: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {STRUCTURE_OPTIONS.map(o => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Width Bucket</label>
          <select value={form.widthBucket} onChange={e => setForm(f => ({ ...f, widthBucket: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {WIDTH_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Directional Bias</label>
          <select value={form.directionalBias} onChange={e => setForm(f => ({ ...f, directionalBias: e.target.value }))} style={selectStyle}>
            <option value="">Select...</option>
            {BIAS_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 8 }}>
        <div style={fieldStyle}>
          <label style={labelStyle}>Entry Logic</label>
          <textarea value={form.entryLogic}
            onChange={e => setForm(f => ({ ...f, entryLogic: e.target.value }))}
            style={{ ...selectStyle, minHeight: 60, resize: 'vertical' }}
            placeholder="What defines entry?" />
          <label style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#aaa' }}>
            <input type="checkbox" checked={form.entryDefined}
              onChange={e => setForm(f => ({ ...f, entryDefined: e.target.checked }))} />
            Entry criteria defined
          </label>
        </div>
        <div style={fieldStyle}>
          <label style={labelStyle}>Exit Logic</label>
          <textarea value={form.exitLogic}
            onChange={e => setForm(f => ({ ...f, exitLogic: e.target.value }))}
            style={{ ...selectStyle, minHeight: 60, resize: 'vertical' }}
            placeholder="What defines exit?" />
          <label style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#aaa' }}>
            <input type="checkbox" checked={form.exitDefined}
              onChange={e => setForm(f => ({ ...f, exitDefined: e.target.checked }))} />
            Exit criteria defined
          </label>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
        <button onClick={onCancel}
          style={{ padding: '8px 16px', borderRadius: 4, border: '1px solid #555', background: 'transparent', color: '#aaa', cursor: 'pointer' }}>
          Cancel
        </button>
        <button onClick={handleSubmit} disabled={!isValid || submitting}
          style={{ padding: '8px 16px', borderRadius: 4, border: 'none', background: isValid ? '#2563eb' : '#333', color: '#fff', cursor: isValid ? 'pointer' : 'default', opacity: submitting ? 0.6 : 1 }}>
          {submitting ? 'Creating...' : 'Create Setup'}
        </button>
      </div>
    </div>
  );
}
