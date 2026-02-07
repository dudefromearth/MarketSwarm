// contexts/SystemNotificationsContext.tsx
// System-level notifications for health, connectivity, errors, and process status
//
// This is SEPARATE from AlertContext which handles user-programmable trading alerts.
// SystemNotifications are for infrastructure/operational concerns:
// - Connectivity issues (SSE disconnected, API unreachable)
// - Caught errors (API failures, unexpected responses)
// - Process errors (service failures, background task issues)
// - Type mismatches (data validation failures)
// - Sync status (offline queue issues)

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';

// Notification severity levels
export type NotificationSeverity = 'info' | 'warning' | 'error' | 'success';

// Notification categories for filtering/grouping
export type NotificationCategory =
  | 'connectivity'    // SSE, WebSocket, network issues
  | 'api'             // API request failures
  | 'sync'            // Offline sync issues
  | 'process'         // Background process/service errors
  | 'validation'      // Type mismatches, data validation
  | 'system';         // General system messages

export interface SystemNotification {
  id: string;
  category: NotificationCategory;
  severity: NotificationSeverity;
  title: string;
  message: string;
  details?: string;           // Stack trace or additional context
  timestamp: number;
  read: boolean;
  dismissed: boolean;
  source?: string;            // Component or service that raised it
  actionLabel?: string;       // Optional action button text
  actionCallback?: () => void; // Optional action handler
  autoExpire?: number;        // Auto-dismiss after ms (0 = never)
}

export type CreateNotificationInput = Omit<SystemNotification, 'id' | 'timestamp' | 'read' | 'dismissed'>;

// State
interface NotificationsState {
  notifications: SystemNotification[];
  maxNotifications: number;  // Keep last N notifications
}

// Actions
type NotificationsAction =
  | { type: 'ADD'; notification: SystemNotification }
  | { type: 'MARK_READ'; id: string }
  | { type: 'MARK_ALL_READ' }
  | { type: 'DISMISS'; id: string }
  | { type: 'DISMISS_ALL' }
  | { type: 'REMOVE'; id: string }
  | { type: 'CLEAR_OLD'; maxAge: number };

const initialState: NotificationsState = {
  notifications: [],
  maxNotifications: 100,
};

function notificationsReducer(state: NotificationsState, action: NotificationsAction): NotificationsState {
  switch (action.type) {
    case 'ADD': {
      const notifications = [action.notification, ...state.notifications]
        .slice(0, state.maxNotifications);
      return { ...state, notifications };
    }

    case 'MARK_READ':
      return {
        ...state,
        notifications: state.notifications.map(n =>
          n.id === action.id ? { ...n, read: true } : n
        ),
      };

    case 'MARK_ALL_READ':
      return {
        ...state,
        notifications: state.notifications.map(n => ({ ...n, read: true })),
      };

    case 'DISMISS':
      return {
        ...state,
        notifications: state.notifications.map(n =>
          n.id === action.id ? { ...n, dismissed: true } : n
        ),
      };

    case 'DISMISS_ALL':
      return {
        ...state,
        notifications: state.notifications.map(n => ({ ...n, dismissed: true })),
      };

    case 'REMOVE':
      return {
        ...state,
        notifications: state.notifications.filter(n => n.id !== action.id),
      };

    case 'CLEAR_OLD': {
      const cutoff = Date.now() - action.maxAge;
      return {
        ...state,
        notifications: state.notifications.filter(n => n.timestamp > cutoff),
      };
    }

    default:
      return state;
  }
}

// Context value
interface SystemNotificationsContextValue {
  notifications: SystemNotification[];
  unreadCount: number;
  activeCount: number;  // Not dismissed

  // Actions
  notify: (input: CreateNotificationInput) => string;
  markRead: (id: string) => void;
  markAllRead: () => void;
  dismiss: (id: string) => void;
  dismissAll: () => void;
  remove: (id: string) => void;

