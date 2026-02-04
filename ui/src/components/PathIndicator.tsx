/**
 * PathIndicator - FOTW Butterfly Avatar
 *
 * A quiet, ambient presence in the bottom-right corner.
 * ~0.5" diameter stylized butterfly bubble.
 *
 * Behavior:
 * - Dim when idle (~0.35 opacity)
 * - Brightens when mouse gets close (~0.7)
 * - Full opacity on hover (1.0)
 * - Click to expand the path panel
 *
 * After welcome modal:
 * - Fades in gently after a pause
 * - No motion, no greeting
 * - The silence is the point
 */

import { useState } from 'react';
import { usePath } from '../contexts/PathContext';
import {
  STAGES,
  STAGE_ORDER,
  PATH_PHILOSOPHY,
  type Stage,
} from '../constants/pathContent';

export default function PathIndicator() {
  const {
    currentStage,
    expanded,
    toggleExpanded,
    setExpanded,
    indicatorVisible,
    transitionPhase,
  } = usePath();
  const [selectedStage, setSelectedStage] = useState<Stage>(currentStage);
  const [videoOpen, setVideoOpen] = useState(false);

  // Don't render until indicator should be visible
  if (!indicatorVisible) {
    return null;
  }

  // When expanding, show the current stage
  const handleExpand = () => {
    if (!expanded) {
      setSelectedStage(currentStage);
    }
    toggleExpanded();
  };

  // Close panel
  const handleClose = () => {
    setExpanded(false);
    setVideoOpen(false);
  };

  // Get stage content
  const stageContent = STAGES[selectedStage];

  // Determine fade-in class
  const fadeClass = transitionPhase === 'fading-in' ? ' fading-in' : '';

  if (expanded) {
    return (
      <div className="path-indicator path-indicator-expanded">
        {/* Header */}
        <div className="path-expanded-header">
          <span className="path-expanded-title">The Path</span>
          <button className="path-close-btn" onClick={handleClose}>
            ×
          </button>
        </div>

        {/* Philosophy */}
        <div className="path-philosophy">
          <p>{PATH_PHILOSOPHY}</p>
        </div>

        {/* Stage tabs */}
        <div className="path-stage-tabs">
          {STAGE_ORDER.map(stage => (
            <button
              key={stage}
              className={`path-stage-tab${selectedStage === stage ? ' active' : ''}${currentStage === stage ? ' current' : ''}`}
              onClick={() => {
                setSelectedStage(stage);
                setVideoOpen(false);
              }}
              title={STAGES[stage].title}
            >
              <span className="path-tab-icon">{STAGES[stage].icon}</span>
              <span className="path-tab-label">
                {stage === currentStage ? '●' : '○'}
              </span>
            </button>
          ))}
        </div>

        {/* Stage content */}
        <div className="path-stage-content">
          {/* Title */}
          <div className="path-content-section">
            <h3 style={{ margin: 0, fontSize: 14, color: '#e5e5e5' }}>
              {stageContent.icon} {stageContent.title}
            </h3>
          </div>

          {/* What this stage is for */}
          <div className="path-content-section">
            <div className="path-content-label">What this stage is for</div>
            <p className="path-content-text">{stageContent.description}</p>
          </div>

          {/* What not to do */}
          <div className="path-content-section not-yet">
            <div className="path-content-label">What not to do</div>
            <p className="path-content-text" style={{ whiteSpace: 'pre-line' }}>
              {stageContent.notYet}
            </p>
          </div>

          {/* Tools that belong here */}
          <div className="path-content-section">
            <div className="path-content-label">Tools that belong here</div>
            <ul className="path-tools-list">
              {stageContent.tools.map(tool => (
                <li key={tool}>{tool}</li>
              ))}
            </ul>
          </div>

          {/* How this feeds forward */}
          <div className="path-content-section">
            <div className="path-content-label">How this feeds forward</div>
            <p className="path-content-text">{stageContent.feedsInto}</p>
          </div>

          {/* Optional video section */}
          {stageContent.videoId && (
            <div className="path-content-section">
              <button
                className={`path-video-toggle${videoOpen ? ' open' : ''}`}
                onClick={() => setVideoOpen(!videoOpen)}
              >
                <span className="toggle-icon">▶</span>
                <span>2-min context video</span>
              </button>
              {videoOpen && (
                <div className="path-video-content">
                  <div className="path-video-placeholder">
                    Video: Why this stage exists
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Collapsed view - butterfly avatar bubble
  return (
    <div
      className={`path-avatar${fadeClass}`}
      onClick={handleExpand}
    >
      <svg
        viewBox="0 0 48 48"
        className="path-avatar-svg"
        aria-label="Path guide"
      >
        {/* Stylized butterfly - abstract, geometric */}
        <g className="butterfly-shape">
          {/* Left wing */}
          <ellipse
            cx="18"
            cy="24"
            rx="10"
            ry="14"
            fill="currentColor"
            opacity="0.6"
          />
          {/* Right wing */}
          <ellipse
            cx="30"
            cy="24"
            rx="10"
            ry="14"
            fill="currentColor"
            opacity="0.6"
          />
          {/* Body */}
          <ellipse
            cx="24"
            cy="24"
            rx="3"
            ry="12"
            fill="currentColor"
            opacity="0.9"
          />
          {/* Wing details - subtle curves */}
          <ellipse
            cx="16"
            cy="20"
            rx="4"
            ry="5"
            fill="currentColor"
            opacity="0.3"
          />
          <ellipse
            cx="32"
            cy="20"
            rx="4"
            ry="5"
            fill="currentColor"
            opacity="0.3"
          />
          <ellipse
            cx="16"
            cy="28"
            rx="3"
            ry="4"
            fill="currentColor"
            opacity="0.25"
          />
          <ellipse
            cx="32"
            cy="28"
            rx="3"
            ry="4"
            fill="currentColor"
            opacity="0.25"
          />
        </g>
      </svg>
    </div>
  );
}
