// types/tradeLog.ts
// TypeScript types for TradeLog/Journal Service Layer
// Based on the normalized domain model from the implementation plan

// =============================================================================
// Core Domain Types (Normalized)
// =============================================================================

export type PositionStatus = 'planned' | 'open' | 'closed';
export type InstrumentType = 'option' | 'stock' | 'future';
export type OptionRight = 'call' | 'put';
export type JournalPhase = 'setup' | 'entry' | 'management' | 'exit' | 'review';
export type OrderStatus = 'pending' | 'filled' | 'cancelled' | 'expired';
export type OrderType = 'limit' | 'market';
export type DerivedStrategy = 'single' | 'vertical' | 'butterfly' | 'custom';

/**
 * Position - Core aggregate for tracking trades
 * This is the normalized domain model replacing the flattened TradeLog
 */
export interface Position {
  id: string;
  userId: number;
  status: PositionStatus;
  symbol: string;
  underlying: string;
  version: number;
  openedAt: string | null;
  closedAt: string | null;
  tags: string[] | null;
  campaignId: string | null;
  createdAt: string;
  updatedAt: string;
  // Denormalized for convenience
  legs?: Leg[];
  fills?: Fill[];
}

/**
 * Leg - Individual option/stock/future leg of a position
 */
export interface Leg {
  id: string;
  positionId: string;
  instrumentType: InstrumentType;
  expiry: string | null;
  strike: number | null;
  right: OptionRight | null;
  quantity: number; // positive = long, negative = short
  createdAt: string;
}

/**
 * Fill - Price/quantity execution record
 */
export interface Fill {
  id: string;
  legId: string;
  price: number;
  quantity: number;
  occurredAt: string; // market reality
  recordedAt: string; // system reality
}

/**
 * JournalEntry - Reflection object attached to a position
 * Follows structured journaling with phases
 */
export interface JournalEntry {
  id: string;
  positionId: string;
  objectOfReflection: string; // required
  biasFlags: string[] | null;
  notes: string | null;
  phase: JournalPhase;
  createdAt: string;
}

/**
 * PendingOrder - Order waiting to be filled
 */
export interface PendingOrder {
  id: number;
  userId: number;
  orderType: 'entry' | 'exit';
  symbol: string;
  direction: 'long' | 'short';
  limitPrice: number;
  quantity: number;
  tradeId: string | null;
  strategy: string | null;
  stopLoss: number | null;
  takeProfit: number | null;
  notes: string | null;
  status: OrderStatus;
  createdAt: string;
  expiresAt: string | null;
  filledAt: string | null;
  filledPrice: number | null;
}

// =============================================================================
// Derived/Computed Types
// =============================================================================

/**
 * PositionMetadata - Computed from position structure, not stored
 */
export interface PositionMetadata {
  derivedStrategy: DerivedStrategy;
  netDebit: number;
  dte: number;
  maxProfit: number | null;
  maxLoss: number | null;
}

/**
 * PositionSnapshot - Complete position state for RiskGraph integration
 * Returned by GET /api/positions/{id}/snapshot
 */
export interface PositionSnapshot {
  positionId: string;
  version: number;
  status: PositionStatus;
  symbol: string;
  underlying: string;
  legs: Leg[];
  fills: Fill[];
  metadata: PositionMetadata;
}

// =============================================================================
// Input Types for API Operations
// =============================================================================

export interface CreatePositionInput {
  symbol: string;
  underlying: string;
  status?: PositionStatus;
  tags?: string[];
  campaignId?: string;
  legs: CreateLegInput[];
}

export interface CreateLegInput {
  instrumentType: InstrumentType;
  expiry?: string;
  strike?: number;
  right?: OptionRight;
  quantity: number;
}

export interface UpdatePositionInput {
  status?: PositionStatus;
  tags?: string[];
  campaignId?: string;
}

export interface RecordFillInput {
  legId: string;
  price: number;
  quantity: number;
  occurredAt: string;
}

export interface CreateOrderInput {
  orderType: 'entry' | 'exit';
  symbol: string;
  direction: 'long' | 'short';
  limitPrice: number;
  quantity?: number;
  tradeId?: string;
  strategy?: string;
  stopLoss?: number;
  takeProfit?: number;
  notes?: string;
  expiresAt?: string;
}

export interface CreateJournalEntryInput {
  positionId: string;
  objectOfReflection: string;
  biasFlags?: string[];
  notes?: string;
  phase: JournalPhase;
}

// =============================================================================
// SSE Event Types (Deterministic Envelope)
// =============================================================================

export type TradeLogEventType =
  | 'PositionCreated'
  | 'FillRecorded'
  | 'PositionAdjusted'
  | 'PositionClosed'
  | 'OrderCreated'
  | 'OrderCancelled'
  | 'OrderFilled';

export type AggregateType = 'position' | 'order';

/**
 * TradeLogEvent - SSE event envelope for deterministic sync
 * Supports deduplication, ordering, and replay
 */
