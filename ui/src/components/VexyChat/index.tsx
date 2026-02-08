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

interface VexyChatProps {
  isOpen: boolean;
  onClose: () => void;
  userTier?: UserTier;
  context?: VexyFullContext;
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
}: VexyChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reflectionDial, setReflectionDial] = useState(0.6);
  const [remainingMessages, setRemainingMessages] = useState<number | undefined>(undefined);
  const [showSettings, setShowSettings] = useState(false);
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
  }, [reflectionDial, context]);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setShowSettings(false);
  }, []);

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
