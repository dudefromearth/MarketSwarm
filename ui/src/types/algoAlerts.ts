/**
 * Algo-Alerts: Position State Machine for Risk Graph
 *
 * Two modes:
 * - Mode A (Entry): No position running → detect conditions → propose position
 * - Mode B (Management): Position exists → monitor structure → recommend action
 *
 * Filters are permission gates (allow/disallow), never triggers.
 * Alert-and-confirm only (no auto-execution).
 */

// ==================== Data Sources ====================

/**
 * Filter data source — maps to Redis feeds from massive
 */
export type FilterDataSource =
  | 'gex'              // GEX data (net_gex, max_gex_strike, zero_gamma_distance)
  | 'market_mode'      // Market mode score & classification
  | 'bias_lfi'         // Bias/LFI absorption & pressure
  | 'vix_regime'       // VIX regime classification
  | 'volume_profile'   // Volume profile (POC, value area)
  | 'price'            // Spot price
  | 'dte'              // Days to expiration
  | 'trade_selector'   // Trade selector recommendations
  | 'position';        // Current position data (Mode B)

/**
 * Filter field mappings per data source
 */
export const FILTER_FIELDS: Record<FilterDataSource, { field: string; label: string; description: string }[]> = {
  gex: [
    { field: 'net_gex', label: 'Net GEX', description: 'Net gamma exposure across strikes' },
    { field: 'max_gex_strike', label: 'Max GEX Strike', description: 'Strike with highest gamma concentration' },
    { field: 'zero_gamma_distance', label: 'Zero Gamma Distance', description: 'Distance from spot to zero gamma level' },
  ],
  market_mode: [
    { field: 'score', label: 'Mode Score (0-100)', description: 'Market mode score — low = compression, high = expansion' },
    { field: 'mode', label: 'Mode', description: 'Classified mode: compression, transition, expansion' },
  ],
  bias_lfi: [
    { field: 'absorption_score', label: 'Absorption Score (0-100)', description: 'Structural absorption intensity' },
    { field: 'pressure_asymmetry', label: 'Pressure Asymmetry (-100 to +100)', description: 'Structural pressure imbalance — not directional bias' },
  ],
  vix_regime: [
    { field: 'regime', label: 'VIX Regime', description: 'Current regime: chaos, goldilocks_2, goldilocks_1, zombieland' },
    { field: 'vix_level', label: 'VIX Level', description: 'Current VIX value' },
  ],
  volume_profile: [
    { field: 'poc_distance', label: 'POC Distance', description: 'Distance from spot to point of control' },
    { field: 'in_value_area', label: 'In Value Area', description: 'Whether spot is within the value area' },
  ],
  price: [
    { field: 'spot', label: 'Spot Price', description: 'Current underlying price' },
  ],
  dte: [
    { field: 'dte', label: 'Days to Expiration', description: 'Days until expiration' },
  ],
  trade_selector: [
    { field: 'top_score', label: 'Top Score (0-100)', description: 'Highest ranked structure score' },
    { field: 'has_recommendation', label: 'Has Recommendation', description: 'Whether trade selector has an active recommendation' },
  ],
  position: [
    { field: 'pnl_percent', label: 'P&L %', description: 'Current position P&L as percentage of entry' },
    { field: 'current_debit', label: 'Current Debit', description: 'Current position value' },
    { field: 'dte_remaining', label: 'DTE Remaining', description: 'Days to expiration for the position' },
  ],
};

// ==================== Filter Conditions ====================

/**
 * Filter operator types
 */
export type FilterOperator = 'gt' | 'lt' | 'eq' | 'gte' | 'lte' | 'between' | 'in' | 'not_in';

/**
 * Structured filter condition — a single permission gate
 */
export interface FilterCondition {
  id: string;
  dataSource: FilterDataSource;
  field: string;
  operator: FilterOperator;
  value: number | string | boolean | number[];  // number[] for 'between', string for 'in'/'eq' on enums
  required: boolean;  // If true, missing data → filter fails (fail-closed)
}

/**
 * Per-filter evaluation result
 */
export interface FilterEvaluationResult {
  filterId: string;
  dataSource: FilterDataSource;
  field: string;
  passed: boolean;
  currentValue: number | string | boolean | null;
  targetValue: number | string | boolean | number[];
  dataAvailable: boolean;
}

// ==================== Algo Alert Core ====================

/**
 * Algo alert mode
 */
export type AlgoAlertMode = 'entry' | 'management';

/**
 * Algo alert status
 * - active: evaluating on each cycle
 * - paused: user-paused, not evaluating
 * - frozen: conflicting regime detected, standing down automatically
 * - archived: no longer active, preserved for reference
 */
export type AlgoAlertStatus = 'active' | 'paused' | 'frozen' | 'archived';

/**
 * Trader constraints for entry proposals (Mode A)
 */
export interface TraderConstraints {
  maxRisk: number;                    // Maximum dollar risk per position
  preferredStructures?: string[];     // e.g., ['butterfly', 'vertical']
  preferredDteRange?: [number, number]; // e.g., [0, 7]
  preferredWidth?: number;            // Preferred spread width
  maxOpenPositions?: number;          // Max concurrent positions
}

/**
 * Algo alert definition — the main configurable object
 */
