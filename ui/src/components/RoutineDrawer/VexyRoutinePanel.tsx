/**
 * VexyRoutinePanel - Single authoritative voice for Routine context
 *
 * Contains:
 * - RoutineBriefing (Orientation - Mode A)
 * - ProcessEcho (quieter, below Orientation)
 * - AskVexyAffordance (Mode B trigger)
 *
 * Rules:
 * - Calm, observational tone only
 * - Silence is first-class
 * - If no content exists, renders minimal
 * - ProcessEcho is QUIETER than Orientation
 */

import RoutineBriefing from './RoutineBriefing';
import ProcessEcho from './ProcessEcho';
import AskVexyAffordance from './AskVexyAffordance';
import type { MarketContext } from './index';

interface VexyRoutinePanelProps {
  isOpen: boolean;
  marketContext?: MarketContext;
  onOrientationShown?: () => void;
}

export default function VexyRoutinePanel({
  isOpen,
  marketContext,
  onOrientationShown,
}: VexyRoutinePanelProps) {
  return (
    <div className="vexy-routine-panel">
      {/* Orientation (Mode A) - may be silent */}
      <RoutineBriefing
        isOpen={isOpen}
        marketContext={marketContext}
        onOrientationShown={onOrientationShown}
      />

      {/* ProcessEcho - quieter weight, below Orientation */}
      <ProcessEcho isOpen={isOpen} />

      {/* Ask Vexy - always visible input */}
      <AskVexyAffordance isOpen={isOpen} />
    </div>
  );
}
