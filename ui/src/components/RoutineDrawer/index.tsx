/**
 * RoutineDrawer v1 - Presence-Based Panel
 *
 * "Enter this space, notice what's here, leave when you're ready."
 *
 * Two parallel domains:
 * - Personal Readiness: soft optional selections + friction markers
 * - Market Readiness: read-only awareness with lens language
 *
 * Philosophy:
 * - Help the trader arrive, not complete tasks
 * - Train how to begin, not what to do
 * - User should feel like they're "entering a space," not "reading a report"
 *
 * This drawer:
 * - Cannot tell you whether a trade will be taken
 * - Cannot tell you whether you are "ready"
 * - Cannot tell you whether preparation was "enough"
 * - Is contextual, not transactional
 */

import { useState, useEffect, useRef } from 'react';
import './RoutineDrawer.css';
import WhatsNew from '../WhatsNew';

import VexyRoutinePanel from './VexyRoutinePanel';
import ReadinessTagSelector from './ReadinessTagSelector';
import StateOfTheMarket from './StateOfTheMarket';
import MicroPause from './MicroPause';
import { useRoutineState } from '../../hooks/useRoutineState';
import { useReadinessTags } from '../../hooks/useReadinessTags';

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
  const [showPause, setShowPause] = useState(false);
  const [pauseText, setPauseText] = useState('');
  const wasOpenRef = useRef(false);

  const {
    markRoutineOpened,
    markOrientationShown,
    setAskVexyOpen,
  } = useRoutineState();

  const {
    readinessTags,
    selectedTagIds,
    toggleReadinessTag,
    loading: readinessLoading,
  } = useReadinessTags();

  // Micro-pause on open/close transitions
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      // Opening
      setPauseText('Entering orientation.');
      setShowPause(true);
      markRoutineOpened();
    } else if (!isOpen && wasOpenRef.current) {
      // Closing
      setPauseText('Leaving routine.');
      setShowPause(true);
    }
    wasOpenRef.current = isOpen;
  }, [isOpen, markRoutineOpened]);

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
            <WhatsNew area="routine" />
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
          {/* Vexy Panel - Orientation + ProcessEcho + Ask Vexy */}
          <VexyRoutinePanel
            isOpen={isOpen}
            marketContext={marketContext}
            onOrientationShown={markOrientationShown}
            onAskVexyOpenChange={setAskVexyOpen}
          />

          {/* Domain separation */}
          <div className="routine-domain-spacer" />

          {/* Personal Readiness Domain */}
          <ReadinessTagSelector
            readinessTags={readinessTags}
            selectedTagIds={selectedTagIds}
            onToggleTag={toggleReadinessTag}
            loading={readinessLoading}
          />

          {/* Domain separation */}
          <div className="routine-domain-spacer" />

          {/* State of the Market */}
          <StateOfTheMarket isOpen={isOpen} />
        </div>
      </div>
    </>
  );
}