export interface AlgoAlert {
  id: string;
  userId: number;
  name: string;
  mode: AlgoAlertMode;
  status: AlgoAlertStatus;
  frozenReason?: string;
  filters: FilterCondition[];
  entryConstraints?: TraderConstraints;   // Mode A only
  positionId?: string;                     // Mode B only — bound position
  promptOverride?: string;                 // Advanced: custom evaluation prompt
  lastEvaluation?: AlgoAlertEvaluationState;
  lastEvaluatedAt?: string;
  evaluationCount: number;
  createdAt: string;
  updatedAt: string;
}

/**
 * Snapshot of the last evaluation cycle for this alert
 */
export interface AlgoAlertEvaluationState {
  filterResults: FilterEvaluationResult[];
  allPassed: boolean;
  evaluatedAt: string;
  frozenCycles?: number;  // How many oscillation cycles detected
}

// ==================== Proposals ====================

/**
 * Proposal action type
 */
export type ProposalType = 'entry' | 'exit' | 'tighten' | 'hold' | 'adjust';

/**
 * Proposal resolution status
 */
export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

/**
 * Suggested position structure (Mode A entry proposals)
 */
export interface SuggestedPosition {
  strategyType: string;    // butterfly, vertical, etc.
  strike: number;
  width: number;
  side: 'call' | 'put';
  dte: number;
  expiration: string;
  estimatedDebit: number;
  symbol?: string;
}

/**
 * Algo proposal — a proposed action requiring trader confirmation
 */
export interface AlgoProposal {
  id: string;
  algoAlertId: string;
  userId: number;
  type: ProposalType;
  status: ProposalStatus;
  suggestedPosition?: SuggestedPosition;   // Mode A: what to open
  reasoning: string;
  filterResults: FilterEvaluationResult[];
  structuralAlignmentScore: number;        // NOT "confidence" — structural alignment only
  createdAt: string;
  expiresAt: string;                       // Proposals auto-expire (default 5 min TTL)
  resolvedAt?: string;
}

// ==================== Input Types ====================

/**
 * Input for creating a new algo alert
 */
export interface CreateAlgoAlertInput {
  name: string;
  mode: AlgoAlertMode;
  filters: Omit<FilterCondition, 'id'>[];
  entryConstraints?: TraderConstraints;
  positionId?: string;
  promptOverride?: string;
}

/**
 * Input for updating an algo alert
 */
export interface UpdateAlgoAlertInput {
  name?: string;
  status?: AlgoAlertStatus;
  filters?: Omit<FilterCondition, 'id'>[];
  entryConstraints?: TraderConstraints;
  positionId?: string;
  promptOverride?: string;
}

// ==================== SSE Event Types ====================

/**
 * SSE event: algo alert proposal generated
 */
export interface AlgoAlertProposalEvent {
  proposalId: string;
  algoAlertId: string;
  type: ProposalType;
  reasoning: string;
  structuralAlignmentScore: number;
  suggestedPosition?: SuggestedPosition;
  expiresAt: string;
}

/**
 * SSE event: algo alert evaluation completed (filter state update)
 */
export interface AlgoAlertEvaluationEvent {
  algoAlertId: string;
  filterResults: FilterEvaluationResult[];
  allPassed: boolean;
  status: AlgoAlertStatus;
  frozenReason?: string;
}

/**
 * SSE event: algo alert frozen due to regime conflict
 */
export interface AlgoAlertFrozenEvent {
  algoAlertId: string;
  reason: string;
}

// ==================== Display Helpers ====================

/**
 * Status styling for algo alerts
 */
export const ALGO_ALERT_STATUS_STYLES: Record<AlgoAlertStatus, {
  color: string;
  bgColor: string;
  label: string;
}> = {
  active: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    label: 'Active',
  },
  paused: {
    color: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.15)',
    label: 'Paused',
  },
  frozen: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    label: 'Frozen',
  },
  archived: {
    color: '#4b5563',
    bgColor: 'rgba(75, 85, 99, 0.15)',
    label: 'Archived',
  },
};

/**
 * Proposal type styling
 */
export const PROPOSAL_TYPE_STYLES: Record<ProposalType, {
  color: string;
  bgColor: string;
  label: string;
}> = {
  entry: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    label: 'ENTRY',
  },
  exit: {
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    label: 'EXIT',
  },
  tighten: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    label: 'TIGHTEN',
  },
  hold: {
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    label: 'HOLD',
  },
  adjust: {
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    label: 'ADJUST',
  },
};

/**
 * Filter data source display names
 */
export const DATA_SOURCE_LABELS: Record<FilterDataSource, string> = {
  gex: 'GEX',
  market_mode: 'Market Mode',
  bias_lfi: 'Bias / LFI',
  vix_regime: 'VIX Regime',
  volume_profile: 'Volume Profile',
  price: 'Price',
  dte: 'DTE',
  trade_selector: 'Trade Selector',
  position: 'Position',
};

/**
 * Operator display labels
 */
export const OPERATOR_LABELS: Record<FilterOperator, string> = {
  gt: '>',
  lt: '<',
  eq: '=',
  gte: '>=',
  lte: '<=',
  between: 'between',
  in: 'in',
  not_in: 'not in',
};
