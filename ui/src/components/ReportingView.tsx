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

  // Gross P&L
  gross_profit: number;
  gross_profit_dollars: number;
  gross_loss: number;
  gross_loss_dollars: number;
  avg_net_profit: number;
  avg_net_profit_dollars: number;

  // System Health
  profit_factor: number;
  max_drawdown_pct: number;
  avg_r_multiple: number;
  avg_r2r: number;
  sharpe_ratio: number;
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

interface DistributionBin {
  bin_start: number;
  bin_start_dollars: number;
  bin_end: number;
  bin_end_dollars: number;
  count: number;
  is_zero: boolean;
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
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const [analytics, setAnalytics] = useState<LogAnalytics | null>(null);
  const [equityData, setEquityData] = useState<EquityPoint[]>([]);
  const [drawdownData, setDrawdownData] = useState<DrawdownPoint[]>([]);
  const [distributionData, setDistributionData] = useState<DistributionBin[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<TimeRange>('ALL');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ imported: number; errors: number } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [analyticsRes, equityRes, drawdownRes, distributionRes] = await Promise.all([
        fetch(`${JOURNAL_API}/api/logs/${logId}/analytics`),
        fetch(`${JOURNAL_API}/api/logs/${logId}/equity`),
        fetch(`${JOURNAL_API}/api/logs/${logId}/drawdown`),
        fetch(`${JOURNAL_API}/api/logs/${logId}/distribution?bin_size=50`)
      ]);

      const analyticsData = await analyticsRes.json();
      const equityDataRes = await equityRes.json();
      const drawdownDataRes = await drawdownRes.json();
      const distributionDataRes = await distributionRes.json();

      if (analyticsData.success) {
        setAnalytics(analyticsData.data);
      }

      if (equityDataRes.success) {
        setEquityData(equityDataRes.data.equity || []);
      }

      if (drawdownDataRes.success) {
        setDrawdownData(drawdownDataRes.data.drawdown || []);
      }

