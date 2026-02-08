/**
 * WorkflowDrawers - Left-to-Right Trading Workflow Drawers
 *
 * Implements the conceptual drawer system from the FOTW design:
 * - Left Drawer (Routine): Preparation and grounding - warm/yellow tones
 * - Right Drawer (Process): Reflection and learning - cool/blue tones
 *
 * Design principles:
 * - Never force themselves open
 * - Gently hint via subtle glow when appropriate
 * - Support the trader's daily routine without policing them
 */

import { useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import './WorkflowDrawers.css';

interface WorkflowDrawersProps {
  /** Content for the main action surface (center) - optional, can be used standalone */
  children?: ReactNode;

  /** Content for the Routine drawer (left) */
  routineContent?: ReactNode;

  /** Content for the Process drawer (right) */
  processContent?: ReactNode;

  /** Whether to show a subtle glow hint on the Routine drawer */
  routineHint?: boolean;

  /** Whether to show a subtle glow hint on the Process drawer */
  processHint?: boolean;

  /** Current workflow phase for visual emphasis */
  currentPhase?: 'routine' | 'analysis' | 'selection' | 'decision' | 'process';
}

export default function WorkflowDrawers({
  children,
  routineContent,
  processContent,
  routineHint = false,
  processHint = false,
  currentPhase = 'analysis',
}: WorkflowDrawersProps) {
  const [routineOpen, setRoutineOpen] = useState(false);
  const [processOpen, setProcessOpen] = useState(false);

  // Close drawers on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setRoutineOpen(false);
        setProcessOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="workflow-container">
      {/* Left Drawer Tab - Routine */}
      <div
        className={`drawer-tab drawer-tab-left ${routineOpen ? 'open' : ''} ${routineHint ? 'hint' : ''} ${currentPhase === 'routine' ? 'active-phase' : ''}`}
        onClick={() => setRoutineOpen(!routineOpen)}
      >
        <span className="drawer-tab-label">Routine</span>
      </div>

      {/* Left Drawer - Routine (Warm tones) */}
      <div className={`drawer drawer-left ${routineOpen ? 'open' : ''}`}>
        <div className="drawer-header">
          <h2>Routine</h2>
          <span className="drawer-subtitle">Preparation & Grounding</span>
          <button className="drawer-close" onClick={() => setRoutineOpen(false)}>
            &times;
          </button>
        </div>
        <div className="drawer-content">
          {routineContent || (
            <div className="drawer-placeholder">
              <p className="drawer-question">Am I ready to engage the market today?</p>
              <ul className="routine-checklist">
                <li>Review overnight action</li>
                <li>Check volatility regime</li>
                <li>Note open positions</li>
                <li>Set daily intention</li>
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Main Action Surface (Center - Neutral tones) - only rendered if children provided */}
      {children && (
        <div className="action-surface">
          {children}
        </div>
      )}

      {/* Right Drawer Tab - Process */}
      <div
        className={`drawer-tab drawer-tab-right ${processOpen ? 'open' : ''} ${processHint ? 'hint' : ''} ${currentPhase === 'process' ? 'active-phase' : ''}`}
        onClick={() => setProcessOpen(!processOpen)}
      >
        <span className="drawer-tab-label">Process</span>
      </div>

      {/* Right Drawer - Process (Cool tones) */}
      <div className={`drawer drawer-right ${processOpen ? 'open' : ''}`}>
        <div className="drawer-header">
          <h2>Process</h2>
          <span className="drawer-subtitle">Reflection & Learning</span>
          <button className="drawer-close" onClick={() => setProcessOpen(false)}>
            &times;
          </button>
        </div>
        <div className="drawer-content">
          {processContent || (
            <div className="drawer-placeholder">
              <p className="drawer-question">What did I learn today?</p>
              <ul className="process-checklist">
                <li>Review trade log</li>
                <li>Journal insights</li>
                <li>Update playbooks</li>
                <li>Plan tomorrow</li>
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Overlay for closing drawers */}
      {(routineOpen || processOpen) && (
        <div
          className="drawer-overlay"
          onClick={() => {
            setRoutineOpen(false);
            setProcessOpen(false);
          }}
        />
      )}
    </div>
  );
}
