// ui/src/pages/AdminDoctrine.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useDoctrinePlaybooks,
  useDoctrineTerms,
  useDoctrineHealth,
  useValidationLog,
  useKillSwitch,
  toggleKillSwitch,
  updateLPDConfig,
  updateValidatorConfig,
  updateThresholds,
  useDoctrinePatterns,
  useDoctrinePatternMetrics,
  useDoctrineOverlays,
  suppressUserOverlay,
  type DoctrinePlaybookSummary,
  type KillSwitchState,
  type ValidationLogEntry,
  type PatternAlert,
  type OverlayRecord,
} from "../hooks/useDoctrine";

type TabType =
  | "health"
  | "playbooks"
  | "terms"
  | "validator"
  | "lpd"
  | "thresholds"
  | "kill-switch"
  | "validation-log"
  | "patterns"
  | "overlays";

export default function AdminDoctrinePage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>("health");

  return (
    <div className="doctrine-page">
      <div className="doctrine-container">
        {/* Header */}
        <div className="doctrine-header">
          <div className="header-left">
            <button className="back-btn" onClick={() => navigate("/admin")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Admin
            </button>
            <h1>Doctrine Governance</h1>
            <span className="aol-badge">AOL v2.0</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="tab-nav">
          {(
            [
              { id: "health", label: "Health" },
              { id: "playbooks", label: "Playbooks" },
              { id: "terms", label: "Terms" },
              { id: "validator", label: "Validator" },
              { id: "lpd", label: "LPD Config" },
              { id: "thresholds", label: "Thresholds" },
              { id: "kill-switch", label: "Kill Switch" },
              { id: "validation-log", label: "Validation Log" },
              { id: "patterns", label: "Patterns" },
              { id: "overlays", label: "Overlays" },
            ] as { id: TabType; label: string }[]
          ).map((tab) => (
            <button
              key={tab.id}
              className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="tab-content">
          {activeTab === "health" && <HealthPanel />}
          {activeTab === "playbooks" && <PlaybooksPanel />}
          {activeTab === "terms" && <TermsPanel />}
          {activeTab === "validator" && <ValidatorPanel />}
          {activeTab === "lpd" && <LPDPanel />}
          {activeTab === "thresholds" && <ThresholdsPanel />}
          {activeTab === "kill-switch" && <KillSwitchPanel />}
          {activeTab === "validation-log" && <ValidationLogPanel />}
          {activeTab === "patterns" && <PatternsPanel />}
          {activeTab === "overlays" && <OverlaysPanel />}
        </div>
      </div>
      <style>{styles}</style>
    </div>
  );
}

// =====================================================================
// PANELS
// =====================================================================

function HealthPanel() {
  const { data, loading, error, refetch } = useDoctrineHealth();
  if (loading) return <div className="panel-loading">Loading health...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const h = data.health;
  const reg = h.registry as Record<string, unknown>;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Doctrine Health</h2>
        <button className="refresh-btn" onClick={refetch}>Refresh</button>
      </div>

      {/* Registry Status */}
      <div className="health-section">
        <h3>Playbook Registry</h3>
        <div className="health-grid">
          <HealthItem
            label="Synchronized"
            value={reg.synchronized ? "Yes" : "No"}
            status={reg.synchronized ? "ok" : "error"}
          />
          <HealthItem
            label="Safe Mode"
            value={reg.safe_mode ? "ACTIVE" : "Off"}
            status={reg.safe_mode ? "error" : "ok"}
          />
          <HealthItem
            label="Playbooks Loaded"
            value={String(reg.playbook_count ?? 0)}
            status="ok"
          />
          <HealthItem
            label="Canonical Terms"
            value={String(reg.term_count ?? 0)}
            status="ok"
          />
        </div>
      </div>

      {/* Kill Switch Status */}
      <div className="health-section">
        <h3>Kill Switch</h3>
        <div className="health-grid">
          {(["pde", "overlay", "rv", "lpd"] as const).map((k) => {
            const key = `${k}_enabled` as keyof typeof h.kill_switch;
            const enabled = h.kill_switch[key];
            return (
              <HealthItem
                key={k}
                label={k.toUpperCase()}
                value={enabled ? "Enabled" : "DISABLED"}
                status={enabled ? "ok" : "warn"}
              />
            );
          })}
        </div>
      </div>

      {/* PDE / AOS */}
      <div className="health-section">
        <h3>Background Systems</h3>
        <div className="health-grid">
          <HealthItem label="PDE" value={h.pde.status} status={h.pde.auto_disabled ? "error" : "info"} />
          <HealthItem label="AOS" value={h.aos.status} status="info" />
          <HealthItem label="Active Overlays" value={String(h.aos.active_overlays)} status="info" />
        </div>
      </div>
    </div>
  );
}

function HealthItem({ label, value, status }: { label: string; value: string; status: string }) {
  return (
    <div className="health-item">
      <span className={`health-dot ${status}`} />
      <div>
        <div className="health-label">{label}</div>
        <div className={`health-value ${status}`}>{value}</div>
      </div>
    </div>
  );
}

function PlaybooksPanel() {
  const { data, loading, error } = useDoctrinePlaybooks();
  const [expanded, setExpanded] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading playbooks...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Doctrine Playbooks</h2>
        <div className="panel-badges">
          <span className={`sync-badge ${data.synchronized ? "synced" : "stale"}`}>
            {data.synchronized ? "Synchronized" : "Out of Sync"}
          </span>
          {data.safe_mode && <span className="safe-mode-badge">SAFE MODE</span>}
          <span className="count-badge">{data.count} playbooks</span>
        </div>
      </div>
      <p className="panel-desc">
        Immutable doctrine playbooks derived from PathRuntime. Changes require version bump + service restart + deployment.
      </p>
      <div className="playbook-list">
        {data.playbooks.map((pb: DoctrinePlaybookSummary) => (
          <div
            key={pb.domain}
            className={`playbook-card ${expanded === pb.domain ? "expanded" : ""}`}
            onClick={() => setExpanded(expanded === pb.domain ? null : pb.domain)}
          >
            <div className="playbook-header">
              <span className="playbook-domain">{pb.domain.replace(/_/g, " ")}</span>
              <span className="playbook-version">v{pb.version}</span>
              <span className="playbook-terms">{pb.term_count} terms</span>
              <span className="playbook-constraints">{pb.constraint_count} constraints</span>
            </div>
            {expanded === pb.domain && (
              <div className="playbook-detail">
                <div className="detail-row">
                  <span className="label">Source</span>
                  <span className="value">{pb.doctrine_source}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Runtime Version</span>
                  <span className="value">{pb.path_runtime_version}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Runtime Hash</span>
                  <span className="value mono">{pb.path_runtime_hash}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Generated</span>
                  <span className="value">{new Date(pb.generated_at).toLocaleString()}</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TermsPanel() {
  const { data, loading, error } = useDoctrineTerms();
  const [search, setSearch] = useState("");

  if (loading) return <div className="panel-loading">Loading terms...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const entries = Object.entries(data.terms).filter(
    ([term, def]) =>
      term.toLowerCase().includes(search.toLowerCase()) ||
      def.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Canonical Terms</h2>
        <span className="count-badge">{data.count} terms</span>
      </div>
      <p className="panel-desc">
        Canonical terminology dictionary. Read-only — changes require playbook regeneration.
      </p>
      <div className="search-box">
        <input
          type="text"
          placeholder="Search terms..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <div className="terms-list">
        {entries.map(([term, definition]) => (
          <div key={term} className="term-item">
            <div className="term-name">{term}</div>
            <div className="term-def">{definition}</div>
          </div>
        ))}
        {entries.length === 0 && <div className="no-results">No matching terms</div>}
      </div>
    </div>
  );
}

function ValidatorPanel() {
  const { data, loading, error, refetch } = useDoctrineHealth();
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const config = data.health.governance.validator_config as Record<string, unknown>;

  const handleUpdate = async (key: string, value: unknown) => {
    setSaving(true);
    try {
      await updateValidatorConfig({ [key]: value });
      setMsg("Updated");
      setTimeout(() => setMsg(null), 2000);
      refetch();
    } catch {
      setMsg("Error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Response Validator Config</h2>
        {msg && <span className="save-msg">{msg}</span>}
      </div>
      <p className="panel-desc">
        Strictness toggles for the post-LLM response validator. Only governance parameters are mutable.
      </p>
      <div className="config-grid">
        <ConfigSelect
          label="Strictness"
          value={String(config.strictness)}
          options={["relaxed", "normal", "strict"]}
          onChange={(v) => handleUpdate("strictness", v)}
          disabled={saving}
        />
        <ConfigNumber
          label="Max Regeneration Attempts"
          value={Number(config.max_regeneration_attempts)}
          onChange={(v) => handleUpdate("max_regeneration_attempts", v)}
          disabled={saving}
          min={0}
          max={3}
        />
        <ConfigToggle
          label="Log Soft Warnings"
          value={Boolean(config.log_soft_warnings)}
          onChange={(v) => handleUpdate("log_soft_warnings", v)}
          disabled={saving}
        />
      </div>
    </div>
  );
}

function LPDPanel() {
  const { data, loading, error, refetch } = useDoctrineHealth();
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const config = data.health.governance.lpd_config;

  const handleUpdate = async (key: string, value: number) => {
    setSaving(true);
    try {
      await updateLPDConfig({ [key]: value });
      setMsg("Updated");
      setTimeout(() => setMsg(null), 2000);
      refetch();
    } catch {
      setMsg("Error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>LPD Classification Config</h2>
        {msg && <span className="save-msg">{msg}</span>}
      </div>
      <p className="panel-desc">
        Language Pattern Detector thresholds for domain classification routing.
      </p>
      <div className="config-grid">
        <ConfigNumber
          label="Confidence Threshold"
          value={config.confidence_threshold}
          onChange={(v) => handleUpdate("confidence_threshold", v)}
          disabled={saving}
          min={0}
          max={1}
          step={0.05}
        />
        <ConfigNumber
          label="Hybrid Margin"
          value={config.hybrid_margin}
          onChange={(v) => handleUpdate("hybrid_margin", v)}
          disabled={saving}
          min={0}
          max={1}
          step={0.05}
        />
      </div>
    </div>
  );
}

function ThresholdsPanel() {
  const { data, loading, error, refetch } = useDoctrineHealth();
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const thresholds = data.health.governance.thresholds;

  const handleUpdate = async (key: string, value: number) => {
    setSaving(true);
    try {
      await updateThresholds({ [key]: value });
      setMsg("Updated");
      setTimeout(() => setMsg(null), 2000);
      refetch();
    } catch {
      setMsg("Error");
    } finally {
      setSaving(false);
    }
  };

  const labels: Record<string, string> = {
    pde_scan_interval_sec: "PDE Scan Interval (sec)",
    overlay_ttl_hours: "Overlay TTL (hours)",
    overlay_max_per_week: "Max Overlays Per Week",
    overlay_cooldown_hours: "Overlay Cooldown (hours)",
    overlay_min_confidence: "Min Overlay Confidence",
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Governance Thresholds</h2>
        {msg && <span className="save-msg">{msg}</span>}
      </div>
      <p className="panel-desc">
        PDE scan intervals, overlay budgets, and cooldown timers.
      </p>
      <div className="config-grid">
        {Object.entries(thresholds).map(([key, val]) => (
          <ConfigNumber
            key={key}
            label={labels[key] || key}
            value={val}
            onChange={(v) => handleUpdate(key, v)}
            disabled={saving}
            min={0}
            step={key.includes("confidence") ? 0.05 : 1}
          />
        ))}
      </div>
    </div>
  );
}

function KillSwitchPanel() {
  const { data, loading, error, refetch } = useKillSwitch();
  const [toggling, setToggling] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const ks = data.kill_switch;

  const handleToggle = async (subsystem: string, current: boolean) => {
    if (!confirm(`${current ? "Disable" : "Enable"} ${subsystem.toUpperCase()}?`)) return;
    setToggling(subsystem);
    try {
      await toggleKillSwitch(subsystem, !current);
      refetch();
    } finally {
      setToggling(null);
    }
  };

  const switches: { key: keyof KillSwitchState; label: string; subsystem: string; desc: string }[] = [
    { key: "pde_enabled", label: "Pattern Detection", subsystem: "pde", desc: "Behavioral drift scanning from Edge Lab data" },
    { key: "overlay_enabled", label: "Admin Overlays", subsystem: "overlay", desc: "Observational signals appended to responses" },
    { key: "rv_enabled", label: "Response Validator", subsystem: "rv", desc: "Post-LLM doctrine compliance validation" },
    { key: "lpd_enabled", label: "Language Pattern Detection", subsystem: "lpd", desc: "Domain classification routing" },
  ];

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Kill Switch</h2>
      </div>
      <p className="panel-desc">
        Toggle subsystems on/off. All toggles are logged with timestamp and admin user.
      </p>
      {ks.last_toggled_by && (
        <div className="last-toggle">
          Last toggled by <strong>{ks.last_toggled_by}</strong>
          {ks.last_toggled_at && <> at {new Date(ks.last_toggled_at * 1000).toLocaleString()}</>}
        </div>
      )}
      <div className="kill-switch-list">
        {switches.map(({ key, label, subsystem, desc }) => {
          const enabled = ks[key] as boolean;
          return (
            <div key={subsystem} className={`kill-switch-item ${enabled ? "enabled" : "disabled"}`}>
              <div className="ks-info">
                <div className="ks-label">{label}</div>
                <div className="ks-desc">{desc}</div>
              </div>
              <button
                className={`ks-toggle ${enabled ? "on" : "off"}`}
                onClick={() => handleToggle(subsystem, enabled)}
                disabled={toggling === subsystem}
              >
                {toggling === subsystem ? "..." : enabled ? "ON" : "OFF"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ValidationLogPanel() {
  const { data, loading, error, refetch } = useValidationLog();

  if (loading) return <div className="panel-loading">Loading...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const entries = data.entries as ValidationLogEntry[];

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Validation Log</h2>
        <button className="refresh-btn" onClick={refetch}>Refresh</button>
      </div>
      <p className="panel-desc">Recent response validation events (hard blocks + soft warnings).</p>
      {entries.length === 0 ? (
        <div className="no-results">No validation events logged yet</div>
      ) : (
        <div className="log-table-wrapper">
          <table className="log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Mode</th>
                <th>Domain</th>
                <th>Hard</th>
                <th>Soft</th>
                <th>Regen</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i}>
                  <td className="mono">{new Date(e.ts * 1000).toLocaleTimeString()}</td>
                  <td>{e.user_id}</td>
                  <td>
                    <span className={`mode-badge ${e.doctrine_mode}`}>{e.doctrine_mode}</span>
                  </td>
                  <td>{e.domain}</td>
                  <td className={e.hard_violations.length > 0 ? "hard" : ""}>
                    {e.hard_violations.length > 0 ? e.hard_violations.join(", ") : "-"}
                  </td>
                  <td className={e.soft_warnings.length > 0 ? "soft" : ""}>
                    {e.soft_warnings.length > 0 ? e.soft_warnings.join(", ") : "-"}
                  </td>
                  <td>{e.regenerated ? "Yes" : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PatternsPanel() {
  const { data: pData, loading: pLoading, error: pError, refetch: pRefetch } = useDoctrinePatterns();
  const { data: mData, loading: mLoading, error: mError, refetch: mRefetch } = useDoctrinePatternMetrics();

  const loading = pLoading || mLoading;
  const error = pError || mError;

  if (loading) return <div className="panel-loading">Loading patterns...</div>;
  if (error) return <div className="panel-error">{error}</div>;

  const health = (pData?.health || {}) as Record<string, unknown>;
  const patterns = (pData?.patterns || []) as PatternAlert[];
  const scan = mData?.scan;
  const metrics = (mData?.metrics || {}) as Record<string, unknown>;

  const refetch = () => { pRefetch(); mRefetch(); };

  const categoryColors: Record<string, string> = {
    execution_drift: "#f59e0b",
    bias_interference: "#ef4444",
    regime_mismatch: "#8b5cf6",
    overtrading_after_loss: "#f87171",
    edge_score_decay: "#60a5fa",
    entropy_collapse: "#22c55e",
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Pattern Detection Engine</h2>
        <button className="refresh-btn" onClick={refetch}>Refresh</button>
      </div>

      {/* Health Card */}
      <div className="health-section">
        <h3>PDE Health</h3>
        <div className="health-grid">
          <HealthItem
            label="Status"
            value={health.auto_disabled ? "AUTO-DISABLED" : "Active"}
            status={health.auto_disabled ? "error" : "ok"}
          />
          <HealthItem
            label="Total Scans"
            value={String(metrics.total_scans ?? 0)}
            status="info"
          />
          <HealthItem
            label="Total Failures"
            value={String(metrics.total_failures ?? 0)}
            status={(metrics.total_failures as number) > 0 ? "warn" : "ok"}
          />
          <HealthItem
            label="Consecutive Failures"
            value={String(metrics.consecutive_failures ?? 0)}
            status={(metrics.consecutive_failures as number) > 0 ? "warn" : "ok"}
          />
        </div>
      </div>

      {/* Scan Activity */}
      {scan && (
        <div className="health-section">
          <h3>Last Scan Cycle</h3>
          <div className="health-grid">
            <HealthItem
              label="Last Scan"
              value={scan.last_scan_ts ? new Date(scan.last_scan_ts * 1000).toLocaleTimeString() : "Never"}
              status={scan.last_scan_ts ? "ok" : "warn"}
            />
            <HealthItem label="Users Scanned" value={String(scan.last_scan_users)} status="info" />
            <HealthItem label="Alerts Generated" value={String(scan.last_scan_alerts)} status={scan.last_scan_alerts > 0 ? "warn" : "info"} />
            <HealthItem label="Latency" value={`${scan.last_scan_latency_ms}ms`} status="info" />
            <HealthItem label="Total Users" value={String(scan.last_scan_users_total)} status="info" />
            <HealthItem label="Batch Size" value={String(scan.last_scan_batch_size)} status="info" />
            <HealthItem label="Running" value={scan.scan_running ? "Yes" : "No"} status={scan.scan_running ? "warn" : "ok"} />
          </div>
        </div>
      )}

      {/* Alerts Table */}
      <div className="health-section">
        <h3>Recent Alerts ({patterns.length})</h3>
        {patterns.length === 0 ? (
          <div className="no-results">No pattern alerts detected yet</div>
        ) : (
          <div className="log-table-wrapper">
            <table className="log-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Category</th>
                  <th>Confidence</th>
                  <th>Samples</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {patterns.map((a, i) => (
                  <tr key={i}>
                    <td className="mono">{new Date(a.ts * 1000).toLocaleTimeString()}</td>
                    <td>{a.user_id}</td>
                    <td>
                      <span
                        className="mode-badge"
                        style={{ background: `${categoryColors[a.category] || "#888"}22`, color: categoryColors[a.category] || "#888" }}
                      >
                        {a.category.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td>
                      <div className="confidence-bar">
                        <div className="confidence-fill" style={{ width: `${Math.round(a.confidence * 100)}%` }} />
                        <span>{(a.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td>{a.sample_size}</td>
                    <td className="summary-cell">{a.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function OverlaysPanel() {
  const { data, loading, error, refetch } = useDoctrineOverlays();
  const [suppressing, setSuppressing] = useState<number | null>(null);

  if (loading) return <div className="panel-loading">Loading overlays...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const overlays = data.overlays as OverlayRecord[];
  const stats = data.stats;

  const handleSuppress = async (userId: number) => {
    if (!confirm(`Suppress overlays for user ${userId}?`)) return;
    setSuppressing(userId);
    try {
      await suppressUserOverlay(userId);
      refetch();
    } finally {
      setSuppressing(null);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Admin Overlays</h2>
        <button className="refresh-btn" onClick={refetch}>Refresh</button>
      </div>

      {/* AOS Stats */}
      <div className="health-section">
        <h3>AOS Status</h3>
        <div className="health-grid">
          <HealthItem label="Active Overlays" value={String(stats.active_overlays)} status={stats.active_overlays > 0 ? "warn" : "ok"} />
          <HealthItem label="Suppressed Users" value={String(stats.suppressed_users)} status={stats.suppressed_users > 0 ? "info" : "ok"} />
          <HealthItem label="Active Cooldowns" value={String(stats.active_cooldowns)} status="info" />
        </div>
      </div>

      {/* Overlay Cards */}
      <div className="health-section">
        <h3>Active Overlays ({overlays.length})</h3>
        {overlays.length === 0 ? (
          <div className="no-results">No active overlays</div>
        ) : (
          <div className="overlay-list">
            {overlays.map((o, i) => {
              const expiresIn = Math.max(0, o.expires_at - Date.now() / 1000);
              const hoursLeft = Math.floor(expiresIn / 3600);
              const minsLeft = Math.floor((expiresIn % 3600) / 60);
              return (
                <div key={i} className="overlay-card">
                  <div className="overlay-top">
                    <span className="overlay-user">User {o.user_id}</span>
                    <span className="mode-badge" style={{ background: "rgba(245, 158, 11, 0.15)", color: "#f59e0b" }}>
                      {o.category.replace(/_/g, " ")}
                    </span>
                    <span className="overlay-expires">
                      {hoursLeft}h {minsLeft}m left
                    </span>
                  </div>
                  <div className="overlay-label">{o.label}</div>
                  <div className="overlay-summary">{o.summary}</div>
                  <div className="overlay-bottom">
                    <span className="overlay-confidence">
                      Confidence: {(o.confidence * 100).toFixed(0)}%
                    </span>
                    <button
                      className="suppress-btn"
                      onClick={() => handleSuppress(o.user_id)}
                      disabled={suppressing === o.user_id}
                    >
                      {suppressing === o.user_id ? "..." : "Suppress"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// CONFIG CONTROLS
// =====================================================================

function ConfigNumber({
  label, value, onChange, disabled, min, max, step,
}: {
  label: string; value: number; onChange: (v: number) => void;
  disabled: boolean; min?: number; max?: number; step?: number;
}) {
  return (
    <div className="config-item">
      <label>{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        min={min}
        max={max}
        step={step}
      />
    </div>
  );
}

function ConfigSelect({
  label, value, options, onChange, disabled,
}: {
  label: string; value: string; options: string[];
  onChange: (v: string) => void; disabled: boolean;
}) {
  return (
    <div className="config-item">
      <label>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}

function ConfigToggle({
  label, value, onChange, disabled,
}: {
  label: string; value: boolean; onChange: (v: boolean) => void; disabled: boolean;
}) {
  return (
    <div className="config-item">
      <label>{label}</label>
      <button
        className={`toggle-btn ${value ? "on" : "off"}`}
        onClick={() => onChange(!value)}
        disabled={disabled}
      >
        {value ? "ON" : "OFF"}
      </button>
    </div>
  );
}

// =====================================================================
// STYLES
// =====================================================================

const styles = `
  .doctrine-page {
    min-height: 100vh;
    background: var(--bg-base);
    color: var(--text-primary);
    padding: 1.5rem;
  }

  .doctrine-container {
    max-width: 1400px;
    margin: 0 auto;
  }

  .doctrine-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .doctrine-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    background: linear-gradient(135deg, #f59e0b, #ef4444);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .aol-badge {
    font-size: 0.625rem;
    padding: 0.25rem 0.5rem;
    background: rgba(245, 158, 11, 0.15);
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 0.25rem;
    color: #f59e0b;
    font-weight: 600;
    letter-spacing: 0.05em;
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: var(--bg-hover);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .back-btn:hover { color: var(--text-bright); }
  .back-btn svg { width: 1rem; height: 1rem; }

  /* Tab Nav */
  .tab-nav {
    display: flex;
    gap: 0.25rem;
    padding: 0.25rem;
    background: var(--bg-surface-alt);
    border-radius: 0.5rem;
    margin-bottom: 1.5rem;
    overflow-x: auto;
    flex-wrap: wrap;
  }

  .tab-btn {
    padding: 0.5rem 0.75rem;
    background: none;
    border: none;
    border-radius: 0.375rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .tab-btn:hover { color: var(--text-primary); }
  .tab-btn.active {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* Panels */
  .tab-content {
    min-height: 400px;
  }

  .panel {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
    padding: 1.25rem;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .panel-header h2 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
  }

  .panel-badges {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }

  .panel-desc {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    margin: 0 0 1.25rem;
    line-height: 1.5;
  }

  .panel-loading, .panel-error {
    padding: 3rem;
    text-align: center;
    color: var(--text-secondary);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: 0.75rem;
  }

  .panel-error { color: #f87171; }

  .refresh-btn {
    padding: 0.375rem 0.75rem;
    background: rgba(59, 130, 246, 0.15);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 0.375rem;
    color: #60a5fa;
    font-size: 0.75rem;
    cursor: pointer;
  }

  .refresh-btn:hover { background: rgba(59, 130, 246, 0.25); }

  /* Badges */
  .sync-badge {
    font-size: 0.6875rem;
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-weight: 500;
  }

  .sync-badge.synced { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
  .sync-badge.stale { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

  .safe-mode-badge {
    font-size: 0.6875rem;
    padding: 0.25rem 0.5rem;
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid rgba(239, 68, 68, 0.4);
    border-radius: 0.25rem;
    color: #f87171;
    font-weight: 600;
    animation: pulse 2s infinite;
  }

  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

  .count-badge {
    font-size: 0.6875rem;
    padding: 0.25rem 0.5rem;
    background: var(--bg-hover);
    border-radius: 0.25rem;
    color: var(--text-secondary);
  }

  /* Health Grid */
  .health-section {
    margin-bottom: 1.25rem;
  }

  .health-section h3 {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 0.75rem;
  }

  .health-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.75rem;
  }

  .health-item {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.5rem;
  }

  .health-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    margin-top: 0.25rem;
    flex-shrink: 0;
  }

  .health-dot.ok { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
  .health-dot.error { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); }
  .health-dot.warn { background: #f59e0b; box-shadow: 0 0 6px rgba(245, 158, 11, 0.5); }
  .health-dot.info { background: #60a5fa; }

  .health-label { font-size: 0.6875rem; color: var(--text-secondary); }
  .health-value { font-size: 0.875rem; font-weight: 600; color: var(--text-primary); }
  .health-value.error { color: #f87171; }
  .health-value.warn { color: #f59e0b; }

  /* Playbook List */
  .playbook-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .playbook-card {
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    padding: 0.875rem 1rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .playbook-card:hover { border-color: rgba(124, 58, 237, 0.3); }
  .playbook-card.expanded { border-color: rgba(124, 58, 237, 0.4); }

  .playbook-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .playbook-domain {
    flex: 1;
    font-weight: 600;
    text-transform: capitalize;
    color: var(--text-primary);
  }

  .playbook-version {
    font-size: 0.6875rem;
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }

  .playbook-terms, .playbook-constraints {
    font-size: 0.6875rem;
    color: var(--text-secondary);
  }

  .playbook-detail {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
  }

  .detail-row {
    display: flex;
    justify-content: space-between;
    padding: 0.375rem 0;
    font-size: 0.8125rem;
  }

  .detail-row .label { color: var(--text-secondary); }
  .detail-row .value { color: var(--text-primary); text-align: right; }
  .detail-row .value.mono { font-family: 'SF Mono', monospace; font-size: 0.75rem; }

  /* Terms */
  .search-box {
    margin-bottom: 1rem;
  }

  .search-box input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-primary);
    font-size: 0.875rem;
  }

  .search-box input:focus { outline: none; border-color: rgba(59, 130, 246, 0.5); }

  .terms-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 600px;
    overflow-y: auto;
  }

  .term-item {
    padding: 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.5rem;
  }

  .term-name {
    font-weight: 600;
    font-size: 0.875rem;
    color: #c4b5fd;
    margin-bottom: 0.25rem;
  }

  .term-def {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .no-results {
    padding: 2rem;
    text-align: center;
    color: var(--text-muted);
  }

  /* Config Grid */
  .config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }

  .config-item {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .config-item label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .config-item input,
  .config-item select {
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.875rem;
  }

  .config-item input:focus,
  .config-item select:focus {
    outline: none;
    border-color: rgba(59, 130, 246, 0.5);
  }

  .config-item input:disabled,
  .config-item select:disabled { opacity: 0.5; }

  .toggle-btn {
    padding: 0.5rem 1rem;
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }

  .toggle-btn.on {
    background: rgba(34, 197, 94, 0.15);
    border-color: rgba(34, 197, 94, 0.3);
    color: #22c55e;
  }

  .toggle-btn.off {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.3);
    color: #f87171;
  }

  .toggle-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .save-msg {
    font-size: 0.75rem;
    color: #22c55e;
    background: rgba(34, 197, 94, 0.1);
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
  }

  /* Kill Switch */
  .last-toggle {
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: 1rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
  }

  .kill-switch-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .kill-switch-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    transition: all 0.15s;
  }

  .kill-switch-item.disabled {
    border-color: rgba(239, 68, 68, 0.2);
    background: rgba(239, 68, 68, 0.05);
  }

  .ks-info { flex: 1; }
  .ks-label { font-weight: 600; font-size: 0.875rem; margin-bottom: 0.25rem; }
  .ks-desc { font-size: 0.75rem; color: var(--text-secondary); }

  .ks-toggle {
    padding: 0.5rem 1.5rem;
    border-radius: 0.5rem;
    font-weight: 700;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.15s;
    min-width: 70px;
  }

  .ks-toggle.on {
    background: rgba(34, 197, 94, 0.2);
    border: 1px solid rgba(34, 197, 94, 0.4);
    color: #22c55e;
  }

  .ks-toggle.off {
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid rgba(239, 68, 68, 0.4);
    color: #ef4444;
  }

  .ks-toggle:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Validation Log Table */
  .log-table-wrapper {
    overflow-x: auto;
  }

  .log-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
  }

  .log-table th {
    text-align: left;
    padding: 0.625rem 0.75rem;
    background: var(--bg-surface-alt);
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border-subtle);
  }

  .log-table td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary);
  }

  .log-table td.hard { color: #f87171; font-weight: 500; }
  .log-table td.soft { color: #f59e0b; }
  .log-table td.mono { font-family: 'SF Mono', monospace; font-size: 0.75rem; }

  .mode-badge {
    display: inline-block;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 500;
  }

  .mode-badge.strict { background: rgba(239, 68, 68, 0.15); color: #f87171; }
  .mode-badge.hybrid { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
  .mode-badge.reflective { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }

  /* Confidence Bar */
  .confidence-bar {
    position: relative;
    width: 80px;
    height: 18px;
    background: var(--bg-surface-alt);
    border-radius: 0.25rem;
    overflow: hidden;
    display: inline-flex;
    align-items: center;
  }

  .confidence-fill {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    background: rgba(245, 158, 11, 0.3);
    border-radius: 0.25rem;
  }

  .confidence-bar span {
    position: relative;
    font-size: 0.6875rem;
    font-weight: 600;
    padding-left: 0.375rem;
    color: var(--text-primary);
  }

  .summary-cell {
    max-width: 300px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* Overlay Cards */
  .overlay-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .overlay-card {
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    padding: 1rem;
  }

  .overlay-top {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .overlay-user {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--text-primary);
  }

  .overlay-expires {
    margin-left: auto;
    font-size: 0.6875rem;
    color: var(--text-secondary);
    background: var(--bg-hover);
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
  }

  .overlay-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
  }

  .overlay-summary {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    line-height: 1.4;
    margin-bottom: 0.75rem;
  }

  .overlay-bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .overlay-confidence {
    font-size: 0.75rem;
    color: var(--text-secondary);
  }

  .suppress-btn {
    padding: 0.25rem 0.75rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 0.375rem;
    color: #f87171;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .suppress-btn:hover { background: rgba(239, 68, 68, 0.2); }
  .suppress-btn:disabled { opacity: 0.5; cursor: not-allowed; }
`;