      if (distributionDataRes.success) {
        setDistributionData(distributionDataRes.data.distribution || []);
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

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setImporting(true);
    setImportResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${JOURNAL_API}/api/logs/${logId}/import`, {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();

      if (result.success) {
        setImportResult({
          imported: result.imported,
          errors: result.total_errors || 0,
        });
        // Refresh data after import
        fetchData();
      } else {
        setImportResult({ imported: 0, errors: 1 });
      }
    } catch (err) {
      console.error('Import error:', err);
      setImportResult({ imported: 0, errors: 1 });
    } finally {
      setImporting(false);
      // Reset file input
      if (importInputRef.current) {
        importInputRef.current.value = '';
      }
    }
  };

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

  // Create and update equity chart
  useEffect(() => {
    if (!equityChartRef.current || loading || equityData.length === 0) return;

    // Clean up existing chart
    if (equityChartApiRef.current) {
      equityChartApiRef.current.remove();
      equityChartApiRef.current = null;
    }

    const container = equityChartRef.current;
    const { width } = container.getBoundingClientRect();

    const chart = createChart(container, {
      width: width || 800,
      height: 438,
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

    equityChartApiRef.current = chart;

    // Add series - use type assertion for v5 API
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = (chart as any).addSeries(AreaSeries, {
      lineColor: 'rgba(74,222,128,1)',
      topColor: 'rgba(74,222,128,0.4)',
      bottomColor: 'rgba(74,222,128,0.05)',
      lineWidth: 2,
    });

    // Process data - deduplicate and sort by time
    const filteredData = filterByTimeRange(equityData, timeRange);
    const timeMap = new Map<number, number>();
    for (const p of filteredData) {
      const time = Math.floor(new Date(p.time).getTime() / 1000);
      timeMap.set(time, p.value / 100);
    }

    const chartData = Array.from(timeMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time: time as UTCTimestamp, value }));

    if (chartData.length > 0) {
      const lastValue = chartData[chartData.length - 1]?.value || 0;
      const isProfit = lastValue >= 0;

      series.applyOptions({
        lineColor: isProfit ? 'rgba(74,222,128,1)' : 'rgba(248,113,113,1)',
        topColor: isProfit ? 'rgba(74,222,128,0.4)' : 'rgba(248,113,113,0.4)',
        bottomColor: isProfit ? 'rgba(74,222,128,0.05)' : 'rgba(248,113,113,0.05)',
      });

      series.setData(chartData);
      chart.timeScale().fitContent();
    }

    const handleResize = () => {
      if (!container || !equityChartApiRef.current) return;
      const { width: newWidth } = container.getBoundingClientRect();
      if (newWidth > 0) {
        equityChartApiRef.current.applyOptions({ width: newWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (equityChartApiRef.current) {
        equityChartApiRef.current.remove();
        equityChartApiRef.current = null;
      }
    };
  }, [loading, equityData, timeRange]);

  // Create and update drawdown chart
  useEffect(() => {
    if (!drawdownChartRef.current || loading || drawdownData.length === 0) return;

    // Clean up existing chart
    if (drawdownChartApiRef.current) {
      drawdownChartApiRef.current.remove();
      drawdownChartApiRef.current = null;
    }

    const container = drawdownChartRef.current;
    const { width } = container.getBoundingClientRect();

    const chart = createChart(container, {
      width: width || 800,
      height: 88,
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

    drawdownChartApiRef.current = chart;

    // Add series
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const series = (chart as any).addSeries(AreaSeries, {
      lineColor: 'rgba(248,113,113,1)',
      topColor: 'rgba(248,113,113,0.4)',
      bottomColor: 'rgba(248,113,113,0.05)',
      lineWidth: 2,
      invertFilledArea: true,
    });

    // Process data
    const filteredData = filterByTimeRange(drawdownData, timeRange);
    const timeMap = new Map<number, number>();
    for (const p of filteredData) {
      const time = Math.floor(new Date(p.time).getTime() / 1000);
      timeMap.set(time, -p.drawdown_pct);
    }

    const chartData = Array.from(timeMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time: time as UTCTimestamp, value }));

    if (chartData.length > 0) {
      series.setData(chartData);
      chart.timeScale().fitContent();
    }

    const handleResize = () => {
      if (!container || !drawdownChartApiRef.current) return;
      const { width: newWidth } = container.getBoundingClientRect();
      if (newWidth > 0) {
        drawdownChartApiRef.current.applyOptions({ width: newWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (drawdownChartApiRef.current) {
        drawdownChartApiRef.current.remove();
        drawdownChartApiRef.current = null;
      }
    };
  }, [loading, drawdownData, timeRange]);

  const _formatCurrency = (cents: number) => {
    const dollars = cents / 100;
    const formatted = Math.abs(dollars).toFixed(2);
    return dollars >= 0 ? `+$${formatted}` : `-$${formatted}`;
  };
  void _formatCurrency; // Available for future use

  const _formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
  };
  void _formatPercent; // Available for future use

  return (
    <div className="reporting-view">
      <div className="reporting-header">
        <button className="btn-back" onClick={onClose}>
          &larr; Back
        </button>
        <h2>{logName} - Performance Review</h2>
        <div className="header-actions">
          <div className="export-buttons">
            <a
              href={`${JOURNAL_API}/api/logs/${logId}/export?format=csv`}
              className="btn-export"
              download
            >
              Export CSV
            </a>
            <a
              href={`${JOURNAL_API}/api/logs/${logId}/export?format=xlsx`}
              className="btn-export"
              download
            >
              Export Excel
            </a>
            <input
              ref={importInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={handleImport}
              className="import-input"
            />
            <button
              className="btn-import"
              onClick={() => importInputRef.current?.click()}
              disabled={importing}
            >
              {importing ? 'Importing...' : 'Import'}
            </button>
          </div>
          {importResult && (
            <div className={`import-result ${importResult.errors > 0 ? 'has-errors' : ''}`}>
              Imported {importResult.imported} trades
              {importResult.errors > 0 && ` (${importResult.errors} errors)`}
            </div>
          )}
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
      </div>

      {loading ? (
        <div className="reporting-loading">Loading analytics...</div>
      ) : analytics ? (
        <>
          <div className="reporting-charts">
            <div className="chart-section equity-section">
              <h4>Equity Curve</h4>
              <div className="chart-container equity-chart" ref={equityChartRef} />
            </div>
            <div className="chart-section drawdown-section">
              <h4>Drawdown</h4>
              <div className="chart-container drawdown-chart" ref={drawdownChartRef} />
            </div>
          </div>

          {distributionData.length > 0 && (
            <div className="distribution-section">
              <h4>Return Distribution</h4>
              <div className="distribution-chart">
                {(() => {
                  const maxCount = Math.max(...distributionData.map(b => b.count));
                  return (
                    <div className="distribution-bars">
                      {distributionData.map((bin, idx) => (
                        <div
                          key={idx}
                          className={`distribution-bar ${bin.is_zero ? 'zero-bin' : ''} ${bin.bin_start_dollars < 0 ? 'loss' : 'profit'}`}
                          style={{ height: `${(bin.count / maxCount) * 100}%` }}
                          title={`$${bin.bin_start_dollars} to $${bin.bin_end_dollars}: ${bin.count} trades`}
                        />
                      ))}
                    </div>
                  );
                })()}
                <div className="distribution-axis">
                  <span className="axis-label left">
                    ${distributionData[0]?.bin_start_dollars || 0}
                  </span>
                  <span className="axis-label center">$0</span>
                  <span className="axis-label right">
                    ${distributionData[distributionData.length - 1]?.bin_end_dollars || 0}
                  </span>
                </div>
              </div>
              <p className="distribution-hint">
                Right-skewed distribution with fat tail = convexity edge
              </p>
            </div>
          )}

          <div className="reporting-stats">
            <div className="stats-section">
              <h4>Capital & Returns</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Span in Days</span>
                  <span className="stat-value">{analytics.span_days}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Starting Capital</span>
                  <span className="stat-value">
                    ${(analytics.starting_capital / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item highlight-green">
                  <span className="stat-label">Balance</span>
                  <span className="stat-value">
                    ${(analytics.current_equity / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item highlight-green">
                  <span className="stat-label">Total Return</span>
                  <span className="stat-value">
                    {analytics.total_return_percent.toFixed(2)}%
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Gross Profit</span>
                  <span className="stat-value profit">
                    ${(analytics.gross_profit / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Gross Loss</span>
                  <span className="stat-value loss">
                    -${(analytics.gross_loss / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Net Profit</span>
                  <span className={`stat-value ${analytics.net_profit >= 0 ? 'profit' : 'loss'}`}>
                    ${(analytics.net_profit / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Profit Factor</span>
                  <span className={`stat-value ${analytics.profit_factor >= 1 ? 'profit' : 'loss'}`}>
                    {analytics.profit_factor.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>Trade Distribution</h4>
              <div className="stats-grid">
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
                  <span className="stat-label">Win Rate</span>
                  <span className="stat-value">{analytics.win_rate.toFixed(1)}%</span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>Trade Averages</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Avg Risk per Trade</span>
                  <span className="stat-value">
                    ${(analytics.avg_risk / 100).toFixed(2)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Net Profit</span>
                  <span className={`stat-value ${analytics.avg_net_profit >= 0 ? 'profit' : 'loss'}`}>
                    ${(analytics.avg_net_profit / 100).toFixed(2)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Winning Trade</span>
                  <span className="stat-value profit">
                    ${(analytics.avg_win / 100).toFixed(2)}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Losing Trade</span>
                  <span className="stat-value loss">
                    (${Math.abs(analytics.avg_loss / 100).toFixed(2)})
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Ratio Avg Win/Loss</span>
                  <span className="stat-value">{analytics.win_loss_ratio.toFixed(2)}</span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>Extremes</h4>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Largest Winner</span>
                  <span className="stat-value profit">
                    ${(analytics.largest_win / 100).toLocaleString()}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Largest Loser</span>
                  <span className="stat-value loss">
                    (${Math.abs(analytics.largest_loss / 100).toLocaleString()})
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Winner as % Gross</span>
                  <span className="stat-value">{analytics.largest_win_pct_gross.toFixed(2)}%</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Loser as % Gross</span>
                  <span className="stat-value">{analytics.largest_loss_pct_gross.toFixed(2)}%</span>
                </div>
              </div>
            </div>

            <div className="stats-section">
              <h4>System Health</h4>
              <div className="stats-grid">
                <div className="stat-item highlight-yellow">
                  <span className="stat-label">Max Drawdown</span>
                  <span className="stat-value">
                    {analytics.max_drawdown_pct.toFixed(2)}%
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Average R2R</span>
                  <span className="stat-value">{analytics.avg_r2r.toFixed(2)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Sharpe Ratio</span>
                  <span className="stat-value">{analytics.sharpe_ratio.toFixed(2)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg R-Multiple</span>
                  <span className={`stat-value ${analytics.avg_r_multiple >= 0 ? 'profit' : 'loss'}`}>
                    {analytics.avg_r_multiple.toFixed(2)}R
                  </span>
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
