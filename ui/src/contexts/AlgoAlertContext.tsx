/**
 * AlgoAlertContext — State management + SSE for algo alerts.
 *
 * Follows AlertContext.tsx pattern: useReducer + Context + SSE subscription.
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import { subscribeAlertSSE } from '../services/alertSSEManager';
import type {
  AlgoAlert,
  AlgoProposal,
  CreateAlgoAlertInput,
  UpdateAlgoAlertInput,
  AlgoAlertEvaluationEvent,
  FilterEvaluationResult,
} from '../types/algoAlerts';
import {
  fetchAlgoAlerts,
  createAlgoAlertApi,
  updateAlgoAlertApi,
  deleteAlgoAlertApi,
  fetchAlgoProposals,
  approveProposalApi,
  rejectProposalApi,
} from '../services/algoAlertService';

// ==================== State ====================

interface AlgoAlertState {
  algoAlerts: AlgoAlert[];
  proposals: AlgoProposal[];
  /** Per-alert filter state from latest evaluation (keyed by alert ID) */
  filterStates: Record<string, FilterEvaluationResult[]>;
  connected: boolean;
  loading: boolean;
  error: string | null;
}

const initialState: AlgoAlertState = {
  algoAlerts: [],
  proposals: [],
  filterStates: {},
  connected: false,
  loading: true,
  error: null,
};

// ==================== Actions ====================

type AlgoAlertAction =
  | { type: 'LOAD_ALERTS'; alerts: AlgoAlert[] }
  | { type: 'ADD_ALERT'; alert: AlgoAlert }
  | { type: 'UPDATE_ALERT'; id: string; updates: Partial<AlgoAlert> }
  | { type: 'DELETE_ALERT'; id: string }
  | { type: 'LOAD_PROPOSALS'; proposals: AlgoProposal[] }
  | { type: 'ADD_PROPOSAL'; proposal: AlgoProposal }
  | { type: 'UPDATE_PROPOSAL'; id: string; updates: Partial<AlgoProposal> }
  | { type: 'SET_FILTER_STATE'; alertId: string; filterResults: FilterEvaluationResult[] }
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_ERROR'; error: string | null };

function algoAlertReducer(state: AlgoAlertState, action: AlgoAlertAction): AlgoAlertState {
  switch (action.type) {
    case 'LOAD_ALERTS':
      return { ...state, algoAlerts: action.alerts, loading: false };
    case 'ADD_ALERT':
      return { ...state, algoAlerts: [...state.algoAlerts, action.alert] };
    case 'UPDATE_ALERT':
      return {
        ...state,
        algoAlerts: state.algoAlerts.map(a =>
          a.id === action.id ? { ...a, ...action.updates } : a
        ),
      };
    case 'DELETE_ALERT':
      return {
        ...state,
        algoAlerts: state.algoAlerts.filter(a => a.id !== action.id),
      };
    case 'LOAD_PROPOSALS':
      return { ...state, proposals: action.proposals };
    case 'ADD_PROPOSAL': {
      // Dedup: replace if same ID already exists
      const existing = state.proposals.find(p => p.id === action.proposal.id);
      if (existing) {
        return {
          ...state,
          proposals: state.proposals.map(p =>
            p.id === action.proposal.id ? action.proposal : p
          ),
        };
      }
      return { ...state, proposals: [...state.proposals, action.proposal] };
    }
    case 'UPDATE_PROPOSAL':
      return {
        ...state,
        proposals: state.proposals.map(p =>
          p.id === action.id ? { ...p, ...action.updates } : p
        ),
      };
    case 'SET_FILTER_STATE':
      return {
        ...state,
        filterStates: {
          ...state.filterStates,
          [action.alertId]: action.filterResults,
        },
      };
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected };
    case 'SET_LOADING':
      return { ...state, loading: action.loading };
    case 'SET_ERROR':
      return { ...state, error: action.error, loading: false };
    default:
      return state;
  }
}

// ==================== Context ====================

interface AlgoAlertContextValue extends AlgoAlertState {
  createAlgoAlert: (input: CreateAlgoAlertInput) => Promise<AlgoAlert | null>;
  updateAlgoAlert: (id: string, input: UpdateAlgoAlertInput) => Promise<AlgoAlert | null>;
  deleteAlgoAlert: (id: string) => Promise<boolean>;
  approveProposal: (id: string) => Promise<AlgoProposal | null>;
  rejectProposal: (id: string) => Promise<AlgoProposal | null>;
  getActiveProposals: () => AlgoProposal[];
  getAlertsForPosition: (positionId: string) => AlgoAlert[];
  getFilterState: (alertId: string) => FilterEvaluationResult[] | undefined;
  refreshAlerts: () => Promise<void>;
  refreshProposals: () => Promise<void>;
}

const AlgoAlertContext = createContext<AlgoAlertContextValue | null>(null);

// ==================== Provider ====================

