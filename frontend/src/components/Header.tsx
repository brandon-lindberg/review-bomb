"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";

const navigation = [
  { name: "Home", href: "/" },
  { name: "News", href: "/news" },
  { name: "Games", href: "/games" },
  { name: "Journalists", href: "/journalists" },
  { name: "Outlets", href: "/outlets" },
  { name: "Leaderboards", href: "/leaderboards" },
  { name: "Compare", href: "/compare" },
  { name: "About", href: "/about" },
];

export function Header() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!mobileMenuOpen) return;

    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
    };
  }, [mobileMenuOpen]);

  return (
    <>
      <header
        className="sticky top-0 z-20 border-b"
        style={{
          borderColor: "var(--border)",
          background:
            "linear-gradient(180deg, color-mix(in srgb, var(--background-card-strong) 94%, var(--background) 6%), color-mix(in srgb, var(--background-card) 92%, var(--background) 8%))",
        }}
      >
        <div className="mx-auto max-w-[88rem] px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <Link href="/" className="flex min-w-0 items-center gap-3">
              <div
                className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-2xl border"
                style={{
                  borderColor: "var(--border)",
                  background:
                    "linear-gradient(135deg, rgba(255,255,255,0.9), rgba(216,197,147,0.28))",
                  boxShadow: "var(--shadow-soft)",
                }}
              >
                <Image
                  src="/logo.png"
                  alt="ReviewDisparity Logo"
                  width={900}
                  height={715}
                  className="h-11 w-auto rounded-sm"
                  priority
                />
              </div>

              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-xl font-black tracking-tight" style={{ color: "var(--foreground)" }}>
                    Review<span style={{ color: "var(--color-rust)" }}>Disparity</span>
                  </span>
                </div>
                <p className="hidden text-xs sm:block" style={{ color: "var(--foreground-muted)" }}>
                  Critics, outlets, and games against player sentiment
                </p>
              </div>
            </Link>

            <div className="hidden min-w-0 items-center gap-3 lg:flex">
              <nav className="site-tab-nav" aria-label="Primary navigation">
                {navigation.map((item) => {
                  const isActive = pathname === item.href
                    || (item.href !== "/" && pathname.startsWith(item.href));

                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={`site-tab-link${isActive ? " site-tab-link--active" : ""}`}
                    >
                      {item.name}
                    </Link>
                  );
                })}
              </nav>

              <ThemeToggle />
            </div>

            <div className="flex items-center gap-2 lg:hidden">
              <button
                type="button"
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border"
                style={{
                  borderColor: "var(--border)",
                  background:
                    "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
                  color: "var(--foreground)",
                }}
                onClick={() => setMobileMenuOpen(true)}
                aria-label="Open menu"
                aria-expanded={mobileMenuOpen}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <line x1="3" y1="12" x2="21" y2="12" />
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <line x1="3" y1="18" x2="21" y2="18" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      {mobileMenuOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/55 lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
          <div className="fixed inset-0 z-50 px-4 py-4 lg:hidden">
            <div
              className="mx-auto flex h-full max-w-md flex-col overflow-hidden rounded-[1.75rem] border"
              style={{
                borderColor: "var(--border-strong)",
                background:
                  "linear-gradient(180deg, var(--background-card-strong), color-mix(in srgb, var(--background-card) 92%, var(--background-tint) 8%))",
                boxShadow: "var(--shadow-strong)",
              }}
            >
              <div className="flex items-center justify-between border-b px-4 py-4" style={{ borderColor: "var(--border)" }}>
                <Link href="/" className="flex min-w-0 items-center gap-3" onClick={() => setMobileMenuOpen(false)}>
                  <div
                    className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-2xl border"
                    style={{
                      borderColor: "var(--border)",
                      background:
                        "linear-gradient(135deg, rgba(255,255,255,0.9), rgba(216,197,147,0.28))",
                    }}
                  >
                    <Image
                      src="/logo.png"
                      alt="ReviewDisparity Logo"
                      width={900}
                      height={715}
                      className="h-9 w-auto rounded-sm"
                    />
                  </div>
                  <span className="truncate text-lg font-black tracking-tight" style={{ color: "var(--foreground)" }}>
                    Review<span style={{ color: "var(--color-rust)" }}>Disparity</span>
                  </span>
                </Link>

                <button
                  type="button"
                  className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border"
                  style={{
                    borderColor: "var(--border)",
                    background:
                      "linear-gradient(180deg, var(--background-card-strong), var(--background-card))",
                    color: "var(--foreground)",
                  }}
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Close menu"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="22"
                    height="22"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-5">
                <nav className="grid grid-cols-1 gap-2">
                  {navigation.map((item) => {
                    const isActive = pathname === item.href
                      || (item.href !== "/" && pathname.startsWith(item.href));

                    return (
                      <Link
                        key={item.name}
                        href={item.href}
                        className="mobile-nav-link flex items-center justify-between rounded-[1.2rem] px-4 py-3 text-base font-semibold"
                        style={
                          isActive
                            ? {
                                background: "linear-gradient(135deg, var(--color-rust), var(--color-orange))",
                                color: "white",
                                boxShadow: "0 12px 28px rgba(187, 59, 14, 0.22)",
                              }
                            : {
                                color: "var(--foreground)",
                                background:
                                  "color-mix(in srgb, var(--background-card-strong) 90%, var(--color-tan) 10%)",
                                border: "1px solid var(--border)",
                              }
                        }
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        <span>{item.name}</span>
                        <span aria-hidden="true" style={{ opacity: isActive ? 0.92 : 0.55 }}>
                          {isActive ? "•" : "→"}
                        </span>
                      </Link>
                    );
                  })}
                </nav>

                <div className="mt-6 border-t pt-5" style={{ borderColor: "var(--border)" }}>
                  <p className="site-data-label">Appearance</p>
                  <div className="mt-3">
                    <ThemeToggle
                      fullWidth
                      labelMode="always"
                      className="rounded-[1.2rem] px-4 py-3"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
