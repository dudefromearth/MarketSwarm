/**
 * Alert Service - HTTP/API Client
 *
 * Provides HTTP methods for alert operations with the backend.
 * Used by AlertContext for persistence and AI evaluation requests.
 *
 * Backend: Journal service at port 3002 (alerts are now server-side persisted)
 * AI evaluations still go to Copilot service at port 8095
 */

import type {
  Alert,
  CreateAlertInput,
  EditAlertInput,
  AIEvaluation,
  MarketContext,
} from '../types/alerts';

// API base URLs
const JOURNAL_API_BASE = 'http://localhost:3002';  // Alert CRUD
const COPILOT_API_BASE = 'http://localhost:8095';  // AI evaluations

/**
 * Parse numeric fields from API response (database returns strings for DECIMAL)
 */
function parseAlertNumericFields(alert: Alert): Alert {
  return {
    ...alert,
    targetValue: alert.targetValue != null ? Number(alert.targetValue) : undefined,
    entryDebit: alert.entryDebit != null ? Number(alert.entryDebit) : undefined,
    minProfitThreshold: alert.minProfitThreshold != null ? Number(alert.minProfitThreshold) : undefined,
    zoneLow: alert.zoneLow != null ? Number(alert.zoneLow) : undefined,
    zoneHigh: alert.zoneHigh != null ? Number(alert.zoneHigh) : undefined,
    aiConfidence: alert.aiConfidence != null ? Number(alert.aiConfidence) : undefined,
    highWaterMark: alert.highWaterMark != null ? Number(alert.highWaterMark) : undefined,
  };
}

// Response wrapper
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/**
 * Fetch all alerts from backend (Journal service)
 */
export async function fetchAlerts(): Promise<Alert[]> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<Alert[]> = await response.json();
    if (result.success && result.data) {
      return result.data.map(parseAlertNumericFields);
    }
    throw new Error(result.error || 'Failed to fetch alerts');
  } catch (err) {
    console.error('fetchAlerts error:', err);
    throw err;
  }
}

/**
 * Create a new alert (Journal service)
 */
export async function createAlertApi(input: CreateAlertInput): Promise<Alert> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts`, {
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
      return parseAlertNumericFields(result.data);
    }
    throw new Error(result.error || 'Failed to create alert');
  } catch (err) {
    console.error('createAlertApi error:', err);
    throw err;
  }
}

/**
 * Update an existing alert (Journal service)
 */
export async function updateAlertApi(input: EditAlertInput): Promise<Alert> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${input.id}`, {
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
      return parseAlertNumericFields(result.data);
    }
    throw new Error(result.error || 'Failed to update alert');
  } catch (err) {
    console.error('updateAlertApi error:', err);
    throw err;
  }
}

/**
 * Delete an alert (Journal service)
 */
export async function deleteAlertApi(id: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}`, {
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
 * Request AI evaluation for an alert (Copilot service)
 */
export async function requestAIEvaluation(
  alertId: string,
  context: MarketContext
): Promise<AIEvaluation> {
  try {
    const response = await fetch(`${COPILOT_API_BASE}/api/alerts/${alertId}/evaluate`, {
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
 * Bulk import alerts (Journal service)
 */
export async function importAlertsApi(alerts: Alert[]): Promise<Alert[]> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/import`, {
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
      return result.data.map(parseAlertNumericFields);
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
 * Check if Journal service is available
 */
export async function checkJournalHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/health`, {
      method: 'GET',
      credentials: 'include',
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Check if Copilot service is available (for AI evaluations)
 */
export async function checkCopilotHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${COPILOT_API_BASE}/health`, {
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
