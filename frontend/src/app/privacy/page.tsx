import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "Privacy Policy for ReviewDisparity.",
  alternates: { canonical: "/privacy" },
  robots: { index: true, follow: true },
};

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <h1
        className="text-3xl font-bold"
        style={{ color: "var(--foreground)" }}
      >
        Privacy Policy
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
            1. Overview
          </h2>
          <p>
            ReviewDisparity (&quot;the Site&quot;) is an informational service
            that does not require user accounts, logins, or registration. We are
            committed to respecting your privacy and being transparent about the
            limited data we collect.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            2. Information We Do Not Collect
          </h2>
          <p>We do not collect, store, or process:</p>
          <ul className="list-disc ml-6 mt-2 space-y-1">
            <li>Personal names, email addresses, or contact information</li>
            <li>User accounts, passwords, or login credentials</li>
            <li>Payment or financial information</li>
            <li>User-generated content or comments</li>
            <li>Location data beyond what is inherent in IP addresses</li>
          </ul>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            3. Information We May Collect
          </h2>

          <h3
            className="font-semibold mt-4 mb-1"
            style={{ color: "var(--foreground)" }}
          >
            Analytics Data
          </h3>
          <p>
            We may use Google Analytics or similar services to collect anonymous,
            aggregated usage data such as:
          </p>
          <ul className="list-disc ml-6 mt-2 space-y-1">
            <li>Pages visited and time spent on pages</li>
            <li>Referring websites and search terms</li>
            <li>Browser type, device type, and screen resolution</li>
            <li>General geographic region (country/city level)</li>
          </ul>
          <p className="mt-2">
            This data is used solely to understand how visitors use the Site and
            to improve the service. It is not used to identify individual users.
          </p>

          <h3
            className="font-semibold mt-4 mb-1"
            style={{ color: "var(--foreground)" }}
          >
            Server Logs
          </h3>
          <p>
            Our servers may automatically log standard request information
            including IP addresses, request timestamps, and user agent strings.
            This data is used for security monitoring, rate limiting, and
            debugging purposes. Server logs are retained for a limited period and
            are not shared with third parties.
          </p>

          <h3
            className="font-semibold mt-4 mb-1"
            style={{ color: "var(--foreground)" }}
          >
            Local Storage
          </h3>
          <p>
            We use your browser&apos;s local storage to save your theme
            preference (light or dark mode). This data stays on your device and
            is never transmitted to our servers.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            4. Cookies
          </h2>
          <p>
            The Site itself does not set first-party cookies. However, if Google
            Analytics is enabled, it may set cookies to distinguish unique
            visitors and track sessions. These are third-party cookies governed
            by{" "}
            <a
              href="https://policies.google.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
              style={{ color: "var(--color-rust)" }}
            >
              Google&apos;s Privacy Policy
            </a>
            .
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            5. Publicly Available Data
          </h2>
          <p>
            The Site displays information about game journalists, gaming outlets,
            and video games that is publicly available from sources such as
            OpenCritic, Steam, and Metacritic. This includes publicly listed
            names, review scores, and publication information. We do not collect
            or display private or non-public information about any individual.
          </p>
          <p className="mt-2">
            If you are a journalist or outlet representative and have concerns
            about how your publicly available data is presented, please contact
            us through our available channels.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            6. Children&apos;s Privacy
          </h2>
          <p>
            The Site is not directed at children under the age of 13. We do not
            knowingly collect any information from children under 13. If you
            believe a child under 13 has provided information to us, please
            contact us so we can take appropriate action.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            7. Third-Party Services
          </h2>
          <p>
            The Site may contain links to third-party websites (such as original
            review articles, Steam store pages, or Metacritic pages). These
            third-party sites have their own privacy policies, and we are not
            responsible for their practices. We encourage you to review the
            privacy policies of any site you visit.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            8. Data Security
          </h2>
          <p>
            We use industry-standard security measures including HTTPS
            encryption, security headers, and rate limiting to protect the Site
            and its visitors. However, no method of transmission over the
            internet is 100% secure, and we cannot guarantee absolute security.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            9. Changes to This Policy
          </h2>
          <p>
            We may update this Privacy Policy from time to time. Changes will be
            posted on this page with an updated &quot;Last updated&quot; date.
            Your continued use of the Site after changes are posted constitutes
            acceptance of the updated policy.
          </p>
        </section>

        <section>
          <h2
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--foreground)" }}
          >
            10. Contact
          </h2>
          <p>
            If you have questions or concerns about this Privacy Policy, please
            reach out through our available contact channels.
          </p>
        </section>
      </div>

      <div className="pt-4 border-t" style={{ borderColor: "var(--border)" }}>
        <Link
          href="/terms"
          className="text-sm hover:underline"
          style={{ color: "var(--color-rust)" }}
        >
          View Terms of Service
        </Link>
      </div>
    </div>
  );
}
