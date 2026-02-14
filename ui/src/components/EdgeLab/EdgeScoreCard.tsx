// ui/src/components/EdgeLab/EdgeScoreCard.tsx
import type { EdgeScoreData } from '../../hooks/useEdgeLab';

interface EdgeScoreCardProps {
  score: EdgeScoreData | null;
  status: string;
  history: EdgeScoreData[];
}

function GaugeBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#888', marginBottom: 2 }}>
        <span>{label}</span>
        <span>{(value * 100).toFixed(1)}%</span>
      </div>
      <div style={{ height: 6, background: '#1e293b', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.3s' }} />
      </div>
    </div>
  );
}

function SparkLine({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const w = 120;
  const h = 30;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4);
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <polyline points={points} fill="none" stroke="#2563eb" strokeWidth="1.5" />
    </svg>
  );
}

export default function EdgeScoreCard({ score, status, history }: EdgeScoreCardProps) {
  if (status === 'insufficient_sample' || !score) {
    return (
      <div style={{ padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333', textAlign: 'center' }}>
        <div style={{ fontSize: 14, color: '#888', marginBottom: 8 }}>Edge Score</div>
        <div style={{ fontSize: 12, color: '#555' }}>
          {status === 'insufficient_sample'
            ? 'Minimum 10 confirmed outcomes required'
            : 'No score computed yet'}
        </div>
      </div>
    );
  }

  const scoreColor = score.finalScore >= 0.7 ? '#10b981' :
    score.finalScore >= 0.5 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ padding: 16, background: '#0d0d1a', borderRadius: 8, border: '1px solid #333' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>Edge Score</div>
          <div style={{ fontSize: 32, fontWeight: 'bold', color: scoreColor }}>
            {(score.finalScore * 100).toFixed(1)}
          </div>
          <div style={{ fontSize: 11, color: '#555' }}>
            {score.sampleSize} samples | {score.windowStart} to {score.windowEnd}
          </div>
        </div>
        {history.length > 1 && (
          <div>
            <div style={{ fontSize: 10, color: '#666', marginBottom: 2 }}>Trend</div>
            <SparkLine data={history.map(h => h.finalScore)} />
          </div>
        )}
      </div>

      <GaugeBar label="Structural Integrity (35%)" value={score.structuralIntegrity} color="#2563eb" />
      <GaugeBar label="Execution Discipline (30%)" value={score.executionDiscipline} color="#10b981" />
      <GaugeBar label="Bias Interference (15%)" value={score.biasInterferenceRate} color="#ef4444" />
      <GaugeBar label="Regime Alignment (20%)" value={score.regimeAlignment} color="#8b5cf6" />
    </div>
  );
}
