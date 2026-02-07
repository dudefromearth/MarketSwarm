/**
 * Process Phase Constants
 *
 * Shared phase definitions for ProcessBar and DailyOnboarding.
 * These represent the Left-to-Right trading workflow.
 */

import { type Stage } from './pathContent';

// Phase IDs that can be active in the ProcessBar
export type ProcessPhase = 'routine' | 'structure' | 'selection' | 'analysis' | 'action' | 'process';

// Phase color semantics
export type PhaseColor = 'warm' | 'neutral' | 'cool';

export interface PhaseDefinition {
  id: ProcessPhase;
  label: string;
  stages: Stage[];
  color: PhaseColor;
}

/**
 * Canonical phase definitions for the trading workflow.
 * Order matters: left-to-right flow from preparation to integration.
 */
export const PROCESS_PHASES: PhaseDefinition[] = [
  { id: 'routine', label: 'Routine', stages: ['discovery'], color: 'warm' },
  { id: 'structure', label: 'Structure', stages: [], color: 'neutral' },
  { id: 'selection', label: 'Selection', stages: [], color: 'neutral' },
  { id: 'analysis', label: 'Analysis', stages: ['analysis'], color: 'neutral' },
  { id: 'action', label: 'Action', stages: ['action'], color: 'neutral' },
  { id: 'process', label: 'Process', stages: ['reflection', 'distillation'], color: 'cool' },
];

// For DailyOnboarding numbered display
export const PROCESS_PHASES_NUMBERED = PROCESS_PHASES.map((phase, index) => ({
  ...phase,
  number: index + 1,
}));
