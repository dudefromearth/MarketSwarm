// src/components/JournalRetrospectiveEditor.tsx
import { useState, useEffect } from 'react';
import type { Retrospective } from '../hooks/useJournal';

interface JournalRetrospectiveEditorProps {
  type: 'weekly' | 'monthly';
  periodStart: string;
  periodEnd: string;
  retrospective: Retrospective | null;
  loading: boolean;
  onSave: (retro: {
    retro_type: 'weekly' | 'monthly';
    period_start: string;
    period_end: string;
    content: string;
    is_playbook_material: boolean;
  }) => Promise<boolean>;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

function formatPeriod(type: 'weekly' | 'monthly', start: string, end: string): string {
  const [startYear, startMonth, startDay] = start.split('-').map(Number);
  const [, endMonth, endDay] = end.split('-').map(Number);

  if (type === 'weekly') {
    const startStr = `${MONTH_NAMES[startMonth - 1].slice(0, 3)} ${startDay}`;
    const endStr = startMonth === endMonth
      ? `${endDay}`
      : `${MONTH_NAMES[endMonth - 1].slice(0, 3)} ${endDay}`;
    return `Week of ${startStr} - ${endStr}, ${startYear}`;
  } else {
    return `${MONTH_NAMES[startMonth - 1]} ${startYear}`;
  }
}

export default function JournalRetrospectiveEditor({
  type,
  periodStart,
  periodEnd,
  retrospective,
  loading,
  onSave,
}: JournalRetrospectiveEditorProps) {
  const [content, setContent] = useState('');
  const [isPlaybook, setIsPlaybook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Sync form state with retrospective data
  useEffect(() => {
    if (retrospective) {
      setContent(retrospective.content || '');
      setIsPlaybook(retrospective.is_playbook_material);
    } else {
      setContent('');
      setIsPlaybook(false);
    }
    setDirty(false);
  }, [retrospective, periodStart]);

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
    const success = await onSave({
      retro_type: type,
      period_start: periodStart,
      period_end: periodEnd,
      content,
      is_playbook_material: isPlaybook,
    });
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

  const placeholder = type === 'weekly'
    ? 'What patterns emerged this week? What worked? What didn\'t?'
    : 'How did this month go overall? What are the key lessons?';

  if (loading) {
    return (
      <div className="retro-editor">
        <div className="retro-header">
          <h3>{formatPeriod(type, periodStart, periodEnd)}</h3>
        </div>
        <div className="retro-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="retro-editor">
      <div className="retro-header">
        <h3>{formatPeriod(type, periodStart, periodEnd)}</h3>
        {retrospective && (
          <span className="retro-meta">
            Last updated: {new Date(retrospective.updated_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="retro-body">
        <textarea
          className="retro-content"
          value={content}
          onChange={handleContentChange}
          placeholder={placeholder}
          autoFocus
        />
      </div>

      <div className="retro-footer">
        <label className="playbook-toggle">
          <input
            type="checkbox"
            checked={isPlaybook}
            onChange={handlePlaybookChange}
          />
          <span>Playbook Material</span>
        </label>

        <div className="retro-actions">
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
    </div>
  );
}
