/**
 * RoutineBriefing - Vexy's orientation narrative for Routine Mode
 *
 * Fires once when Routine drawer opens.
 * Self-contained - fetches its own context.
 * Renders static narrative - no streaming, no live updates.
 *
 * Rules:
 * - Max 1-2 short paragraphs
 * - No bullet points
 * - No calls to action
 * - No buttons (except refresh)
 * - Silence is acceptable
 */

import { useState, useEffect, useRef } from 'react';
import { marked } from 'marked';
import { usePositionsContext } from '../../contexts/PositionsContext';
import { useAlerts } from '../../contexts/AlertContext';
import type { MarketContext } from './index';

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

interface BriefingResponse {
  briefing_id: string;
  mode: string;
  narrative: string;
  generated_at: string;
  model: string;
}

interface RoutineBriefingProps {
  isOpen: boolean;
  marketContext?: MarketContext;
}

export default function RoutineBriefing({ isOpen, marketContext }: RoutineBriefingProps) {
  const { positions } = usePositionsContext();
  const { alerts } = useAlerts();
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasFetchedRef = useRef(false);
  const lastOpenRef = useRef(false);

  const fetchBriefing = async () => {
    setLoading(true);
    setError(null);

    // Count open positions
    const openPositions = positions.filter(p => p.status === 'open');
    const armedAlerts = alerts.filter(a => a.enabled && !a.triggered);

    try {
      const payload = {
        mode: 'routine',
        timestamp: new Date().toISOString(),
        market_context: {
          spx_value: marketContext?.spxPrice ?? null,
          vix_level: marketContext?.vixLevel ?? null,
        },
        user_context: {},
        open_loops: {
          open_trades: openPositions.length,
          armed_alerts: armedAlerts.length,
        },
      };

      const response = await fetch('/api/vexy/routine-briefing', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch briefing: ${response.status}`);
      }

      const data: BriefingResponse = await response.json();
      setBriefing(data);
    } catch (err) {
      console.error('[RoutineBriefing] Error:', err);
      setError(err instanceof Error ? err.message : 'Failed to load briefing');
    } finally {
      setLoading(false);
    }
  };

  // Fetch when drawer opens (transition from closed to open)
  useEffect(() => {
    if (isOpen && !lastOpenRef.current && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchBriefing();
    }
    lastOpenRef.current = isOpen;
  }, [isOpen]);

  // Reset fetch flag when drawer closes so next open triggers a fresh fetch
  useEffect(() => {
    if (!isOpen) {
      hasFetchedRef.current = false;
    }
  }, [isOpen]);

  const handleRefresh = () => {
    fetchBriefing();
  };

  // Render narrative as markdown
  const renderNarrative = (text: string) => {
    const html = marked.parse(text) as string;
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  // Loading state
  if (loading) {
    return (
      <div className="routine-briefing">
        <div className="routine-briefing-loading">
          <span className="routine-briefing-spinner">◌</span>
          <span>Preparing orientation...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="routine-briefing">
        <div className="routine-briefing-error">
          <span>Unable to load briefing</span>
          <button className="routine-briefing-retry" onClick={handleRefresh}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Silence is first-class - if no briefing, render minimal
  if (!briefing) {
    return null;
  }

  return (
    <div className="routine-briefing">
      <div className="routine-briefing-header">
        <span className="routine-briefing-title">Orientation</span>
        <button
          className="routine-briefing-refresh"
          onClick={handleRefresh}
          title="Refresh briefing"
        >
          ↻
        </button>
      </div>
      <div className="routine-briefing-content">
        {renderNarrative(briefing.narrative)}
      </div>
      <div className="routine-briefing-meta">
        <span>{new Date(briefing.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
    </div>
  );
}
