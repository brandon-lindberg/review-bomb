"use client";

import { useState, type ReactNode } from "react";

interface GameDetailTabsProps {
  criticReviews: ReactNode;
  journalistAlignment: ReactNode | null;
}

export function GameDetailTabs({ criticReviews, journalistAlignment }: GameDetailTabsProps) {
  const [activeTab, setActiveTab] = useState<"reviews" | "alignment">("reviews");

  // If no alignment data, just render reviews directly
  if (!journalistAlignment) {
    return (
      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          Critic Reviews
        </h2>
        {criticReviews}
      </section>
    );
  }

  const tabs = [
    { id: "reviews" as const, label: "Critic Reviews" },
    { id: "alignment" as const, label: "Journalist Alignment" },
  ];

  return (
    <section className="bg-white rounded-lg shadow">
      <div className="border-b" style={{ borderColor: "var(--border)" }}>
        <nav className="flex gap-4 px-6">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="py-3 px-1 border-b-2 font-medium text-sm transition-colors cursor-pointer"
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
      <div className="p-6">
        {activeTab === "reviews" ? criticReviews : journalistAlignment}
      </div>
    </section>
  );
}
