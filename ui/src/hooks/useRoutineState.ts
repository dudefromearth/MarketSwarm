/**
 * useRoutineState - localStorage persistence for Routine Drawer
 *
 * Manages daily-resetting state for:
 * - State Reset (focus, energy, emotional load)
 * - Risk Orientation (width, capital, optionality postures)
 * - Intent Declaration (intent type + note)
 * - Section expansion states
 */

import { useState, useCallback, useEffect } from 'react';

// Section 1: State Reset
export interface StateResetData {
  focus: 'low' | 'medium' | 'high' | null;
  energy: 'low' | 'medium' | 'high' | null;
  emotionalLoad: 'calm' | 'charged' | 'distracted' | null;
  freeText: string;
}

// Section 4: Risk Orientation
export interface RiskOrientationData {
  widthPosture: 'narrow' | 'normal' | 'wide' | null;
  capitalPosture: 'defensive' | 'neutral' | 'offensive' | null;
  optionalityPosture: 'patience' | 'speed' | 'observation' | null;
}

// Section 5: Intent Declaration
export type IntentType =
  | 'observe_only'
  | 'manage_existing'
  | 'one_trade_max'
  | 'full_participation'
  | 'test_hypothesis';

export interface IntentDeclarationData {
  intent: IntentType | null;
  note: string;
}

// Section expansion states
export interface SectionExpandedState {
  stateReset: boolean;
  openLoops: boolean;
  marketContext: boolean;
  riskOrientation: boolean;
  intent: boolean;
  vexy: boolean;
}

// localStorage keys
const STORAGE_KEYS = {
  sessionDate: 'routine-session-date',
  stateReset: 'routine-state-reset',
  riskOrientation: 'routine-risk-orientation',
  intent: 'routine-intent',
  sectionsExpanded: 'routine-sections-expanded',
};

// Default values
const DEFAULT_STATE_RESET: StateResetData = {
  focus: null,
  energy: null,
  emotionalLoad: null,
  freeText: '',
};

const DEFAULT_RISK_ORIENTATION: RiskOrientationData = {
  widthPosture: null,
  capitalPosture: null,
  optionalityPosture: null,
};

const DEFAULT_INTENT: IntentDeclarationData = {
  intent: null,
  note: '',
};

const DEFAULT_SECTIONS_EXPANDED: SectionExpandedState = {
  stateReset: true,
  openLoops: false,
  marketContext: true,
  riskOrientation: true,
  intent: true,
  vexy: true,
};

/**
 * Get current date in America/New_York timezone as YYYY-MM-DD
 */
function getTodayET(): string {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return formatter.format(now);
}

/**
 * Check if stored date matches today, reset if not
 */
function checkAndResetDaily<T>(key: string, defaultValue: T, sessionDateKey: string): T {
  const today = getTodayET();
  const storedDate = localStorage.getItem(sessionDateKey);

  if (storedDate !== today) {
    // New day - reset
    localStorage.setItem(sessionDateKey, today);
    localStorage.removeItem(key);
    return defaultValue;
  }

  // Same day - try to restore
  const stored = localStorage.getItem(key);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch {
      return defaultValue;
    }
  }

  return defaultValue;
}

export function useRoutineState() {
  // Initialize state with daily reset logic
  const [stateReset, setStateResetRaw] = useState<StateResetData>(() =>
    checkAndResetDaily(STORAGE_KEYS.stateReset, DEFAULT_STATE_RESET, STORAGE_KEYS.sessionDate)
  );

  const [riskOrientation, setRiskOrientationRaw] = useState<RiskOrientationData>(() =>
    checkAndResetDaily(STORAGE_KEYS.riskOrientation, DEFAULT_RISK_ORIENTATION, STORAGE_KEYS.sessionDate)
  );

  const [intent, setIntentRaw] = useState<IntentDeclarationData>(() =>
    checkAndResetDaily(STORAGE_KEYS.intent, DEFAULT_INTENT, STORAGE_KEYS.sessionDate)
  );

  const [sectionsExpanded, setSectionsExpandedRaw] = useState<SectionExpandedState>(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.sectionsExpanded);
    if (stored) {
      try {
        return { ...DEFAULT_SECTIONS_EXPANDED, ...JSON.parse(stored) };
      } catch {
        return DEFAULT_SECTIONS_EXPANDED;
      }
    }
    return DEFAULT_SECTIONS_EXPANDED;
  });

  // Persist state changes to localStorage
  const setStateReset = useCallback((update: Partial<StateResetData> | ((prev: StateResetData) => StateResetData)) => {
    setStateResetRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.stateReset, JSON.stringify(next));
      return next;
    });
  }, []);

  const setRiskOrientation = useCallback((update: Partial<RiskOrientationData> | ((prev: RiskOrientationData) => RiskOrientationData)) => {
    setRiskOrientationRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.riskOrientation, JSON.stringify(next));
      return next;
    });
  }, []);

  const setIntent = useCallback((update: Partial<IntentDeclarationData> | ((prev: IntentDeclarationData) => IntentDeclarationData)) => {
    setIntentRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.intent, JSON.stringify(next));
      return next;
    });
  }, []);

  const setSectionsExpanded = useCallback((update: Partial<SectionExpandedState> | ((prev: SectionExpandedState) => SectionExpandedState)) => {
    setSectionsExpandedRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.sectionsExpanded, JSON.stringify(next));
      return next;
    });
  }, []);

  const toggleSection = useCallback((section: keyof SectionExpandedState) => {
    setSectionsExpanded((prev) => ({ ...prev, [section]: !prev[section] }));
  }, [setSectionsExpanded]);

  // Check for day change on visibility change (user returns to tab)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const today = getTodayET();
        const storedDate = localStorage.getItem(STORAGE_KEYS.sessionDate);

        if (storedDate !== today) {
          // Day changed while away - reset all
          localStorage.setItem(STORAGE_KEYS.sessionDate, today);
          setStateResetRaw(DEFAULT_STATE_RESET);
          setRiskOrientationRaw(DEFAULT_RISK_ORIENTATION);
          setIntentRaw(DEFAULT_INTENT);
          localStorage.removeItem(STORAGE_KEYS.stateReset);
          localStorage.removeItem(STORAGE_KEYS.riskOrientation);
          localStorage.removeItem(STORAGE_KEYS.intent);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  // Computed: is routine complete?
  const isRoutineComplete =
    stateReset.focus !== null &&
    stateReset.energy !== null &&
    stateReset.emotionalLoad !== null &&
    riskOrientation.widthPosture !== null &&
    riskOrientation.capitalPosture !== null &&
    riskOrientation.optionalityPosture !== null &&
    intent.intent !== null;

  return {
    stateReset,
    setStateReset,
    riskOrientation,
    setRiskOrientation,
    intent,
    setIntent,
    sectionsExpanded,
    setSectionsExpanded,
    toggleSection,
    isRoutineComplete,
  };
}
