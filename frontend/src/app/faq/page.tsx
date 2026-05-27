import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Answers to common questions about ReviewDisparity: what review disparity means, how scores are calculated, where the data comes from, and how to read the leaderboards.",
  alternates: { canonical: "/faq" },
  openGraph: {
    title: "Frequently Asked Questions - ReviewDisparity",
    description:
      "Answers to common questions about review disparity, scoring methodology, and data sources.",
    url: "/faq",
  },
};

// Each answer is plain prose so it reads cleanly both on the page and inside
// the FAQPage structured data we emit for AI search engines and rich results.
const faqs = [
  {
    question: "What is review disparity?",
    answer:
      "Review disparity is the difference between how professional game critics score a game and how regular players rate it. A positive disparity means critics scored a game higher than players did; a negative disparity means critics scored it lower. ReviewDisparity tracks this gap across games, journalists, and outlets so you can see who aligns with players and who diverges.",
  },
  {
    question: "How is disparity calculated?",
    answer:
      "Disparity is calculated per review as the critic score minus the user score, computed separately for Steam and Metacritic. The combined disparity is the average of the Steam and Metacritic disparities; if only one source is available, that source is used directly. For journalists and outlets, we average the combined disparity across all qualifying launch window reviews.",
  },
  {
    question: "What does a positive vs. negative disparity mean?",
    answer:
      "A positive disparity means critics rated the game higher than players, which can reflect critic priorities, marketing influence, or different evaluation criteria. A negative disparity means critics rated it lower than players. What matters most is the magnitude of the gap, not its direction: a +15 and a -15 both signal a significant disagreement between critics and players.",
  },
  {
    question: "Where does the data come from?",
    answer:
      "Critic reviews, scores, outlets, and journalist profiles come from OpenCritic, which is the core review history behind the site. Player sentiment comes from Steam (percent-positive reviews) and Metacritic user ratings. ReviewDisparity is independent and is not affiliated with or endorsed by any of those services.",
  },
  {
    question: "How are different scoring scales compared fairly?",
    answer:
      "Every score is normalized to a 0-100 scale before comparison. A review out of 10, out of 5, out of 100, or given as a letter grade is converted to the same scale, as are Steam percent-positive scores and Metacritic user scores. This lets critic and player scores be compared directly.",
  },
  {
    question: "What is the launch window, and why 60 days?",
    answer:
      "Reviews are categorized by when they were published relative to a game's release: Early (before release), Launch Window (within 60 days of release), and Late (more than 60 days after release). The 60-day launch window captures the period when most professional reviews are published and when user scores are most actively submitted, so it is the primary window shown on profiles and used for rankings.",
  },
  {
    question: "Why don't some games, journalists, or outlets appear on the leaderboards?",
    answer:
      "To keep rankings statistically reliable and resistant to manipulation, we apply minimum thresholds. Games need at least 50 Steam user reviews before Steam counts and at least 20 Metacritic user reviews before Metacritic counts. Journalists and outlets need at least 10 scored reviews and a score spread of at least 10 to qualify for ranking. Profiles can still exist even when they do not qualify for leaderboard inclusion.",
  },
  {
    question: "What is the difference between disparity and score spread?",
    answer:
      "Disparity measures how far a critic's scores are from user scores. Score spread is the standard deviation of a critic's own scores, measuring how varied their scoring is. A low score spread can indicate binary or overly narrow scoring patterns, which is why reviewers below the spread threshold are filtered from leaderboard rankings.",
  },
  {
    question: "Does a high disparity mean a review is wrong?",
    answer:
      "No. A high disparity does not mean a critic is wrong. Critics and players often have different priorities, and disparity simply makes that disagreement visible. Sample size and score spread should be considered too: a journalist with hundreds of reviews is more reliable than one with a handful, and a reviewer might align with Steam users while diverging from Metacritic users.",
  },
  {
    question: "How often is the data updated?",
    answer:
      "Critic reviews are synced continuously, and user scores from Steam and Metacritic are updated regularly. Historical disparity data powers the trend charts and reception story views, so the live pages are always the most current source.",
  },
] as const;

function FaqItem({ question, answer }: { question: string; answer: string }) {
  return (
    <div
      className="rounded-[1.25rem] border px-5 py-5 sm:px-6 sm:py-6"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--background-card)" }}
    >
      <h3 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>
        {question}
      </h3>
      <p className="mt-3 text-sm leading-7" style={{ color: "var(--foreground-muted)" }}>
        {answer}
      </p>
    </div>
  );
}

export default function FaqPage() {
  const faqJsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <JsonLd data={faqJsonLd} />

      <section className="site-panel text-center px-6 py-8 sm:px-8 sm:py-10">
        <h1 className="text-4xl font-bold mb-4" style={{ color: "var(--foreground)" }}>
          Frequently Asked <span style={{ color: "var(--color-rust)" }}>Questions</span>
        </h1>
        <p className="text-lg" style={{ color: "var(--foreground-muted)" }}>
          What review disparity is, how we calculate it, and where the data comes from
        </p>
      </section>

      <section className="site-panel px-6 py-7 sm:px-8 sm:py-8">
        <div className="space-y-4">
          {faqs.map((faq) => (
            <FaqItem key={faq.question} question={faq.question} answer={faq.answer} />
          ))}
        </div>

        <p className="mt-8 text-sm leading-7" style={{ color: "var(--foreground-muted)" }}>
          Want the full methodology, chart guides, and scoring details? Read{" "}
          <Link href="/about" className="font-medium hover:text-rust" style={{ color: "var(--color-rust)" }}>
            How It Works
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
