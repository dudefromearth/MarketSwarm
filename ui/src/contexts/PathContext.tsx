/**
 * PathContext - FOTW Path Stage State Management
 *
 * Provides:
 * - Current stage inference from active UI panel
 * - Expansion state for the path indicator
 * - Tour completion tracking (persisted to localStorage)
 * - Transition state for welcome → indicator handoff
 *
 * The system reflects where the user is — it does not tell them where to go.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';

import { type Stage, PANEL_STAGE_MAP } from '../constants/pathContent';

const TOUR_COMPLETED_KEY = 'fotw-tour-completed';

/**
 * Transition phases for welcome → indicator handoff
 *
 * 'idle'       - Normal state, no transition happening
 * 'pre-dismiss' - Brief cue showing mini indicator in modal (300-500ms)
 * 'fading-out' - Modal fading out (300ms)
 * 'waiting'    - Pause before indicator appears (1-2s)
 * 'fading-in'  - Indicator fading into existence (500-800ms)
 * 'complete'   - Transition done, indicator at rest
 */
type TransitionPhase = 'idle' | 'pre-dismiss' | 'fading-out' | 'waiting' | 'fading-in' | 'complete';

interface PathState {
  currentStage: Stage;
  activePanel: string | null;
  expanded: boolean;
  tourCompleted: boolean;
  showTour: boolean;
  transitionPhase: TransitionPhase;
  indicatorVisible: boolean;
}

interface PathContextValue extends PathState {
  setActivePanel: (panel: string | null) => void;
  setExpanded: (expanded: boolean) => void;
  toggleExpanded: () => void;
  beginTourDismiss: () => void;
  completeTour: () => void;
  resetTour: () => void;
  showTourModal: () => void;
}

const PathContext = createContext<PathContextValue | null>(null);

/**
 * Infer stage from active panel
 * Returns 'discovery' as default - the starting point
 */
function inferStage(activePanel: string | null): Stage {
  if (!activePanel) return 'discovery';
  return PANEL_STAGE_MAP[activePanel] || 'discovery';
}

export function PathProvider({ children }: { children: ReactNode }) {
  const [activePanel, setActivePanelState] = useState<string | null>(null);
  const [expanded, setExpandedState] = useState(false);
  const [tourCompleted, setTourCompleted] = useState(() => {
    try {
      return localStorage.getItem(TOUR_COMPLETED_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [showTour, setShowTour] = useState(() => {
    try {
      return localStorage.getItem(TOUR_COMPLETED_KEY) !== 'true';
    } catch {
      return true;
    }
  });
  const [transitionPhase, setTransitionPhase] = useState<TransitionPhase>(() => {
    // If tour already completed, indicator should be visible
    try {
      return localStorage.getItem(TOUR_COMPLETED_KEY) === 'true' ? 'complete' : 'idle';
    } catch {
      return 'idle';
    }
  });
  const [indicatorVisible, setIndicatorVisible] = useState(() => {
    // Only visible if tour already completed
    try {
      return localStorage.getItem(TOUR_COMPLETED_KEY) === 'true';
    } catch {
      return false;
    }
  });

  // Derive current stage from active panel
  const currentStage = inferStage(activePanel);

  // Set active panel (can be called from anywhere in the app)
  const setActivePanel = useCallback((panel: string | null) => {
    setActivePanelState(panel);
  }, []);

  // Expansion controls
  const setExpanded = useCallback((value: boolean) => {
    setExpandedState(value);
  }, []);

  const toggleExpanded = useCallback(() => {
    setExpandedState(prev => !prev);
  }, []);

  /**
   * Begin the tour dismissal sequence
   * Called when user clicks "Begin"
   */
  const beginTourDismiss = useCallback(() => {
    // Phase 1: Pre-dismiss cue (show mini indicator in modal)
    setTransitionPhase('pre-dismiss');

    // After 400ms, start fading out the modal
    setTimeout(() => {
      setTransitionPhase('fading-out');

      // After 300ms fade, hide modal and start waiting
      setTimeout(() => {
        setShowTour(false);
        setTourCompleted(true);
        try {
          localStorage.setItem(TOUR_COMPLETED_KEY, 'true');
        } catch {
          // localStorage may not be available
        }
        setTransitionPhase('waiting');

        // After 1.5s pause, start fading in indicator
        setTimeout(() => {
          setIndicatorVisible(true);
          setTransitionPhase('fading-in');

          // After 700ms fade-in, transition complete
          setTimeout(() => {
            setTransitionPhase('complete');
          }, 700);
        }, 1500);
      }, 300);
    }, 400);
  }, []);

  // Legacy completeTour for skip functionality (immediate dismiss)
  const completeTour = useCallback(() => {
    setTourCompleted(true);
    setShowTour(false);
    setIndicatorVisible(true);
    setTransitionPhase('complete');
    try {
      localStorage.setItem(TOUR_COMPLETED_KEY, 'true');
    } catch {
      // localStorage may not be available
    }
  }, []);

  const resetTour = useCallback(() => {
    setTourCompleted(false);
    setShowTour(true);
    setIndicatorVisible(false);
    setTransitionPhase('idle');
    try {
      localStorage.removeItem(TOUR_COMPLETED_KEY);
    } catch {
      // localStorage may not be available
    }
  }, []);

  const showTourModal = useCallback(() => {
    setShowTour(true);
    setIndicatorVisible(false);
    setTransitionPhase('idle');
  }, []);

  const value: PathContextValue = {
    currentStage,
    activePanel,
    expanded,
    tourCompleted,
    showTour,
    transitionPhase,
    indicatorVisible,
    setActivePanel,
    setExpanded,
    toggleExpanded,
    beginTourDismiss,
    completeTour,
    resetTour,
    showTourModal,
  };

  return <PathContext.Provider value={value}>{children}</PathContext.Provider>;
}

/**
 * Hook to use path context
 */
export function usePath(): PathContextValue {
  const context = useContext(PathContext);
  if (!context) {
    throw new Error('usePath must be used within a PathProvider');
  }
  return context;
}

/**
 * Hook to set active panel on mount/unmount
 * Use this in components that represent specific panels
 */
export function useActivePanel(panelName: string) {
  const { setActivePanel } = usePath();

  useEffect(() => {
    setActivePanel(panelName);
    return () => {
      // Don't clear on unmount - let the next panel set itself
      // This avoids flickering between panels
    };
  }, [panelName, setActivePanel]);
}
