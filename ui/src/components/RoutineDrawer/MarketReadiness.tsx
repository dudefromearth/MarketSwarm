/**
 * MarketReadiness - Establish context, not predictions
 *
 * Read-only awareness with lens-based layout.
 * Three lenses (NOT sections with heavy borders):
 * 1. "What the market is carrying" - overnight, euro, macro
 * 2. "Volatility posture" - VIX with regime badge
 * 3. "Topology & memory" - Volume Nodes, Wells, Crevasses, GEX
 *
 * Lexicon Constraints (HARD RULES):
 * - NEVER use: POC, VAH, VAL
 * - MUST use: Volume Node (HVN), Volume Well (LVN), Crevasse, Market Memory
 *
 * Critical: Never answers "when". Reinforces waiting as success.
 */

import { useState, useEffect } from 'react';
import { API, type VixRegime, type RoutineContextPhase } from '../../config/api';

interface MarketReadinessPayload {
  generated_at: string;
  context_phase: RoutineContextPhase;
  carrying: {
    globex_summary: string;
    euro_note: string | null;
    macro_events: string[];
  };
  volatility: {
    vix_level: number | null;
    regime: VixRegime | null;
    implication: string | null;
  };
  topology: {
    structure_synopsis: string;
    gex_posture: string | null;
    key_levels: number[];
  };
  waiting_anchor: string;
}

interface MarketReadinessProps {
  isOpen: boolean;
}

// VIX regime display names
const VIX_REGIME_LABELS: Record<string, string> = {
  zombieland: 'Zombieland',
  goldilocks: 'Goldilocks',
  elevated: 'Elevated',
  chaos: 'Chaos',
};

export default function MarketReadiness({ isOpen }: MarketReadinessProps) {
  const [payload, setPayload] = useState<MarketReadinessPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    const fetchMarketReadiness = async () => {
      setLoading(true);
      setError(null);

      try {
        // For now, use a mock payload
        // In production: const response = await fetch('/api/vexy/routine/market-readiness/1');
        const mockPayload: MarketReadinessPayload = {
          generated_at: new Date().toISOString(),
          context_phase: 'weekday_premarket',
          carrying: {
            globex_summary: 'Overnight session showed range-bound action. ES held above 5980 through Asia.',
            euro_note: 'Euro session saw a test of the 6000 level with rejection.',
            macro_events: [],
          },
          volatility: {
            vix_level: 14.5,
            regime: 'goldilocks',
            implication: 'Balanced conditions for patient waiting.',
          },
          topology: {
            structure_synopsis: 'Volume Nodes at 5980, 6020. Volume Well between 5990-6010.',
            gex_posture: 'Positive gamma above 6000',
            key_levels: [5980, 5990, 6010, 6020],
          },
          waiting_anchor: "Today is a waiting day until an entry event appears (or doesn't). Waiting is part of the edge.",
        };

        // Fetch from API
        try {
          const response = await fetch(API.vexy.marketReadiness(1), {
            credentials: 'include',
          });

          if (response.ok) {
            const data = await response.json();
            if (data.success && data.data) {
              setPayload(data.data);
              return;
            }
          }
        } catch (err) {
          console.error('[MarketReadiness] API fetch failed:', err);
        }

        // Fall back to mock data if API unavailable
        setPayload(mockPayload);
      } catch (err) {
        console.error('[MarketReadiness] Error:', err);
        setError('Unable to load market context');
      } finally {
        setLoading(false);
      }
    };

    fetchMarketReadiness();
  }, [isOpen]);

  if (loading) {
    return (
      <div className="market-readiness">
        <div className="routine-lens-header">Market Readiness</div>
        <div className="market-readiness-loading">
          <span className="routine-briefing-spinner">◌</span>
          <span>Loading market context...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-readiness">
        <div className="routine-lens-header">Market Readiness</div>
        <div className="market-readiness-error">{error}</div>
      </div>
    );
  }

  if (!payload) {
    return null;
  }

  return (
    <div className="market-readiness">
      <div className="routine-lens-header">Market Readiness</div>

      {/* Lens 1: What the market is carrying */}
      <div className="market-lens">
        <div className="market-lens-title">What the market is carrying</div>
        <div className="market-lens-content">
          <p>{payload.carrying.globex_summary}</p>
          {payload.carrying.euro_note && (
            <p>{payload.carrying.euro_note}</p>
          )}
          {payload.carrying.macro_events.length > 0 && (
            <ul className="market-lens-bullets">
              {payload.carrying.macro_events.map((event, idx) => (
                <li key={idx}>{event}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Lens 2: Volatility posture */}
      <div className="market-lens">
        <div className="market-lens-title">Volatility posture</div>
        <div className="market-lens-content">
          <div className="volatility-row">
            {payload.volatility.vix_level !== null && (
              <span className="vix-level">
                VIX {payload.volatility.vix_level.toFixed(1)}
              </span>
            )}
            {payload.volatility.regime && (
              <span className={`vix-regime-badge ${payload.volatility.regime}`}>
                {VIX_REGIME_LABELS[payload.volatility.regime] || payload.volatility.regime}
              </span>
            )}
          </div>
          {payload.volatility.implication && (
            <p className="volatility-implication">{payload.volatility.implication}</p>
          )}
        </div>
      </div>

      {/* Lens 3: Topology & memory */}
      <div className="market-lens">
        <div className="market-lens-title">Topology & memory</div>
        <div className="market-lens-content">
          <p>{payload.topology.structure_synopsis}</p>
          {payload.topology.gex_posture && (
            <p className="gex-posture">{payload.topology.gex_posture}</p>
          )}
        </div>
      </div>

      {/* Waiting Anchor */}
      <div className="waiting-anchor">
        {payload.waiting_anchor}
      </div>
    </div>
  );
}
