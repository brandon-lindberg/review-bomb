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
  name: string;
  image_url: string | null;
  bio: string | null;
  opencritic_id: number | null;
  review_count: number;
  avg_disparity: number | null;
  avg_score: number | null;
}

export interface JournalistStats {
  total_reviews: number;
  avg_score_given: number | null;
  avg_disparity_steam: number | null;
  avg_disparity_metacritic: number | null;
  avg_disparity_combined: number | null;
  std_deviation: number | null;
  alignment_rating: number | null;
}

export interface OutletBreakdown {
  outlet_id: number;
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
  avg_score: number | null;
  journalists?: Journalist[];
}

// Game Types
export interface Game {
  id: number;
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
  opencritic_score: number | null;
  top_critic_score: number | null;
  steam_user_score: number | null;
  steam_score: number | null;
  steam_sample_size: number | null;
  metacritic_user_score: number | null;
  metacritic_score: number | null;
  metacritic_sample_size: number | null;
  avg_critic_score: number | null;
  critic_avg: number | null;
  user_avg: number | null;
  disparity: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
  tier: string | null;
  percent_recommended: number | null;
  review_count: number;
}

// Review Types
export interface Review {
  id: number;
  journalist_id: number;
  game_id: number;
  outlet_id: number | null;
  score_raw: string;
  score_scale: string | null;
  score_normalized: number | null;
  review_url: string | null;
  snippet: string | null;
  published_at: string | null;
}

export interface ReviewWithDisparity extends Review {
  game_title: string;
  outlet_name: string | null;
  steam_user_score: number | null;
  metacritic_user_score: number | null;
  disparity: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
}

export interface ReviewWithJournalist extends Review {
  journalist_name: string;
  journalist_image_url: string | null;
  outlet_name: string | null;
  disparity: number | null;
  disparity_steam: number | null;
  disparity_metacritic: number | null;
}

// Leaderboard Types
export interface JournalistRanking {
  rank: number;
  journalist_id: number;
  journalist_name: string;
  journalist_image_url: string | null;
  outlet_name: string | null;
  avg_disparity: number;
  review_count: number;
}

export interface OutletRanking {
  rank: number;
  outlet_id: number;
  outlet_name: string;
  outlet_logo_url: string | null;
  avg_disparity: number;
  journalist_count: number;
  review_count: number;
}

export interface GameRanking {
  rank: number;
  game_id: number;
  game_title: string;
  game_image_url: string | null;
  release_date: string | null;
  avg_critic_score: number;
  steam_user_score: number | null;
  metacritic_user_score: number | null;
  disparity: number;
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
