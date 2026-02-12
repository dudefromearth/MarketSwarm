/**
 * ElevationHint — Subtle footer below Vexy response for observer tier.
 *
 * 11px italic, muted, max 1 line, no icons.
 * Session-scoped cooldown (max 1 shown per session).
 */

import { useState } from 'react';

const SHOWN_KEY = 'vexy_elevation_hint_shown';

interface ElevationHintProps {
  hint: string | undefined;
}

export default function ElevationHint({ hint }: ElevationHintProps) {
  const [alreadyShown] = useState(() => {
    try {
      return sessionStorage.getItem(SHOWN_KEY) === '1';
    } catch {
      return false;
    }
  });

  if (!hint || alreadyShown) return null;

  // Mark as shown for this session
  try {
    sessionStorage.setItem(SHOWN_KEY, '1');
  } catch {
    // sessionStorage unavailable
  }

  return (
    <div className="vexy-elevation-hint">
      {hint}
    </div>
  );
}
