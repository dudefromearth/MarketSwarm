/**
 * ProcessEcho - Process-Level Echo for Routine Panel
 *
 * Renders BELOW Orientation with QUIETER visual weight.
 * Feels like a small reflective note, NOT a module.
 *
 * Per spec:
 * - Maximum 1-2 echoes per session
 * - Silence is first-class (renders nothing when no echoes)
 * - Read-only, no state changes
 * - Follows Vexy voice rules (observational, non-judgmental)
 * - No advice, no warning language
 */

import { useState, useEffect, useRef } from 'react';

interface ProcessEchoData {
  type: 'process_echo';
  category: 'continuity';
  delta_type: string;
  log_name?: string;
  message: string;
  source: string[];
  confidence: string;
}

interface ProcessEchoResponse {
  success: boolean;
  echoes: ProcessEchoData[];
  narrative_fragment: string;
  echo_count: number;
  error?: string;
}

interface ProcessEchoProps {
  isOpen: boolean;
}

export default function ProcessEcho({ isOpen }: ProcessEchoProps) {
  const [echoes, setEchoes] = useState<ProcessEchoData[]>([]);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState<number | null>(null);
  const hasFetchedRef = useRef(false);
  const lastOpenRef = useRef(false);

  // Fetch user ID from auth endpoint on mount
  useEffect(() => {
    const fetchUserId = async () => {
      try {
        const response = await fetch('/api/auth/me', { credentials: 'include' });
        if (response.ok) {
          const data = await response.json();
          // The wp.id is the WordPress user ID
          const wpId = data?.wp?.id;
          if (wpId) {
            setUserId(parseInt(wpId, 10));
          }
        }
      } catch (err) {
        console.error('[ProcessEcho] Failed to get user ID:', err);
      }
    };
    fetchUserId();
  }, []);

  const fetchEchoes = async () => {
    if (!userId) return;

    setLoading(true);

    try {
      const response = await fetch(`/api/vexy/process-echo/${userId}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        console.error('[ProcessEcho] Fetch failed:', response.status);
        return;
      }

      const data: ProcessEchoResponse = await response.json();

      if (data.success && data.echoes && data.echoes.length > 0) {
        // Limit to max 2 echoes as per spec
        setEchoes(data.echoes.slice(0, 2));
      }
    } catch (err) {
      console.error('[ProcessEcho] Error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch when drawer opens (transition from closed to open) and userId is available
  useEffect(() => {
    if (isOpen && userId && !lastOpenRef.current && !hasFetchedRef.current) {
      hasFetchedRef.current = true;
      fetchEchoes();
    }
    lastOpenRef.current = isOpen;
  }, [isOpen, userId]);

  // Reset fetch flag when drawer closes
  useEffect(() => {
    if (!isOpen) {
      hasFetchedRef.current = false;
    }
  }, [isOpen]);

  // Silence is first-class: render nothing if no echoes
  if (loading || echoes.length === 0) {
    return null;
  }

  return (
    <div className="process-echo quiet">
      {echoes.map((echo, idx) => (
        <div key={`echo-${idx}`} className="process-echo-message">
          {echo.message}
        </div>
      ))}
    </div>
  );
}
