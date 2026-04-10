import { parseEntityRouteSegment } from "@/lib/entity-paths";

export type RecentPageHistoryKind = "games" | "journalists" | "outlets";

export interface RecentPageHistoryEntry {
  href: string;
  imageUrl?: string;
  kind: RecentPageHistoryKind;
  subtitle: string;
  title: string;
  visitedAt: number;
}

const RECENT_PAGE_HISTORY_STORAGE_KEY = "review-disparity:recent-page-history";
const MAX_STORED_RECENT_PAGE_HISTORY = 10;
export const MAX_VISIBLE_RECENT_PAGE_HISTORY = 10;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function parseHref(href: string): URL | null {
  try {
    return new URL(href, "https://reviewdisparity.local");
  } catch {
    return null;
  }
}

function normalizeHref(href: string): string {
  const trimmedHref = href.trim();
  if (!trimmedHref) return "";

  const parsedHref = parseHref(trimmedHref);
  if (!parsedHref) return "";
  return parsedHref.pathname;
}

function toTitleCase(value: string): string {
  return value
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function buildLegacyFallbackTitle(href: string): string {
  const parsedHref = parseHref(href);
  if (!parsedHref) return "Viewed page";
  if (parsedHref.pathname === "/") return "Home";

  const segments = parsedHref.pathname.split("/").filter(Boolean);
  const lastSegment = segments[segments.length - 1];
  if (!lastSegment) return "Viewed page";
  return toTitleCase(lastSegment);
}

function buildFallbackTitle(href: string): string {
  const parsedHref = parseHref(href);
  if (!parsedHref) return "Viewed page";
  if (parsedHref.pathname === "/") return "Home";

  const segments = parsedHref.pathname.split("/").filter(Boolean);
  const lastSegment = segments[segments.length - 1];
  if (!lastSegment) return "Viewed page";

  const parsedSegment = parseEntityRouteSegment(lastSegment);
  const fallbackLabel = parsedSegment.slug ?? lastSegment;
  return toTitleCase(fallbackLabel);
}

function stripSiteName(title: string): string {
  return title.trim().replace(/\s+\|\s+ReviewDisparity$/i, "");
}

function stripEntityPageSuffix(title: string): string {
  return title.replace(/\s+-\s+(Critic vs User Scores|Review Scores & Disparity|Review Timing Snapshot|Disparity Trend Snapshot)$/i, "");
}

export function getRecentPageHistoryKind(href: string): RecentPageHistoryKind | null {
  const parsedHref = parseHref(href);
  if (!parsedHref) return null;

  const segments = parsedHref.pathname.split("/").filter(Boolean);
  if (segments.length < 2) return null;

  const [section] = segments;
  if (section === "games") return "games";
  if (section === "journalists") return "journalists";
  if (section === "outlets") return "outlets";
  return null;
}

function normalizeTitle(title: string, href: string): string {
  const strippedTitle = stripSiteName(title);
  const legacyFallbackTitle = buildLegacyFallbackTitle(href);
  if (!strippedTitle || strippedTitle === legacyFallbackTitle) {
    return buildFallbackTitle(href);
  }
  const entityTitle = stripEntityPageSuffix(strippedTitle).trim();
  return entityTitle || buildFallbackTitle(href);
}

function normalizeSubtitle(subtitle: string, href: string, kind: RecentPageHistoryKind): string {
  const trimmedSubtitle = subtitle.trim();
  if (trimmedSubtitle) return trimmedSubtitle;

  if (kind === "games") return "Game profile";
  if (kind === "journalists") return "Journalist profile";
  return "Outlet profile";
}

function normalizeImageUrl(imageUrl: string | undefined): string | undefined {
  const trimmedImageUrl = imageUrl?.trim();
  if (!trimmedImageUrl) return undefined;
  return trimmedImageUrl;
}

function normalizeEntry(entry: Partial<RecentPageHistoryEntry>): RecentPageHistoryEntry | null {
  const normalizedHref = normalizeHref(entry.href ?? "");
  if (!normalizedHref) return null;
  const kind = getRecentPageHistoryKind(normalizedHref);
  if (!kind) return null;

  return {
    href: normalizedHref,
    imageUrl: normalizeImageUrl(entry.imageUrl),
    kind,
    subtitle: normalizeSubtitle(entry.subtitle ?? "", normalizedHref, kind),
    title: normalizeTitle(entry.title ?? "", normalizedHref),
    visitedAt: typeof entry.visitedAt === "number" ? entry.visitedAt : Date.now(),
  };
}

export function buildRecentPageTitle(title: string, href: string): string {
  return normalizeTitle(title, href);
}

export function buildRecentPageSubtitle(href: string): string {
  const kind = getRecentPageHistoryKind(href);
  return kind ? normalizeSubtitle("", href, kind) : "";
}

export function getRecentPageHistory(): RecentPageHistoryEntry[] {
  if (!isBrowser()) return [];

  try {
    const storedValue = window.localStorage.getItem(RECENT_PAGE_HISTORY_STORAGE_KEY);
    if (!storedValue) return [];

    const parsedValue = JSON.parse(storedValue);
    if (!Array.isArray(parsedValue)) return [];

    return parsedValue
      .map((value) => {
        if (!value || typeof value !== "object") return null;
        return normalizeEntry(value as Partial<RecentPageHistoryEntry>);
      })
      .filter((value): value is RecentPageHistoryEntry => value != null)
      .sort((left, right) => right.visitedAt - left.visitedAt)
      .slice(0, MAX_STORED_RECENT_PAGE_HISTORY);
  } catch {
    return [];
  }
}

export function saveRecentPageView(entry: Pick<RecentPageHistoryEntry, "href" | "imageUrl" | "subtitle" | "title">): RecentPageHistoryEntry[] {
  const normalizedEntry = normalizeEntry({ ...entry, visitedAt: Date.now() });

  if (!normalizedEntry) {
    return getRecentPageHistory();
  }

  const existingEntries = getRecentPageHistory();
  const nextEntries = [
    normalizedEntry,
    ...existingEntries.filter((value) => value.href !== normalizedEntry.href),
  ].slice(0, MAX_STORED_RECENT_PAGE_HISTORY);

  if (!isBrowser()) return nextEntries;

  try {
    window.localStorage.setItem(RECENT_PAGE_HISTORY_STORAGE_KEY, JSON.stringify(nextEntries));
  } catch {
    return nextEntries;
  }

  return nextEntries;
}

export function upsertRecentPageHistoryEntry(entry: RecentPageHistoryEntry): RecentPageHistoryEntry[] {
  const normalizedEntry = normalizeEntry(entry);
  if (!normalizedEntry) {
    return getRecentPageHistory();
  }

  const existingEntries = getRecentPageHistory();
  const nextEntries = [
    normalizedEntry,
    ...existingEntries.filter((value) => value.href !== normalizedEntry.href),
  ]
    .sort((left, right) => right.visitedAt - left.visitedAt)
    .slice(0, MAX_STORED_RECENT_PAGE_HISTORY);

  if (!isBrowser()) return nextEntries;

  try {
    window.localStorage.setItem(RECENT_PAGE_HISTORY_STORAGE_KEY, JSON.stringify(nextEntries));
  } catch {
    return nextEntries;
  }

  return nextEntries;
}

export function clearRecentPageHistory(): void {
  if (!isBrowser()) return;

  try {
    window.localStorage.removeItem(RECENT_PAGE_HISTORY_STORAGE_KEY);
  } catch {
    // Ignore storage failures and leave the UI unchanged.
  }
}
