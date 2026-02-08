/**
 * TierBadge - Displays user's subscription tier
 */

export type UserTier = 'observer' | 'activator' | 'navigator' | 'coaching' | 'administrator';

interface TierBadgeProps {
  tier: UserTier;
}

const TIER_LABELS: Record<UserTier, string> = {
  observer: 'Observer',
  activator: 'Activator',
  navigator: 'Navigator',
  coaching: 'Coaching',
  administrator: 'Admin',
};

export default function TierBadge({ tier }: TierBadgeProps) {
  return (
    <span className={`vexy-tier-badge ${tier}`}>
      {TIER_LABELS[tier] || tier}
    </span>
  );
}
