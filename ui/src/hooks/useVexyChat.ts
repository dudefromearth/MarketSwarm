/**
 * useVexyChat - Hook for Vexy Chat API integration
 *
 * Handles:
 * - Sending messages to /api/vexy/chat
 * - Streaming responses (SSE)
 * - Rate limit tracking
 * - Error handling
 */

import { useState, useCallback, useRef } from 'react';
import type { Message } from '../components/VexyChat/ChatMessage';
import type { UserTier } from '../components/VexyChat/TierBadge';

interface MarketContext {
  spxPrice?: number | null;
  vixLevel?: number | null;
  gexPosture?: string | null;
  marketMode?: string | null;
}

interface UserProfile {
  display_name?: string;
  user_id?: number;
  is_admin?: boolean;
}

interface ChatResponse {
  response: string;
  agent?: string;
  echo_updated?: boolean;
  tokens_used?: number;
  remaining_today?: number;
}

interface UseVexyChatOptions {
  userTier?: UserTier;
  marketContext?: MarketContext;
  userProfile?: UserProfile;
}

interface UseVexyChatReturn {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  remainingMessages: number | undefined;
  sendMessage: (content: string, reflectionDial?: number) => Promise<void>;
  clearMessages: () => void;
  dismissError: () => void;
}

export function useVexyChat(options: UseVexyChatOptions = {}): UseVexyChatReturn {
  const { marketContext, userProfile } = options;

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remainingMessages, setRemainingMessages] = useState<number | undefined>(undefined);
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (content: string, reflectionDial = 0.6) => {
    if (!content.trim()) return;

    // Abort any pending request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    // Add user message immediately
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
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          message: content,
          reflection_dial: reflectionDial,
          context: {
            market_data: marketContext,
          },
          user_profile: userProfile,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed: ${response.status}`);
      }

      const data: ChatResponse = await response.json();

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
      if (err instanceof Error && err.name === 'AbortError') {
        return; // Request was cancelled
      }
      const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
      setError(errorMessage);
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [marketContext, userProfile]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const dismissError = useCallback(() => {
    setError(null);
  }, []);

  return {
    messages,
    isLoading,
    error,
    remainingMessages,
    sendMessage,
    clearMessages,
    dismissError,
  };
}
