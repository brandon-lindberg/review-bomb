import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "Learn how ReviewDisparity calculates score disparities between critics and players. Understand our methodology, data sources, chart views, and scoring system.",
  alternates: { canonical: "/about" },
  openGraph: {
    title: "How It Works - ReviewDisparity",
    description:
      "Learn how ReviewDisparity calculates score disparities between critics and players.",
    url: "/about",
  },
};

const appAreas = [
  {
    title: "Games",
    href: "/games",
    description:
      "Browse release-by-release score gaps, latest reviews, release dates, and score breakdowns for tracked games.",
  },
  {
    title: "Journalists",
    href: "/journalists",
    description:
      "See which reviewers track closest to players, inspect their latest review activity, and open their full scoring history.",
  },
  {
    title: "Outlets",
    href: "/outlets",
    description:
      "Measure publications at the outlet level, then drill down into contributor activity and recent review coverage.",
  },
  {
    title: "Leaderboards",
    href: "/leaderboards",
    description:
      "Rank games, journalists, and outlets by disparity and recency to surface the strongest gaps or tightest alignment.",
  },
  {
    title: "Compare",
    href: "/compare",
    description:
      "Stack up to four games, journalists, or outlets side by side to compare disparity, score baselines, and trend direction.",
  },
  {
    title: "News and Reception Story",
    href: "/news",
    description:
      "Pair score data with related coverage, milestones, and review timing so a launch story can be read in context.",
  },
] as const;

const colorBands = [
  {
    range: "±0-5",
    label: "Aligned",
    color: "#708160",
    background: "rgba(112, 129, 96, 0.15)",
    copy: "Critic is closely aligned with user opinions",
  },
  {
    range: "±5-10",
    label: "Moderate",
    color: "#D4A017",
    background: "rgba(212, 160, 23, 0.15)",
    copy: "Some divergence from user scores",
  },
  {
    range: "±10-15",
    label: "High",
    color: "#DD7631",
    background: "rgba(221, 118, 49, 0.15)",
    copy: "Significant divergence from users",
  },
  {
    range: "±15+",
    label: "Extreme",
    color: "#BB3B0E",
    background: "rgba(187, 59, 14, 0.15)",
    copy: "Major divergence from user opinions",
  },
] as const;

const thresholdCards = [
  {
    value: "50",
    color: "var(--color-sage)",
    title: "Minimum Steam user reviews",
    copy:
      "Games need at least 50 Steam user reviews before Steam counts in disparity calculations.",
  },
  {
    value: "20",
    color: "var(--color-orange)",
    title: "Minimum Metacritic user reviews",
    copy:
      "Games need at least 20 Metacritic user reviews before Metacritic counts in disparity calculations.",
  },
  {
    value: "10",
    color: "var(--color-rust)",
    title: "Minimum scored reviews for journalists and outlets",
    copy:
      "Journalists and outlets need at least 10 scored reviews to qualify for leaderboard-style ranking.",
  },
  {
    value: "10",
    color: "var(--color-rust)",
    title: "Minimum critic reviews for games leaderboard",
    copy:
      "Games need at least 10 critic reviews to appear on the games leaderboard.",
  },
  {
    value: "10",
    color: "var(--color-orange)",
    title: "Minimum score spread",
    copy:
      "Journalists and outlets need a score spread of at least 10 to avoid binary or overly narrow scoring patterns distorting the rankings.",
  },
] as const;

const disparitySourceCards = [
  {
    title: "Steam Disparity",
    accent: "var(--color-sage)",
    formula: "Critic Score - Steam User Score",
    copy:
      "Compares critic reviews against Steam&apos;s PC gaming audience.",
  },
  {
    title: "Metacritic Disparity",
    accent: "var(--color-orange)",
    formula: "Critic Score - Metacritic User Score",
    copy:
      "Compares critic reviews against Metacritic&apos;s broader cross-platform user audience.",
  },
  {
    title: "Combined Disparity",
    accent: "var(--color-rust)",
    formula: "(Steam Disparity + MC Disparity) / 2",
    copy:
      "Averages the two source disparities when both exist. If only one source is available, that source is used directly.",
  },
] as const;

