// src/components/ReportingView.tsx
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  AreaSeries,
} from 'lightweight-charts';
import type { IChartApi, UTCTimestamp } from 'lightweight-charts';

const JOURNAL_API = 'http://localhost:3002';

interface LogAnalytics {
  log_id: string;
  log_name: string;

  // Time & Scale
  span_days: number;
  total_trades: number;
  trades_per_week: number;

  // Capital & Returns
  starting_capital: number;
  starting_capital_dollars: number;
  current_equity: number;
  current_equity_dollars: number;
  net_profit: number;
  net_profit_dollars: number;
  total_return_percent: number;

  // Win/Loss Distribution
  open_trades: number;
  closed_trades: number;
  winners: number;
  losers: number;
  breakeven: number;
  win_rate: number;
  avg_win: number;
  avg_win_dollars: number;
  avg_loss: number;
  avg_loss_dollars: number;
  win_loss_ratio: number;

  // Risk & Asymmetry
  avg_risk: number;
  avg_risk_dollars: number;
  largest_win: number;
  largest_win_dollars: number;
  largest_loss: number;
  largest_loss_dollars: number;
  largest_win_pct_gross: number;
  largest_loss_pct_gross: number;

  // System Health
  profit_factor: number;
  max_drawdown_pct: number;
  avg_r_multiple: number;
}

interface EquityPoint {
  time: string;
  value: number;
  trade_id?: string;
}

interface DrawdownPoint {
  time: string;
  drawdown_pct: number;
  peak: number;
  current: number;
}

interface ReportingViewProps {
  logId: string;
  logName: string;
  onClose: () => void;
}

type TimeRange = '1M' | '3M' | 'ALL';

