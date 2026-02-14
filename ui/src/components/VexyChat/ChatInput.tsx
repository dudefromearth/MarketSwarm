/**
 * ChatInput - Message input component with reflection dial
 *
 * Handles text input, send button, and reflection dial slider
 * for Navigator+ tiers.
 */

import { useState, useRef, useEffect, type KeyboardEvent, type ChangeEvent } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  reflectionDial?: number;
  onReflectionDialChange?: (value: number) => void;
  showReflectionDial?: boolean;
  remainingMessages?: number;
  hourlyLimit?: number;
}

export default function ChatInput({
  onSend,
  disabled = false,
  reflectionDial = 0.6,
  onReflectionDialChange,
  showReflectionDial = false,
  remainingMessages,
  hourlyLimit,
}: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 100)}px`;
    }
  }, [message]);

  const handleSend = () => {
    const trimmed = message.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.focus();
      }
    }
  };

  // Re-focus textarea when disabled clears (response finished)
  const prevDisabled = useRef(disabled);
  useEffect(() => {
    if (prevDisabled.current && !disabled) {
      textareaRef.current?.focus();
    }
    prevDisabled.current = disabled;
  }, [disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
  };

  const handleDialChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value);
    onReflectionDialChange?.(value);
  };

  const isExhausted = remainingMessages !== undefined && remainingMessages <= 0;
  const isLimited = remainingMessages !== undefined && hourlyLimit !== undefined && hourlyLimit > 0;

  return (
    <div className="vexy-chat-input-area">
      <div className="vexy-chat-input-row">
        <div className="vexy-chat-input-wrapper">
          <textarea
            ref={textareaRef}
            className="vexy-chat-input"
            value={message}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isExhausted ? 'Rate limit reached — try again shortly' : 'Type a message...'}
            disabled={disabled || isExhausted}
            rows={1}
          />
        </div>
        <button
          className="vexy-chat-send-btn"
          onClick={handleSend}
          disabled={disabled || !message.trim() || isExhausted}
          title="Send message"
        >
          ➤
        </button>
      </div>

      {showReflectionDial && (
        <div className="vexy-reflection-dial">
          <span className="vexy-dial-label">Reflection</span>
          <input
            type="range"
            className="vexy-dial-slider"
            min="0.3"
            max="0.9"
            step="0.1"
            value={reflectionDial}
            onChange={handleDialChange}
          />
          <span className="vexy-dial-value">{reflectionDial.toFixed(1)}</span>
        </div>
      )}

      {isLimited && (
        <div className={`vexy-rate-limit ${isExhausted ? 'exhausted' : ''}`}>
          <span>
            {isExhausted
              ? 'Rate limit reached — try again shortly'
              : `${remainingMessages} of ${hourlyLimit} messages remaining this hour`}
          </span>
        </div>
      )}
    </div>
  );
}
