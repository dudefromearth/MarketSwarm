/**
 * RoutineDrawer - Left-side panel for pre-market preparation
 *
 * "Routine should feel like putting your hands on the table before you trade
 *  — grounding, familiar, and steady."
 */

import './RoutineDrawer.css';
import { useRoutineState } from '../../hooks/useRoutineState';
import { useOpenLoops } from '../../hooks/useOpenLoops';

import RoutineSection from './RoutineSection';
import StateResetSection from './StateResetSection';
import OpenLoopsSection from './OpenLoopsSection';
import MarketContextSection from './MarketContextSection';
import RiskOrientationSection from './RiskOrientationSection';
import IntentDeclarationSection from './IntentDeclarationSection';
import BeginSessionButton from './BeginSessionButton';
import RoutineBriefing from './RoutineBriefing';
import ObserverPanel from '../ObserverPanel';

interface SpotData {
  [symbol: string]: {
    value: number;
    ts: string;
    symbol: string;
    prevClose?: number;
    change?: number;
    changePercent?: number;
  };
}

interface MarketModeData {
  score: number;
  mode: 'compression' | 'transition' | 'expansion';
  ts?: string;
}

interface BiasLfiData {
  directional_strength: number;
  lfi_score: number;
  ts?: string;
}

interface VexyMessage {
  kind: 'epoch' | 'event';
  text: string;
  meta: Record<string, unknown>;
  ts: string;
  voice: string;
}

interface VexyData {
  epoch: VexyMessage | null;
  event: VexyMessage | null;
}

interface RoutineDrawerProps {
  isOpen: boolean;
  vexy: VexyData | null;
  biasLfi: BiasLfiData | null;
  marketMode: MarketModeData | null;
  spot: SpotData;
  onSessionRelease: () => void;
  onCloseDrawer: () => void;
}

export default function RoutineDrawer({
  isOpen,
  vexy,
  biasLfi,
  marketMode,
  spot,
  onSessionRelease,
}: RoutineDrawerProps) {
  const {
    stateReset,
    setStateReset,
    riskOrientation,
    setRiskOrientation,
    intent,
    setIntent,
    sectionsExpanded,
    toggleSection,
    isRoutineComplete,
  } = useRoutineState();

  const openLoops = useOpenLoops();

  const handleBeginSession = () => {
    onSessionRelease();
  };

  return (
    <div className="routine-drawer-container">
      <div className="routine-header">
        <div className="routine-title">
          <span className="routine-title-icon">🌅</span>
          <span>Routine</span>
        </div>
        <div className="routine-status">
          {isRoutineComplete && (
            <span className="routine-complete-badge">Ready</span>
          )}
        </div>
      </div>

      <div className="routine-sections">
        <RoutineSection
          title="State Reset"
          icon="🧘"
          expanded={sectionsExpanded.stateReset}
          onToggle={() => toggleSection('stateReset')}
        >
          <StateResetSection data={stateReset} onChange={setStateReset} />
        </RoutineSection>

        <RoutineSection
          title="Open Loops"
          icon="🔄"
          expanded={sectionsExpanded.openLoops}
          onToggle={() => toggleSection('openLoops')}
          badge={openLoops.totalCount > 0 ? openLoops.totalCount : null}
        >
          <OpenLoopsSection data={openLoops} />
        </RoutineSection>

        <RoutineSection
          title="Market Context"
          icon="📊"
          expanded={sectionsExpanded.marketContext}
          onToggle={() => toggleSection('marketContext')}
        >
          <MarketContextSection
            spot={spot}
            marketMode={marketMode}
            biasLfi={biasLfi}
            vexy={vexy}
          />
        </RoutineSection>

        <RoutineSection
          title="Risk Orientation"
          icon="⚖️"
          expanded={sectionsExpanded.riskOrientation}
          onToggle={() => toggleSection('riskOrientation')}
        >
          <RiskOrientationSection data={riskOrientation} onChange={setRiskOrientation} />
        </RoutineSection>

        <RoutineSection
          title="Intent"
          icon="🎯"
          expanded={sectionsExpanded.intent}
          onToggle={() => toggleSection('intent')}
        >
          <IntentDeclarationSection data={intent} onChange={setIntent} />
        </RoutineSection>

        <RoutineSection
          title="Vexy"
          icon="💬"
          expanded={sectionsExpanded.vexy}
          onToggle={() => toggleSection('vexy')}
        >
          <RoutineBriefing
            isOpen={isOpen}
            spot={spot}
            marketMode={marketMode}
            biasLfi={biasLfi}
            vexy={vexy}
            stateReset={stateReset}
            riskOrientation={riskOrientation}
            intent={intent}
            openLoops={openLoops}
          />
          <div className="routine-vexy-divider">Live Feed</div>
          <div className="routine-vexy-embed">
            <ObserverPanel />
          </div>
        </RoutineSection>
      </div>

      <BeginSessionButton
        isRoutineComplete={isRoutineComplete}
        onBegin={handleBeginSession}
      />
    </div>
  );
}
