/**
 * ChatMessage - Individual message display component
 *
 * Renders Vexy or user messages with appropriate styling,
 * agent tags, and timestamps.
 */

import { useState } from 'react';
import { marked } from 'marked';

export interface Message {
  id: string;
  role: 'vexy' | 'user';
  content: string;
  timestamp: Date;
  agent?: string;
}

interface ChatMessageProps {
  message: Message;
}

// Configure marked for simple inline rendering
marked.setOptions({
  breaks: true,
  gfm: true,
});

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isVexy = message.role === 'vexy';
  const timeStr = message.timestamp.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });

  // Parse markdown for Vexy messages
  const htmlContent = isVexy
    ? marked.parse(message.content, { async: false }) as string
    : message.content;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className={`vexy-message ${message.role}`}>
      <div className="vexy-message-header">
        {isVexy && <span className="vexy-message-icon">🦋</span>}
        {isVexy && <span>Vexy</span>}
        {isVexy && message.agent && (
          <span className="vexy-message-agent-tag">{message.agent}</span>
        )}
        {!isVexy && <span>You</span>}
        <span className="vexy-message-time">{timeStr}</span>
        {isVexy && (
          <button
            className="vexy-message-copy"
            onClick={handleCopy}
            title="Copy to clipboard"
          >
            {copied ? '✓' : '⧉'}
          </button>
        )}
      </div>
      {isVexy ? (
        <div
          className="vexy-message-content selectable"
          dangerouslySetInnerHTML={{ __html: htmlContent }}
        />
      ) : (
        <div className="vexy-message-content">
          {message.content}
        </div>
      )}
    </div>
  );
}
