import type {
  PaginatedResponse,
  Journalist,
  JournalistDetail,
  OutletWithStats,
  GameWithScores,
  ReviewWithDisparity,
  ReviewWithJournalist,
  JournalistRanking,
  OutletRanking,
  GameRanking,
  SiteStats,
  SearchResult,
  DisparitySnapshot,
  NewsArticle,
} from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// Stats
export async function getStats(): Promise<SiteStats> {
  return fetchAPI<SiteStats>("/stats");
}

export async function getRecentReviews(limit = 10): Promise<ReviewWithJournalist[]> {
  return fetchAPI<ReviewWithJournalist[]>(`/stats/recent-reviews?limit=${limit}`);
}

// Journalists
export async function getJournalists(
  page = 1,
  perPage = 20,
  sortBy = "disparity",
  sortOrder = "desc",
  search?: string
): Promise<PaginatedResponse<Journalist>> {
  let url = `/journalists?page=${page}&per_page=${perPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return fetchAPI<PaginatedResponse<Journalist>>(url);
}

export async function getJournalist(id: number): Promise<JournalistDetail> {
  return fetchAPI<JournalistDetail>(`/journalists/${id}`);
}

export async function getJournalistReviews(
  id: number,
  page = 1,
  perPage = 20
): Promise<PaginatedResponse<ReviewWithDisparity>> {
  return fetchAPI<PaginatedResponse<ReviewWithDisparity>>(
    `/journalists/${id}/reviews?page=${page}&per_page=${perPage}`
  );
}

// Outlets
export async function getOutlets(
  page = 1,
  perPage = 20,
  sortBy = "disparity",
  sortOrder = "desc",
  search?: string
): Promise<PaginatedResponse<OutletWithStats>> {
  let url = `/outlets?page=${page}&per_page=${perPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return fetchAPI<PaginatedResponse<OutletWithStats>>(url);
}

export async function getOutlet(id: number): Promise<OutletWithStats> {
  return fetchAPI<OutletWithStats>(`/outlets/${id}`);
}

export async function getOutletReviews(
  id: number,
  page = 1,
  perPage = 20
): Promise<PaginatedResponse<ReviewWithJournalist>> {
  return fetchAPI<PaginatedResponse<ReviewWithJournalist>>(
    `/outlets/${id}/reviews?page=${page}&per_page=${perPage}`
  );
}

// Games
export async function getGames(
  page = 1,
  perPage = 20,
  sortBy = "release_date",
  sortOrder = "desc",
  year?: number,
  search?: string
): Promise<PaginatedResponse<GameWithScores>> {
  let url = `/games?page=${page}&per_page=${perPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;
  if (year) url += `&year=${year}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  return fetchAPI<PaginatedResponse<GameWithScores>>(url);
}

export async function getGame(id: number): Promise<GameWithScores> {
  return fetchAPI<GameWithScores>(`/games/${id}`);
}

export async function getGameReviews(
  id: number,
  page = 1,
  perPage = 20,
  reviewTiming?: string,
  sortOrder?: string,
): Promise<PaginatedResponse<ReviewWithJournalist>> {
  let url = `/games/${id}/reviews?page=${page}&per_page=${perPage}`;
  if (reviewTiming) url += `&review_timing=${reviewTiming}`;
  if (sortOrder) url += `&sort_order=${sortOrder}`;
  return fetchAPI<PaginatedResponse<ReviewWithJournalist>>(url);
}

// Leaderboards
export async function getJournalistLeaderboard(
  page = 1,
  perPage = 20,
  sort = "recent"
): Promise<PaginatedResponse<JournalistRanking>> {
  return fetchAPI<PaginatedResponse<JournalistRanking>>(
    `/leaderboards/journalists?page=${page}&per_page=${perPage}&sort=${sort}`
  );
}

export async function getOutletLeaderboard(
  page = 1,
  perPage = 20,
  sort = "recent"
): Promise<PaginatedResponse<OutletRanking>> {
  return fetchAPI<PaginatedResponse<OutletRanking>>(
    `/leaderboards/outlets?page=${page}&per_page=${perPage}&sort=${sort}`
  );
}

export async function getGameLeaderboard(
  page = 1,
  perPage = 20,
  sort = "recent"
): Promise<PaginatedResponse<GameRanking>> {
  return fetchAPI<PaginatedResponse<GameRanking>>(
    `/leaderboards/games?page=${page}&per_page=${perPage}&sort=${sort}`
  );
}

// Search
export async function search(query: string, limit = 10): Promise<SearchResult> {
  return fetchAPI<SearchResult>(`/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

// History (for charts) - returns full career timeline
export async function getJournalistHistory(
  id: number,
  limit = 10000
): Promise<DisparitySnapshot[]> {
  return fetchAPI<DisparitySnapshot[]>(`/journalists/${id}/history?limit=${limit}`);
}

export async function getOutletHistory(
  id: number,
  limit = 10000
): Promise<DisparitySnapshot[]> {
  return fetchAPI<DisparitySnapshot[]>(`/outlets/${id}/history?limit=${limit}`);
}

// All reviews for charts - fetches ALL reviews by paginating through all pages
export async function getJournalistAllReviews(
  id: number
): Promise<ReviewWithDisparity[]> {
  const allReviews: ReviewWithDisparity[] = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetchAPI<PaginatedResponse<ReviewWithDisparity>>(
      `/journalists/${id}/reviews?page=${page}&per_page=100`
    );
    allReviews.push(...response.items);
    hasMore = page < response.total_pages;
    page++;
  }

  return allReviews;
}

export async function getOutletAllReviews(
  id: number
): Promise<ReviewWithJournalist[]> {
  const allReviews: ReviewWithJournalist[] = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetchAPI<PaginatedResponse<ReviewWithJournalist>>(
      `/outlets/${id}/reviews?page=${page}&per_page=100`
    );
    allReviews.push(...response.items);
    hasMore = page < response.total_pages;
    page++;
  }

  return allReviews;
}

export async function getGameAllReviews(
  id: number
): Promise<ReviewWithJournalist[]> {
  const allReviews: ReviewWithJournalist[] = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetchAPI<PaginatedResponse<ReviewWithJournalist>>(
      `/games/${id}/reviews?page=${page}&per_page=100`
    );
    allReviews.push(...response.items);
    hasMore = page < response.total_pages;
    page++;
  }

  return allReviews;
}

// News
export async function getNews(
  page = 1,
  perPage = 20,
  source?: string
): Promise<PaginatedResponse<NewsArticle>> {
  let url = `/news?page=${page}&per_page=${perPage}`;
  if (source) url += `&source=${encodeURIComponent(source)}`;
  return fetchAPI<PaginatedResponse<NewsArticle>>(url);
}

export async function getNewsSources(): Promise<string[]> {
  return fetchAPI<string[]>("/news/sources");
}

export async function getGameNews(
  gameTitle: string,
  limit = 5
): Promise<PaginatedResponse<NewsArticle>> {
  return fetchAPI<PaginatedResponse<NewsArticle>>(
    `/news?per_page=${limit}&search=${encodeURIComponent(gameTitle)}`
  );
}
