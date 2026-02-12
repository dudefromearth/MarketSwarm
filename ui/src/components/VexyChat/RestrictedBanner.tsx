/**
 * RestrictedBanner — Post-trial inline banner for observer_restricted users.
 *
 * Not modal. Calm. Inline with dismiss (x).
 * sessionStorage tracks dismissal (once per session).
 */

import { useState } from 'react';

const DISMISS_KEY = 'vexy_restricted_banner_dismissed';

interface RestrictedBannerProps {
  tier: string;
}

export default function RestrictedBanner({ tier }: RestrictedBannerProps) {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return sessionStorage.getItem(DISMISS_KEY) === '1';
    } catch {
      return false;
    }
  });

  if (tier !== 'observer_restricted' || dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      // sessionStorage unavailable
    }
  };

  return (
    <div className="vexy-restricted-banner">
      <span>Interactive depth is currently limited. Full continuity available at Activator tier.</span>
      <button className="vexy-restricted-banner-dismiss" onClick={handleDismiss}>
        &times;
      </button>
    </div>
  );
}