export default function ReportingView({ logId, logName, onClose }: ReportingViewProps) {
  const equityChartRef = useRef<HTMLDivElement | null>(null);
  const drawdownChartRef = useRef<HTMLDivElement | null>(null);
  const equityChartApiRef = useRef<IChartApi | null>(null);
  const drawdownChartApiRef = useRef<IChartApi | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const equitySeriesRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const drawdownSeriesRef = useRef<any>(null);

  const [analytics, setAnalytics] = useState<LogAnalytics | null>(null);
  const [equityData, setEquityData] = useState<EquityPoint[]>([]);
  const [drawdownData, setDrawdownData] = useState<DrawdownPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<TimeRange>('ALL');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [analyticsRes, equityRes, drawdownRes] = await Promise.all([
        fetch(`${JOURNAL_API}/api/logs/${logId}/analytics`),
        fetch(`${JOURNAL_API}/api/logs/${logId}/equity`),
        fetch(`${JOURNAL_API}/api/logs/${logId}/drawdown`)
      ]);

      const analyticsData = await analyticsRes.json();
      const equityDataRes = await equityRes.json();
      const drawdownDataRes = await drawdownRes.json();

      if (analyticsData.success) {
        setAnalytics(analyticsData.data);
      }

      if (equityDataRes.success) {
        setEquityData(equityDataRes.data.equity || []);
      }

      if (drawdownDataRes.success) {
        setDrawdownData(drawdownDataRes.data.drawdown || []);
      }
    } catch (err) {
      console.error('ReportingView fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [logId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Create equity chart
  useEffect(() => {
    if (!equityChartRef.current || equityChartApiRef.current) return;

    try {
      const chart = createChart(equityChartRef.current, {
        height: 180,
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
        });
        equitySeriesRef.current = series;
      }

      equityChartApiRef.current = chart;

      const handleResize = () => {
        if (!equityChartRef.current || !equityChartApiRef.current) return;
        const { width } = equityChartRef.current.getBoundingClientRect();
        equityChartApiRef.current.applyOptions({ width });
      };

      handleResize();
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        if (equityChartApiRef.current) equityChartApiRef.current.remove();
        equityChartApiRef.current = null;
        equitySeriesRef.current = null;
      };
    } catch (err) {
      console.error('Equity chart creation error:', err);
    }
  }, []);

  // Create drawdown chart
  useEffect(() => {
    if (!drawdownChartRef.current || drawdownChartApiRef.current) return;

    try {
      const chart = createChart(drawdownChartRef.current, {
        height: 120,
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
          lineColor: 'rgba(248,113,113,1)',
          topColor: 'rgba(248,113,113,0.4)',
          bottomColor: 'rgba(248,113,113,0.05)',
          lineWidth: 2,
          invertFilledArea: true,
        });
        drawdownSeriesRef.current = series;
      }

      drawdownChartApiRef.current = chart;

      const handleResize = () => {
        if (!drawdownChartRef.current || !drawdownChartApiRef.current) return;
        const { width } = drawdownChartRef.current.getBoundingClientRect();
        drawdownChartApiRef.current.applyOptions({ width });
      };

      handleResize();
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        if (drawdownChartApiRef.current) drawdownChartApiRef.current.remove();
        drawdownChartApiRef.current = null;
        drawdownSeriesRef.current = null;
      };
    } catch (err) {
      console.error('Drawdown chart creation error:', err);
    }
  }, []);

  // Update equity chart data
  useEffect(() => {
    if (!equitySeriesRef.current || !equityChartApiRef.current || equityData.length === 0) return;

    try {
      const filteredData = filterByTimeRange(equityData, timeRange);
      if (filteredData.length === 0) {
        equitySeriesRef.current.setData([]);
        return;
      }

      const chartData = filteredData.map(p => ({
        time: Math.floor(new Date(p.time).getTime() / 1000) as UTCTimestamp,
        value: p.value / 100,
      }));

      const lastValue = chartData[chartData.length - 1]?.value || 0;
      const isProfit = lastValue >= 0;

      equitySeriesRef.current.applyOptions({
        lineColor: isProfit ? 'rgba(74,222,128,1)' : 'rgba(248,113,113,1)',
        topColor: isProfit ? 'rgba(74,222,128,0.4)' : 'rgba(248,113,113,0.4)',
        bottomColor: isProfit ? 'rgba(74,222,128,0.05)' : 'rgba(248,113,113,0.05)',
      });

      equitySeriesRef.current.setData(chartData);
      equityChartApiRef.current.timeScale().fitContent();
    } catch (err) {
      console.error('Equity chart data update error:', err);
    }
  }, [equityData, timeRange]);

  // Update drawdown chart data
  useEffect(() => {
    if (!drawdownSeriesRef.current || !drawdownChartApiRef.current || drawdownData.length === 0) return;

    try {
      const filteredData = filterByTimeRange(drawdownData, timeRange);
      if (filteredData.length === 0) {
        drawdownSeriesRef.current.setData([]);
        return;
      }

      const chartData = filteredData.map(p => ({
        time: Math.floor(new Date(p.time).getTime() / 1000) as UTCTimestamp,
        value: -p.drawdown_pct, // Negative so it goes down
      }));

      drawdownSeriesRef.current.setData(chartData);
      drawdownChartApiRef.current.timeScale().fitContent();
    } catch (err) {
      console.error('Drawdown chart data update error:', err);
    }
  }, [drawdownData, timeRange]);

  const filterByTimeRange = <T extends { time: string }>(data: T[], range: TimeRange): T[] => {
    if (range === 'ALL') return data;

    const now = new Date();
    let fromDate: Date;

    switch (range) {
      case '1M':
        fromDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        break;
      case '3M':
        fromDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
        break;
      default:
        return data;
    }

    return data.filter(p => new Date(p.time) >= fromDate);
  };

  const formatCurrency = (cents: number) => {
    const dollars = cents / 100;
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
  };

  return (
    <div className="reporting-view">
      <div className="reporting-header">
        <button className="btn-back" onClick={onClose}>
          &larr; Back
        </button>
        <h2>{logName} - Performance Review</h2>
        <div className="time-range-buttons">
          {(['1M', '3M', 'ALL'] as TimeRange[]).map(range => (
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

      {loading ? (
        <div className="reporting-loading">Loading analytics...</div>
      ) : analytics ? (
        <>
          <div className="reporting-charts">
            <div className="chart-section">
              <h4>Equity Curve</h4>
              <div className="chart-container" ref={equityChartRef} />
            </div>
            <div className="chart-section">
              <h4>Drawdown</h4>
              <div className="chart-container" ref={drawdownChartRef} />
            </div>
          </div>

          <div className="reporting-stats">
            <div className="stats-section">
              <h4>Capital & Returns</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Starting</span>
                  <span className="stat-value">
                    ${(analytics.starting_capital / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Current</span>
                  <span className="stat-value">
                    ${(analytics.current_equity / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Net Profit</span>
                  <span className={`stat-value ${analytics.net_profit >= 0 ? 'profit' : 'loss'}`}>
                    {formatCurrency(analytics.net_profit)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Return</span>
                  <span className={`stat-value ${analytics.total_return_percent >= 0 ? 'profit' : 'loss'}`}>
                    {formatPercent(analytics.total_return_percent)}
                  </span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>Win/Loss Distribution</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Winners</span>
                  <span className="stat-value profit">
                    {analytics.winners} ({analytics.win_rate.toFixed(1)}%)
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Losers</span>
                  <span className="stat-value loss">
                    {analytics.losers}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Win</span>
                  <span className="stat-value profit">
                    {formatCurrency(analytics.avg_win)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Loss</span>
                  <span className="stat-value loss">
                    {formatCurrency(analytics.avg_loss)}
                  </span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>Risk & Asymmetry</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Avg Risk</span>
                  <span className="stat-value">
                    ${(analytics.avg_risk / 100).toFixed(2)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Largest Win</span>
                  <span className="stat-value profit">
                    {formatCurrency(analytics.largest_win)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Largest Loss</span>
                  <span className="stat-value loss">
                    {formatCurrency(analytics.largest_loss)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Win/Loss Ratio</span>
                  <span className="stat-value">
                    {analytics.win_loss_ratio.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>System Health</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Profit Factor</span>
                  <span className={`stat-value ${analytics.profit_factor >= 1 ? 'profit' : 'loss'}`}>
                    {analytics.profit_factor.toFixed(2)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Max Drawdown</span>
                  <span className="stat-value loss">
                    -{analytics.max_drawdown_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg R-Multiple</span>
                  <span className={`stat-value ${analytics.avg_r_multiple >= 0 ? 'profit' : 'loss'}`}>
                    {analytics.avg_r_multiple.toFixed(2)}R
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Span</span>
                  <span className="stat-value">
                    {analytics.span_days} days
                  </span>
                </div>
              </div>
            </div>

            <div className="stats-section time-scale">
              <h4>Time & Scale</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Total Trades</span>
                  <span className="stat-value">{analytics.total_trades}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Open</span>
                  <span className="stat-value">{analytics.open_trades}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Closed</span>
                  <span className="stat-value">{analytics.closed_trades}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Trades/Week</span>
                  <span className="stat-value">{analytics.trades_per_week.toFixed(1)}</span>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="reporting-empty">No analytics data available</div>
      )}
    </div>
  );
}
