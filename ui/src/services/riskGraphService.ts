// services/riskGraphService.ts
// HTTP client for Risk Graph API

import type {
  RiskGraphStrategy,
  RiskGraphStrategyVersion,
  RiskGraphTemplate,
  CreateStrategyInput,
  UpdateStrategyInput,
  CreateTemplateInput,
  UpdateTemplateInput,
  UseTemplateInput,
  StrategiesListResponse,
  StrategyResponse,
  VersionsListResponse,
  TemplatesListResponse,
  TemplateResponse,
  ExportResponse,
  ShareCodeResponse,
  ApiResponse,
  RiskGraphSSEEvent,
} from '../types/riskGraph';

const API_BASE = '/api/risk-graph';

// Helper for API calls
async function apiCall<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const startTime = performance.now();
  console.log('[riskGraphService] Calling:', url);
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    signal: options.signal ?? AbortSignal.timeout(30_000),
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  console.log('[riskGraphService] Response from', url, 'status:', response.status, 'in', (performance.now() - startTime).toFixed(0), 'ms');
  const data = await response.json();

  if (!response.ok || !data.success) {
    console.error('[riskGraphService] Error from', url, ':', data.error || response.status);
    throw new Error(data.error || `API error: ${response.status}`);
  }

  return data;
}

// ==================== Strategies ====================

/**
 * Parse numeric fields that come as strings from MySQL DECIMAL
 */
function parseStrategy(data: RiskGraphStrategy): RiskGraphStrategy {
  return {
    ...data,
    strike: typeof data.strike === 'string' ? parseFloat(data.strike) : data.strike,
    debit: data.debit !== null && data.debit !== undefined
      ? (typeof data.debit === 'string' ? parseFloat(data.debit) : data.debit)
      : null,
    width: data.width !== null && data.width !== undefined
      ? (typeof data.width === 'string' ? parseInt(data.width as unknown as string, 10) : data.width)
      : null,
    dte: typeof data.dte === 'string' ? parseInt(data.dte, 10) : data.dte,
  };
}

export async function fetchStrategies(
  includeInactive = false
): Promise<RiskGraphStrategy[]> {
  const params = includeInactive ? '?include_inactive=true' : '';
  const response = await apiCall<StrategiesListResponse>(
    `${API_BASE}/strategies${params}`
  );
  return (response.data ?? []).map(parseStrategy);
}

export async function fetchStrategy(id: string): Promise<RiskGraphStrategy> {
  const response = await apiCall<StrategyResponse>(
    `${API_BASE}/strategies/${id}`
  );
  if (!response.data) throw new Error('Strategy not found');
  return parseStrategy(response.data);
}

export async function createStrategy(
  input: CreateStrategyInput
): Promise<RiskGraphStrategy> {
  const response = await apiCall<StrategyResponse>(
    `${API_BASE}/strategies`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    }
  );
  if (!response.data) throw new Error('Failed to create strategy');
  return parseStrategy(response.data);
}

export async function updateStrategy(
  id: string,
  input: UpdateStrategyInput
): Promise<RiskGraphStrategy> {
  const response = await apiCall<StrategyResponse>(
    `${API_BASE}/strategies/${id}`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    }
  );
  if (!response.data) throw new Error('Failed to update strategy');
  return parseStrategy(response.data);
}

export async function deleteStrategy(
  id: string,
  hard = false
): Promise<void> {
  const params = hard ? '?hard=true' : '';
  await apiCall<ApiResponse<void>>(
    `${API_BASE}/strategies/${id}${params}`,
    { method: 'DELETE' }
  );
}

export async function fetchStrategyVersions(
  id: string
): Promise<RiskGraphStrategyVersion[]> {
  const response = await apiCall<VersionsListResponse>(
    `${API_BASE}/strategies/${id}/versions`
  );
  return response.data ?? [];
}

// ==================== Bulk Operations ====================

export async function importStrategies(
  strategies: CreateStrategyInput[]
): Promise<RiskGraphStrategy[]> {
  const response = await apiCall<StrategiesListResponse>(
    `${API_BASE}/strategies/import`,
    {
      method: 'POST',
      body: JSON.stringify({ strategies }),
    }
  );
  return response.data ?? [];
}

