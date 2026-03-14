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
  TrendingGamesResponse,
} from "@/types";
import { getApiUrl } from "@/lib/api-base-url";

const API_URL = getApiUrl();
const journalistAllReviewsCache = new Map<string, Promise<ReviewWithDisparity[]>>();
const outletAllReviewsCache = new Map<string, Promise<ReviewWithJournalist[]>>();
const gameAllReviewsCache = new Map<string, Promise<ReviewWithJournalist[]>>();

type NextFetchOptions = RequestInit & {
  next?: {
    revalidate?: number;
    tags?: string[];
  };
};

function getServerRevalidateSeconds(endpoint: string): number {
  if (endpoint.startsWith("/stats/recent-reviews")) return 15;
  if (endpoint.startsWith("/journalists")) return 15;
  if (endpoint.startsWith("/outlets")) return 15;
  if (endpoint.startsWith("/games")) return 15;
  if (endpoint.startsWith("/stats/sitemap-data")) return 3600;
  if (endpoint.startsWith("/news/sources")) return 300;
  if (endpoint.startsWith("/search")) return 30;
  return 60;
}

async function fetchAPI<T>(endpoint: string, options?: NextFetchOptions): Promise<T> {
  const isServer = typeof window === "undefined";
  const hasExplicitRevalidate = options?.next?.revalidate != null;
  const hasExplicitCache = options?.cache != null;

  const requestOptions: NextFetchOptions = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  };

  if (isServer && !hasExplicitRevalidate && !hasExplicitCache) {
    requestOptions.next = {
      ...requestOptions.next,
      revalidate: getServerRevalidateSeconds(endpoint),
    };
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...requestOptions,
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function fetchAllPaginatedReviews<T>(
  buildEndpoint: (page: number) => string
): Promise<T[]> {
  const firstPage = await fetchAPI<PaginatedResponse<T>>(buildEndpoint(1));
  if (firstPage.total_pages <= 1) {
    return firstPage.items;
  }

  const remainingPages = await Promise.all(
    Array.from({ length: firstPage.total_pages - 1 }, (_, index) =>
      fetchAPI<PaginatedResponse<T>>(buildEndpoint(index + 2))
    )
  );

  return [
    ...firstPage.items,
    ...remainingPages.flatMap((page) => page.items),
  ];
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

export async function getJournalist(id: string | number): Promise<JournalistDetail> {
  return fetchAPI<JournalistDetail>(`/journalists/${id}`);
}

export async function getJournalistReviews(
  id: string | number,
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

export async function getOutlet(id: string | number): Promise<OutletWithStats> {
  return fetchAPI<OutletWithStats>(`/outlets/${id}`);
}

export async function getOutletReviews(
  id: string | number,
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

export async function getGame(id: string | number): Promise<GameWithScores> {
  return fetchAPI<GameWithScores>(`/games/${id}`);
}

export async function getGameReviews(
  id: string | number,
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
  id: string | number,
  limit = 10000
): Promise<DisparitySnapshot[]> {
  return fetchAPI<DisparitySnapshot[]>(`/journalists/${id}/history?limit=${limit}`);
}

export async function getOutletHistory(
  id: string | number,
  limit = 10000
): Promise<DisparitySnapshot[]> {
  return fetchAPI<DisparitySnapshot[]>(`/outlets/${id}/history?limit=${limit}`);
}

export async function getGameHistory(
  id: string | number,
  limit = 10000
): Promise<DisparitySnapshot[]> {
  return fetchAPI<DisparitySnapshot[]>(`/games/${id}/history?limit=${limit}`);
}

// All reviews for charts - fetches ALL reviews by paginating through all pages
export async function getJournalistAllReviews(
  id: string | number
): Promise<ReviewWithDisparity[]> {
  const cacheKey = String(id);
  const isBrowser = typeof window !== "undefined";
  if (isBrowser) {
    const cached = journalistAllReviewsCache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  const request = fetchAllPaginatedReviews<ReviewWithDisparity>(
    (page) => `/journalists/${id}/reviews?page=${page}&per_page=500`
  );

  if (isBrowser) {
    journalistAllReviewsCache.set(cacheKey, request);
  }

  try {
    return await request;
  } catch (error) {
    if (isBrowser) {
      journalistAllReviewsCache.delete(cacheKey);
    }
    throw error;
  }
}

export async function getOutletAllReviews(
  id: string | number
): Promise<ReviewWithJournalist[]> {
  const cacheKey = String(id);
  const isBrowser = typeof window !== "undefined";
  if (isBrowser) {
    const cached = outletAllReviewsCache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  const request = (async () => {
    return fetchAllPaginatedReviews<ReviewWithJournalist>(
      (page) => `/outlets/${id}/reviews?page=${page}&per_page=500`
    );
  })();

  if (isBrowser) {
    outletAllReviewsCache.set(cacheKey, request);
  }

  try {
    return await request;
  } catch (error) {
    if (isBrowser) {
      outletAllReviewsCache.delete(cacheKey);
    }
    throw error;
  }
}

export async function getGameAllReviews(
  id: string | number
): Promise<ReviewWithJournalist[]> {
  const cacheKey = String(id);
  const isBrowser = typeof window !== "undefined";
  if (isBrowser) {
    const cached = gameAllReviewsCache.get(cacheKey);
    if (cached) {
      return cached;
    }
  }

  const request = fetchAllPaginatedReviews<ReviewWithJournalist>(
    (page) => `/games/${id}/reviews?page=${page}&per_page=500`
  );

  if (isBrowser) {
    gameAllReviewsCache.set(cacheKey, request);
  }

  try {
    return await request;
  } catch (error) {
    if (isBrowser) {
      gameAllReviewsCache.delete(cacheKey);
    }
    throw error;
  }
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
  gameId: string | number,
  page = 1,
  perPage = 5
): Promise<PaginatedResponse<NewsArticle>> {
  return fetchAPI<PaginatedResponse<NewsArticle>>(
    `/games/${gameId}/news?page=${page}&per_page=${perPage}`
  );
}

export async function getTrendingGames(
  limit = 8,
  windowHours = 48,
): Promise<TrendingGamesResponse> {
  return fetchAPI<TrendingGamesResponse>(
    `/stats/trending-games?limit=${limit}&window_hours=${windowHours}`
  );
}