export function AlgoAlertProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(algoAlertReducer, initialState);

  // Load initial data
  const loadAlerts = useCallback(async () => {
    try {
      const alerts = await fetchAlgoAlerts();
      dispatch({ type: 'LOAD_ALERTS', alerts });
    } catch (err) {
      console.error('Failed to load algo alerts:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to load algo alerts' });
    }
  }, []);

  const loadProposals = useCallback(async () => {
    try {
      const proposals = await fetchAlgoProposals(undefined, 'pending');
      dispatch({ type: 'LOAD_PROPOSALS', proposals });
    } catch (err) {
      console.error('Failed to load algo proposals:', err);
    }
  }, []);

  useEffect(() => {
    loadAlerts();
    loadProposals();
  }, [loadAlerts, loadProposals]);

  // SSE subscription for real-time updates (shared with AlertContext)
  useEffect(() => {
    const unsubscribe = subscribeAlertSSE(
      {
        algo_alert_proposal: (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            if (data.data) {
              const proposal: AlgoProposal = {
                id: data.data.proposalId,
                algoAlertId: data.data.algoAlertId,
                userId: 0,
                type: data.data.type,
                status: 'pending',
                suggestedPosition: data.data.suggestedPosition,
                reasoning: data.data.reasoning,
                filterResults: [],
                structuralAlignmentScore: data.data.structuralAlignmentScore || 0,
                createdAt: new Date().toISOString(),
                expiresAt: data.data.expiresAt,
              };
              dispatch({ type: 'ADD_PROPOSAL', proposal });
            }
          } catch (e) {
            console.error('Parse algo_alert_proposal error:', e);
          }
        },
        algo_alert_evaluation: (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            if (data.data) {
              const evalData = data.data as AlgoAlertEvaluationEvent;
              dispatch({
                type: 'SET_FILTER_STATE',
                alertId: evalData.algoAlertId,
                filterResults: evalData.filterResults,
              });
              if (evalData.status) {
                dispatch({
                  type: 'UPDATE_ALERT',
                  id: evalData.algoAlertId,
                  updates: {
                    status: evalData.status as AlgoAlert['status'],
                    frozenReason: evalData.frozenReason,
                  },
                });
              }
            }
          } catch (e) {
            console.error('Parse algo_alert_evaluation error:', e);
          }
        },
        algo_alert_frozen: (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            if (data.data) {
              dispatch({
                type: 'UPDATE_ALERT',
                id: data.data.algoAlertId,
                updates: { status: 'frozen', frozenReason: data.data.reason },
              });
            }
          } catch (e) {
            console.error('Parse algo_alert_frozen error:', e);
          }
        },
        algo_alert_resumed: (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            if (data.data) {
              dispatch({
                type: 'UPDATE_ALERT',
                id: data.data.algoAlertId,
                updates: { status: 'active', frozenReason: undefined },
              });
            }
          } catch (e) {
            console.error('Parse algo_alert_resumed error:', e);
          }
        },
      },
      () => dispatch({ type: 'SET_CONNECTED', connected: true }),
      () => dispatch({ type: 'SET_CONNECTED', connected: false }),
    );

    return unsubscribe;
  }, []);

  // CRUD operations
  const createAlgoAlert = useCallback(async (input: CreateAlgoAlertInput): Promise<AlgoAlert | null> => {
    try {
      const alert = await createAlgoAlertApi(input);
      dispatch({ type: 'ADD_ALERT', alert });
      return alert;
    } catch (err) {
      console.error('Failed to create algo alert:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to create algo alert' });
      return null;
    }
  }, []);

  const updateAlgoAlert = useCallback(async (id: string, input: UpdateAlgoAlertInput): Promise<AlgoAlert | null> => {
    try {
      const alert = await updateAlgoAlertApi(id, input);
      dispatch({ type: 'UPDATE_ALERT', id, updates: alert });
      return alert;
    } catch (err) {
      console.error('Failed to update algo alert:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to update algo alert' });
      return null;
    }
  }, []);

  const deleteAlgoAlert = useCallback(async (id: string): Promise<boolean> => {
    try {
      await deleteAlgoAlertApi(id);
      dispatch({ type: 'DELETE_ALERT', id });
      return true;
    } catch (err) {
      console.error('Failed to delete algo alert:', err);
      return false;
    }
  }, []);

  const approveProposal = useCallback(async (id: string): Promise<AlgoProposal | null> => {
    try {
      const proposal = await approveProposalApi(id);
      dispatch({ type: 'UPDATE_PROPOSAL', id, updates: { status: 'approved', resolvedAt: new Date().toISOString() } });
      return proposal;
    } catch (err) {
      console.error('Failed to approve proposal:', err);
      return null;
    }
  }, []);

  const rejectProposal = useCallback(async (id: string): Promise<AlgoProposal | null> => {
    try {
      const proposal = await rejectProposalApi(id);
      dispatch({ type: 'UPDATE_PROPOSAL', id, updates: { status: 'rejected', resolvedAt: new Date().toISOString() } });
      return proposal;
    } catch (err) {
      console.error('Failed to reject proposal:', err);
      return null;
    }
  }, []);

  // Queries
  const getActiveProposals = useCallback((): AlgoProposal[] => {
    const now = new Date().toISOString();
    return state.proposals.filter(p =>
      p.status === 'pending' && p.expiresAt > now
    );
  }, [state.proposals]);

  const getAlertsForPosition = useCallback((positionId: string): AlgoAlert[] => {
    return state.algoAlerts.filter(a => a.positionId === positionId);
  }, [state.algoAlerts]);

  const getFilterState = useCallback((alertId: string): FilterEvaluationResult[] | undefined => {
    return state.filterStates[alertId];
  }, [state.filterStates]);

  const value: AlgoAlertContextValue = {
    ...state,
    createAlgoAlert,
    updateAlgoAlert,
    deleteAlgoAlert,
    approveProposal,
    rejectProposal,
    getActiveProposals,
    getAlertsForPosition,
    getFilterState,
    refreshAlerts: loadAlerts,
    refreshProposals: loadProposals,
  };

  return (
    <AlgoAlertContext.Provider value={value}>
      {children}
    </AlgoAlertContext.Provider>
  );
}

// ==================== Hook ====================

export function useAlgoAlerts(): AlgoAlertContextValue {
  const context = useContext(AlgoAlertContext);
  if (!context) {
    throw new Error('useAlgoAlerts must be used within an AlgoAlertProvider');
  }
  return context;
}
