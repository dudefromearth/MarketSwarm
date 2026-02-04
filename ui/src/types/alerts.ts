/**
 * Shared Alert Types
 *
 * System-wide alert infrastructure types used by:
 * - AlertContext (state management)
 * - RiskGraphPanel, HeatMap, GEX, Widgets, TradeLog, Journal, Playbook
 * - Backend alert evaluation engine
 * - SSE real-time updates
 */

// Alert type categories
export type AlertType =
  | 'price'                 // Spot price crosses level
  | 'debit'                 // Position debit crosses level
  | 'profit_target'         // Profit reaches target
  | 'trailing_stop'         // Trailing stop triggered
  | 'ai_theta_gamma'        // AI-computed dynamic risk zone
  | 'ai_sentiment'          // AI market sentiment analysis
  | 'ai_risk_zone'          // AI-computed risk boundaries
  | 'time_boundary'         // EOD/EOW/EOM alerts
  | 'trade_closed'          // Trade closed notification
  | 'butterfly_entry'       // OTM butterfly entry detection
  | 'butterfly_profit_mgmt'; // Butterfly profit management

// Intent class - determines alert UX behavior
// See fotw-alerts.md for philosophy
export type AlertIntentClass =
  | 'informational'   // "Something changed" - e.g., price crossed a level
  | 'reflective'      // "Worth noticing" - e.g., trade closed, pattern recurrence
  | 'protective';     // "Attention, not action" - e.g., risk envelope degraded

// Alert condition operators
export type AlertCondition = 'above' | 'below' | 'at' | 'outside_zone' | 'inside_zone';

// Behavior when alert triggers
export type AlertBehavior = 'remove_on_hit' | 'once_only' | 'repeat';

// Priority levels for alert urgency
export type AlertPriority = 'low' | 'medium' | 'high' | 'critical';

// Source component that created the alert
export interface AlertSource {
  type: 'strategy' | 'widget' | 'gex' | 'heatmap' | 'tradelog' | 'journal' | 'playbook' | 'chart';
  id: string;
  label: string;
  metadata?: Record<string, unknown>;
}

// Base alert interface - all alerts extend this
export interface AlertBase {
  id: string;
  type: AlertType;
  source: AlertSource;

  // Trigger configuration
  condition: AlertCondition;
  targetValue: number;
  behavior: AlertBehavior;
  priority: AlertPriority;

  // State
  enabled: boolean;
  triggered: boolean;
  triggeredAt?: number;
  triggerCount: number;
  createdAt: number;
  updatedAt: number;

  // Visual
  color: string;
  label?: string;

  // For repeat behavior
  wasOnOtherSide?: boolean;
}

// Price alert - spot price crosses level
export interface PriceAlert extends AlertBase {
  type: 'price';
}

// Debit alert - position debit crosses level
export interface DebitAlert extends AlertBase {
  type: 'debit';
  strategyId: string;
}

// Profit target alert
export interface ProfitTargetAlert extends AlertBase {
  type: 'profit_target';
  strategyId: string;
  entryDebit: number;
}

// Trailing stop alert
export interface TrailingStopAlert extends AlertBase {
  type: 'trailing_stop';
  strategyId: string;
  highWaterMark: number;
}

// AI Theta/Gamma alert - dynamic risk zone
export interface AIThetaGammaAlert extends AlertBase {
  type: 'ai_theta_gamma';
  strategyId: string;
  minProfitThreshold: number;  // e.g., 0.5 = 50% of debit
  entryDebit: number;

  // AI-computed zone (updated by backend)
  zoneLow?: number;
  zoneHigh?: number;
  isZoneActive: boolean;
  highWaterMarkProfit?: number;

  // AI evaluation results
  aiConfidence?: number;      // 0.0 - 1.0
  aiReasoning?: string;
  lastAIUpdate?: number;
}

// AI Sentiment alert
export interface AISentimentAlert extends AlertBase {
  type: 'ai_sentiment';
  symbol: string;
  sentimentThreshold: number;  // -1.0 (bearish) to 1.0 (bullish)
  direction: 'bullish' | 'bearish' | 'either';

  // AI state
  currentSentiment?: number;
  aiSources?: string[];
  aiReasoning?: string;
  lastAIUpdate?: number;
}

// AI Risk Zone alert
export interface AIRiskZoneAlert extends AlertBase {
  type: 'ai_risk_zone';
  symbol: string;

