/**
 * useRoutineState - localStorage persistence for Routine Panel v1
 *
 * Manages daily-resetting state for:
 * - Personal Readiness (Day Qualities: sleep, focus, distractions, bodyState)
 * - Friction Markers (atmospheric conditions, not problems)
 * - Routine interaction timestamps
 *
 * Philosophy: Help the trader arrive, not complete tasks.
 * No completion mechanics, no scoring, no "ready" state.
 */

import { useState, useCallback, useEffect } from 'react';

// Personal Readiness - Day Qualities
export type SleepQuality = 'short' | 'adequate' | 'strong' | null;
export type FocusQuality = 'scattered' | 'centered' | null;
export type DistractionLevel = 'low' | 'medium' | 'high' | null;
export type BodyState = 'tight' | 'neutral' | 'energized' | null;

export interface PersonalReadinessState {
  sleep: SleepQuality;
  focus: FocusQuality;
  distractions: DistractionLevel;
  bodyState: BodyState;
}

// Friction Markers - atmospheric conditions, not problems
export interface FrictionMarkers {
  carryover: boolean;     // "stuff from yesterday"
  noise: boolean;         // "external interruptions"
  tension: boolean;       // "internal pressure"
  timePressure: boolean;  // "compressed availability"
}

// Full routine state
export interface RoutineState {
  personalReadiness: PersonalReadinessState;
  friction: FrictionMarkers;
  routineOpenedAt: string | null;
  orientationShownAt: string | null;
  askVexyOpen: boolean;
}

// localStorage keys
const STORAGE_KEYS = {
  sessionDate: 'routine-session-date',
  personalReadiness: 'routine-personal-readiness',
  friction: 'routine-friction',
  routineOpenedAt: 'routine-opened-at',
  orientationShownAt: 'routine-orientation-shown-at',
};

// Default values
const DEFAULT_PERSONAL_READINESS: PersonalReadinessState = {
  sleep: null,
  focus: null,
  distractions: null,
  bodyState: null,
};

