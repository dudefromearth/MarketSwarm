/**
 * ObserverPanel - Unified panel for Vexy commentary and alerts
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { marked } from 'marked';

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

// Simple markdown renderer
function Markdown({ text }: { text: string }) {
  const html = useMemo(() => {
    if (!text) return '';
    return marked.parse(text) as string;
  }, [text]);
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
import type { PromptStage } from '../types/alerts';
import { PROMPT_STAGE_STYLES } from '../types/alerts';
import '../styles/prompt-alert.css';

interface ObserverMessage {
  id: string;
  type: 'vexy' | 'alert' | 'prompt_alert';
  kind?: 'epoch' | 'event';  // For vexy messages
  alertType?: string;        // For alerts: 'triggered', 'added', etc.
  promptStage?: PromptStage; // For prompt alerts
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

    const handleVexy = (e: MessageEvent) => {
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
    };

    es.addEventListener('vexy', handleVexy);

    return () => {
      es.removeEventListener('vexy', handleVexy);
      es.close();
    };
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

    const handleTriggered = (e: MessageEvent) => {
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
    };

    const handleAdded = (e: MessageEvent) => {
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
    };

    const handlePromptStage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const stage = data.stage as PromptStage;
        const stageInfo = PROMPT_STAGE_STYLES[stage];
        const msg: ObserverMessage = {
          id: `prompt-${data.alertId}-${Date.now()}`,
          type: 'prompt_alert',
          promptStage: stage,
          text: data.reasoning || `Stage changed to ${stageInfo.label}`,
          ts: data.timestamp || new Date().toISOString(),
          meta: {
            alertId: data.alertId,
            stage: data.stage,
            confidence: data.confidence,
            reasoning: data.reasoning,
          },
        };
        setMessages((prev) => [...prev, msg].slice(-100));
      } catch (err) {
        console.error('[Observer] Prompt alert parse error', err);
      }
    };

    es.addEventListener('alert_triggered', handleTriggered);
    es.addEventListener('alert_added', handleAdded);
    es.addEventListener('prompt_alert_stage_change', handlePromptStage);

    return () => {
      es.removeEventListener('alert_triggered', handleTriggered);
      es.removeEventListener('alert_added', handleAdded);
      es.removeEventListener('prompt_alert_stage_change', handlePromptStage);
      es.close();
    };
  }, []);

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const getIcon = (msg: ObserverMessage) => {
    if (msg.type === 'prompt_alert' && msg.promptStage) {
      return PROMPT_STAGE_STYLES[msg.promptStage].icon;
    }
    if (msg.type === 'alert') {
      return msg.alertType === 'triggered' ? '🔔' : '➕';
    }
    return msg.kind === 'epoch' ? '🎙️' : '💥';
  };

  const getPromptStageClass = (stage?: PromptStage) => {
    if (!stage) return '';
    return `prompt-stage-${stage}`;
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
            className={`commentary-msg commentary-${msg.type === 'alert' ? 'alert' : msg.type === 'prompt_alert' ? 'prompt-alert' : msg.kind} ${msg.type === 'prompt_alert' ? getPromptStageClass(msg.promptStage) : ''}`}
          >
            <div className="commentary-msg-header">
              <span className="commentary-category-icon">{getIcon(msg)}</span>
              {msg.type === 'vexy' && msg.meta?.epoch && (
                <span className="commentary-epoch-label">{String(msg.meta.epoch)}</span>
              )}
              {msg.type === 'alert' && (
                <span className="commentary-alert-label">Alert</span>
              )}
              {msg.type === 'prompt_alert' && msg.promptStage && (
                <span className={`prompt-stage-badge ${msg.promptStage}`}>
                  {PROMPT_STAGE_STYLES[msg.promptStage].label}
                </span>
              )}
              <span className="commentary-time">{formatTime(msg.ts)}</span>
            </div>
            <div className="commentary-text"><Markdown text={msg.text} /></div>
            {msg.type === 'prompt_alert' && msg.meta?.confidence != null && (
              <div className="observer-prompt-meta">
                <div className="observer-prompt-confidence">
                  <span>Confidence:</span>
                  <div className="observer-prompt-confidence-bar">
                    <div
                      className="observer-prompt-confidence-fill"
                      style={{ width: `${(msg.meta.confidence as number) * 100}%` }}
                    />
                  </div>
                  <span>{((msg.meta.confidence as number) * 100).toFixed(0)}%</span>
                </div>
              </div>
            )}
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
