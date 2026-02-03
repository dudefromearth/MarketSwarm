/**
 * WelcomeTour - First-time modal for new users
 *
 * Shows once for new users. Skippable. Can be re-triggered from settings.
 * Purpose: Set expectations once, then get out of the way.
 */

import { usePath } from '../contexts/PathContext';
import { WELCOME_CONTENT } from '../constants/pathContent';

export default function WelcomeTour() {
  const { showTour, completeTour } = usePath();

  if (!showTour) {
    return null;
  }

  return (
    <div className="welcome-tour-overlay" onClick={completeTour}>
      <div className="welcome-tour-modal" onClick={e => e.stopPropagation()}>
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
              onClick={completeTour}
            >
              {WELCOME_CONTENT.beginButton}
            </button>
            <button
              className="welcome-tour-btn secondary"
              onClick={completeTour}
            >
              {WELCOME_CONTENT.skipButton}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
