import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getGame, getGameNews } from "@/lib/api";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { LazyChartSection } from "@/components/LazyChartSection";
import { JsonLd } from "@/components/JsonLd";
import { getDisplayDisparity } from "@/lib/disparity-colors";
import { ShareButtons } from "@/components/ShareButtons";
import { getSiteUrl } from "@/lib/site-url";

export const revalidate = 60;
const GAME_CARD_VERSION = "g5";

function buildGameSnapshotVersion(game: {
  critic_review_count?: number | null;
  avg_critic_score?: number | null;
  steam_user_score?: number | null;
  metacritic_user_score?: number | null;
  disparity_steam?: number | null;
  disparity_metacritic?: number | null;
}): string {
  const disparity = getDisplayDisparity(game.disparity_steam ?? null, game.disparity_metacritic ?? null);
  return [
    (game.critic_review_count ?? 0).toString(),
    game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(2) : "na",
    game.steam_user_score != null ? Number(game.steam_user_score).toFixed(2) : "na",
    game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(2) : "na",
    disparity != null ? Number(disparity).toFixed(2) : "na",
  ].join("-");
}

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { id } = await params;
  const query = await searchParams;
  const siteUrl = getSiteUrl();
  try {
    const game = await getGame(id);
    const canonicalId = game.public_id;
    const requestedCardVersion = query.card?.trim() || GAME_CARD_VERSION;
    const snapshotVersion = query.v?.trim() || buildGameSnapshotVersion(game);
    const isCardShareUrl = query.card != null || query.v != null;
    const sharePageUrl = `${siteUrl}/games/${canonicalId}?${new URLSearchParams({
      card: requestedCardVersion,
      v: snapshotVersion,
    }).toString()}`;
    const criticScore = game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : null;
    const steamUserScore = game.steam_user_score != null ? Number(game.steam_user_score).toFixed(0) : null;
    const metacriticUserScore = game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(0) : null;
    const userScoreSummary = steamUserScore && metacriticUserScore
      ? `Steam ${steamUserScore} | MC ${metacriticUserScore}`
      : steamUserScore
        ? `Steam ${steamUserScore}`
        : metacriticUserScore
          ? `MC ${metacriticUserScore}`
          : null;
    const disparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(0)}` : null;
    const ogParams = new URLSearchParams({
      kind: "game",
      name: game.title,
      subtitle: "Critic vs player score snapshot",
      disparity: disparity != null ? Number(disparity).toFixed(1) : "",
      reviews: (game.critic_review_count ?? 0).toString(),
      score: criticScore ?? "N/A",
      steam: steamUserScore ?? "N/A",
      mc: metacriticUserScore ?? "N/A",
      extra: userScoreSummary ? `User scores ${userScoreSummary}` : "User scores N/A",
      card: requestedCardVersion,
      v: snapshotVersion,
    });
    const imageKey = encodeURIComponent(`${requestedCardVersion}-${snapshotVersion}`);
    const openGraphImage = `${siteUrl}/og/entity/${imageKey}?${ogParams.toString()}`;

    let description = `${game.title} critic vs user review scores.`;
    if (criticScore && userScoreSummary && disparityStr) {
      description = `${game.title}: critic score ${criticScore} vs ${userScoreSummary} (${disparityStr} disparity). See all ${game.critic_review_count || 0} critic reviews.`;
    }

    return {
      title: `${game.title} - Critic vs User Scores`,
      description,
      alternates: isCardShareUrl ? undefined : { canonical: `/games/${canonicalId}` },
      ...(isCardShareUrl && { robots: { index: false, follow: true } }),
      openGraph: {
        title: `${game.title} - Critic vs User Scores | ReviewDisparity`,
        description,
        url: isCardShareUrl ? sharePageUrl : `${siteUrl}/games/${canonicalId}`,
        type: "article",
        images: [{ url: openGraphImage, width: 1200, height: 630, alt: `${game.title} review disparity snapshot` }],
      },
      twitter: {
        card: "summary_large_image",
        title: game.title,
        description,
        images: [openGraphImage],
      },
    };
  } catch {
    return { title: "Game Details" };
  }
}

export default async function GameDetailPage({ params }: PageProps) {
  const { id } = await params;

  let game = null;
  let newsArticles: Awaited<ReturnType<typeof getGameNews>>["items"] = [];
  let newsTotalPages = 0;

  try {
    game = await getGame(id);
  } catch (error) {
    console.error("Error fetching game:", error);
    notFound();
  }

  if (!game) {
    notFound();
  }

  if (id !== game.public_id) {
    redirect(`/games/${game.public_id}`);
  }

  try {
    const newsResponse = await getGameNews(game.public_id, 1, 5);
    newsArticles = newsResponse.items;
    newsTotalPages = newsResponse.total_pages;
  } catch {
    // News is non-critical — silently continue without it
  }

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "VideoGame",
    name: game.title,
    url: `/games/${game.public_id}`,
    ...(game.release_date && { datePublished: game.release_date }),
    ...(game.description && { description: game.description }),
    ...(game.avg_critic_score != null && {
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: Number(game.avg_critic_score).toFixed(1),
        bestRating: 100,
        worstRating: 0,
        ratingCount: game.critic_review_count || 1,
      },
    }),
  };

  const shareDisparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);
  const shareDisparityStr = shareDisparity != null ? `${Number(shareDisparity) > 0 ? "+" : ""}${Number(shareDisparity).toFixed(0)}` : null;
  const shareCriticScore = game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : null;
  const shareSnapshotVersion = buildGameSnapshotVersion(game);
  const shareUrl = `${getSiteUrl()}/games/${game.public_id}?card=${GAME_CARD_VERSION}&v=${encodeURIComponent(shareSnapshotVersion)}`;
  const hasBothUserScores = game.steam_user_score != null && game.metacritic_user_score != null;
  const shareTextParts = [`${game.title} on Review Disparity`];
  if (shareCriticScore) shareTextParts.push(`Critics: ${shareCriticScore}`);
  if (hasBothUserScores) {
    shareTextParts.push(`Steam: ${Number(game.steam_user_score).toFixed(0)}`);
    shareTextParts.push(`MC: ${Number(game.metacritic_user_score).toFixed(0)}`);
  } else if (game.steam_user_score != null) {
    shareTextParts.push(`Users: ${Number(game.steam_user_score).toFixed(0)}`);
  } else if (game.metacritic_user_score != null) {
    shareTextParts.push(`Users: ${Number(game.metacritic_user_score).toFixed(0)}`);
  }
  if (shareDisparityStr) shareTextParts.push(`Disparity: ${shareDisparityStr}`);
  const shareText = shareTextParts.join(" — ");

  return (
    <div className="space-y-8">
      <JsonLd data={jsonLdData} />
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
          <div className="flex-1">
            <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>{game.title}</h1>
            {game.release_date && (
              <p className="mt-2 text-sm text-gray-500">
                Released: {new Date(game.release_date).toLocaleDateString()}
              </p>
            )}
            <div className="mt-3">
              <ShareButtons url={shareUrl} text={shareText} />
            </div>
            {game.description && (
              <p className="mt-4 text-gray-600">{game.description}</p>
            )}
          </div>

          <ScoreDisplay
            criticScore={game.avg_critic_score}
            steamUserScore={game.steam_user_score}
            metacriticUserScore={game.metacritic_user_score}
            size="lg"
          />
        </div>

        {/* Score Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Score Breakdown
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(1) : undefined}
              subtitle={`${game.critic_review_count || 0} reviews`}
            />
            <ScoreCard
              label="Steam User Score"
              value={game.steam_user_score != null ? Number(game.steam_user_score).toFixed(0) : undefined}
              subtitle={
                game.steam_user_score != null
                  ? game.steam_sample_size
                    ? `${game.steam_sample_size.toLocaleString()} reviews`
                    : undefined
                  : "Less than 50 reviews"
              }
            />
            <ScoreCard
              label="Metacritic User Score"
              value={game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(0) : undefined}
              subtitle={
                game.metacritic_user_score != null
                  ? game.metacritic_sample_size
                    ? `${game.metacritic_sample_size.toLocaleString()} reviews`
                    : undefined
                  : "Less than 20 reviews"
              }
            />
          </div>
        </div>

        {/* Disparity Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Disparity Breakdown
          </h2>
          <DisparityScoreCards
            steamDisparity={game.disparity_steam}
            metacriticDisparity={game.disparity_metacritic}
            combinedDisparity={getDisplayDisparity(game.disparity_steam, game.disparity_metacritic)}
          />
        </div>

        {/* Review Timing Breakdown */}
        {(game.early_review_count != null || game.launch_window_review_count != null || game.late_review_count != null) && (() => {
          const early = game.early_review_count ?? 0;
          const launchWindow = game.launch_window_review_count ?? 0;
          const late = game.late_review_count ?? 0;
          const timingTotal = early + launchWindow + late;
          if (timingTotal === 0) return null;
          const pct = (n: number) => timingTotal > 0 ? ((n / timingTotal) * 100).toFixed(0) : "0";

          return (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <h2 className="text-lg font-semibold mb-3" style={{ color: "var(--foreground)" }}>
                Review Timing
              </h2>
              <div className="text-xs flex flex-wrap gap-x-3 gap-y-1" style={{ color: "var(--foreground-muted)" }}>
                {early > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                    {early} early ({pct(early)}%)
                  </span>
                )}
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-500"></span>
                  {launchWindow} launch window ({pct(launchWindow)}%)
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  {late} late ({pct(late)}%)
                </span>
              </div>
            </div>
          );
        })()}
      </div>

      {/* Disparity Chart + Critic Reviews + Journalist Alignment + News - lazy loaded on scroll */}
      <LazyChartSection
        entityType="game"
        entityId={game.public_id}
        gameTitle={game.title}
        newsArticles={newsArticles}
        newsTotalPages={newsTotalPages}
        timingCounts={{
          early: game.early_review_count ?? 0,
          launchWindow: game.launch_window_review_count ?? 0,
          late: game.late_review_count ?? 0,
        }}
      />
    </div>
  );
}

function ScoreCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value?: string;
  subtitle?: string;
}) {
  return (
    <div className="p-4 bg-gray-50 rounded-lg text-center">
      <p className="text-2xl font-bold text-gray-900">{value ?? "N/A"}</p>
      <p className="text-sm font-medium text-gray-700">{label}</p>
      {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
    </div>
  );
}