const DEFAULT_FRICTION: FrictionMarkers = {
  carryover: false,
  noise: false,
  tension: false,
  timePressure: false,
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

/**
 * Get a string value from localStorage with daily reset
 */
function getStringWithDailyReset(key: string, sessionDateKey: string): string | null {
  const today = getTodayET();
  const storedDate = localStorage.getItem(sessionDateKey);

  if (storedDate !== today) {
    localStorage.removeItem(key);
    return null;
  }

  return localStorage.getItem(key);
}

export function useRoutineState() {
  // Initialize state with daily reset logic
  const [personalReadiness, setPersonalReadinessRaw] = useState<PersonalReadinessState>(() =>
    checkAndResetDaily(STORAGE_KEYS.personalReadiness, DEFAULT_PERSONAL_READINESS, STORAGE_KEYS.sessionDate)
  );

  const [friction, setFrictionRaw] = useState<FrictionMarkers>(() =>
    checkAndResetDaily(STORAGE_KEYS.friction, DEFAULT_FRICTION, STORAGE_KEYS.sessionDate)
  );

  const [routineOpenedAt, setRoutineOpenedAtRaw] = useState<string | null>(() =>
    getStringWithDailyReset(STORAGE_KEYS.routineOpenedAt, STORAGE_KEYS.sessionDate)
  );

  const [orientationShownAt, setOrientationShownAtRaw] = useState<string | null>(() =>
    getStringWithDailyReset(STORAGE_KEYS.orientationShownAt, STORAGE_KEYS.sessionDate)
  );

  const [askVexyOpen, setAskVexyOpen] = useState(false);

  // Persist personal readiness changes
  const setPersonalReadiness = useCallback((
    update: Partial<PersonalReadinessState> | ((prev: PersonalReadinessState) => PersonalReadinessState)
  ) => {
    setPersonalReadinessRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.personalReadiness, JSON.stringify(next));
      return next;
    });
  }, []);

  // Persist friction changes
  const setFriction = useCallback((
    update: Partial<FrictionMarkers> | ((prev: FrictionMarkers) => FrictionMarkers)
  ) => {
    setFrictionRaw((prev) => {
      const next = typeof update === 'function' ? update(prev) : { ...prev, ...update };
      localStorage.setItem(STORAGE_KEYS.friction, JSON.stringify(next));
      return next;
    });
  }, []);

  // Toggle a specific friction marker
  const toggleFriction = useCallback((key: keyof FrictionMarkers) => {
    setFriction((prev) => ({ ...prev, [key]: !prev[key] }));
  }, [setFriction]);

  // Toggle a personal readiness value (click to select, click again to deselect)
  const togglePersonalReadiness = useCallback(<K extends keyof PersonalReadinessState>(
    key: K,
    value: PersonalReadinessState[K]
  ) => {
    setPersonalReadiness((prev) => ({
      ...prev,
      [key]: prev[key] === value ? null : value,
    }));
  }, [setPersonalReadiness]);

  // Mark routine as opened
  const markRoutineOpened = useCallback(() => {
    const now = new Date().toISOString();
    setRoutineOpenedAtRaw(now);
    localStorage.setItem(STORAGE_KEYS.routineOpenedAt, now);
  }, []);

  // Mark orientation as shown
  const markOrientationShown = useCallback(() => {
    const now = new Date().toISOString();
    setOrientationShownAtRaw(now);
    localStorage.setItem(STORAGE_KEYS.orientationShownAt, now);
  }, []);

  // Check for day change on visibility change (user returns to tab)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const today = getTodayET();
        const storedDate = localStorage.getItem(STORAGE_KEYS.sessionDate);

        if (storedDate !== today) {
          // Day changed while away - reset all
          localStorage.setItem(STORAGE_KEYS.sessionDate, today);
          setPersonalReadinessRaw(DEFAULT_PERSONAL_READINESS);
          setFrictionRaw(DEFAULT_FRICTION);
          setRoutineOpenedAtRaw(null);
          setOrientationShownAtRaw(null);
          localStorage.removeItem(STORAGE_KEYS.personalReadiness);
          localStorage.removeItem(STORAGE_KEYS.friction);
          localStorage.removeItem(STORAGE_KEYS.routineOpenedAt);
          localStorage.removeItem(STORAGE_KEYS.orientationShownAt);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  // Export Day Texture for Journal integration
  const getDayTexture = useCallback(() => {
    const qualities: string[] = [];

    if (personalReadiness.sleep) {
      qualities.push(`Sleep: ${personalReadiness.sleep.charAt(0).toUpperCase() + personalReadiness.sleep.slice(1)}`);
    }
    if (personalReadiness.focus) {
      qualities.push(`Focus: ${personalReadiness.focus.charAt(0).toUpperCase() + personalReadiness.focus.slice(1)}`);
    }
    if (personalReadiness.distractions) {
      qualities.push(`Distractions: ${personalReadiness.distractions.charAt(0).toUpperCase() + personalReadiness.distractions.slice(1)}`);
    }
    if (personalReadiness.bodyState) {
      qualities.push(`Body: ${personalReadiness.bodyState.charAt(0).toUpperCase() + personalReadiness.bodyState.slice(1)}`);
    }

    const frictionItems: string[] = [];
    if (friction.carryover) frictionItems.push('Carryover');
    if (friction.noise) frictionItems.push('Noise');
    if (friction.tension) frictionItems.push('Tension');
    if (friction.timePressure) frictionItems.push('Time pressure');

    return {
      qualities: qualities.join(' · '),
      friction: frictionItems.join(' · '),
    };
  }, [personalReadiness, friction]);

  return {
    // State
    personalReadiness,
    friction,
    routineOpenedAt,
    orientationShownAt,
    askVexyOpen,

    // Setters
    setPersonalReadiness,
    setFriction,
    toggleFriction,
    togglePersonalReadiness,
    markRoutineOpened,
    markOrientationShown,
    setAskVexyOpen,

    // Helpers
    getDayTexture,
  };
}
