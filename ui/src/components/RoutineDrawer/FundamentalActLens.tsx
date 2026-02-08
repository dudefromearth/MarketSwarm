/**
 * FundamentalActLens - A single attentional invitation
 *
 * Not a section. Not a card. A lens.
 *
 * Rules:
 * - No borders
 * - No headers
 * - No expand/collapse
 * - No icons
 * - No numbering
 *
 * Just text, space, and presence.
 */

import { useState, useEffect, useRef } from 'react';

interface FundamentalActLensProps {
  id: string;
  prompt: string;
  note?: string;
  onNoteChange?: (id: string, note: string) => void;
}

export default function FundamentalActLens({
  id,
  prompt,
  note = '',
  onNoteChange,
}: FundamentalActLensProps) {
  const [localNote, setLocalNote] = useState(note);
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Sync external note
  useEffect(() => {
    setLocalNote(note);
  }, [note]);

  // Autosave after typing stops
  useEffect(() => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    if (localNote !== note && onNoteChange) {
      saveTimeoutRef.current = setTimeout(() => {
        onNoteChange(id, localNote);
      }, 1000);
    }

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [localNote, note, id, onNoteChange]);

  const showNoteField = focused || hovered || localNote.length > 0;

  return (
    <div
      className="fundamental-act-lens"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="fundamental-act-lens-prompt">{prompt}</div>

      <div className={`fundamental-act-lens-note-container ${showNoteField ? 'visible' : ''}`}>
        <textarea
          className="fundamental-act-lens-note"
          value={localNote}
          onChange={(e) => setLocalNote(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="..."
          rows={2}
        />
      </div>
    </div>
  );
}

// Prompts only - titles are invisible metadata
export const FUNDAMENTAL_ACT_PROMPTS = [
  { id: 'arrival', prompt: 'What state did you bring with you today?' },
  { id: 'orientation', prompt: 'What feels different about today?' },
  { id: 'risk', prompt: 'Where does risk feel tight or wide?' },
  { id: 'structure', prompt: 'Which levels feel obvious? Which feel uncertain?' },
  { id: 'readiness', prompt: 'What would a clean decision feel like today?' },
  { id: 'transition', prompt: 'What are you leaving behind as you move forward?' },
];
