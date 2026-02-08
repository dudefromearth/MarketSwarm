/**
 * RoutineBriefing - Vexy Mode A (Orientation)
 *
 * Fires once when Routine drawer opens (after MicroPause).
 * Adapts to RoutineContextPhase.
 *
 * Doctrine:
 * - May be silent (silence is valid)
 * - Never asks questions
 * - Never instructs
 * - Max 1-2 short sentences
 *
 * Rules:
 * - No bullet points
 * - No calls to action
 * - No buttons (except refresh)
 * - Silence is acceptable and expected
 */

import { useState, useEffect, useRef } from 'react';
import { marked } from 'marked';
import type { MarketContext } from './index';

// Configure marked
marked.setOptions({ breaks: true, gfm: true });

interface OrientationResponse {
  orientation: string | null;  // null = silence
  context_phase: string;
  generated_at: string;
}

interface RoutineBriefingProps {
  isOpen: boolean;
  marketContext?: MarketContext;
  onOrientationShown?: () => void;
}

export default function RoutineBriefing({
  isOpen,
  marketContext,
  onOrientationShown,
}: RoutineBriefingProps) {
  const [orientation, setOrientation] = useState<string | null>(null);
  const [contextPhase, setContextPhase] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSilent, setIsSilent] = useState(false);
  const hasFetchedRef = useRef(false);
  const lastOpenRef = useRef(false);

  const fetchOrientation = async () => {
    setLoading(true);
    setError(null);
    setIsSilent(false);

    try {
      const payload = {
        vix_level: marketContext?.vixLevel ?? null,
      };

      const response = await fetch('/api/vexy/routine/orientation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        // If endpoint doesn't exist yet, generate client-side orientation
        if (response.status === 404) {
          generateClientSideOrientation();
          return;
        }
        throw new Error(`Failed to fetch orientation: ${response.status}`);
      }

      const data: OrientationResponse = await response.json();

      if (data.orientation === null) {
        // Silence is valid
        setIsSilent(true);
        setOrientation(null);
      } else {
        setOrientation(data.orientation);
      }

      setContextPhase(data.context_phase);
      onOrientationShown?.();
    } catch (err) {
      console.error('[RoutineBriefing] Error:', err);
      // Fall back to client-side orientation
      generateClientSideOrientation();
    } finally {
      setLoading(false);
    }
  };

  const generateClientSideOrientation = () => {
    // Determine context phase client-side
    const now = new Date();
    const etOptions = { timeZone: 'America/New_York' };
    const etTime = new Date(now.toLocaleString('en-US', etOptions));
    const hour = etTime.getHours();
    const day = etTime.getDay(); // 0=Sunday, 6=Saturday

    let phase = 'weekday_premarket';
    let message: string | null = null;

    // Weekend
    if (day === 0 || day === 6) {
      if (hour < 12) {
        phase = 'weekend_morning';
        const dayName = day === 0 ? 'Sunday' : 'Saturday';
        message = `${dayName}. Markets rest. So can you.`;
      } else if (hour < 17) {
        phase = 'weekend_afternoon';
        message = null; // Silence
      } else {
        phase = 'weekend_evening';
        message = day === 0 ? 'Sunday evening. Monday approaches.' : null;
      }
    }
    // Friday after 4pm
    else if (day === 5 && hour >= 16) {
      phase = 'friday_night';
      message = 'Friday evening. The week closes behind you.';
    }
    // Weekday
    else {
      if (hour < 9.5) {
        phase = 'weekday_premarket';
        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        const dayName = dayNames[day];

        // VIX note
        let vixNote = '';
        if (marketContext?.vixLevel != null) {
          const vix = marketContext.vixLevel;
          if (vix < 13) vixNote = 'Volatility is suppressed.';
          else if (vix < 18) vixNote = 'Volatility is moderate.';
          else if (vix < 25) vixNote = 'Volatility is elevated.';
          else vixNote = 'Volatility is running high.';
        }

        message = `It's ${dayName} morning.${vixNote ? ' ' + vixNote : ''}`;
      } else if (hour < 16) {
        phase = 'weekday_intraday';
        message = 'Markets are open.';
      } else {
        phase = 'weekday_afterhours';
        message = 'Markets have closed for the day.';
      }
    }

    // Random chance of silence (30%)
    if (Math.random() < 0.3) {
      message = null;
    }

    setContextPhase(phase);
    if (message === null) {
      setIsSilent(true);
      setOrientation(null);
    } else {
      setOrientation(message);
    }

    onOrientationShown?.();
  };

  // Fetch when drawer opens (transition from closed to open)
  useEffect(() => {
    if (isOpen && !lastOpenRef.current && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchOrientation();
    }
    lastOpenRef.current = isOpen;
  }, [isOpen]);

  // Reset fetch flag when drawer closes
  useEffect(() => {
    if (!isOpen) {
      hasFetchedRef.current = false;
    }
  }, [isOpen]);

  const handleRefresh = () => {
    fetchOrientation();
  };

  // Loading state
  if (loading) {
    return (
      <div className="routine-briefing orientation">
        <div className="routine-briefing-loading">
          <span className="routine-briefing-spinner">◌</span>
          <span>Arriving...</span>
        </div>
      </div>
    );
  }

  // Error state - show nothing (fail silently)
  if (error) {
    return null;
  }

  // Silence is first-class - if orientation is null/silent, render nothing
  if (isSilent || orientation === null) {
    return null;
  }

  // Render narrative as markdown
  const renderNarrative = (text: string) => {
    const html = marked.parse(text) as string;
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="routine-briefing orientation">
      <div className="routine-briefing-header">
        <span className="routine-briefing-title">Orientation</span>
        <button
          className="routine-briefing-refresh"
          onClick={handleRefresh}
          title="Refresh"
        >
          ↻
        </button>
      </div>
      <div className="routine-briefing-content orientation-content">
        {renderNarrative(orientation)}
      </div>
    </div>
  );
}
