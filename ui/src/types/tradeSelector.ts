// ui/src/types/tradeSelector.ts
// TypeScript interfaces for Trade Selector model

export interface TileScoreComponents {
  r2r: number;              // 0-100
  convexity: number;        // 0-100
  width_fit: number;        // 0-100
  gamma_alignment: number;  // 0-100
}

export interface TileScore {
  tile_key: string;         // "butterfly:0:30:6020"
  composite: number;        // 0-100 weighted
  confidence: number;       // 0-1 data quality
  components: TileScoreComponents;
}

export interface TradeRecommendation {
  rank: number;
  tile_key: string;
  score: TileScore;

  // Tile details
  strategy: 'butterfly' | 'vertical';
  side: 'call' | 'put';
  strike: number;
  width: number;
  dte: number;
  debit: number;

  // Computed
  max_profit: number;       // width - debit
  max_loss: number;         // debit
  r2r_ratio: number;
  distance_to_spot: number;
  distance_to_gamma_magnet: number | null;
}

export type VixRegime = 'zombieland' | 'goldilocks' | 'chaos';
export type VixSpecial = 'timewarp' | 'gamma_scalp' | 'batman' | null;

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

export interface TradeSelectorModel {
  ts: number;
  ts_iso: string;
  symbol: string;
  spot: number;
  vix: number;
  vix_regime: VixRegime;
  vix_special: VixSpecial;
  gamma_magnet: number | null;
  zero_gamma: number | null;
  indicator_snapshot: IndicatorSnapshot;
  scores: Record<string, TileScore>;
  recommendations: TradeRecommendation[];  // Top 10
  total_scored: number;
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
