/**
 * StateOfTheMarket — SoM v2
 *
 * Four lenses, always visible (no collapse/expand):
 * 1. Big Picture Volatility — VIX regime classification
 * 2. Localized Volatility — dealer posture, expansion probability
 * 3. Potential Energy — economic events, event posture
 * 4. Convexity Temperature — synthesized from other 3 lenses
 *
 * Hidden on weekends/holidays (context_phase = "weekend" | "holiday").
 * Calibrates posture — never recommends trades.
 */

import { useCallback } from 'react';
import { API } from '../../config/api';
import { useSingleFetch } from '../../hooks/useSingleFetch';

// ── Types ────────────────────────────────────────────────────────────

type SomContextPhase = 'weekday_premarket' | 'weekday_live' | 'weekend' | 'holiday';

type SomRegimeKey = 'compression' | 'goldilocks_i' | 'goldilocks_ii' | 'elevated' | 'chaos';

type ConvexityTemp = 'cold' | 'cool' | 'warm' | 'hot';

interface SomEvent {
  time_et: string;
  name: string;
  impact: string;
}

interface SomPayload {
  schema_version: string;
  generated_at: string;
  context_phase: SomContextPhase;
  big_picture_volatility: {
    vix: number;
    regime_key: SomRegimeKey;
    regime_label: string;
    decay_profile: string;
    gamma_sensitivity: string;
  } | null;
  localized_volatility: {
    dealer_posture: string;
    intraday_expansion_probability: string;
    localized_vol_label: string;
  } | null;
  event_energy: {
    events: SomEvent[];
    event_posture: string;
  } | null;
  convexity_temperature: {
    temperature: ConvexityTemp;
    summary: string;
  } | null;
}

interface StateOfTheMarketProps {
  isOpen: boolean;
}

// ── Regime badge CSS class mapping ───────────────────────────────────

const REGIME_CSS: Record<SomRegimeKey, string> = {
  compression: 'som-regime-compression',
  goldilocks_i: 'som-regime-goldilocks-i',
  goldilocks_ii: 'som-regime-goldilocks-ii',
  elevated: 'som-regime-elevated',
  chaos: 'som-regime-chaos',
};

// ── Dealer posture display ───────────────────────────────────────────

const DEALER_LABELS: Record<string, string> = {
  short_gamma: 'Short gamma',
  long_gamma: 'Long gamma',
  neutral: 'Neutral',
};

// ── Event posture display ────────────────────────────────────────────

const EVENT_POSTURE_LABELS: Record<string, string> = {
  clean_morning: 'Clean morning',
  front_loaded: 'Front-loaded',
  midday_loaded: 'Midday-loaded',
  binary_event_day: 'Binary event day',
  speech_risk: 'Speech risk',
  high_energy_cluster: 'High-energy cluster',
};

// ── Expansion display ────────────────────────────────────────────────

const EXPANSION_LABELS: Record<string, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
};

// ── Temperature CSS class ────────────────────────────────────────────

const TEMP_CSS: Record<ConvexityTemp, string> = {
  cold: 'som-temp-cold',
  cool: 'som-temp-cool',
  warm: 'som-temp-warm',
  hot: 'som-temp-hot',
};

const TEMP_LABELS: Record<ConvexityTemp, string> = {
  cold: 'Cold',
  cool: 'Cool',
  warm: 'Warm',
  hot: 'Hot',
};

// ── Component ────────────────────────────────────────────────────────

export default function StateOfTheMarket({ isOpen }: StateOfTheMarketProps) {
  const fetchMarketState = useCallback(async (signal: AbortSignal): Promise<SomPayload | null> => {
    try {
      const response = await fetch(API.vexy.marketState, {
        credentials: 'include',
        signal,
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        throw err;
      }
      console.error('[StateOfTheMarket] API fetch failed:', err);
    }
    return null;
  }, []);

  const { data: payload, loading, error } = useSingleFetch(
    isOpen,
    fetchMarketState
  );

  // Loading state
  if (loading) {
    return (
      <div className="som-container">
        <div className="som-header">
          <div className="som-title">State of the Market</div>
          <div className="som-subtitle">Volatility, energy, posture</div>
        </div>
        <div className="som-loading">
          <span className="routine-briefing-spinner">&#9676;</span>
          <span>Reading market state...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="som-container">
        <div className="som-header">
          <div className="som-title">State of the Market</div>
        </div>
        <div className="som-error">{error}</div>
      </div>
    );
  }

  // No data or off-market: hide entirely
  if (!payload) return null;
  if (payload.context_phase === 'weekend' || payload.context_phase === 'holiday') return null;

  const bpv = payload.big_picture_volatility;
  const lv = payload.localized_volatility;
  const ee = payload.event_energy;
  const ct = payload.convexity_temperature;

  // If all lenses are null (graceful degradation), hide
  if (!bpv && !lv && !ee && !ct) return null;

  return (
    <div className="som-container">
      {/* Header */}
      <div className="som-header">
        <div className="som-title">State of the Market</div>
        <div className="som-subtitle">Volatility, energy, posture</div>
      </div>

      {/* Lens 1: Big Picture Volatility */}
      {bpv && (
        <div className="som-lens">
          <div className="som-lens-title">Big Picture Volatility</div>
          <div className="som-lens-content">
            <div className="som-vix-row">
              <span className="som-vix-value">VIX {bpv.vix.toFixed(1)}</span>
              <span className={`som-regime-badge ${REGIME_CSS[bpv.regime_key]}`}>
                {bpv.regime_label}
              </span>
            </div>
            <div className="som-detail">Decay: {bpv.decay_profile}</div>
            <div className="som-detail">Gamma Sensitivity: {bpv.gamma_sensitivity}</div>
          </div>
        </div>
      )}

      {/* Lens 2: Localized Volatility */}
      {lv && (
        <div className="som-lens">
          <div className="som-lens-title">Localized Volatility</div>
          <div className="som-lens-content">
            <div className="som-detail">Dealer Posture: {DEALER_LABELS[lv.dealer_posture] || lv.dealer_posture}</div>
            <div className="som-detail">Intraday Expansion: {EXPANSION_LABELS[lv.intraday_expansion_probability] || lv.intraday_expansion_probability}</div>
          </div>
        </div>
      )}

      {/* Lens 3: Potential Energy */}
      {ee && (
        <div className="som-lens">
          <div className="som-lens-title">Potential Energy</div>
          <div className="som-lens-content">
            {ee.events.length > 0 ? (
              <div className="som-events">
                {ee.events.map((evt, idx) => (
                  <div key={idx} className="som-event-row">
                    <span className="som-event-time">{evt.time_et}</span>
                    <span className="som-event-name">{evt.name}</span>
                    <span className={`som-event-impact som-impact-${evt.impact.toLowerCase().replace(' ', '-')}`}>
                      {evt.impact}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="som-detail som-clean">No scheduled events</div>
            )}
            <div className="som-detail som-posture">
              Event Posture: {EVENT_POSTURE_LABELS[ee.event_posture] || ee.event_posture}
            </div>
          </div>
        </div>
      )}

      {/* Lens 4: Convexity Temperature */}
      {ct && (
        <div className="som-lens som-lens-temperature">
          <div className="som-temp-row">
            <span className="som-lens-title">Convexity Temperature:</span>
            <span className={`som-temp-badge ${TEMP_CSS[ct.temperature]}`}>
              {TEMP_LABELS[ct.temperature]}
            </span>
          </div>
          <div className="som-temp-summary">{ct.summary}</div>
        </div>
      )}
    </div>
  );
}