export interface TradeLogEvent {
  eventId: string;
  eventSeq: number;
  type: TradeLogEventType;
  aggregateType: AggregateType;
  aggregateId: string;
  aggregateVersion: number;
  occurredAt: string;
  payload: unknown;
}

// =============================================================================
// API Response Types
// =============================================================================

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  count?: number;
}

export interface PositionsListResponse extends ApiResponse<Position[]> {
  count: number;
}

export interface PositionResponse extends ApiResponse<Position> {}

export interface PositionSnapshotResponse extends ApiResponse<PositionSnapshot> {}

export interface OrdersListResponse extends ApiResponse<PendingOrder[]> {
  count: number;
}

export interface OrderResponse extends ApiResponse<PendingOrder> {}

export interface JournalEntriesResponse extends ApiResponse<JournalEntry[]> {
  count: number;
}

export interface JournalEntryResponse extends ApiResponse<JournalEntry> {}

// =============================================================================
// Legacy Type Compatibility
// =============================================================================

/**
 * LegacyTrade - Matches existing Trade interface in components
 * Used during migration to maintain backward compatibility
 */
export interface LegacyTrade {
  id: string;
  log_id: string;
  symbol: string;
  underlying: string;
  strategy: string;
  side: 'call' | 'put';
  strike: number;
  width: number | null;
  dte: number | null;
  quantity: number;
  entry_time: string;
  entry_price: number; // cents
  entry_spot: number | null;
  entry_iv: number | null;
  exit_time: string | null;
  exit_price: number | null;
  exit_spot: number | null;
  planned_risk: number | null;
  max_profit: number | null;
  max_loss: number | null;
  pnl: number | null;
  r_multiple: number | null;
  status: 'open' | 'closed';
  entry_mode: 'instant' | 'freeform' | 'simulated';
  immutable_at: string | null;
  notes: string | null;
  tags: string[];
  source: string;
  playbook_id: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * LegacyOrder - Matches existing Order interface in MonitorPanel
 */
export interface LegacyOrder {
  id: number;
  order_type: 'entry' | 'exit';
  symbol: string;
  direction: 'long' | 'short';
  limit_price: number;
  quantity: number;
  strategy?: string;
  trade_id?: string;
  status: 'pending' | 'filled' | 'cancelled' | 'expired';
  created_at: string;
  expires_at: string | null;
  filled_at: string | null;
  filled_price: number | null;
  notes?: string;
}

// =============================================================================
// Conversion Utilities
// =============================================================================

/**
 * Convert server Position to legacy Trade format
 * Used during migration for components that haven't been updated
 */
export function toLegacyTrade(position: Position, snapshot: PositionSnapshot): LegacyTrade {
  const { metadata, legs, fills } = snapshot;
  const firstLeg = legs[0];
  const entryFill = fills.find(f => f.legId === firstLeg?.id);

  return {
    id: position.id,
    log_id: '', // No longer used in normalized model
    symbol: position.symbol,
    underlying: position.underlying,
    strategy: metadata.derivedStrategy,
    side: firstLeg?.right || 'call',
    strike: firstLeg?.strike || 0,
    width: legs.length > 1 ? Math.abs((legs[1]?.strike || 0) - (firstLeg?.strike || 0)) : null,
    dte: metadata.dte,
    quantity: firstLeg?.quantity || 0,
    entry_time: position.openedAt || position.createdAt,
    entry_price: entryFill?.price ? entryFill.price * 100 : 0, // convert to cents
    entry_spot: null,
    entry_iv: null,
    exit_time: position.closedAt,
    exit_price: null, // Would need exit fill
    exit_spot: null,
    planned_risk: metadata.maxLoss ? metadata.maxLoss * 100 : null,
    max_profit: metadata.maxProfit ? metadata.maxProfit * 100 : null,
    max_loss: metadata.maxLoss ? metadata.maxLoss * 100 : null,
    pnl: null, // Computed on close
    r_multiple: null,
    status: position.status === 'closed' ? 'closed' : 'open',
    entry_mode: 'instant',
    immutable_at: null,
    notes: null,
    tags: position.tags || [],
    source: 'manual',
    playbook_id: null,
    created_at: position.createdAt,
    updated_at: position.updatedAt,
  };
}

/**
 * Convert PendingOrder to legacy Order format
 */
export function toLegacyOrder(order: PendingOrder): LegacyOrder {
  return {
    id: order.id,
    order_type: order.orderType,
    symbol: order.symbol,
    direction: order.direction,
    limit_price: order.limitPrice,
    quantity: order.quantity,
    strategy: order.strategy || undefined,
    trade_id: order.tradeId || undefined,
    status: order.status,
    created_at: order.createdAt,
    expires_at: order.expiresAt,
    filled_at: order.filledAt,
    filled_price: order.filledPrice,
    notes: order.notes || undefined,
  };
}
