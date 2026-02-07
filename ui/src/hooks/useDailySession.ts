/**
 * useDailySession - Daily trading session state tracking
 *
 * Tracks whether this is the first app open of the day and manages
 * session activation state for the Left-to-Right workflow.
 */

import { useState, useCallback, useMemo, useEffect } from 'react';

// Stage types (matching PathContext)
type Stage = 'discovery' | 'analysis' | 'action' | 'reflection' | 'distillation';

interface DailySessionState {
  isFirstOpenToday: boolean;
  sessionActivated: boolean;
  activatedAt: number | null;
  stagesVisited: Stage[];
  sessionDate: string;
}

const STORAGE_KEYS = {
  sessionDate: 'fotw-session-date',
  activatedAt: 'fotw-session-activated-at',
  stagesVisited: 'fotw-stages-visited',
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
  return formatter.format(now); // Returns YYYY-MM-DD
}

/**
 * Get current hour in ET (0-23, with decimals for minutes)
 */
export function getCurrentETHour(): number {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: 'numeric',
    hour12: false,
  });
  const timeStr = formatter.format(now); // "HH:MM"
  const [hours, minutes] = timeStr.split(':').map(Number);
  return hours + minutes / 60;
}

// How often to update the current hour (in ms)
const TIME_UPDATE_INTERVAL = 60000; // 1 minute

export function useDailySession() {
  // Track current ET hour to re-evaluate time-based hints
  // Updates every minute to catch market open/close transitions
  const [currentHour, setCurrentHour] = useState(getCurrentETHour);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentHour(getCurrentETHour());
    }, TIME_UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  const [state, setState] = useState<DailySessionState>(() => {
    const today = getTodayET();
    const storedDate = localStorage.getItem(STORAGE_KEYS.sessionDate);
    const isNewDay = storedDate !== today;

    if (isNewDay) {
      // New day - reset session state
      localStorage.setItem(STORAGE_KEYS.sessionDate, today);
      localStorage.removeItem(STORAGE_KEYS.activatedAt);
      localStorage.removeItem(STORAGE_KEYS.stagesVisited);

      return {
        isFirstOpenToday: true,
        sessionActivated: false,
        activatedAt: null,
        stagesVisited: [],
        sessionDate: today,
      };
    }

    // Same day - restore session state
    const activatedAt = localStorage.getItem(STORAGE_KEYS.activatedAt);
    const stagesVisitedJson = localStorage.getItem(STORAGE_KEYS.stagesVisited);
    const stagesVisited: Stage[] = stagesVisitedJson
      ? JSON.parse(stagesVisitedJson)
      : [];

    return {
      isFirstOpenToday: false,
      sessionActivated: activatedAt !== null,
      activatedAt: activatedAt ? parseInt(activatedAt, 10) : null,
      stagesVisited,
      sessionDate: today,
    };
  });

  // Activate the session (user clicked to dismiss onboarding)
  const activateSession = useCallback(() => {
    const now = Date.now();
    localStorage.setItem(STORAGE_KEYS.activatedAt, now.toString());

    setState(prev => ({
      ...prev,
      isFirstOpenToday: false,
      sessionActivated: true,
      activatedAt: now,
    }));
  }, []);

  // Mark a stage as visited
  const markStageVisited = useCallback((stage: Stage) => {
    setState(prev => {
      if (prev.stagesVisited.includes(stage)) {
        return prev;
      }

      const newStagesVisited = [...prev.stagesVisited, stage];
      localStorage.setItem(STORAGE_KEYS.stagesVisited, JSON.stringify(newStagesVisited));

      return {
        ...prev,
        stagesVisited: newStagesVisited,
      };
    });
  }, []);

  // Check if a stage has been visited
  const hasVisitedStage = useCallback((stage: Stage): boolean => {
    return state.stagesVisited.includes(stage);
  }, [state.stagesVisited]);

  // Determine if Routine drawer should hint
  // Uses currentHour state (updates every minute) to catch market open transition
  const shouldHintRoutine = useMemo(() => {
    // Hint if session just activated and discovery not yet visited
    if (state.sessionActivated && !state.stagesVisited.includes('discovery')) {
      return true;
    }

    // Hint during pre-market if discovery not visited
    const isPreMarket = currentHour < 9.5; // Before 9:30 AM ET
    if (isPreMarket && !state.stagesVisited.includes('discovery')) {
      return true;
    }

    return false;
  }, [state.sessionActivated, state.stagesVisited, currentHour]);

  // Determine if Process drawer should hint
  // Uses currentHour state (updates every minute) to catch market close transition
  const shouldHintProcess = useMemo(() => {
    // Only hint after market close if user has taken action
    const isPostMarket = currentHour >= 16; // After 4:00 PM ET
    const hasTakenAction = state.stagesVisited.includes('action');
    const hasReflected = state.stagesVisited.includes('reflection');

    return isPostMarket && hasTakenAction && !hasReflected;
  }, [state.stagesVisited, currentHour]);

  // Show onboarding overlay if first open today and not yet activated
  const showOnboarding = state.isFirstOpenToday && !state.sessionActivated;

  return {
    ...state,
    showOnboarding,
    shouldHintRoutine,
    shouldHintProcess,
    activateSession,
    markStageVisited,
    hasVisitedStage,
  };
}

export type { Stage, DailySessionState };
