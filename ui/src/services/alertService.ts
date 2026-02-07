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
const JOURNAL_API_BASE = '';  // Alert CRUD
const COPILOT_API_BASE = '';  // AI evaluations

/**
 * Parse numeric fields from API response (database returns strings for DECIMAL)
 * Uses 'any' assertion because Alert is a discriminated union and not all types have all fields
 */
function parseAlertNumericFields(alert: Alert): Alert {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const a = alert as any;
  const result = { ...a };

  // Convert numeric fields if they exist
  if (a.targetValue != null) result.targetValue = Number(a.targetValue);
  if (a.entryDebit != null) result.entryDebit = Number(a.entryDebit);
  if (a.minProfitThreshold != null) result.minProfitThreshold = Number(a.minProfitThreshold);
  if (a.zoneLow != null) result.zoneLow = Number(a.zoneLow);
  if (a.zoneHigh != null) result.zoneHigh = Number(a.zoneHigh);
  if (a.aiConfidence != null) result.aiConfidence = Number(a.aiConfidence);
  if (a.highWaterMark != null) result.highWaterMark = Number(a.highWaterMark);

  return result as Alert;
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

// ==================== Alert Definition API (v2) ====================

import type {
  AlertDefinition,
  AlertEvent,
  AlertOverride,
  CreateAlertDefinitionInput,
  UpdateAlertDefinitionInput,
} from '../types/alerts';

/**
 * Fetch all alert definitions for current user
 */
export async function fetchAlertDefinitions(): Promise<AlertDefinition[]> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<AlertDefinition[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch alert definitions');
  } catch (err) {
    console.error('fetchAlertDefinitions error:', err);
    throw err;
  }
}

/**
 * Create a new alert definition (prompt-first)
 */
export async function createAlertDefinition(input: CreateAlertDefinitionInput): Promise<AlertDefinition> {
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

    const result: ApiResponse<AlertDefinition> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to create alert');
  } catch (err) {
    console.error('createAlertDefinition error:', err);
    throw err;
  }
}

/**
 * Update an alert definition
 */
export async function updateAlertDefinition(input: UpdateAlertDefinitionInput): Promise<AlertDefinition> {
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

    const result: ApiResponse<AlertDefinition> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to update alert');
  } catch (err) {
    console.error('updateAlertDefinition error:', err);
    throw err;
  }
}

/**
 * Pause an alert
 */
export async function pauseAlert(id: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/pause`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('pauseAlert error:', err);
    throw err;
  }
}

/**
 * Resume a paused alert
 */
export async function resumeAlert(id: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/resume`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('resumeAlert error:', err);
    throw err;
  }
}

/**
 * Acknowledge a triggered alert (for warn severity)
 */
export async function acknowledgeAlert(id: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/ack`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('acknowledgeAlert error:', err);
    throw err;
  }
}

/**
 * Dismiss an alert (for inform/notify severity)
 */
export async function dismissAlert(id: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/dismiss`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('dismissAlert error:', err);
    throw err;
  }
}

/**
 * Override a block alert (requires reason)
 */
export async function overrideAlert(id: string, reason: string): Promise<AlertOverride> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ reason }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<AlertOverride> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to override alert');
  } catch (err) {
    console.error('overrideAlert error:', err);
    throw err;
  }
}

/**
 * Get alert event history
 */
export async function getAlertHistory(id: string): Promise<AlertEvent[]> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${id}/history`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<AlertEvent[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch alert history');
  } catch (err) {
    console.error('getAlertHistory error:', err);
    throw err;
  }
}

// ==================== Vexy Meta-Alert API ====================

/**
 * Vexy alert digest response
 */
export interface VexyAlertDigest {
  narrative: string;
  topAttentionPoints?: string[];
  suggestedQuestion?: string;
  generatedAt: string;
}

/**
 * Get Vexy's alert digest (meta-synthesis of recent alerts)
 */
export async function getVexyAlertDigest(): Promise<VexyAlertDigest> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/vexy/alert-digest`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<VexyAlertDigest> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to get alert digest');
  } catch (err) {
    console.error('getVexyAlertDigest error:', err);
    throw err;
  }
}

/**
 * Get Vexy's routine briefing
 */
export async function getVexyRoutineBriefing(): Promise<VexyAlertDigest> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/vexy/routine-briefing`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<VexyAlertDigest> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to get routine briefing');
  } catch (err) {
    console.error('getVexyRoutineBriefing error:', err);
    throw err;
  }
}

// ==================== ML Findings API (Trade Tracking ML) ====================

import type { MLFinding, MLAlertDefinition, MLAlertCategory } from '../types/alerts';

// ML Feedback service base URL
const ML_FEEDBACK_API_BASE = '';  // ML findings

/**
 * Fetch active ML findings for current market conditions
 * These come from the ml_feedback service's analysis of historical trade outcomes
 */
export async function fetchMLFindings(): Promise<MLFinding[]> {
  try {
    const response = await fetch(`${ML_FEEDBACK_API_BASE}/api/ml/findings`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<MLFinding[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch ML findings');
  } catch (err) {
    console.error('fetchMLFindings error:', err);
    throw err;
  }
}

/**
 * Fetch ML findings filtered by category
 */
export async function fetchMLFindingsByCategory(category: MLAlertCategory): Promise<MLFinding[]> {
  try {
    const response = await fetch(`${ML_FEEDBACK_API_BASE}/api/ml/findings?category=${category}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<MLFinding[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch ML findings');
  } catch (err) {
    console.error('fetchMLFindingsByCategory error:', err);
    throw err;
  }
}

