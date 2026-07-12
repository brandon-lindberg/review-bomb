import { buildEntityPath } from "./entity-paths";
import { getDisplayDisparity } from "./disparity-colors";
import type {
  GameWithScores,
  JournalistDetail,
  OutletWithStats,
  ReviewWithDisparity,
  ReviewWithJournalist,
  SimilarGame,
  SiteStats,
} from "../types";

// Markdown representations of public pages, built from the same structured
// API data the HTML pages render. Served via `Accept: text/markdown`
// content negotiation (see src/proxy.ts and src/app/md/[[...slug]]/route.ts).
// Keep these pure so they stay unit-testable without a server.

const DISPARITY_NOTE =
  "Disparity = critic score minus player score on a 0-100 scale. Positive disparity means critics scored higher than players.";

function escapeCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();
}

function formatScore(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(Number(value))) return "N/A";
  return Number(value).toFixed(digits);
}

function formatSignedScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "N/A";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "unknown date";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "unknown date";
  return parsed.toISOString().slice(0, 10);
}

function canonicalLine(siteUrl: string, path: string): string {
  return `Canonical URL: ${siteUrl}${path}`;
}

function footerLines(siteUrl: string): string[] {
  return [
    "---",
    "",
    `Source: ReviewDisparity (${siteUrl}). ${DISPARITY_NOTE}`,
    `More: [Games](${siteUrl}/games) | [Journalists](${siteUrl}/journalists) | [Outlets](${siteUrl}/outlets) | [Leaderboards](${siteUrl}/leaderboards) | [About](${siteUrl}/about) | [FAQ](${siteUrl}/faq)`,
    "",
  ];
}

function reviewRowsForGame(siteUrl: string, reviews: ReviewWithJournalist[]): string[] {
  if (reviews.length === 0) return [];

  const rows = reviews.map((review) => {
    const journalist = review.journalist_public_id
      ? `[${escapeCell(review.journalist_name)}](${siteUrl}${buildEntityPath("journalists", review.journalist_name, review.journalist_public_id)})`
      : escapeCell(review.journalist_name);
    const outlet = review.outlet_name
      ? review.outlet_public_id
        ? `[${escapeCell(review.outlet_name)}](${siteUrl}${buildEntityPath("outlets", review.outlet_name, review.outlet_public_id)})`
        : escapeCell(review.outlet_name)
      : "-";
    const score =
      review.score_normalized != null
        ? `${formatScore(review.score_normalized)}/100`
        : escapeCell(review.score_raw || "N/A");
    return `| ${journalist} | ${outlet} | ${score} | ${formatDate(review.published_at)} |`;
  });

  return [
    "| Critic | Outlet | Score | Published |",
    "| --- | --- | --- | --- |",
    ...rows,
  ];
}

export interface GameMarkdownInput {
  siteUrl: string;
  game: GameWithScores;
  reviews: ReviewWithJournalist[];
  totalReviewCount: number;
  similarGames: SimilarGame[];
}

export function buildGameMarkdown({
  siteUrl,
  game,
  reviews,
  totalReviewCount,
  similarGames,
}: GameMarkdownInput): string {
  const canonicalPath = buildEntityPath("games", game.title, game.public_id);
  const disparity = getDisplayDisparity(game.disparity_steam, game.disparity_metacritic);

  const lines: string[] = [
    `# ${game.title} — Critic vs User Scores`,
    "",
    canonicalLine(siteUrl, canonicalPath),
    "",
  ];

  if (game.release_date) lines.push(`- Release date: ${formatDate(game.release_date)}`);
  lines.push(`- Critic average: ${formatScore(game.avg_critic_score, 1)} (${game.critic_review_count ?? 0} reviews)`);
  lines.push(
    `- Steam user score: ${formatScore(game.steam_user_score)}${game.steam_sample_size ? ` (${game.steam_sample_size.toLocaleString("en-US")} reviews)` : ""}`
  );
  lines.push(
    `- Metacritic user score: ${formatScore(game.metacritic_user_score)}${game.metacritic_sample_size ? ` (${game.metacritic_sample_size.toLocaleString("en-US")} reviews)` : ""}`
  );
  lines.push(`- Disparity (critic minus player): ${formatSignedScore(disparity)}`);
  if (game.disparity_steam != null) lines.push(`  - vs Steam: ${formatSignedScore(game.disparity_steam)}`);
  if (game.disparity_metacritic != null) lines.push(`  - vs Metacritic: ${formatSignedScore(game.disparity_metacritic)}`);

  const early = game.early_review_count ?? 0;
  const launch = game.launch_window_review_count ?? 0;
  const late = game.late_review_count ?? 0;
  if (early + launch + late > 0) {
    lines.push(`- Review timing: ${early} early, ${launch} launch window, ${late} late`);
  }
  lines.push("", DISPARITY_NOTE, "");

  if (game.description) {
    lines.push("## About", "", game.description.trim(), "");
  }

  if (reviews.length > 0) {
    const shownNote =
      totalReviewCount > reviews.length
        ? ` (showing ${reviews.length} most recent of ${totalReviewCount})`
        : "";
    lines.push(`## Critic reviews${shownNote}`, "", ...reviewRowsForGame(siteUrl, reviews), "");
  }

  if (similarGames.length > 0) {
    lines.push("## Similar games", "");
    for (const similar of similarGames) {
      lines.push(
        `- [${similar.title}](${siteUrl}${buildEntityPath("games", similar.title, similar.public_id)}): critic ${formatScore(similar.avg_critic_score, 1)}, Steam ${formatScore(similar.steam_user_score)}, Metacritic ${formatScore(similar.metacritic_user_score)}`
      );
    }
    lines.push("");
  }

  lines.push(...footerLines(siteUrl));
  return lines.join("\n");
}

