"use client";

import { useEffect, useRef, useState, useTransition, type FormEvent, type ReactNode } from "react";
import Image from "@/components/AppImage";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DisparityBadge } from "@/components/DisparityBadge";
import { GameAvatar } from "@/components/GameAvatar";
import { getBrowserApiUrl } from "@/lib/api-base-url";
import { buildEntityPath } from "@/lib/entity-paths";
import type { Game, Journalist, Outlet, SearchResult } from "@/types";

interface HeaderSearchProps {
  open: boolean;
  onClose: () => void;
}

const EMPTY_SEARCH_RESULT: SearchResult = {
  journalists: [],
  outlets: [],
  games: [],
};

function SearchSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section
      className="rounded-[1.4rem] border p-3"
      style={{
        borderColor: "var(--border)",
        background:
          "linear-gradient(180deg, color-mix(in srgb, var(--background-card-strong) 94%, var(--color-tan) 6%), color-mix(in srgb, var(--background-card) 96%, transparent))",
      }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
          {title}
        </h2>
        <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ backgroundColor: "rgba(187, 59, 14, 0.12)", color: "var(--color-rust)" }}>
          {count}
        </span>
      </div>
      <div className="space-y-2">
        {children}
      </div>
    </section>
  );
}

function SearchResultCard({
  href,
  media,
  title,
  subtitle,
  disparity,
  onSelect,
}: {
  href: string;
  media: ReactNode;
  title: string;
  subtitle: string;
  disparity: number | null | undefined;
  onSelect: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onSelect}
      className="flex items-center justify-between gap-3 rounded-[1rem] border px-3 py-3 transition-opacity hover:opacity-85"
      style={{
        borderColor: "color-mix(in srgb, var(--border) 86%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--background-card-strong) 84%, transparent)",
      }}
    >
      <div className="flex min-w-0 items-center gap-3">
        {media}
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" style={{ color: "var(--foreground)" }}>
            {title}
          </div>
          <div className="truncate text-xs" style={{ color: "var(--foreground-muted)" }}>
            {subtitle}
          </div>
        </div>
      </div>
      <div className="shrink-0">
        <DisparityBadge disparity={disparity} size="sm" />
      </div>
    </Link>
  );
}

function renderJournalistResult(journalist: Journalist, onSelect: () => void) {
  return (
    <SearchResultCard
      key={`journalist-${journalist.id}`}
      href={buildEntityPath("journalists", journalist.name, journalist.public_id)}
      onSelect={onSelect}
      title={journalist.name}
      subtitle={`${journalist.review_count.toLocaleString()} review${journalist.review_count === 1 ? "" : "s"}`}
      disparity={journalist.avg_disparity}
      media={journalist.image_url ? (
        <Image
          src={journalist.image_url}
          alt={journalist.name}
          width={40}
          height={40}
          sizes="40px"
          className="h-10 w-10 rounded-full object-cover"
        />
      ) : (
        <div
          className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold"
          style={{ backgroundColor: "rgba(187, 59, 14, 0.14)", color: "var(--color-rust)" }}
        >
          {journalist.name.charAt(0)}
        </div>
      )}
    />
  );
}

function renderOutletResult(outlet: Outlet, onSelect: () => void) {
  const reviewCount = outlet.review_count ?? 0;

  return (
    <SearchResultCard
      key={`outlet-${outlet.id}`}
      href={buildEntityPath("outlets", outlet.name, outlet.public_id)}
      onSelect={onSelect}
      title={outlet.name}
      subtitle={`${reviewCount.toLocaleString()} review${reviewCount === 1 ? "" : "s"}`}
      disparity={outlet.avg_disparity}
      media={outlet.logo_url ? (
        <Image
          src={outlet.logo_url}
          alt={outlet.name}
          width={40}
          height={40}
          sizes="40px"
          className="h-10 w-10 rounded-xl object-contain"
        />
      ) : (
        <div
          className="flex h-10 w-10 items-center justify-center rounded-xl text-sm font-semibold"
          style={{ backgroundColor: "rgba(216, 197, 147, 0.2)", color: "var(--color-rust)" }}
        >
          {outlet.name.charAt(0)}
        </div>
      )}
    />
  );
}

function renderGameResult(game: Game, onSelect: () => void) {
  const subtitle = game.release_date
    ? new Date(`${game.release_date}T00:00:00`).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Release date unavailable";

  return (
    <SearchResultCard
      key={`game-${game.id}`}
      href={buildEntityPath("games", game.title, game.public_id)}
      onSelect={onSelect}
      title={game.title}
      subtitle={subtitle}
      disparity={game.disparity}
      media={(
        <GameAvatar
          title={game.title}
          imageUrl={game.image_url}
          width={54}
          height={30}
          sizes="54px"
          className="h-[1.875rem] w-[3.375rem] rounded-lg object-contain"
        />
      )}
    />
  );
}

