/**
 * VexyChat - Direct Vexy Chat Interface
 *
 * Transforms the PathIndicator butterfly into a conversational
 * chat panel. Vexy is the AI engine running on The Path OS.
 *
 * Features:
 * - Tiered access based on subscription level
 * - Echo Memory integration for cross-session continuity
 * - Reflection dial for depth control (Navigator+)
 * - Rate limiting per tier
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import './VexyChat.css';
import ChatMessage, { type Message } from './ChatMessage';
import ChatInput from './ChatInput';
import TierBadge, { type UserTier } from './TierBadge';
import { type VexyFullContext, formatContextForApi } from '../../hooks/useVexyContext';

interface UserProfile {
  display_name?: string;
  user_id?: number;
  is_admin?: boolean;
}

interface VexyChatProps {
  isOpen: boolean;
  onClose: () => void;
  userTier?: UserTier;
  context?: VexyFullContext;
  userProfile?: UserProfile;
}

/**
 * Format context data for clipboard (readable by external AI chatbots)
 */
function formatContextForClipboard(
  context: VexyFullContext | undefined,
  userProfile: UserProfile | undefined
): string {
  const lines: string[] = [];
  const timestamp = new Date().toLocaleString('en-US', {
    timeZone: 'America/New_York',
    dateStyle: 'short',
    timeStyle: 'short',
  });

  lines.push(`# FOTW Trading Context (${timestamp} ET)`);
  lines.push('');

  // User
  if (userProfile?.display_name) {
    lines.push(`## Trader: ${userProfile.display_name}`);
    lines.push('');
  }

  // Market
  if (context?.market) {
    const m = context.market;
    const marketParts: string[] = [];

    if (m.spxPrice) {
      let spxStr = `SPX: ${m.spxPrice.toFixed(2)}`;
      if (m.spxChangePercent) spxStr += ` (${m.spxChangePercent >= 0 ? '+' : ''}${m.spxChangePercent.toFixed(2)}%)`;
      marketParts.push(spxStr);
    }
    if (m.vixLevel) {
      let vixStr = `VIX: ${m.vixLevel.toFixed(1)}`;
      if (m.vixRegime) vixStr += ` (${m.vixRegime})`;
      marketParts.push(vixStr);
    }
    if (m.marketMode) {
      marketParts.push(`Mode: ${m.marketMode}`);
    }
    if (m.directionalStrength !== null && m.directionalStrength !== undefined) {
      const bias = m.directionalStrength > 0.3 ? 'Bullish' :
                   m.directionalStrength < -0.3 ? 'Bearish' : 'Neutral';
      marketParts.push(`Bias: ${bias}`);
    }

    if (marketParts.length > 0) {
      lines.push('## Market Context');
      lines.push(marketParts.join(' | '));
      lines.push('');
    }
  }

  // Positions
  if (context?.positions && context.positions.length > 0) {
    lines.push('## Open Positions');
    for (const pos of context.positions.slice(0, 10)) {
      let posLine = `- ${pos.type || 'Position'}`;
      if (pos.direction) posLine += ` (${pos.direction})`;
      if (pos.symbol) posLine += ` ${pos.symbol}`;
      if (pos.strikes && pos.strikes.length > 0) {
        posLine += ` @ ${pos.strikes.slice(0, 3).join('/')}`;
      }
      if (pos.daysToExpiry !== undefined) posLine += ` [${pos.daysToExpiry}d]`;
      if (pos.pnl !== undefined) {
        posLine += `: $${pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(0)}`;
        if (pos.pnlPercent !== undefined) {
          posLine += ` (${pos.pnlPercent >= 0 ? '+' : ''}${pos.pnlPercent.toFixed(1)}%)`;
        }
      }
      lines.push(posLine);
    }
    lines.push('');
  }

  // Trading Activity
  if (context?.trading) {
    const t = context.trading;
    const tradeParts: string[] = [];

    if (t.openTrades) tradeParts.push(`Open: ${t.openTrades}`);
    if (t.closedTrades) tradeParts.push(`Closed: ${t.closedTrades}`);
    if (t.todayTrades) tradeParts.push(`Today: ${t.todayTrades}`);
    if (t.winRate !== undefined) {
      const wr = t.winRate <= 1 ? (t.winRate * 100).toFixed(0) : t.winRate.toFixed(0);
      tradeParts.push(`Win Rate: ${wr}%`);
    }
    if (t.todayPnl !== undefined) {
      tradeParts.push(`Today P&L: $${t.todayPnl >= 0 ? '+' : ''}${t.todayPnl.toFixed(0)}`);
    }
    if (t.weekPnl !== undefined) {
      tradeParts.push(`Week P&L: $${t.weekPnl >= 0 ? '+' : ''}${t.weekPnl.toFixed(0)}`);
    }

    if (tradeParts.length > 0) {
      lines.push('## Trading Activity');
      lines.push(tradeParts.join(' | '));
      lines.push('');
    }
  }

  // Risk Graph
  if (context?.risk && context.risk.strategiesOnGraph) {
    const r = context.risk;
    const riskParts: string[] = [];

    riskParts.push(`Strategies: ${r.strategiesOnGraph}`);
    if (r.totalMaxProfit !== undefined) {
      riskParts.push(`Max Profit: $${r.totalMaxProfit >= 0 ? '+' : ''}${r.totalMaxProfit.toFixed(0)}`);
    }
    if (r.totalMaxLoss !== undefined) {
      riskParts.push(`Max Loss: $${r.totalMaxLoss.toFixed(0)}`);
    }
    if (r.breakevenPoints && r.breakevenPoints.length > 0) {
      riskParts.push(`Breakevens: ${r.breakevenPoints.slice(0, 3).join(', ')}`);
    }

    lines.push('## Risk Graph');
    lines.push(riskParts.join(' | '));
    lines.push('');
  }

  // Alerts
  if (context?.alerts && (context.alerts.armed > 0 || context.alerts.triggered > 0)) {
    const a = context.alerts;
    const alertParts: string[] = [];

    if (a.armed) alertParts.push(`Armed: ${a.armed}`);
    if (a.triggered) alertParts.push(`Triggered: ${a.triggered}`);

    lines.push('## Alerts');
    lines.push(alertParts.join(' | '));

    if (a.recentTriggers && a.recentTriggers.length > 0) {
      for (const trigger of a.recentTriggers.slice(0, 3)) {
        lines.push(`- ${trigger.type}: ${trigger.message} (${trigger.triggeredAt})`);
      }
    }
    lines.push('');
  }

  // Footer
  lines.push('---');
  lines.push('*Context from FOTW MarketSwarm*');

  return lines.join('\n');
}

