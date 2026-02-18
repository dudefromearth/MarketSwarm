// AFI (Antifragile Index) leaderboard types

export type TrendSignal = 'improving' | 'stable' | 'decaying';

export interface AFIComponents {
  r_slope: number;
  sharpe: number;
  ltc: number;
  dd_containment: number;
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
