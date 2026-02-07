// types/riskGraph.ts
// TypeScript types for Risk Graph Service
//
// Position types are imported from @market-swarm/core
// API-specific types remain here

// ============================================================
// Re-export shared types from core
// ============================================================

export type {
  PositionType,
  PositionDirection,
  OptionRight,
  CostBasisType,
  PositionLeg,
  Position,
  ImportSource,
  ImportMetadata,
} from '@market-swarm/core';

export {
  POSITION_TYPE_LABELS,
  POSITION_TYPE_CODES,
  POSITION_TYPE_COLORS,
} from '@market-swarm/core';

// ============================================================
// Legacy types (for backward compatibility with existing API)
// ============================================================

export type StrategyType = 'single' | 'vertical' | 'butterfly';
export type Side = 'call' | 'put';
export type ChangeType = 'created' | 'debit_updated' | 'visibility_toggled' | 'edited' | 'deleted';

// ============================================================
// API Types (specific to backend communication)
// ============================================================

// Core strategy interface matching backend model
export interface RiskGraphStrategy {
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

// Version history for audit trail
export interface RiskGraphStrategyVersion {
  id: number;
  strategyId: string;
  version: number;
  debit: number | null;
  visible: boolean;
  label: string | null;
  changeType: ChangeType;
  changeReason: string | null;
  createdAt: string;
}

// Template for reusable strategy configurations
export interface RiskGraphTemplate {
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

// ============================================================
// Input types for creating/updating
// ============================================================

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
  addedAt?: number;
}

export interface UpdateStrategyInput {
  debit?: number | null;
  visible?: boolean;
  sortOrder?: number;
  color?: string | null;
  label?: string | null;
  changeReason?: string;
}

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

export interface UpdateTemplateInput {
  name?: string;
  description?: string | null;
  symbol?: string;
  strategy?: StrategyType;
  side?: Side;
  strikeOffset?: number;
  width?: number | null;
  dteTarget?: number;
  debitEstimate?: number | null;
  isPublic?: boolean;
}

export interface UseTemplateInput {
  spotPrice: number;
  underlying?: string;
  debit?: number | null;
}

// ============================================================
// API Response types
// ============================================================

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  count?: number;
}

export interface StrategiesListResponse extends ApiResponse<RiskGraphStrategy[]> {
  count: number;
}

export interface StrategyResponse extends ApiResponse<RiskGraphStrategy> {}

export interface VersionsListResponse extends ApiResponse<RiskGraphStrategyVersion[]> {
  count: number;
}

export interface TemplatesListResponse extends ApiResponse<RiskGraphTemplate[]> {
  count: number;
}

export interface TemplateResponse extends ApiResponse<RiskGraphTemplate> {}

export interface ExportResponse extends ApiResponse<{
  strategies: RiskGraphStrategy[];
  exportedAt: string;
  count: number;
}> {}

export interface ShareCodeResponse extends ApiResponse<{
  shareCode: string;
}> {}

// ============================================================
// SSE Event types
// ============================================================

export type RiskGraphEventType = 'strategy_added' | 'strategy_updated' | 'strategy_removed';

export interface RiskGraphSSEEvent {
  type: RiskGraphEventType;
  data: RiskGraphStrategy | { id: string };
  ts: string;
}

// ============================================================
// UI-specific Position type (extends core Position)
// ============================================================

import type { Position } from '@market-swarm/core';

/**
 * RiskGraphPosition - UI-specific position with additional fields
 *
 * This extends the core Position type with fields needed for
 * the risk graph UI that aren't part of the core model.
 */
export interface RiskGraphPosition extends Position {
  // UI-specific fields can be added here
  // For now, it's identical to Position
}

// ============================================================
// Legacy type compatibility
// ============================================================

export interface LegacyRiskGraphStrategy {
  id: string;
  strategy: StrategyType;
  side: Side;
  strike: number;
  width: number;
  dte: number;
  expiration: string;
  debit: number | null;
  visible: boolean;
  addedAt: number;
  symbol?: string;
}

// ============================================================
// Conversion utilities
// ============================================================

export function toLegacyStrategy(s: RiskGraphStrategy): LegacyRiskGraphStrategy {
  return {
    id: s.id,
    strategy: s.strategy,
    side: s.side,
    strike: s.strike,
    width: s.width ?? 0,
    dte: s.dte,
    expiration: s.expiration,
    debit: s.debit,
    visible: s.visible,
    addedAt: s.addedAt,
    symbol: s.symbol,
  };
}

export function fromLegacyStrategy(s: LegacyRiskGraphStrategy, _userId: number): CreateStrategyInput {
  return {
    symbol: s.symbol ?? 'SPX',
    underlying: `I:${s.symbol ?? 'SPX'}`,
    strategy: s.strategy,
    side: s.side,
    strike: s.strike,
    width: s.width || null,
    dte: s.dte,
    expiration: s.expiration,
    debit: s.debit,
    visible: s.visible,
    addedAt: s.addedAt,
  };
}
