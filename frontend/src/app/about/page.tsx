import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "Learn how ReviewDisparity calculates score disparities between critics and players. Understand our methodology, data sources, and scoring system.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: "How It Works - ReviewDisparity",
    description:
      "Learn how ReviewDisparity calculates score disparities between critics and players.",
    url: "/about",
  },
};

export default function AboutPage() {
  const jsonLdData = {
    "@context": "https://schema.org",
    "@type": "AboutPage",
    name: "How ReviewDisparity Works",
    description:
      "Learn how ReviewDisparity calculates score disparities between critics and players.",
    url: "/about",
  };

  return (
    <div className="max-w-4xl mx-auto space-y-12">
      <JsonLd data={jsonLdData} />
      {/* Hero */}
      <section className="text-center py-8">
        <h1 className="text-4xl font-bold mb-4" style={{ color: "var(--foreground)" }}>
          How It <span style={{ color: "var(--color-rust)" }}>Works</span>
        </h1>
        <p className="text-lg" style={{ color: "var(--foreground-muted)" }}>
          Understanding our methodology and data sources
        </p>
      </section>

      {/* What is Disparity */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          What is Review Disparity?
        </h2>
        <p className="mb-4" style={{ color: "var(--foreground-muted)" }}>
          Review disparity measures the difference between how professional game critics score a game
          versus how regular players rate it. A positive disparity means critics scored a game higher
          than players did, while a negative disparity means critics scored lower than players.
        </p>
        <div className="grid md:grid-cols-2 gap-4 mt-6">
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-2xl font-bold" style={{ color: "#BB3B0E" }}>+15</span>
              <span className="font-medium" style={{ color: "var(--foreground)" }}>Positive Disparity</span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Critics rated the game 15 points higher than players on average.
              This could indicate critic bias, marketing influence, or different evaluation criteria.
            </p>
          </div>
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-2xl font-bold" style={{ color: "#BB3B0E" }}>-15</span>
              <span className="font-medium" style={{ color: "var(--foreground)" }}>Negative Disparity</span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Critics rated the game 15 points lower than players.
              This could mean critics were harsher, or players found unexpected value in the game.
            </p>
          </div>
        </div>
        <p className="mt-4 text-sm" style={{ color: "var(--foreground-muted)" }}>
          <strong style={{ color: "var(--foreground)" }}>Note:</strong> What matters most is the
          <em> magnitude</em> of the disparity (how far from users), not the direction. A disparity
          of +15 or -15 both indicate a significant gap between critics and players.
        </p>
      </section>

      {/* Understanding Our Colors */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Understanding Our Colors
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Our color system is based on the <strong>magnitude</strong> of disparity—how far the critic
          score is from the user score, regardless of direction. This helps you quickly identify how
          aligned or divergent a critic is with players:
        </p>

        <div className="space-y-3">
          <div className="flex items-center gap-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(112, 129, 96, 0.15)" }}>
            <span className="text-xl font-bold w-16 text-center" style={{ color: "#708160" }}>±0-5</span>
            <div>
              <span className="font-semibold" style={{ color: "#708160" }}>Aligned</span>
              <span className="text-sm ml-2" style={{ color: "var(--foreground-muted)" }}>
                — Critic is closely aligned with user opinions
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(212, 160, 23, 0.15)" }}>
            <span className="text-xl font-bold w-16 text-center" style={{ color: "#D4A017" }}>±5-10</span>
            <div>
              <span className="font-semibold" style={{ color: "#D4A017" }}>Moderate</span>
              <span className="text-sm ml-2" style={{ color: "var(--foreground-muted)" }}>
                — Some divergence from user scores
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(221, 118, 49, 0.15)" }}>
            <span className="text-xl font-bold w-16 text-center" style={{ color: "#DD7631" }}>±10-15</span>
            <div>
              <span className="font-semibold" style={{ color: "#DD7631" }}>High</span>
              <span className="text-sm ml-2" style={{ color: "var(--foreground-muted)" }}>
                — Significant divergence from users
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(187, 59, 14, 0.15)" }}>
            <span className="text-xl font-bold w-16 text-center" style={{ color: "#BB3B0E" }}>±15+</span>
            <div>
              <span className="font-semibold" style={{ color: "#BB3B0E" }}>Extreme</span>
              <span className="text-sm ml-2" style={{ color: "var(--foreground-muted)" }}>
                — Major divergence from user opinions
              </span>
            </div>
          </div>
        </div>

        <p className="mt-6 text-sm" style={{ color: "var(--foreground-muted)" }}>
          The +/- sign still tells you the <em>direction</em> (positive means critic scored higher),
          but the color indicates <em>magnitude</em>. A +3 and -3 are both green because they&apos;re
          both closely aligned with users.
        </p>
      </section>

      {/* The Formula */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          The Formula
        </h2>
        <div
          className="p-6 rounded-lg text-center mb-6 font-mono text-lg"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--color-rust)" }}>Disparity</span>
          <span style={{ color: "var(--foreground-muted)" }}> = </span>
          <span style={{ color: "var(--color-rust)" }}>Critic Score</span>
          <span style={{ color: "var(--foreground-muted)" }}> − </span>
          <span style={{ color: "var(--color-sage)" }}>User Score</span>
        </div>
        <p style={{ color: "var(--foreground-muted)" }}>
          We calculate disparity for each review by subtracting the user score from the critic score.
          For journalists and outlets, we average all their individual review disparities to get an
          overall disparity score.
        </p>
      </section>

      {/* Launch Window Methodology */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Review Timing Categories
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          We categorize reviews based on when they were published relative to a game&apos;s release date.
          This helps identify review patterns and ensures fair disparity calculations.
        </p>

        <div className="grid md:grid-cols-3 gap-4 mb-6">
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300">
                Early Review
              </span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Reviews published <strong>before</strong> the game&apos;s official release date. These are typically
              from reviewers who received early access copies from publishers.
            </p>
          </div>
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300">
                Launch Window
              </span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Reviews published within <strong>60 days</strong> of the game&apos;s release. These are used for the
              <strong> primary disparity score</strong> shown on profiles.
            </p>
          </div>
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                Late Review
              </span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Reviews published <strong>more than 60 days</strong> after release. These count toward the
              overall disparity as a secondary metric.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "var(--foreground)" }}>Why 60 days?</strong> This window captures the period
              when most professional reviews are published and when user scores are most actively being submitted.
              It also prevents journalists from gaming their scores by selectively reviewing older games where
              user sentiment has shifted or stabilized.
            </p>
          </div>

          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#3B82F6" }}>About early reviews:</strong> Early reviews are included in
              disparity calculations and count toward the launch window. However, they&apos;re marked separately
              so you can see which critics frequently receive early access—a potential indicator of closer
              publisher relationships.
            </p>
          </div>
        </div>
      </section>

      {/* Two Disparity Scores */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Primary vs. Overall Disparity
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Each journalist and outlet has two disparity metrics calculated:
        </p>

        <div className="space-y-4 mb-6">
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-rust)" }}>
            <h3 className="font-semibold mb-1" style={{ color: "var(--foreground)" }}>Launch Window Disparity (Primary)</h3>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Calculated only from reviews published within 60 days of each game&apos;s release.
              This is the main metric displayed on profile pages and used for leaderboard rankings.
            </p>
          </div>

          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-sage)" }}>
            <h3 className="font-semibold mb-1" style={{ color: "var(--foreground)" }}>Overall Disparity (Secondary)</h3>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Calculated from all reviews, including late reviews. Used as a fallback when a journalist
              has no qualifying launch window reviews. When shown, it&apos;s marked with an asterisk (*).
            </p>
          </div>
        </div>

        <div
          className="p-4 rounded-lg"
          style={{ backgroundColor: "rgba(212, 160, 23, 0.15)", border: "1px solid rgba(212, 160, 23, 0.3)" }}
        >
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            <strong style={{ color: "#D4A017" }}>Transparency note:</strong> On journalist profiles, you&apos;ll see
            a breakdown showing how many of their reviews fall within the launch window vs. late reviews.
            If a journalist&apos;s disparity is calculated from overall reviews rather than launch window, this is
            clearly indicated.
          </p>
        </div>
      </section>

      {/* Minimum Thresholds */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Quality Thresholds
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          To ensure statistical reliability and prevent manipulation, we apply minimum thresholds:
        </p>

        <div className="space-y-4">
          <div className="flex items-start gap-4 p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 text-xl font-bold"
              style={{ backgroundColor: "var(--color-sage)", color: "white" }}
            >
              50
            </div>
            <div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Minimum User Reviews</h3>
              <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                Games must have at least 50 user reviews on Steam or Metacritic to be included in
                disparity calculations. This ensures we&apos;re comparing against a meaningful sample of
                player opinions, not just a handful of potentially biased early reviewers.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 text-xl font-bold"
              style={{ backgroundColor: "var(--color-rust)", color: "white" }}
            >
              10
            </div>
            <div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Minimum Critic Reviews for Journalists/Outlets</h3>
              <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                Journalists and outlets must have at least 10 scored reviews to appear on the leaderboards.
                This prevents new or occasional reviewers with just a few reviews from dominating the rankings
                due to small sample sizes.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 text-xl font-bold"
              style={{ backgroundColor: "var(--color-rust)", color: "white" }}
            >
              10
            </div>
            <div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Minimum Critic Reviews for Games</h3>
              <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                Games must have at least 10 critic reviews to appear on the games leaderboard.
                This ensures we have enough professional opinions to calculate a meaningful disparity score.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 text-xl font-bold"
              style={{ backgroundColor: "var(--color-orange)", color: "white" }}
            >
              10
            </div>
            <div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Minimum Score Spread</h3>
              <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                Journalists and outlets must have a score spread (standard deviation) of at least 10 to appear
                on leaderboards. This filters out reviewers who use binary scoring (only 0 or 100) or an
                extremely narrow scoring range, which can artificially inflate disparity metrics.
              </p>
            </div>
          </div>
        </div>

        <div
          className="p-4 rounded-lg mt-6"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            <strong style={{ color: "var(--foreground)" }}>Note:</strong> Individual journalist and game profiles are
            still accessible even if they don&apos;t meet the leaderboard thresholds—they just won&apos;t appear in
            the ranked lists.
          </p>
        </div>
      </section>

      {/* Score Normalization */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Score Normalization
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Different outlets use different scoring scales. To compare apples to apples, we normalize
          all scores to a 0-100 scale:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border)" }}>
                <th className="py-3 px-4 font-semibold" style={{ color: "var(--foreground)" }}>Original Format</th>
                <th className="py-3 px-4 font-semibold" style={{ color: "var(--foreground)" }}>Example</th>
                <th className="py-3 px-4 font-semibold" style={{ color: "var(--foreground)" }}>Normalized</th>
              </tr>
            </thead>
            <tbody style={{ color: "var(--foreground-muted)" }}>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-3 px-4">Out of 10</td>
                <td className="py-3 px-4">8.5 / 10</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-rust)" }}>85</td>
              </tr>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-3 px-4">Out of 5</td>
                <td className="py-3 px-4">4 / 5</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-rust)" }}>80</td>
              </tr>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-3 px-4">Out of 100</td>
                <td className="py-3 px-4">85 / 100</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-rust)" }}>85</td>
              </tr>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-3 px-4">Letter Grade</td>
                <td className="py-3 px-4">B+</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-rust)" }}>87</td>
              </tr>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="py-3 px-4">Steam (% positive)</td>
                <td className="py-3 px-4">85% positive</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-sage)" }}>85</td>
              </tr>
              <tr>
                <td className="py-3 px-4">Metacritic User</td>
                <td className="py-3 px-4">7.5 / 10</td>
                <td className="py-3 px-4 font-medium" style={{ color: "var(--color-orange)" }}>75</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Data Sources */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Data Sources
        </h2>
        <div className="space-y-6">
          <div className="flex gap-4">
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: "var(--color-rust)", color: "white" }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-lg" style={{ color: "var(--foreground)" }}>OpenCritic</h3>
              <p style={{ color: "var(--foreground-muted)" }}>
                Professional critic reviews, scores, and journalist profiles. OpenCritic aggregates
                reviews from major gaming publications and provides standardized critic scores.
              </p>
            </div>
          </div>

          <div className="flex gap-4">
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: "var(--color-sage)", color: "white" }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-lg" style={{ color: "var(--foreground)" }}>Steam</h3>
              <p style={{ color: "var(--foreground-muted)" }}>
                Player reviews and ratings from the world&apos;s largest PC gaming platform. Steam scores
                are based on the percentage of positive user reviews.
              </p>
            </div>
          </div>

          <div className="flex gap-4">
            <div
              className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: "var(--color-orange)", color: "white" }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-lg" style={{ color: "var(--foreground)" }}>Metacritic</h3>
              <p style={{ color: "var(--foreground-muted)" }}>
                User scores from Metacritic, which collects ratings from registered users on a 0-10 scale.
                We multiply by 10 to normalize to our 0-100 scale.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Three Disparity Scores */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Three Disparity Scores
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          We calculate and display disparity separately for each user score source, giving you
          a complete picture of how critics compare to different player communities:
        </p>

        <div className="space-y-4">
          {/* Steam Disparity */}
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-3 mb-2">
              <div
                className="w-8 h-8 rounded flex items-center justify-center"
                style={{ backgroundColor: "var(--color-sage)", color: "white" }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                </svg>
              </div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Steam Disparity</h3>
            </div>
            <p className="text-sm ml-11" style={{ color: "var(--foreground-muted)" }}>
              <span className="font-mono">Critic Score − Steam User Score</span><br/>
              Compares critic reviews against Steam&apos;s PC gaming community. Steam users tend to be
              dedicated PC gamers who may have different expectations than the general gaming audience.
            </p>
          </div>

          {/* Metacritic Disparity */}
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-3 mb-2">
              <div
                className="w-8 h-8 rounded flex items-center justify-center"
                style={{ backgroundColor: "var(--color-orange)", color: "white" }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
              </div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Metacritic Disparity</h3>
            </div>
            <p className="text-sm ml-11" style={{ color: "var(--foreground-muted)" }}>
              <span className="font-mono">Critic Score − Metacritic User Score</span><br/>
              Compares critic reviews against Metacritic&apos;s cross-platform user ratings. Metacritic
              includes console and PC players, often reflecting a broader gaming audience.
            </p>
          </div>

          {/* Combined Disparity */}
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-3 mb-2">
              <div
                className="w-8 h-8 rounded flex items-center justify-center"
                style={{ backgroundColor: "var(--color-rust)", color: "white" }}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10"/>
                  <line x1="12" y1="20" x2="12" y2="4"/>
                  <line x1="6" y1="20" x2="6" y2="14"/>
                </svg>
              </div>
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>Combined Disparity</h3>
            </div>
            <p className="text-sm ml-11" style={{ color: "var(--foreground-muted)" }}>
              <span className="font-mono">Critic Score − Average(Steam, Metacritic)</span><br/>
              When both sources are available, we also show a combined disparity using the average
              of Steam and Metacritic user scores. This provides an overall view across platforms.
            </p>
          </div>
        </div>

        <div
          className="p-4 rounded-lg mt-6"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            <strong style={{ color: "var(--foreground)" }}>Why show all three?</strong> Steam and
            Metacritic audiences can differ significantly. A game might have a +10 disparity on
            Metacritic but -5 on Steam, revealing that PC players loved it more than the broader
            audience. Seeing each source independently helps you understand the full picture.
          </p>
        </div>
      </section>

      {/* Score Spread vs Disparity */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Score Spread vs. Disparity
        </h2>
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          On journalist and outlet profiles, you&apos;ll see both <strong>Disparity</strong> and{" "}
          <strong>Score Spread</strong>. These measure different things:
        </p>

        <div className="grid md:grid-cols-2 gap-6 mb-6">
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-rust)" }}>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>
              Disparity
            </h3>
            <p className="text-sm mb-3" style={{ color: "var(--foreground-muted)" }}>
              How far the critic&apos;s scores are from <strong>user scores</strong> (Steam/Metacritic).
            </p>
            <div className="text-sm font-mono p-2 rounded" style={{ backgroundColor: "var(--background)", color: "var(--color-rust)" }}>
              Critic Score − User Score
            </div>
            <p className="text-xs mt-2" style={{ color: "var(--foreground-muted)" }}>
              Example: A critic gives 90, users give 70 → Disparity is +20
            </p>
          </div>

          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-sage)" }}>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>
              Score Spread
            </h3>
            <p className="text-sm mb-3" style={{ color: "var(--foreground-muted)" }}>
              How varied the critic&apos;s <strong>own scores</strong> are (variance in their scoring).
            </p>
            <div className="text-sm font-mono p-2 rounded" style={{ backgroundColor: "var(--background)", color: "var(--color-sage)" }}>
              Standard Deviation of Critic&apos;s Scores
            </div>
            <p className="text-xs mt-2" style={{ color: "var(--foreground-muted)" }}>
              Example: Scores range from 40 to 95 → High spread (uses full range)
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(112, 129, 96, 0.15)", border: "1px solid rgba(112, 129, 96, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#708160" }}>High Score Spread (10+):</strong> The critic uses a wide
              range of scores, differentiating between games they love and games they don&apos;t. This suggests
              thoughtful, discriminating reviews. These reviewers appear on leaderboards.
            </p>
          </div>

          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(212, 160, 23, 0.15)", border: "1px solid rgba(212, 160, 23, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#D4A017" }}>Low Score Spread (&lt;10):</strong> The critic gives similar
              scores to most games, or uses binary scoring (only 0s and 100s). This can artificially inflate
              disparity metrics and make their scores less meaningful.
            </p>
          </div>
        </div>

        <div
          className="p-4 rounded-lg mt-6"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <h4 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>
            How we handle low score spread reviewers:
          </h4>
          <ul className="text-sm space-y-2" style={{ color: "var(--foreground-muted)" }}>
            <li className="flex items-start gap-2">
              <span style={{ color: "var(--color-rust)" }}>•</span>
              <span><strong>Leaderboards:</strong> Journalists and outlets with score spread below 10 are excluded from leaderboard rankings to prevent skewed data.</span>
            </li>
            <li className="flex items-start gap-2">
              <span style={{ color: "var(--color-sage)" }}>•</span>
              <span><strong>Profile pages:</strong> Their individual profiles remain fully accessible with all their reviews and statistics.</span>
            </li>
            <li className="flex items-start gap-2">
              <span style={{ color: "var(--color-orange)" }}>•</span>
              <span><strong>Warning indicator:</strong> A warning message appears on profiles when score spread is below 10, helping you understand why their disparity might be less reliable.</span>
            </li>
            <li className="flex items-start gap-2">
              <span style={{ color: "var(--foreground-muted)" }}>•</span>
              <span><strong>Search results:</strong> They still appear in search results on the Journalists and Outlets listing pages.</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Data Coverage */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Data Coverage
        </h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>Time Period</h3>
            <p style={{ color: "var(--foreground-muted)" }}>
              We track all available review data from OpenCritic, going back to the earliest reviews
              in their database. This gives us comprehensive coverage of gaming journalism history
              and allows tracking of long-term reviewer patterns.
            </p>
          </div>
          <div>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>Update Frequency</h3>
            <p style={{ color: "var(--foreground-muted)" }}>
              Critic reviews are synced continuously from OpenCritic. User scores from Steam and Metacritic
              are updated regularly. Historical disparity data powers our trend charts, showing how
              journalists&apos; alignment with users has changed over time.
            </p>
          </div>
        </div>
      </section>

      {/* Interpreting Results */}
      <section className="bg-white rounded-lg shadow p-8">
        <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Interpreting the Data
        </h2>
        <div className="space-y-4" style={{ color: "var(--foreground-muted)" }}>
          <p>
            <strong style={{ color: "var(--foreground)" }}>High disparity doesn&apos;t mean &quot;wrong&quot;:</strong> Critics
            and players often have different priorities. Critics may weigh innovation, artistic merit,
            and technical achievement more heavily, while players focus on fun, value, and replay value.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Direction vs. magnitude:</strong> The sign (+/-)
            tells you whether the critic scored higher or lower than users, but the <em>magnitude</em> (how
            far from zero) is what matters most. A critic with +12 and one with -12 both have significant
            divergence from users—they just diverge in opposite directions.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Sample size matters:</strong> A journalist with
            5 reviews will have a less reliable disparity score than one with 500 reviews. We display
            review counts so you can judge the statistical significance yourself. Journalists need at least
            10 reviews to appear on leaderboards.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Check score spread:</strong> A journalist&apos;s
            &quot;Score Spread&quot; tells you how varied their own scores are. Low spread means they give
            similar scores to most games (or use binary 0/100 scoring), which can make their disparity
            less meaningful. We filter out very low spread reviewers from leaderboards.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Launch window focus:</strong> Our primary disparity
            score uses only reviews published within 60 days of a game&apos;s release. This ensures we&apos;re
            measuring how aligned critics are with players when it matters most—at launch.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Context is key:</strong> Some genres naturally
            have higher disparities. Niche games may be loved by their target audience but rated lower
            by critics reviewing for a general audience.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Compare sources:</strong> A journalist might be
            aligned with Steam users but divergent from Metacritic users, or vice versa. Checking all
            three disparity scores (Steam, Metacritic, Combined) gives you the complete picture.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="text-center py-8">
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Ready to explore the data?
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            href="/journalists"
            className="px-6 py-3 text-white rounded-lg font-medium hover:opacity-90 transition-opacity"
            style={{ backgroundColor: "var(--color-rust)" }}
          >
            Browse Journalists
          </Link>
          <Link
            href="/leaderboards"
            className="px-6 py-3 rounded-lg font-medium hover:opacity-80 transition-opacity"
            style={{ backgroundColor: "var(--color-sage)", color: "white" }}
          >
            View Leaderboards
          </Link>
        </div>
      </section>
    </div>
  );
}
