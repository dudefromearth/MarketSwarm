/**
 * RoutineDrawer v1 - An attentional container
 *
 * "Enter this space, notice what's here, leave when you're ready."
 *
 * This drawer:
 * - hosts Vexy content and Fundamental Acts
 * - does not manage session state
 * - does not signal readiness, progress, or completion
 *
 * It cannot tell you:
 * - whether a trade will be taken
 * - whether you are "ready"
 * - whether preparation was "enough"
 * - whether the routine was "completed"
 *
 * It is contextual, not transactional.
 */

import { useState, useEffect, useRef } from 'react';
import './RoutineDrawer.css';

import VexyRoutinePanel from './VexyRoutinePanel';
import FundamentalActLens, { FUNDAMENTAL_ACT_PROMPTS } from './FundamentalActLens';
import MicroPause from './MicroPause';

export interface MarketContext {
  spxPrice?: number | null;
  vixLevel?: number | null;
}

interface RoutineDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  marketContext?: MarketContext;
}

export default function RoutineDrawer({ isOpen, onClose, marketContext }: RoutineDrawerProps) {
  const [actNotes, setActNotes] = useState<Record<string, string>>({});
  const [showPause, setShowPause] = useState(false);
  const [pauseText, setPauseText] = useState('');
  const wasOpenRef = useRef(false);

  // Load notes from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('routine-act-notes');
    if (saved) {
      try {
        setActNotes(JSON.parse(saved));
      } catch {
        // Ignore
      }
    }
  }, []);

  // Micro-pause on open/close transitions
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      // Opening
      setPauseText('Entering orientation.');
      setShowPause(true);
    } else if (!isOpen && wasOpenRef.current) {
      // Closing
      setPauseText('Leaving routine.');
      setShowPause(true);
    }
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  const handleNoteChange = (id: string, note: string) => {
    const updated = { ...actNotes, [id]: note };
    setActNotes(updated);
    localStorage.setItem('routine-act-notes', JSON.stringify(updated));
  };

  const handlePauseComplete = () => {
    setShowPause(false);
  };

  return (
    <>
      {/* Micro-pause overlay */}
      {showPause && (
        <MicroPause
          text={pauseText}
          durationMs={1200}
          onComplete={handlePauseComplete}
        />
      )}

      <div className={`routine-drawer-container ${isOpen ? 'open' : ''}`}>
        {/* Header - minimal */}
        <div className="routine-header">
          <div className="routine-title">
            <span className="routine-title-icon">🌅</span>
            <span>Routine</span>
          </div>
          <button
            className="routine-close-btn"
            onClick={onClose}
          >
            Close routine
          </button>
        </div>

        {/* Scrollable content - breathing space */}
        <div className="routine-content">
          {/* Vexy Panel - Outlet B */}
          <VexyRoutinePanel isOpen={isOpen} marketContext={marketContext} />

          {/* Spacer */}
          <div className="routine-spacer" />

          {/* Fundamental Act Lenses - just prompts, space, presence */}
          {FUNDAMENTAL_ACT_PROMPTS.map((act, index) => (
            <div key={act.id}>
              <FundamentalActLens
                id={act.id}
                prompt={act.prompt}
                note={actNotes[act.id] || ''}
                onNoteChange={handleNoteChange}
              />
              {index < FUNDAMENTAL_ACT_PROMPTS.length - 1 && (
                <div className="routine-spacer" />
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
