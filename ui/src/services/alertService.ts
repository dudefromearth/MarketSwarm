/**
 * Alert Service - HTTP/API Client
 *
 * Provides HTTP methods for alert operations with the backend.
 * Used by AlertContext for persistence and AI evaluation requests.
 *
 * Backend: Copilot service at port 8095
 */

import type {
  Alert,
  CreateAlertInput,
  EditAlertInput,
  AIEvaluation,
  MarketContext,
} from '../types/alerts';

// API base URL - Copilot service
const API_BASE = 'http://localhost:8095';

// Response wrapper
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/**
 * Fetch all alerts from backend
 */
export async function fetchAlerts(): Promise<Alert[]> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<Alert[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch alerts');
  } catch (err) {
    console.error('fetchAlerts error:', err);
    throw err;
  }
}

/**
 * Create a new alert
 */
export async function createAlertApi(input: CreateAlertInput): Promise<Alert> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(input),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<Alert> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to create alert');
  } catch (err) {
    console.error('createAlertApi error:', err);
    throw err;
  }
}

/**
 * Update an existing alert
 */
export async function updateAlertApi(input: EditAlertInput): Promise<Alert> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts/${input.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(input),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<Alert> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to update alert');
  } catch (err) {
    console.error('updateAlertApi error:', err);
    throw err;
  }
}

/**
 * Delete an alert
 */
export async function deleteAlertApi(id: string): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<void> = await response.json();
    if (!result.success) {
      throw new Error(result.error || 'Failed to delete alert');
    }
  } catch (err) {
    console.error('deleteAlertApi error:', err);
    throw err;
  }
}

/**
 * Request AI evaluation for an alert
 */
export async function requestAIEvaluation(
  alertId: string,
  context: MarketContext
): Promise<AIEvaluation> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts/${alertId}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ context }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<AIEvaluation> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to get AI evaluation');
  } catch (err) {
    console.error('requestAIEvaluation error:', err);
    throw err;
  }
}

/**
 * Bulk import alerts
 */
export async function importAlertsApi(alerts: Alert[]): Promise<Alert[]> {
  try {
    const response = await fetch(`${API_BASE}/api/alerts/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ alerts }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<Alert[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to import alerts');
  } catch (err) {
    console.error('importAlertsApi error:', err);
    throw err;
  }
}

/**
 * Export alerts to file
 */
export function exportAlertsToFile(alerts: Alert[], filename = 'alerts.json'): void {
  const blob = new Blob([JSON.stringify(alerts, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Check if backend is available
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: 'GET',
      credentials: 'include',
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Subscribe to alert SSE stream
 * Returns cleanup function
 */
export function subscribeToAlertStream(handlers: {
  onTriggered?: (data: { alertId: string; triggeredAt: number; aiReasoning?: string; aiConfidence?: number }) => void;
  onUpdated?: (data: { alertId: string; updates: Partial<Alert> }) => void;
  onEvaluation?: (data: AIEvaluation) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}): () => void {
  const es = new EventSource('/sse/alerts');

  es.onopen = () => {
    handlers.onConnect?.();
  };

  es.onerror = () => {
    handlers.onDisconnect?.();
  };

  es.addEventListener('alert_triggered', (event: MessageEvent) => {
    try {
      handlers.onTriggered?.(JSON.parse(event.data));
    } catch (err) {
      console.error('Failed to parse alert_triggered:', err);
    }
  });

  es.addEventListener('alert_updated', (event: MessageEvent) => {
    try {
      handlers.onUpdated?.(JSON.parse(event.data));
    } catch (err) {
      console.error('Failed to parse alert_updated:', err);
    }
  });

  es.addEventListener('ai_evaluation', (event: MessageEvent) => {
    try {
      handlers.onEvaluation?.(JSON.parse(event.data));
    } catch (err) {
      console.error('Failed to parse ai_evaluation:', err);
    }
  });

  // Return cleanup function
  return () => {
    es.close();
  };
}
