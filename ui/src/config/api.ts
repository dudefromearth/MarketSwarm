/**
 * Centralized API endpoint configuration
 *
 * All API endpoints should be defined here to:
 * - Avoid hardcoded URLs scattered across components
 * - Make endpoint changes easier
 * - Enable environment-specific overrides
 */

export const API = {
  auth: {
    me: '/api/auth/me',
  },

  vexy: {
    chat: '/api/vexy/chat',
    routineBriefing: '/api/vexy/routine-briefing',
    orientation: '/api/vexy/routine/orientation',
    marketReadiness: (userId: number) => `/api/vexy/routine/market-readiness/${userId}`,
    marketState: '/api/vexy/market-state',
    processEcho: (userId: number) => `/api/vexy/process-echo/${userId}`,

    // Journal
    journalSynopsis: '/api/vexy/journal/synopsis',
    journalPrompts: '/api/vexy/journal/prompts',
    journalChat: '/api/vexy/journal/chat',

    // Playbook
    playbookSections: '/api/vexy/playbook/sections',
    playbookFodder: '/api/vexy/playbook/fodder',
    playbookChat: '/api/vexy/playbook/chat',

    // ML
    mlStatus: '/api/vexy/ml/status',
    mlThresholds: '/api/vexy/ml/thresholds',
  },
} as const;

/**
 * RoutineContextPhase - matches backend enum
 */
export type RoutineContextPhase =
  | 'weekday_premarket'
  | 'weekday_intraday'
  | 'weekday_afterhours'
  | 'friday_night'
  | 'weekend_morning'
  | 'weekend_afternoon'
  | 'weekend_evening'
  | 'holiday';

/**
 * VIX Regime types (legacy 4-regime)
 */
export type VixRegime = 'zombieland' | 'goldilocks' | 'elevated' | 'chaos';

/**
 * SoM v2 — 5-regime VIX classification
 */
export type MarketStateRegime = 'compression' | 'goldilocks_i' | 'goldilocks_ii' | 'elevated' | 'chaos';
