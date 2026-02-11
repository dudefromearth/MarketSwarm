// ui/src/pages/AdminEconIndicators.tsx
// Admin page for Economic Indicators CRUD management

import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";

interface Indicator {
  id: string;
  key: string;
  name: string;
  rating: number;
  tier: string;
  description: string | null;
  is_active: boolean;
  aliases: string[];
  created_at: string;
  updated_at: string;
}

interface ModalState {
  open: boolean;
  mode: "create" | "edit";
  indicator: Indicator | null;
}

const TIER_COLORS: Record<string, { bg: string; color: string; label: string }> = {
  critical: { bg: "rgba(239, 68, 68, 0.15)", color: "#ef4444", label: "Critical" },
  high: { bg: "rgba(249, 115, 22, 0.15)", color: "#f97316", label: "High" },
  medium: { bg: "rgba(234, 179, 8, 0.15)", color: "#eab308", label: "Medium" },
  low: { bg: "rgba(156, 163, 175, 0.15)", color: "#9ca3af", label: "Low" },
};

function ratingToTier(rating: number): string {
  if (rating >= 9) return "critical";
  if (rating >= 7) return "high";
  if (rating >= 5) return "medium";
  return "low";
}

export default function AdminEconIndicatorsPage() {
  const navigate = useNavigate();
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ open: false, mode: "create", indicator: null });
  const [saving, setSaving] = useState(false);

  // Form state
  const [formKey, setFormKey] = useState("");
  const [formName, setFormName] = useState("");
  const [formRating, setFormRating] = useState(5);
  const [formDescription, setFormDescription] = useState("");
  const [formAliases, setFormAliases] = useState<string[]>([]);
  const [formAliasInput, setFormAliasInput] = useState("");
  const [formActive, setFormActive] = useState(true);

  const fetchIndicators = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/economic-indicators", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load indicators");
      const data = await res.json();
      setIndicators(data.data || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIndicators();
  }, [fetchIndicators]);

  const openCreate = () => {
    setFormKey("");
    setFormName("");
    setFormRating(5);
    setFormDescription("");
    setFormAliases([]);
    setFormAliasInput("");
    setFormActive(true);
    setModal({ open: true, mode: "create", indicator: null });
  };

  const openEdit = (ind: Indicator) => {
    setFormKey(ind.key);
    setFormName(ind.name);
    setFormRating(ind.rating);
    setFormDescription(ind.description || "");
    setFormAliases([...ind.aliases]);
    setFormAliasInput("");
    setFormActive(ind.is_active);
    setModal({ open: true, mode: "edit", indicator: ind });
  };

  const closeModal = () => {
    setModal({ open: false, mode: "create", indicator: null });
  };

  const addAlias = () => {
    const val = formAliasInput.trim();
    if (val && !formAliases.includes(val)) {
      setFormAliases([...formAliases, val]);
    }
    setFormAliasInput("");
  };

  const removeAlias = (alias: string) => {
    setFormAliases(formAliases.filter(a => a !== alias));
  };

  const handleAliasKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addAlias();
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (modal.mode === "create") {
        const res = await fetch("/api/admin/economic-indicators", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            key: formKey,
            name: formName,
            rating: formRating,
            description: formDescription || null,
            aliases: formAliases,
          }),
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.error || "Create failed");
        }
      } else if (modal.indicator) {
        const res = await fetch(`/api/admin/economic-indicators/${modal.indicator.id}`, {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: formName,
            rating: formRating,
            description: formDescription || null,
            is_active: formActive,
            aliases: formAliases,
          }),
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.error || "Update failed");
        }
      }
      closeModal();
      fetchIndicators();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (ind: Indicator) => {
    try {
      if (ind.is_active) {
        await fetch(`/api/admin/economic-indicators/${ind.id}`, {
          method: "DELETE",
          credentials: "include",
        });
      } else {
        await fetch(`/api/admin/economic-indicators/${ind.id}`, {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_active: true }),
        });
      }
      fetchIndicators();
    } catch (e) {
      console.error("Toggle active failed:", e);
    }
  };

  const previewTier = ratingToTier(formRating);
  const previewTierStyle = TIER_COLORS[previewTier];

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-loading">Loading...</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-page">
        <div className="admin-error">
          <h2>Error</h2>
          <p>{error}</p>
          <button onClick={() => navigate("/admin")}>Back to Admin</button>
        </div>
        <style>{styles}</style>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="admin-container">
        {/* Header */}
        <div className="admin-header">
          <div className="header-left">
            <button className="back-btn" onClick={() => navigate("/admin")}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Admin
            </button>
            <h1>Economic Indicators</h1>
            <span className="indicator-count">{indicators.length} indicators</span>
          </div>
          <button className="add-btn" onClick={openCreate}>
            + Add Indicator
          </button>
        </div>

        {/* Table */}
        <div className="econ-table-container">
          <table className="econ-table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Name</th>
                <th>Rating</th>
                <th>Tier</th>
                <th>Aliases</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {indicators.map((ind) => {
                const tierStyle = TIER_COLORS[ind.tier] || TIER_COLORS.low;
                return (
                  <tr key={ind.id} className={ind.is_active ? "" : "retired"}>
                    <td className="key-cell">{ind.key}</td>
                    <td className="name-cell">{ind.name}</td>
                    <td className="rating-cell">
                      <span className="rating-number">{ind.rating}</span>
                    </td>
                    <td>
                      <span
                        className="tier-badge"
                        style={{ background: tierStyle.bg, color: tierStyle.color }}
                      >
                        {tierStyle.label}
                      </span>
                    </td>
                    <td className="aliases-cell">
                      <div className="alias-tags">
                        {ind.aliases.slice(0, 3).map((a, i) => (
                          <span key={i} className="alias-tag">{a}</span>
                        ))}
                        {ind.aliases.length > 3 && (
                          <span className="alias-more">+{ind.aliases.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`active-badge ${ind.is_active ? "active" : "inactive"}`}>
                        {ind.is_active ? "Active" : "Retired"}
                      </span>
                    </td>
                    <td className="actions-cell">
                      <button className="action-btn edit" onClick={() => openEdit(ind)}>Edit</button>
                      <button
                        className={`action-btn ${ind.is_active ? "retire" : "reactivate"}`}
                        onClick={() => handleToggleActive(ind)}
                      >
                        {ind.is_active ? "Retire" : "Reactivate"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create/Edit Modal */}
      {modal.open && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{modal.mode === "create" ? "Add Indicator" : "Edit Indicator"}</h2>
              <button className="modal-close" onClick={closeModal}>&times;</button>
            </div>

            <div className="modal-body">
              <div className="form-group">
                <label>Key</label>
                <input
                  type="text"
                  value={formKey}
                  onChange={(e) => setFormKey(e.target.value)}
                  placeholder="e.g., cpi"
                  disabled={modal.mode === "edit"}
                  className={modal.mode === "edit" ? "disabled" : ""}
                />
                {modal.mode === "edit" && (
                  <span className="form-hint">Key is immutable after creation</span>
                )}
              </div>

              <div className="form-group">
                <label>Name</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., Consumer Price Index (CPI)"
                />
              </div>

              <div className="form-group">
                <label>
                  Rating: <strong>{formRating}</strong>
                  <span
                    className="tier-preview"
                    style={{ background: previewTierStyle.bg, color: previewTierStyle.color }}
                  >
                    {previewTierStyle.label}
                  </span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={formRating}
                  onChange={(e) => setFormRating(Number(e.target.value))}
                  className="rating-slider"
                />
                <div className="rating-labels">
                  <span>1 (Low)</span>
                  <span>10 (Critical)</span>
                </div>
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Optional description..."
                  rows={3}
                />
              </div>

              <div className="form-group">
                <label>Aliases ({formAliases.length})</label>
                <div className="alias-input-row">
                  <input
                    type="text"
                    value={formAliasInput}
                    onChange={(e) => setFormAliasInput(e.target.value)}
                    onKeyDown={handleAliasKeyDown}
                    placeholder="Type alias and press Enter"
                  />
                  <button type="button" className="alias-add-btn" onClick={addAlias}>Add</button>
                </div>
                <div className="alias-list">
                  {formAliases.map((alias, i) => (
                    <span key={i} className="alias-chip">
                      {alias}
                      <button onClick={() => removeAlias(alias)}>&times;</button>
                    </span>
                  ))}
                </div>
              </div>

              {modal.mode === "edit" && (
                <div className="form-group">
                  <label className="toggle-label">
                    <input
                      type="checkbox"
                      checked={formActive}
                      onChange={(e) => setFormActive(e.target.checked)}
                    />
                    Active
                  </label>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="cancel-btn" onClick={closeModal}>Cancel</button>
              <button
                className="save-btn"
                onClick={handleSave}
                disabled={saving || !formKey || !formName}
              >
                {saving ? "Saving..." : modal.mode === "create" ? "Create" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .admin-page {
    min-height: 100vh;
    background: #09090b;
    color: #f1f5f9;
    padding: 1.5rem;
  }

  .admin-container {
    max-width: 1400px;
    margin: 0 auto;
  }

  .admin-loading,
  .admin-error {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 50vh;
    text-align: center;
  }

  .admin-error h2 { color: #f87171; margin-bottom: 0.5rem; }
  .admin-error button {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #3b82f6;
    border: none;
    border-radius: 0.5rem;
    color: white;
    cursor: pointer;
  }

  .admin-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .admin-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    background: linear-gradient(135deg, #7c3aed, #6366f1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .indicator-count {
    font-size: 0.875rem;
    color: #71717a;
  }

  .back-btn {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.5rem;
    color: #a1a1aa;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .back-btn:hover { background: rgba(255, 255, 255, 0.08); color: #e4e4e7; }
  .back-btn svg { width: 1rem; height: 1rem; }

  .add-btn {
    padding: 0.5rem 1rem;
    background: rgba(124, 58, 237, 0.15);
    border: 1px solid rgba(124, 58, 237, 0.3);
    border-radius: 0.5rem;
    color: #a78bfa;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .add-btn:hover {
    background: rgba(124, 58, 237, 0.25);
    color: #c4b5fd;
  }

  /* Table */
  .econ-table-container {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .econ-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }

  .econ-table th {
    text-align: left;
    padding: 0.875rem 1rem;
    background: rgba(255, 255, 255, 0.03);
    color: #71717a;
    font-weight: 500;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .econ-table td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .econ-table tr.retired td { opacity: 0.5; }

  .key-cell {
    font-family: 'SF Mono', monospace;
    font-size: 0.8125rem;
    color: #60a5fa;
  }

  .name-cell { font-weight: 500; color: #f1f5f9; }

  .rating-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    border-radius: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    font-weight: 700;
    font-size: 0.875rem;
  }

  .tier-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .aliases-cell { max-width: 300px; }

  .alias-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }

  .alias-tag {
    display: inline-block;
    padding: 0.125rem 0.375rem;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    color: #a1a1aa;
  }

  .alias-more {
    font-size: 0.6875rem;
    color: #71717a;
    padding: 0.125rem 0.25rem;
  }

  .active-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .active-badge.active {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
  }

  .active-badge.inactive {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }

  .actions-cell {
    display: flex;
    gap: 0.375rem;
    white-space: nowrap;
  }

  .action-btn {
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    cursor: pointer;
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.05);
    color: #a1a1aa;
    transition: all 0.15s;
  }

  .action-btn:hover { background: rgba(255, 255, 255, 0.1); color: #f1f5f9; }

  .action-btn.retire { color: #f87171; }
  .action-btn.retire:hover { background: rgba(239, 68, 68, 0.15); }

  .action-btn.reactivate { color: #22c55e; }
  .action-btn.reactivate:hover { background: rgba(34, 197, 94, 0.15); }

  /* Modal */
  .modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 200;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.7);
  }

  .modal-content {
    width: 540px;
    max-height: 90vh;
    overflow-y: auto;
    background: #18181b;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.75rem;
    box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .modal-header h2 { font-size: 1.125rem; margin: 0; }

  .modal-close {
    background: none;
    border: none;
    color: #71717a;
    font-size: 1.5rem;
    cursor: pointer;
    line-height: 1;
  }

  .modal-close:hover { color: #f1f5f9; }

  .modal-body { padding: 1.5rem; }

  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    color: #a1a1aa;
    margin-bottom: 0.375rem;
  }

  .form-group input[type="text"],
  .form-group textarea {
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.375rem;
    color: #f1f5f9;
    font-size: 0.875rem;
    font-family: inherit;
    box-sizing: border-box;
  }

  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: rgba(124, 58, 237, 0.5);
  }

  .form-group input.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .form-hint {
    font-size: 0.6875rem;
    color: #52525b;
    display: block;
    margin-top: 0.25rem;
  }

  .rating-slider {
    width: 100%;
    accent-color: #7c3aed;
    margin-top: 0.25rem;
  }

  .rating-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.6875rem;
    color: #52525b;
    margin-top: 0.25rem;
  }

  .tier-preview {
    display: inline-block;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.6875rem;
    font-weight: 500;
    margin-left: 0.25rem;
  }

  .alias-input-row {
    display: flex;
    gap: 0.5rem;
  }

  .alias-input-row input { flex: 1; }

  .alias-add-btn {
    padding: 0.5rem 0.75rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.375rem;
    color: #a1a1aa;
    font-size: 0.8125rem;
    cursor: pointer;
  }

  .alias-add-btn:hover { background: rgba(255, 255, 255, 0.1); }

  .alias-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin-top: 0.5rem;
  }

  .alias-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: rgba(124, 58, 237, 0.15);
    border-radius: 0.25rem;
    font-size: 0.75rem;
    color: #c4b5fd;
  }

  .alias-chip button {
    background: none;
    border: none;
    color: #a78bfa;
    font-size: 0.875rem;
    cursor: pointer;
    padding: 0;
    line-height: 1;
  }

  .alias-chip button:hover { color: #ef4444; }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding: 1rem 1.5rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  .cancel-btn {
    padding: 0.5rem 1rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.375rem;
    color: #a1a1aa;
    font-size: 0.875rem;
    cursor: pointer;
  }

  .cancel-btn:hover { background: rgba(255, 255, 255, 0.1); }

  .save-btn {
    padding: 0.5rem 1rem;
    background: #7c3aed;
    border: none;
    border-radius: 0.375rem;
    color: white;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }

  .save-btn:hover:not(:disabled) { background: #6d28d9; }
  .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
`;
