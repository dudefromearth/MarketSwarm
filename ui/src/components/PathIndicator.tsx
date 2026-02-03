/**
 * PathIndicator - FOTW Path Stage Indicator
 *
 * A quiet, persistent indicator showing the 5-stage path.
 * Layer 1: Collapsed view with dots and current stage name
 * Layer 2: Expanded panel with full stage content
 *
 * Design principles:
 * - Informs without interrupting
 * - Reminds without nagging
 * - Preserves user sovereignty
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
  const { currentStage, expanded, toggleExpanded, setExpanded } = usePath();
  const [selectedStage, setSelectedStage] = useState<Stage>(currentStage);
  const [videoOpen, setVideoOpen] = useState(false);

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

  // Collapsed view
  return (
    <div
      className="path-indicator path-indicator-collapsed"
      onClick={handleExpand}
      title="Click to expand path guide"
    >
      {/* Stage dots */}
      <div className="path-dots">
        {STAGE_ORDER.map((stage, index) => (
          <span key={stage}>
            <span className={`path-dot${currentStage === stage ? ' active' : ''}`}>
              {STAGES[stage].icon}
            </span>
            {index < STAGE_ORDER.length - 1 && <span className="path-connector" />}
          </span>
        ))}
      </div>

      {/* Current stage name */}
      <div className="path-stage-name">
        You're in {STAGES[currentStage].title}
      </div>
    </div>
  );
}
