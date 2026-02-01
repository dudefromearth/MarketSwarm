/**
 * AlertContext - Shared Alert State Management
 *
 * Provides system-wide alert infrastructure:
 * - CRUD operations for alerts
 * - SSE connection for real-time updates
 * - localStorage persistence
 * - AI evaluation results
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
} from '../types/alerts';

// State shape
interface AlertState {
  alerts: Alert[];
  aiEvaluations: Record<string, AIEvaluation>;
  connected: boolean;
  loading: boolean;
  error: string | null;
}

// Action types
type AlertAction =
  | { type: 'LOAD_ALERTS'; alerts: Alert[] }
  | { type: 'ADD_ALERT'; alert: Alert }
  | { type: 'UPDATE_ALERT'; id: string; updates: Partial<Alert> }
  | { type: 'DELETE_ALERT'; id: string }
  | { type: 'TRIGGER_ALERT'; id: string; triggeredAt: number }
  | { type: 'CLEAR_TRIGGERED' }
  | { type: 'AI_EVALUATION'; alertId: string; evaluation: AIEvaluation }
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'SET_LOADING'; loading: boolean }
  | { type: 'SET_ERROR'; error: string | null };

// Initial state
const initialState: AlertState = {
  alerts: [],
  aiEvaluations: {},
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
  // CRUD Operations
  createAlert: (input: CreateAlertInput) => Alert;
  updateAlert: (input: EditAlertInput) => void;
  deleteAlert: (id: string) => void;
  toggleAlert: (id: string) => void;

  // Queries
  getAlert: (id: string) => Alert | undefined;
  getAlertsForSource: (sourceType: AlertSource['type'], sourceId?: string) => Alert[];
  getAlertsForStrategy: (strategyId: string) => Alert[];
  getTriggeredAlerts: () => Alert[];
  getAIEvaluation: (alertId: string) => AIEvaluation | undefined;

  // Batch Operations
  clearTriggeredAlerts: () => void;
  importAlerts: (alerts: Alert[]) => void;
  exportAlerts: () => Alert[];
}

// Create context
const AlertContext = createContext<AlertContextValue | null>(null);

// Storage key
const STORAGE_KEY = 'fotw_alerts';

// Generate unique ID
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// Default values
const DEFAULT_BEHAVIOR: AlertBehavior = 'once_only';
const DEFAULT_PRIORITY: AlertPriority = 'medium';
const DEFAULT_COLOR = '#3b82f6'; // blue

// Provider component
export function AlertProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(alertReducer, initialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // Load alerts from localStorage on mount
  useEffect(() => {
    dispatch({ type: 'SET_LOADING', loading: true });
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const alerts = JSON.parse(saved) as Alert[];
        dispatch({ type: 'LOAD_ALERTS', alerts });
      } else {
        dispatch({ type: 'SET_LOADING', loading: false });
      }
    } catch (err) {
      console.error('Failed to load alerts from localStorage:', err);
      dispatch({ type: 'SET_ERROR', error: 'Failed to load alerts' });
      dispatch({ type: 'SET_LOADING', loading: false });
    }
  }, []);

  // Persist alerts to localStorage on change
  useEffect(() => {
    if (!state.loading) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state.alerts));
      } catch (err) {
        console.error('Failed to persist alerts:', err);
      }
    }
  }, [state.alerts, state.loading]);

  // SSE connection for real-time updates
  useEffect(() => {
    const connect = () => {
      // Close existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource('/sse/alerts');

      es.onopen = () => {
        dispatch({ type: 'SET_CONNECTED', connected: true });
        dispatch({ type: 'SET_ERROR', error: null });
      };

      es.onerror = () => {
        dispatch({ type: 'SET_CONNECTED', connected: false });
        es.close();

        // Reconnect after delay
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = window.setTimeout(connect, 5000);
      };

      // Alert triggered event
      es.addEventListener('alert_triggered', (event: MessageEvent) => {
        try {
          const data: AlertTriggerEvent = JSON.parse(event.data);
          dispatch({ type: 'TRIGGER_ALERT', id: data.alertId, triggeredAt: data.triggeredAt });

          // Play notification sound
          playAlertSound();

          // If AI reasoning included, store it
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
      });

      // Alert updated event
      es.addEventListener('alert_updated', (event: MessageEvent) => {
        try {
          const data: AlertUpdateEvent = JSON.parse(event.data);
          dispatch({ type: 'UPDATE_ALERT', id: data.alertId, updates: data.updates });
        } catch (err) {
          console.error('Failed to parse alert_updated event:', err);
        }
      });

      // AI evaluation event
      es.addEventListener('ai_evaluation', (event: MessageEvent) => {
        try {
          const evaluation: AIEvaluation = JSON.parse(event.data);
          dispatch({ type: 'AI_EVALUATION', alertId: evaluation.alertId, evaluation });
        } catch (err) {
          console.error('Failed to parse ai_evaluation event:', err);
        }
      });

      eventSourceRef.current = es;
    };

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  // Play alert sound
  const playAlertSound = useCallback(() => {
    try {
      const audio = new Audio(
        'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQA6s+DZpGgLJJPo7bN1'
      );
      audio.volume = 0.3;
      audio.play().catch(() => {});
    } catch {
      // Ignore audio errors
    }
  }, []);

  // Create alert
  const createAlert = useCallback((input: CreateAlertInput): Alert => {
    const now = Date.now();
    const id = generateId();

    const baseAlert = {
      id,
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

    let alert: Alert;

    switch (input.type) {
      case 'price':
        alert = { ...baseAlert, type: 'price' } as Alert;
        break;

      case 'debit':
        alert = {
          ...baseAlert,
          type: 'debit',
          strategyId: input.strategyId || '',
        } as Alert;
        break;

      case 'profit_target':
        alert = {
          ...baseAlert,
          type: 'profit_target',
          strategyId: input.strategyId || '',
          entryDebit: input.entryDebit || 0,
        } as Alert;
        break;

      case 'trailing_stop':
        alert = {
          ...baseAlert,
          type: 'trailing_stop',
          strategyId: input.strategyId || '',
          highWaterMark: input.entryDebit || 0,
        } as Alert;
        break;

      case 'ai_theta_gamma':
        alert = {
          ...baseAlert,
          type: 'ai_theta_gamma',
          strategyId: input.strategyId || '',
          minProfitThreshold: input.minProfitThreshold || 0.5,
          entryDebit: input.entryDebit || 0,
          isZoneActive: false,
        } as Alert;
        break;

      case 'ai_sentiment':
        alert = {
          ...baseAlert,
          type: 'ai_sentiment',
          symbol: input.symbol || 'SPX',
          sentimentThreshold: input.sentimentThreshold || 0,
          direction: input.direction || 'either',
        } as Alert;
        break;

      case 'ai_risk_zone':
        alert = {
          ...baseAlert,
          type: 'ai_risk_zone',
          symbol: input.symbol || 'SPX',
          zoneType: input.zoneType || 'pivot',
        } as Alert;
        break;

      default:
        alert = baseAlert as Alert;
    }

    dispatch({ type: 'ADD_ALERT', alert });
    return alert;
  }, []);

  // Update alert
  const updateAlert = useCallback((input: EditAlertInput) => {
    const { id, ...updates } = input;
    dispatch({ type: 'UPDATE_ALERT', id, updates });
  }, []);

  // Delete alert
  const deleteAlert = useCallback((id: string) => {
    dispatch({ type: 'DELETE_ALERT', id });
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

  const value: AlertContextValue = {
    ...state,
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
