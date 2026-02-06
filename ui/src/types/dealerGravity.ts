/**
 * Dealer Gravity Type Definitions
 *
 * IMPORTANT: This file uses Dealer Gravity lexicon exclusively.
 *
 * Canonical Terminology:
 *   - Volume Node: Price level with concentrated market attention (NOT HVN)
 *   - Volume Well: Price level with neglect (NOT LVN)
 *   - Crevasse: Extended region of persistent volume scarcity
 *   - Market Memory: Persistent topology across long horizons
 *
 * BANNED TERMS (never use): POC, VAH, VAL, Value Area, HVN, LVN
 */

// ============================================================================
// Tier 1: Visualization Artifact (UI-Focused)
// ============================================================================

/**
 * Volume profile bins in compact array format.
 * min + index * step = price level
 * bins[index] = normalized volume (0-1000 scale)
 */
export interface DGProfile {
  min: number;
  step: number;
  bins: number[];
}

/**
 * Structural features detected by the artifact builder.
 * These are pre-computed - frontend just renders them.
 */
export interface DGStructures {
  /** Price levels with concentrated market attention (friction, memory) */
  volumeNodes: number[];
  /** Price levels with neglect (low resistance, acceleration zones) */
  volumeWells: number[];
  /** Extended regions of persistent volume scarcity [start, end] pairs */
  crevasses: [number, number][];
}

/**
 * Artifact metadata for versioning and audit.
 */
export interface DGArtifactMeta {
  spot: number | null;
  algorithm: string;
  normalizedScale: number;
  artifactVersion: string;
  lastUpdate: string;
}

/**
 * Complete visualization artifact (Tier 1).
 * The frontend maps bins → pixels, draws overlays, applies colors.
 * NO inference, NO recomputation, NO ambiguity.
 */
export interface DGArtifact {
  profile: DGProfile;
  structures: DGStructures;
  meta: DGArtifactMeta;
}

// ============================================================================
// Tier 2: Context Snapshot (System-Focused)
// ============================================================================

/**
 * ML-ready context snapshot for Trade Selector, RiskGraph, ML systems.
 * Extremely small (~200 bytes), deterministic, replayable.
 */
export interface DGContextSnapshot {
  symbol: string;
  spot: number | null;
  nearestVolumeNode: number | null;
  nearestVolumeNodeDist: number | null;
  volumeWellProximity: number | null;
  inCrevasse: boolean;
  marketMemoryStrength: number;
  gammaAlignment: 'positive' | 'negative' | null;
  artifactVersion: string;
  timestamp: string;
}

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * User's Dealer Gravity display configuration.
 */
export interface DealerGravityConfig {
  id: number;
  name: string;
  enabled: boolean;
  mode: 'raw' | 'tv';
  widthPercent: number;
  numBins: number;
  cappingSigma: number;
  color: string;
  transparency: number;
  showVolumeNodes: boolean;
  showVolumeWells: boolean;
  showCrevasses: boolean;
  isDefault: boolean;
  createdAt?: string;
  updatedAt?: string;
}

/**
 * GEX panel display configuration.
 */
export interface GexPanelConfig {
  id: number;
  enabled: boolean;
  mode: 'combined' | 'net';
  callsColor: string;
  putsColor: string;
  widthPx: number;
  isDefault: boolean;
  createdAt?: string;
  updatedAt?: string;
}

// ============================================================================
// AI Analysis Types
// ============================================================================

/**
 * AI visual analysis result using Dealer Gravity lexicon.
 */
export interface DGAnalysisResult {
  id: number;
  symbol: string;
  spotPrice: number;
  volumeNodes: number[];
  volumeWells: number[];
  crevasses: [number, number][];
  marketMemoryStrength: number;
  bias: 'bullish' | 'bearish' | 'neutral';
  summary: string;
  provider?: string;
  model?: string;
  tokensUsed?: number;
  latencyMs?: number;
  createdAt: string;
}

// ============================================================================
// SSE Event Types
// ============================================================================

/**
 * SSE event when artifact is updated.
 * Frontend should refetch artifact when artifact_version changes.
 */
export interface DGArtifactUpdatedEvent {
  type: 'dealer_gravity_artifact_updated';
  symbol: string;
  artifactVersion: string;
  occurredAt: string;
}

// ============================================================================
// API Response Types
// ============================================================================

export interface DGArtifactResponse {
  success: boolean;
  data?: DGArtifact;
  error?: string;
  ts: number;
}

export interface DGContextResponse {
  success: boolean;
  data?: DGContextSnapshot;
  error?: string;
  ts: number;
}

export interface DGConfigsResponse {
  success: boolean;
  data?: DealerGravityConfig[];
  error?: string;
  ts: number;
}

export interface GexConfigsResponse {
  success: boolean;
  data?: GexPanelConfig[];
  error?: string;
  ts: number;
}

export interface DGAnalysesResponse {
  success: boolean;
  data?: DGAnalysisResult[];
  error?: string;
  ts: number;
}

// ============================================================================
// Partial Update Types (for PATCH operations)
// ============================================================================

export type DealerGravityConfigUpdate = Partial<Omit<DealerGravityConfig, 'id' | 'createdAt' | 'updatedAt'>>;

export type GexPanelConfigUpdate = Partial<Omit<GexPanelConfig, 'id' | 'createdAt' | 'updatedAt'>>;
