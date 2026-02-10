/**
 * Shared Alert Types
 *
 * System-wide alert infrastructure types used by:
 * - AlertContext (state management)
 * - RiskGraphPanel, HeatMap, GEX, Widgets, TradeLog, Journal, Playbook
 * - Backend alert evaluation engine
 * - SSE real-time updates
 *
 * Architecture (from alert-mgr.md spec):
 * - Alert Definition: persistent, declarative (prompt, scope, severity, schedule)
 * - Alert Evaluation: runtime interpretation (fast/slow/event evaluators)
 */

// ==================== Alert Manager v1.1 Unified Model ====================

/**
 * Alert Scope - what the alert is attached to
 * From spec section 4
 */
export type AlertScope =
  | 'position'    // Bound to a specific position
  | 'symbol'      // Applies to an instrument (e.g. SPX)
  | 'portfolio'   // Aggregated exposure / risk
  | 'behavioral'  // Trader behavior patterns
  | 'workflow';   // Routine / journaling / process

/**
 * Alert Severity - determines UI behavior
 * From spec section 7
 */
export type AlertSeverity =
  | 'inform'  // Passive awareness
  | 'notify'  // Draw attention
  | 'warn'    // Requires acknowledgment
  | 'block';  // Prevents action; override allowed

/**
 * Alert Lifecycle Stage
 * From spec section 3: CREATED → WATCHING → UPDATE → WARN → ACCOMPLISHED | DISMISSED | OVERRIDDEN
 */
export type AlertLifecycleStage =
  | 'created'      // Initial state
  | 'watching'     // Conditions monitored
  | 'update'       // Informational context change
  | 'warn'         // Action-worthy condition
  | 'accomplished' // Intent satisfied
  | 'dismissed'    // User dismissed
  | 'overridden';  // User overrode block

/**
 * Alert Status - active/paused state (separate from lifecycle)
 */
export type AlertStatus = 'active' | 'paused' | 'archived';

/**
 * Alert Binding State - whether alert is bound to a target
 * From spec section 5: Alerts may be created before their target exists
 */
export type AlertBindingState =
  | 'unbound'          // No target yet
  | 'symbol_bound'     // Bound to symbol
  | 'position_bound'   // Bound to position
  | 'portfolio_bound'  // Portfolio-wide
  | 'workflow_bound';  // Process-driven

/**
 * Alert Binding Policy - how alert binds to targets
 * From spec section 5
 */
export type AlertBindingPolicy =
  | 'manual'                  // User manually binds
  | 'auto_on_next_position'   // Auto-bind when next position created
  | 'auto_on_matching_symbol'; // Auto-bind when matching symbol position

/**
 * Process Phase - which FOTW phase the alert belongs to
 * From spec section 10
 */
export type ProcessPhase =
  | 'routine'    // Prep phase
  | 'structure'  // Dealer Gravity
  | 'selection'  // Heatmap
  | 'analysis'   // Risk Graph
  | 'action'     // Execution / Simulation
  | 'process';   // Journal, Retrospective

/**
 * Budget Class for fatigue control
 * From spec section 8
 */
export type AlertBudgetClass = 'standard' | 'high_priority' | 'critical';

/**
 * Alert Intent - whether alert is position-specific or strategy-general
 * Used for default selection logic in orphan alert dialog
 */
export type AlertIntent = 'position_specific' | 'strategy_general';

/**
 * Map alert type to default intent
 */
export function getDefaultAlertIntent(type: AlertType): AlertIntent {
  switch (type) {
    case 'ai_theta_gamma':
    case 'ai_sentiment':
    case 'ai_risk_zone':
    case 'butterfly_profit_mgmt':
      return 'strategy_general';
    default:
      return 'position_specific';
  }
}

// ==================== Algo Alerts (Strategy-Aware) ====================

/**
 * Alert Category - extended taxonomy from algo-alerts.md
 *
 * 1. Informational - Context, orientation, awareness
 * 2. Behavioral/Process - Discipline, habit reinforcement
 * 3. Structural - Market topology, regime, Dealer Gravity
 * 4. Algo - Strategy-aware, rule-expressive alerts (NEW)
 */
export type AlertCategory =
  | 'informational'  // "Something is happening"
  | 'behavioral'     // "You are doing something"
  | 'structural'     // "The market structure is changing"
  | 'algo';          // "This strategy's assumptions are being met or violated"

