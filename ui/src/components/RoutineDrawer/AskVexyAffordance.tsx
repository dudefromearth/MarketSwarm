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
import DOMPurify from 'dompurify';
import { API, type RoutineContextPhase } from '../../config/api';

interface AskVexyAffordanceProps {
  isOpen: boolean;
  contextPhase?: RoutineContextPhase;
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
}: AskVexyAffordanceProps) {
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset when drawer closes
  useEffect(() => {
    if (!drawerOpen) {
      setMessage('');
      setResponse(null);
      setError(null);
    }
  }, [drawerOpen]);

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

      const res = await fetch(API.vexy.chat, {
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

  const handleClear = () => {
    setResponse(null);
    setError(null);
    inputRef.current?.focus();
  };

  // Render response as sanitized markdown
  const renderResponse = (text: string) => {
    const html = DOMPurify.sanitize(marked.parse(text) as string);
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="ask-vexy-affordance">
      <div className="ask-vexy-header">
        <span className="ask-vexy-title">Ask Vexy</span>
        {response && (
          <button
            type="button"
            className="ask-vexy-clear"
            onClick={handleClear}
            title="Clear"
          >
            ×
          </button>
        )}
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
          placeholder="Ask about context, regimes, structure..."
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
    </div>
  );
}
