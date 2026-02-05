// ui/src/components/PeakUsageChart.tsx
// Admin dashboard chart showing peak usage over time

import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

interface HourlyData {
  hour_start: string;
  user_count: number;
}

interface BusiestHour {
  hour: number;
  avgUsers: number;
}

interface Props {
  days?: number;
}

export default function PeakUsageChart({ days = 7 }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [data, setData] = useState<HourlyData[]>([]);
  const [busiestHours, setBusiestHours] = useState<BusiestHour[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch data
  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const res = await fetch(`/api/admin/activity/hourly?days=${days}`, {
          credentials: "include",
        });
        if (!res.ok) throw new Error("Failed to fetch activity data");
        const json = await res.json();
        setData(json.data || []);
        setBusiestHours(json.busiestHours || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [days]);

  // Render chart
  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current, "dark");
    }

    const chart = chartInstance.current;

    // Prepare data for chart
    const xData = data.map((d) => {
      const date = new Date(d.hour_start);
      return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:00`;
    });
    const yData = data.map((d) => d.user_count);

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: (params: any) => {
          const p = params[0];
          return `${p.name}<br/><strong>${p.value}</strong> user${p.value !== 1 ? "s" : ""} online`;
        },
      },
      grid: {
        top: 20,
        right: 20,
        bottom: 40,
        left: 50,
      },
      xAxis: {
        type: "category",
        data: xData,
        axisLabel: {
          fontSize: 9,
          color: "#71717a",
          rotate: 45,
          interval: Math.floor(data.length / 12),
        },
        axisLine: { lineStyle: { color: "#27272a" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: {
          fontSize: 10,
          color: "#71717a",
        },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "#1f1f23" } },
      },
      series: [
        {
          type: "bar",
          data: yData,
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "#60a5fa" },
              { offset: 1, color: "#3b82f6" },
            ]),
            borderRadius: [2, 2, 0, 0],
          },
          emphasis: {
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "#93c5fd" },
                { offset: 1, color: "#60a5fa" },
              ]),
            },
          },
          barMaxWidth: 20,
        },
      ],
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [data]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  const formatHour = (hour: number) => {
    if (hour === 0) return "12 AM";
    if (hour === 12) return "12 PM";
    return hour < 12 ? `${hour} AM` : `${hour - 12} PM`;
  };

  if (loading) {
    return (
      <div className="peak-usage-chart loading">
        <div className="chart-header">
          <h3>Peak Usage</h3>
        </div>
        <div className="chart-loading">Loading activity data...</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="peak-usage-chart error">
        <div className="chart-header">
          <h3>Peak Usage</h3>
        </div>
        <div className="chart-error">{error}</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="peak-usage-chart empty">
        <div className="chart-header">
          <h3>Peak Usage</h3>
        </div>
        <div className="chart-empty">No activity data yet. Data will appear after users connect.</div>
        <style>{styles}</style>
      </div>
    );
  }

  return (
    <div className="peak-usage-chart">
      <div className="chart-header">
        <h3>Peak Usage (Last {days} Days)</h3>
        {busiestHours.length > 0 && (
          <div className="busiest-hours">
            <span className="busiest-label">Busiest:</span>
            {busiestHours.map((h, i) => (
              <span key={h.hour} className="busiest-hour">
                {formatHour(h.hour)}
                {i < busiestHours.length - 1 && ", "}
              </span>
            ))}
          </div>
        )}
      </div>
      <div ref={chartRef} style={{ width: "100%", height: "200px" }} />
      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .peak-usage-chart {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .chart-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }

  .chart-header h3 {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: #f1f5f9;
  }

  .busiest-hours {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
  }

  .busiest-label {
    color: #71717a;
  }

  .busiest-hour {
    color: #60a5fa;
    font-weight: 500;
  }

  .chart-loading,
  .chart-error,
  .chart-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 200px;
    color: #71717a;
    font-size: 0.875rem;
  }

  .chart-error {
    color: #f87171;
  }
`;