/**
 * Algo Alert Class - types of strategy-aware alerts
 * From algo-alerts.md
 */
export type AlgoAlertClass =
  | 'execution_guard'     // Prevent misuse of a strategy
  | 'validity_monitor'    // Ensure trade still makes sense
  | 'profit_management';  // Generic or strategy-specific exit logic

/**
 * Strategy Type - supported trading strategies
 * Each has specific algo alert templates
 */
export type StrategyType =
  | '0dte_tactical'      // Fast convexity, tight timing, high gamma
  | 'timewarp'           // Harvest time + structure stability
  | 'batman'             // Extreme asymmetry, rare activation (tail campaigns)
  | 'convexity_stack'    // Layered convex exposure across strikes
  | 'gamma_scalping'     // Monetize movement + reversion
  | 'butterfly'          // Standard butterfly strategies
  | 'vertical'           // Vertical spreads
  | 'custom';            // User-defined strategy

/**
 * Algo Alert Configuration - strategy-specific parameters
 */
export interface AlgoAlertConfig {
  strategyType: StrategyType;
  algoClass: AlgoAlertClass;

  // Strategy-specific parameters (varies by type)
  parameters?: {
    // 0DTE Tactical
    entryDeadline?: string;      // e.g., "13:45" - block after this time
    expansionWindow?: number;    // minutes to wait for structure expansion

    // TimeWarp
    carryThreshold?: number;     // warn if carry drops below
    decayWindow?: string;        // optimal decay window

    // Batman / Tail
    chaosRegimeRequired?: boolean;
    tailProbabilityMin?: number;

    // Convexity Stack
    riskZoneOverlapMax?: number; // max overlap percentage
    gammaClusterThreshold?: number;

    // Gamma Scalping
    oscillationMin?: number;     // min spot oscillation
    volatilityFloor?: number;    // warn below this

    // Profit Management (generic)
    profitTargetPercent?: number;   // e.g., 50 for 50% of max profit
    riskRewardFloor?: number;       // warn when R:R drops below
    expectedValueFloor?: number;    // warn when EV turns negative
  };

  // Evaluation function reference
  evaluatorId?: string;

  // Suggested action when triggered
  suggestedAction?: 'hold' | 'exit' | 'trim' | 'adjust' | 'pause' | 'review';
}

/**
 * Algo Alert Definition - extends base AlertDefinition
 */
export interface AlgoAlertDefinition {
  // Inherits all AlertDefinition fields
  id: string;
  userId: number;
  prompt: string;
  title?: string;

  // Algo-specific fields
  category: 'algo';
  algoConfig: AlgoAlertConfig;

  // Strategy binding
  strategyId?: string;        // Bound to specific position
  strategyType: StrategyType;

  // Intent summary (human-readable)
  intentSummary: string;      // e.g., "Fast convexity, tight timing"

  // Trigger condition (human-readable)
  triggerCondition: string;   // e.g., "Entry attempted after 1:45pm"

  // Confidence in evaluation (0-1)
  confidence?: number;

  // Standard fields
  scope: AlertScope;
  severity: AlertSeverity;
  status: AlertStatus;
  lifecycleStage: AlertLifecycleStage;
  bindingState: AlertBindingState;
  bindingPolicy: AlertBindingPolicy;
  targetRef: AlertTargetRef;
  cooldownSeconds: number;
  budgetClass: AlertBudgetClass;
  createdAt: string;
  updatedAt: string;
  lastTriggeredAt?: string;
  triggerCount: number;
}

/**
 * Algo Alert Category Styles
 */
export const ALERT_CATEGORY_STYLES: Record<AlertCategory, {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
}> = {
  informational: {
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    icon: 'ℹ',
    label: 'Informational',
  },
  behavioral: {
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '🧠',
    label: 'Behavioral',
  },
  structural: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '📊',
    label: 'Structural',
  },
  algo: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    icon: '⚡',
    label: 'Algo',
  },
};

/**
 * Algo Alert Class Styles
 */
export const ALGO_CLASS_STYLES: Record<AlgoAlertClass, {
  color: string;
  icon: string;
  label: string;
  description: string;
}> = {
  execution_guard: {
    color: '#ef4444',
    icon: '🛡',
    label: 'Guard',
    description: 'Prevent misuse of strategy',
  },
  validity_monitor: {
    color: '#f59e0b',
    icon: '👁',
    label: 'Monitor',
    description: 'Ensure trade still makes sense',
  },
  profit_management: {
    color: '#22c55e',
    icon: '💰',
    label: 'Profit',
    description: 'Exit and profit logic',
  },
};

