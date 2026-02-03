/**
 * VexyAdvisorWidget - Tabbed widget for Vexy AI commentary and AI Advisor.
 *
 * Two tabs:
 * - Vexy: Scrollable list of all session messages (epochs and events)
 * - Advisor: AI-driven trading suggestions based on VIX regime and positions
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { marked } from 'marked';

// Types
interface VexyMessage {
  kind: 'epoch' | 'event';
  text: string;
  ts: string;
  voice?: string;
  meta?: {
    epoch_name?: string;
    [key: string]: unknown;
  };
}

interface RiskGraphAlert {
  id: string;
  enabled: boolean;
  type: string;
  strategyId: string;
  entryDebit?: number;
}

interface RiskGraphStrategy {
  id: string;
  strike: number;
  width?: number;
  debit?: number;
}

interface VexyAdvisorWidgetProps {
  messages: VexyMessage[];
  vixValue: number | null;
  riskGraphAlerts?: RiskGraphAlert[];
  riskGraphStrategies?: RiskGraphStrategy[];
  effectiveSpot?: number | null;
  timeMachineEnabled?: boolean;
  simVolatilityOffset?: number;
  simTimeOffsetHours?: number;
  calculateStrategyTheoreticalPnL?: (
    strategy: RiskGraphStrategy,
    spot: number,
    volatility: number,
    rate: number,
    timeOffset: number
  ) => number;
  isAdmin?: boolean;
  onClearMessages?: () => void;
}

// Configure marked for inline rendering
marked.setOptions({
  breaks: true,
  gfm: true,
});

// Markdown renderer using marked
function MarkdownText({ content }: { content: string }) {
  const html = useMemo(() => {
    if (!content) return '';
    try {
      return marked.parse(content) as string;
    } catch {
      return content;
    }
  }, [content]);

  return <div className="vexy-md" dangerouslySetInnerHTML={{ __html: html }} />;
}

// Format timestamp for display
function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function VexyAdvisorWidget({
  messages,
  vixValue,
  riskGraphAlerts = [],
  riskGraphStrategies = [],
  effectiveSpot,
  timeMachineEnabled = false,
  simVolatilityOffset = 0,
  simTimeOffsetHours = 0,
  calculateStrategyTheoreticalPnL,
  isAdmin = false,
  onClearMessages,
}: VexyAdvisorWidgetProps) {
  const [activeTab, setActiveTab] = useState<'vexy' | 'advisor'>('vexy');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest message when new messages arrive
  useEffect(() => {
    if (activeTab === 'vexy') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab]);

  // AI Advisor logic
  const renderAdvisorContent = () => {
    const vix = vixValue || 20;
    const currentHour = new Date().getHours();
    const currentMinute = new Date().getMinutes();
    const isAfternoon = currentHour >= 14;
    const timeString = `${currentHour}:${currentMinute.toString().padStart(2, '0')}`;

    const marketCloseHour = 16;
    const hoursToClose = Math.max(0, marketCloseHour - currentHour - currentMinute / 60);

    const activeAlerts = riskGraphAlerts.filter(a => a.enabled && a.type === 'ai_theta_gamma');

    const isZombieland = vix <= 17;
    const isGoldilocks = vix > 17 && vix <= 32;
    const isChaos = vix > 32;
    const isBatmanTerritory = vix > 40;
    const isGammaScalpWindow = isZombieland && isAfternoon;
    const isTimeWarp = vix <= 15;

    const commentary: string[] = [];
    let advisorMood: 'neutral' | 'bullish' | 'cautious' | 'alert' = 'neutral';

    if (isBatmanTerritory) {
      commentary.push(`Batman territory at VIX ${vix.toFixed(1)}. Gamma is crushed - bracket spot with wide flies.`);
      advisorMood = 'bullish';
    } else if (isChaos) {
      commentary.push(`Chaos zone. Wide flies cheap, suppressed gamma. Good for asymmetric setups.`);
      advisorMood = 'bullish';
    } else if (isGammaScalpWindow) {
      commentary.push(`Gamma Scalp window OPEN. Look for backstop to sandwich 10-20w fly near spot.`);
      advisorMood = 'bullish';
    } else if (isTimeWarp && !isAfternoon) {
      commentary.push(`TimeWarp. VIX ${vix.toFixed(1)} - go 1-2 DTE, 0 DTE premium gone.`);
      advisorMood = 'cautious';
    } else if (isZombieland) {
      commentary.push(`Zombieland. High gamma - narrow flies, manage carefully.`);
      advisorMood = 'cautious';
    } else if (isGoldilocks) {
      commentary.push(`Goldilocks. Ideal for OTM butterfly utility trades.`);
      advisorMood = 'neutral';
    }

    if (hoursToClose <= 0.5) {
      commentary.push(`Final 30 min. Gamma max. Close or tight stops.`);
      advisorMood = 'alert';
    } else if (hoursToClose <= 1) {
      commentary.push(`Last hour. Protect gains aggressively.`);
      if (advisorMood === 'neutral' || advisorMood === 'bullish') advisorMood = 'cautious';
    }

    if (activeAlerts.length > 0 && effectiveSpot && calculateStrategyTheoreticalPnL) {
      activeAlerts.forEach(alert => {
        const strategy = riskGraphStrategies.find(s => s.id === alert.strategyId);
        if (!strategy) return;

        const entryDebit = alert.entryDebit || strategy.debit || 1;
        const adjustedVix = timeMachineEnabled ? vix + simVolatilityOffset : vix;
        const volatility = Math.max(0.05, adjustedVix) / 100;
        const timeOffset = timeMachineEnabled ? simTimeOffsetHours : 0;

        const pnlAtSpot = calculateStrategyTheoreticalPnL(strategy, effectiveSpot, volatility, 0.05, timeOffset);
        const currentProfit = pnlAtSpot / 100;
        const profitPercent = entryDebit > 0 ? (currentProfit / entryDebit) * 100 : 0;

        const pnlPlus = calculateStrategyTheoreticalPnL(strategy, effectiveSpot + 1, volatility, 0.05, timeOffset);
        const pnlMinus = calculateStrategyTheoreticalPnL(strategy, effectiveSpot - 1, volatility, 0.05, timeOffset);
        const delta = (pnlPlus - pnlMinus) / 200;

        const strategyLabel = `${strategy.strike}${strategy.width ? '/' + strategy.width : ''}`;

        if (profitPercent >= 100) {
          commentary.push(`${strategyLabel}: ${profitPercent.toFixed(0)}% profit${Math.abs(delta) < 0.5 ? ', at peak' : ''}.`);
        } else if (profitPercent >= 50) {
          commentary.push(`${strategyLabel}: ${profitPercent.toFixed(0)}% profit.`);
        } else if (profitPercent > 0) {
          commentary.push(`${strategyLabel}: ${profitPercent.toFixed(0)}% - building.`);
        } else {
          commentary.push(`${strategyLabel}: underwater.`);
          if (advisorMood === 'neutral' || advisorMood === 'bullish') advisorMood = 'cautious';
        }
      });
    }

    if (commentary.length === 0) {
      commentary.push(`VIX ${vix.toFixed(1)}, ${hoursToClose.toFixed(1)}h to close.`);
    }

    return (
      <div className={`ai-advisor-content ${advisorMood}`}>
        <div className="ai-advisor-time">{timeString} ET | {hoursToClose.toFixed(1)}h left</div>
        <div className="ai-advisor-commentary">
          {commentary.map((line, i) => (
            <p key={i} className="ai-commentary-line">{line}</p>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="widget vexy-advisor-widget">
      <div className="widget-tabs">
        <button
          className={`widget-tab ${activeTab === 'vexy' ? 'active' : ''}`}
          onClick={() => setActiveTab('vexy')}
        >
          Vexy {messages.length > 0 && <span className="vexy-count">{messages.length}</span>}
        </button>
        <button
          className={`widget-tab ${activeTab === 'advisor' ? 'active' : ''}`}
          onClick={() => setActiveTab('advisor')}
        >
          Advisor
        </button>
        {isAdmin && messages.length > 0 && (
          <button
            className="vexy-clear-btn"
            onClick={onClearMessages}
            title="Clear all messages"
          >
            Clear
          </button>
        )}
      </div>

      {activeTab === 'vexy' ? (
        <div className="widget-content vexy-content vexy-messages-list">
          {messages.length === 0 ? (
            <div className="vexy-empty">Awaiting commentary...</div>
          ) : (
            messages.map((msg, idx) => (
              <div key={`${msg.ts}-${idx}`} className={`vexy-message vexy-${msg.kind}`}>
                <div className="vexy-message-header">
                  <span className="vexy-icon">{msg.kind === 'epoch' ? '🎙️' : '💥'}</span>
                  <span className="vexy-kind">{msg.kind === 'epoch' ? 'Epoch' : 'Event'}</span>
                  {msg.meta?.epoch_name && (
                    <span className="vexy-epoch-name">{String(msg.meta.epoch_name)}</span>
                  )}
                  <span className="vexy-time">{formatTime(msg.ts)}</span>
                </div>
                <div className="vexy-message-text">
                  <MarkdownText content={msg.text || ''} />
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      ) : (
        renderAdvisorContent()
      )}
    </div>
  );
}
