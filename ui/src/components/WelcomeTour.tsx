/**
 * WelcomeTour - First-time welcome modal
 *
 * The only moment where the system addresses the user directly.
 * After this, it steps aside and waits.
 *
 * Butterfly avatar sequence:
 * 1. Modal appears
 * 2. Butterfly briefly appears (teaser), then fades out
 * 3. User clicks Begin
 * 4. Butterfly reappears as handoff cue
 * 5. Modal fades out
 * 6. Brief pause
 * 7. Butterfly fades into bottom-right corner of dashboard
 */

import { useState, useEffect } from 'react';
import { usePath } from '../contexts/PathContext';
import { WELCOME_CONTENT } from '../constants/pathContent';

/** Butterfly SVG component - reusable */
function ButterflyAvatar({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      className={className}
      aria-hidden="true"
    >
      <g className="butterfly-shape">
        {/* Left wing */}
        <ellipse cx="18" cy="24" rx="10" ry="14" fill="currentColor" opacity="0.6" />
        {/* Right wing */}
        <ellipse cx="30" cy="24" rx="10" ry="14" fill="currentColor" opacity="0.6" />
        {/* Body */}
        <ellipse cx="24" cy="24" rx="3" ry="12" fill="currentColor" opacity="0.9" />
        {/* Wing details */}
        <ellipse cx="16" cy="20" rx="4" ry="5" fill="currentColor" opacity="0.3" />
        <ellipse cx="32" cy="20" rx="4" ry="5" fill="currentColor" opacity="0.3" />
        <ellipse cx="16" cy="28" rx="3" ry="4" fill="currentColor" opacity="0.25" />
        <ellipse cx="32" cy="28" rx="3" ry="4" fill="currentColor" opacity="0.25" />
      </g>
    </svg>
  );
}

export default function WelcomeTour() {
  const { showTour, transitionPhase, beginTourDismiss } = usePath();
  const [showTeaser, setShowTeaser] = useState(false);
  const [teaserFading, setTeaserFading] = useState(false);

  // Brief teaser: butterfly appears then fades after modal loads
  useEffect(() => {
    if (showTour && transitionPhase === 'idle') {
      // Show teaser after a short delay
      const showTimer = setTimeout(() => {
        setShowTeaser(true);
      }, 800);

      // Start fading after it's been visible
      const fadeTimer = setTimeout(() => {
        setTeaserFading(true);
      }, 2000);

      // Hide completely
      const hideTimer = setTimeout(() => {
        setShowTeaser(false);
        setTeaserFading(false);
      }, 2500);

      return () => {
        clearTimeout(showTimer);
        clearTimeout(fadeTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [showTour, transitionPhase]);

  // Don't render if tour is not showing
  if (!showTour) {
    return null;
  }

  // Determine CSS classes based on transition phase
  const overlayClass = `welcome-tour-overlay${
    transitionPhase === 'fading-out' ? ' fading-out' : ''
  }`;
  const modalClass = `welcome-tour-modal${
    transitionPhase === 'fading-out' ? ' fading-out' : ''
  }`;

  return (
    <div className={overlayClass}>
      <div className={modalClass} onClick={e => e.stopPropagation()}>
        <div className="welcome-tour-content">
          <h1 className="welcome-tour-headline">{WELCOME_CONTENT.headline}</h1>

          <div className="welcome-tour-video">
            {WELCOME_CONTENT.videoPlaceholder}
          </div>

          <div className="welcome-tour-text">
            <p>{WELCOME_CONTENT.intro}</p>
            <p>{WELCOME_CONTENT.pathIntro}</p>
            <div className="welcome-tour-path">
              {WELCOME_CONTENT.pathSummary}
            </div>
            {WELCOME_CONTENT.philosophy.map((line, i) => (
              <p key={i} className="welcome-tour-philosophy">{line}</p>
            ))}
          </div>

          <div className="welcome-tour-actions">
            <button
              className="welcome-tour-btn primary"
              onClick={beginTourDismiss}
              disabled={transitionPhase !== 'idle'}
            >
              {WELCOME_CONTENT.beginButton}
            </button>
          </div>
        </div>

        {/* Teaser: butterfly appears briefly when modal first shows */}
        {showTeaser && transitionPhase === 'idle' && (
          <div className={`welcome-butterfly-teaser${teaserFading ? ' fading' : ''}`}>
            <ButterflyAvatar className="teaser-butterfly-svg" />
          </div>
        )}

        {/* Handoff cue: butterfly reappears before modal fades */}
        {(transitionPhase === 'pre-dismiss' || transitionPhase === 'fading-out') && (
          <div className="welcome-butterfly-handoff">
            <ButterflyAvatar className="handoff-butterfly-svg" />
          </div>
        )}
      </div>
    </div>
  );
}
