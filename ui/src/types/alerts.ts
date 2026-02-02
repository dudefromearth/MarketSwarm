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
  | 'price'           // Spot price crosses level
  | 'debit'           // Position debit crosses level
  | 'profit_target'   // Profit reaches target
  | 'trailing_stop'   // Trailing stop triggered
  | 'ai_theta_gamma'  // AI-computed dynamic risk zone
  | 'ai_sentiment'    // AI market sentiment analysis
  | 'ai_risk_zone'    // AI-computed risk boundaries
  | 'time_boundary'   // EOD/EOW/EOM alerts
  | 'trade_closed';   // Trade closed notification

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

// Union type of all alerts
export type Alert =
  | PriceAlert
  | DebitAlert
  | ProfitTargetAlert
  | TrailingStopAlert
  | AIThetaGammaAlert
  | AISentimentAlert
  | AIRiskZoneAlert;

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

export function hasAIReasoning(alert: Alert): boolean {
  return 'aiReasoning' in alert && alert.aiReasoning !== undefined;
}
