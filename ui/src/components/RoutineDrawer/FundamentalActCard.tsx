/**
 * FundamentalActCard - A single inhabitable state in the Routine field
 *
 * Not a step. Not a task. A lens.
 *
 * Rules:
 * - No completion state
 * - No required interaction
 * - Prompt is a question to hold, not answer
 * - Optional note field, collapsed by default
 */

import { useState, useEffect, useRef } from 'react';

export interface FundamentalAct {
  id: string;
  title: string;
  prompt: string;
}

interface FundamentalActCardProps {
  act: FundamentalAct;
  note?: string;
  onNoteChange?: (actId: string, note: string) => void;
}

export default function FundamentalActCard({
  act,
  note = '',
  onNoteChange,
}: FundamentalActCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [localNote, setLocalNote] = useState(note);
  const [showNoteField, setShowNoteField] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Sync external note changes
  useEffect(() => {
    setLocalNote(note);
  }, [note]);

  // Autosave note after typing stops
  useEffect(() => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    if (localNote !== note && onNoteChange) {
      saveTimeoutRef.current = setTimeout(() => {
        onNoteChange(act.id, localNote);
      }, 1000);
    }

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [localNote, note, act.id, onNoteChange]);

  const handleCardClick = () => {
    setExpanded(!expanded);
  };

  const handleNoteToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowNoteField(!showNoteField);
  };

  return (
    <div
      className={`fundamental-act-card ${expanded ? 'expanded' : ''}`}
      onClick={handleCardClick}
    >
      <div className="fundamental-act-title">{act.title}</div>

      {expanded && (
        <div className="fundamental-act-content">
          <div className="fundamental-act-prompt">{act.prompt}</div>

          {showNoteField ? (
            <textarea
              className="fundamental-act-note"
              value={localNote}
              onChange={(e) => setLocalNote(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              placeholder="Note if you want..."
              rows={2}
            />
          ) : (
            <button
              className="fundamental-act-note-toggle"
              onClick={handleNoteToggle}
            >
              {localNote ? 'view note' : 'add note'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Default Fundamental Acts for v1
export const DEFAULT_FUNDAMENTAL_ACTS: FundamentalAct[] = [
  {
    id: 'arrival',
    title: 'Arrival',
    prompt: 'What state did you bring with you today?',
  },
  {
    id: 'orientation',
    title: 'Orientation',
    prompt: 'What feels different about today?',
  },
  {
    id: 'risk',
    title: 'Risk Framing',
    prompt: 'Where does risk feel tight or wide?',
  },
  {
    id: 'structure',
    title: 'Structure Recognition',
    prompt: 'Which levels feel obvious? Which feel uncertain?',
  },
  {
    id: 'readiness',
    title: 'Readiness',
    prompt: 'What would a clean decision feel like today?',
  },
  {
    id: 'transition',
    title: 'Transition to Action',
    prompt: 'What are you leaving behind as you move forward?',
  },
];
