/**
 * API Client Types
 *
 * Request/response types for the Market Swarm API.
 */

import type { Position, PositionLeg, PositionType, PositionDirection, CostBasisType } from '@market-swarm/core';

// ============================================================
// API Response Types
// ============================================================

/** Standard API response wrapper */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  count?: number;
}

// ============================================================
// Position Types
// ============================================================

/** Input for creating a position */
export interface CreatePositionInput {
  symbol?: string;
  positionType: PositionType;
  direction: PositionDirection;
  legs: PositionLeg[];
  costBasis?: number | null;
  costBasisType?: CostBasisType;
  visible?: boolean;
  label?: string | null;
  color?: string | null;
}

/** Input for updating a position */
export interface UpdatePositionInput {
  symbol?: string;
  positionType?: PositionType;
  direction?: PositionDirection;
  legs?: PositionLeg[];
  costBasis?: number | null;
  costBasisType?: CostBasisType;
  visible?: boolean;
  label?: string | null;
  color?: string | null;
  sortOrder?: number;
}

/** Position list response */
export interface PositionsListResponse extends ApiResponse<Position[]> {
  count: number;
}

/** Single position response */
export interface PositionResponse extends ApiResponse<Position> {}

// ============================================================
// Legacy Strategy Types (for backward compatibility)
// ============================================================

export type StrategyType = 'single' | 'vertical' | 'butterfly';
export type Side = 'call' | 'put';

/** Legacy strategy from API */
export interface Strategy {
  id: string;
  userId: number;
  symbol: string;
  underlying: string;
  strategy: StrategyType;
  side: Side;
  strike: number;
  width: number | null;
  dte: number;
  expiration: string;
  debit: number | null;
  visible: boolean;
  sortOrder: number;
  color: string | null;
  label: string | null;
  addedAt: number;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

/** Input for creating a legacy strategy */
export interface CreateStrategyInput {
  symbol?: string;
  underlying?: string;
  strategy: StrategyType;
  side: Side;
  strike: number;
  width?: number | null;
  dte: number;
  expiration: string;
  debit?: number | null;
  visible?: boolean;
  sortOrder?: number;
  color?: string | null;
  label?: string | null;
}

/** Input for updating a legacy strategy */
export interface UpdateStrategyInput {
  debit?: number | null;
  visible?: boolean;
  sortOrder?: number;
  color?: string | null;
  label?: string | null;
}

/** Strategy list response */
export interface StrategiesListResponse extends ApiResponse<Strategy[]> {
  count: number;
}

/** Single strategy response */
export interface StrategyResponse extends ApiResponse<Strategy> {}

// ============================================================
// Template Types
// ============================================================

/** Strategy template */
export interface Template {
  id: string;
  userId: number;
  name: string;
  description: string | null;
  symbol: string;
  strategy: StrategyType;
  side: Side;
  strikeOffset: number;
  width: number | null;
  dteTarget: number;
  debitEstimate: number | null;
  isPublic: boolean;
  shareCode: string | null;
  useCount: number;
  createdAt: string;
}

/** Input for creating a template */
export interface CreateTemplateInput {
  name: string;
  description?: string | null;
  symbol?: string;
  strategy: StrategyType;
  side: Side;
  strikeOffset?: number;
  width?: number | null;
  dteTarget: number;
  debitEstimate?: number | null;
  isPublic?: boolean;
}

/** Template list response */
export interface TemplatesListResponse extends ApiResponse<Template[]> {
  count: number;
}

// ============================================================
// Auth Types
// ============================================================

/** User info */
export interface User {
  id: number;
  email: string;
  name?: string;
  createdAt: string;
}

/** Auth response */
export interface AuthResponse extends ApiResponse<{
  user: User;
  token: string;
}> {}

/** Login input */
export interface LoginInput {
  email: string;
  password: string;
}

/** Register input */
export interface RegisterInput {
  email: string;
  password: string;
  name?: string;
}

// ============================================================
// SSE Event Types
// ============================================================

export type SSEEventType =
  | 'strategy_added'
  | 'strategy_updated'
  | 'strategy_removed'
  | 'position_added'
  | 'position_updated'
  | 'position_removed';

export interface SSEEvent {
  type: SSEEventType;
  data: unknown;
  ts: string;
}

// ============================================================
// Client Options
// ============================================================

export interface ClientOptions {
  /** Base URL for API */
  baseUrl: string;

  /** Enable offline support */
  offlineEnabled?: boolean;

  /** Auth token */
  token?: string;

  /** Token refresh handler */
  onTokenRefresh?: (token: string) => void;

  /** Auth error handler */
  onAuthError?: () => void;
}
