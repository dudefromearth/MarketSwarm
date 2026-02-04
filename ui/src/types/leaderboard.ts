// Leaderboard types for gamified engagement tracking

export type LeaderboardPeriod = 'weekly' | 'monthly' | 'all_time';

export interface LeaderboardScore {
  user_id: number;
  rank: number;
  trades_logged: number;
  journal_entries: number;
  tags_used: number;
  total_pnl: number;
  win_rate: number;
  avg_r_multiple: number;
  closed_trades: number;
  activity_score: number;
  performance_score: number;
  total_score: number;
  calculated_at: string;
  // Display name added by frontend after fetching user info
  displayName?: string;
}

export interface LeaderboardResponse {
  success: boolean;
  data: {
    rankings: LeaderboardScore[];
    currentUserRank: LeaderboardScore | null;
    totalParticipants: number;
    periodType: LeaderboardPeriod;
    periodKey: string;
  };
}

export interface MyLeaderboardResponse {
  success: boolean;
  data: {
    weekly: {
      score: LeaderboardScore | null;
      totalParticipants: number;
      periodKey: string;
    };
    monthly: {
      score: LeaderboardScore | null;
      totalParticipants: number;
      periodKey: string;
    };
    all_time: {
      score: LeaderboardScore | null;
      totalParticipants: number;
      periodKey: string;
    };
  };
}

export interface LeaderboardSettings {
  userId: number;
  screenName: string | null;
  showScreenName: boolean;
  displayName: string | null;
}

export interface LeaderboardSettingsUpdate {
  screenName?: string;
  showScreenName?: boolean;
}
