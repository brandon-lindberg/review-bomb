"use client";

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
];

export function Header() {
  const pathname = usePathname();

  return (
    <header className="bg-white shadow-sm border-b" style={{ borderColor: "var(--border)" }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex">
            <Link href="/" className="flex items-center">
              <span className="text-xl font-bold" style={{ color: "var(--foreground)" }}>
                Review<span style={{ color: "var(--color-rust)" }}>Disparity</span>
              </span>
            </Link>
          </div>

          <div className="flex items-center gap-4">
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
          </div>
        </div>
      </div>
    </header>
  );
}
