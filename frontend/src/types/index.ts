// API Response Types

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// Journalist Types
export interface Journalist {
  id: number;
  public_id: string;
  name: string;
  image_url: string | null;
  bio: string | null;
  opencritic_id: number | null;
  review_count: number;
  avg_disparity: number | null;
  latest_review?: JournalistLatestReview | null;
}

export interface JournalistLatestReview {
  review_id: number;
  game_id: number;
  game_title: string;
  game_release_date: string | null;
  outlet_name: string | null;
  snippet: string | null;
  score_normalized: number | null;
  published_at: string | null;
  review_timing: ReviewTiming;
}

export interface JournalistStats {
  total_reviews: number;
  avg_score_given: number | null;

  // Launch window disparity (reviews within 60 days of game release)
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;

  // Overall disparity (all reviews, including late ones)
  overall_disparity_steam: number | null;
  overall_disparity_metacritic: number | null;
  overall_disparity_combined: number | null;

  std_deviation: number | null;
  alignment_rating: number | null;

  // Transparency metrics - timing
  early_review_count: number;
  launch_window_review_count: number;
  late_review_count: number;

  // Transparency metrics - scoring patterns
  min_score_given: number | null;
  max_score_given: number | null;
  score_std_deviation: number | null;
}

export interface OutletBreakdown {
  outlet_id: number;
  outlet_public_id: string;
  outlet_name: string;
  review_count: number;
  avg_disparity: number | null;
  date_range_start: string | null;
  date_range_end: string | null;
}

export interface JournalistDetail extends Journalist {
  stats: JournalistStats;
  outlet_breakdown: OutletBreakdown[];
  created_at: string;
  updated_at: string;
  std_deviation: number | null;
}

// Outlet Types
export interface Outlet {
  id: number;
  public_id: string;
  name: string;
  website_url: string | null;
  logo_url: string | null;
  opencritic_id: number | null;
  review_count?: number;
  avg_disparity?: number | null;
}

export interface OutletWithStats extends Outlet {
  journalist_count: number;
  review_count: number;
  avg_disparity: number | null;
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;
  avg_score: number | null;
  journalists?: Journalist[];
  // Transparency metrics - timing
  early_review_count?: number;
  launch_window_review_count?: number;
  late_review_count?: number;
  // Transparency metrics - scoring patterns
  min_score_given: number | null;
  max_score_given: number | null;
  score_std_deviation: number | null;
  latest_review?: ReviewWithJournalist | null;
}

// Game Types
export interface Game {
  id: number;
  public_id: string;
  title: string;
  release_date: string | null;
  description: string | null;
  image_url: string | null;
  opencritic_id: number | null;
  steam_app_id: number | null;
  critic_review_count?: number;
  disparity?: number | null;
}

export interface GameWithScores extends Game {
  // From API - these are the actual field names returned
  opencritic_score: number | null;
  steam_user_score: number | null;
  steam_sample_size: number | null;
  steam_player_24h_peak: number | null;
  steam_player_24h_low_observed: number | null;
  steam_player_all_time_peak: number | null;
  steam_player_all_time_peak_at: string | null;
  steam_player_stats_synced_at: string | null;
  steam_achievement_count: number | null;
  steam_achievement_count_synced_at: string | null;
  metacritic_user_score: number | null;
  metacritic_sample_size: number | null;
  avg_critic_score: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
  tier: string | null;
  percent_recommended: number | null;
  early_review_count?: number;
  launch_window_review_count?: number;
  late_review_count?: number;
  latest_review?: ReviewWithJournalist | null;
}

// Review Types
export interface Review {
  id: number;
  journalist_id: number;
  journalist_public_id?: string | null;
  game_id: number;
  game_public_id?: string | null;
  outlet_id: number | null;
  outlet_public_id?: string | null;
  score_raw: string;
  score_scale: string | null;
  score_normalized: number | null;
  review_url: string | null;
  snippet: string | null;
  published_at: string | null;
}

export type ReviewTiming = "early" | "launch_window" | "late" | "unknown";

export interface ReviewWithDisparity extends Review {
  game_title: string;
  game_release_date: string | null;
  outlet_name: string | null;
  steam_user_score: number | null;
  metacritic_user_score: number | null;
  disparity: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
  is_launch_window: boolean;  // Deprecated - use review_timing
  review_timing: ReviewTiming;
}

export interface ReviewWithJournalist extends Review {
  journalist_name: string;
  journalist_image_url: string | null;
  outlet_name: string | null;
  game_title: string | null;
  game_release_date: string | null;
  disparity: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
  is_launch_window: boolean;  // Deprecated - use review_timing
  review_timing: ReviewTiming;
}

// Leaderboard Types
export interface JournalistRanking {
  rank: number;
  journalist_id: number;
  journalist_public_id: string;
  journalist_name: string;
  journalist_image_url: string | null;
  outlet_name: string | null;
  avg_disparity: number;
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;
  review_count: number;
}

export interface OutletRanking {
  rank: number;
  outlet_id: number;
  outlet_public_id: string;
  outlet_name: string;
  outlet_logo_url: string | null;
  avg_disparity: number;
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;
  journalist_count: number;
  review_count: number;
}

export interface GameRanking {
  rank: number;
  game_id: number;
  game_public_id: string;
  game_title: string;
  game_image_url: string | null;
  release_date: string | null;
  avg_critic_score: number;
  steam_user_score: number | null;
  metacritic_user_score: number | null;
  disparity: number;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
  critic_review_count: number;
}

// Stats Types
export interface SiteStats {
  total_journalists: number;
  total_outlets: number;
  total_games: number;
  total_reviews: number;
  avg_disparity_site: number | null;
  last_updated: string;
}

// Search Types
export interface SearchResult {
  journalists: Journalist[];
  outlets: Outlet[];
  games: Game[];
}

// History/Chart Types
export interface DisparitySnapshot {
  date: string;
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;
  review_count: number;
}

export type SteamPlayerMarkerType =
  | "first_tracked"
  | "all_time_peak"
  | "major_surge"
  | "major_drop"
  | "rebound";

export interface SteamPlayerPoint {
  sampled_at: string;
  observed_24h_high: number;
  observed_24h_low: number;
  latest_players?: number | null;
}

export interface SteamPlayerMarker {
  marker_type: SteamPlayerMarkerType;
  sampled_at: string;
  concurrent_players: number;
  label: string;
  detail: string | null;
}

export interface SteamActivityResponse {
  summary: GameWithScores;
  points: SteamPlayerPoint[];
  markers: SteamPlayerMarker[];
}

// Compare Types
export interface CompareJournalist {
  journalist: JournalistDetail;
  history: DisparitySnapshot[];
}

export interface CompareOutlet {
  outlet: OutletWithStats;
  history: DisparitySnapshot[];
}

// News Types
export interface NewsArticle {
  id: number;
  title: string;
  description: string | null;
  url: string;
  image_url: string | null;
  source_name: string;
  author: string | null;
  published_at: string | null;
}

export interface TrendingGame {
  rank: number;
  trend_key: string;
  title: string;
  game_id: number | null;
  game_public_id: string | null;
  release_date: string | null;
  image_url: string | null;
  is_linked: boolean;
  is_upcoming: boolean;
  latest_article_at: string | null;
  latest_article_url: string | null;
  news_mention_count: number;
  news_source_count: number;
  trend_score: number;
  source_scores: Record<string, number>;
}

export interface TrendingGamesResponse {
  as_of: string;
  window_hours: number;
  items: TrendingGame[];
}
