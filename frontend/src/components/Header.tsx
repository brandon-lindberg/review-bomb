"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";

const navigation = [
  { name: "Home", href: "/" },
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

  return (
    <header className="bg-white shadow-sm border-b" style={{ borderColor: "var(--border)" }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-20">
          <div className="flex">
            <Link href="/" className="flex items-center gap-3">
              <Image
                src="/logo.png"
                alt="ReviewDisparity Logo"
                width={900}
                height={715}
                className="rounded-sm h-16 w-auto"
                priority
              />
              <span className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
                Review<span style={{ color: "var(--color-rust)" }}>Disparity</span>
              </span>
            </Link>
          </div>

          <div className="flex items-center gap-4">
            {/* Desktop Navigation */}
            <nav className="hidden md:flex items-center space-x-8">
              {navigation.map((item) => {
                const isActive = pathname === item.href ||
                  (item.href !== "/" && pathname.startsWith(item.href));

                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className="text-sm font-medium transition-colors"
                    style={isActive
                      ? { color: "var(--color-rust)", borderBottom: "2px solid var(--color-rust)", paddingBottom: "4px" }
                      : { color: "var(--foreground-muted)" }
                    }
                  >
                    {item.name}
                  </Link>
                );
              })}
            </nav>

            <ThemeToggle />

            {/* Mobile menu button */}
            <button
              type="button"
              className="md:hidden p-2 rounded-lg transition-colors"
              style={{ color: "var(--foreground-muted)" }}
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle menu"
              aria-expanded={mobileMenuOpen}
            >
              {mobileMenuOpen ? (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
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
              ) : (
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
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
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        >
          <div
            className="fixed inset-0 bg-black/20"
            aria-hidden="true"
          />
        </div>
      )}

      {/* Mobile menu panel */}
      <div
        className={`fixed top-0 right-0 z-50 h-full w-64 shadow-xl transform transition-transform duration-300 ease-in-out md:hidden ${
          mobileMenuOpen ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ backgroundColor: "var(--background)" }}
      >
        <div className="flex items-center justify-between h-20 px-4 border-b" style={{ borderColor: "var(--border)" }}>
          <span className="font-bold" style={{ color: "var(--foreground)" }}>Menu</span>
          <button
            type="button"
            className="p-2 rounded-lg transition-colors"
            style={{ color: "var(--foreground-muted)" }}
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="24"
              height="24"
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

        <nav className="px-4 py-4 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));

            return (
              <Link
                key={item.name}
                href={item.href}
                className={`block px-3 py-3 rounded-lg font-medium transition-colors ${!isActive ? "mobile-nav-link" : ""}`}
                style={isActive
                  ? { backgroundColor: "var(--color-rust)", color: "white" }
                  : { color: "var(--foreground-muted)" }
                }
                onClick={() => setMobileMenuOpen(false)}
              >
                {item.name}
              </Link>
            );
          })}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between">
            <span className="text-sm" style={{ color: "var(--foreground-muted)" }}>Theme</span>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </header>
  );
}
