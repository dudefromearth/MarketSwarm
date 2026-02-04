// ui/src/types/tradeSelector.ts
// TypeScript interfaces for Trade Selector model

export interface TileScoreComponents {
  r2r: number;              // 0-100 (25% weight)
  convexity: number;        // 0-100 (40% weight - PRIMARY)
  width_fit: number;        // 0-100 (20% weight)
  gamma_alignment: number;  // 0-100 (15% weight)
}

export interface TileScore {
  tile_key: string;         // "butterfly:0:30:6020"
  composite: number;        // 0-100 weighted
  confidence: number;       // 0-1 data quality
  components: TileScoreComponents;
}

// Campaign types
export type Campaign = '0dte_tactical' | 'convex_stack' | 'sigma_drift';
export type EdgeCase = 'batman' | 'timewarp' | 'gamma_scalp';

export interface TradeRecommendation {
  rank: number;
  tile_key: string;
  score: TileScore;

  // Campaign info
  campaign: Campaign;
  edge_cases: EdgeCase[];
  r2r_vs_typical: string;   // e.g., "12.5 vs 9-18"

  // Tile details
  strategy: 'butterfly' | 'vertical';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  debit: number;
  debit_pct: number;        // Debit as % of width

  // Computed
  max_profit: number;       // width - debit
  max_loss: number;         // debit
  r2r_ratio: number;
  distance_to_spot: number;
  distance_to_gamma_magnet: number | null;
}

export type VixRegime = 'zombieland' | 'goldilocks_1' | 'goldilocks_2' | 'chaos';
export type VixSpecial = 'timewarp' | 'gamma_scalp' | 'batman' | null;

// Campaign definition
export interface CampaignDefinition {
  dte_range: [number, number];
  r2r_typical: [number, number];
  debit_pct_range: [number, number];
  frequency: string;
}

// Scoring weights
export interface ScoringWeights {
  convexity: number;        // 40% - PRIMARY
  r2r: number;              // 25%
  width_fit: number;        // 20%
  gamma_alignment: number;  // 15%
}

// Snapshot of all indicators at recommendation time
export interface IndicatorSnapshot {
  spot: number;
  vix: number;
  vix_regime: VixRegime;
  vix_special: VixSpecial;
  gamma_magnet: number | null;
  zero_gamma: number | null;
  flip_above: number | null;
  flip_below: number | null;
  directional_strength: number | null;  // -100 to +100
  lfi_score: number | null;             // 0 to 100
  market_mode_score: number | null;     // 0 to 100
  total_net_gex: number | null;
  max_call_gex_strike: number | null;
  max_put_gex_strike: number | null;
}

// Playbook context
export interface PlaybookContext {
  regime: VixRegime;
  session: string;
  ideal_width: string;
  ideal_dte: string;
  max_debit_pct: number;
  decay_factor: number;
  entry_optimal: boolean;
  exercise_window: boolean;
  outlier_zone: boolean;
}

// Edge case availability
export interface EdgeCaseAvailability {
  batman_available: boolean;
  timewarp_available: boolean;
  gamma_scalp_active: boolean;
}

export interface TradeSelectorModel {
  ts: number;
  ts_iso: string;
  symbol: string;
  spot: number;
  vix: number;
  vix_regime: VixRegime;
  vix_special: VixSpecial;

  // Scoring methodology
  scoring: {
    weights: ScoringWeights;
    hard_filter: string;
  };

  // Campaign definitions
  campaigns: Record<Campaign, CampaignDefinition>;

  // Playbook context
  playbook: PlaybookContext;

  // Edge case availability
  edge_cases: EdgeCaseAvailability;

  gamma_magnet: number | null;
  zero_gamma: number | null;
  indicator_snapshot: IndicatorSnapshot;
  scores: Record<string, TileScore>;
  recommendations: TradeRecommendation[];  // Top 10
  total_scored: number;
  filtered_by_debit_rule: number;
}

// SSE event data (may include symbol from broadcast)
export interface TradeSelectorSSEData extends TradeSelectorModel {
  symbol: string;
}

// API response wrapper
export interface TradeSelectorAPIResponse {
  success: boolean;
  data: TradeSelectorModel;
  ts: number;
}
