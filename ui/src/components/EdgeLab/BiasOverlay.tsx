// ui/src/components/EdgeLab/BiasOverlay.tsx
import ReactECharts from 'echarts-for-react';

interface BiasOverlayProps {
  data: {
    dimensions: Record<string, Record<string, {
      outcomes: Record<string, number>;
      sample_size: number;
      insufficient_sample: boolean;
    }>>;
    total_records: number;
  } | null;
}

const DIMENSION_LABELS: Record<string, string> = {
  sleep: 'Sleep',
  focus: 'Focus',
  distractions: 'Distractions',
  body_state: 'Body State',
  friction: 'Friction',
};

const OUTCOME_COLORS: Record<string, string> = {
  structural_win: '#10b981',
  structural_loss: '#ef4444',
  execution_error: '#f59e0b',
  bias_interference: '#8b5cf6',
  regime_mismatch: '#6366f1',
};

export default function BiasOverlay({ data }: BiasOverlayProps) {
  if (!data || data.total_records === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#555', fontSize: 13 }}>
        No bias overlay data yet. Record readiness state and confirm outcomes to see patterns.
      </div>
    );
  }

  const charts = Object.entries(data.dimensions).map(([dim, buckets]) => {
    const entries = Object.entries(buckets).sort((a, b) => b[1].sample_size - a[1].sample_size);
    if (entries.length === 0) return null;

    const categories = entries.map(([k]) => k.replace(/_/g, ' '));
    const outcomeTypes = new Set<string>();
    entries.forEach(([, v]) => Object.keys(v.outcomes).forEach(t => outcomeTypes.add(t)));

    const series = Array.from(outcomeTypes).map(ot => ({
      name: ot.replace(/_/g, ' '),
      type: 'bar' as const,
      stack: 'total',
      barMaxWidth: 24,
      data: entries.map(([, v]) => v.outcomes[ot] || 0),
      itemStyle: { color: OUTCOME_COLORS[ot] || '#666' },
    }));

    const option = {
      title: { text: DIMENSION_LABELS[dim] || dim, textStyle: { color: '#888', fontSize: 12 }, left: 'center', top: 0 },
      tooltip: { trigger: 'axis' as const },
      legend: { show: false },
      grid: { left: 40, right: 10, top: 30, bottom: 30 },
      xAxis: { type: 'category' as const, data: categories, axisLabel: { color: '#888', fontSize: 10 } },
      yAxis: { type: 'value' as const, axisLabel: { color: '#666', fontSize: 10 } },
      series,
    };

    return (
      <div key={dim} style={{ flex: '1 1 280px', minWidth: 250 }}>
        <ReactECharts option={option} style={{ height: 180 }} />
      </div>
    );
  });

  return (
    <div>
      <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>
        Outcome distributions by readiness state ({data.total_records} total records)
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12 }}>
        {Object.entries(OUTCOME_COLORS).map(([key, color]) => (
          <span key={key} style={{ fontSize: 10, color, marginRight: 12 }}>
            {key.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        {charts}
      </div>
    </div>
  );
}
