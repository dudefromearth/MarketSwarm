// ui/src/pages/AdminDoctrine.tsx
import { useState, useCallback } from "react";
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
  usePlaybookFull,
  updatePlaybookField,
  clearPlaybookOverrides,
  regeneratePlaybooks,
  useRoutingMap,
  updateRoutingPatterns,
  updatePlaybookMap,
  testClassification,
  useTermRegistry,
  createTerm,
  updateTermRegistry,
  deleteTerm,
  type DoctrinePlaybookSummary,
  type KillSwitchState,
  type ValidationLogEntry,
  type PatternAlert,
  type OverlayRecord,
  type AnnotatedTerm,
  type AnnotatedListItem,
  type ClassificationTestResult,
  type TermRegistryEntry,
} from "../hooks/useDoctrine";

type TabType =
  | "health"
  | "playbooks"
  | "terms"
  | "routing"
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
              { id: "routing", label: "Routing" },
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
          {activeTab === "routing" && <RoutingPanel />}
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
            value={reg.doctrine_synchronized ? "Yes" : "No"}
            status={reg.doctrine_synchronized ? "ok" : "error"}
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

        {/* Safe Mode Diagnostic */}
        {reg.safe_mode && (
          <div className="diagnostic-box error">
            <div className="diagnostic-title">Playbook Desync Detected</div>
            <div className="diagnostic-body">
              <p>
                One or more playbooks were generated against a different version of the Path doctrine
                than what is currently loaded. While in safe mode, domain-specific playbook guidance
                is disabled — responses use core doctrine only.
              </p>
              {Array.isArray(reg.mismatch_details) && (reg.mismatch_details as string[]).length > 0 && (
                <div className="diagnostic-details">
                  <div className="diagnostic-label">Mismatched files:</div>
                  <ul>
                    {(reg.mismatch_details as string[]).map((d, i) => (
                      <li key={i} className="mono">{d}</li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="diagnostic-fix">
                <div className="diagnostic-label">To fix:</div>
                <p>Regenerate playbooks from the current PathRuntime. Admin overrides will be preserved and re-applied.</p>
                <RegenerateButton onDone={refetch} />
              </div>
            </div>
          </div>
        )}

        {/* Per-Playbook Hash Status */}
        {reg.playbooks && (
          <div className="playbook-health-list">
            {Object.entries(reg.playbooks as Record<string, { version: string; generated_at: string; hash: string }>).map(
              ([domain, pb]) => {
                const allHashes = Object.values(reg.playbooks as Record<string, { hash: string }>).map((p) => p.hash);
                const commonHash = allHashes.sort((a, b) => allHashes.filter((h) => h === b).length - allHashes.filter((h) => h === a).length)[0];
                const isMatch = pb.hash === commonHash;
                return (
                  <div key={domain} className={`playbook-health-row ${isMatch ? "" : "mismatch"}`}>
                    <span className={`health-dot ${isMatch ? "ok" : "error"}`} />
                    <span className="playbook-health-domain">{domain.replace(/_/g, " ")}</span>
                    <span className="playbook-health-version">v{pb.version}</span>
                    <span className="playbook-health-hash mono">{pb.hash}</span>
                    <span className="playbook-health-date">
                      {new Date(pb.generated_at).toLocaleDateString()}
                    </span>
                  </div>
                );
              }
            )}
          </div>
        )}
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

function RegenerateButton({ onDone }: { onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleRegenerate = async () => {
    if (!confirm("Regenerate all 8 playbooks from the current Path doctrine? Admin overrides will be preserved and re-applied.")) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await regeneratePlaybooks();
      if (res.success) {
        setResult(`Regenerated ${res.regenerated_count} playbooks. Hash: ${res.new_hash?.slice(0, 16)}...`);
        onDone?.();
      } else {
        setResult(`Error: ${res.error}`);
      }
    } catch (e) {
      setResult("Regeneration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <button className="refresh-btn" onClick={handleRegenerate} disabled={busy} style={{ padding: "0.5rem 1rem" }}>
        {busy ? "Regenerating..." : "Regenerate Playbooks"}
      </button>
      {result && <span className="save-msg" style={{ marginLeft: "0.5rem" }}>{result}</span>}
    </div>
  );
}

function PlaybooksPanel() {
  const { data, loading, error, refetch: refetchList } = useDoctrinePlaybooks();
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const { data: fullData, loading: fullLoading, refetch: refetchFull } = usePlaybookFull(selectedDomain);
  const [viewMode, setViewMode] = useState<"merged" | "changes">("merged");
  const [msg, setMsg] = useState<string | null>(null);

  // Inline editing state
  const [addingTerm, setAddingTerm] = useState(false);
  const [newTermName, setNewTermName] = useState("");
  const [newTermDef, setNewTermDef] = useState("");
  const [addingField, setAddingField] = useState<string | null>(null);
  const [newFieldText, setNewFieldText] = useState("");

  if (loading) return <div className="panel-loading">Loading playbooks...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 3000); };

  const handleAddTerm = async () => {
    if (!selectedDomain || !newTermName.trim() || !newTermDef.trim()) return;
    const res = await updatePlaybookField(selectedDomain, "terms", {
      add: [{ term: newTermName.trim(), definition: newTermDef.trim() }],
    });
    if (res.success) {
      showMsg("Term added");
      setAddingTerm(false);
      setNewTermName("");
      setNewTermDef("");
      refetchFull();
    } else {
      showMsg(res.error || "Failed");
    }
  };

  const handleRemoveTerm = async (term: string) => {
    if (!selectedDomain || !confirm(`Remove term "${term}"?`)) return;
    const res = await updatePlaybookField(selectedDomain, "terms", { remove: [term] });
    if (res.success) { showMsg("Term removed"); refetchFull(); }
  };

  const handleRestoreTerm = async (term: AnnotatedTerm) => {
    if (!selectedDomain) return;
    // Re-add the hidden base term as admin override
    const res = await updatePlaybookField(selectedDomain, "terms", {
      add: [{ term: term.term, definition: term.definition }],
    });
    if (res.success) { showMsg("Term restored"); refetchFull(); }
  };

  const handleAddListItem = async (field: string) => {
    if (!selectedDomain || !newFieldText.trim()) return;
    const res = await updatePlaybookField(selectedDomain, field, {
      add: [newFieldText.trim()],
    });
    if (res.success) {
      showMsg("Added");
      setAddingField(null);
      setNewFieldText("");
      refetchFull();
    }
  };

  const handleRemoveListItem = async (field: string, idx: number) => {
    if (!selectedDomain || !confirm("Remove this item?")) return;
    const res = await updatePlaybookField(selectedDomain, field, { remove: [idx] });
    if (res.success) { showMsg("Removed"); refetchFull(); }
  };

  const handleResetDomain = async () => {
    if (!selectedDomain || !confirm(`Reset "${selectedDomain}" to base YAML? All admin overrides will be cleared.`)) return;
    const res = await clearPlaybookOverrides(selectedDomain);
    if (res.success) { showMsg("Reset to default"); refetchFull(); refetchList(); }
  };

  const pb = fullData?.playbook;

  const fieldLabel: Record<string, string> = {
    structural_logic: "structural-logic",
    mechanisms: "mechanisms",
    constraints: "constraints",
    failure_modes: "failure-modes",
    non_capabilities: "non-capabilities",
  };

  const renderListSection = (title: string, field: string, items: AnnotatedListItem[]) => {
    const visible = items.filter((i) => !i.hidden);
    const hidden = items.filter((i) => i.hidden);
    return (
      <div className="pb-section">
        <div className="pb-section-header">
          <h4>{title}</h4>
          <button className="add-btn" onClick={() => { setAddingField(field); setNewFieldText(""); }}>+ Add</button>
        </div>
        <div className="pb-list">
          {visible.map((item, i) => (
            <div key={i} className={`pb-list-item ${item.source}`}>
              <span className="pb-list-text">{item.text}</span>
              <div className="pb-list-actions">
                {item.source === "admin" && <span className="source-badge admin">admin</span>}
                <button className="remove-btn" onClick={() => handleRemoveListItem(fieldLabel[field] || field, i)} title="Remove">x</button>
              </div>
            </div>
          ))}
          {hidden.map((item, i) => (
            <div key={`h${i}`} className="pb-list-item hidden">
              <span className="pb-list-text strikethrough">{item.text}</span>
              <span className="source-badge hidden">hidden</span>
            </div>
          ))}
        </div>
        {addingField === field && (
          <div className="inline-add-form">
            <textarea
              value={newFieldText}
              onChange={(e) => setNewFieldText(e.target.value)}
              placeholder={`New ${title.toLowerCase()} item...`}
              rows={2}
            />
            <div className="inline-add-actions">
              <button className="refresh-btn" onClick={() => handleAddListItem(fieldLabel[field] || field)}>Save</button>
              <button className="remove-btn" onClick={() => setAddingField(null)}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="panel playbooks-editor">
      <div className="panel-header">
        <h2>Doctrine Playbooks</h2>
        <div className="panel-badges">
          <span className={`sync-badge ${data.synchronized ? "synced" : "stale"}`}>
            {data.synchronized ? "Synchronized" : "Out of Sync"}
          </span>
          {data.safe_mode && <span className="safe-mode-badge">SAFE MODE</span>}
          <span className="count-badge">{data.count} playbooks</span>
          {msg && <span className="save-msg">{msg}</span>}
          <RegenerateButton onDone={() => { refetchList(); refetchFull(); }} />
        </div>
      </div>

      <div className="playbooks-layout">
        {/* Left sidebar: playbook list */}
        <div className="pb-sidebar">
          {data.playbooks.map((p: DoctrinePlaybookSummary) => (
            <div
              key={p.domain}
              className={`pb-sidebar-item ${selectedDomain === p.domain ? "active" : ""}`}
              onClick={() => setSelectedDomain(p.domain)}
            >
              <span className="pb-sidebar-domain">{p.domain.replace(/_/g, " ")}</span>
              <span className="pb-sidebar-meta">v{p.version} | {p.term_count}t {p.constraint_count}c</span>
            </div>
          ))}
        </div>

        {/* Right content: selected playbook detail */}
        <div className="pb-content">
          {!selectedDomain && (
            <div className="pb-empty">Select a playbook from the sidebar to view and edit its content.</div>
          )}
          {selectedDomain && fullLoading && <div className="panel-loading">Loading playbook...</div>}
          {selectedDomain && pb && (
            <>
              {/* Header */}
              <div className="pb-detail-header">
                <div className="pb-detail-title">
                  <h3>{pb.domain.replace(/_/g, " ")}</h3>
                  <span className="playbook-version">v{pb.version}</span>
                  {pb.has_overrides && <span className="source-badge admin">has overrides</span>}
                  <span className={`health-dot ${data.synchronized ? "ok" : "error"}`} style={{ marginLeft: "0.5rem" }} />
                </div>
                <div className="pb-detail-actions">
                  <button
                    className={`tab-btn ${viewMode === "merged" ? "active" : ""}`}
                    onClick={() => setViewMode("merged")}
                  >Merged</button>
                  <button
                    className={`tab-btn ${viewMode === "changes" ? "active" : ""}`}
                    onClick={() => setViewMode("changes")}
                  >Changes</button>
                  {pb.has_overrides && (
                    <button className="suppress-btn" onClick={handleResetDomain}>Reset to Default</button>
                  )}
                </div>
              </div>

              {/* Meta info */}
              <div className="pb-meta-row">
                <span>Hash: <span className="mono">{pb.path_runtime_hash.slice(0, 16)}...</span></span>
                <span>Generated: {new Date(pb.generated_at).toLocaleDateString()}</span>
                <span>Source: {pb.doctrine_source}</span>
              </div>

              {viewMode === "merged" ? (
                <>
                  {/* Canonical Terms */}
                  <div className="pb-section">
                    <div className="pb-section-header">
                      <h4>Canonical Terms ({pb.canonical_terminology.filter((t: AnnotatedTerm) => !t.hidden).length})</h4>
                      <button className="add-btn" onClick={() => { setAddingTerm(true); setNewTermName(""); setNewTermDef(""); }}>+ Add Term</button>
                    </div>
                    <div className="pb-terms-table">
                      {pb.canonical_terminology.filter((t: AnnotatedTerm) => !t.hidden).map((t: AnnotatedTerm) => (
                        <div key={t.term} className={`pb-term-row ${t.source}`}>
                          <span className="pb-term-name">{t.term}</span>
                          <span className="pb-term-def">{t.definition}</span>
                          <div className="pb-term-actions">
                            {t.source === "admin" && <span className="source-badge admin">admin</span>}
                            <button className="remove-btn" onClick={() => handleRemoveTerm(t.term)} title="Remove">x</button>
                          </div>
                        </div>
                      ))}
                      {pb.canonical_terminology.filter((t: AnnotatedTerm) => t.hidden).map((t: AnnotatedTerm) => (
                        <div key={`h-${t.term}`} className="pb-term-row hidden">
                          <span className="pb-term-name strikethrough">{t.term}</span>
                          <span className="pb-term-def strikethrough">{t.definition}</span>
                          <div className="pb-term-actions">
                            <span className="source-badge hidden">hidden</span>
                            <button className="add-btn" onClick={() => handleRestoreTerm(t)} title="Restore">restore</button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {addingTerm && (
                      <div className="inline-add-form">
                        <input placeholder="Term name" value={newTermName} onChange={(e) => setNewTermName(e.target.value)} />
                        <input placeholder="Definition" value={newTermDef} onChange={(e) => setNewTermDef(e.target.value)} />
                        <div className="inline-add-actions">
                          <button className="refresh-btn" onClick={handleAddTerm}>Save</button>
                          <button className="remove-btn" onClick={() => setAddingTerm(false)}>Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Definitions */}
                  <div className="pb-section">
                    <h4>Definitions</h4>
                    <div className="pb-definitions">
                      {Object.entries(pb.definitions).map(([key, def]) => {
                        const d = def as { value: string; source: string };
                        return (
                          <div key={key} className="pb-def-row">
                            <span className="pb-def-key">{key}</span>
                            <span className="pb-def-value">{d.value}</span>
                            {d.source === "admin" && <span className="source-badge admin">admin</span>}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* List sections */}
                  {renderListSection("Structural Logic", "structural_logic", pb.structural_logic)}
                  {renderListSection("Mechanisms", "mechanisms", pb.mechanisms)}
                  {renderListSection("Constraints", "constraints", pb.constraints)}
                  {renderListSection("Failure Modes", "failure_modes", pb.failure_modes)}
                  {renderListSection("Non-Capabilities", "non_capabilities", pb.non_capabilities)}
                </>
              ) : (
                <DiffView domain={selectedDomain} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function RoutingPanel() {
  const { data, loading, error, refetch } = useRoutingMap();
  const { data: pbData } = useDoctrinePlaybooks();
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [addingPattern, setAddingPattern] = useState(false);
  const [newPattern, setNewPattern] = useState("");
  const [newWeight, setNewWeight] = useState(1.0);
  const [testInput, setTestInput] = useState("");
  const [testResult, setTestResult] = useState<ClassificationTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (loading) return <div className="panel-loading">Loading routing...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const routing = data.routing;
  const domains = Object.keys(routing);
  const allPlaybooks = pbData?.playbooks?.map((p: DoctrinePlaybookSummary) => p.domain) || [];
  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 3000); };

  const handleAddPattern = async () => {
    if (!selectedDomain || !newPattern.trim()) return;
    const res = await updateRoutingPatterns(selectedDomain, {
      add: [{ pattern: newPattern.trim(), weight: newWeight }],
    });
    if (res.success) {
      showMsg("Pattern added");
      setAddingPattern(false);
      setNewPattern("");
      setNewWeight(1.0);
      refetch();
    }
  };

  const handleRemovePattern = async (domain: string, idx: number) => {
    if (!confirm("Remove this pattern?")) return;
    const res = await updateRoutingPatterns(domain, { remove: [idx] });
    if (res.success) { showMsg("Pattern removed"); refetch(); }
  };

  const handlePlaybookMap = async (domain: string, playbook: string) => {
    const res = await updatePlaybookMap(domain, playbook);
    if (res.success) { showMsg("Mapping updated"); refetch(); }
  };

  const handleTest = async () => {
    if (!testInput.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testClassification(testInput);
      if (res.success) setTestResult(res.result);
    } finally {
      setTesting(false);
    }
  };

  const sel = selectedDomain ? routing[selectedDomain] : null;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Classification Routing</h2>
        <div className="panel-badges">
          <span className="count-badge">{domains.length} domains</span>
          {msg && <span className="save-msg">{msg}</span>}
        </div>
      </div>
      <p className="panel-desc">
        Domain classification patterns, weights, and playbook mapping. Patterns are matched against user messages to route to the correct playbook.
      </p>

      <div className="routing-layout">
        {/* Left: Domain List */}
        <div className="routing-sidebar">
          {domains.map((d) => (
            <div
              key={d}
              className={`routing-domain-item ${selectedDomain === d ? "active" : ""}`}
              onClick={() => { setSelectedDomain(d); setAddingPattern(false); }}
            >
              <span className="routing-domain-name">{d.replace(/_/g, " ")}</span>
              <span className="routing-domain-meta">
                {routing[d].patterns.length}p → {routing[d].playbook}
              </span>
            </div>
          ))}
        </div>

        {/* Right: Selected Domain Detail */}
        <div className="routing-content">
          {!selectedDomain && (
            <div className="pb-empty">Select a domain to view and edit its routing patterns.</div>
          )}
          {sel && selectedDomain && (
            <>
              <div className="routing-detail-header">
                <h3>{selectedDomain.replace(/_/g, " ")}</h3>
                <div className="routing-playbook-map">
                  <span className="routing-map-label">Playbook:</span>
                  <select
                    value={sel.playbook}
                    onChange={(e) => handlePlaybookMap(selectedDomain, e.target.value)}
                  >
                    {allPlaybooks.map((p: string) => (
                      <option key={p} value={p}>{p.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Patterns Table */}
              <div className="routing-patterns-section">
                <div className="pb-section-header">
                  <h4>Patterns ({sel.patterns.length})</h4>
                  <button className="add-btn" onClick={() => { setAddingPattern(true); setNewPattern(""); setNewWeight(1.0); }}>+ Add Pattern</button>
                </div>
                <div className="routing-patterns-list">
                  {sel.patterns.map((p, i) => (
                    <div key={i} className={`routing-pattern-row ${p.source}`}>
                      <span className="routing-pattern-text">{p.pattern}</span>
                      <span className="routing-pattern-weight">w: {p.weight.toFixed(1)}</span>
                      {p.source === "admin" && <span className="source-badge admin">admin</span>}
                      <button className="remove-btn" onClick={() => handleRemovePattern(selectedDomain, i)} title="Remove">x</button>
                    </div>
                  ))}
                </div>
                {addingPattern && (
                  <div className="inline-add-form">
                    <input
                      placeholder="Pattern text (e.g. 'options chain')"
                      value={newPattern}
                      onChange={(e) => setNewPattern(e.target.value)}
                    />
                    <div className="inline-add-row">
                      <label>Weight:</label>
                      <input
                        type="number"
                        value={newWeight}
                        onChange={(e) => setNewWeight(parseFloat(e.target.value))}
                        min={0.1}
                        max={5}
                        step={0.1}
                        style={{ width: "80px" }}
                      />
                    </div>
                    <div className="inline-add-actions">
                      <button className="refresh-btn" onClick={handleAddPattern}>Save</button>
                      <button className="remove-btn" onClick={() => setAddingPattern(false)}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>

              {/* Admin Pattern Overrides */}
              {sel.admin_patterns.length > 0 && (
                <div className="routing-admin-section">
                  <h4>Admin Override Patterns</h4>
                  <div className="routing-patterns-list">
                    {sel.admin_patterns.map((p, i) => (
                      <div key={i} className="routing-pattern-row admin">
                        <span className="routing-pattern-text">{p.pattern}</span>
                        <span className="routing-pattern-weight">w: {p.weight.toFixed(1)}</span>
                        <span className="source-badge admin">admin</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Test Console */}
      <div className="routing-test-section">
        <h3>Classification Test Console</h3>
        <p className="panel-desc">Dry-run a message through the LPD classifier to see which domain and playbook it routes to.</p>
        <div className="routing-test-form">
          <textarea
            placeholder="Type a test message... e.g. 'What does gamma exposure look like for SPY?'"
            value={testInput}
            onChange={(e) => setTestInput(e.target.value)}
            rows={3}
          />
          <button className="refresh-btn" onClick={handleTest} disabled={testing || !testInput.trim()}>
            {testing ? "Classifying..." : "Test Classification"}
          </button>
        </div>
        {testResult && (
          <div className="routing-test-result">
            <div className="routing-result-grid">
              <div className="routing-result-item">
                <span className="routing-result-label">Domain</span>
                <span className="routing-result-value">{testResult.domain.replace(/_/g, " ")}</span>
              </div>
              <div className="routing-result-item">
                <span className="routing-result-label">Confidence</span>
                <span className="routing-result-value">{(testResult.confidence * 100).toFixed(0)}%</span>
              </div>
              <div className="routing-result-item">
                <span className="routing-result-label">Doctrine Mode</span>
                <span className="routing-result-value">
                  <span className={`mode-badge ${testResult.doctrine_mode}`}>{testResult.doctrine_mode}</span>
                </span>
              </div>
              <div className="routing-result-item">
                <span className="routing-result-label">Playbook</span>
                <span className="routing-result-value">{testResult.playbook_domain.replace(/_/g, " ")}</span>
              </div>
              {testResult.secondary_domain && (
                <div className="routing-result-item">
                  <span className="routing-result-label">Secondary</span>
                  <span className="routing-result-value">{testResult.secondary_domain.replace(/_/g, " ")}</span>
                </div>
              )}
              <div className="routing-result-item">
                <span className="routing-result-label">Require Playbook</span>
                <span className="routing-result-value">{testResult.require_playbook ? "Yes" : "No"}</span>
              </div>
            </div>
            {testResult.matched_patterns.length > 0 && (
              <div className="routing-matched-patterns">
                <span className="routing-result-label">Matched Patterns:</span>
                <div className="routing-matched-list">
                  {testResult.matched_patterns.map((p, i) => (
                    <span key={i} className="chip active">{p}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DiffView({ domain }: { domain: string }) {
  const { data, loading } = usePlaybookDiff(domain);
  if (loading) return <div className="panel-loading">Loading diff...</div>;
  if (!data?.diff) return <div className="no-results">No diff data available</div>;

  const { diff } = data;
  if (!diff.has_overrides) return <div className="no-results">No admin overrides for this playbook.</div>;

  return (
    <div className="diff-view">
      <h4>Admin Overrides</h4>
      <pre className="diff-json">{JSON.stringify(diff.overrides, null, 2)}</pre>
    </div>
  );
}

function TermsPanel() {
  const { data, loading, error, refetch } = useTermRegistry();
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [newTerm, setNewTerm] = useState("");
  const [newDef, setNewDef] = useState("");
  const [newPlaybooks, setNewPlaybooks] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [editTerm, setEditTerm] = useState<TermRegistryEntry | null>(null);
  const [editDef, setEditDef] = useState("");
  const [editPlaybooks, setEditPlaybooks] = useState<string[]>([]);
  const { data: pbData } = useDoctrinePlaybooks();

  if (loading) return <div className="panel-loading">Loading terms...</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const allDomains = pbData?.playbooks?.map((p: DoctrinePlaybookSummary) => p.domain) || [];
  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 3000); };

  const entries = data.terms.filter(
    (t) =>
      t.term.toLowerCase().includes(search.toLowerCase()) ||
      t.definition.toLowerCase().includes(search.toLowerCase())
  );

  const handleCreate = async () => {
    if (!newTerm.trim() || !newDef.trim() || newPlaybooks.length === 0) return;
    const res = await createTerm(newTerm.trim(), newDef.trim(), newPlaybooks);
    if (res.success) {
      showMsg("Term created");
      setAdding(false);
      setNewTerm("");
      setNewDef("");
      setNewPlaybooks([]);
      refetch();
    }
  };

  const handleUpdate = async () => {
    if (!editTerm || !editDef.trim() || editPlaybooks.length === 0) return;
    const res = await updateTermRegistry(editTerm.term, editDef.trim(), editPlaybooks);
    if (res.success) {
      showMsg("Term updated");
      setEditTerm(null);
      refetch();
    }
  };

  const handleDelete = async (term: string) => {
    if (!confirm(`Remove term "${term}" from all playbooks?`)) return;
    const res = await deleteTerm(term);
    if (res.success) { showMsg("Term removed"); refetch(); }
  };

  const togglePlaybook = (list: string[], domain: string, setter: (v: string[]) => void) => {
    setter(list.includes(domain) ? list.filter((d) => d !== domain) : [...list, domain]);
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Term Registry</h2>
        <div className="panel-badges">
          <span className="count-badge">{data.count} terms</span>
          {msg && <span className="save-msg">{msg}</span>}
          <button className="add-btn" onClick={() => setAdding(true)}>+ Add Term</button>
        </div>
      </div>
      <p className="panel-desc">
        Unified canonical term dictionary across all playbooks. Edit terms and assign them to playbooks.
      </p>
      <div className="search-box">
        <input
          type="text"
          placeholder="Search terms..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {adding && (
        <div className="term-add-form">
          <input placeholder="Term name" value={newTerm} onChange={(e) => setNewTerm(e.target.value)} />
          <input placeholder="Definition" value={newDef} onChange={(e) => setNewDef(e.target.value)} />
          <div className="playbook-chips">
            {allDomains.map((d: string) => (
              <button key={d} className={`chip ${newPlaybooks.includes(d) ? "active" : ""}`}
                onClick={() => togglePlaybook(newPlaybooks, d, setNewPlaybooks)}>
                {d.replace(/_/g, " ")}
              </button>
            ))}
          </div>
          <div className="inline-add-actions">
            <button className="refresh-btn" onClick={handleCreate}>Create</button>
            <button className="remove-btn" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="terms-list">
        {entries.map((t) => (
          <div key={t.term} className="term-item-registry">
            {editTerm?.term === t.term ? (
              <div className="term-edit-form">
                <div className="term-name">{t.term}</div>
                <textarea value={editDef} onChange={(e) => setEditDef(e.target.value)} rows={2} />
                <div className="playbook-chips">
                  {allDomains.map((d: string) => (
                    <button key={d} className={`chip ${editPlaybooks.includes(d) ? "active" : ""}`}
                      onClick={() => togglePlaybook(editPlaybooks, d, setEditPlaybooks)}>
                      {d.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>
                <div className="inline-add-actions">
                  <button className="refresh-btn" onClick={handleUpdate}>Save</button>
                  <button className="remove-btn" onClick={() => setEditTerm(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="term-info">
                  <div className="term-name">{t.term}</div>
                  <div className="term-def">{t.definition}</div>
                  <div className="term-playbooks">
                    {t.playbooks.map((d) => (
                      <span key={d} className="chip active">{d.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                </div>
                <div className="term-actions">
                  {t.source === "admin" && <span className="source-badge admin">admin</span>}
                  <button className="add-btn" onClick={() => { setEditTerm(t); setEditDef(t.definition); setEditPlaybooks([...t.playbooks]); }}>Edit</button>
                  <button className="remove-btn" onClick={() => handleDelete(t.term)}>x</button>
                </div>
              </>
            )}
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

  /* Diagnostic Box */
  .diagnostic-box {
    margin-top: 1rem;
    padding: 1rem 1.25rem;
    border-radius: 0.5rem;
    font-size: 0.8125rem;
    line-height: 1.6;
  }

  .diagnostic-box.error {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.25);
  }

  .diagnostic-title {
    font-weight: 700;
    font-size: 0.875rem;
    color: #f87171;
    margin-bottom: 0.5rem;
  }

  .diagnostic-body p {
    color: var(--text-secondary);
    margin: 0 0 0.75rem;
  }

  .diagnostic-label {
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.25rem;
  }

  .diagnostic-details ul {
    margin: 0.25rem 0 0.75rem 1.25rem;
    padding: 0;
  }

  .diagnostic-details li {
    color: #f87171;
    font-size: 0.75rem;
    margin-bottom: 0.25rem;
  }

  .diagnostic-fix p {
    color: var(--text-secondary);
    margin: 0;
  }

  /* Per-Playbook Health Rows */
  .playbook-health-list {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .playbook-health-row {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
    border: 1px solid transparent;
    font-size: 0.8125rem;
  }

  .playbook-health-row.mismatch {
    border-color: rgba(239, 68, 68, 0.25);
    background: rgba(239, 68, 68, 0.05);
  }

  .playbook-health-domain {
    flex: 1;
    font-weight: 500;
    text-transform: capitalize;
    color: var(--text-primary);
  }

  .playbook-health-version {
    font-size: 0.6875rem;
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
  }

  .playbook-health-hash {
    font-size: 0.6875rem;
    color: var(--text-muted);
  }

  .playbook-health-date {
    font-size: 0.6875rem;
    color: var(--text-secondary);
  }

  .mono { font-family: 'SF Mono', ui-monospace, monospace; }

  /* =========================================================
     Playbooks Editor Layout
     ========================================================= */
  .playbooks-editor { padding: 0; }
  .playbooks-editor .panel-header { padding: 1.25rem 1.25rem 0; }
  .playbooks-editor .panel-badges { flex-wrap: wrap; }

  .playbooks-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 0;
    min-height: 500px;
    border-top: 1px solid var(--border-subtle);
    margin-top: 0.75rem;
  }

  .pb-sidebar {
    border-right: 1px solid var(--border-subtle);
    overflow-y: auto;
    max-height: 700px;
  }

  .pb-sidebar-item {
    padding: 0.75rem 1rem;
    cursor: pointer;
    border-bottom: 1px solid var(--border-subtle);
    transition: all 0.15s;
  }

  .pb-sidebar-item:hover { background: var(--bg-hover); }
  .pb-sidebar-item.active {
    background: rgba(124, 58, 237, 0.08);
    border-left: 3px solid #7c3aed;
  }

  .pb-sidebar-domain {
    display: block;
    font-weight: 600;
    font-size: 0.8125rem;
    text-transform: capitalize;
    color: var(--text-primary);
  }

  .pb-sidebar-meta {
    font-size: 0.6875rem;
    color: var(--text-secondary);
  }

  .pb-content {
    padding: 1.25rem;
    overflow-y: auto;
    max-height: 700px;
  }

  .pb-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 300px;
    color: var(--text-muted);
    font-size: 0.875rem;
  }

  /* Playbook Detail Header */
  .pb-detail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .pb-detail-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .pb-detail-title h3 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
    text-transform: capitalize;
  }

  .pb-detail-actions {
    display: flex;
    gap: 0.375rem;
    align-items: center;
  }

  .pb-meta-row {
    display: flex;
    gap: 1.5rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    margin-bottom: 1.25rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-subtle);
    flex-wrap: wrap;
  }

  /* Playbook Sections */
  .pb-section {
    margin-bottom: 1.5rem;
  }

  .pb-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }

  .pb-section h4, .pb-section-header h4 {
    font-size: 0.8125rem;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  /* Terms Table */
  .pb-terms-table {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .pb-term-row {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
    font-size: 0.8125rem;
  }

  .pb-term-row.hidden { opacity: 0.5; }
  .pb-term-row.admin { border-left: 2px solid #f59e0b; }

  .pb-term-name {
    font-weight: 600;
    color: #c4b5fd;
    min-width: 120px;
    flex-shrink: 0;
  }

  .pb-term-def {
    flex: 1;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .pb-term-actions {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    flex-shrink: 0;
  }

  /* Definitions */
  .pb-definitions {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .pb-def-row {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
    font-size: 0.8125rem;
  }

  .pb-def-key {
    font-weight: 600;
    color: #60a5fa;
    min-width: 120px;
    flex-shrink: 0;
  }

  .pb-def-value {
    flex: 1;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  /* List Items */
  .pb-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .pb-list-item {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
    font-size: 0.8125rem;
  }

  .pb-list-item.hidden { opacity: 0.5; }
  .pb-list-item.admin { border-left: 2px solid #f59e0b; }

  .pb-list-text {
    flex: 1;
    color: var(--text-secondary);
    line-height: 1.4;
  }

  .pb-list-actions {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    flex-shrink: 0;
  }

  /* Source Badges */
  .source-badge {
    font-size: 0.625rem;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .source-badge.admin {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
  }

  .source-badge.hidden {
    background: rgba(107, 114, 128, 0.15);
    color: #9ca3af;
  }

  .strikethrough { text-decoration: line-through; }

  /* Add / Remove Buttons */
  .add-btn {
    padding: 0.25rem 0.625rem;
    background: rgba(34, 197, 94, 0.1);
    border: 1px solid rgba(34, 197, 94, 0.3);
    border-radius: 0.375rem;
    color: #22c55e;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .add-btn:hover { background: rgba(34, 197, 94, 0.2); }

  .remove-btn {
    padding: 0.25rem 0.5rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: 0.375rem;
    color: #f87171;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .remove-btn:hover { background: rgba(239, 68, 68, 0.2); }

  /* Inline Add Forms */
  .inline-add-form {
    margin-top: 0.5rem;
    padding: 0.75rem;
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .inline-add-form input,
  .inline-add-form textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.8125rem;
    font-family: inherit;
    resize: vertical;
  }

  .inline-add-form input:focus,
  .inline-add-form textarea:focus {
    outline: none;
    border-color: rgba(59, 130, 246, 0.5);
  }

  .inline-add-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }

  .inline-add-actions {
    display: flex;
    gap: 0.5rem;
  }

  /* Diff View */
  .diff-view {
    padding: 0.5rem 0;
  }

  .diff-view h4 {
    font-size: 0.875rem;
    font-weight: 600;
    margin: 0 0 0.75rem;
    color: var(--text-primary);
  }

  .diff-json {
    padding: 1rem;
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    font-family: 'SF Mono', ui-monospace, monospace;
    font-size: 0.75rem;
    color: var(--text-secondary);
    overflow-x: auto;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* =========================================================
     Term Registry Panel
     ========================================================= */
  .term-item-registry {
    padding: 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.5rem;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
  }

  .term-info { flex: 1; min-width: 0; }

  .term-playbooks {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.375rem;
  }

  .term-actions {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    flex-shrink: 0;
  }

  .term-edit-form {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .term-edit-form textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.8125rem;
    font-family: inherit;
    resize: vertical;
  }

  .term-add-form {
    padding: 0.75rem;
    background: var(--bg-surface-alt);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .term-add-form input {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.8125rem;
  }

  /* Chips */
  .playbook-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }

  .chip {
    padding: 0.2rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    background: var(--bg-hover);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    text-transform: capitalize;
  }

  .chip.active {
    background: rgba(124, 58, 237, 0.15);
    border-color: rgba(124, 58, 237, 0.3);
    color: #a78bfa;
  }

  .chip:hover { border-color: rgba(124, 58, 237, 0.4); }

  /* =========================================================
     Routing Panel
     ========================================================= */
  .routing-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 0;
    min-height: 400px;
    border: 1px solid var(--border-subtle);
    border-radius: 0.5rem;
    margin-bottom: 1.5rem;
    overflow: hidden;
  }

  .routing-sidebar {
    border-right: 1px solid var(--border-subtle);
    overflow-y: auto;
    max-height: 500px;
    background: var(--bg-surface-alt);
  }

  .routing-domain-item {
    padding: 0.75rem 1rem;
    cursor: pointer;
    border-bottom: 1px solid var(--border-subtle);
    transition: all 0.15s;
  }

  .routing-domain-item:hover { background: var(--bg-hover); }
  .routing-domain-item.active {
    background: rgba(59, 130, 246, 0.08);
    border-left: 3px solid #3b82f6;
  }

  .routing-domain-name {
    display: block;
    font-weight: 600;
    font-size: 0.8125rem;
    text-transform: capitalize;
    color: var(--text-primary);
  }

  .routing-domain-meta {
    font-size: 0.6875rem;
    color: var(--text-secondary);
  }

  .routing-content {
    padding: 1.25rem;
    overflow-y: auto;
    max-height: 500px;
  }

  .routing-detail-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .routing-detail-header h3 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0;
    text-transform: capitalize;
  }

  .routing-playbook-map {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .routing-map-label {
    font-size: 0.75rem;
    color: var(--text-secondary);
    font-weight: 500;
  }

  .routing-playbook-map select {
    padding: 0.375rem 0.625rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.375rem;
    color: var(--text-primary);
    font-size: 0.8125rem;
    text-transform: capitalize;
  }

  .routing-patterns-section, .routing-admin-section {
    margin-bottom: 1.25rem;
  }

  .routing-admin-section h4 {
    font-size: 0.8125rem;
    font-weight: 600;
    margin: 0 0 0.5rem;
    color: var(--text-primary);
  }

  .routing-patterns-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .routing-pattern-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-surface-alt);
    border-radius: 0.375rem;
    font-size: 0.8125rem;
  }

  .routing-pattern-row.admin { border-left: 2px solid #f59e0b; }

  .routing-pattern-text {
    flex: 1;
    color: var(--text-primary);
    font-family: 'SF Mono', ui-monospace, monospace;
    font-size: 0.75rem;
  }

  .routing-pattern-weight {
    font-size: 0.6875rem;
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    flex-shrink: 0;
  }

  /* Test Console */
  .routing-test-section {
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-subtle);
  }

  .routing-test-section h3 {
    font-size: 0.875rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
    color: var(--text-primary);
  }

  .routing-test-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .routing-test-form textarea {
    width: 100%;
    padding: 0.75rem;
    background: var(--bg-input);
    border: 1px solid var(--border-default);
    border-radius: 0.5rem;
    color: var(--text-primary);
    font-size: 0.8125rem;
    font-family: inherit;
    resize: vertical;
  }

  .routing-test-form textarea:focus {
    outline: none;
    border-color: rgba(59, 130, 246, 0.5);
  }

  .routing-test-result {
    padding: 1rem;
    background: var(--bg-surface-alt);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 0.5rem;
  }

  .routing-result-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .routing-result-item {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .routing-result-label {
    font-size: 0.6875rem;
    color: var(--text-secondary);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .routing-result-value {
    font-size: 0.875rem;
    color: var(--text-primary);
    font-weight: 600;
    text-transform: capitalize;
  }

  .routing-matched-patterns {
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
  }

  .routing-matched-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin-top: 0.375rem;
  }
`;