export interface JournalistMarkdownInput {
  siteUrl: string;
  journalist: JournalistDetail;
  reviews: ReviewWithDisparity[];
  totalReviewCount: number;
}

export function buildJournalistMarkdown({
  siteUrl,
  journalist,
  reviews,
  totalReviewCount,
}: JournalistMarkdownInput): string {
  const canonicalPath = buildEntityPath("journalists", journalist.name, journalist.public_id);
  const stats = journalist.stats;

  const lines: string[] = [
    `# ${journalist.name} — Critic Score Alignment`,
    "",
    canonicalLine(siteUrl, canonicalPath),
    "",
    `- Reviews tracked: ${stats.total_reviews}`,
    `- Average score given: ${formatScore(stats.avg_score_given, 1)}`,
    `- Launch-window disparity vs players: ${formatSignedScore(stats.avg_disparity_combined)}`,
    `- Overall disparity vs players: ${formatSignedScore(stats.overall_disparity_combined)}`,
    `- Review timing: ${stats.early_review_count} early, ${stats.launch_window_review_count} launch window, ${stats.late_review_count} late`,
  ];
  if (stats.min_score_given != null && stats.max_score_given != null) {
    lines.push(`- Score range given: ${formatScore(stats.min_score_given)}-${formatScore(stats.max_score_given)}`);
  }
  lines.push("", DISPARITY_NOTE, "");

  if (journalist.bio) {
    lines.push("## Bio", "", journalist.bio.trim(), "");
  }

  if (journalist.outlet_breakdown.length > 0) {
    lines.push("## Outlets", "");
    for (const outlet of journalist.outlet_breakdown) {
      lines.push(`- ${outlet.outlet_name}: ${outlet.review_count} reviews`);
    }
    lines.push("");
  }

  if (reviews.length > 0) {
    const shownNote =
      totalReviewCount > reviews.length
        ? ` (showing ${reviews.length} most recent of ${totalReviewCount})`
        : "";
    lines.push(
      `## Recent reviews${shownNote}`,
      "",
      "| Game | Score | Disparity | Published |",
      "| --- | --- | --- | --- |",
      ...reviews.map((review) => {
        const game = review.game_public_id
          ? `[${escapeCell(review.game_title)}](${siteUrl}${buildEntityPath("games", review.game_title, review.game_public_id)})`
          : escapeCell(review.game_title);
        const score =
          review.score_normalized != null
            ? `${formatScore(review.score_normalized)}/100`
            : escapeCell(review.score_raw || "N/A");
        return `| ${game} | ${score} | ${formatSignedScore(review.disparity)} | ${formatDate(review.published_at)} |`;
      }),
      ""
    );
  }

  lines.push(...footerLines(siteUrl));
  return lines.join("\n");
}

export interface OutletMarkdownInput {
  siteUrl: string;
  outlet: OutletWithStats;
  reviews: ReviewWithJournalist[];
  totalReviewCount: number;
}

