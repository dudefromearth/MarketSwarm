/**
 * alertSSEManager — Singleton shared EventSource for /sse/alerts.
 *
 * AlertContext and AlgoAlertContext both subscribe to /sse/alerts but listen
 * for completely different event types. This module opens a single connection
 * and fans out events to all subscribers, reducing the SSE connection count.
 *
 * Usage:
 *   const unsub = subscribeAlertSSE(
 *     { alert_triggered: handler, alert_updated: handler2 },
 *     () => setConnected(true),
 *     () => setConnected(false),
 *   );
 *   // later:
 *   unsub();
 */

type EventHandler = (event: MessageEvent) => void;

interface Subscriber {
  events: Record<string, EventHandler>;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

let eventSource: EventSource | null = null;
let subscribers: Subscriber[] = [];
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;

const MAX_RECONNECT_DELAY = 30_000;
const BASE_DELAY = 2_000;

function connect() {
  if (eventSource) {
    eventSource.close();
  }

  const es = new EventSource('/sse/alerts', { withCredentials: true });

  es.onopen = () => {
    reconnectAttempts = 0;
    subscribers.forEach((s) => s.onConnect?.());
  };

  es.onerror = () => {
    es.close();
    eventSource = null;
    subscribers.forEach((s) => s.onDisconnect?.());
    scheduleReconnect();
  };

  eventSource = es;

  // Attach all current subscribers' event listeners
  attachListeners(es);
}

function attachListeners(es: EventSource) {
  // Collect all unique event types across subscribers
  const eventTypes = new Set<string>();
  subscribers.forEach((s) => {
    Object.keys(s.events).forEach((t) => eventTypes.add(t));
  });

  eventTypes.forEach((eventType) => {
    es.addEventListener(eventType, (e: MessageEvent) => {
      subscribers.forEach((s) => {
        s.events[eventType]?.(e);
      });
    });
  });
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (subscribers.length === 0) return;

  const delay = Math.min(
    BASE_DELAY * Math.pow(2, reconnectAttempts) + Math.random() * 1000,
    MAX_RECONNECT_DELAY,
  );
  reconnectAttempts++;

  reconnectTimer = setTimeout(connect, delay);
}

/**
 * Subscribe to /sse/alerts events. Opens the connection on first subscriber,
 * closes on last unsubscribe.
 *
 * @param events  Map of SSE event type → handler (e.g. { alert_triggered: fn })
 * @param onConnect   Called when the EventSource opens
 * @param onDisconnect Called when the EventSource errors / closes
 * @returns unsubscribe function
 */
export function subscribeAlertSSE(
  events: Record<string, EventHandler>,
  onConnect?: () => void,
  onDisconnect?: () => void,
): () => void {
  const subscriber: Subscriber = { events, onConnect, onDisconnect };
  subscribers.push(subscriber);

  // First subscriber opens the connection
  if (subscribers.length === 1) {
    connect();
  } else if (eventSource?.readyState === EventSource.OPEN) {
    // Connection already open — notify immediately and attach new event types
    onConnect?.();

    // Attach any new event types this subscriber needs
    const existingTypes = new Set<string>();
    subscribers.forEach((s) => {
      if (s !== subscriber) {
        Object.keys(s.events).forEach((t) => existingTypes.add(t));
      }
    });

    Object.keys(events).forEach((eventType) => {
      if (!existingTypes.has(eventType) && eventSource) {
        eventSource.addEventListener(eventType, (e: MessageEvent) => {
          subscribers.forEach((s) => {
            s.events[eventType]?.(e);
          });
        });
      }
    });
  }

  // Return unsubscribe function
  return () => {
    subscribers = subscribers.filter((s) => s !== subscriber);

    // Last subscriber — close connection
    if (subscribers.length === 0) {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      reconnectAttempts = 0;
    }
  };
}