/**
 * Strategy Type Display Info
 */
export const STRATEGY_TYPE_INFO: Record<StrategyType, {
  label: string;
  intent: string;
  icon: string;
}> = {
  '0dte_tactical': {
    label: '0DTE Tactical',
    intent: 'Fast convexity, tight timing, high gamma',
    icon: '⚡',
  },
  'timewarp': {
    label: 'TimeWarp',
    intent: 'Harvest time + structure stability',
    icon: '⏱',
  },
  'batman': {
    label: 'Batman / Tail',
    intent: 'Extreme asymmetry, rare activation',
    icon: '🦇',
  },
  'convexity_stack': {
    label: 'Convexity Stack',
    intent: 'Layered convex exposure across strikes',
    icon: '📚',
  },
  'gamma_scalping': {
    label: 'Gamma Scalping',
    intent: 'Monetize movement + reversion',
    icon: '🔄',
  },
  'butterfly': {
    label: 'Butterfly',
    intent: 'Balanced risk/reward structure',
    icon: '🦋',
  },
  'vertical': {
    label: 'Vertical',
    intent: 'Directional bias with defined risk',
    icon: '↕',
  },
  'custom': {
    label: 'Custom',
    intent: 'User-defined strategy',
    icon: '⚙',
  },
};

/**
 * Get category style
 */
export function getCategoryStyle(category: AlertCategory) {
  return ALERT_CATEGORY_STYLES[category];
}

/**
 * Get algo class style
 */
export function getAlgoClassStyle(algoClass: AlgoAlertClass) {
  return ALGO_CLASS_STYLES[algoClass];
}

/**
 * Get strategy type info
 */
export function getStrategyTypeInfo(strategyType: StrategyType) {
  return STRATEGY_TYPE_INFO[strategyType];
}

/**
 * Check if alert is an algo alert
 */
export function isAlgoAlert(alert: AlertDefinition | AlgoAlertDefinition): alert is AlgoAlertDefinition {
  return 'category' in alert && alert.category === 'algo';
}

// ==================== ML-Driven Alerts (Trade Tracking ML) ====================

/**
 * ML Alert Category - types of ML-driven insights
 * From ml-driven-alerts.md
 *
 * ML Alerts react to:
 * - What has *actually worked* for this trader
 * - What has *historically failed*
 * - What conditions amplify or destroy edge
 * - When current behavior diverges from learned optimal patterns
 */
export type MLAlertCategory =
  | 'edge_degradation'       // Current conditions outside historically successful regimes
  | 'timing_deviation'       // Entry/exit timing deviates from learned optimal windows
  | 'strategy_misalignment'  // Chosen strategy doesn't match current regime (ML clustering)
  | 'behavioral_drift'       // Trader behavior deviates from success-correlated patterns
  | 'opportunity_amplification'; // Conditions align with historically high-performance patterns

/**
 * ML Finding - output from the ML system consumed by Alert Manager
 * Findings are versioned, time-bounded, confidence-scored, and explainable
 */
export interface MLFinding {
  findingId: string;
  type: MLAlertCategory;
  confidence: number;           // 0.0 - 1.0
  summary: string;              // Human-readable summary
  applicableStrategies?: StrategyType[];
  conditions?: {
    vixBucket?: 'low' | 'medium' | 'high';
    timeOfDay?: 'early' | 'mid' | 'late';
    regime?: 'positive_gex' | 'negative_gex' | 'neutral';
    gammaProfile?: 'long' | 'short' | 'neutral';
    [key: string]: unknown;
  };
  recommendedIntervention?: 'inform' | 'warn' | 'exit_warning' | 'entry_block' | 'review';

  // Metadata
  version: string;
  validFrom: string;
  validUntil?: string;
  sampleSize?: number;          // Number of trades this finding is based on
  statisticalSignificance?: number;
  createdAt: string;
}

/**
 * ML Alert Definition - extends base AlertDefinition for ML-driven alerts
 * These are evidence-based, probabilistic, and personalized
 */
