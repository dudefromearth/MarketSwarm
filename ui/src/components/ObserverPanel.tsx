/**
 * ObserverPanel - Unified panel for Vexy commentary and alerts
 */

import { useState, useEffect, useRef } from 'react';

interface ObserverMessage {
  id: string;
  type: 'vexy' | 'alert';
  kind?: 'epoch' | 'event';  // For vexy messages
  alertType?: string;        // For alerts: 'triggered', 'added', etc.
  text: string;
  ts: string;
  meta?: Record<string, unknown>;
}

export default function ObserverPanel() {
  const [messages, setMessages] = useState<ObserverMessage[]>([]);
  const [vexyConnected, setVexyConnected] = useState(false);
  const [alertsConnected, setAlertsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Vexy SSE connection
  useEffect(() => {
    console.log('[Observer] Connecting to Vexy...');
    const es = new EventSource('/sse/vexy', { withCredentials: true });

    es.onopen = () => {
      setVexyConnected(true);
      console.log('[Observer] Vexy connected');
    };

    es.onerror = () => {
      setVexyConnected(false);
      console.log('[Observer] Vexy error');
    };

    es.addEventListener('vexy', (e) => {
      try {
        const data = JSON.parse(e.data);
        const newMsgs: ObserverMessage[] = [];

        if (data.epoch) {
          newMsgs.push({
            id: `vexy-${data.epoch.ts}`,
            type: 'vexy',
            kind: 'epoch',
            text: data.epoch.text,
            ts: data.epoch.ts,
            meta: data.epoch.meta,
          });
        }
        if (data.event) {
          newMsgs.push({
            id: `vexy-${data.event.ts}`,
            type: 'vexy',
            kind: 'event',
            text: data.event.text,
            ts: data.event.ts,
            meta: data.event.meta,
          });
        }

        if (newMsgs.length > 0) {
          setMessages((prev) => {
            const existing = new Set(prev.map(m => m.id));
            const toAdd = newMsgs.filter(m => !existing.has(m.id));
            if (toAdd.length === 0) return prev;
            return [...prev, ...toAdd].slice(-100);
          });
        }
      } catch (err) {
        console.error('[Observer] Vexy parse error', err);
      }
    });

    return () => es.close();
  }, []);

  // Alerts SSE connection
  useEffect(() => {
    console.log('[Observer] Connecting to Alerts...');
    const es = new EventSource('/sse/alerts', { withCredentials: true });

    es.onopen = () => {
      setAlertsConnected(true);
      console.log('[Observer] Alerts connected');
    };

    es.onerror = () => {
      setAlertsConnected(false);
      console.log('[Observer] Alerts error');
    };

    es.addEventListener('alert_triggered', (e) => {
      try {
        const data = JSON.parse(e.data);
        const msg: ObserverMessage = {
          id: `alert-${data.id}-${Date.now()}`,
          type: 'alert',
          alertType: 'triggered',
          text: data.message || `Alert triggered: ${data.label || data.id}`,
          ts: new Date().toISOString(),
          meta: data,
        };
        setMessages((prev) => [...prev, msg].slice(-100));
      } catch (err) {
        console.error('[Observer] Alert parse error', err);
      }
    });

    es.addEventListener('alert_added', (e) => {
      try {
        const data = JSON.parse(e.data);
        const msg: ObserverMessage = {
          id: `alert-added-${data.id}-${Date.now()}`,
          type: 'alert',
          alertType: 'added',
          text: `Alert created: ${data.label || data.id}`,
          ts: new Date().toISOString(),
          meta: data,
        };
        setMessages((prev) => [...prev, msg].slice(-100));
      } catch (err) {
        console.error('[Observer] Alert parse error', err);
      }
    });

    return () => es.close();
  }, []);

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getIcon = (msg: ObserverMessage) => {
    if (msg.type === 'alert') {
      return msg.alertType === 'triggered' ? '🔔' : '➕';
    }
    return msg.kind === 'epoch' ? '🎙️' : '💥';
  };

  const connected = vexyConnected || alertsConnected;

  return (
    <div className="commentary-panel">
      <div className="commentary-header">
        <div className="commentary-title">
          <span className="commentary-icon">👁️</span>
          <span>Observer</span>
          <span className={`commentary-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '●' : '○'}
          </span>
        </div>
        <div className="commentary-controls">
          <button
            className="commentary-clear-btn"
            onClick={() => setMessages([])}
            title="Clear"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="commentary-messages">
        {!connected && <div className="commentary-offline">Connecting...</div>}
        {connected && messages.length === 0 && (
          <div className="commentary-empty">Waiting for observations...</div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`commentary-msg commentary-${msg.type === 'alert' ? 'alert' : msg.kind}`}
          >
            <div className="commentary-msg-header">
              <span className="commentary-category-icon">{getIcon(msg)}</span>
              {msg.type === 'vexy' && msg.meta?.epoch && (
                <span className="commentary-epoch-label">{String(msg.meta.epoch)}</span>
              )}
              {msg.type === 'alert' && (
                <span className="commentary-alert-label">Alert</span>
              )}
              <span className="commentary-time">{formatTime(msg.ts)}</span>
            </div>
            <div className="commentary-text">{msg.text}</div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="commentary-footer">
        <span className="commentary-mode">{messages.length} messages</span>
      </div>
    </div>
  );
}
