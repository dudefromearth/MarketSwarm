/**
 * VexyRoutinePanel - Single authoritative voice for Routine context
 *
 * Contains:
 * - RoutineBriefing (morning orientation)
 * - ProcessEcho (delta reflection)
 *
 * Rules:
 * - Calm, observational tone only
 * - Silence is first-class
 * - If no content exists, renders nothing
 */

import RoutineBriefing from './RoutineBriefing';
import ProcessEcho from './ProcessEcho';
import type { MarketContext } from './index';

interface VexyRoutinePanelProps {
  isOpen: boolean;
  marketContext?: MarketContext;
}

export default function VexyRoutinePanel({ isOpen, marketContext }: VexyRoutinePanelProps) {
  return (
    <div className="vexy-routine-panel">
      <div className="vexy-routine-panel-header">
        <span className="vexy-routine-panel-icon">💬</span>
        <span className="vexy-routine-panel-title">Vexy</span>
      </div>
      <div className="vexy-routine-panel-content">
        <RoutineBriefing isOpen={isOpen} marketContext={marketContext} />
        <ProcessEcho isOpen={isOpen} />
      </div>
    </div>
  );
}
