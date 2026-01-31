/**
 * CommentaryPanel - AI market commentary display (Vexy).
 *
 * One-way contextual observations. The AI observes and comments,
 * users do not interact. Uses SSE for real-time updates.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

interface VexyMessage {
  kind: 'epoch' | 'event';
  text: string;
  ts: string;
  voice: string;
  meta?: {
    epoch?: string;
    type?: string;
    [key: string]: unknown;
  };
}

interface CommentaryPanelProps {
  sseUrl?: string;
  maxMessages?: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function CommentaryPanel({
  sseUrl = '/sse/vexy',
  maxMessages = 50,
  collapsed = false,
  onToggleCollapse,
}: CommentaryPanelProps) {
  const [messages, setMessages] = useState<VexyMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll to latest message
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // SSE connection
  useEffect(() => {
    const connect = () => {
      // Use full URL for SSE endpoint
      const baseUrl = import.meta.env.VITE_SSE_URL || 'http://localhost:8085';
      const fullUrl = `${baseUrl}${sseUrl}`;

      const eventSource = new EventSource(fullUrl);

      eventSource.onopen = () => {
        setConnected(true);
        console.log('Vexy SSE connected');
      };

      eventSource.onerror = () => {
        setConnected(false);
        console.log('Vexy SSE disconnected, reconnecting...');
        eventSource.close();
        // Reconnect after delay
        setTimeout(connect, 5000);
      };

      // Handle connection confirmation
      eventSource.addEventListener('connected', (event) => {
        console.log('Vexy SSE channel connected:', JSON.parse(event.data));
      });

      // Handle initial history (all today's messages)
      eventSource.addEventListener('vexy_history', (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.messages && Array.isArray(data.messages)) {
            setMessages(data.messages.slice(-maxMessages));
          }
        } catch (e) {
          console.error('Failed to parse vexy_history:', e);
        }
      });

      // Handle new messages
      eventSource.addEventListener('vexy_message', (event) => {
        try {
          const message = JSON.parse(event.data) as VexyMessage;
          setMessages((prev) => {
            const updated = [...prev, message];
            return updated.slice(-maxMessages);
          });
        } catch (e) {
          console.error('Failed to parse vexy_message:', e);
        }
      });

      eventSourceRef.current = eventSource;
    };

    connect();

    return () => {
      eventSourceRef.current?.close();
    };
  }, [sseUrl, maxMessages]);

  const toggleEnabled = () => {
    setEnabled((prev) => !prev);
  };

  const getKindIcon = (kind: string): string => {
    switch (kind) {
      case 'epoch':
        return '🎙️';
      case 'event':
        return '💥';
      default:
        return '○';
    }
  };

  const getKindClass = (kind: string): string => {
    return `commentary-msg commentary-${kind}`;
  };

  const formatTime = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getEpochLabel = (msg: VexyMessage): string | null => {
    if (msg.kind === 'epoch' && msg.meta?.epoch) {
      return msg.meta.epoch as string;
    }
    return null;
  };

  if (collapsed) {
    return (
      <div className="commentary-panel-collapsed" onClick={onToggleCollapse}>
        <span className="commentary-expand-icon">🎙️</span>
        <span className="commentary-expand-label">Vexy</span>
        {messages.length > 0 && (
          <span className="commentary-unread-badge">{messages.length}</span>
        )}
      </div>
    );
  }

  return (
    <div className="commentary-panel">
      <div className="commentary-header">
        <div className="commentary-title">
          <span className="commentary-icon">🎙️</span>
          <span>Vexy</span>
          <span className={`commentary-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '●' : '○'}
          </span>
        </div>
        <div className="commentary-controls">
          <button
            className={`commentary-toggle ${enabled ? 'enabled' : 'disabled'}`}
            onClick={toggleEnabled}
            title={enabled ? 'Disable commentary' : 'Enable commentary'}
          >
            {enabled ? 'ON' : 'OFF'}
          </button>
          {onToggleCollapse && (
            <button className="commentary-collapse-btn" onClick={onToggleCollapse}>
              −
            </button>
          )}
        </div>
      </div>

      <div className="commentary-messages">
        {!connected && (
          <div className="commentary-offline">
            Connecting to commentary service...
          </div>
        )}

        {connected && !enabled && (
          <div className="commentary-disabled">
            Commentary is disabled
          </div>
        )}

        {connected && enabled && messages.length === 0 && (
          <div className="commentary-empty">
            Waiting for market observations...
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={`${msg.ts}-${idx}`} className={getKindClass(msg.kind)}>
            <div className="commentary-msg-header">
              <span className="commentary-category-icon">
                {getKindIcon(msg.kind)}
              </span>
              {getEpochLabel(msg) && (
                <span className="commentary-epoch-label">{getEpochLabel(msg)}</span>
              )}
              <span className="commentary-time">{formatTime(msg.ts)}</span>
            </div>
            <div className="commentary-text">{msg.text}</div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      <div className="commentary-footer">
        <span className="commentary-mode">{messages.length} messages today</span>
      </div>
    </div>
  );
}
