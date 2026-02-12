/**
 * TrialIndicator — Small muted text for observer-tier trial countdown.
 *
 * Only shown when tier=observer AND daysRemaining > 0.
 * Style: 10px, muted, never red, never bold.
 */

interface TrialIndicatorProps {
  tier: string;
  createdAt?: string;
}

export default function TrialIndicator({ tier, createdAt }: TrialIndicatorProps) {
  if (tier !== 'observer' || !createdAt) return null;

  const created = new Date(createdAt);
  const now = new Date();
  const daysSince = Math.floor((now.getTime() - created.getTime()) / (1000 * 60 * 60 * 24));
  const daysRemaining = 28 - daysSince;

  if (daysRemaining <= 0) return null;

  return (
    <div className="vexy-trial-indicator">
      Observer Trial &mdash; {daysRemaining} day{daysRemaining !== 1 ? 's' : ''} remaining
    </div>
  );
}
