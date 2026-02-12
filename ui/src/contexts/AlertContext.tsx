/**
 * AlertContext - Shared Alert State Management
 *
 * Provides system-wide alert infrastructure:
 * - CRUD operations for alerts (persisted to server)
 * - SSE connection for real-time updates
 * - AI evaluation results
 *
 * Alerts are now server-side (Journal service) and survive browser refresh.
 * Client is purely UI - no alert logic, no modals, no interruptions.
 *
 * Usage:
 *   const { alerts, createAlert, deleteAlert } = useAlerts();
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';

import { subscribeAlertSSE } from '../services/alertSSEManager';

import type {
  Alert,
  CreateAlertInput,
  EditAlertInput,
  AlertSource,
  AIEvaluation,
  AlertTriggerEvent,
  AlertUpdateEvent,
  AlertBehavior,
  AlertPriority,
  // v1.1 types
  AlertDefinition,
  AlertLifecycleStage,
  CreateAlertDefinitionInput,
} from '../types/alerts';

import {
  fetchAlerts,
  createAlertApi,
  updateAlertApi,
  deleteAlertApi,
  // v1.1 API methods
  fetchAlertDefinitions,
  createAlertDefinition,
  pauseAlert as pauseAlertApi,
  resumeAlert as resumeAlertApi,
  acknowledgeAlert as acknowledgeAlertApi,
  dismissAlert as dismissAlertApi,
  overrideAlert as overrideAlertApi,
} from '../services/alertService';

// State shape
interface AlertState {
  // Legacy alerts (v1)
  alerts: Alert[];
  aiEvaluations: Record<string, AIEvaluation>;

  // v1.1 Alert Definitions
  alertDefinitions: AlertDefinition[];

  // Connection state
  connected: boolean;
  loading: boolean;
  error: string | null;
}

// Action types
type AlertAction =
  // Legacy actions
  | { type: 'LOAD_ALERTS'; alerts: Alert[] }
  | { type: 'ADD_ALERT'; alert: Alert }
  | { type: 'UPDATE_ALERT'; id: string; updates: Partial<Alert> }
  | { type: 'DELETE_ALERT'; id: string }
  | { type: 'TRIGGER_ALERT'; id: string; triggeredAt: number }
  | { type: 'CLEAR_TRIGGERED' }
  | { type: 'AI_EVALUATION'; alertId: string; evaluation: AIEvaluation }
  // v1.1 actions
  | { type: 'LOAD_DEFINITIONS'; definitions: AlertDefinition[] }
  | { type: 'ADD_DEFINITION'; definition: AlertDefinition }
  | { type: 'UPDATE_DEFINITION'; id: string; updates: Partial<AlertDefinition> }
  | { type: 'DELETE_DEFINITION'; id: string }
  | { type: 'SET_LIFECYCLE_STAGE'; id: string; stage: AlertLifecycleStage }
  // Common actions
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_ERROR'; error: string | null };

// Initial state
const initialState: AlertState = {
  alerts: [],
  aiEvaluations: {},
  alertDefinitions: [],
  connected: false,
  loading: false,
  error: null,
};

// Reducer
function alertReducer(state: AlertState, action: AlertAction): AlertState {
  switch (action.type) {
    case 'LOAD_ALERTS':
      return { ...state, alerts: action.alerts, loading: false };

    case 'ADD_ALERT':
      return { ...state, alerts: [...state.alerts, action.alert] };

    case 'UPDATE_ALERT':
      return {
        ...state,
        alerts: state.alerts.map((a) =>
          a.id === action.id ? { ...a, ...action.updates, updatedAt: Date.now() } as Alert : a
        ),
      };

    case 'DELETE_ALERT': {
      const { [action.id]: _, ...remainingEvaluations } = state.aiEvaluations;
      return {
        ...state,
        alerts: state.alerts.filter((a) => a.id !== action.id),
        aiEvaluations: remainingEvaluations,
      };
    }

    case 'TRIGGER_ALERT':
      return {
        ...state,
        alerts: state.alerts.map((a) =>
          a.id === action.id
            ? {
                ...a,
                triggered: true,
                triggeredAt: action.triggeredAt,
                triggerCount: (a.triggerCount || 0) + 1,
              }
            : a
        ),
      };

    case 'CLEAR_TRIGGERED':
      return {
        ...state,
        alerts: state.alerts.map((a) => ({ ...a, triggered: false })),
      };

    case 'AI_EVALUATION':
      return {
        ...state,
        aiEvaluations: {
          ...state.aiEvaluations,
          [action.alertId]: action.evaluation,
        },
        alerts: state.alerts.map((a) =>
          a.id === action.alertId
            ? {
                ...a,
                aiConfidence: action.evaluation.confidence,
                aiReasoning: action.evaluation.reasoning,
                lastAIUpdate: action.evaluation.timestamp,
                ...(action.evaluation.zoneLow !== undefined && { zoneLow: action.evaluation.zoneLow }),
                ...(action.evaluation.zoneHigh !== undefined && { zoneHigh: action.evaluation.zoneHigh }),
              }
            : a
        ),
      };

    // v1.1 AlertDefinition actions
    case 'LOAD_DEFINITIONS':
      return { ...state, alertDefinitions: action.definitions, loading: false };

    case 'ADD_DEFINITION':
      return { ...state, alertDefinitions: [...state.alertDefinitions, action.definition] };

    case 'UPDATE_DEFINITION':
      return {
        ...state,
        alertDefinitions: state.alertDefinitions.map((d) =>
          d.id === action.id
            ? { ...d, ...action.updates, updatedAt: new Date().toISOString() }
            : d
        ),
      };

    case 'DELETE_DEFINITION':
      return {
        ...state,
        alertDefinitions: state.alertDefinitions.filter((d) => d.id !== action.id),
      };

    case 'SET_LIFECYCLE_STAGE':
      return {
        ...state,
        alertDefinitions: state.alertDefinitions.map((d) =>
          d.id === action.id
            ? {
                ...d,
                lifecycleStage: action.stage,
                updatedAt: new Date().toISOString(),
                ...(action.stage === 'accomplished' || action.stage === 'dismissed'
                  ? { acknowledgedAt: new Date().toISOString() }
                  : {}),
              }
            : d
        ),
      };

    case 'SET_CONNECTED':
      return { ...state, connected: action.connected };

    case 'SET_LOADING':
      return { ...state, loading: action.loading };

    case 'SET_ERROR':
      return { ...state, error: action.error };

    default:
      return state;
  }
}

// Context value interface
interface AlertContextValue extends AlertState {
  // Legacy CRUD Operations (v1)
  createAlert: (input: CreateAlertInput) => Alert;
  updateAlert: (input: EditAlertInput) => void;
  deleteAlert: (id: string) => void;
  toggleAlert: (id: string) => void;

  // Legacy Queries (v1)
  getAlert: (id: string) => Alert | undefined;
  getAlertsForSource: (sourceType: AlertSource['type'], sourceId?: string) => Alert[];
  getAlertsForStrategy: (strategyId: string) => Alert[];
  getTriggeredAlerts: () => Alert[];
  getAIEvaluation: (alertId: string) => AIEvaluation | undefined;

  // Legacy Batch Operations (v1)
  clearTriggeredAlerts: () => void;
  importAlerts: (alerts: Alert[]) => void;
  exportAlerts: () => Alert[];

  // v1.1 AlertDefinition Operations
  createDefinition: (input: CreateAlertDefinitionInput) => Promise<AlertDefinition | null>;
  pauseDefinition: (id: string) => Promise<void>;
  resumeDefinition: (id: string) => Promise<void>;
  acknowledgeDefinition: (id: string) => Promise<void>;
  dismissDefinition: (id: string) => Promise<void>;
  overrideDefinition: (id: string, reason: string) => Promise<void>;
  deleteDefinition: (id: string) => Promise<void>;

  // v1.1 Queries
  getDefinition: (id: string) => AlertDefinition | undefined;
  getDefinitionsNeedingAttention: () => AlertDefinition[];
}

// Create context
const AlertContext = createContext<AlertContextValue | null>(null);

// Default values
const DEFAULT_BEHAVIOR: AlertBehavior = 'once_only';
const DEFAULT_PRIORITY: AlertPriority = 'medium';
const DEFAULT_COLOR = '#3b82f6'; // blue

// Provider component
export function AlertProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(alertReducer, initialState);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Load alerts from API on mount
  useEffect(() => {
    const loadAlerts = async () => {
      dispatch({ type: 'SET_LOADING', loading: true });
      try {
        const alerts = await fetchAlerts();
        dispatch({ type: 'LOAD_ALERTS', alerts });
      } catch (err) {
        console.error('Failed to load alerts from API:', err);
        dispatch({ type: 'SET_ERROR', error: 'Failed to load alerts' });
        dispatch({ type: 'SET_LOADING', loading: false });
      }
    };
    loadAlerts();
  }, []);

  // Initialize audio element once
  useEffect(() => {
    const audio = new Audio(
      'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQA6s+DZpGgLJJPo7bN1'
    );
    audio.volume = 0.3;
    audioRef.current = audio;

    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  // Play alert sound (reuses single audio element)
  const playAlertSound = useCallback(() => {
    try {
      if (audioRef.current) {
        audioRef.current.currentTime = 0;
        audioRef.current.play().catch(() => {});
      }
    } catch {
      // Ignore audio errors
    }
  }, []);

  // SSE connection for real-time updates (shared with AlgoAlertContext)
  useEffect(() => {
    const unsubscribe = subscribeAlertSSE(
      {
        alert_triggered: (event: MessageEvent) => {
          try {
            const data: AlertTriggerEvent = JSON.parse(event.data);
            dispatch({ type: 'TRIGGER_ALERT', id: data.alertId, triggeredAt: data.triggeredAt });
            playAlertSound();

            if (data.aiReasoning !== undefined) {
              dispatch({
                type: 'AI_EVALUATION',
                alertId: data.alertId,
                evaluation: {
                  alertId: data.alertId,
                  timestamp: data.triggeredAt,
                  provider: 'openai',
                  model: 'gpt-4o',
                  shouldTrigger: true,
                  confidence: data.aiConfidence || 0,
                  reasoning: data.aiReasoning,
                  latencyMs: 0,
                },
              });
            }
          } catch (err) {
            console.error('Failed to parse alert_triggered event:', err);
          }
        },
        alert_updated: (event: MessageEvent) => {
          try {
            const data: AlertUpdateEvent = JSON.parse(event.data);
            dispatch({ type: 'UPDATE_ALERT', id: data.alertId, updates: data.updates });
          } catch (err) {
            console.error('Failed to parse alert_updated event:', err);
          }
        },
        ai_evaluation: (event: MessageEvent) => {
          try {
            const evaluation: AIEvaluation = JSON.parse(event.data);
            dispatch({ type: 'AI_EVALUATION', alertId: evaluation.alertId, evaluation });
          } catch (err) {
            console.error('Failed to parse ai_evaluation event:', err);
          }
        },
      },
      () => {
        dispatch({ type: 'SET_CONNECTED', connected: true });
        dispatch({ type: 'SET_ERROR', error: null });
      },
      () => {
        dispatch({ type: 'SET_CONNECTED', connected: false });
      },
    );

    return unsubscribe;
  }, [playAlertSound]);

  // Create alert (calls API, updates local state on success)
  const createAlert = useCallback((input: CreateAlertInput): Alert => {
    const now = Date.now();

    // Build optimistic alert for immediate UI feedback
    const baseAlert = {
      id: `temp-${now}`, // Temporary ID, will be replaced by server
      type: input.type,
      source: input.source,
      condition: input.condition,
      targetValue: input.targetValue,
      behavior: input.behavior || DEFAULT_BEHAVIOR,
      priority: input.priority || DEFAULT_PRIORITY,
      color: input.color || DEFAULT_COLOR,
      label: input.label,
      enabled: true,
      triggered: false,
      triggerCount: 0,
      createdAt: now,
      updatedAt: now,
    };

    let optimisticAlert: Alert;

    switch (input.type) {
      case 'price':
        optimisticAlert = { ...baseAlert, type: 'price' } as Alert;
        break;

      case 'debit':
        optimisticAlert = {
          ...baseAlert,
          type: 'debit',
          strategyId: input.strategyId || '',
        } as Alert;
        break;

      case 'profit_target':
        optimisticAlert = {
          ...baseAlert,
          type: 'profit_target',
          strategyId: input.strategyId || '',
          entryDebit: input.entryDebit || 0,
        } as Alert;
        break;

      case 'trailing_stop':
        optimisticAlert = {
          ...baseAlert,
          type: 'trailing_stop',
          strategyId: input.strategyId || '',
          highWaterMark: input.entryDebit || 0,
        } as Alert;
        break;

      case 'ai_theta_gamma':
        optimisticAlert = {
          ...baseAlert,
          type: 'ai_theta_gamma',
          strategyId: input.strategyId || '',
          minProfitThreshold: input.minProfitThreshold || 0.5,
          entryDebit: input.entryDebit || 0,
          isZoneActive: false,
        } as Alert;
        break;

      case 'ai_sentiment':
        optimisticAlert = {
          ...baseAlert,
          type: 'ai_sentiment',
          symbol: input.symbol || 'SPX',
          sentimentThreshold: input.sentimentThreshold || 0,
          direction: input.direction || 'either',
        } as Alert;
        break;

      case 'ai_risk_zone':
        optimisticAlert = {
          ...baseAlert,
          type: 'ai_risk_zone',
          symbol: input.symbol || 'SPX',
          zoneType: input.zoneType || 'pivot',
        } as Alert;
        break;

      case 'portfolio_pnl':
        optimisticAlert = {
          ...baseAlert,
          type: 'portfolio_pnl',
        } as Alert;
        break;

      case 'portfolio_trailing':
        optimisticAlert = {
          ...baseAlert,
          type: 'portfolio_trailing',
          highWaterMark: 0,
        } as Alert;
        break;

      case 'greeks_threshold':
        optimisticAlert = {
          ...baseAlert,
          type: 'greeks_threshold',
          greekName: input.greekName || 'delta',
        } as Alert;
        break;

      default:
        optimisticAlert = baseAlert as Alert;
    }

    // Add optimistically to UI
    dispatch({ type: 'ADD_ALERT', alert: optimisticAlert });

    // Call API in background and update with real data
    createAlertApi(input)
      .then((serverAlert) => {
        // Remove temp, add real alert
        dispatch({ type: 'DELETE_ALERT', id: optimisticAlert.id });
        dispatch({ type: 'ADD_ALERT', alert: serverAlert });
      })
      .catch((err) => {
        console.error('Failed to create alert on server:', err);
        // Remove optimistic alert on failure
        dispatch({ type: 'DELETE_ALERT', id: optimisticAlert.id });
        dispatch({ type: 'SET_ERROR', error: 'Failed to create alert' });
      });

    return optimisticAlert;
  }, []);

  // Update alert (calls API, updates local state optimistically)
  const updateAlert = useCallback((input: EditAlertInput) => {
    const { id, ...updates } = input;
    // Optimistic update
    dispatch({ type: 'UPDATE_ALERT', id, updates: updates as Partial<Alert> });

    // Call API in background
    updateAlertApi(input).catch((err) => {
      console.error('Failed to update alert on server:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to update alert' });
    });
  }, []);

  // Delete alert (calls API, updates local state optimistically)
  const deleteAlert = useCallback((id: string) => {
    // Skip temp alerts that haven't been persisted yet
    if (id.startsWith('temp-')) {
      dispatch({ type: 'DELETE_ALERT', id });
      return;
    }

    // Optimistic delete
    dispatch({ type: 'DELETE_ALERT', id });

    // Call API in background
    deleteAlertApi(id).catch((err) => {
      console.error('Failed to delete alert on server:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to delete alert' });
    });
  }, []);

  // Toggle alert enabled
  const toggleAlert = useCallback((id: string) => {
    const alert = state.alerts.find((a) => a.id === id);
    if (alert) {
      dispatch({ type: 'UPDATE_ALERT', id, updates: { enabled: !alert.enabled } });
    }
  }, [state.alerts]);

  // Get single alert
  const getAlert = useCallback(
    (id: string) => state.alerts.find((a) => a.id === id),
    [state.alerts]
  );

  // Get alerts for source type/id
  const getAlertsForSource = useCallback(
    (sourceType: AlertSource['type'], sourceId?: string) =>
      state.alerts.filter(
        (a) => a.source.type === sourceType && (sourceId === undefined || a.source.id === sourceId)
      ),
    [state.alerts]
  );

  // Get alerts for strategy
  const getAlertsForStrategy = useCallback(
    (strategyId: string) =>
      state.alerts.filter((a) => 'strategyId' in a && a.strategyId === strategyId),
    [state.alerts]
  );

  // Get triggered alerts
  const getTriggeredAlerts = useCallback(
    () => state.alerts.filter((a) => a.triggered),
    [state.alerts]
  );

  // Get AI evaluation
  const getAIEvaluation = useCallback(
    (alertId: string) => state.aiEvaluations[alertId],
    [state.aiEvaluations]
  );

  // Clear triggered alerts
  const clearTriggeredAlerts = useCallback(() => {
    dispatch({ type: 'CLEAR_TRIGGERED' });
  }, []);

  // Import alerts
  const importAlerts = useCallback((alerts: Alert[]) => {
    dispatch({ type: 'LOAD_ALERTS', alerts });
  }, []);

  // Export alerts
  const exportAlerts = useCallback(() => state.alerts, [state.alerts]);

  // ==================== v1.1 AlertDefinition Operations ====================

  // Create definition (prompt-first)
  const createDefinition = useCallback(async (input: CreateAlertDefinitionInput): Promise<AlertDefinition | null> => {
    try {
      const definition = await createAlertDefinition(input);
      dispatch({ type: 'ADD_DEFINITION', definition });
      return definition;
    } catch (err) {
      console.error('Failed to create alert definition:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to create alert' });
      return null;
    }
  }, []);

  // Pause definition
  const pauseDefinition = useCallback(async (id: string): Promise<void> => {
    // Optimistic update
    dispatch({ type: 'UPDATE_DEFINITION', id, updates: { status: 'paused' } });
    try {
      await pauseAlertApi(id);
    } catch (err) {
      console.error('Failed to pause alert:', err);
      dispatch({ type: 'UPDATE_DEFINITION', id, updates: { status: 'active' } });
      dispatch({ type: 'SET_ERROR', error: 'Failed to pause alert' });
    }
  }, []);

  // Resume definition
  const resumeDefinition = useCallback(async (id: string): Promise<void> => {
    dispatch({ type: 'UPDATE_DEFINITION', id, updates: { status: 'active' } });
    try {
      await resumeAlertApi(id);
    } catch (err) {
      console.error('Failed to resume alert:', err);
      dispatch({ type: 'UPDATE_DEFINITION', id, updates: { status: 'paused' } });
      dispatch({ type: 'SET_ERROR', error: 'Failed to resume alert' });
    }
  }, []);

  // Acknowledge definition (moves to accomplished stage)
  const acknowledgeDefinition = useCallback(async (id: string): Promise<void> => {
    dispatch({ type: 'SET_LIFECYCLE_STAGE', id, stage: 'accomplished' });
    try {
      await acknowledgeAlertApi(id);
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
      dispatch({ type: 'SET_LIFECYCLE_STAGE', id, stage: 'warn' }); // Revert
      dispatch({ type: 'SET_ERROR', error: 'Failed to acknowledge alert' });
    }
  }, []);

  // Dismiss definition
  const dismissDefinition = useCallback(async (id: string): Promise<void> => {
    dispatch({ type: 'SET_LIFECYCLE_STAGE', id, stage: 'dismissed' });
    try {
      await dismissAlertApi(id);
    } catch (err) {
      console.error('Failed to dismiss alert:', err);
      dispatch({ type: 'SET_LIFECYCLE_STAGE', id, stage: 'warn' }); // Revert
      dispatch({ type: 'SET_ERROR', error: 'Failed to dismiss alert' });
    }
  }, []);

  // Override definition (block override with reason)
  const overrideDefinition = useCallback(async (id: string, reason: string): Promise<void> => {
    dispatch({
      type: 'UPDATE_DEFINITION',
      id,
      updates: { lifecycleStage: 'overridden', overrideReason: reason },
    });
    try {
      await overrideAlertApi(id, reason);
    } catch (err) {
      console.error('Failed to override alert:', err);
      dispatch({
        type: 'UPDATE_DEFINITION',
        id,
        updates: { lifecycleStage: 'warn', overrideReason: undefined },
      });
      dispatch({ type: 'SET_ERROR', error: 'Failed to override alert' });
    }
  }, []);

  // Delete definition
  const deleteDefinition = useCallback(async (id: string): Promise<void> => {
    const definition = state.alertDefinitions.find((d) => d.id === id);
    dispatch({ type: 'DELETE_DEFINITION', id });
    try {
      await deleteAlertApi(id);
    } catch (err) {
      console.error('Failed to delete alert definition:', err);
      if (definition) {
        dispatch({ type: 'ADD_DEFINITION', definition });
      }
      dispatch({ type: 'SET_ERROR', error: 'Failed to delete alert' });
    }
  }, [state.alertDefinitions]);

  // Get single definition
  const getDefinition = useCallback(
    (id: string) => state.alertDefinitions.find((d) => d.id === id),
    [state.alertDefinitions]
  );

  // Get definitions needing attention (update or warn stage)
  const getDefinitionsNeedingAttention = useCallback(
    () => state.alertDefinitions.filter(
      (d) => d.lifecycleStage === 'update' || d.lifecycleStage === 'warn'
    ),
    [state.alertDefinitions]
  );

  const value: AlertContextValue = {
    ...state,
    // Legacy v1
    createAlert,
    updateAlert,
    deleteAlert,
    toggleAlert,
    getAlert,
    getAlertsForSource,
    getAlertsForStrategy,
    getTriggeredAlerts,
    getAIEvaluation,
    clearTriggeredAlerts,
    importAlerts,
    exportAlerts,
    // v1.1
    createDefinition,
    pauseDefinition,
    resumeDefinition,
    acknowledgeDefinition,
    dismissDefinition,
    overrideDefinition,
    deleteDefinition,
    getDefinition,
    getDefinitionsNeedingAttention,
  };

  return <AlertContext.Provider value={value}>{children}</AlertContext.Provider>;
}

// Hook to use alert context
export function useAlerts(): AlertContextValue {
  const context = useContext(AlertContext);
  if (!context) {
    throw new Error('useAlerts must be used within an AlertProvider');
  }
  return context;
}

// Hook for alerts filtered by source (convenience)
export function useAlertsForSource(sourceType: AlertSource['type'], sourceId?: string) {
  const context = useAlerts();
  return {
    ...context,
    alerts: context.getAlertsForSource(sourceType, sourceId),
  };
}

// Hook for alerts filtered by strategy (convenience)
export function useAlertsForStrategy(strategyId: string) {
  const context = useAlerts();
  return {
    ...context,
    alerts: context.getAlertsForStrategy(strategyId),
  };
}
