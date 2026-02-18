// ui/src/pages/MLLab.tsx
import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import ReactECharts from "echarts-for-react";

// ============================================================================
// Types
// ============================================================================

interface CircuitBreakerStatus {
  daily_pnl: number;
  daily_trades: number;
  high_water: number;
  avg_slippage: number;
  regime_confidence: number;
  ml_enabled: boolean;
  limits: {
    max_daily_loss: number;
    max_drawdown_pct: number;
    max_orders_per_second: number;
    slippage_threshold: number;
    min_confidence: number;
  };
}

interface BreakerCheckResult {
  allow_trade: boolean;
  action: "allow" | "rules_only" | "block_all";
  triggered_breakers: Array<{
    name: string;
    triggered: boolean;
    severity: "warning" | "critical";
    message: string;
    threshold: number | null;
    current_value: number | null;
  }>;
  checked_at: string;
}

interface MLModel {
  id: number;
  model_name: string;
  model_version: number;
  model_type: string;
  feature_set_version: string;
  train_auc: number | null;
  val_auc: number | null;
  train_samples: number | null;
  val_samples: number | null;
  brier_tier_0: number | null;
  brier_tier_1: number | null;
  brier_tier_2: number | null;
  brier_tier_3: number | null;
  top_10_avg_pnl: number | null;
  top_20_avg_pnl: number | null;
  regime: string | null;
  status: "training" | "validating" | "champion" | "challenger" | "retired";
  deployed_at: string | null;
  retired_at: string | null;
  created_at: string;
}

interface MLExperiment {
  id: number;
  experiment_name: string;
  description: string | null;
  champion_model_id: number;
  challenger_model_id: number;
  traffic_split: number;
  max_duration_days: number;
  min_samples_per_arm: number;
  early_stop_threshold: number;
  status: "running" | "concluded" | "aborted";
  started_at: string;
  ended_at: string | null;
  champion_samples: number;
  challenger_samples: number;
  champion_win_rate: number | null;
  challenger_win_rate: number | null;
  champion_avg_rar: number | null;
  challenger_avg_rar: number | null;
  p_value: number | null;
  winner: "champion" | "challenger" | "no_difference" | null;
}

interface MLDecision {
  id: number;
  ideaId: string;
  decisionTime: string;
  modelId: number | null;
  modelVersion: number | null;
  selectorParamsVersion: number;
  featureSnapshotId: number | null;
  originalScore: number;
  mlScore: number | null;
  finalScore: number;
  experimentId: number | null;
  experimentArm: "champion" | "challenger" | null;
  actionTaken: "ranked" | "presented" | "traded" | "dismissed";
}

interface DailyPerformance {
  id: number;
  date: string;
  net_pnl: number;
  gross_pnl: number;
  total_fees: number;
  high_water_pnl: number;
  max_drawdown: number;
  drawdown_pct: number | null;
  trade_count: number;
  win_count: number;
  loss_count: number;
  primary_model_id: number | null;
  ml_contribution_pct: number | null;
}

interface EquityCurvePoint {
  timestamp: string;
  cumulative_pnl: number;
  high_water: number;
  drawdown: number;
}

interface MLDecisionStats {
  totals: {
    count: number;
    avg_original: number;
    avg_ml: number;
    avg_final: number;
    ml_stddev: number;
  };
  score_distribution: Array<{
    bucket: string;
    count: number;
    avg_original: number;
    avg_ml: number;
  }>;
  comparison: {
    similar: number;
    ml_much_higher: number;
    ml_slightly_higher: number;
    ml_much_lower: number;
    ml_slightly_lower: number;
  };
  hourly_volume: Array<{
    hour: string;
    count: number;
  }>;
}

// ============================================================================
// Component
// ============================================================================

