/**
 * MELDashboard - Full MEL effectiveness dashboard.
 *
 * Shows detailed effectiveness percentages with progress bars,
 * state indicators, and global structure integrity.
 */

import type { MELSnapshot, MELModelScore, ModelState } from '../hooks/useMEL';
import { getStateColor, getTrendArrow } from '../hooks/useMEL';

// Coherence state colors - defined at module scope for performance
const COHERENCE_STATE_COLORS: Record<string, string> = {
  STABLE: '#22c55e',
  MIXED: '#f59e0b',
  COLLAPSING: '#ef4444',
  RECOVERED: '#3b82f6',
};

interface MELDashboardProps {
  snapshot: MELSnapshot;
  onClose: () => void;
}

export default function MELDashboard({ snapshot, onClose }: MELDashboardProps) {
  const {
    global_structure_integrity,
    coherence_state,
    cross_model_coherence,
    event_flags,
    session,
  } = snapshot;

  // Determine global state
  const globalState: ModelState =
    global_structure_integrity >= 70 ? 'VALID' :
    global_structure_integrity >= 50 ? 'DEGRADED' : 'REVOKED';

  return (
    <div className="mel-dashboard-overlay" onClick={onClose}>
      <div className="mel-dashboard" onClick={(e) => e.stopPropagation()}>
        <div className="mel-dashboard-header">
          <h2>MEL SCORES</h2>
          <span className="mel-dashboard-subtitle">Model Effectiveness Layer</span>
          <button className="mel-dashboard-close" onClick={onClose}>×</button>
        </div>

        <div className="mel-dashboard-question">
          Are Market Models Valid Today?
        </div>

        <div className="mel-dashboard-content">
          {/* Individual Models */}
          <div className="mel-models-section">
            <ModelRow
              label="Gamma / Dealer Positioning"
              score={snapshot.gamma}
            />
            <ModelRow
              label="Volume Profile / Auction"
              score={snapshot.volume_profile}
            />
            <ModelRow
              label="Liquidity / Microstructure"
              score={snapshot.liquidity}
            />
            <ModelRow
              label="Volatility Regime"
              score={snapshot.volatility}
            />
            <ModelRow
              label="Session / Time-of-Day"
              score={snapshot.session_structure}
            />
            <CoherenceRow
              coherence={cross_model_coherence}
              state={coherence_state}
            />
          </div>

          {/* Global Integrity Gauge */}
          <div className="mel-global-section">
            <div className="mel-global-gauge">
              <div
                className={`mel-global-circle mel-state-${globalState.toLowerCase()}`}
                style={{
                  '--integrity': `${global_structure_integrity}%`,
                  background: `conic-gradient(${getStateColor(globalState)} ${global_structure_integrity * 3.6}deg, #333 0deg)`,
                } as React.CSSProperties}
              >
                <div className="mel-global-inner">
                  <span className="mel-global-value">
                    {global_structure_integrity.toFixed(0)}%
                  </span>
                  <span className="mel-global-label">GLOBAL<br/>STRUCTURE<br/>INTEGRITY</span>
                </div>
              </div>
            </div>

            {/* Interpretation */}
            <div className="mel-interpretation">
              {global_structure_integrity >= 70 && (
                <span className="mel-interp-valid">Structure present, models trustworthy</span>
              )}
              {global_structure_integrity >= 50 && global_structure_integrity < 70 && (
                <span className="mel-interp-degraded">Partial structure, selective trust</span>
              )}
              {global_structure_integrity < 50 && (
                <span className="mel-interp-revoked">Structure absent, no-trade conditions</span>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="mel-dashboard-footer">
            {event_flags.length > 0 && (
              <span className="mel-footer-events">
                EVENT FLAGS: [{event_flags.join(', ')}]
              </span>
            )}
            <span className="mel-footer-session">
              SESSION: {session}
            </span>
            <span className="mel-footer-timestamp">
              {new Date(snapshot.timestamp_utc).toLocaleTimeString()}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

interface ModelRowProps {
  label: string;
  score: MELModelScore;
}

function ModelRow({ label, score }: ModelRowProps) {
  const { effectiveness, state, trend } = score;
  const color = getStateColor(state);
  const trendArrow = getTrendArrow(trend);

  return (
    <div className={`mel-model-row mel-state-${state.toLowerCase()}`}>
      <span className="mel-model-name">{label}</span>
      <div className="mel-model-bar-container">
        <div
          className="mel-model-bar"
          style={{
            width: `${effectiveness}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span className="mel-model-pct" style={{ color }}>
        {effectiveness.toFixed(0)}%
      </span>
      <span className="mel-model-state" style={{ color }}>
        {state}
      </span>
      <span className="mel-model-trend">{trendArrow}</span>
    </div>
  );
}

interface CoherenceRowProps {
  coherence: number;
  state: string;
}

function CoherenceRow({ coherence, state }: CoherenceRowProps) {
  const color = COHERENCE_STATE_COLORS[state] || '#666';

  return (
    <div className={`mel-model-row mel-coherence-row`}>
      <span className="mel-model-name">Cross-Model Coherence</span>
      <div className="mel-model-bar-container">
        <div
          className="mel-model-bar"
          style={{
            width: `${coherence}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span className="mel-model-pct" style={{ color }}>
        {coherence.toFixed(0)}%
      </span>
      <span className="mel-model-state" style={{ color }}>
        {state}
      </span>
      <span className="mel-model-trend">
        {state === 'COLLAPSING' ? '↓' : state === 'RECOVERED' ? '↑' : '→'}
      </span>
    </div>
  );
}
