import Link from "next/link";

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer
      className="border-t mt-16"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
            &copy; {year} ReviewDisparity. All rights reserved.
          </p>

          <nav className="flex items-center gap-6">
            <Link
              href="/about"
              className="text-sm hover:underline"
              style={{ color: "var(--foreground-muted)" }}
            >
              About
            </Link>
            <Link
              href="/terms"
              className="text-sm hover:underline"
              style={{ color: "var(--foreground-muted)" }}
            >
              Terms of Service
            </Link>
            <Link
              href="/privacy"
              className="text-sm hover:underline"
              style={{ color: "var(--foreground-muted)" }}
            >
              Privacy Policy
            </Link>
          </nav>
        </div>

        <p
          className="text-xs mt-4 text-center sm:text-left"
          style={{ color: "var(--foreground-muted)", opacity: 0.6 }}
        >
          Data sourced from publicly available information on OpenCritic, Steam,
          and Metacritic. Not affiliated with or endorsed by any of these
          services.
        </p>
      </div>
    </footer>
  );
}