const chartGuide = [
  {
    title: "Solid colored line",
    description: "Rolling average for the active series inside the selected view.",
    kind: "solid",
  },
  {
    title: "Light dotted baseline",
    description:
      "The light dotted horizontal line is the 0 baseline. Above it means critics scored higher than users. Below it means critics scored lower.",
    kind: "baseline",
  },
  {
    title: "Colored dotted connector",
    description:
      "The colored dotted line marks the change from the first visible review to the last visible review in the selected release window for that series.",
    kind: "connector",
  },
  {
    title: "Vertical dashed release markers",
    description:
      "On game Release Map views, day 0 marks launch and day 60 marks the end of the launch window.",
    kind: "release",
  },
] as const;

const chartSections = [
  {
    title: "Disparity Trend",
    items: [
      "Shows the direction and magnitude of critic-to-user gaps over time.",
      "Sage, orange, and rust identify Steam, Metacritic, and Combined series.",
      "Hover points and tooltips reveal the underlying review values behind the rolling averages.",
    ],
  },
  {
    title: "Release Map / Score Map",
    items: [
      "On game pages, the x-axis is days from release and the y-axis is disparity.",
      "On journalist and outlet pages, the x-axis becomes critic score while the y-axis stays disparity.",
      "Each point is one review.",
    ],
  },
  {
    title: "Review Timing",
    items: [
      "The donut splits reviews into Early, Launch Window, and Late.",
      "Early means before release, Launch Window means within 60 days, and Late means more than 60 days after release.",
      "The center number is the total review count represented by the chart.",
    ],
  },
  {
    title: "Reception Story",
    items: [
      "Game detail pages combine release events, reviews, milestones, and linked news into a single timeline.",
      "Use it to understand what happened around a launch instead of reading the disparity number in isolation.",
    ],
  },
  {
    title: "Journalist Scoring Pattern",
    items: [
      "Each square is one review from the journalist.",
      "Rust means the critic scored above users, sage means below users, and neutral tiles sit near parity.",
      "You can sort chronologically or by disparity and filter to a single year.",
    ],
  },
  {
    title: "Outlet Activity Stream",
    items: [
      "Groups an outlet's reviews by month or quarter.",
      "Rust bands are more generous-than-users reviews, tan bands are aligned, and sage bands are more critical-than-users reviews.",
      "You can focus on a single journalist and select a time range to filter the review stream below.",
    ],
  },
] as const;

const dataSources = [
  {
    title: "OpenCritic",
    copy:
      "Professional critic reviews, scores, outlets, and journalist profiles. This is the core review history behind the site.",
  },
  {
    title: "Steam",
    copy:
      "Player review sentiment from Steam, normalized to the same 0-100 scale as critic scores.",
  },
  {
    title: "Metacritic",
    copy:
      "Player ratings from Metacritic, converted from the 0-10 scale into 0-100 for direct comparison.",
  },
] as const;

function Section({
  id,
  title,
  children,
  subtitle,
}: {
  id?: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="site-panel px-6 py-7 sm:px-8 sm:py-8">
      <h2 className="text-2xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
        {title}
      </h2>
      {subtitle && (
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          {subtitle}
        </p>
      )}
      {children}
    </section>
  );
}

