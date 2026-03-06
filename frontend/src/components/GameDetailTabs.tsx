"use client";

import { useState, type ReactNode } from "react";

interface GameDetailTabsProps {
  criticReviews: ReactNode;
  journalistAlignment: ReactNode | null;
  latestNews: ReactNode | null;
  defaultTab?: "reviews" | "alignment" | "news";
}

export function GameDetailTabs({
  criticReviews,
  journalistAlignment,
  latestNews,
  defaultTab = "reviews",
}: GameDetailTabsProps) {
  const [activeTab, setActiveTab] = useState<"reviews" | "alignment" | "news">(defaultTab);

  // If no alignment data and no news, just render reviews directly
  if (!journalistAlignment && !latestNews) {
    return (
      <section className="bg-white rounded-lg shadow p-4 sm:p-6">
        <h2 className="text-xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Critic Reviews
        </h2>
        {criticReviews}
      </section>
    );
  }

  const tabs: { id: "reviews" | "alignment" | "news"; label: string }[] = [
    { id: "reviews", label: "Critic Reviews" },
  ];
  if (journalistAlignment) tabs.push({ id: "alignment", label: "Journalist Alignment" });
  if (latestNews) tabs.push({ id: "news", label: "Latest News" });

  return (
    <section className="bg-white rounded-lg shadow">
      <div className="border-b" style={{ borderColor: "var(--border)" }}>
        <nav className="flex gap-2 sm:gap-4 px-4 sm:px-6 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="py-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer whitespace-nowrap"
              style={activeTab === tab.id
                ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                : { borderColor: "transparent", color: "var(--foreground-muted)" }
              }
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="p-4 sm:p-6">
        {activeTab === "reviews" && criticReviews}
        {activeTab === "alignment" && journalistAlignment}
        {activeTab === "news" && latestNews}
      </div>
    </section>
  );
}