export interface MLAlertDefinition {
  // Inherits all AlertDefinition fields
  id: string;
  userId: number;
  prompt: string;           // Vexy-generated narrative
  title?: string;

  // ML-specific fields
  category: 'ml';           // Distinguishes from 'algo'
  mlCategory: MLAlertCategory;
  finding: MLFinding;       // The underlying ML finding

  // Historical context
  historicalContext?: {
    winRate?: number;         // Historical win rate for this pattern
    avgReturn?: number;       // Average return
    sampleSize?: number;      // Number of historical trades
    lastOccurrence?: string;  // When this pattern last appeared
    outcomeDistribution?: {   // Distribution of outcomes
      profitable: number;
      breakeven: number;
      loss: number;
    };
  };

  // Vexy interpretation
  vexyNarrative?: string;     // Vexy's human-friendly explanation
  vexyConfidence?: number;    // Vexy's confidence in recommendation

  // Override tracking (for learning loop)
  wasOverridden?: boolean;
  overrideReason?: string;
  overrideOutcome?: 'validated' | 'regretted' | 'pending';

  // Standard fields
  scope: AlertScope;
  severity: AlertSeverity;
  status: AlertStatus;
  lifecycleStage: AlertLifecycleStage;
  bindingState: AlertBindingState;
  bindingPolicy: AlertBindingPolicy;
  targetRef: AlertTargetRef;
  cooldownSeconds: number;
  budgetClass: AlertBudgetClass;
  createdAt: string;
  updatedAt: string;
  lastTriggeredAt?: string;
  triggerCount: number;
}

/**
 * ML Alert Category Styles
 */
export const ML_ALERT_CATEGORY_STYLES: Record<MLAlertCategory, {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
  description: string;
}> = {
  edge_degradation: {
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    icon: '📉',
    label: 'Edge Degradation',
    description: 'Current conditions fall outside historically successful regimes',
  },
  timing_deviation: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '⏰',
    label: 'Timing Deviation',
    description: 'Entry/exit timing deviates from learned optimal windows',
  },
  strategy_misalignment: {
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '🎯',
    label: 'Strategy Misalignment',
    description: 'Chosen strategy does not match current regime',
  },
  behavioral_drift: {
    color: '#ec4899',
    bgColor: 'rgba(236, 72, 153, 0.15)',
    icon: '🧠',
    label: 'Behavioral Drift',
    description: 'Behavior deviates from success-correlated patterns',
  },
  opportunity_amplification: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    icon: '✨',
    label: 'Opportunity',
    description: 'Conditions align with historically high-performance patterns',
  },
};

/**
 * Get ML alert category style
 */
export function getMLCategoryStyle(category: MLAlertCategory) {
  return ML_ALERT_CATEGORY_STYLES[category];
}

/**
 * Check if alert is an ML alert
 */
export function isMLAlert(alert: AlertDefinition | AlgoAlertDefinition | MLAlertDefinition): alert is MLAlertDefinition {
  return 'category' in alert && alert.category === 'ml';
}

/**
 * Check if ML finding is still valid (not expired)
 */
export function isFindingValid(finding: MLFinding): boolean {
  if (!finding.validUntil) return true;
  return new Date(finding.validUntil) > new Date();
}

/**
 * Get confidence level display for ML findings
 */
export function getMLConfidenceDisplay(confidence: number): {
  level: 'low' | 'medium' | 'high';
  color: string;
  label: string;
} {
  if (confidence >= 0.8) {
    return { level: 'high', color: '#22c55e', label: 'High Confidence' };
  }
  if (confidence >= 0.5) {
    return { level: 'medium', color: '#f59e0b', label: 'Medium Confidence' };
  }
  return { level: 'low', color: '#6b7280', label: 'Low Confidence' };
}

/**
 * Interpreted evaluator type - how the prompt was compiled
 */
export type EvaluatorType =
  | 'threshold'  // Price, time, PnL thresholds
  | 'rule'       // Discipline rules (max loss, position limits)
  | 'workflow'   // Process triggers
  | 'ai'         // AI-powered semantic evaluation
  | 'custom';    // Custom evaluator spec

/**
 * Alert event types for history
 */
export type AlertEventType =
  | 'triggered'
  | 'acknowledged'
  | 'dismissed'
  | 'blocked'
  | 'overridden'
  | 'paused'
  | 'resumed'
  | 'updated'
  | 'created';

