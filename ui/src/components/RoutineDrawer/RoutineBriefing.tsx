/**
 * RoutineBriefing - Vexy's orientation narrative for Routine Mode
 *
 * Fires once when Routine drawer opens.
 * Renders static narrative - no streaming, no live updates.
 * Vexy is stateless and deterministic.
 */

import { useState, useEffect, useRef } from 'react';
import { marked } from 'marked';
import type { StateResetData, RiskOrientationData, IntentDeclarationData } from '../../hooks/useRoutineState';
import type { OpenLoops } from '../../hooks/useOpenLoops';

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

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

interface RoutineBriefingProps {
  isOpen: boolean;
  spot: SpotData;
  marketMode: MarketModeData | null;
  biasLfi: BiasLfiData | null;
  vexy: VexyData | null;
  stateReset: StateResetData;
  riskOrientation: RiskOrientationData;
  intent: IntentDeclarationData;
  openLoops: OpenLoops;
}

interface BriefingResponse {
  briefing_id: string;
  mode: string;
  narrative: string;
  generated_at: string;
  model: string;
}

export default function RoutineBriefing({
  isOpen,
  spot,
  marketMode,
  biasLfi,
  vexy,
  stateReset,
  intent,
  openLoops,
}: RoutineBriefingProps) {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasFetchedRef = useRef(false);
  const lastOpenRef = useRef(false);

  const fetchBriefing = async () => {
    setLoading(true);
    setError(null);

    try {
      // Build the request payload per spec
      const payload = {
        mode: 'routine',
        timestamp: new Date().toISOString(),

        market_context: {
          globex_summary: vexy?.epoch?.text || null,
          vix_level: spot['I:VIX']?.value || null,
          vix_regime: marketMode?.mode || null,
          gex_posture: biasLfi ? (
            biasLfi.directional_strength > 0.3 ? 'bullish' :
            biasLfi.directional_strength < -0.3 ? 'bearish' : 'balanced'
          ) : null,
          market_mode: marketMode?.mode || null,
          market_mode_score: marketMode?.score || null,
          directional_strength: biasLfi?.directional_strength || null,
          lfi_score: biasLfi?.lfi_score || null,
          spx_value: spot['I:SPX']?.value || null,
          spx_change_percent: spot['I:SPX']?.changePercent || null,
        },

        user_context: {
          focus: stateReset.focus,
          energy: stateReset.energy,
          emotional_load: stateReset.emotionalLoad,
          intent: intent.intent,
          intent_note: intent.note || null,
          free_text: stateReset.freeText || null,
        },

        open_loops: {
          open_trades: openLoops.openTrades.length,
          unjournaled_closes: openLoops.unjournaled.length,
          armed_alerts: openLoops.armedAlerts.length,
        },
      };

      const response = await fetch('/api/vexy/routine-briefing', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch briefing: ${response.status}`);
      }

      const data: BriefingResponse = await response.json();
      setBriefing(data);
    } catch (err) {
      console.error('[RoutineBriefing] Error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load briefing');
    } finally {
      setLoading(false);
    }
  };

  // Fetch when drawer opens (transition from closed to open)
  useEffect(() => {
    if (isOpen && !lastOpenRef.current && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchBriefing();
    }
    lastOpenRef.current = isOpen;
  }, [isOpen]);

  // Reset fetch flag when drawer closes so next open triggers a fresh fetch
  useEffect(() => {
    if (!isOpen) {
      hasFetchedRef.current = false;
    }
  }, [isOpen]);

  const handleRefresh = () => {
    fetchBriefing();
  };

  // Render narrative as markdown
  const renderNarrative = (text: string) => {
    const html = marked.parse(text) as string;
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  if (loading) {
    return (
      <div className="routine-briefing">
        <div className="routine-briefing-loading">
          <span className="routine-briefing-spinner">◌</span>
          <span>Preparing orientation...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="routine-briefing">
        <div className="routine-briefing-error">
          <span>Unable to load briefing</span>
          <button className="routine-briefing-retry" onClick={handleRefresh}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!briefing) {
    return (
      <div className="routine-briefing">
        <div className="routine-briefing-empty">
          <span>Open the drawer to receive your orientation</span>
        </div>
      </div>
    );
  }

  return (
    <div className="routine-briefing">
      <div className="routine-briefing-header">
        <span className="routine-briefing-title">Orientation</span>
        <button
          className="routine-briefing-refresh"
          onClick={handleRefresh}
          title="Refresh briefing"
        >
          ↻
        </button>
      </div>
      <div className="routine-briefing-content">
        {renderNarrative(briefing.narrative)}
      </div>
      <div className="routine-briefing-meta">
        <span>{new Date(briefing.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
    </div>
  );
}
