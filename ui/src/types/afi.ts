// AFI (Antifragile Index) leaderboard types

export type TrendSignal = 'improving' | 'stable' | 'decaying';

export interface AFIComponents {
  r_slope: number;
  sharpe: number;
  ltc: number;
  dd_containment: number;
}

export interface AFIComponentsV4 {
  daily_sharpe: number | null;
  drawdown_resilience: number | null;
  payoff_asymmetry: number | null;
  recovery_velocity: number | null;
}

export type CapitalStatus = 'verified' | 'unverified';

export interface AFIScore {
  user_id: number;
  rank: number;
  afi_score: number;
  robustness: number;
  trend: TrendSignal;
  is_provisional: boolean;
  trade_count: number;
  calculated_at: string;
  components: AFIComponents;
  displayName?: string;
  afi_version?: number;
  cps?: number;
  repeatability?: number;
  capital_status?: CapitalStatus;
  leaderboard_eligible?: boolean;
  // v4 dual-index fields
  afi_m?: number | null;
  afi_r?: number | null;
  composite?: number | null;
  components_v4?: AFIComponentsV4;
  confidence?: number | null;
}

export interface AFILeaderboardResponse {
  success: boolean;
  data: {
    rankings: AFIScore[];
    currentUserRank: AFIScore | null;
    totalParticipants: number;
  };
}

export interface AFIMyResponse {
  success: boolean;
  data: {
    score: AFIScore | null;
    totalParticipants: number;
  };
}

export function getAFITier(score: number, capitalStatus?: CapitalStatus): { name: string; className: string } {
  if (capitalStatus === 'unverified') return { name: 'Unrated', className: 'afi-unrated' };
  if (score >= 820) return { name: 'Black', className: 'afi-black' };
  if (score >= 790) return { name: 'Gold', className: 'afi-gold' };
  if (score >= 700) return { name: 'Purple', className: 'afi-purple' };
  if (score >= 600) return { name: 'Blue', className: 'afi-blue' };
  return { name: 'Neutral', className: 'afi-neutral' };
}

/** Get the primary display score for a user (composite for v4/v5, afi_score for v1-v3). */
export function getPrimaryScore(score: AFIScore): number {
  if ((score.afi_version === 5 || score.afi_version === 4) && score.composite != null) return score.composite;
  return score.afi_score;
}
