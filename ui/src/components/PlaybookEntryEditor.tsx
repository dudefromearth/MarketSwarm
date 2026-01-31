// src/components/PlaybookEntryEditor.tsx
import { useState, useEffect, useCallback } from 'react';
import { usePlaybook, type PlaybookEntry, type PlaybookSourceRef } from '../hooks/usePlaybook';

interface PlaybookEntryEditorProps {
  entry: PlaybookEntry | null;
  loading: boolean;
  isNew: boolean;
  onSave: () => void;
  onDelete: () => void;
  onClose: () => void;
}

const ENTRY_TYPES = [
  { value: 'pattern', label: 'Pattern', description: 'When X conditions exist, Y tends to happen' },
  { value: 'rule', label: 'Rule', description: 'I only do X when Y is true' },
  { value: 'warning', label: 'Warning', description: 'Avoid X — it consistently leads to trouble' },
  { value: 'filter', label: 'Filter', description: 'If X is missing, I pass' },
  { value: 'constraint', label: 'Constraint', description: 'Never exceed X risk under Y conditions' },
];

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'retired', label: 'Retired' },
];

export default function PlaybookEntryEditor({
  entry,
  loading,
  isNew,
  onSave,
  onDelete,
  onClose,
}: PlaybookEntryEditorProps) {
  const playbook = usePlaybook();

  const [title, setTitle] = useState('');
  const [entryType, setEntryType] = useState<string>('pattern');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<string>('draft');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [initialSources, setInitialSources] = useState<Array<{ source_type: string; source_id: string }>>([]);

  // Initialize form from entry or check for distill sources
  useEffect(() => {
    if (entry) {
      setTitle(entry.title);
      setEntryType(entry.entry_type);
      setDescription(entry.description);
      setStatus(entry.status);
      setDirty(false);
    } else if (isNew) {
      // Check for distill sources in session storage
      const sourcesJson = sessionStorage.getItem('playbook_distill_sources');
      if (sourcesJson) {
        try {
          const sources = JSON.parse(sourcesJson);
          setInitialSources(sources);
        } catch {
          // Ignore parse errors
        }
        sessionStorage.removeItem('playbook_distill_sources');
      }
      setTitle('');
      setEntryType('pattern');
      setDescription('');
      setStatus('draft');
      setDirty(false);
    }
  }, [entry, isNew]);

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTitle(e.target.value);
    setDirty(true);
  };

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setEntryType(e.target.value);
    setDirty(true);
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDescription(e.target.value);
    setDirty(true);
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatus(e.target.value);
    setDirty(true);
  };

  const handleSave = useCallback(async () => {
    if (!title.trim()) return;

    setSaving(true);

    if (isNew) {
      const created = await playbook.createEntry({
        title: title.trim(),
        entry_type: entryType,
        description: description,
        status: status,
        sources: initialSources.length > 0 ? initialSources : undefined,
      });

      if (created) {
        setDirty(false);
        setInitialSources([]);
        onSave();
      }
    } else if (entry) {
      const success = await playbook.updateEntry(entry.id, {
        title: title.trim(),
        entry_type: entryType as PlaybookEntry['entry_type'],
        description: description,
        status: status as PlaybookEntry['status'],
      });

      if (success) {
        setDirty(false);
        onSave();
      }
    }

    setSaving(false);
  }, [title, entryType, description, status, isNew, entry, initialSources, playbook, onSave]);

  const handleDelete = useCallback(async () => {
    if (!entry) return;

    setDeleting(true);
    const success = await playbook.deleteEntry(entry.id);
    setDeleting(false);

    if (success) {
      setShowDeleteConfirm(false);
      onDelete();
    }
  }, [entry, playbook, onDelete]);

  const handleRemoveSource = useCallback(async (sourceId: string) => {
    await playbook.removeSource(sourceId);
  }, [playbook]);

  const getSourceLabel = (source: PlaybookSourceRef) => {
    switch (source.source_type) {
      case 'entry':
        return `Journal Entry`;
      case 'retrospective':
        return `Retrospective`;
      case 'trade':
        return `Trade`;
      default:
        return source.source_type;
    }
  };

  if (loading) {
    return (
      <div className="playbook-entry-editor">
        <div className="editor-loading">Loading...</div>
      </div>
    );
  }

  const selectedType = ENTRY_TYPES.find(t => t.value === entryType);

  return (
    <div className="playbook-entry-editor">
      <div className="editor-header">
        <h3>{isNew ? 'New Playbook Entry' : 'Edit Entry'}</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="editor-form">
        <div className="form-group">
          <label>Title</label>
          <input
            type="text"
            value={title}
            onChange={handleTitleChange}
            placeholder="e.g., Never fade the first move"
            className="title-input"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Type</label>
            <select value={entryType} onChange={handleTypeChange} className="type-select">
              {ENTRY_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            {selectedType && (
              <span className="type-hint">{selectedType.description}</span>
            )}
          </div>

          <div className="form-group">
            <label>Status</label>
            <select value={status} onChange={handleStatusChange} className="status-select">
              {STATUS_OPTIONS.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label>Description</label>
          <textarea
            value={description}
            onChange={handleDescriptionChange}
            placeholder="Describe this pattern, rule, or insight in your own words..."
            className="description-textarea"
            rows={8}
          />
        </div>

        {/* Sources */}
        {entry?.sources && entry.sources.length > 0 && (
          <div className="form-group sources-section">
            <label>Source References</label>
            <div className="sources-list">
              {entry.sources.map(source => (
                <div key={source.id} className="source-item">
                  <span className="source-type">{getSourceLabel(source)}</span>
                  <span className="source-id">{source.source_id.slice(0, 8)}...</span>
                  {source.note && <span className="source-note">{source.note}</span>}
                  <button
                    className="remove-source-btn"
                    onClick={() => handleRemoveSource(source.id)}
                    title="Remove source"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <p className="sources-hint">
              These are the journal entries and retrospectives this wisdom was distilled from.
            </p>
          </div>
        )}

        {isNew && initialSources.length > 0 && (
          <div className="form-group sources-section">
            <label>Sources to Link</label>
            <div className="sources-list">
              {initialSources.map((source, idx) => (
                <div key={idx} className="source-item pending">
                  <span className="source-type">{source.source_type}</span>
                  <span className="source-id">{source.source_id.slice(0, 8)}...</span>
                </div>
              ))}
            </div>
            <p className="sources-hint">
              These sources will be linked when you save.
            </p>
          </div>
        )}
      </div>

      <div className="editor-footer">
        <div className="footer-left">
          {!isNew && entry && (
            <>
              {showDeleteConfirm ? (
                <div className="delete-confirm">
                  <span>Delete this entry?</span>
                  <button
                    className="btn-delete-confirm"
                    onClick={handleDelete}
                    disabled={deleting}
                  >
                    {deleting ? 'Deleting...' : 'Yes, delete'}
                  </button>
                  <button
                    className="btn-delete-cancel"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  className="btn-delete"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  Delete
                </button>
              )}
            </>
          )}
        </div>

        <div className="footer-right">
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
          <button
            className="btn-save"
            onClick={handleSave}
            disabled={saving || !title.trim()}
          >
            {saving ? 'Saving...' : isNew ? 'Create Entry' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
