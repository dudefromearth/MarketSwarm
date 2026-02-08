/**
 * MicroPause - Marks shifts in cognitive mode
 *
 * A full-screen subtle fade with one neutral sentence.
 * No buttons. No interaction. Just a breath.
 *
 * Used at:
 * - Drawer open
 * - Drawer close
 * - Transition from Routine → other surfaces
 */

import { useEffect, useState, useRef } from 'react';

interface MicroPauseProps {
  text: string;
  durationMs?: number;
  onComplete?: () => void;
}

export default function MicroPause({
  text,
  durationMs = 1200,
  onComplete,
}: MicroPauseProps) {
  const [phase, setPhase] = useState<'entering' | 'holding' | 'exiting' | 'done'>('entering');
  const onCompleteRef = useRef(onComplete);
  const hasCompletedRef = useRef(false);

  // Keep ref updated but don't trigger effect
  onCompleteRef.current = onComplete;

  useEffect(() => {
    // Reset on mount
    hasCompletedRef.current = false;

    // Enter phase (fade in)
    const enterTimer = setTimeout(() => {
      setPhase('holding');
    }, 300);

    // Hold phase
    const holdTimer = setTimeout(() => {
      setPhase('exiting');
    }, durationMs - 300);

    // Exit phase (fade out)
    const exitTimer = setTimeout(() => {
      setPhase('done');
      if (!hasCompletedRef.current) {
        hasCompletedRef.current = true;
        onCompleteRef.current?.();
      }
    }, durationMs);

    return () => {
      clearTimeout(enterTimer);
      clearTimeout(holdTimer);
      clearTimeout(exitTimer);
    };
  }, [durationMs]); // Only depend on durationMs

  if (phase === 'done') {
    return null;
  }

  return (
    <div className={`micro-pause ${phase}`}>
      <span className="micro-pause-text">{text}</span>
    </div>
  );
}
