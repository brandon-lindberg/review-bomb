import Link from "next/link";

const footerLinks = [
  { href: "/games", label: "Browse games" },
  { href: "/journalists", label: "Browse journalists" },
  { href: "/outlets", label: "Browse outlets" },
  { href: "/compare", label: "Compare entities" },
];

const legalLinks = [
  { href: "/about", label: "About" },
  { href: "/faq", label: "FAQ" },
  { href: "/terms", label: "Terms of Service" },
  { href: "/privacy", label: "Privacy Policy" },
];

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="mt-16 border-t" style={{ borderColor: "var(--border)" }}>
      <div className="mx-auto max-w-[88rem] px-4 py-10 sm:px-6 lg:px-8">
        <div className="site-panel rounded-[2rem] p-6 sm:p-8">
          <div className="grid gap-10 lg:flex lg:items-start lg:gap-8">
            <div className="space-y-5 lg:max-w-[44rem] lg:pr-6">
              <span className="site-eyebrow">Review Signal</span>
              <div className="space-y-3">
                <h2 className="max-w-xl text-2xl font-black tracking-tight sm:text-3xl" style={{ color: "var(--foreground)" }}>
                  Keep the data honest.
                </h2>
                <p className="max-w-2xl text-sm leading-7 sm:text-base" style={{ color: "var(--foreground-muted)" }}>
                  ReviewDisparity tracks how critics, outlets, and games compare with player opinion
                  across Steam and Metacritic. The goal is simple: make disagreement visible instead
                  of burying it in scattered scorecards.
                </p>
              </div>
            </div>

            <div className="grid gap-6 sm:grid-cols-2 lg:ml-auto lg:flex lg:w-fit lg:items-start lg:justify-end lg:gap-6">
              <div className="space-y-4 text-left">
                <span className="site-data-label">Explore</span>
                <nav className="grid gap-3 text-left">
                  {footerLinks.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      className="text-base font-medium hover:text-rust"
                      style={{ color: "var(--foreground-muted)" }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              </div>

              <div className="space-y-4 text-left lg:min-w-[11rem]">
                <span className="site-data-label">Site</span>
                <nav className="grid gap-3 text-left">
                  {legalLinks.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      className="text-base font-medium hover:text-rust"
                      style={{ color: "var(--foreground-muted)" }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </nav>
              </div>
            </div>
          </div>

          <div
            className="mt-8 border-t pt-6"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="mx-auto max-w-4xl space-y-2 text-center">
              <p className="text-sm" style={{ color: "var(--foreground-muted)" }}>
                &copy; {year} ReviewDisparity. Independent review disparity tracking.
              </p>
              <p className="text-xs leading-6 sm:text-sm" style={{ color: "var(--foreground-muted)" }}>
                Data sourced from publicly available information on OpenCritic, Steam, and Metacritic.
                ReviewDisparity is not affiliated with or endorsed by any of those services.
              </p>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