function LineSwatch({ kind }: { kind: (typeof chartGuide)[number]["kind"] }) {
  if (kind === "solid") {
    return (
      <div className="relative h-14 rounded-xl border" style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}>
        <div className="absolute left-8 right-8 top-1/2 -translate-y-1/2" style={{ borderTop: "4px solid var(--color-rust)" }} />
        <span className="absolute left-16 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full" style={{ backgroundColor: "var(--color-rust)" }} />
        <span className="absolute right-20 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full" style={{ backgroundColor: "var(--color-rust)" }} />
      </div>
    );
  }

  if (kind === "baseline") {
    return (
      <div className="relative h-14 rounded-xl border" style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}>
        <div
          className="absolute left-8 right-8 top-1/2 h-1 -translate-y-1/2"
          style={{
            backgroundImage:
              "repeating-linear-gradient(to right, var(--color-tan) 0 14px, transparent 14px 22px)",
          }}
        />
      </div>
    );
  }

  if (kind === "connector") {
    return (
      <div className="relative h-14 rounded-xl border" style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}>
        <div
          className="absolute left-8 right-8 top-1/2 h-1 -translate-y-1/2"
          style={{
            backgroundImage:
              "repeating-linear-gradient(to right, var(--color-rust) 0 14px, transparent 14px 22px)",
          }}
        />
        <span className="absolute left-12 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full" style={{ backgroundColor: "var(--color-rust)" }} />
        <span className="absolute right-16 top-1/2 h-4 w-4 -translate-y-1/2 rounded-full" style={{ backgroundColor: "var(--color-rust)" }} />
      </div>
    );
  }

  return (
    <div className="relative h-24 rounded-xl border" style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}>
      <div
        className="absolute left-8 right-8 bottom-6"
        style={{ borderTop: "2px solid color-mix(in srgb, var(--foreground-subtle) 68%, transparent)" }}
      />
      <div
        className="absolute top-5 bottom-9 rounded-md"
        style={{
          left: "30%",
          right: "30%",
          backgroundColor: "rgba(216, 197, 147, 0.22)",
        }}
      />
      <div
        className="absolute top-4 bottom-8 flex w-[3px] flex-col justify-between"
        style={{
          left: "30%",
          color: "var(--foreground-subtle)",
        }}
      >
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
      </div>
      <div
        className="absolute top-4 bottom-8 flex w-[3px] flex-col justify-between"
        style={{
          left: "70%",
          color: "var(--foreground-subtle)",
        }}
      >
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
        <span className="block h-2 w-full rounded-full" style={{ backgroundColor: "currentColor" }} />
      </div>
      <span
        className="absolute bottom-2 text-[10px] font-semibold"
        style={{ left: "calc(30% - 0.3rem)", color: "var(--foreground-subtle)" }}
      >
        0
      </span>
      <span
        className="absolute bottom-2 text-[10px] font-semibold"
        style={{ left: "calc(70% - 0.45rem)", color: "var(--foreground-subtle)" }}
      >
        60
      </span>
    </div>
  );
}

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
    <div className="max-w-5xl mx-auto space-y-8">
      <JsonLd data={jsonLdData} />

      <section className="site-panel text-center px-6 py-8 sm:px-8 sm:py-10">
        <h1 className="text-4xl font-bold mb-4" style={{ color: "var(--foreground)" }}>
          How It <span style={{ color: "var(--color-rust)" }}>Works</span>
        </h1>
        <p className="text-lg" style={{ color: "var(--foreground-muted)" }}>
          Understanding our methodology, data sources, and chart views
        </p>
      </section>

      <Section
        id="coverage"
        title="What You Can Explore"
        subtitle="The rules and methodology stay the same. The newer additions are extra ways to inspect the same disparity data in more detail."
      >
        <div className="grid gap-4 md:grid-cols-2">
          {appAreas.map((area) => (
            <Link
              key={area.title}
              href={area.href}
              className="block rounded-[1.25rem] border px-5 py-5 transition-colors hover:border-[var(--border-strong)]"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--background-card)" }}
            >
              <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
                {area.title}
              </h3>
              <p className="mt-3 text-sm leading-7" style={{ color: "var(--foreground-muted)" }}>
                {area.description}
              </p>
            </Link>
          ))}
        </div>
      </Section>

      <Section id="disparity" title="What is Review Disparity?">
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
      </Section>

      <Section id="colors" title="Understanding Our Colors">
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Our color system is based on the <strong>magnitude</strong> of disparity. This helps you quickly
          identify how aligned or divergent a critic is with players.
        </p>
        <div className="space-y-3">
          {colorBands.map((band) => (
            <div
              key={band.label}
              className="grid grid-cols-[minmax(5.5rem,7rem)_1fr] items-center gap-4 p-3 rounded-lg"
              style={{ backgroundColor: band.background }}
            >
              <span
                className="text-xl font-bold text-center whitespace-nowrap tabular-nums"
                style={{ color: band.color }}
              >
                {band.range}
              </span>
              <div>
                <span className="font-semibold" style={{ color: band.color }}>
                  {band.label}
                </span>
                <span className="text-sm ml-2" style={{ color: "var(--foreground-muted)" }}>
                  - {band.copy}
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-6 text-sm" style={{ color: "var(--foreground-muted)" }}>
          The +/- sign still tells you the <em>direction</em>, but the color indicates <em>magnitude</em>.
          A +3 and -3 are both green because they are both closely aligned with users.
        </p>
      </Section>

      <Section id="formula" title="The Formula">
        <h3 className="text-sm font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--foreground-muted)" }}>
          Step 1 - Per-review disparity
        </h3>
        <div
          className="p-5 rounded-lg text-center mb-2 font-mono text-lg"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--color-rust)" }}>Disparity</span>
          <span style={{ color: "var(--foreground-muted)" }}> = </span>
          <span style={{ color: "var(--color-rust)" }}>Critic Score</span>
          <span style={{ color: "var(--foreground-muted)" }}> - </span>
          <span style={{ color: "var(--color-sage)" }}>User Score</span>
        </div>
        <p className="text-sm mb-8" style={{ color: "var(--foreground-muted)" }}>
          Calculated separately for Steam and Metacritic on every review.
        </p>

        <h3 className="text-sm font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--foreground-muted)" }}>
          Step 2 - Combined disparity
        </h3>
        <div
          className="p-5 rounded-lg text-center mb-2 font-mono text-lg"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--color-rust)" }}>Combined</span>
          <span style={{ color: "var(--foreground-muted)" }}> = </span>
          <span style={{ color: "var(--foreground-muted)" }}>(</span>
          <span style={{ color: "#708160" }}>Steam Disparity</span>
          <span style={{ color: "var(--foreground-muted)" }}> + </span>
          <span style={{ color: "#DD7631" }}>MC Disparity</span>
          <span style={{ color: "var(--foreground-muted)" }}>) / 2</span>
        </div>
        <p className="text-sm mb-2" style={{ color: "var(--foreground-muted)" }}>
          The simple average of Steam and Metacritic disparities. If only one source is available, that source is used directly as the combined score.
        </p>
        <div
          className="p-4 rounded-lg text-sm font-mono"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)", color: "var(--foreground-muted)" }}
        >
          <div className="mb-1">
            <span style={{ color: "#708160" }}>Steam Disparity</span>
            <span> = Critic Score - Steam User Score</span>
          </div>
          <div className="mb-1">
            <span style={{ color: "#DD7631" }}>MC Disparity</span>
            <span> = Critic Score - Metacritic User Score</span>
          </div>
          <div className="mt-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
            <span style={{ color: "var(--color-rust)" }}>Combined</span>
            <span> = (Steam Disparity + MC Disparity) / 2</span>
          </div>
        </div>

        <h3 className="text-sm font-semibold uppercase tracking-wide mb-2 mt-8" style={{ color: "var(--foreground-muted)" }}>
          Step 3 - Journalist and outlet averages
        </h3>
        <div
          className="p-5 rounded-lg text-center mb-2 font-mono text-lg"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <span style={{ color: "var(--color-rust)" }}>Avg Disparity</span>
          <span style={{ color: "var(--foreground-muted)" }}> = mean of all </span>
          <span style={{ color: "var(--color-rust)" }}>launch window</span>
          <span style={{ color: "var(--foreground-muted)" }}> review disparities</span>
        </div>
        <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
          For journalists and outlets, we average the combined disparity across all qualifying launch window reviews.
          Steam and Metacritic averages are calculated independently, then the combined score is the average of those two source averages.
        </p>
      </Section>

      <Section id="timing" title="Review Timing Categories">
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
              Reviews published <strong>before</strong> the game&apos;s official release date.
            </p>
          </div>
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300">
                Launch Window
              </span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Reviews published within <strong>60 days</strong> of release. This is the primary disparity window shown on profiles.
            </p>
          </div>
          <div className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                Late Review
              </span>
            </div>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Reviews published <strong>more than 60 days</strong> after release.
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
            </p>
          </div>
          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#3B82F6" }}>About early reviews:</strong> Early reviews are included in
              disparity calculations and count toward the launch window, but they are marked separately.
            </p>
          </div>
        </div>
      </Section>

      <Section id="primary-overall" title="Primary vs. Overall Disparity">
        <p className="mb-6" style={{ color: "var(--foreground-muted)" }}>
          Each journalist and outlet has two disparity metrics calculated:
        </p>
        <div className="space-y-4 mb-6">
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-rust)" }}>
            <h3 className="font-semibold mb-1" style={{ color: "var(--foreground)" }}>Launch Window Disparity (Primary)</h3>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Calculated only from reviews published within 60 days of each game&apos;s release. This is the main metric shown on profile pages and used for leaderboard rankings.
            </p>
          </div>
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-sage)" }}>
            <h3 className="font-semibold mb-1" style={{ color: "var(--foreground)" }}>Overall Disparity (Secondary)</h3>
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              Calculated from all reviews, including late reviews. Used as a fallback when a journalist or outlet has no qualifying launch window reviews.
            </p>
          </div>
        </div>
        <div
          className="p-4 rounded-lg"
          style={{ backgroundColor: "rgba(212, 160, 23, 0.15)", border: "1px solid rgba(212, 160, 23, 0.3)" }}
        >
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            <strong style={{ color: "#D4A017" }}>Transparency note:</strong> On profile pages, you can see how many reviews fall within the launch window versus late reviews.
          </p>
        </div>
      </Section>

      <Section id="thresholds" title="Quality Thresholds" subtitle="To ensure statistical reliability and prevent manipulation, we apply minimum thresholds.">
        <div className="space-y-4">
          {thresholdCards.map((card) => (
            <div
              key={card.title}
              className="flex items-start gap-4 p-4 rounded-lg"
              style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
            >
              <div
                className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 text-xl font-bold"
                style={{ backgroundColor: card.color, color: "white" }}
              >
                {card.value}
              </div>
              <div>
                <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>
                  {card.title}
                </h3>
                <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                  {card.copy}
                </p>
              </div>
            </div>
          ))}
        </div>
        <div
          className="p-4 rounded-lg mt-6"
          style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}
        >
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            <strong style={{ color: "var(--foreground)" }}>Note:</strong> Individual profiles can still exist even if they do not qualify for leaderboard inclusion.
          </p>
        </div>
      </Section>

      <Section id="normalization" title="Score Normalization" subtitle="Different outlets use different scoring scales. To compare apples to apples, all scores are normalized to a 0-100 scale.">
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
      </Section>

      <Section id="sources" title="Data Sources">
        <div className="space-y-6">
          {dataSources.map((source) => (
            <div key={source.title} className="flex gap-4">
              <div
                className="w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 font-bold"
                style={{ backgroundColor: "var(--color-rust)", color: "white" }}
              >
                {source.title.slice(0, 1)}
              </div>
              <div>
                <h3 className="font-semibold text-lg" style={{ color: "var(--foreground)" }}>
                  {source.title}
                </h3>
                <p style={{ color: "var(--foreground-muted)" }}>
                  {source.copy}
                </p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section id="three-scores" title="Three Disparity Scores" subtitle="We show disparity separately for each user score source so you can see how critics compare to different player communities.">
        <div className="space-y-4">
          {disparitySourceCards.map((card) => (
            <div key={card.title} className="p-4 rounded-lg" style={{ backgroundColor: "var(--background-card)", border: "1px solid var(--border)" }}>
              <div className="flex items-center gap-3 mb-2">
                <div
                  className="w-8 h-8 rounded flex items-center justify-center"
                  style={{ backgroundColor: card.accent, color: "white" }}
                >
                  {card.title.slice(0, 1)}
                </div>
                <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>
                  {card.title}
                </h3>
              </div>
              <p className="text-sm ml-11" style={{ color: "var(--foreground-muted)" }}>
                <span className="font-mono">{card.formula}</span>
                <br />
                {card.copy}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="score-spread" title="Score Spread vs. Disparity" subtitle="On journalist and outlet profiles, these measure different things.">
        <div className="grid md:grid-cols-2 gap-6 mb-6">
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-rust)" }}>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>
              Disparity
            </h3>
            <p className="text-sm mb-3" style={{ color: "var(--foreground-muted)" }}>
              How far the critic&apos;s scores are from <strong>user scores</strong>.
            </p>
            <div className="text-sm font-mono p-2 rounded" style={{ backgroundColor: "var(--background)", color: "var(--color-rust)" }}>
              Critic Score - User Score
            </div>
          </div>
          <div className="p-4 rounded-lg border-l-4" style={{ backgroundColor: "var(--background-card)", borderLeftColor: "var(--color-sage)" }}>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>
              Score Spread
            </h3>
            <p className="text-sm mb-3" style={{ color: "var(--foreground-muted)" }}>
              How varied the critic&apos;s <strong>own scores</strong> are.
            </p>
            <div className="text-sm font-mono p-2 rounded" style={{ backgroundColor: "var(--background)", color: "var(--color-sage)" }}>
              Standard Deviation of Critic Scores
            </div>
          </div>
        </div>
        <div className="space-y-4">
          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(112, 129, 96, 0.15)", border: "1px solid rgba(112, 129, 96, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#708160" }}>High Score Spread (10+):</strong> Uses a meaningful range of scores.
            </p>
          </div>
          <div
            className="p-4 rounded-lg"
            style={{ backgroundColor: "rgba(212, 160, 23, 0.15)", border: "1px solid rgba(212, 160, 23, 0.3)" }}
          >
            <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
              <strong style={{ color: "#D4A017" }}>Low Score Spread (&lt;10):</strong> Can indicate binary or overly narrow scoring patterns, which is why these reviewers are filtered from leaderboard rankings.
            </p>
          </div>
        </div>
      </Section>

      <Section id="charts" title="How to Read the Charts" subtitle="These are additional views on top of the same scoring rules above.">
        <div className="rounded-[1.25rem] border px-5 py-5" style={{ borderColor: "var(--border)", backgroundColor: "var(--background-card)" }}>
          <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
            What the lines mean
          </h3>
          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {chartGuide.map((item) => (
              <div
                key={item.title}
                className="space-y-4 rounded-[1rem] border px-4 py-4"
                style={{ borderColor: "var(--border)", backgroundColor: "var(--background)" }}
              >
                <LineSwatch kind={item.kind} />
                <h4 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>
                  {item.title}
                </h4>
                <p className="text-sm leading-7" style={{ color: "var(--foreground-muted)" }}>
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {chartSections.map((section) => (
            <div
              key={section.title}
              className="rounded-[1.25rem] border px-5 py-5"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--background-card)" }}
            >
              <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
                {section.title}
              </h3>
              <ul className="mt-4 space-y-2 text-sm leading-7" style={{ color: "var(--foreground-muted)" }}>
                {section.items.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span className="mt-2 h-1.5 w-1.5 rounded-full" style={{ backgroundColor: "var(--color-rust)" }} />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <Section id="coverage-detail" title="Data Coverage">
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>Time Period</h3>
            <p style={{ color: "var(--foreground-muted)" }}>
              We track all available review data from OpenCritic, going back to the earliest reviews
              in their database.
            </p>
          </div>
          <div>
            <h3 className="font-semibold mb-2" style={{ color: "var(--foreground)" }}>Update Frequency</h3>
            <p style={{ color: "var(--foreground-muted)" }}>
              Critic reviews are synced continuously. User scores from Steam and Metacritic are updated regularly. Historical disparity data powers the trend charts and new story views.
            </p>
          </div>
        </div>
      </Section>

      <Section id="interpreting" title="Interpreting the Data">
        <div className="space-y-4" style={{ color: "var(--foreground-muted)" }}>
          <p>
            <strong style={{ color: "var(--foreground)" }}>High disparity does not mean &quot;wrong&quot;:</strong> critics
            and players often have different priorities.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Direction vs. magnitude:</strong> the sign (+/-)
            tells you whether the critic scored higher or lower than users, but the magnitude is what matters most.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Sample size matters:</strong> a journalist with
            5 reviews will be less reliable than one with 500.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Check score spread:</strong> low spread means a reviewer may give similar scores to almost everything, which can make disparity less meaningful.
          </p>
          <p>
            <strong style={{ color: "var(--foreground)" }}>Compare sources:</strong> a journalist might be
            aligned with Steam users but divergent from Metacritic users, or vice versa.
          </p>
        </div>
      </Section>

    </div>
  );
}