// Tier configuration for client-side
const TIER_CONFIG: Record<UserTier, {
  dailyLimit: number;
  echoEnabled: boolean;
  showReflectionDial: boolean;
  reflectionDialMax: number;
}> = {
  observer: {
    dailyLimit: 5,
    echoEnabled: false,
    showReflectionDial: false,
    reflectionDialMax: 0.5,
  },
  activator: {
    dailyLimit: 25,
    echoEnabled: true,
    showReflectionDial: false,
    reflectionDialMax: 0.6,
  },
  navigator: {
    dailyLimit: 100,
    echoEnabled: true,
    showReflectionDial: true,
    reflectionDialMax: 0.9,
  },
  coaching: {
    dailyLimit: 100,
    echoEnabled: true,
    showReflectionDial: true,
    reflectionDialMax: 0.9,
  },
  administrator: {
    dailyLimit: -1, // Unlimited
    echoEnabled: true,
    showReflectionDial: true,
    reflectionDialMax: 1.0,
  },
};

export default function VexyChat({
  isOpen,
  onClose,
  userTier = 'observer',
  context,
  userProfile,
}: VexyChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reflectionDial, setReflectionDial] = useState(0.6);
  const [remainingMessages, setRemainingMessages] = useState<number | undefined>(undefined);
  const [showSettings, setShowSettings] = useState(false);
  const [copied, setCopied] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const tierConfig = TIER_CONFIG[userTier] || TIER_CONFIG.observer;

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Close settings when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setShowSettings(false);
    if (showSettings) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showSettings]);

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/vexy/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          message: content,
          reflection_dial: reflectionDial,
          context: context ? formatContextForApi(context) : {},
          user_profile: userProfile,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed: ${response.status}`);
      }

      const data = await response.json();

      // Add Vexy response
      const vexyMessage: Message = {
        id: `vexy-${Date.now()}`,
        role: 'vexy',
        content: data.response,
        timestamp: new Date(),
        agent: data.agent,
      };
      setMessages(prev => [...prev, vexyMessage]);

      // Update remaining messages
      if (data.remaining_today !== undefined) {
        setRemainingMessages(data.remaining_today);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [reflectionDial, context, userProfile]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setShowSettings(false);
  }, []);

  const copyContext = useCallback(async () => {
    const contextText = formatContextForClipboard(context, userProfile);
    try {
      await navigator.clipboard.writeText(contextText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      // Fallback for older browsers or restricted contexts
      const textarea = document.createElement('textarea');
      textarea.value = contextText;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
    setShowSettings(false);
  }, [context, userProfile]);

  const handleReflectionDialChange = useCallback((value: number) => {
    // Clamp to tier's max
    const clamped = Math.min(value, tierConfig.reflectionDialMax);
    setReflectionDial(clamped);
  }, [tierConfig.reflectionDialMax]);

  return (
    <div className={`vexy-chat-panel ${isOpen ? 'open' : ''}`}>
      {/* Header */}
      <div className="vexy-chat-header">
        <div className="vexy-chat-header-left">
          <div className="vexy-chat-title">
            <span>🦋</span>
            <span>Vexy</span>
          </div>
          <div className="vexy-chat-status">
            <TierBadge tier={userTier} />
            <div className="vexy-echo-status">
              <span className={`vexy-echo-dot ${tierConfig.echoEnabled ? 'active' : ''}`} />
              <span>Echo: {tierConfig.echoEnabled ? 'Active' : 'Inactive'}</span>
            </div>
          </div>
        </div>
        <div className="vexy-chat-header-actions">
          <button
            className="vexy-chat-action-btn"
            onClick={() => onClose()}
            title="Minimize"
          >
            −
          </button>
          <button
            className="vexy-chat-action-btn"
            onClick={(e) => {
              e.stopPropagation();
              setShowSettings(!showSettings);
            }}
            title="Settings"
          >
            ⋮
          </button>
          <button
            className="vexy-chat-action-btn"
            onClick={onClose}
            title="Close"
          >
            ×
          </button>
        </div>

        {/* Settings dropdown */}
        {showSettings && (
          <div className="vexy-settings-menu" onClick={(e) => e.stopPropagation()}>
            <button className="vexy-settings-item" onClick={copyContext}>
              <span className="vexy-settings-item-icon">{copied ? '✓' : '📋'}</span>
              {copied ? 'Copied!' : 'Copy context'}
            </button>
            <button className="vexy-settings-item" onClick={clearHistory}>
              <span className="vexy-settings-item-icon">🗑️</span>
              Clear history
            </button>
          </div>
        )}
      </div>

      {/* Message area */}
      {messages.length === 0 ? (
        <div className="vexy-chat-empty">
          <div className="vexy-chat-empty-icon">🦋</div>
          <div className="vexy-chat-empty-text">
            The mirror awaits.<br />
            Share what's present.
          </div>
        </div>
      ) : (
        <div className="vexy-chat-messages">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          {isLoading && (
            <div className="vexy-typing-indicator">
              <span className="vexy-typing-dot" />
              <span className="vexy-typing-dot" />
              <span className="vexy-typing-dot" />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Error display */}
      {error && (
        <div className="vexy-chat-error">
          <span>{error}</span>
          <button className="vexy-chat-error-retry" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Input area */}
      <ChatInput
        onSend={sendMessage}
        disabled={isLoading}
        reflectionDial={reflectionDial}
        onReflectionDialChange={handleReflectionDialChange}
        showReflectionDial={tierConfig.showReflectionDial}
        remainingMessages={remainingMessages}
        dailyLimit={tierConfig.dailyLimit > 0 ? tierConfig.dailyLimit : undefined}
      />
    </div>
  );
}
