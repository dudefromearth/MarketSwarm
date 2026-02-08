// ui/src/pages/AdminVexy.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

interface PromptData {
  default: string;
  custom: string | null;
  active: string;
  updated: string | null;
}

interface AllPrompts {
  outlets: {
    chat: PromptData;
    routine: PromptData;
    process: PromptData;
  };
  tiers: {
    observer: PromptData;
    activator: PromptData;
    navigator: PromptData;
    administrator: PromptData;
  };
}

type TabType = 'outlets' | 'tiers';
type OutletKey = 'chat' | 'routine' | 'process';
type TierKey = 'observer' | 'activator' | 'navigator' | 'administrator';

export default function AdminVexyPage() {
  const navigate = useNavigate();
  const [prompts, setPrompts] = useState<AllPrompts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // UI state
  const [activeTab, setActiveTab] = useState<TabType>('outlets');
  const [selectedOutlet, setSelectedOutlet] = useState<OutletKey>('chat');
  const [selectedTier, setSelectedTier] = useState<TierKey>('observer');
  const [editContent, setEditContent] = useState<string>('');
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch all prompts on mount
  useEffect(() => {
    fetchPrompts();
  }, []);

  const fetchPrompts = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/vexy/admin/prompts", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load prompts");
      const json = await res.json();
      // Backend returns { success: true, data: {...} }
      const data = json.data || json;
      setPrompts(data);
      // Initialize edit content with first outlet
      if (data.outlets?.chat) {
        setEditContent(data.outlets.chat.active);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load prompts");
    } finally {
      setLoading(false);
    }
  };

  // Update edit content when selection changes
  useEffect(() => {
    if (!prompts) return;

    if (activeTab === 'outlets') {
      const prompt = prompts.outlets[selectedOutlet];
      if (prompt) {
        setEditContent(prompt.active);
        setHasChanges(false);
      }
    } else {
      const prompt = prompts.tiers[selectedTier];
      if (prompt) {
        setEditContent(prompt.active);
        setHasChanges(false);
      }
    }
  }, [activeTab, selectedOutlet, selectedTier, prompts]);

  const handleContentChange = (value: string) => {
    setEditContent(value);

    // Check if content differs from active
    if (prompts) {
      if (activeTab === 'outlets') {
        setHasChanges(value !== prompts.outlets[selectedOutlet].active);
      } else {
        setHasChanges(value !== prompts.tiers[selectedTier].active);
      }
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMessage(null);

    try {
      const endpoint = activeTab === 'outlets'
        ? `/api/vexy/admin/prompts/outlet/${selectedOutlet}`
        : `/api/vexy/admin/prompts/tier/${selectedTier}`;

      const res = await fetch(endpoint, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ prompt: editContent }),
      });

      if (!res.ok) throw new Error("Failed to save prompt");

      setSaveMessage("Saved successfully");
      setHasChanges(false);

      // Refresh prompts
      await fetchPrompts();

      setTimeout(() => setSaveMessage(null), 3000);
    } catch (e) {
      setSaveMessage(`Error: ${e instanceof Error ? e.message : "Save failed"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Reset to default prompt? This will remove any custom modifications.")) {
      return;
    }

    setSaving(true);
    setSaveMessage(null);

    try {
      const endpoint = activeTab === 'outlets'
        ? `/api/vexy/admin/prompts/outlet/${selectedOutlet}`
        : `/api/vexy/admin/prompts/tier/${selectedTier}`;

      const res = await fetch(endpoint, {
        method: "DELETE",
        credentials: "include",
      });

      if (!res.ok) throw new Error("Failed to reset prompt");

      setSaveMessage("Reset to default");
      setHasChanges(false);

      // Refresh prompts
      await fetchPrompts();

      setTimeout(() => setSaveMessage(null), 3000);
    } catch (e) {
      setSaveMessage(`Error: ${e instanceof Error ? e.message : "Reset failed"}`);
    } finally {
      setSaving(false);
    }
  };

  const getCurrentPromptData = (): PromptData | null => {
    if (!prompts) return null;
    if (activeTab === 'outlets') {
      return prompts.outlets[selectedOutlet];
    }
    return prompts.tiers[selectedTier];
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleString();
  };

  if (loading) {
    return (
      <div className="admin-vexy-page">
        <div className="admin-loading">Loading Vexy configuration...</div>
        <style>{styles}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-vexy-page">
        <div className="admin-error">
          <h2>Error Loading Prompts</h2>
          <p>{error}</p>
          <button onClick={() => navigate("/admin")}>Back to Admin</button>
        </div>
        <style>{styles}</style>
      </div>
    );
  }

  const currentPrompt = getCurrentPromptData();
  const isCustomized = currentPrompt?.custom !== null;

  return (
    <div className="admin-vexy-page">
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
            <h1>Vexy Instructions</h1>
          </div>
          <div className="header-actions">
            {saveMessage && (
              <span className={`save-message ${saveMessage.startsWith('Error') ? 'error' : 'success'}`}>
                {saveMessage}
              </span>
            )}
            {isCustomized && (
              <button
                className="reset-btn"
                onClick={handleReset}
                disabled={saving}
              >
                Reset to Default
              </button>
            )}
            <button
              className="save-btn"
              onClick={handleSave}
              disabled={saving || !hasChanges}
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="tab-nav">
          <button
            className={`tab-btn ${activeTab === 'outlets' ? 'active' : ''}`}
            onClick={() => setActiveTab('outlets')}
          >
            Outlets
          </button>
          <button
            className={`tab-btn ${activeTab === 'tiers' ? 'active' : ''}`}
            onClick={() => setActiveTab('tiers')}
          >
            Tier Guardrails
          </button>
        </div>

        <div className="content-layout">
          {/* Sidebar */}
          <div className="sidebar">
            {activeTab === 'outlets' ? (
              <>
                <div className="sidebar-header">Outlet Prompts</div>
                <div className="sidebar-desc">
                  Base instructions for each Vexy interface
                </div>
                <div className="sidebar-items">
                  {(['chat', 'routine', 'process'] as OutletKey[]).map((outlet) => {
                    const data = prompts?.outlets[outlet];
                    return (
                      <button
                        key={outlet}
                        className={`sidebar-item ${selectedOutlet === outlet ? 'active' : ''}`}
                        onClick={() => setSelectedOutlet(outlet)}
                      >
                        <span className="item-icon">
                          {outlet === 'chat' && '💬'}
                          {outlet === 'routine' && '🌅'}
                          {outlet === 'process' && '🌙'}
                        </span>
                        <span className="item-name">{outlet.charAt(0).toUpperCase() + outlet.slice(1)}</span>
                        {data?.custom && <span className="custom-badge">Custom</span>}
                      </button>
                    );
                  })}
                </div>
              </>
            ) : (
              <>
                <div className="sidebar-header">Tier Guardrails</div>
                <div className="sidebar-desc">
                  Access controls and semantic limits per tier
                </div>
                <div className="sidebar-items">
                  {(['observer', 'activator', 'navigator', 'administrator'] as TierKey[]).map((tier) => {
                    const data = prompts?.tiers[tier];
                    return (
                      <button
                        key={tier}
                        className={`sidebar-item ${selectedTier === tier ? 'active' : ''}`}
                        onClick={() => setSelectedTier(tier)}
                      >
                        <span className="item-icon">
                          {tier === 'observer' && '👁️'}
                          {tier === 'activator' && '⚡'}
                          {tier === 'navigator' && '🧭'}
                          {tier === 'administrator' && '🔧'}
                        </span>
                        <span className="item-name">{tier.charAt(0).toUpperCase() + tier.slice(1)}</span>
                        {data?.custom && <span className="custom-badge">Custom</span>}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {/* Editor */}
          <div className="editor-panel">
            <div className="editor-header">
              <div className="editor-title">
                <h2>
                  {activeTab === 'outlets'
                    ? `${selectedOutlet.charAt(0).toUpperCase() + selectedOutlet.slice(1)} Mode`
                    : `${selectedTier.charAt(0).toUpperCase() + selectedTier.slice(1)} Tier`
                  }
                </h2>
                {isCustomized && (
                  <span className="customized-indicator">
                    Customized {currentPrompt?.updated && `• ${formatDate(currentPrompt.updated)}`}
                  </span>
                )}
              </div>
              {hasChanges && (
                <span className="unsaved-indicator">Unsaved changes</span>
              )}
            </div>

            <div className="editor-description">
              {activeTab === 'outlets' && (
                <>
                  {selectedOutlet === 'chat' && 'Instructions for conversational chat via the butterfly button. Keep responses short and direct.'}
                  {selectedOutlet === 'routine' && 'Morning orientation ritual. Calm, observational, present-focused.'}
                  {selectedOutlet === 'process' && 'End-of-day integration. Connects morning intentions to session outcomes.'}
                </>
              )}
              {activeTab === 'tiers' && (
                <>
                  {selectedTier === 'observer' && 'Basic access. Orientation and presence only, no detailed strategy.'}
                  {selectedTier === 'activator' && 'Standard access. Light pattern recognition, 7-day Echo Memory.'}
                  {selectedTier === 'navigator' && 'Full Path OS. All agents, 30-day Echo, VIX-scaled responses.'}
                  {selectedTier === 'administrator' && 'Complete access including system diagnostics.'}
                </>
              )}
            </div>

            <textarea
              className="editor-textarea"
              value={editContent}
              onChange={(e) => handleContentChange(e.target.value)}
              placeholder="Enter prompt instructions..."
              spellCheck={false}
            />

            <div className="editor-footer">
              <span className="char-count">{editContent.length} characters</span>
              <span className="line-count">{editContent.split('\n').length} lines</span>
            </div>
          </div>
        </div>
      </div>

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .admin-vexy-page {
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

  .header-actions {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .admin-header h1 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
    background: linear-gradient(135deg, #c084fc, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
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

  .save-btn {
    padding: 0.5rem 1rem;
    background: linear-gradient(135deg, #7c3aed, #6366f1);
    border: none;
    border-radius: 0.5rem;
    color: white;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .save-btn:hover:not(:disabled) { opacity: 0.9; }
  .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .reset-btn {
    padding: 0.5rem 1rem;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 0.5rem;
    color: #f87171;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .reset-btn:hover:not(:disabled) { background: rgba(239, 68, 68, 0.2); }
  .reset-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .save-message {
    font-size: 0.875rem;
    padding: 0.25rem 0.75rem;
    border-radius: 0.25rem;
  }

  .save-message.success { color: #22c55e; background: rgba(34, 197, 94, 0.1); }
  .save-message.error { color: #f87171; background: rgba(239, 68, 68, 0.1); }

  /* Tab Navigation */
  .tab-nav {
    display: flex;
    gap: 0.25rem;
    padding: 0.25rem;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 0.5rem;
    margin-bottom: 1.5rem;
    width: fit-content;
  }

  .tab-btn {
    padding: 0.5rem 1rem;
    background: none;
    border: none;
    border-radius: 0.375rem;
    color: #71717a;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .tab-btn:hover { color: #a1a1aa; }
  .tab-btn.active {
    background: rgba(255, 255, 255, 0.08);
    color: #f1f5f9;
  }

  /* Content Layout */
  .content-layout {
    display: grid;
    grid-template-columns: 240px 1fr;
    gap: 1.5rem;
    min-height: calc(100vh - 180px);
  }

  /* Sidebar */
  .sidebar {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    padding: 1rem;
    height: fit-content;
  }

  .sidebar-header {
    font-size: 0.75rem;
    font-weight: 600;
    color: #a1a1aa;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
  }

  .sidebar-desc {
    font-size: 0.75rem;
    color: #52525b;
    margin-bottom: 1rem;
    line-height: 1.4;
  }

  .sidebar-items {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .sidebar-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 0.75rem;
    background: none;
    border: 1px solid transparent;
    border-radius: 0.5rem;
    color: #a1a1aa;
    font-size: 0.875rem;
    text-align: left;
    cursor: pointer;
    transition: all 0.15s;
  }

  .sidebar-item:hover {
    background: rgba(255, 255, 255, 0.03);
    color: #e4e4e7;
  }

  .sidebar-item.active {
    background: rgba(124, 58, 237, 0.1);
    border-color: rgba(124, 58, 237, 0.3);
    color: #c4b5fd;
  }

  .item-icon { font-size: 1rem; }
  .item-name { flex: 1; }

  .custom-badge {
    font-size: 0.625rem;
    padding: 0.125rem 0.375rem;
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    border-radius: 0.25rem;
    font-weight: 500;
  }

  /* Editor Panel */
  .editor-panel {
    background: rgba(24, 24, 27, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 0.75rem;
    display: flex;
    flex-direction: column;
  }

  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .editor-title h2 {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
  }

  .customized-indicator {
    font-size: 0.75rem;
    color: #22c55e;
    margin-top: 0.25rem;
    display: block;
  }

  .unsaved-indicator {
    font-size: 0.75rem;
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.1);
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
  }

  .editor-description {
    padding: 0.75rem 1.25rem;
    font-size: 0.8125rem;
    color: #71717a;
    background: rgba(255, 255, 255, 0.02);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }

  .editor-textarea {
    flex: 1;
    padding: 1rem 1.25rem;
    background: transparent;
    border: none;
    color: #e4e4e7;
    font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
    font-size: 0.8125rem;
    line-height: 1.6;
    resize: none;
    min-height: 500px;
  }

  .editor-textarea:focus {
    outline: none;
  }

  .editor-textarea::placeholder {
    color: #52525b;
  }

  .editor-footer {
    display: flex;
    gap: 1rem;
    padding: 0.75rem 1.25rem;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(255, 255, 255, 0.02);
  }

  .char-count, .line-count {
    font-size: 0.75rem;
    color: #52525b;
  }

  @media (max-width: 768px) {
    .content-layout {
      grid-template-columns: 1fr;
    }

    .sidebar {
      order: 2;
    }

    .editor-panel {
      order: 1;
    }
  }
`;
