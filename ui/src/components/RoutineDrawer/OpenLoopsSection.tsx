/**
 * OpenLoopsSection - Display counts of unresolved commitments
 *
 * "Surface unresolved commitments"
 */

import type { OpenLoops } from '../../hooks/useOpenLoops';

interface OpenLoopsSectionProps {
  data: OpenLoops;
}

export default function OpenLoopsSection({ data }: OpenLoopsSectionProps) {
  const hasLoops = data.totalCount > 0;

  if (!hasLoops) {
    return (
      <div className="routine-loop-empty">
        No open loops - clear to begin fresh
      </div>
    );
  }

  return (
    <div className="routine-loops-list">
      {data.openTrades.length > 0 && (
        <div className="routine-loop-item">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">📈</span>
            <span className="routine-loop-label">Open Trades</span>
          </div>
          <span className="routine-loop-count">{data.openTrades.length}</span>
        </div>
      )}

      {data.expiringSoon.length > 0 && (
        <div className="routine-loop-item routine-loop-warning">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">&#9888;</span>
            <span className="routine-loop-label">{data.expiringSoon.length === 1 ? '1 trade expires' : `${data.expiringSoon.length} trades expire`} within 24h</span>
          </div>
          <span className="routine-loop-count">{data.expiringSoon.length}</span>
        </div>
      )}

      {data.needsSettlement.length > 0 && (
        <div className="routine-loop-item routine-loop-urgent">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">&#10071;</span>
            <span className="routine-loop-label">Needs Settlement</span>
          </div>
          <span className="routine-loop-count">{data.needsSettlement.length}</span>
        </div>
      )}

      {data.unjournaled.length > 0 && (
        <div className="routine-loop-item">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">📝</span>
            <span className="routine-loop-label">Awaiting Journal</span>
          </div>
          <span className="routine-loop-count">{data.unjournaled.length}</span>
        </div>
      )}

      {data.armedAlerts.length > 0 && (
        <div className="routine-loop-item">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">🔔</span>
            <span className="routine-loop-label">Armed Alerts</span>
          </div>
          <span className="routine-loop-count">{data.armedAlerts.length}</span>
        </div>
      )}

      {data.incompleteRetros.length > 0 && (
        <div className="routine-loop-item">
          <div className="routine-loop-item-left">
            <span className="routine-loop-icon">📊</span>
            <span className="routine-loop-label">Incomplete Retros</span>
          </div>
          <span className="routine-loop-count">{data.incompleteRetros.length}</span>
        </div>
      )}
    </div>
  );
}
