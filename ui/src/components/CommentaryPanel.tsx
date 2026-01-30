/**
 * CommentaryPanel - AI market commentary display.
 *
 * One-way contextual observations. The AI observes and comments,
 * users do not interact. Commentary is ephemeral and observational.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

interface CommentaryMessage {
  id: string;
  category: 'observation' | 'doctrine' | 'mel_warning' | 'structure' | 'event';
  text: string;
  timestamp: string;
  trigger?: {
    type: string;
    data: Record<string, unknown>;
  };
  metadata?: Record<string, unknown>;
}

interface CommentaryPanelProps {
  wsUrl?: string;
  maxMessages?: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export default function CommentaryPanel({
  wsUrl = 'ws://localhost:8095/ws/commentary',
  maxMessages = 20,
  collapsed = false,
  onToggleCollapse,
}: CommentaryPanelProps) {
  const [messages, setMessages] = useState<CommentaryMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Auto-scroll to latest message
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // WebSocket connection
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnected(true);
        console.log('Commentary WebSocket connected');
      };

      ws.onclose = () => {
        setConnected(false);
        console.log('Commentary WebSocket disconnected');
        // Reconnect after delay
        setTimeout(connect, 5000);
      };

      ws.onerror = (error) => {
        console.error('Commentary WebSocket error:', error);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'init') {
            setEnabled(data.data.enabled);
          } else if (data.type === 'commentary') {
            setMessages((prev) => {
              const updated = [...prev, data.data as CommentaryMessage];
              return updated.slice(-maxMessages);
            });
          } else if (data.type === 'config_update') {
            setEnabled(data.data.enabled);
          } else if (data.type === 'recent') {
            setMessages(data.data.messages);
          }
        } catch (e) {
          console.error('Failed to parse commentary message:', e);
        }
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      wsRef.current?.close();
    };
  }, [wsUrl, maxMessages]);

  // Request recent messages on mount
  useEffect(() => {
    if (connected && wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: 'get_recent', limit: maxMessages }));
    }
  }, [connected, maxMessages]);

  const toggleEnabled = () => {
    if (wsRef.current && connected) {
      wsRef.current.send(JSON.stringify({ type: 'toggle' }));
    }
  };

  const getCategoryIcon = (category: string): string => {
    switch (category) {
      case 'mel_warning':
        return '⚠';
      case 'doctrine':
        return '📖';
      case 'structure':
        return '◆';
      case 'event':
        return '◉';
      default:
        return '○';
    }
  };

  const getCategoryClass = (category: string): string => {
    return `commentary-msg commentary-${category}`;
  };

  const formatTime = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  if (collapsed) {
    return (
      <div className="commentary-panel-collapsed" onClick={onToggleCollapse}>
        <span className="commentary-expand-icon">💬</span>
        <span className="commentary-expand-label">AI Observer</span>
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
          <span className="commentary-icon">💬</span>
          <span>AI Observer</span>
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

        {messages.map((msg) => (
          <div key={msg.id} className={getCategoryClass(msg.category)}>
            <div className="commentary-msg-header">
              <span className="commentary-category-icon">
                {getCategoryIcon(msg.category)}
              </span>
              <span className="commentary-time">{formatTime(msg.timestamp)}</span>
            </div>
            <div className="commentary-text">{msg.text}</div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      <div className="commentary-footer">
        <span className="commentary-mode">one-way • observe only</span>
      </div>
    </div>
  );
}
