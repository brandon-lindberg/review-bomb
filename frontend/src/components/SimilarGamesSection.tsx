import Link from "next/link";

import { GameAvatar } from "@/components/GameAvatar";
import { buildEntityPath } from "@/lib/entity-paths";
import type { SimilarGame } from "@/types";

interface SimilarGamesSectionProps {
  games: SimilarGame[];
}

function formatScore(value: number | null | undefined): string {
  return value != null ? Number(value).toFixed(0) : "N/A";
}

function formatReleaseDate(value: string | null | undefined): string {
  if (!value) return "Unknown release date";
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function SimilarGamesSection({ games }: SimilarGamesSectionProps) {
  if (games.length < 2) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.2em]"
            style={{ color: "var(--foreground-muted)" }}
          >
            Similar Games
          </p>
          <h2 className="mt-1 text-xl font-semibold" style={{ color: "var(--foreground)" }}>
            Strict Matches
          </h2>
        </div>
        <p
          className="max-w-2xl text-sm leading-6"
          style={{ color: "var(--foreground-muted)" }}
        >
          Only shown when archetype and gameplay fingerprint line up strongly enough.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {games.map((game) => (
          <Link
            key={game.id}
            href={buildEntityPath("games", game.title, game.public_id)}
            className="block rounded-2xl border p-3 transition-colors sm:p-4"
            style={{
              borderColor: "var(--border)",
              backgroundColor: "color-mix(in srgb, var(--background-card-strong) 92%, var(--background) 8%)",
            }}
          >
            <div className="flex items-start gap-3">
              <GameAvatar
                title={game.title}
                imageUrl={game.image_url}
                width={84}
                height={48}
                sizes="84px"
                className="h-12 w-[84px] shrink-0 rounded-xl object-contain"
              />

              <div className="min-w-0 flex-1">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-semibold" style={{ color: "var(--foreground)" }}>
                    {game.title}
                  </h3>
                  <p className="mt-1 text-sm" style={{ color: "var(--foreground-muted)" }}>
                    {formatReleaseDate(game.release_date)}
                  </p>
                </div>

                <p className="mt-2 text-sm" style={{ color: "var(--foreground-muted)" }}>
                  Critics {formatScore(game.avg_critic_score)} • Steam {formatScore(game.steam_user_score)} • MC {formatScore(game.metacritic_user_score)}
                </p>

                <div className="mt-3 flex flex-wrap gap-2">
                  {game.match_reasons.slice(0, 3).map((reason) => (
                    <span
                      key={reason}
                      className="rounded-full px-2.5 py-1 text-[11px] font-medium"
                      style={{
                        color: "var(--foreground-muted)",
                        backgroundColor: "color-mix(in srgb, var(--background) 35%, var(--background-card-strong) 65%)",
                        border: "1px solid color-mix(in srgb, var(--border) 85%, transparent 15%)",
                      }}
                    >
                      {reason}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
