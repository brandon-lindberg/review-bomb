import "server-only";

import { cache } from "react";
import {
  getGame,
  getGameHistory,
  getGameNews,
  getGameSimilarGames,
  getJournalist,
  getJournalistHistory,
  getOutlet,
  getOutletHistory,
} from "@/lib/api";

export const getCachedGame = cache(async (id: string | number) => getGame(id));
export const getCachedGameHistory = cache(async (id: string | number, limit = 180) =>
  getGameHistory(id, limit)
);
export const getCachedGameNews = cache(async (id: string | number, page = 1, perPage = 5) =>
  getGameNews(id, page, perPage)
);
export async function getCachedGameSimilarGames(id: string | number, limit = 4) {
  return getGameSimilarGames(id, limit, { cache: "no-store" });
}

export const getCachedJournalist = cache(async (id: string | number) => getJournalist(id));
export const getCachedJournalistHistory = cache(async (id: string | number, limit = 180) =>
  getJournalistHistory(id, limit)
);

export const getCachedOutlet = cache(async (id: string | number) => getOutlet(id));
export const getCachedOutletHistory = cache(async (id: string | number, limit = 180) =>
  getOutletHistory(id, limit)
);
