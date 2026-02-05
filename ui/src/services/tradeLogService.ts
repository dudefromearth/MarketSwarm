// services/tradeLogService.ts
// HTTP client for TradeLog/Journal API with idempotency and versioning support

import type {
  Position,
  PositionSnapshot,
  PendingOrder,
  JournalEntry,
  CreatePositionInput,
  UpdatePositionInput,
  RecordFillInput,
  CreateOrderInput,
  CreateJournalEntryInput,
  PositionsListResponse,
  PositionResponse,
  PositionSnapshotResponse,
  OrderResponse,
  JournalEntriesResponse,
  JournalEntryResponse,
  TradeLogEvent,
  ApiResponse,
  LegacyTrade,
  LegacyOrder,
} from '../types/tradeLog';

const JOURNAL_API = '';

// =============================================================================
// Request Helpers
// =============================================================================

/**
 * Generate a unique idempotency key for mutations
 */
function generateIdempotencyKey(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * Create fetch options with proper headers
 */
function createFetchOptions(
  method: string = 'GET',
  body?: unknown,
  version?: number,
  idempotencyKey?: string
): RequestInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (version !== undefined) {
    headers['If-Match'] = String(version);
  }

  if (idempotencyKey) {
    headers['Idempotency-Key'] = idempotencyKey;
  }

  const options: RequestInit = {
    method,
    credentials: 'include',
    headers,
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  return options;
}

/**
 * Parse API response and handle errors
 */
async function parseResponse<T>(response: Response): Promise<T> {
  const data = await response.json();

  if (!response.ok) {
    // Handle version conflict
    if (response.status === 409) {
      const error = new Error(data.error || 'Version conflict') as Error & { conflict: true; currentVersion?: number };
      error.conflict = true;
      error.currentVersion = data.currentVersion;
      throw error;
    }
    throw new Error(data.error || `API error: ${response.status}`);
  }

  if (!data.success) {
    throw new Error(data.error || 'API returned success=false');
  }

  return data;
}

// =============================================================================
// Position Endpoints
// =============================================================================

/**
 * Fetch positions for the authenticated user
 */
export async function fetchPositions(
  status?: 'planned' | 'open' | 'closed'
): Promise<Position[]> {
  const params = status ? `?status=${status}` : '';
  const response = await fetch(
    `${JOURNAL_API}/api/positions${params}`,
    createFetchOptions()
  );
  const data = await parseResponse<PositionsListResponse>(response);
  return data.data ?? [];
}

/**
 * Get a single position by ID
 */
export async function fetchPosition(id: string): Promise<Position> {
  const response = await fetch(
    `${JOURNAL_API}/api/positions/${id}`,
    createFetchOptions()
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Position not found');
  return data.data;
}

/**
 * Get a complete position snapshot for RiskGraph integration
 */
export async function fetchPositionSnapshot(id: string): Promise<PositionSnapshot> {
  const response = await fetch(
    `${JOURNAL_API}/api/positions/${id}/snapshot`,
    createFetchOptions()
  );
  const data = await parseResponse<PositionSnapshotResponse>(response);
  if (!data.data) throw new Error('Position not found');
  return data.data;
}

/**
 * Create a new position (with idempotency)
 */
export async function createPosition(
  input: CreatePositionInput,
  idempotencyKey?: string
): Promise<Position> {
  const key = idempotencyKey || generateIdempotencyKey();
  const response = await fetch(
    `${JOURNAL_API}/api/positions`,
    createFetchOptions('POST', input, undefined, key)
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Failed to create position');
  return data.data;
}

/**
 * Update a position (requires version for optimistic locking)
 */
export async function updatePosition(
  id: string,
  updates: UpdatePositionInput,
  version: number
): Promise<Position> {
  const response = await fetch(
    `${JOURNAL_API}/api/positions/${id}`,
    createFetchOptions('PATCH', updates, version)
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Failed to update position');
  return data.data;
}

/**
 * Record a fill for a position leg (with idempotency)
 */
export async function recordFill(
  positionId: string,
  fill: RecordFillInput,
  idempotencyKey?: string
): Promise<Position> {
  const key = idempotencyKey || generateIdempotencyKey();
  const response = await fetch(
    `${JOURNAL_API}/api/positions/${positionId}/fills`,
    createFetchOptions('POST', fill, undefined, key)
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Failed to record fill');
  return data.data;
}

/**
 * Close a position (requires version)
 */
export async function closePosition(
  id: string,
  version: number
): Promise<Position> {
  const response = await fetch(
    `${JOURNAL_API}/api/positions/${id}/close`,
    createFetchOptions('POST', undefined, version)
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Failed to close position');
  return data.data;
}

// =============================================================================
// Order Endpoints
// =============================================================================

/**
 * Fetch active/pending orders
 */
export async function fetchPendingOrders(): Promise<PendingOrder[]> {
  const response = await fetch(
    `${JOURNAL_API}/api/orders/active`,
    createFetchOptions()
  );
  const data = await parseResponse<{
    success: boolean;
    data: {
      pending_entries: PendingOrder[];
      pending_exits: PendingOrder[];
      total: number;
    };
  }>(response);
  return [
    ...(data.data?.pending_entries || []),
    ...(data.data?.pending_exits || []),
  ];
}

/**
 * Create a new order (with idempotency)
 */
export async function createOrder(
  input: CreateOrderInput,
  idempotencyKey?: string
): Promise<PendingOrder> {
  const key = idempotencyKey || generateIdempotencyKey();
  const response = await fetch(
    `${JOURNAL_API}/api/orders`,
    createFetchOptions('POST', {
      order_type: input.orderType,
      symbol: input.symbol,
      direction: input.direction,
      limit_price: input.limitPrice,
      quantity: input.quantity ?? 1,
      trade_id: input.tradeId,
      strategy: input.strategy,
      stop_loss: input.stopLoss,
      take_profit: input.takeProfit,
      notes: input.notes,
      expires_at: input.expiresAt,
    }, undefined, key)
  );
  const data = await parseResponse<OrderResponse>(response);
  if (!data.data) throw new Error('Failed to create order');
  return data.data;
}

/**
 * Cancel an order
 */
export async function cancelOrder(id: number): Promise<void> {
  const response = await fetch(
    `${JOURNAL_API}/api/orders/${id}`,
    createFetchOptions('DELETE')
  );
  await parseResponse<ApiResponse<void>>(response);
}

/**
 * Execute an order (manual fill)
 */
export async function executeOrder(id: number): Promise<Position> {
  const response = await fetch(
    `${JOURNAL_API}/api/orders/${id}/execute`,
    createFetchOptions('POST')
  );
  const data = await parseResponse<PositionResponse>(response);
  if (!data.data) throw new Error('Failed to execute order');
  return data.data;
}

// =============================================================================
// Journal Endpoints
// =============================================================================

/**
 * Create a journal entry for a position
 */
export async function createJournalEntry(
  input: CreateJournalEntryInput
): Promise<JournalEntry> {
  const response = await fetch(
    `${JOURNAL_API}/api/journal_entries`,
    createFetchOptions('POST', {
      position_id: input.positionId,
      object_of_reflection: input.objectOfReflection,
      bias_flags: input.biasFlags,
      notes: input.notes,
      phase: input.phase,
    })
  );
  const data = await parseResponse<JournalEntryResponse>(response);
  if (!data.data) throw new Error('Failed to create journal entry');
  return data.data;
}

/**
 * Fetch journal entries for a position
 */
export async function fetchJournalEntries(
  positionId: string
): Promise<JournalEntry[]> {
  const response = await fetch(
    `${JOURNAL_API}/api/journal_entries?position_id=${positionId}`,
    createFetchOptions()
  );
  const data = await parseResponse<JournalEntriesResponse>(response);
  return data.data ?? [];
}

// =============================================================================
// Legacy API Compatibility (for migration)
// =============================================================================

/**
 * Fetch trades using legacy API (for components not yet migrated)
 */
export async function fetchLegacyTrades(
  status?: 'open' | 'closed'
): Promise<LegacyTrade[]> {
  const params = status ? `?status=${status}` : '';
  const response = await fetch(
    `${JOURNAL_API}/api/trades${params}`,
    createFetchOptions()
  );
  const data = await parseResponse<{ success: boolean; data: LegacyTrade[] }>(response);
  return data.data ?? [];
}

/**
 * Fetch legacy orders (for MonitorPanel)
 */
export async function fetchLegacyOrders(): Promise<LegacyOrder[]> {
  const response = await fetch(
    `${JOURNAL_API}/api/orders/active`,
    createFetchOptions()
  );
  const data = await parseResponse<{
    success: boolean;
    data: {
      pending_entries: LegacyOrder[];
      pending_exits: LegacyOrder[];
    };
  }>(response);
  return [
    ...(data.data?.pending_entries || []),
    ...(data.data?.pending_exits || []),
  ];
}

/**
 * Close a trade using legacy API
 */
export async function closeLegacyTrade(
  tradeId: string,
  exitPrice: number,
  exitSpot?: number
): Promise<LegacyTrade> {
  const response = await fetch(
    `${JOURNAL_API}/api/trades/${tradeId}/close`,
    createFetchOptions('POST', {
      exit_price: exitPrice,
      exit_spot: exitSpot,
    })
  );
  const data = await parseResponse<{ success: boolean; data: LegacyTrade }>(response);
  if (!data.data) throw new Error('Failed to close trade');
  return data.data;
}

/**
 * Cancel a legacy order
 */
export async function cancelLegacyOrder(orderId: number): Promise<void> {
  const response = await fetch(
    `${JOURNAL_API}/api/orders/${orderId}`,
    createFetchOptions('DELETE')
  );
  await parseResponse<ApiResponse<void>>(response);
}

// =============================================================================
// SSE Subscription
// =============================================================================

export type TradeLogEventHandler = (event: TradeLogEvent) => void;

export interface TradeLogSSESubscription {
  close: () => void;
  reconnect: () => void;
}

/**
 * Subscribe to the trade-log SSE stream for real-time updates
 */
export function subscribeToTradeLogStream(
  onEvent: TradeLogEventHandler,
  onConnect?: () => void,
  onDisconnect?: () => void,
  lastSeq?: number
): TradeLogSSESubscription {
  let eventSource: EventSource | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_DELAY = 30000;

  const connect = () => {
    if (eventSource) {
      eventSource.close();
    }

    // Include last_seq for reconnection to avoid gaps
    const params = lastSeq ? `?last_seq=${lastSeq}` : '';
    eventSource = new EventSource(`/sse/trade-log${params}`, {
      withCredentials: true,
    });

    eventSource.onopen = () => {
      reconnectAttempts = 0;
      onConnect?.();
    };

    eventSource.onerror = () => {
      onDisconnect?.();

      // Exponential backoff with jitter
      const baseDelay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
      const jitter = Math.random() * 1000;
      const delay = baseDelay + jitter;
      reconnectAttempts++;

      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      reconnectTimeout = setTimeout(connect, delay);
    };

    // Listen for all trade-log events
    const eventTypes: string[] = [
      'PositionCreated',
      'FillRecorded',
      'PositionAdjusted',
      'PositionClosed',
      'OrderCreated',
      'OrderCancelled',
      'OrderFilled',
    ];

    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data);
          onEvent({
            eventId: payload.event_id,
            eventSeq: payload.event_seq,
            type: eventType as TradeLogEvent['type'],
            aggregateType: payload.aggregate_type,
            aggregateId: payload.aggregate_id,
            aggregateVersion: payload.aggregate_version,
            occurredAt: payload.occurred_at,
            payload: payload.payload,
          });
        } catch {
          // Malformed event, skip
        }
      });
    }

    // Also handle generic message event for backwards compatibility
    eventSource.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.type && payload.event_id) {
          onEvent({
            eventId: payload.event_id,
            eventSeq: payload.event_seq,
            type: payload.type,
            aggregateType: payload.aggregate_type,
            aggregateId: payload.aggregate_id,
            aggregateVersion: payload.aggregate_version,
            occurredAt: payload.occurred_at,
            payload: payload.payload,
          });
        }
      } catch {
        // Not a valid event
      }
    };
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