export default function MLLabPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data state
  const [circuitBreakers, setCircuitBreakers] = useState<CircuitBreakerStatus | null>(null);
  const [breakerCheck, setBreakerCheck] = useState<BreakerCheckResult | null>(null);
  const [models, setModels] = useState<MLModel[]>([]);
  const [champion, setChampion] = useState<MLModel | null>(null);
  const [experiments, setExperiments] = useState<MLExperiment[]>([]);
  const [decisions, setDecisions] = useState<MLDecision[]>([]);
  const [decisionStats, setDecisionStats] = useState<MLDecisionStats | null>(null);
  const [dailyPerformance, setDailyPerformance] = useState<DailyPerformance[]>([]);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);

  // UI state
  const [activeTab, setActiveTab] = useState<"overview" | "models" | "experiments" | "decisions" | "performance">("overview");
  const [refreshing, setRefreshing] = useState(false);

  // Fetch all data
  const fetchData = async () => {
    try {
      // Fetch each endpoint separately to handle individual failures
      const safeFetch = async (url: string, options?: RequestInit) => {
        try {
          const res = await fetch(url, { credentials: "include", ...options });
          if (res.ok) return await res.json();
          return null;
        } catch {
          return null;
        }
      };

      const [cb, check, modelsList, champ, exps, decs, stats, perf, equity] = await Promise.all([
        safeFetch("/api/admin/ml/circuit-breakers"),
        safeFetch("/api/admin/ml/circuit-breakers/check", { method: "POST" }),
        safeFetch("/api/admin/ml/models"),
        safeFetch("/api/admin/ml/models/champion"),
        safeFetch("/api/admin/ml/experiments"),
        safeFetch("/api/admin/ml/decisions?limit=100"),
        safeFetch("/api/admin/ml/decisions/stats"),
        safeFetch("/api/admin/ml/daily-performance?limit=30"),
        safeFetch("/api/admin/ml/equity-curve?days=30"),
      ]);

      if (cb) setCircuitBreakers(cb);
      if (check) setBreakerCheck(check);
      if (modelsList) setModels(Array.isArray(modelsList) ? modelsList : (modelsList?.data || []));
      if (champ && !champ.error) setChampion(champ?.data || champ);
      if (exps) setExperiments(Array.isArray(exps) ? exps : (exps?.data || []));

      // Debug: log raw decisions response
      console.log('[MLLab] Raw decisions response:', decs);
      const decisionsArray = Array.isArray(decs) ? decs : (decs?.data || []);
      console.log('[MLLab] Extracted decisions array:', decisionsArray);
      if (decisionsArray.length > 0) {
        console.log('[MLLab] First decision:', decisionsArray[0]);
        console.log('[MLLab] First decision keys:', Object.keys(decisionsArray[0]));
      }
      if (decs) setDecisions(decisionsArray);

      if (stats) setDecisionStats(stats?.data || stats);
      if (perf) setDailyPerformance(Array.isArray(perf) ? perf : (perf?.data || []));
      if (equity) setEquityCurve(Array.isArray(equity) ? equity : (equity?.data || []));

    } catch (err) {
      setError("Failed to load ML Lab data");
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  // Toggle ML
  const handleToggleML = async () => {
    if (!circuitBreakers) return;
    const endpoint = circuitBreakers.ml_enabled
      ? "/api/admin/ml/circuit-breakers/disable-ml"
      : "/api/admin/ml/circuit-breakers/enable-ml";

    await fetch(endpoint, { credentials: "include", method: "POST" });
    fetchData();
  };

  // Format helpers
  const formatCurrency = (value: number) => {
    const abs = Math.abs(value);
    const sign = value >= 0 ? "+" : "-";
    return `${sign}$${abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatPercent = (value: number | null) => {
    if (value === null) return "—";
    return `${(value * 100).toFixed(1)}%`;
  };

  const formatDate = (d: string) => {
    if (!d) return "—";
    // Handle ISO dates with microseconds (trim to milliseconds for JS Date)
    const normalized = d.replace(/(\.\d{3})\d+/, "$1");
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return "—";
    return date.toLocaleString();
  };

  const formatShortDate = (d: string) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString();
  };

  // Equity curve chart options
  const equityChartOptions = useMemo(() => {
    if (equityCurve.length === 0) return {};

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(24, 24, 27, 0.95)",
        borderColor: "rgba(255, 255, 255, 0.1)",
        textStyle: { color: "#e4e4e7", fontSize: 12 },
        formatter: (params: any) => {
          const point = params[0];
          return `
            <div style="font-size: 11px;">
              <div style="margin-bottom: 4px;">${new Date(point.axisValue).toLocaleDateString()}</div>
              <div>P&L: <b style="color: ${point.value >= 0 ? '#22c55e' : '#ef4444'}">${formatCurrency(point.value)}</b></div>
            </div>
          `;
        },
      },
      grid: { top: 20, right: 20, bottom: 30, left: 60 },
      xAxis: {
        type: "category",
        data: equityCurve.map((p) => p.timestamp),
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
        axisLabel: {
          color: "#71717a",
          fontSize: 10,
          formatter: (v: string) => new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
        axisLabel: {
          color: "#71717a",
          fontSize: 10,
          formatter: (v: number) => `$${v.toLocaleString()}`,
        },
      },
      series: [
        {
          type: "line",
          data: equityCurve.map((p) => p.cumulative_pnl),
          smooth: true,
          symbol: "none",
          lineStyle: { color: "#3b82f6", width: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(59, 130, 246, 0.3)" },
                { offset: 1, color: "rgba(59, 130, 246, 0)" },
              ],
            },
          },
        },
        {
          type: "line",
          data: equityCurve.map((p) => p.high_water),
          smooth: true,
          symbol: "none",
          lineStyle: { color: "#22c55e", width: 1, type: "dashed" },
        },
      ],
    };
  }, [equityCurve]);

  if (loading) {
    return (
      <div className="ml-lab-page">
        <div className="loading-state">Loading ML Lab...</div>
        <style>{styles}</style>
      </div>
    );
  }

  return (
    <div className="ml-lab-page">
      {/* Header */}
      <header className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate("/admin")}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </button>
          <h1>ML Lab</h1>
          <span className="subtitle">Trade Selector Machine Learning</span>
        </div>
        <div className="header-right">
          <button className="refresh-btn" onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="tab-nav">
        {(["overview", "models", "experiments", "decisions", "performance"] as const).map((tab) => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="page-content">
        {error && <div className="error-banner">{error}</div>}

        {activeTab === "overview" && (
          <div className="overview-tab">
            {/* Circuit Breaker Status */}
            <section className="section">
              <div className="section-header">
                <h2>Circuit Breakers</h2>
                <button
                  className={`ml-toggle ${circuitBreakers?.ml_enabled ? "enabled" : "disabled"}`}
                  onClick={handleToggleML}
                >
                  ML {circuitBreakers?.ml_enabled ? "Enabled" : "Disabled"}
                </button>
              </div>

              {breakerCheck && (
                <div className={`system-status status-${breakerCheck.action}`}>
                  <div className="status-indicator">
                    <span className={`status-dot ${breakerCheck.action}`}></span>
                    <span className="status-text">
                      {breakerCheck.action === "allow" && "All Systems Go"}
                      {breakerCheck.action === "rules_only" && "Rules Only Mode"}
                      {breakerCheck.action === "block_all" && "Trading Blocked"}
                    </span>
                  </div>
                  {breakerCheck.triggered_breakers?.length > 0 && (
                    <div className="triggered-list">
                      {breakerCheck.triggered_breakers.map((b, i) => (
                        <div key={i} className={`triggered-item ${b.severity}`}>
                          <span className="breaker-name">{b.name.replace(/_/g, " ")}</span>
                          <span className="breaker-msg">{b.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {circuitBreakers?.limits && (
                <div className="breakers-grid">
                  <div className="breaker-card">
                    <div className="breaker-label">Daily P&L</div>
                    <div className={`breaker-value ${circuitBreakers.daily_pnl >= 0 ? "positive" : "negative"}`}>
                      {formatCurrency(circuitBreakers.daily_pnl)}
                    </div>
                    <div className="breaker-limit">Limit: -{formatCurrency(circuitBreakers.limits.max_daily_loss).slice(1)}</div>
                    <div className="breaker-bar">
                      <div
                        className="breaker-fill"
                        style={{
                          width: `${Math.min(100, Math.abs(circuitBreakers.daily_pnl) / circuitBreakers.limits.max_daily_loss * 100)}%`,
                          background: circuitBreakers.daily_pnl >= 0 ? "#22c55e" : "#ef4444",
                        }}
                      />
                    </div>
                  </div>

                  <div className="breaker-card">
                    <div className="breaker-label">Drawdown</div>
                    <div className="breaker-value">
                      {circuitBreakers.high_water > 0
                        ? formatPercent((circuitBreakers.high_water - circuitBreakers.daily_pnl) / circuitBreakers.high_water)
                        : "0%"}
                    </div>
                    <div className="breaker-limit">Limit: {formatPercent(circuitBreakers.limits.max_drawdown_pct)}</div>
                    <div className="breaker-bar">
                      <div
                        className="breaker-fill"
                        style={{
                          width: `${Math.min(100, (circuitBreakers.high_water > 0
                            ? (circuitBreakers.high_water - circuitBreakers.daily_pnl) / circuitBreakers.high_water / circuitBreakers.limits.max_drawdown_pct * 100
                            : 0))}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div className="breaker-card">
                    <div className="breaker-label">Avg Slippage</div>
                    <div className="breaker-value">${circuitBreakers.avg_slippage.toFixed(2)}</div>
                    <div className="breaker-limit">Threshold: ${circuitBreakers.limits.slippage_threshold.toFixed(2)}</div>
                    <div className="breaker-bar">
                      <div
                        className="breaker-fill"
                        style={{
                          width: `${Math.min(100, circuitBreakers.avg_slippage / circuitBreakers.limits.slippage_threshold * 100)}%`,
                        }}
                      />
                    </div>
                  </div>

                  <div className="breaker-card">
                    <div className="breaker-label">Regime Confidence</div>
                    <div className="breaker-value">{formatPercent(circuitBreakers.regime_confidence)}</div>
                    <div className="breaker-limit">Min: {formatPercent(circuitBreakers.limits.min_confidence)}</div>
                    <div className="breaker-bar">
                      <div
                        className="breaker-fill positive"
                        style={{ width: `${circuitBreakers.regime_confidence * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}
            </section>

            {/* Champion Model */}
            <section className="section">
              <h2>Champion Model</h2>
              {champion ? (
                <div className="champion-card">
                  <div className="champion-header">
                    <div className="champion-name">{champion.model_name}</div>
                    <span className="version-badge">v{champion.model_version}</span>
                    <span className="status-badge champion">Champion</span>
                  </div>
                  <div className="champion-stats">
                    <div className="stat">
                      <span className="stat-label">Type</span>
                      <span className="stat-value">{champion.model_type}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Features</span>
                      <span className="stat-value">{champion.feature_set_version}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Val AUC</span>
                      <span className="stat-value">{champion.val_auc?.toFixed(3) ?? "—"}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Top-10 Avg</span>
                      <span className="stat-value">{champion.top_10_avg_pnl ? formatCurrency(champion.top_10_avg_pnl) : "—"}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Samples</span>
                      <span className="stat-value">{champion.train_samples?.toLocaleString() ?? "—"}</span>
                    </div>
                    <div className="stat">
                      <span className="stat-label">Deployed</span>
                      <span className="stat-value">{champion.deployed_at ? formatShortDate(champion.deployed_at) : "—"}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="no-data">No champion model deployed. System is in rules-only mode.</div>
              )}
            </section>

            {/* ML Decision Stats */}
            {decisionStats && (
              <section className="section">
                <h2>ML Scoring Statistics</h2>
                <div className="stats-summary">
                  <div className="stat-card">
                    <div className="stat-value">{decisionStats.totals.count.toLocaleString()}</div>
                    <div className="stat-label">Total Decisions</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{decisionStats.totals.avg_original.toFixed(1)}</div>
                    <div className="stat-label">Avg Original Score</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{decisionStats.totals.avg_ml.toFixed(1)}</div>
                    <div className="stat-label">Avg ML Score</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-value">{decisionStats.totals.avg_final.toFixed(1)}</div>
                    <div className="stat-label">Avg Final Score</div>
                  </div>
                </div>

                <h3 style={{ marginTop: "1.5rem", marginBottom: "1rem" }}>ML Score Distribution</h3>
                <div className="chart-container">
                  <ReactECharts
                    option={{
                      tooltip: { trigger: "axis" },
                      xAxis: {
                        type: "category",
                        data: decisionStats.score_distribution.map((d) => d.bucket),
                        axisLabel: { color: "#9ca3af" },
                      },
                      yAxis: {
                        type: "value",
                        axisLabel: { color: "#9ca3af" },
                      },
                      series: [
                        {
                          name: "Count",
                          type: "bar",
                          data: decisionStats.score_distribution.map((d) => d.count),
                          itemStyle: {
                            color: (params: { dataIndex: number }) => {
                              const colors = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#10b981"];
                              return colors[params.dataIndex] || "#6366f1";
                            },
                          },
                        },
                      ],
                      grid: { left: 60, right: 20, top: 20, bottom: 40 },
                    }}
                    style={{ height: 250 }}
                  />
                </div>

                <h3 style={{ marginTop: "1.5rem", marginBottom: "1rem" }}>ML vs Original Score Comparison</h3>
                <div className="comparison-grid">
                  <div className="comparison-item negative">
                    <div className="comparison-value">{decisionStats.comparison.ml_much_lower?.toLocaleString() || 0}</div>
                    <div className="comparison-label">ML Much Lower</div>
                    <div className="comparison-pct">
                      {((decisionStats.comparison.ml_much_lower || 0) / decisionStats.totals.count * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="comparison-item warning">
                    <div className="comparison-value">{decisionStats.comparison.ml_slightly_lower?.toLocaleString() || 0}</div>
                    <div className="comparison-label">ML Slightly Lower</div>
                    <div className="comparison-pct">
                      {((decisionStats.comparison.ml_slightly_lower || 0) / decisionStats.totals.count * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="comparison-item neutral">
                    <div className="comparison-value">{decisionStats.comparison.similar?.toLocaleString() || 0}</div>
                    <div className="comparison-label">Similar</div>
                    <div className="comparison-pct">
                      {((decisionStats.comparison.similar || 0) / decisionStats.totals.count * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="comparison-item positive-light">
                    <div className="comparison-value">{decisionStats.comparison.ml_slightly_higher?.toLocaleString() || 0}</div>
                    <div className="comparison-label">ML Slightly Higher</div>
                    <div className="comparison-pct">
                      {((decisionStats.comparison.ml_slightly_higher || 0) / decisionStats.totals.count * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="comparison-item positive">
                    <div className="comparison-value">{decisionStats.comparison.ml_much_higher?.toLocaleString() || 0}</div>
                    <div className="comparison-label">ML Much Higher</div>
                    <div className="comparison-pct">
                      {((decisionStats.comparison.ml_much_higher || 0) / decisionStats.totals.count * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </section>
            )}

            {/* Equity Curve */}
            <section className="section">
              <h2>Equity Curve (30 Days)</h2>
              {equityCurve.length > 0 ? (
                <div className="chart-container">
                  <ReactECharts option={equityChartOptions} style={{ height: 300 }} />
                </div>
              ) : (
                <div className="no-data">No P&L data available yet.</div>
              )}
            </section>

            {/* Active Experiments */}
            <section className="section">
              <h2>Active Experiments</h2>
              {experiments.filter((e) => e.status === "running").length > 0 ? (
                <div className="experiments-list">
                  {experiments
                    .filter((e) => e.status === "running")
                    .map((exp) => (
                      <div key={exp.id} className="experiment-card">
                        <div className="exp-header">
                          <span className="exp-name">{exp.experiment_name}</span>
                          <span className="status-badge running">Running</span>
                        </div>
                        <div className="exp-stats">
                          <div className="exp-arm">
                            <span className="arm-label">Champion</span>
                            <span className="arm-samples">{exp.champion_samples} samples</span>
                            <span className="arm-winrate">{exp.champion_win_rate ? `${(exp.champion_win_rate * 100).toFixed(1)}% win` : "—"}</span>
                          </div>
                          <div className="exp-vs">vs</div>
                          <div className="exp-arm challenger">
                            <span className="arm-label">Challenger</span>
                            <span className="arm-samples">{exp.challenger_samples} samples</span>
                            <span className="arm-winrate">{exp.challenger_win_rate ? `${(exp.challenger_win_rate * 100).toFixed(1)}% win` : "—"}</span>
                          </div>
                        </div>
                        <div className="exp-footer">
                          <span className="traffic-split">{(exp.traffic_split * 100).toFixed(0)}% to challenger</span>
                          {exp.p_value && <span className="p-value">p = {exp.p_value.toFixed(4)}</span>}
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="no-data">No active experiments.</div>
              )}
            </section>
          </div>
        )}

        {activeTab === "models" && (
          <div className="models-tab">
            <section className="section">
              <h2>Model Registry</h2>
              {models.length > 0 ? (
                <div className="models-table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Version</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Val AUC</th>
                        <th>Top-10</th>
                        <th>Samples</th>
                        <th>Created</th>
                      </tr>
                    </thead>
                    <tbody>
                      {models.map((m) => (
                        <tr key={m.id} className={m.status === "champion" ? "highlight" : ""}>
                          <td className="model-name">{m.model_name}</td>
                          <td>v{m.model_version}</td>
                          <td>{m.model_type}</td>
                          <td>
                            <span className={`status-badge ${m.status}`}>{m.status}</span>
                          </td>
                          <td>{m.val_auc?.toFixed(3) ?? "—"}</td>
                          <td>{m.top_10_avg_pnl ? formatCurrency(m.top_10_avg_pnl) : "—"}</td>
                          <td>{m.train_samples?.toLocaleString() ?? "—"}</td>
                          <td>{formatShortDate(m.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="no-data">No models registered yet.</div>
              )}
            </section>
          </div>
        )}

        {activeTab === "experiments" && (
          <div className="experiments-tab">
            <section className="section">
              <h2>A/B Experiments</h2>
              {experiments.length > 0 ? (
                <div className="experiments-full-list">
                  {experiments.map((exp) => (
                    <div key={exp.id} className={`experiment-card-full ${exp.status}`}>
                      <div className="exp-header">
                        <div className="exp-title">
                          <span className="exp-name">{exp.experiment_name}</span>
                          <span className={`status-badge ${exp.status}`}>{exp.status}</span>
                        </div>
                        <div className="exp-meta">
                          Started {formatShortDate(exp.started_at)}
                          {exp.ended_at && ` • Ended ${formatShortDate(exp.ended_at)}`}
                        </div>
                      </div>

                      {exp.description && <p className="exp-description">{exp.description}</p>}

                      <div className="exp-comparison">
                        <div className="comparison-arm">
                          <div className="arm-header">Champion (Model #{exp.champion_model_id})</div>
                          <div className="arm-metrics">
                            <div className="metric">
                              <span className="metric-value">{exp.champion_samples}</span>
                              <span className="metric-label">samples</span>
                            </div>
                            <div className="metric">
                              <span className="metric-value">{exp.champion_win_rate ? `${(exp.champion_win_rate * 100).toFixed(1)}%` : "—"}</span>
                              <span className="metric-label">win rate</span>
                            </div>
                            <div className="metric">
                              <span className="metric-value">{exp.champion_avg_rar ? exp.champion_avg_rar.toFixed(2) : "—"}</span>
                              <span className="metric-label">avg RAR</span>
                            </div>
                          </div>
                        </div>

                        <div className="comparison-vs">VS</div>

                        <div className="comparison-arm challenger">
                          <div className="arm-header">Challenger (Model #{exp.challenger_model_id})</div>
                          <div className="arm-metrics">
                            <div className="metric">
                              <span className="metric-value">{exp.challenger_samples}</span>
                              <span className="metric-label">samples</span>
                            </div>
                            <div className="metric">
                              <span className="metric-value">{exp.challenger_win_rate ? `${(exp.challenger_win_rate * 100).toFixed(1)}%` : "—"}</span>
                              <span className="metric-label">win rate</span>
                            </div>
                            <div className="metric">
                              <span className="metric-value">{exp.challenger_avg_rar ? exp.challenger_avg_rar.toFixed(2) : "—"}</span>
                              <span className="metric-label">avg RAR</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="exp-results">
                        <div className="result-item">
                          <span className="result-label">Traffic Split</span>
                          <span className="result-value">{(exp.traffic_split * 100).toFixed(0)}% to challenger</span>
                        </div>
                        {exp.p_value !== null && (
                          <div className="result-item">
                            <span className="result-label">P-Value</span>
                            <span className={`result-value ${exp.p_value < 0.05 ? "significant" : ""}`}>
                              {exp.p_value.toFixed(4)}
                              {exp.p_value < 0.05 && " (significant)"}
                            </span>
                          </div>
                        )}
                        {exp.winner && (
                          <div className="result-item">
                            <span className="result-label">Winner</span>
                            <span className="result-value winner">{exp.winner}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">No experiments created yet.</div>
              )}
            </section>
          </div>
        )}

        {activeTab === "decisions" && (
          <div className="decisions-tab">
            <section className="section">
              <h2>Recent ML Decisions</h2>
              {decisions.length > 0 ? (
                <div className="decisions-table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Idea ID</th>
                        <th>Original</th>
                        <th>ML Score</th>
                        <th>Final</th>
                        <th>Action</th>
                        <th>Experiment</th>
                      </tr>
                    </thead>
                    <tbody>
                      {decisions.map((d) => (
                        <tr key={d.id}>
                          <td className="time-cell">{formatDate(d.decisionTime)}</td>
                          <td className="idea-cell">{d.ideaId?.slice(0, 30) || "—"}...</td>
                          <td className="score-cell">{d.originalScore != null ? Number(d.originalScore).toFixed(1) : "—"}</td>
                          <td className="score-cell ml">{d.mlScore != null ? Number(d.mlScore).toFixed(1) : "—"}</td>
                          <td className="score-cell final">{d.finalScore != null ? Number(d.finalScore).toFixed(1) : "—"}</td>
                          <td>
                            <span className={`action-badge ${d.actionTaken || "unknown"}`}>{d.actionTaken || "—"}</span>
                          </td>
                          <td>
                            {d.experimentId ? (
                              <span className={`arm-badge ${d.experimentArm}`}>
                                {d.experimentArm}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="no-data">No ML decisions logged yet. System is in shadow mode.</div>
              )}
            </section>
          </div>
        )}

        {activeTab === "performance" && (
          <div className="performance-tab">
            <section className="section">
              <h2>Daily Performance</h2>
              {dailyPerformance.length > 0 ? (
                <div className="performance-table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Net P&L</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Drawdown</th>
                        <th>ML %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyPerformance.map((d) => (
                        <tr key={d.id}>
                          <td>{d.date}</td>
                          <td className={d.net_pnl >= 0 ? "positive" : "negative"}>
                            {formatCurrency(d.net_pnl)}
                          </td>
                          <td>{d.trade_count}</td>
                          <td>
                            {d.trade_count > 0
                              ? `${((d.win_count / d.trade_count) * 100).toFixed(1)}%`
                              : "—"}
                          </td>
                          <td>{d.drawdown_pct ? formatPercent(d.drawdown_pct) : "—"}</td>
                          <td>{d.ml_contribution_pct ? formatPercent(d.ml_contribution_pct) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="no-data">No daily performance data yet.</div>
              )}
            </section>
          </div>
        )}
      </main>

      <style>{styles}</style>
    </div>
  );
}

// ============================================================================
// Styles
// ============================================================================

const styles = `
  .ml-lab-page {
    min-height: 100vh;
    background: #09090b;
    color: #f1f5f9;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }

  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    color: #71717a;
    font-size: 1rem;
  }

  /* Header */
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 2rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(24, 24, 27, 0.6);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .back-btn {
    background: none;
    border: none;
    color: #71717a;
    cursor: pointer;
    padding: 0.5rem;
    border-radius: 0.375rem;
    transition: all 0.15s;
  }

  .back-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #f1f5f9;
  }

  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
  }

  .subtitle {
    color: #71717a;
    font-size: 0.875rem;
  }

  .refresh-btn {
    padding: 0.5rem 1rem;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.5rem;
    color: #60a5fa;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .refresh-btn:hover:not(:disabled) {
    background: rgba(59, 130, 246, 0.25);
  }

  .refresh-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Tab Navigation */
  .tab-nav {
    display: flex;
    gap: 0.25rem;
    padding: 0.75rem 2rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(24, 24, 27, 0.3);
  }

  .tab-btn {
    padding: 0.5rem 1rem;
    background: none;
    border: none;
    color: #71717a;
    font-size: 0.875rem;
    cursor: pointer;
    border-radius: 0.375rem;
    transition: all 0.15s;
  }

  .tab-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #a1a1aa;
  }

  .tab-btn.active {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
  }

  /* Content */
  .page-content {
    padding: 2rem;
    max-width: 1400px;
    margin: 0 auto;
  }

  .error-banner {
    padding: 1rem;
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 0.5rem;
    color: #f87171;
    margin-bottom: 1.5rem;
  }

  /* Section */
  .section {
    margin-bottom: 2rem;
  }

  .section h2 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 1rem;
    color: #e4e4e7;
  }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
  }

  .section-header h2 {
    margin: 0;
  }

  /* ML Toggle */
  .ml-toggle {
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .ml-toggle.enabled {
    background: rgba(34, 197, 94, 0.15);
    border: 1px solid rgba(34, 197, 94, 0.3);
    color: #22c55e;
  }

  .ml-toggle.disabled {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #ef4444;
  }

  /* System Status */
  .system-status {
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
  }

  .system-status.status-allow {
    background: rgba(34, 197, 94, 0.1);
    border: 1px solid rgba(34, 197, 94, 0.2);
  }

  .system-status.status-rules_only {
    background: rgba(234, 179, 8, 0.1);
    border: 1px solid rgba(234, 179, 8, 0.2);
  }

  .system-status.status-block_all {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
  }

  .status-dot {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 50%;
  }

  .status-dot.allow {
    background: #22c55e;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
  }

  .status-dot.rules_only {
    background: #eab308;
    box-shadow: 0 0 8px rgba(234, 179, 8, 0.5);
  }

  .status-dot.block_all {
    background: #ef4444;
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
  }

  .triggered-list {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .triggered-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem;
    border-radius: 0.375rem;
    font-size: 0.8125rem;
  }

  .triggered-item.warning {
    background: rgba(234, 179, 8, 0.1);
  }

  .triggered-item.critical {
    background: rgba(239, 68, 68, 0.1);
  }

  .breaker-name {
    font-weight: 500;
    text-transform: capitalize;
  }

  .breaker-msg {
    color: #a1a1aa;
  }

  /* Breakers Grid */
  .breakers-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
  }

  .breaker-card {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 1rem;
  }

  .breaker-label {
    font-size: 0.75rem;
    color: #71717a;
    margin-bottom: 0.5rem;
  }

  .breaker-value {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
  }

  .breaker-value.positive {
    color: #22c55e;
  }

  .breaker-value.negative {
    color: #ef4444;
  }

  .breaker-limit {
    font-size: 0.6875rem;
    color: #52525b;
    margin-bottom: 0.5rem;
  }

  .breaker-bar {
    height: 4px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
    overflow: hidden;
  }

  .breaker-fill {
    height: 100%;
    background: #3b82f6;
    transition: width 0.3s;
  }

  .breaker-fill.positive {
    background: #22c55e;
  }

  /* Champion Card */
  .champion-card {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.5rem;
    padding: 1.25rem;
  }

  .champion-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .champion-name {
    font-size: 1.125rem;
    font-weight: 600;
  }

  .version-badge {
    padding: 0.25rem 0.5rem;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #a1a1aa;
  }

  .status-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 500;
    text-transform: uppercase;
  }

  .status-badge.champion {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .status-badge.challenger {
    background: rgba(168, 85, 247, 0.2);
    color: #a855f7;
  }

  .status-badge.training {
    background: rgba(234, 179, 8, 0.2);
    color: #eab308;
  }

  .status-badge.retired {
    background: rgba(113, 113, 122, 0.2);
    color: #71717a;
  }

  .status-badge.running {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
  }

  .status-badge.concluded {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .status-badge.aborted {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
  }

  .champion-stats {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 1rem;
  }

  .stat {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .stat-label {
    font-size: 0.6875rem;
    color: #71717a;
    text-transform: uppercase;
  }

  .stat-value {
    font-size: 0.875rem;
    font-weight: 500;
  }

  /* Chart Container */
  .chart-container {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 1rem;
  }

  /* Experiments List */
  .experiments-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .experiment-card {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 1rem;
  }

  .exp-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .exp-name {
    font-weight: 500;
  }

  .exp-stats {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .exp-arm {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 0.375rem;
  }

  .exp-arm.challenger {
    background: rgba(168, 85, 247, 0.1);
  }

  .arm-label {
    font-size: 0.6875rem;
    color: #71717a;
    text-transform: uppercase;
  }

  .arm-samples {
    font-size: 0.8125rem;
    color: #a1a1aa;
  }

  .arm-winrate {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .exp-vs {
    color: #52525b;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .exp-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 0.75rem;
    color: #71717a;
  }

  .p-value {
    font-family: 'SF Mono', monospace;
  }

  /* Data Tables */
  .models-table-container,
  .decisions-table-container,
  .performance-table-container {
    overflow-x: auto;
  }

  .data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
  }

  .data-table th {
    text-align: left;
    padding: 0.75rem;
    color: #71717a;
    font-weight: 500;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    white-space: nowrap;
  }

  .data-table td {
    padding: 0.75rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .data-table tr.highlight {
    background: rgba(59, 130, 246, 0.05);
  }

  .data-table tr:hover {
    background: rgba(255, 255, 255, 0.02);
  }

  .model-name {
    font-weight: 500;
  }

  .time-cell {
    font-size: 0.75rem;
    color: #a1a1aa;
    white-space: nowrap;
  }

  .idea-cell {
    font-family: 'SF Mono', monospace;
    font-size: 0.75rem;
  }

  .score-cell {
    font-weight: 500;
  }

  .score-cell.ml {
    color: #a855f7;
  }

  .score-cell.final {
    color: #60a5fa;
  }

  .action-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    text-transform: uppercase;
  }

  .action-badge.ranked {
    background: rgba(113, 113, 122, 0.2);
    color: #71717a;
  }

  .action-badge.presented {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .action-badge.traded {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
  }

  .action-badge.dismissed {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
  }

  .arm-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    text-transform: uppercase;
  }

  .arm-badge.champion {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
  }

  .arm-badge.challenger {
    background: rgba(168, 85, 247, 0.2);
    color: #a855f7;
  }

  .positive {
    color: #22c55e;
  }

  .negative {
    color: #ef4444;
  }

  /* Experiments Full List */
  .experiments-full-list {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .experiment-card-full {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
    padding: 1.25rem;
  }

  .experiment-card-full.running {
    border-color: rgba(34, 197, 94, 0.3);
  }

  .experiment-card-full.concluded {
    border-color: rgba(59, 130, 246, 0.3);
  }

  .exp-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .exp-meta {
    font-size: 0.75rem;
    color: #71717a;
    margin-top: 0.25rem;
  }

  .exp-description {
    font-size: 0.8125rem;
    color: #a1a1aa;
    margin: 0.75rem 0;
  }

  .exp-comparison {
    display: flex;
    align-items: stretch;
    gap: 1rem;
    margin: 1rem 0;
  }

  .comparison-arm {
    flex: 1;
    padding: 1rem;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 0.5rem;
  }

  .comparison-arm.challenger {
    background: rgba(168, 85, 247, 0.1);
  }

  .arm-header {
    font-size: 0.75rem;
    color: #71717a;
    margin-bottom: 0.75rem;
    text-transform: uppercase;
  }

  .arm-metrics {
    display: flex;
    gap: 1.5rem;
  }

  .metric {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .metric-value {
    font-size: 1.125rem;
    font-weight: 600;
  }

  .metric-label {
    font-size: 0.6875rem;
    color: #71717a;
  }

  .comparison-vs {
    display: flex;
    align-items: center;
    font-size: 0.75rem;
    font-weight: 600;
    color: #52525b;
  }

  .exp-results {
    display: flex;
    gap: 2rem;
    padding-top: 1rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  .result-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .result-label {
    font-size: 0.6875rem;
    color: #71717a;
    text-transform: uppercase;
  }

  .result-value {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .result-value.significant {
    color: #22c55e;
  }

  .result-value.winner {
    color: #60a5fa;
    text-transform: capitalize;
  }

  /* No Data */
  .no-data {
    padding: 2rem;
    text-align: center;
    color: #71717a;
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.5rem;
  }

  /* Responsive */
  @media (max-width: 1200px) {
    .breakers-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .champion-stats {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (max-width: 768px) {
    .page-content {
      padding: 1rem;
    }

    .breakers-grid {
      grid-template-columns: 1fr;
    }

    .champion-stats {
      grid-template-columns: repeat(2, 1fr);
    }

    .exp-comparison {
      flex-direction: column;
    }

    .comparison-vs {
      justify-content: center;
      padding: 0.5rem 0;
    }
  }

  /* ML Stats Summary */
  .stats-summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .stat-card {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 1.25rem;
    text-align: center;
  }

  .stat-card .stat-value {
    font-size: 1.75rem;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 0.25rem;
  }

  .stat-card .stat-label {
    font-size: 0.75rem;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* Comparison Grid */
  .comparison-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 0.75rem;
  }

  .comparison-item {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 1rem;
    text-align: center;
  }

  .comparison-item.negative {
    border-color: rgba(239, 68, 68, 0.3);
    background: rgba(239, 68, 68, 0.1);
  }

  .comparison-item.warning {
    border-color: rgba(249, 115, 22, 0.3);
    background: rgba(249, 115, 22, 0.1);
  }

  .comparison-item.neutral {
    border-color: rgba(161, 161, 170, 0.3);
    background: rgba(161, 161, 170, 0.1);
  }

  .comparison-item.positive-light {
    border-color: rgba(34, 197, 94, 0.3);
    background: rgba(34, 197, 94, 0.1);
  }

  .comparison-item.positive {
    border-color: rgba(16, 185, 129, 0.3);
    background: rgba(16, 185, 129, 0.15);
  }

  .comparison-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: #f1f5f9;
  }

  .comparison-label {
    font-size: 0.7rem;
    color: #9ca3af;
    margin-top: 0.25rem;
  }

  .comparison-pct {
    font-size: 0.875rem;
    color: #71717a;
    margin-top: 0.5rem;
    font-weight: 500;
  }

  @media (max-width: 900px) {
    .stats-summary {
      grid-template-columns: repeat(2, 1fr);
    }
    .comparison-grid {
      grid-template-columns: repeat(3, 1fr);
    }
  }

  @media (max-width: 600px) {
    .comparison-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
`;