  // AI-computed zones
  zoneLow?: number;
  zoneHigh?: number;
  zoneType: 'support' | 'resistance' | 'pivot';

  // AI evaluation
  aiConfidence?: number;
  aiReasoning?: string;
  lastAIUpdate?: number;
}

// Support type for butterfly entry detection
export type SupportType = 'gex' | 'hvn' | 'poc' | 'val' | 'zero_gamma';

// Butterfly Entry alert - OTM butterfly entry detection
export interface ButterflyEntryAlert extends AlertBase {
  type: 'butterfly_entry';

  // Entry detection results
  entrySupportType?: SupportType;
  entrySupportLevel?: number;
  entryReversalConfirmed: boolean;
  entryTargetStrike?: number;
  entryTargetWidth?: number;

  // Configuration
  supportTypes: SupportType[];      // Which support types to monitor
  minMarketModeScore?: number;      // Max market mode score (compression = low)
  minLfiScore?: number;             // Min LFI score for absorbing regime
}

// Profit management recommendation
export type MgmtRecommendation = 'HOLD' | 'EXIT' | 'TIGHTEN';

// Butterfly Profit Management alert
export interface ButterflyProfitMgmtAlert extends AlertBase {
  type: 'butterfly_profit_mgmt';
  strategyId: string;
  entryDebit: number;

  // Activation and tracking
  mgmtActivationThreshold: number;  // Default 0.75 (75% profit)
  mgmtHighWaterMark?: number;
  mgmtInitialDte?: number;
  mgmtInitialGamma?: number;

  // Risk assessment
  mgmtRiskScore?: number;           // 0-100 composite score
  mgmtRecommendation?: MgmtRecommendation;
  mgmtLastAssessment?: string;
}

// Union type of all alerts
export type Alert =
  | PriceAlert
  | DebitAlert
  | ProfitTargetAlert
  | TrailingStopAlert
  | AIThetaGammaAlert
  | AISentimentAlert
  | AIRiskZoneAlert
  | ButterflyEntryAlert
  | ButterflyProfitMgmtAlert;

// Input type for creating alerts (id, timestamps auto-generated)
export interface CreateAlertInput {
  type: AlertType;
  source: AlertSource;
  condition: AlertCondition;
  targetValue: number;
  behavior?: AlertBehavior;
  priority?: AlertPriority;
  color?: string;
  label?: string;

  // Type-specific fields
  strategyId?: string;
  entryDebit?: number;
  minProfitThreshold?: number;
  symbol?: string;
  sentimentThreshold?: number;
  direction?: 'bullish' | 'bearish' | 'either';
  zoneType?: 'support' | 'resistance' | 'pivot';

  // Butterfly entry specific
  supportTypes?: SupportType[];
  minMarketModeScore?: number;
  minLfiScore?: number;

  // Butterfly profit management specific
  mgmtActivationThreshold?: number;
  mgmtInitialDte?: number;
  mgmtInitialGamma?: number;
}

// Input type for editing alerts
export interface EditAlertInput {
  id: string;
  type?: AlertType;
  condition?: AlertCondition;
  targetValue?: number;
  behavior?: AlertBehavior;
  priority?: AlertPriority;
  color?: string;
  label?: string;
  enabled?: boolean;
  minProfitThreshold?: number;
}

// AI evaluation result from backend
export interface AIEvaluation {
  alertId: string;
  timestamp: number;
  provider: 'openai' | 'anthropic' | 'grok';
  model: string;

  // Decision
  shouldTrigger: boolean;
  confidence: number;  // 0.0 - 1.0
  reasoning: string;

  // Zone updates (for zone-based alerts)
  zoneLow?: number;
  zoneHigh?: number;

  // Metadata
  tokensUsed?: number;
  latencyMs: number;
}

// Market context for AI evaluation
export interface MarketContext {
  symbol: string;
  spotPrice: number;
  vix: number;
  gexRegime: 'positive' | 'negative';
  marketMode: 'compression' | 'transition' | 'expansion';
  biasLfi?: { bias: string; flow: string };

  // Strategy context (if applicable)
  strategy?: {
    id: string;
    type: string;
    strike: number;
    width: number;
    side: 'call' | 'put';
    dte: number;
    currentDebit: number | null;
    entryDebit: number | null;
    theoreticalPnL?: number;
  };
}

