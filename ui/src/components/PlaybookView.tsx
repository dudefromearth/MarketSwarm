// src/components/PlaybookView.tsx
import { useState, useEffect, useCallback } from 'react';
import { usePlaybook } from '../hooks/usePlaybook';
import PlaybookEntryEditor from './PlaybookEntryEditor';
import '../styles/playbook.css';

interface PlaybookViewProps {
  onClose: () => void;
  backLabel?: string;
}

type Tab = 'entries' | 'flagged';
type EntryTypeFilter = '' | 'pattern' | 'rule' | 'warning' | 'filter' | 'constraint';
type StatusFilter = '' | 'draft' | 'active' | 'retired';

const ENTRY_TYPES = [
  { value: 'pattern', label: 'Pattern', description: 'When X conditions exist, Y tends to happen' },
  { value: 'rule', label: 'Rule', description: 'I only do X when Y is true' },
  { value: 'warning', label: 'Warning', description: 'Avoid X — it consistently leads to trouble' },
  { value: 'filter', label: 'Filter', description: 'If X is missing, I pass' },
  { value: 'constraint', label: 'Constraint', description: 'Never exceed X risk under Y conditions' },
];

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  active: 'Active',
  retired: 'Retired',
};

export default function PlaybookView({ onClose, backLabel = 'Back to Trades' }: PlaybookViewProps) {
  const playbook = usePlaybook();

  const [activeTab, setActiveTab] = useState<Tab>('entries');
  const [typeFilter, setTypeFilter] = useState<EntryTypeFilter>('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedFlaggedItems, setSelectedFlaggedItems] = useState<Set<string>>(new Set());

  // Fetch entries on mount and filter change
  useEffect(() => {
    playbook.fetchEntries({
      type: typeFilter || undefined,
      status: statusFilter || undefined,
      search: searchQuery || undefined,
    });
  }, [typeFilter, statusFilter, searchQuery]);

  // Fetch flagged material when tab changes
  useEffect(() => {
    if (activeTab === 'flagged') {
      playbook.fetchFlaggedMaterial();
    }
  }, [activeTab]);

  // Fetch selected entry details
  useEffect(() => {
    if (selectedEntryId) {
      playbook.fetchEntry(selectedEntryId);
    } else {
      playbook.clearEntry();
    }
  }, [selectedEntryId]);

  const handleCreateNew = useCallback(() => {
    setSelectedEntryId(null);
    setIsCreating(true);
  }, []);

  const handleSelectEntry = useCallback((id: string) => {
    setIsCreating(false);
    setSelectedEntryId(id);
  }, []);

  const handleEditorClose = useCallback(() => {
    setIsCreating(false);
    setSelectedEntryId(null);
    playbook.clearEntry();
  }, [playbook]);

  const handleEntrySaved = useCallback(() => {
    playbook.fetchEntries({
      type: typeFilter || undefined,
      status: statusFilter || undefined,
      search: searchQuery || undefined,
    });
  }, [typeFilter, statusFilter, searchQuery, playbook]);

  const handleEntryDeleted = useCallback(() => {
    setSelectedEntryId(null);
    playbook.fetchEntries({
      type: typeFilter || undefined,
      status: statusFilter || undefined,
      search: searchQuery || undefined,
    });
  }, [typeFilter, statusFilter, searchQuery, playbook]);

  const handleToggleFlaggedItem = useCallback((id: string) => {
    setSelectedFlaggedItems(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleDistillSelected = useCallback(() => {
    if (selectedFlaggedItems.size === 0) return;

    // Get the selected items to pass as sources
    const sources: Array<{ source_type: string; source_id: string }> = [];

    selectedFlaggedItems.forEach(id => {
      // Check if it's an entry or retrospective
      const entry = playbook.flaggedMaterial?.entries.find(e => e.id === id);
      if (entry) {
        sources.push({ source_type: 'entry', source_id: id });
      } else {
        const retro = playbook.flaggedMaterial?.retrospectives.find(r => r.id === id);
        if (retro) {
          sources.push({ source_type: 'retrospective', source_id: id });
        }
      }
    });

    // Switch to create mode with sources
    setIsCreating(true);
    setSelectedEntryId(null);
    setActiveTab('entries');

    // Store sources in session for the editor to pick up
    sessionStorage.setItem('playbook_distill_sources', JSON.stringify(sources));
    setSelectedFlaggedItems(new Set());
  }, [selectedFlaggedItems, playbook.flaggedMaterial]);

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'pattern': return '🔄';
      case 'rule': return '📏';
      case 'warning': return '⚠️';
      case 'filter': return '🔍';
      case 'constraint': return '🚧';
      default: return '📝';
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'active': return 'status-active';
      case 'retired': return 'status-retired';
      default: return 'status-draft';
    }
  };

  return (
    <div className="playbook-view">
      <div className="playbook-header">
        <h2>Playbook</h2>
        <div className="playbook-tabs">
          <button
            className={`playbook-tab ${activeTab === 'entries' ? 'active' : ''}`}
            onClick={() => setActiveTab('entries')}
          >
            Entries
          </button>
          <button
            className={`playbook-tab ${activeTab === 'flagged' ? 'active' : ''}`}
            onClick={() => setActiveTab('flagged')}
          >
            Flagged Material
            {playbook.flaggedMaterial && (
              <span className="flagged-count">
                {playbook.flaggedMaterial.entries.length + playbook.flaggedMaterial.retrospectives.length}
              </span>
            )}
          </button>
        </div>
        <button className="btn-back" onClick={onClose}>
          ← {backLabel}
        </button>
      </div>

      <div className="playbook-content">
        {activeTab === 'entries' ? (
          <div className="playbook-entries-layout">
            <div className="playbook-list-section">
              <div className="playbook-filters">
                <select
                  value={typeFilter}
                  onChange={e => setTypeFilter(e.target.value as EntryTypeFilter)}
                  className="filter-select"
                >
                  <option value="">All Types</option>
                  {ENTRY_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <select
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value as StatusFilter)}
                  className="filter-select"
                >
                  <option value="">All Status</option>
                  <option value="active">Active</option>
                  <option value="draft">Draft</option>
                  <option value="retired">Retired</option>
                </select>
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="search-input"
                />
                <button className="btn-new-entry" onClick={handleCreateNew}>
                  + New Entry
                </button>
              </div>

              <div className="playbook-list">
                {playbook.loadingEntries ? (
                  <div className="loading">Loading entries...</div>
                ) : playbook.entries.length === 0 ? (
                  <div className="empty-state">
                    <p>No playbook entries yet.</p>
                    <p className="hint">
                      Create entries from your flagged journal material, or start with a new entry.
                    </p>
                  </div>
                ) : (
                  playbook.entries.map(entry => (
                    <div
                      key={entry.id}
                      className={`playbook-list-item ${selectedEntryId === entry.id ? 'selected' : ''}`}
                      onClick={() => handleSelectEntry(entry.id)}
                    >
                      <span className="entry-type-icon">{getTypeIcon(entry.entry_type)}</span>
                      <div className="entry-info">
                        <span className="entry-title">{entry.title}</span>
                        <span className="entry-meta">
                          <span className={`entry-status ${getStatusClass(entry.status)}`}>
                            {STATUS_LABELS[entry.status]}
                          </span>
                          {entry.source_count !== undefined && entry.source_count > 0 && (
                            <span className="source-count">{entry.source_count} sources</span>
                          )}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="playbook-editor-section">
              {isCreating || selectedEntryId ? (
                <PlaybookEntryEditor
                  entry={isCreating ? null : playbook.currentEntry}
                  loading={playbook.loadingEntry}
                  isNew={isCreating}
                  onSave={handleEntrySaved}
                  onDelete={handleEntryDeleted}
                  onClose={handleEditorClose}
                />
              ) : (
                <div className="editor-placeholder">
                  <p>Select an entry to view or edit, or create a new one.</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flagged-material-layout">
            <div className="flagged-header">
              <p className="flagged-description">
                Items flagged as "Playbook Material" from your journal. Select items to distill into a playbook entry.
              </p>
              {selectedFlaggedItems.size > 0 && (
                <button className="btn-distill" onClick={handleDistillSelected}>
                  Distill {selectedFlaggedItems.size} item{selectedFlaggedItems.size > 1 ? 's' : ''} into Playbook Entry
                </button>
              )}
            </div>

            {playbook.loadingFlagged ? (
              <div className="loading">Loading flagged material...</div>
            ) : !playbook.flaggedMaterial ||
              (playbook.flaggedMaterial.entries.length === 0 &&
                playbook.flaggedMaterial.retrospectives.length === 0) ? (
              <div className="empty-state">
                <p>No flagged material yet.</p>
                <p className="hint">
                  Mark journal entries or retrospectives as "Playbook Material" to see them here.
                </p>
              </div>
            ) : (
              <div className="flagged-list">
                {playbook.flaggedMaterial.entries.length > 0 && (
                  <div className="flagged-section">
                    <h4>Journal Entries</h4>
                    {playbook.flaggedMaterial.entries.map(entry => (
                      <div
                        key={entry.id}
                        className={`flagged-item ${selectedFlaggedItems.has(entry.id) ? 'selected' : ''}`}
                        onClick={() => handleToggleFlaggedItem(entry.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedFlaggedItems.has(entry.id)}
                          onChange={() => {}}
                        />
                        <div className="flagged-item-content">
                          <span className="flagged-date">{entry.entry_date}</span>
                          <span className="flagged-preview">
                            {entry.content?.slice(0, 100) || '(empty)'}
                            {entry.content && entry.content.length > 100 && '...'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {playbook.flaggedMaterial.retrospectives.length > 0 && (
                  <div className="flagged-section">
                    <h4>Retrospectives</h4>
                    {playbook.flaggedMaterial.retrospectives.map(retro => (
                      <div
                        key={retro.id}
                        className={`flagged-item ${selectedFlaggedItems.has(retro.id) ? 'selected' : ''}`}
                        onClick={() => handleToggleFlaggedItem(retro.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedFlaggedItems.has(retro.id)}
                          onChange={() => {}}
                        />
                        <div className="flagged-item-content">
                          <span className="flagged-date">
                            {retro.retro_type === 'weekly' ? 'Week of ' : ''}
                            {retro.period_start}
                          </span>
                          <span className="flagged-type">{retro.retro_type}</span>
                          <span className="flagged-preview">
                            {retro.content?.slice(0, 100) || '(empty)'}
                            {retro.content && retro.content.length > 100 && '...'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {playbook.error && (
        <div className="playbook-error">
          {playbook.error}
          <button onClick={playbook.clearError}>×</button>
        </div>
      )}
    </div>
  );
}