export function HeaderSearch({
  open,
  onClose,
}: HeaderSearchProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isNavigating, startTransition] = useTransition();

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults(null);
      setIsLoading(false);
      return;
    }

    const focusTimeout = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 30);

    return () => window.clearTimeout(focusTimeout);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;

    const trimmedQuery = query.trim();
    if (trimmedQuery.length < 2) {
      setResults(null);
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    const searchTimeout = window.setTimeout(async () => {
      setIsLoading(true);
      try {
        const response = await fetch(
          `${getBrowserApiUrl()}/search?q=${encodeURIComponent(trimmedQuery)}&limit=6`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          throw new Error(`Search failed: ${response.status}`);
        }

        const payload = await response.json() as SearchResult;
        setResults(payload);
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Header search error:", error);
        setResults(EMPTY_SEARCH_RESULT);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, 220);

    return () => {
      controller.abort();
      window.clearTimeout(searchTimeout);
    };
  }, [open, query]);

  if (!open) {
    return null;
  }

  const trimmedQuery = query.trim();
  const hasEnoughQuery = trimmedQuery.length >= 2;
  const activeResults = results ?? EMPTY_SEARCH_RESULT;
  const totalResults = activeResults.journalists.length + activeResults.outlets.length + activeResults.games.length;
  const hasVisibleResults = hasEnoughQuery && totalResults > 0;
  const searchPlaceholder = "Search games, journalists, or outlets";

  const handleFullSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!trimmedQuery) return;

    startTransition(() => {
      onClose();
      router.push(`/search?q=${encodeURIComponent(trimmedQuery)}`);
    });
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="fixed inset-x-3 top-20 z-50 sm:inset-x-6 sm:top-24">
        <div
          className="mx-auto w-full max-w-5xl overflow-hidden rounded-[1.9rem] border"
          style={{
            borderColor: "var(--border-strong)",
            background:
              "linear-gradient(180deg, color-mix(in srgb, var(--background-card-strong) 96%, var(--background) 4%), color-mix(in srgb, var(--background-card) 94%, var(--background) 6%))",
            boxShadow: "var(--shadow-strong)",
          }}
          role="dialog"
          aria-modal="true"
          aria-label="Site search"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="border-b px-4 py-4 sm:px-5" style={{ borderColor: "var(--border)" }}>
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div
                  className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border"
                  style={{
                    borderColor: "var(--border)",
                    background:
                      "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
                    color: "var(--foreground)",
                  }}
                  aria-hidden="true"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
                    Search the site
                  </div>
                  <div className="text-xs" style={{ color: "var(--foreground-muted)" }}>
                    Find games, journalists, and outlets without leaving the home page.
                  </div>
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border transition-opacity hover:opacity-80"
                  style={{
                    borderColor: "var(--border)",
                    background:
                      "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
                    color: "var(--foreground)",
                  }}
                  aria-label="Close search"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              <form onSubmit={handleFullSearch} className="rounded-[1.25rem] border p-3" style={{ borderColor: "var(--border)", backgroundColor: "color-mix(in srgb, var(--background-card-strong) 82%, transparent)" }}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-center gap-3 rounded-full border px-4 py-3" style={{ borderColor: "color-mix(in srgb, var(--border) 88%, transparent)", backgroundColor: "color-mix(in srgb, var(--background-card) 78%, transparent)" }}>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{ color: "var(--foreground-muted)" }}
                      aria-hidden="true"
                    >
                      <circle cx="11" cy="11" r="8" />
                      <path d="m21 21-4.35-4.35" />
                    </svg>
                    <input
                      ref={inputRef}
                      type="text"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder={searchPlaceholder}
                      className="min-w-0 flex-1 bg-transparent text-base outline-none"
                      style={{ color: "var(--foreground)" }}
                      aria-label="Search games, journalists, or outlets"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={!trimmedQuery || isNavigating}
                    className="w-full rounded-full px-4 py-3 text-sm font-semibold uppercase tracking-[0.12em] disabled:opacity-50 sm:w-auto sm:px-5 sm:py-2.5"
                    style={{
                      backgroundColor: "var(--color-rust)",
                      color: "white",
                    }}
                  >
                    Search
                  </button>
                </div>
              </form>
            </div>
          </div>

          <div className="max-h-[min(68vh,42rem)] overflow-y-auto px-4 py-4 sm:px-5">
            {!hasEnoughQuery ? (
              <div
                className="rounded-[1.4rem] border px-4 py-5 text-sm"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "color-mix(in srgb, var(--background-card-strong) 88%, transparent)",
                  color: "var(--foreground-muted)",
                }}
              >
                Type at least 2 characters to search across games, journalists, and outlets.
              </div>
            ) : isLoading ? (
              <div
                className="rounded-[1.4rem] border px-4 py-5 text-sm"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "color-mix(in srgb, var(--background-card-strong) 88%, transparent)",
                  color: "var(--foreground-muted)",
                }}
              >
                Searching for matches...
              </div>
            ) : hasVisibleResults ? (
              <div className="grid gap-4 lg:grid-cols-3">
                {activeResults.games.length > 0 ? (
                  <SearchSection title="Games" count={activeResults.games.length}>
                    {activeResults.games.map((game) => renderGameResult(game, onClose))}
                  </SearchSection>
                ) : null}

                {activeResults.journalists.length > 0 ? (
                  <SearchSection title="Journalists" count={activeResults.journalists.length}>
                    {activeResults.journalists.map((journalist) => renderJournalistResult(journalist, onClose))}
                  </SearchSection>
                ) : null}

                {activeResults.outlets.length > 0 ? (
                  <SearchSection title="Outlets" count={activeResults.outlets.length}>
                    {activeResults.outlets.map((outlet) => renderOutletResult(outlet, onClose))}
                  </SearchSection>
                ) : null}
              </div>
            ) : (
              <div
                className="rounded-[1.4rem] border px-4 py-5 text-sm"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "color-mix(in srgb, var(--background-card-strong) 88%, transparent)",
                  color: "var(--foreground-muted)",
                }}
              >
                No matches found for &ldquo;{trimmedQuery}&rdquo;.
              </div>
            )}

            {hasEnoughQuery ? (
              <div className="mt-4 flex justify-end">
                <Link
                  href={`/search?q=${encodeURIComponent(trimmedQuery)}`}
                  onClick={onClose}
                  className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-opacity hover:opacity-85"
                  style={{
                    borderColor: "var(--border)",
                    backgroundColor: "color-mix(in srgb, var(--background-card-strong) 86%, transparent)",
                    color: "var(--foreground)",
                  }}
                >
                  View full search results
                  <span aria-hidden="true">→</span>
                </Link>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