/**
 * Fetch ML alerts that have been generated from findings
 * These are alerts that have matched current trading context
 */
export async function fetchMLAlerts(): Promise<MLAlertDefinition[]> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts?category=ml`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result: ApiResponse<MLAlertDefinition[]> = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch ML alerts');
  } catch (err) {
    console.error('fetchMLAlerts error:', err);
    throw err;
  }
}

/**
 * Log an ML alert override (for learning loop)
 * Overrides are tracked and outcomes are fed back to the ML system
 */
export async function logMLAlertOverride(alertId: string, reason: string): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${alertId}/ml-override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ reason }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('logMLAlertOverride error:', err);
    throw err;
  }
}

/**
 * Report outcome of an ML alert override (for continuous learning)
 * Called after trade completion to feed back to ML system
 */
export async function reportMLOverrideOutcome(
  alertId: string,
  outcome: 'validated' | 'regretted'
): Promise<void> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/alerts/${alertId}/ml-override/outcome`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ outcome }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (err) {
    console.error('reportMLOverrideOutcome error:', err);
    throw err;
  }
}

/**
 * Get historical performance data for an ML finding
 * Shows win rate, avg return, sample size, outcome distribution
 */
export async function getMLFindingHistory(findingId: string): Promise<{
  winRate: number;
  avgReturn: number;
  sampleSize: number;
  outcomeDistribution: { profitable: number; breakeven: number; loss: number };
  lastOccurrence?: string;
}> {
  try {
    const response = await fetch(`${ML_FEEDBACK_API_BASE}/api/ml/findings/${findingId}/history`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to fetch finding history');
  } catch (err) {
    console.error('getMLFindingHistory error:', err);
    throw err;
  }
}

/**
 * Request Vexy interpretation of an ML finding
 * Vexy is the meaning layer that translates statistics into human insight
 */
export async function getVexyMLInterpretation(findingId: string): Promise<{
  narrative: string;
  confidence: number;
  suggestedAction?: string;
}> {
  try {
    const response = await fetch(`${JOURNAL_API_BASE}/api/vexy/ml-interpretation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ findingId }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const result = await response.json();
    if (result.success && result.data) {
      return result.data;
    }
    throw new Error(result.error || 'Failed to get Vexy interpretation');
  } catch (err) {
    console.error('getVexyMLInterpretation error:', err);
    throw err;
  }
}

// ==================== SSE Subscriptions ====================

/**
 * Subscribe to alert SSE stream (v2 with all event types)
 * Returns cleanup function
 */
export function subscribeToAlertStreamV2(handlers: {
  onCreated?: (data: AlertDefinition) => void;
  onUpdated?: (data: { alertId: string; updates: Partial<AlertDefinition> }) => void;
  onPaused?: (data: { alertId: string }) => void;
  onTriggered?: (data: { alertId: string; triggeredAt: string; severity: string; payload: Record<string, unknown> }) => void;
  onAcknowledged?: (data: { alertId: string }) => void;
  onDismissed?: (data: { alertId: string }) => void;
  onBlocked?: (data: { alertId: string; reason: string }) => void;
  onOverrideLogged?: (data: AlertOverride) => void;
  onDigest?: (data: VexyAlertDigest) => void;
  // ML-driven alert events
  onMLFinding?: (data: MLFinding) => void;
  onMLAlertCreated?: (data: MLAlertDefinition) => void;
  onMLOverrideOutcome?: (data: { alertId: string; outcome: 'validated' | 'regretted' }) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}): () => void {
  const es = new EventSource('/sse/alerts', { withCredentials: true });

  es.onopen = () => {
    handlers.onConnect?.();
  };

  es.onerror = () => {
    handlers.onDisconnect?.();
  };

  const eventHandlers: Record<string, (event: MessageEvent) => void> = {
    alert_created: (event) => {
      try { handlers.onCreated?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_updated: (event) => {
      try { handlers.onUpdated?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_paused: (event) => {
      try { handlers.onPaused?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_triggered: (event) => {
      try { handlers.onTriggered?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_acknowledged: (event) => {
      try { handlers.onAcknowledged?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_dismissed: (event) => {
      try { handlers.onDismissed?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_blocked: (event) => {
      try { handlers.onBlocked?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_override_logged: (event) => {
      try { handlers.onOverrideLogged?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    alert_digest: (event) => {
      try { handlers.onDigest?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    // ML-driven alert events
    ml_finding: (event) => {
      try { handlers.onMLFinding?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    ml_alert_created: (event) => {
      try { handlers.onMLAlertCreated?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
    ml_override_outcome: (event) => {
      try { handlers.onMLOverrideOutcome?.(JSON.parse(event.data)); } catch (e) { console.error('Parse error:', e); }
    },
  };

  // Register all event handlers
  for (const [eventType, handler] of Object.entries(eventHandlers)) {
    es.addEventListener(eventType, handler);
  }

  // Return cleanup function
  return () => {
    for (const [eventType, handler] of Object.entries(eventHandlers)) {
      es.removeEventListener(eventType, handler);
    }
    es.close();
  };
}

/**
 * Subscribe to alert SSE stream (legacy v1 - backward compat)
 * Returns cleanup function
 */
export function subscribeToAlertStream(handlers: {
  onTriggered?: (data: { alertId: string; triggeredAt: number; aiReasoning?: string; aiConfidence?: number }) => void;
  onUpdated?: (data: { alertId: string; updates: Partial<Alert> }) => void;
  onEvaluation?: (data: AIEvaluation) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}): () => void {
  const es = new EventSource('/sse/alerts', { withCredentials: true });

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