  // Queries
  getByCategory: (category: NotificationCategory) => SystemNotification[];
  getBySeverity: (severity: NotificationSeverity) => SystemNotification[];
  getActive: () => SystemNotification[];
}

const SystemNotificationsContext = createContext<SystemNotificationsContextValue | null>(null);

// Generate unique ID
let notificationCounter = 0;
function generateId(): string {
  return `sn-${Date.now()}-${++notificationCounter}`;
}

export function SystemNotificationsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(notificationsReducer, initialState);

  // Auto-expire notifications
  useEffect(() => {
    const expirableNotifications = state.notifications.filter(
      n => n.autoExpire && n.autoExpire > 0 && !n.dismissed
    );

    if (expirableNotifications.length === 0) return;

    const timers = expirableNotifications.map(n => {
      const elapsed = Date.now() - n.timestamp;
      const remaining = (n.autoExpire || 0) - elapsed;

      if (remaining <= 0) {
        dispatch({ type: 'DISMISS', id: n.id });
        return null;
      }

      return setTimeout(() => {
        dispatch({ type: 'DISMISS', id: n.id });
      }, remaining);
    }).filter(Boolean) as ReturnType<typeof setTimeout>[];

    return () => timers.forEach(t => clearTimeout(t));
  }, [state.notifications]);

  // Clear old notifications periodically (keep last 24 hours)
  useEffect(() => {
    const interval = setInterval(() => {
      dispatch({ type: 'CLEAR_OLD', maxAge: 24 * 60 * 60 * 1000 });
    }, 60 * 60 * 1000); // Check every hour

    return () => clearInterval(interval);
  }, []);

  const notify = useCallback((input: CreateNotificationInput): string => {
    const id = generateId();
    const notification: SystemNotification = {
      ...input,
      id,
      timestamp: Date.now(),
      read: false,
      dismissed: false,
    };
    dispatch({ type: 'ADD', notification });
    return id;
  }, []);

  const markRead = useCallback((id: string) => {
    dispatch({ type: 'MARK_READ', id });
  }, []);

  const markAllRead = useCallback(() => {
    dispatch({ type: 'MARK_ALL_READ' });
  }, []);

  const dismiss = useCallback((id: string) => {
    dispatch({ type: 'DISMISS', id });
  }, []);

  const dismissAll = useCallback(() => {
    dispatch({ type: 'DISMISS_ALL' });
  }, []);

  const remove = useCallback((id: string) => {
    dispatch({ type: 'REMOVE', id });
  }, []);

  const getByCategory = useCallback(
    (category: NotificationCategory) =>
      state.notifications.filter(n => n.category === category && !n.dismissed),
    [state.notifications]
  );

  const getBySeverity = useCallback(
    (severity: NotificationSeverity) =>
      state.notifications.filter(n => n.severity === severity && !n.dismissed),
    [state.notifications]
  );

  const getActive = useCallback(
    () => state.notifications.filter(n => !n.dismissed),
    [state.notifications]
  );

  const unreadCount = state.notifications.filter(n => !n.read && !n.dismissed).length;
  const activeCount = state.notifications.filter(n => !n.dismissed).length;

  const value: SystemNotificationsContextValue = {
    notifications: state.notifications,
    unreadCount,
    activeCount,
    notify,
    markRead,
    markAllRead,
    dismiss,
    dismissAll,
    remove,
    getByCategory,
    getBySeverity,
    getActive,
  };

  return (
    <SystemNotificationsContext.Provider value={value}>
      {children}
    </SystemNotificationsContext.Provider>
  );
}

export function useSystemNotifications(): SystemNotificationsContextValue {
  const context = useContext(SystemNotificationsContext);
  if (!context) {
    throw new Error('useSystemNotifications must be used within a SystemNotificationsProvider');
  }
  return context;
}

// Convenience hook for adding notifications
export function useNotify() {
  const { notify } = useSystemNotifications();
  return notify;
}
