import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "Terms of Service for ReviewDisparity.",
  alternates: { canonical: "/terms" },
  robots: { index: true, follow: true },
};

export default function TermsPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <h1
        className="text-3xl font-bold"
        style={{ color: "var(--foreground)" }}
      >
        Terms of Service
      </h1>
      <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
        Last updated: February 2026
      </p>

      <div
        className="space-y-6 text-sm leading-relaxed"
        style={{ color: "var(--foreground-muted)" }}
      >
        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            1. Acceptance of Terms
          </h2>
          <p>
            By accessing or using ReviewDisparity (&quot;the Site&quot;), you
            agree to be bound by these Terms of Service. If you do not agree to
            these terms, do not use the Site.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            2. Description of Service
          </h2>
          <p>
            ReviewDisparity is a free, informational service that aggregates and
            analyzes publicly available video game review scores from critics and
            players. We compile data from public sources including OpenCritic,
            Steam, and Metacritic to calculate and display the disparity between
            professional critic scores and user scores.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            3. Publicly Available Data
          </h2>
          <p>
            All review scores, journalist names, outlet names, game titles, and
            related information displayed on this Site are derived from publicly
            available sources. We do not claim ownership of this data. The
            disparity calculations, aggregations, and analyses are original work
            produced by ReviewDisparity.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            4. No Warranty &amp; Disclaimer of Liability
          </h2>
          <p>
            The Site and all content are provided &quot;as is&quot; and &quot;as
            available&quot; without warranties of any kind, either express or
            implied. ReviewDisparity makes no guarantees regarding the accuracy,
            completeness, reliability, or timeliness of any information displayed
            on the Site.
          </p>
          <p className="mt-2">
            To the fullest extent permitted by law, ReviewDisparity and its
            operators shall not be liable for any direct, indirect, incidental,
            consequential, or punitive damages arising from your use of or
            inability to use the Site, including but not limited to reliance on
            any information obtained from the Site.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            5. Fair Use &amp; Editorial Purpose
          </h2>
          <p>
            ReviewDisparity uses publicly available review data for purposes of
            commentary, criticism, research, and education. Our service provides
            transformative analysis by calculating disparities and trends that
            are not available from the original sources. This use is consistent
            with fair use principles.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            6. Age Requirement
          </h2>
          <p>
            You must be at least 13 years of age to use this Site. By using the
            Site, you represent and warrant that you are at least 13 years old.
            If you are under 13, you may not access or use the Site.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            7. Acceptable Use
          </h2>
          <p>You agree not to:</p>
          <ul className="list-disc ml-6 mt-2 space-y-1">
            <li>
              Use the Site for any unlawful purpose or in violation of any
              applicable laws
            </li>
            <li>
              Attempt to gain unauthorized access to the Site&apos;s systems or
              infrastructure
            </li>
            <li>
              Scrape, crawl, or use automated means to access the Site in a
              manner that exceeds reasonable use or places undue burden on our
              servers
            </li>
            <li>
              Misrepresent data obtained from the Site or present it in a
              misleading context
            </li>
          </ul>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            8. Intellectual Property
          </h2>
          <p>
            The site design, code, disparity calculations, and original analyses
            are the property of ReviewDisparity. Game titles, journalist names,
            outlet names, and review scores belong to their respective owners.
            All trademarks referenced on the Site are the property of their
            respective holders.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            9. Third-Party Links &amp; Data Sources
          </h2>
          <p>
            The Site may contain links to third-party websites (such as original
            review articles). We are not responsible for the content, accuracy,
            or practices of any third-party sites. Clicking external links is at
            your own risk.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            10. Modifications to Terms
          </h2>
          <p>
            We reserve the right to modify these Terms of Service at any time.
            Changes will be effective immediately upon posting to the Site. Your
            continued use of the Site after changes are posted constitutes
            acceptance of the modified terms.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            11. Termination
          </h2>
          <p>
            We reserve the right to restrict or terminate access to the Site at
            any time, for any reason, without notice or liability.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            12. Contact
          </h2>
          <p>
            If you have questions about these Terms of Service, please reach out
            through our available contact channels.
          </p>
        </section>
      </div>

      <div className="pt-4 border-t" style={{ borderColor: "var(--border)" }}>
        <Link
          href="/privacy"
          className="text-sm hover:underline"
          style={{ color: "var(--color-rust)" }}
        >
          View Privacy Policy
        </Link>
      </div>
    </div>
  );
}
