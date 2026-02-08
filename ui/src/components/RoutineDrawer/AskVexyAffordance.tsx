/**
 * AskVexyAffordance - Vexy Mode B trigger
 *
 * User-initiated conversational access to Vexy within Routine context.
 * Uses existing /api/vexy/chat endpoint with outlet="routine".
 *
 * Visual: Small "Ask Vexy" text link, no badges, no pulsing
 *
 * Allowed Scopes:
 * - Context recall ("What was VIX yesterday?")
 * - Summarization ("Summarize overnight action")
 * - Clarification ("What does this regime mean?")
 * - Light synthesis
 *
 * Disallowed:
 * - Trade recommendations
 * - Strategy walkthroughs
 * - Optimization language
 * - Urgency
 */

import { useState, useRef, useEffect } from 'react';
import { marked } from 'marked';

interface AskVexyAffordanceProps {
  isOpen: boolean;
  contextPhase?: string;
  onOpenChange?: (isOpen: boolean) => void;
}

interface ChatResponse {
  response: string;
  agent?: string;
  tokens_used: number;
  remaining_today: number;
}

export default function AskVexyAffordance({
  isOpen: drawerOpen,
  contextPhase,
  onOpenChange,
}: AskVexyAffordanceProps) {
  const [expanded, setExpanded] = useState(false);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when expanded
  useEffect(() => {
    if (expanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [expanded]);

  // Close when drawer closes
  useEffect(() => {
    if (!drawerOpen) {
      setExpanded(false);
      setMessage('');
      setResponse(null);
      setError(null);
    }
  }, [drawerOpen]);

  const handleToggle = () => {
    const newState = !expanded;
    setExpanded(newState);
    onOpenChange?.(newState);

    if (!newState) {
      setMessage('');
      setResponse(null);
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!message.trim() || loading) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const payload = {
        message: message.trim(),
        outlet: 'routine',
        mode: 'ask_vexy',
        routine_context_phase: contextPhase || 'weekday_premarket',
        constraints: { no_trade_advice: true },
      };

      const res = await fetch('/api/vexy/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        if (res.status === 429) {
          throw new Error('Daily message limit reached');
        }
        throw new Error(`Request failed: ${res.status}`);
      }

      const data: ChatResponse = await res.json();
      setResponse(data.response);
      setMessage('');
    } catch (err) {
      console.error('[AskVexy] Error:', err);
      setError(err instanceof Error ? err.message : 'Unable to reach Vexy');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleToggle();
    }
  };

  // Render response as markdown
  const renderResponse = (text: string) => {
    const html = marked.parse(text) as string;
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  if (!expanded) {
    return (
      <div className="ask-vexy-affordance">
        <button
          type="button"
          className="ask-vexy-trigger"
          onClick={handleToggle}
        >
          Ask Vexy
        </button>
      </div>
    );
  }

  return (
    <div className="ask-vexy-affordance expanded">
      <div className="ask-vexy-header">
        <span className="ask-vexy-title">Ask Vexy</span>
        <button
          type="button"
          className="ask-vexy-close"
          onClick={handleToggle}
        >
          ×
        </button>
      </div>

      {response && (
        <div className="ask-vexy-response">
          {renderResponse(response)}
        </div>
      )}

      {error && (
        <div className="ask-vexy-error">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="ask-vexy-form">
        <input
          ref={inputRef}
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What's on your mind?"
          className="ask-vexy-input"
          disabled={loading}
        />
        <button
          type="submit"
          className="ask-vexy-submit"
          disabled={!message.trim() || loading}
        >
          {loading ? '...' : '→'}
        </button>
      </form>

      <div className="ask-vexy-hint">
        Context recall, clarification, light synthesis only.
      </div>
    </div>
  );
}
