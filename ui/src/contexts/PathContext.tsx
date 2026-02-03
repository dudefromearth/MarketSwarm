/**
 * PathContext - FOTW Path Stage State Management
 *
 * Provides:
 * - Current stage inference from active UI panel
 * - Expansion state for the path indicator
 * - Tour completion tracking (persisted to localStorage)
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

interface PathState {
  currentStage: Stage;
  activePanel: string | null;
  expanded: boolean;
  tourCompleted: boolean;
  showTour: boolean;
}

interface PathContextValue extends PathState {
  setActivePanel: (panel: string | null) => void;
  setExpanded: (expanded: boolean) => void;
  toggleExpanded: () => void;
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

  // Tour controls
  const completeTour = useCallback(() => {
    setTourCompleted(true);
    setShowTour(false);
    try {
      localStorage.setItem(TOUR_COMPLETED_KEY, 'true');
    } catch {
      // localStorage may not be available
    }
  }, []);

  const resetTour = useCallback(() => {
    setTourCompleted(false);
    setShowTour(true);
    try {
      localStorage.removeItem(TOUR_COMPLETED_KEY);
    } catch {
      // localStorage may not be available
    }
  }, []);

  const showTourModal = useCallback(() => {
    setShowTour(true);
  }, []);

  const value: PathContextValue = {
    currentStage,
    activePanel,
    expanded,
    tourCompleted,
    showTour,
    setActivePanel,
    setExpanded,
    toggleExpanded,
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