/**
 * Target reference - what the alert is bound to
 */
export interface AlertTargetRef {
  positionId?: string;
  symbol?: string;
  portfolioId?: string;
  workflowKey?: string;  // e.g., 'journal_after_close', 'routine_checklist'
}

/**
 * Schedule rules for alert
 */
export interface AlertSchedule {
  activeHours?: { start: string; end: string };  // "09:30", "16:00"
  quietHours?: { start: string; end: string };
  cooldownSeconds?: number;
  maxTriggersPerSession?: number;
  daysOfWeek?: number[];  // 0-6, Sunday = 0
}

/**
 * Alert Definition (v1.1)
 * The canonical, persistent alert object
 * From spec section 6 & 12
 */
export interface AlertDefinition {
  id: string;
  userId: number;
  prompt: string;  // Canonical - the natural language description
  title?: string;

  // Core classification
  scope: AlertScope;
  severity: AlertSeverity;
  status: AlertStatus;
  lifecycleStage: AlertLifecycleStage;

  // Binding model (spec section 5)
  bindingState: AlertBindingState;
  bindingPolicy: AlertBindingPolicy;
  targetRef: AlertTargetRef;

  // Process integration (spec section 10)
  originTool?: string;  // Which tool created this alert
  phase?: ProcessPhase;  // Which FOTW phase

  // Fatigue control (spec section 8)
  cooldownSeconds: number;
  budgetClass: AlertBudgetClass;
  schedule?: AlertSchedule;

  // Timestamps
  createdAt: string;
  updatedAt: string;

  // Current interpretation (latest parsed version)
  currentInterpretation?: AlertInterpretation;

  // Runtime state
  lastTriggeredAt?: string;
  triggerCount: number;
  acknowledgedAt?: string;
  overrideReason?: string;  // If overridden, the reason
}

/**
 * Alert Interpretation - versioned prompt parsing result
 * Allows re-parsing without losing history
 * From spec section 12: alert_interpretations
 */
export interface AlertInterpretation {
  id: string;
  alertId: string;
  parserVersion: string;
  interpretedType: EvaluatorType;
  evaluatorSpec: Record<string, unknown>;  // Compiled evaluator config
  parseConfidence: number;  // 0.0-1.0, confidence in parsing
  createdAt: string;
}

/**
 * Alert Event - history record
 */
export interface AlertEvent {
  id: string;
  userId: number;
  alertId: string;
  eventType: AlertEventType;
  severityAtEvent: AlertSeverity;
  payload: Record<string, unknown>;  // Condition values, context snapshot
  createdAt: string;
}

/**
 * Alert Override - for block overrides
 */
export interface AlertOverride {
  id: string;
  userId: number;
  alertId: string;
  reason: string;  // Required for block overrides
  createdAt: string;
}

/**
 * SSE Event types from spec section 6.2
 */
export type AlertSSEEventType =
  | 'alert_created'
  | 'alert_updated'
  | 'alert_paused'
  | 'alert_triggered'
  | 'alert_acknowledged'
  | 'alert_dismissed'
  | 'alert_blocked'
  | 'alert_override_logged'
  | 'alert_digest';  // From Vexy meta synthesis

// ==================== Legacy Alert Types (v1 - backward compat) ====================

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
  strategyId?: string;
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

// ==================== Alert Manager v2 Styles & Helpers ====================

/**
 * Severity styling configuration
 * From spec section 3.2
 */
export const ALERT_SEVERITY_STYLES: Record<AlertSeverity, {
  color: string;
  bgColor: string;
  borderColor: string;
  icon: string;
  label: string;
}> = {
  inform: {
    color: '#9ca3af',
    bgColor: '#1f2937',
    borderColor: '#374151',
    icon: 'ℹ️',
    label: 'Inform',
  },
  notify: {
    color: '#3b82f6',
    bgColor: '#1e3a5f',
    borderColor: '#2563eb',
    icon: '🔔',
    label: 'Notify',
  },
  warn: {
    color: '#f59e0b',
    bgColor: '#78350f',
    borderColor: '#d97706',
    icon: '⚠️',
    label: 'Warning',
  },
  block: {
    color: '#ef4444',
    bgColor: '#7f1d1d',
    borderColor: '#dc2626',
    icon: '🛑',
    label: 'Block',
  },
};

/**
 * Scope display configuration
 */
