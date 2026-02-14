// ui/src/components/EdgeLab/RegimeChart.tsx
import ReactECharts from 'echarts-for-react';

interface RegimeChartProps {
  data: {
    dimensions: Record<string, Record<string, {
      structural_validity_rate: number | null;
      sample_size: number;
      structural_wins: number;
      insufficient_sample: boolean;
    }>>;
    total_records: number;
  } | null;
}

const DIMENSION_LABELS: Record<string, string> = {
  regime: 'Regime',
  gex_posture: 'GEX Posture',
  vol_state: 'Vol State',
  time_structure: 'Time Structure',
  heatmap_color: 'Heatmap',
};

export default function RegimeChart({ data }: RegimeChartProps) {
  if (!data || data.total_records === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: '#555', fontSize: 13 }}>
        No regime correlation data yet. Confirm at least 10 outcomes to see patterns.
      </div>
    );
  }

  // Build one chart per dimension
  const charts = Object.entries(data.dimensions).map(([dim, buckets]) => {
    const entries = Object.entries(buckets).sort((a, b) => b[1].sample_size - a[1].sample_size);
    const categories = entries.map(([k]) => k.replace(/_/g, ' '));
    const rates = entries.map(([, v]) => v.structural_validity_rate !== null ? +(v.structural_validity_rate * 100).toFixed(1) : 0);
    const sizes = entries.map(([, v]) => v.sample_size);
    const insufficients = entries.map(([, v]) => v.insufficient_sample);

    const option = {
      title: { text: DIMENSION_LABELS[dim] || dim, textStyle: { color: '#888', fontSize: 12 }, left: 'center', top: 0 },
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: any[]) => {
          const idx = params[0]?.dataIndex;
          if (idx === undefined) return '';
          const rate = rates[idx];
          const size = sizes[idx];
          const insuf = insufficients[idx];
          return `${categories[idx]}<br/>Validity: ${insuf ? 'N/A' : rate + '%'}<br/>Samples: ${size}${insuf ? ' (insufficient)' : ''}`;
        },
      },
      grid: { left: 40, right: 10, top: 30, bottom: 30 },
      xAxis: { type: 'category' as const, data: categories, axisLabel: { color: '#888', fontSize: 10 } },
      yAxis: { type: 'value' as const, max: 100, axisLabel: { color: '#666', fontSize: 10 } },
      series: [{
        type: 'bar',
        data: rates.map((r, i) => ({
          value: r,
          itemStyle: { color: insufficients[i] ? '#333' : '#2563eb', opacity: insufficients[i] ? 0.4 : 1 },
        })),
        barMaxWidth: 30,
      }],
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
        Structural validity rate by regime dimension ({data.total_records} total records)
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        {charts}
      </div>
    </div>
  );
}