export function buildOutletMarkdown({
  siteUrl,
  outlet,
  reviews,
  totalReviewCount,
}: OutletMarkdownInput): string {
  const canonicalPath = buildEntityPath("outlets", outlet.name, outlet.public_id);

  const lines: string[] = [
    `# ${outlet.name} — Outlet Score Alignment`,
    "",
    canonicalLine(siteUrl, canonicalPath),
    "",
    `- Journalists tracked: ${outlet.journalist_count}`,
    `- Reviews tracked: ${outlet.review_count}`,
    `- Average score given: ${formatScore(outlet.avg_score, 1)}`,
    `- Average disparity vs players: ${formatSignedScore(outlet.avg_disparity_combined ?? outlet.avg_disparity)}`,
  ];
  if (outlet.website_url) lines.push(`- Website: ${outlet.website_url}`);
  lines.push("", DISPARITY_NOTE, "");

  if (reviews.length > 0) {
    const shownNote =
      totalReviewCount > reviews.length
        ? ` (showing ${reviews.length} most recent of ${totalReviewCount})`
        : "";
    lines.push(
      `## Recent reviews${shownNote}`,
      "",
      "| Game | Critic | Score | Published |",
      "| --- | --- | --- | --- |",
      ...reviews.map((review) => {
        const game =
          review.game_title && review.game_public_id
            ? `[${escapeCell(review.game_title)}](${siteUrl}${buildEntityPath("games", review.game_title, review.game_public_id)})`
            : escapeCell(review.game_title ?? "-");
        const journalist = review.journalist_public_id
          ? `[${escapeCell(review.journalist_name)}](${siteUrl}${buildEntityPath("journalists", review.journalist_name, review.journalist_public_id)})`
          : escapeCell(review.journalist_name);
        const score =
          review.score_normalized != null
            ? `${formatScore(review.score_normalized)}/100`
            : escapeCell(review.score_raw || "N/A");
        return `| ${game} | ${journalist} | ${score} | ${formatDate(review.published_at)} |`;
      }),
      ""
    );
  }

  lines.push(...footerLines(siteUrl));
  return lines.join("\n");
}

export interface HomeMarkdownInput {
  siteUrl: string;
  stats: SiteStats | null;
  recentReviews: ReviewWithJournalist[];
}

export function buildHomeMarkdown({ siteUrl, stats, recentReviews }: HomeMarkdownInput): string {
  const lines: string[] = [
    "# ReviewDisparity — Game Critic vs User Score Tracker",
    "",
    canonicalLine(siteUrl, "/"),
    "",
    "ReviewDisparity tracks the gap between professional game critic review scores and real player scores from Steam and Metacritic. It surfaces which critics and outlets align with players and which diverge.",
    "",
    DISPARITY_NOTE,
    "",
  ];

  if (stats) {
    lines.push(
      "## Coverage",
      "",
      `- Games tracked: ${stats.total_games.toLocaleString("en-US")}`,
      `- Journalists tracked: ${stats.total_journalists.toLocaleString("en-US")}`,
      `- Outlets tracked: ${stats.total_outlets.toLocaleString("en-US")}`,
      `- Reviews tracked: ${stats.total_reviews.toLocaleString("en-US")}`,
      ""
    );
  }

  if (recentReviews.length > 0) {
    lines.push(
      "## Latest critic reviews",
      "",
      "| Game | Critic | Outlet | Score | Disparity |",
      "| --- | --- | --- | --- | --- |",
      ...recentReviews.map((review) => {
        const game =
          review.game_title && review.game_public_id
            ? `[${escapeCell(review.game_title)}](${siteUrl}${buildEntityPath("games", review.game_title, review.game_public_id)})`
            : escapeCell(review.game_title ?? "-");
        const journalist = review.journalist_public_id
          ? `[${escapeCell(review.journalist_name)}](${siteUrl}${buildEntityPath("journalists", review.journalist_name, review.journalist_public_id)})`
          : escapeCell(review.journalist_name);
        const score =
          review.score_normalized != null
            ? `${formatScore(review.score_normalized)}/100`
            : escapeCell(review.score_raw || "N/A");
        return `| ${game} | ${journalist} | ${escapeCell(review.outlet_name ?? "-")} | ${score} | ${formatSignedScore(review.disparity)} |`;
      }),
      ""
    );
  }

  lines.push(
    "## Explore",
    "",
    `- [Games](${siteUrl}/games): critic vs player score gaps per game`,
    `- [Journalists](${siteUrl}/journalists): critics ranked by player alignment`,
    `- [Outlets](${siteUrl}/outlets): publications and their aggregate disparity`,
    `- [Leaderboards](${siteUrl}/leaderboards): biggest disparities and most aligned`,
    `- [News](${siteUrl}/news): gaming news from tracked publications`,
    `- [Sitemap](${siteUrl}/sitemap.xml)`,
    "",
    "Any of the pages above, and every game/journalist/outlet detail page, can be fetched as Markdown by sending an `Accept: text/markdown` request header to the canonical URL.",
    ""
  );

  lines.push(...footerLines(siteUrl));
  return lines.join("\n");
}
