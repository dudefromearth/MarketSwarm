// src/components/EquityChartWidget.tsx
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  AreaSeries,
} from 'lightweight-charts';
import type { IChartApi, UTCTimestamp } from 'lightweight-charts';

const JOURNAL_API = 'http://localhost:3002';

interface EquityPoint {
  time: string;
  value: number;
  trade_id?: string;
}

interface AnalyticsSummary {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  winners: number;
  losers: number;
  breakeven: number;
  total_pnl: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  largest_win: number;
  largest_loss: number;
  avg_trade: number;
}

interface EquityChartWidgetProps {
  refreshTrigger?: number;
}

type TimeRange = '1W' | '1M' | '3M' | 'YTD' | 'ALL';

export default function EquityChartWidget({ refreshTrigger = 0 }: EquityChartWidgetProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null);

  const [equityData, setEquityData] = useState<EquityPoint[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<TimeRange>('1M');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch analytics and equity curve
      const [analyticsRes, equityRes] = await Promise.all([
        fetch(`${JOURNAL_API}/api/analytics`),
        fetch(`${JOURNAL_API}/api/analytics/equity`)
      ]);

      const analyticsData = await analyticsRes.json();
      const equityDataRes = await equityRes.json();

      if (analyticsData.success) {
        setAnalytics(analyticsData.data.summary);
      }

      if (equityDataRes.success) {
        setEquityData(equityDataRes.data.equity || []);
      }
    } catch (err) {
      console.error('EquityChartWidget fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    try {
      const chart = createChart(containerRef.current, {
        height: 200,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: 'rgba(148,163,184,1)',
        },
        grid: {
          vertLines: { color: 'rgba(51,65,85,0.3)' },
          horzLines: { color: 'rgba(51,65,85,0.3)' },
        },
        rightPriceScale: {
          borderColor: 'rgba(30,41,59,1)',
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          borderColor: 'rgba(30,41,59,1)',
          timeVisible: true,
          secondsVisible: false,
        },
        crosshair: { mode: 1 },
      });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (typeof (chart as any).addSeries === 'function') {
        const series = (chart as any).addSeries(AreaSeries, {
          lineColor: 'rgba(74,222,128,1)',
          topColor: 'rgba(74,222,128,0.4)',
          bottomColor: 'rgba(74,222,128,0.05)',
          lineWidth: 2,
          priceLineVisible: true,
          lastValueVisible: true,
        });
        seriesRef.current = series;
      }

      chartRef.current = chart;

      const handleResize = () => {
        if (!containerRef.current || !chartRef.current) return;
        const { width } = containerRef.current.getBoundingClientRect();
        chartRef.current.applyOptions({ width });
      };

      handleResize();
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        if (chartRef.current) chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = null;
      };
    } catch (err) {
      console.error('EquityChartWidget chart creation error:', err);
    }
  }, []);

  // Update chart data when equity data or time range changes
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current || equityData.length === 0) return;
    try {

    // Filter by time range
    const now = new Date();
    let fromDate: Date;

    switch (timeRange) {
      case '1W':
        fromDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        break;
      case '1M':
        fromDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        break;
      case '3M':
        fromDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
        break;
      case 'YTD':
        fromDate = new Date(now.getFullYear(), 0, 1);
        break;
      case 'ALL':
      default:
        fromDate = new Date(0);
        break;
    }

    const filteredData = equityData.filter(p => new Date(p.time) >= fromDate);

    if (filteredData.length === 0) {
      seriesRef.current.setData([]);
      return;
    }

    // Format data for lightweight-charts
    const chartData = filteredData.map(p => ({
      time: Math.floor(new Date(p.time).getTime() / 1000) as UTCTimestamp,
      value: p.value / 100, // Convert cents to dollars
    }));

    // Determine if overall profitable or not for color
    const lastValue = chartData[chartData.length - 1]?.value || 0;
    const isProfit = lastValue >= 0;

    seriesRef.current.applyOptions({
      lineColor: isProfit ? 'rgba(74,222,128,1)' : 'rgba(248,113,113,1)',
      topColor: isProfit ? 'rgba(74,222,128,0.4)' : 'rgba(248,113,113,0.4)',
      bottomColor: isProfit ? 'rgba(74,222,128,0.05)' : 'rgba(248,113,113,0.05)',
    });

    seriesRef.current.setData(chartData);
    chartRef.current.timeScale().fitContent();
    } catch (err) {
      console.error('EquityChartWidget data update error:', err);
    }
  }, [equityData, timeRange]);

  const formatCurrency = (value: number) => {
    const dollars = value / 100; // Convert cents to dollars
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

  const formatPercent = (value: number) => {
    return `${value.toFixed(1)}%`;
  };

  return (
    <div className="equity-chart-widget">
      <div className="equity-header">
        <h3>Performance</h3>
        <div className="time-range-buttons">
          {(['1W', '1M', '3M', 'YTD', 'ALL'] as TimeRange[]).map(range => (
            <button
              key={range}
              className={`range-btn ${timeRange === range ? 'active' : ''}`}
              onClick={() => setTimeRange(range)}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      <div className="equity-chart" ref={containerRef} />

      {loading ? (
        <div className="equity-stats loading">Loading...</div>
      ) : analytics ? (
        <div className="equity-stats">
          <div className="stat-row primary">
            <div className="stat-item large">
              <span className="stat-label">Total P&L</span>
              <span className={`stat-value ${analytics.total_pnl >= 0 ? 'profit' : 'loss'}`}>
                {formatCurrency(analytics.total_pnl)}
              </span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Win Rate</span>
              <span className="stat-value">{formatPercent(analytics.win_rate)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Avg Win</span>
              <span className="stat-value profit">{formatCurrency(analytics.avg_win)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Avg Loss</span>
              <span className="stat-value loss">{formatCurrency(analytics.avg_loss)}</span>
            </div>
          </div>

          <div className="stat-row secondary">
            <div className="stat-item">
              <span className="stat-label">Total Trades</span>
              <span className="stat-value">{analytics.total_trades}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Winners</span>
              <span className="stat-value profit">{analytics.winners}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Losers</span>
              <span className="stat-value loss">{analytics.losers}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Open</span>
              <span className="stat-value">{analytics.open_trades}</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="equity-stats empty">
          <p>No trade data available</p>
        </div>
      )}
    </div>
  );
}