// Alert trigger event from SSE
export interface AlertTriggerEvent {
  alertId: string;
  triggeredAt: number;
  aiReasoning?: string;
  aiConfidence?: number;
}

// Alert update event from SSE
export interface AlertUpdateEvent {
  alertId: string;
  updates: Partial<Alert>;
}

// Default alert colors
export const ALERT_COLORS = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#3b82f6', // blue
  '#8b5cf6', // purple
  '#ffffff', // white
  '#9ca3af', // light gray
  '#4b5563', // dark gray
] as const;

// Helper to get confidence level label
export function getConfidenceLevel(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.5) return 'medium';
  return 'low';
}

// Helper to get confidence color
export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return '#22c55e'; // green
  if (confidence >= 0.5) return '#eab308'; // yellow
  return '#ef4444'; // red
}

// Type guard functions
export function isPriceAlert(alert: Alert): alert is PriceAlert {
  return alert.type === 'price';
}

export function isDebitAlert(alert: Alert): alert is DebitAlert {
  return alert.type === 'debit';
}

export function isAIAlert(alert: Alert): alert is AIThetaGammaAlert | AISentimentAlert | AIRiskZoneAlert {
  return alert.type.startsWith('ai_');
}

export function isButterflyEntryAlert(alert: Alert): alert is ButterflyEntryAlert {
  return alert.type === 'butterfly_entry';
}

export function isButterflyProfitMgmtAlert(alert: Alert): alert is ButterflyProfitMgmtAlert {
  return alert.type === 'butterfly_profit_mgmt';
}

export function isButterflyAlert(alert: Alert): alert is ButterflyEntryAlert | ButterflyProfitMgmtAlert {
  return alert.type === 'butterfly_entry' || alert.type === 'butterfly_profit_mgmt';
}

export function hasAIReasoning(alert: Alert): boolean {
  return 'aiReasoning' in alert && alert.aiReasoning !== undefined;
}

// ==================== Prompt Alert Types ====================

/**
 * Confidence threshold for AI evaluation
 * Determines how certain the AI must be before triggering stage transitions
 */
export type ConfidenceThreshold = 'high' | 'medium' | 'low';

/**
 * Orchestration mode for multi-prompt relationships
 */
export type OrchestrationMode = 'parallel' | 'overlapping' | 'sequential';

/**
 * Lifecycle state of a prompt alert
 */
export type PromptLifecycleState = 'active' | 'dormant' | 'accomplished';

/**
 * Stage in the prompt alert flow
 */
export type PromptStage = 'watching' | 'update' | 'warn' | 'accomplished';

/**
 * Reference state snapshot captured at alert creation
 */
export interface ReferenceStateSnapshot {
  id: string;
  promptAlertId: string;

  // Greeks
  delta?: number;
  gamma?: number;
  theta?: number;

  // P&L
  expirationBreakevens?: number[];
  theoreticalBreakevens?: number[];
  maxProfit?: number;
  maxLoss?: number;
  pnlAtSpot?: number;

  // Market
  spotPrice?: number;
  vix?: number;
  marketRegime?: string;

  // Strategy
  dte?: number;
  debit?: number;
  strike?: number;
  width?: number;
  side?: string;

  capturedAt: string;
}

/**
 * Version history record for a prompt alert
 */
export interface PromptAlertVersion {
  id: string;
  promptAlertId: string;
  version: number;
  promptText: string;
  parsedZones?: {
    referenceLogic?: Record<string, unknown>;
    deviationLogic?: Record<string, unknown>;
    evaluationMode?: string;
    stageThresholds?: Record<string, unknown>;
  };
  createdAt: string;
}

/**
 * Trigger history record
 */
export interface PromptAlertTrigger {
  id: string;
  promptAlertId: string;
  versionAtTrigger: number;
  stage: PromptStage;
  aiConfidence?: number;
  aiReasoning?: string;
  marketSnapshot?: Record<string, unknown>;
  triggeredAt: string;
}

/**
 * Parsed semantic zones from AI prompt parsing
 */
export interface ParsedPromptZones {
  referenceLogic?: {
    metrics: string[];
    captureFields: string[];
    notes?: string;
  };
  deviationLogic?: {
    watchFor: string;
    direction: string;
    metric: string;
    comparisonType: string;
    comparisonTarget: string;
    notes?: string;
  };
  evaluationMode?: 'regular' | 'threshold' | 'event';
  stageThresholds?: {
    updateTrigger?: { condition: string; thresholdPercentage?: number };
    warnTrigger?: { condition: string; thresholdPercentage?: number };
    accomplishedTrigger?: { condition: string; outcome?: string };
  };
}

