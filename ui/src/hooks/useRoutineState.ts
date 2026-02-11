/**
 * useRoutineState - localStorage persistence for Routine Panel
 *
 * Manages daily-resetting state for:
 * - Routine interaction timestamps
 * - Ask Vexy open state
 *
 * Personal Readiness is now server-backed via useReadinessTags.
 */

import { useState, useCallback, useEffect } from 'react';

// Full routine state
export interface RoutineState {
  routineOpenedAt: string | null;
  orientationShownAt: string | null;
  askVexyOpen: boolean;
}

// localStorage keys
const STORAGE_KEYS = {
  sessionDate: 'routine-session-date',
  routineOpenedAt: 'routine-opened-at',
  orientationShownAt: 'routine-orientation-shown-at',
};

/**
 * Get current date in America/New_York timezone as YYYY-MM-DD
 */
export function getTodayET(): string {
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
  const [routineOpenedAt, setRoutineOpenedAtRaw] = useState<string | null>(() =>
    getStringWithDailyReset(STORAGE_KEYS.routineOpenedAt, STORAGE_KEYS.sessionDate)
  );

  const [orientationShownAt, setOrientationShownAtRaw] = useState<string | null>(() =>
    getStringWithDailyReset(STORAGE_KEYS.orientationShownAt, STORAGE_KEYS.sessionDate)
  );

  const [askVexyOpen, setAskVexyOpen] = useState(false);

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
          // Day changed while away - reset
          localStorage.setItem(STORAGE_KEYS.sessionDate, today);
          setRoutineOpenedAtRaw(null);
          setOrientationShownAtRaw(null);
          localStorage.removeItem(STORAGE_KEYS.routineOpenedAt);
          localStorage.removeItem(STORAGE_KEYS.orientationShownAt);
          // Clean up old localStorage keys from previous version
          localStorage.removeItem('routine-personal-readiness');
          localStorage.removeItem('routine-friction');
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, []);

  return {
    // State
    routineOpenedAt,
    orientationShownAt,
    askVexyOpen,

    // Setters
    markRoutineOpened,
    markOrientationShown,
    setAskVexyOpen,
  };
}
