// src/components/JournalEntryEditor.tsx
import { useState, useEffect } from 'react';
import type { JournalEntry } from '../hooks/useJournal';

interface JournalEntryEditorProps {
  date: string;
  entry: JournalEntry | null;
  loading: boolean;
  onSave: (content: string, isPlaybook: boolean) => Promise<boolean>;
}

const WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function formatDate(dateStr: string): string {
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const weekday = WEEKDAY_NAMES[date.getDay()];
  const monthName = MONTH_NAMES[month - 1];
  return `${weekday}, ${monthName} ${day}, ${year}`;
}

export default function JournalEntryEditor({
  date,
  entry,
  loading,
  onSave,
}: JournalEntryEditorProps) {
  const [content, setContent] = useState('');
  const [isPlaybook, setIsPlaybook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Sync form state with entry data
  useEffect(() => {
    if (entry) {
      setContent(entry.content || '');
      setIsPlaybook(entry.is_playbook_material);
    } else {
      setContent('');
      setIsPlaybook(false);
    }
    setDirty(false);
  }, [entry, date]);

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setContent(e.target.value);
    setDirty(true);
  };

  const handlePlaybookChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setIsPlaybook(e.target.checked);
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    const success = await onSave(content, isPlaybook);
    setSaving(false);
    if (success) {
      setDirty(false);
    }
  };

  // Keyboard shortcut: Cmd/Ctrl + S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (dirty && !saving) {
          handleSave();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [dirty, saving, content, isPlaybook]);

  if (loading) {
    return (
      <div className="journal-entry-editor">
        <div className="entry-header">
          <h3>{formatDate(date)}</h3>
        </div>
        <div className="entry-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="journal-entry-editor">
      <div className="entry-header">
        <h3>{formatDate(date)}</h3>
        {entry && (
          <span className="entry-meta">
            Last updated: {new Date(entry.updated_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="entry-body">
        <textarea
          className="entry-content"
          value={content}
          onChange={handleContentChange}
          placeholder="What happened today? What did you learn?"
          autoFocus
        />
      </div>

      <div className="entry-footer">
        <label className="playbook-toggle">
          <input
            type="checkbox"
            checked={isPlaybook}
            onChange={handlePlaybookChange}
          />
          <span>Playbook Material</span>
        </label>

        <div className="entry-actions">
          {dirty && <span className="unsaved-indicator">Unsaved changes</span>}
          <button
            className="save-btn"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {entry && entry.trade_refs && entry.trade_refs.length > 0 && (
        <div className="entry-trade-refs">
          <h4>Linked Trades</h4>
          <ul>
            {entry.trade_refs.map(ref => (
              <li key={ref.id}>
                Trade: {ref.trade_id}
                {ref.note && <span className="ref-note"> - {ref.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {entry && entry.attachments && entry.attachments.length > 0 && (
        <div className="entry-attachments">
          <h4>Attachments</h4>
          <ul>
            {entry.attachments.map(att => (
              <li key={att.id}>
                {att.filename}
                {att.file_size && <span className="att-size"> ({Math.round(att.file_size / 1024)}KB)</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