export async function exportStrategies(): Promise<{
  strategies: RiskGraphStrategy[];
  exportedAt: string;
  count: number;
}> {
  const response = await apiCall<ExportResponse>(
    `${API_BASE}/strategies/export`
  );
  return response.data ?? { strategies: [], exportedAt: '', count: 0 };
}

export async function reorderStrategies(
  order: string[]
): Promise<void> {
  await apiCall<ApiResponse<void>>(
    `${API_BASE}/strategies/reorder`,
    {
      method: 'POST',
      body: JSON.stringify({ order }),
    }
  );
}

// ==================== Templates ====================

export async function fetchTemplates(
  includePublic = false
): Promise<RiskGraphTemplate[]> {
  const params = includePublic ? '?include_public=true' : '';
  const response = await apiCall<TemplatesListResponse>(
    `${API_BASE}/templates${params}`
  );
  return response.data ?? [];
}

export async function fetchTemplate(id: string): Promise<RiskGraphTemplate> {
  const response = await apiCall<TemplateResponse>(
    `${API_BASE}/templates/${id}`
  );
  if (!response.data) throw new Error('Template not found');
  return response.data;
}

export async function createTemplate(
  input: CreateTemplateInput
): Promise<RiskGraphTemplate> {
  const response = await apiCall<TemplateResponse>(
    `${API_BASE}/templates`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    }
  );
  if (!response.data) throw new Error('Failed to create template');
  return response.data;
}

export async function updateTemplate(
  id: string,
  input: UpdateTemplateInput
): Promise<RiskGraphTemplate> {
  const response = await apiCall<TemplateResponse>(
    `${API_BASE}/templates/${id}`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    }
  );
  if (!response.data) throw new Error('Failed to update template');
  return response.data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await apiCall<ApiResponse<void>>(
    `${API_BASE}/templates/${id}`,
    { method: 'DELETE' }
  );
}

export async function useTemplate(
  id: string,
  input: UseTemplateInput
): Promise<RiskGraphStrategy> {
  const response = await apiCall<StrategyResponse>(
    `${API_BASE}/templates/${id}/use`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    }
  );
  if (!response.data) throw new Error('Failed to use template');
  return response.data;
}

export async function shareTemplate(id: string): Promise<string> {
  const response = await apiCall<ShareCodeResponse>(
    `${API_BASE}/templates/${id}/share`,
    { method: 'POST' }
  );
  return response.data?.shareCode ?? '';
}

export async function fetchSharedTemplate(
  shareCode: string
): Promise<RiskGraphTemplate> {
  const response = await apiCall<TemplateResponse>(
    `${API_BASE}/templates/shared/${shareCode}`
  );
  if (!response.data) throw new Error('Template not found');
  return response.data;
}

// ==================== SSE Subscription ====================

export type RiskGraphEventHandler = (event: RiskGraphSSEEvent) => void;

export interface RiskGraphSSESubscription {
  close: () => void;
  reconnect: () => void;
}

export function subscribeToRiskGraphStream(
  onEvent: RiskGraphEventHandler,
  onConnect?: () => void,
  onDisconnect?: () => void
): RiskGraphSSESubscription {
  let eventSource: EventSource | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_DELAY = 30000;

  const connect = () => {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource('/sse/risk-graph', { withCredentials: true });

    eventSource.onopen = () => {
      reconnectAttempts = 0;
      onConnect?.();
    };

    eventSource.onerror = () => {
      onDisconnect?.();

      // Exponential backoff
      const baseDelay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
      const jitter = Math.random() * 1000;
      const delay = baseDelay + jitter;
      reconnectAttempts++;

      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      reconnectTimeout = setTimeout(connect, delay);
    };

    // Listen for specific event types
    eventSource.addEventListener('strategy_added', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ type: 'strategy_added', data, ts: new Date().toISOString() });
      } catch {}
    });

    eventSource.addEventListener('strategy_updated', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ type: 'strategy_updated', data, ts: new Date().toISOString() });
      } catch {}
    });

    eventSource.addEventListener('strategy_removed', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        onEvent({ type: 'strategy_removed', data, ts: new Date().toISOString() });
      } catch {}
    });
  };

  // Initial connection
  connect();

  return {
    close: () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (eventSource) eventSource.close();
      eventSource = null;
    },
    reconnect: () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      reconnectAttempts = 0;
      connect();
    },
  };
}
