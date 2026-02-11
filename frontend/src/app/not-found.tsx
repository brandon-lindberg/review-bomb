import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Page Not Found",
  description: "The page you're looking for doesn't exist.",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <h1
        className="text-7xl font-bold mb-2"
        style={{ color: "var(--color-rust)" }}
      >
        404
      </h1>
      <p
        className="text-xl mb-8"
        style={{ color: "var(--foreground-muted)" }}
      >
        This page doesn&apos;t exist or may have been removed.
      </p>

      <div className="flex flex-wrap justify-center gap-4">
        <Link
          href="/"
          className="px-6 py-3 text-white rounded-lg font-medium hover:opacity-90 transition-opacity"
          style={{ backgroundColor: "var(--color-rust)" }}
        >
          Go Home
        </Link>
        <Link
          href="/search"
          className="px-6 py-3 rounded-lg font-medium hover:opacity-80 transition-opacity"
          style={{
            backgroundColor: "var(--color-tan)",
            color: "var(--foreground)",
          }}
        >
          Search
        </Link>
        <Link
          href="/games"
          className="px-6 py-3 rounded-lg font-medium hover:opacity-80 transition-opacity"
          style={{ backgroundColor: "var(--color-sage)", color: "white" }}
        >
          Browse Games
        </Link>
      </div>
    </div>
  );
}
