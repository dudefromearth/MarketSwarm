// ui/src/components/ActivityHeatmap.tsx
// User activity heatmap showing when a user is typically online

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

interface Props {
  data: [number, number, number][]; // [hour, dayOfWeek, count][]
  totalActiveTime?: {
    hours: number;
    minutes: number;
    formatted: string;
  };
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOURS = Array.from({ length: 24 }, (_, i) => {
  if (i === 0) return "12a";
  if (i === 12) return "12p";
  if (i < 12) return `${i}a`;
  return `${i - 12}p`;
});

export default function ActivityHeatmap({ data, totalActiveTime }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;

    // Initialize chart
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current, "dark");
    }

    const chart = chartInstance.current;

    // Find max value for color scaling
    const maxValue = Math.max(...data.map((d) => d[2]), 1);

    const option: echarts.EChartsOption = {
      tooltip: {
        position: "top",
        formatter: (params: any) => {
          const hour = params.data[0];
          const day = DAYS[params.data[1]];
          const count = params.data[2];
          const hourLabel = hour === 0 ? "12:00 AM" : hour < 12 ? `${hour}:00 AM` : hour === 12 ? "12:00 PM" : `${hour - 12}:00 PM`;
          return `${day} ${hourLabel}<br/><strong>${count}</strong> session${count !== 1 ? "s" : ""}`;
        },
      },
      grid: {
        top: 10,
        right: 10,
        bottom: 30,
        left: 40,
      },
      xAxis: {
        type: "category",
        data: HOURS,
        splitArea: { show: true },
        axisLabel: {
          fontSize: 9,
          color: "#71717a",
          interval: 2,
        },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: "category",
        data: DAYS,
        splitArea: { show: true },
        axisLabel: {
          fontSize: 10,
          color: "#71717a",
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
          color: ["#18181b", "#1e3a5f", "#2563eb", "#60a5fa"],
        },
      },
      series: [
        {
          name: "Activity",
          type: "heatmap",
          data: data,
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.5)",
            },
          },
          itemStyle: {
            borderColor: "#09090b",
            borderWidth: 1,
            borderRadius: 2,
          },
        },
      ],
    };

    chart.setOption(option);

    // Handle resize
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [data]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, []);

  return (
    <div className="activity-heatmap">
      <div className="heatmap-header">
        <h4>Activity Pattern</h4>
        {totalActiveTime && (
          <span className="total-time">
            Total: {totalActiveTime.formatted}
          </span>
        )}
      </div>
      <div ref={chartRef} style={{ width: "100%", height: "180px" }} />
      <style>{`
        .activity-heatmap {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 0.5rem;
          padding: 0.75rem;
        }
        .heatmap-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 0.5rem;
        }
        .heatmap-header h4 {
          margin: 0;
          font-size: 0.75rem;
          color: #71717a;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .total-time {
          font-size: 0.75rem;
          color: #60a5fa;
          font-weight: 500;
        }
      `}</style>
    </div>
  );
}