/**
 * Prompt-driven strategy alert
 *
 * Lets traders describe, in natural language, when a strategy stops
 * behaving as designed. AI parses the prompt and evaluates against
 * a captured reference state.
 */
export interface PromptAlert {
  id: string;
  userId: number;
  strategyId: string;

  // Prompt content
  promptText: string;
  promptVersion: number;

  // AI-parsed semantic zones
  parsedReferenceLogic?: Record<string, unknown>;
  parsedDeviationLogic?: Record<string, unknown>;
  parsedEvaluationMode?: string;
  parsedStageThresholds?: Record<string, unknown>;

  // User declarations
  confidenceThreshold: ConfidenceThreshold;

  // Orchestration
  orchestrationMode: OrchestrationMode;
  orchestrationGroupId?: string;
  sequenceOrder: number;
  activatesAfterAlertId?: string;

  // State
  lifecycleState: PromptLifecycleState;
  currentStage: PromptStage;

  // Last evaluation
  lastAiConfidence?: number;
  lastAiReasoning?: string;
  lastEvaluationAt?: string;

  // Timestamps
  createdAt: string;
  updatedAt: string;
  activatedAt?: string;
  accomplishedAt?: string;

  // Populated by API when requested
  referenceState?: ReferenceStateSnapshot;
  versions?: PromptAlertVersion[];
  triggers?: PromptAlertTrigger[];
}

/**
 * Input for creating a new prompt alert
 */
export interface CreatePromptAlertInput {
  strategyId: string;
  promptText: string;
  confidenceThreshold?: ConfidenceThreshold;
  orchestrationMode?: OrchestrationMode;
  orchestrationGroupId?: string;
  sequenceOrder?: number;
  activatesAfterAlertId?: string;

  // Parsed zones (from AI parsing)
  parsedReferenceLogic?: Record<string, unknown>;
  parsedDeviationLogic?: Record<string, unknown>;
  parsedEvaluationMode?: string;
  parsedStageThresholds?: Record<string, unknown>;

  // Reference state snapshot
  referenceState?: Partial<ReferenceStateSnapshot>;
}

/**
 * Input for editing a prompt alert
 */
export interface EditPromptAlertInput {
  promptText?: string;
  confidenceThreshold?: ConfidenceThreshold;
  orchestrationMode?: OrchestrationMode;
  orchestrationGroupId?: string;
  sequenceOrder?: number;
  activatesAfterAlertId?: string;
  lifecycleState?: PromptLifecycleState;
  currentStage?: PromptStage;

  // Parsed zones (re-parsed if text changes)
  parsedReferenceLogic?: Record<string, unknown>;
  parsedDeviationLogic?: Record<string, unknown>;
  parsedEvaluationMode?: string;
  parsedStageThresholds?: Record<string, unknown>;
}

/**
 * Prompt alert stage change SSE event
 */
export interface PromptAlertStageChangeEvent {
  alertId: string;
  stage: PromptStage;
  reasoning: string;
  confidence: number;
  timestamp: string;
}

/**
 * Stage styling configuration
 */
export const PROMPT_STAGE_STYLES: Record<PromptStage, {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
}> = {
  watching: {
    color: '#9ca3af',
    bgColor: '#1f2937',
    icon: '👁️',
    label: 'Watching',
  },
  update: {
    color: '#3b82f6',
    bgColor: '#1e3a5f',
    icon: '📊',
    label: 'Update',
  },
  warn: {
    color: '#f59e0b',
    bgColor: '#78350f',
    icon: '⚠️',
    label: 'Warning',
  },
  accomplished: {
    color: '#22c55e',
    bgColor: '#14532d',
    icon: '✓',
    label: 'Accomplished',
  },
};

/**
 * Check if a prompt alert is actionable (not dormant/accomplished)
 */
export function isPromptAlertActive(alert: PromptAlert): boolean {
  return alert.lifecycleState === 'active';
}

/**
 * Get stage display info
 */
export function getPromptStageInfo(stage: PromptStage) {
  return PROMPT_STAGE_STYLES[stage];
}
