import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getGame } from "@/lib/api";
import { DisparityScoreCards } from "@/components/DisparityScores";
import { ScoreDisplay } from "@/components/ScoreDisplay";
import { LazyChartSection } from "@/components/LazyChartSection";
import { JsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  try {
    const game = await getGame(parseInt(id));
    const criticScore = game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(0) : null;
    const userScore = game.steam_user_score != null
      ? Number(game.steam_user_score).toFixed(0)
      : game.metacritic_user_score != null
        ? Number(game.metacritic_user_score).toFixed(0)
        : null;
    const disparity = game.disparity_steam ?? game.disparity_metacritic;
    const disparityStr = disparity != null ? `${Number(disparity) > 0 ? "+" : ""}${Number(disparity).toFixed(0)}` : null;

    let description = `${game.title} critic vs user review scores.`;
    if (criticScore && userScore && disparityStr) {
      description = `${game.title}: critic score ${criticScore} vs user score ${userScore} (${disparityStr} disparity). See all ${game.critic_review_count || 0} critic reviews.`;
    }

    return {
      title: `${game.title} - Critic vs User Scores`,
      description,
      alternates: { canonical: `/games/${id}` },
      openGraph: {
        title: `${game.title} - Critic vs User Scores | ReviewDisparity`,
        description,
        url: `/games/${id}`,
        type: "article",
      },
      twitter: { card: "summary", title: game.title, description },
    };
  } catch {
    return { title: "Game Details" };
  }
}

export default async function GameDetailPage({ params }: PageProps) {
  const { id } = await params;

  let game = null;

  try {
    game = await getGame(parseInt(id));
  } catch (error) {
    console.error("Error fetching game:", error);
    notFound();
  }

  if (!game) {
    notFound();
  }

  const jsonLdData: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "VideoGame",
    name: game.title,
    url: `/games/${id}`,
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
            {game.description && (
              <p className="mt-4 text-gray-600">{game.description}</p>
            )}
          </div>

          <ScoreDisplay
            criticScore={game.avg_critic_score}
            userScore={game.steam_user_score || game.metacritic_user_score}
            size="lg"
          />
        </div>

        {/* Score Breakdown */}
        <div className="mt-6 pt-6 border-t border-gray-200">
          <h2 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
            Score Breakdown
          </h2>
          <div className="grid grid-cols-3 gap-4">
            <ScoreCard
              label="Critic Average"
              value={game.avg_critic_score != null ? Number(game.avg_critic_score).toFixed(1) : undefined}
              subtitle={`${game.critic_review_count || 0} reviews`}
            />
            <ScoreCard
              label="Steam User Score"
              value={game.steam_user_score != null ? Number(game.steam_user_score).toFixed(0) : undefined}
              subtitle={
                game.steam_sample_size
                  ? `${game.steam_sample_size.toLocaleString()} reviews`
                  : undefined
              }
            />
            <ScoreCard
              label="Metacritic User Score"
              value={game.metacritic_user_score != null ? Number(game.metacritic_user_score).toFixed(0) : undefined}
              subtitle={
                game.metacritic_sample_size
                  ? `${game.metacritic_sample_size.toLocaleString()} reviews`
                  : undefined
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
            combinedDisparity={game.disparity_steam != null && game.disparity_metacritic != null
              ? (Number(game.disparity_steam) + Number(game.disparity_metacritic)) / 2
              : game.disparity_steam ?? game.disparity_metacritic}
            steamUserScore={game.steam_user_score}
            metacriticUserScore={game.metacritic_user_score}
            criticScore={game.avg_critic_score}
          />
        </div>
      </div>

      {/* Disparity Chart + Critic Reviews + Journalist Alignment - lazy loaded on scroll */}
      <LazyChartSection entityType="game" entityId={parseInt(id)} gameTitle={game.title} />
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
