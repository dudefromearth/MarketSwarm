// AFI (Antifragile Index) leaderboard types

export type TrendSignal = 'improving' | 'stable' | 'decaying';

export interface AFIComponents {
  r_slope: number;
  sharpe: number;
  ltc: number;
  dd_containment: number;
}

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

export function getAFITier(score: number): { name: string; className: string } {
  if (score >= 820) return { name: 'Black', className: 'afi-black' };
  if (score >= 790) return { name: 'Gold', className: 'afi-gold' };
  if (score >= 700) return { name: 'Purple', className: 'afi-purple' };
  if (score >= 600) return { name: 'Blue', className: 'afi-blue' };
  return { name: 'Neutral', className: 'afi-neutral' };
}