export const ALERT_SCOPE_STYLES: Record<AlertScope, {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
}> = {
  position: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    icon: '📊',
    label: 'Position',
  },
  symbol: {
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    icon: '📈',
    label: 'Symbol',
  },
  portfolio: {
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '💼',
    label: 'Portfolio',
  },
  workflow: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '🔄',
    label: 'Workflow',
  },
  behavioral: {
    color: '#ec4899',
    bgColor: 'rgba(236, 72, 153, 0.15)',
    icon: '🧠',
    label: 'Behavioral',
  },
};

/**
 * Get severity style info
 */
export function getSeverityStyle(severity: AlertSeverity) {
  return ALERT_SEVERITY_STYLES[severity];
}

/**
 * Get scope style info
 */
export function getScopeStyle(scope: AlertScope) {
  return ALERT_SCOPE_STYLES[scope];
}

/**
 * Check if severity requires acknowledgment
 */
export function requiresAcknowledgment(severity: AlertSeverity): boolean {
  return severity === 'warn' || severity === 'block';
}

/**
 * Check if severity can block actions
 */
export function canBlockAction(severity: AlertSeverity): boolean {
  return severity === 'block';
}

/**
 * Default cooldown seconds by severity
 */
export const DEFAULT_COOLDOWNS: Record<AlertSeverity, number> = {
  inform: 60,      // 1 minute
  notify: 300,     // 5 minutes
  warn: 600,       // 10 minutes
  block: 0,        // No cooldown for blocks
};

/**
 * Input for creating a new AlertDefinition
 * From spec v1.1 section 12
 */
export interface CreateAlertDefinitionInput {
  prompt: string;
  title?: string;
  scope: AlertScope;
  severity?: AlertSeverity;  // Defaults to 'notify'

  // Binding (optional - defaults to manual/unbound)
  bindingPolicy?: AlertBindingPolicy;
  targetRef?: AlertTargetRef;

  // Process integration
  originTool?: string;
  phase?: ProcessPhase;

  // Fatigue control
  cooldownSeconds?: number;
  budgetClass?: AlertBudgetClass;
  schedule?: AlertSchedule;
}

/**
 * Input for updating an AlertDefinition
 */
export interface UpdateAlertDefinitionInput {
  id: string;
  prompt?: string;
  title?: string;
  scope?: AlertScope;
  severity?: AlertSeverity;
  status?: AlertStatus;
  lifecycleStage?: AlertLifecycleStage;
  bindingPolicy?: AlertBindingPolicy;
  targetRef?: AlertTargetRef;
  phase?: ProcessPhase;
  cooldownSeconds?: number;
  budgetClass?: AlertBudgetClass;
  schedule?: AlertSchedule;
}

/**
 * Lifecycle stage styling configuration
 */
export const ALERT_LIFECYCLE_STYLES: Record<AlertLifecycleStage, {
  color: string;
  bgColor: string;
  icon: string;
  label: string;
}> = {
  created: {
    color: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.15)',
    icon: '◯',
    label: 'Created',
  },
  watching: {
    color: '#3b82f6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    icon: '👁',
    label: 'Watching',
  },
  update: {
    color: '#8b5cf6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '📊',
    label: 'Update',
  },
  warn: {
    color: '#f59e0b',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '⚠',
    label: 'Warning',
  },
  accomplished: {
    color: '#22c55e',
    bgColor: 'rgba(34, 197, 94, 0.15)',
    icon: '✓',
    label: 'Accomplished',
  },
  dismissed: {
    color: '#6b7280',
    bgColor: 'rgba(107, 114, 128, 0.15)',
    icon: '✕',
    label: 'Dismissed',
  },
  overridden: {
    color: '#ef4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    icon: '⚡',
    label: 'Overridden',
  },
};

/**
 * Get lifecycle stage style info
 */
export function getLifecycleStageStyle(stage: AlertLifecycleStage) {
  return ALERT_LIFECYCLE_STYLES[stage];
}

/**
 * Check if lifecycle stage is terminal
 */
export function isTerminalStage(stage: AlertLifecycleStage): boolean {
  return stage === 'accomplished' || stage === 'dismissed' || stage === 'overridden';
}

/**
 * Check if lifecycle stage requires attention
 */
export function requiresAttention(stage: AlertLifecycleStage): boolean {
  return stage === 'update' || stage === 'warn';
}
