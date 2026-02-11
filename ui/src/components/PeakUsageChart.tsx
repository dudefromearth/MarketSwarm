// ui/src/components/PeakUsageChart.tsx
// Admin dashboard heatmap showing peak usage patterns by hour and day

import { useEffect, useRef, useState, useMemo } from "react";
import * as echarts from "echarts";
import { useTimezone } from "../contexts/TimezoneContext";

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

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOURS = Array.from({ length: 24 }, (_, i) => {
  if (i === 0) return "12a";
  if (i === 12) return "12p";
  if (i < 12) return `${i}a`;
  return `${i - 12}p`;
});

export default function PeakUsageChart({ days = 7 }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [rawData, setRawData] = useState<HourlyData[]>([]);
  const [busiestHours, setBusiestHours] = useState<BusiestHour[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { timezone } = useTimezone();

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
        setRawData(json.data || []);
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

  // Convert raw hourly data to heatmap format [hour, dayOfWeek, count]
  // Aggregated by hour-of-day and day-of-week in user's timezone
  const heatmapData = useMemo(() => {
    if (rawData.length === 0) return [];

    // Create a 7x24 grid for day-of-week x hour aggregation
    const grid: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));
    const counts: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));

    rawData.forEach((d) => {
      // Parse the UTC timestamp and convert to user's timezone
      const utcDate = new Date(d.hour_start);

      // Convert to user's timezone
      const localDate = new Date(utcDate.toLocaleString("en-US", { timeZone: timezone }));
      const dayOfWeek = localDate.getDay(); // 0 = Sunday
      const hour = localDate.getHours();

      grid[dayOfWeek][hour] += d.user_count;
      counts[dayOfWeek][hour] += 1;
    });

    // Convert to echarts heatmap format: [hour, day, value]
    const result: [number, number, number][] = [];
    for (let day = 0; day < 7; day++) {
      for (let hour = 0; hour < 24; hour++) {
        // Average if we have multiple samples, otherwise use sum
        const value = counts[day][hour] > 0
          ? Math.round(grid[day][hour] / counts[day][hour] * 10) / 10
          : 0;
        result.push([hour, day, value]);
      }
    }

    return result;
  }, [rawData, timezone]);

  // Find peak times in user's timezone
  const peakInfo = useMemo(() => {
    if (heatmapData.length === 0) return null;

    // Find the max value and peak day
    let maxValue = 0;
    let peakDay = 0;

    heatmapData.forEach(([, day, value]) => {
      if (value > maxValue) {
        maxValue = value;
        peakDay = day;
      }
    });

    // Find busiest hour overall (across all days)
    const hourTotals = Array(24).fill(0);
    heatmapData.forEach(([hour, , value]) => {
      hourTotals[hour] += value;
    });
    const busiestHourIdx = hourTotals.indexOf(Math.max(...hourTotals));

    return {
      maxValue,
      peakDay: DAYS[peakDay],
      peakHour: busiestHourIdx,
      totalUsers: Math.round(heatmapData.reduce((sum, [, , v]) => sum + v, 0)),
    };
  }, [heatmapData]);

  // Render chart
  useEffect(() => {
    if (!chartRef.current || heatmapData.length === 0) return;

    // Read CSS variable values for canvas-rendered elements
    const cs = getComputedStyle(document.documentElement);
    const cssVar = (name: string) => cs.getPropertyValue(name).trim();
    const bgBase = cssVar("--bg-base");
    const bgRaised = cssVar("--bg-raised");
    const textSecondary = cssVar("--text-secondary");
    const textBright = cssVar("--text-bright");
    const borderDefault = cssVar("--border-default");

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const chart = chartInstance.current;
    const maxValue = Math.max(...heatmapData.map((d) => d[2]), 1);

    const option: echarts.EChartsOption = {
      tooltip: {
        position: "top",
        formatter: (params: any) => {
          const hour = params.data[0];
          const day = DAYS[params.data[1]];
          const count = params.data[2];
          const hourLabel = hour === 0 ? "12:00 AM" : hour < 12 ? `${hour}:00 AM` : hour === 12 ? "12:00 PM" : `${hour - 12}:00 PM`;
          return `<strong>${day}</strong> at ${hourLabel}<br/><span style="color: #60a5fa">~${count.toFixed(1)}</span> avg users`;
        },
        backgroundColor: bgRaised,
        borderColor: borderDefault,
        textStyle: { color: textBright, fontSize: 12 },
      },
      grid: {
        top: 10,
        right: 15,
        bottom: 35,
        left: 45,
      },
      xAxis: {
        type: "category",
        data: HOURS,
        splitArea: { show: true, areaStyle: { color: ["transparent", "rgba(255,255,255,0.01)"] } },
        axisLabel: {
          fontSize: 9,
          color: textSecondary,
          interval: 2,
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: "category",
        data: DAYS,
        splitArea: { show: true, areaStyle: { color: ["transparent", "rgba(255,255,255,0.01)"] } },
        axisLabel: {
          fontSize: 10,
          color: textSecondary,
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      visualMap: {
        min: 0,
        max: maxValue,
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        show: false,
        inRange: {
          color: [bgBase, "#1e3a5f", "#1d4ed8", "#3b82f6", "#60a5fa", "#93c5fd"],
        },
      },
      series: [
        {
          name: "Peak Usage",
          type: "heatmap",
          data: heatmapData,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(59, 130, 246, 0.5)",
            },
          },
          itemStyle: {
            borderColor: bgBase,
            borderWidth: 1,
            borderRadius: 3,
          },
        },
      ],
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [heatmapData]);

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

  if (rawData.length === 0) {
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

  // Get timezone abbreviation for display
  const tzAbbrev = new Date().toLocaleTimeString("en-US", {
    timeZone: timezone,
    timeZoneName: "short"
  }).split(" ").pop();

  return (
    <div className="peak-usage-chart">
      <div className="chart-header">
        <div className="chart-title">
          <h3>Peak Usage Pattern</h3>
          <span className="timezone-badge">{tzAbbrev}</span>
        </div>
        <div className="chart-stats">
          {peakInfo && (
            <>
              <span className="stat">
                <span className="stat-label">Busiest:</span>
                <span className="stat-value">{formatHour(peakInfo.peakHour)}</span>
              </span>
              {busiestHours.length > 0 && (
                <span className="stat">
                  <span className="stat-label">Peak Day:</span>
                  <span className="stat-value">{peakInfo.peakDay}</span>
                </span>
              )}
            </>
          )}
        </div>
      </div>
      <div ref={chartRef} style={{ width: "100%", height: "220px" }} />
      <div className="chart-footer">
        <span className="legend-label">Less active</span>
        <div className="legend-gradient" />
        <span className="legend-label">More active</span>
      </div>
      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .peak-usage-chart {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .chart-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .chart-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .chart-header h3 {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .timezone-badge {
    padding: 0.125rem 0.375rem;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.25rem;
    font-size: 0.625rem;
    color: #60a5fa;
    font-weight: 500;
    text-transform: uppercase;
  }

  .chart-stats {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .stat {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
  }

  .stat-label {
    color: var(--text-secondary);
  }

  .stat-value {
    color: #60a5fa;
    font-weight: 500;
  }

  .chart-footer {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border-subtle);
  }

  .legend-label {
    font-size: 0.625rem;
    color: var(--text-muted);
    text-transform: uppercase;
  }

  .legend-gradient {
    width: 80px;
    height: 8px;
    border-radius: 4px;
    background: linear-gradient(to right, #18181b, #1e3a5f, #1d4ed8, #3b82f6, #60a5fa, #93c5fd);
  }

  .chart-loading,
  .chart-error,
  .chart-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 220px;
    color: var(--text-secondary);
    font-size: 0.875rem;
  }

  .chart-error {
    color: #f87171;
  }
`;
