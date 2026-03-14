"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { DisparityBadge } from "@/components/DisparityBadge";
import { buildEntityPath } from "@/lib/entity-paths";

type PlatformFilter = "combined" | "steam" | "metacritic";

export interface AlignmentJournalist {
  id: number;
  publicId: string;
  name: string;
  imageUrl: string | null;
  outletName: string | null;
  score: number;
  disparitySteam: number | null;
  disparityMetacritic: number | null;
  disparityCombined: number | null;
}

interface JournalistAlignmentSectionProps {
  journalists: AlignmentJournalist[];
}

function useIsDarkMode() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const checkDarkMode = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };

    checkDarkMode();

    const observer = new MutationObserver(checkDarkMode);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return isDark;
}

const getThemeColors = (isDark: boolean) => ({
  rust: isDark ? "#E05A2B" : "#BB3B0E",
  orange: isDark ? "#E8904D" : "#DD7631",
  sage: isDark ? "#8FA87A" : "#708160",
  text: isDark ? "#B8B4AC" : "#6b7280",
  textStrong: isDark ? "#F5F3EF" : "#2D2A26",
  muted: isDark ? "#6A655C" : "#9ca3af",
  inactiveBg: isDark ? "#3D3A35" : "#f3f4f6",
  hoverBg: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.03)",
  avatarBg: isDark ? "#3D3A35" : "#e5e7eb",
  avatarText: isDark ? "#B8B4AC" : "#6b7280",
});

const PLATFORM_LABELS: Record<PlatformFilter, string> = {
  combined: "Combined",
  steam: "Steam",
  metacritic: "Metacritic",
};

function getDisparity(j: AlignmentJournalist, platform: PlatformFilter): number | null {
  if (platform === "steam") return j.disparitySteam;
  if (platform === "metacritic") return j.disparityMetacritic;
  return j.disparityCombined;
}

function getPlatformColor(platform: PlatformFilter, colors: ReturnType<typeof getThemeColors>): string {
  if (platform === "steam") return colors.sage;
  if (platform === "metacritic") return colors.orange;
  return colors.rust;
}

export function JournalistAlignmentSection({ journalists }: JournalistAlignmentSectionProps) {
  const [platform, setPlatform] = useState<PlatformFilter>("combined");
  const isDark = useIsDarkMode();
  const colors = getThemeColors(isDark);

  const hasSteam = journalists.some(j => j.disparitySteam !== null);
  const hasMetacritic = journalists.some(j => j.disparityMetacritic !== null);

  const filtered = journalists.filter(j => getDisparity(j, platform) !== null);

  const topGenerous = filtered
    .filter(j => (getDisparity(j, platform) ?? 0) > 0)
    .sort((a, b) => (getDisparity(b, platform) ?? 0) - (getDisparity(a, platform) ?? 0))
    .slice(0, 5);

  const topCritical = filtered
    .filter(j => (getDisparity(j, platform) ?? 0) < 0)
    .sort((a, b) => (getDisparity(a, platform) ?? 0) - (getDisparity(b, platform) ?? 0))
    .slice(0, 5);

  const platformEnabled: Record<PlatformFilter, boolean> = {
    combined: true,
    steam: hasSteam,
    metacritic: hasMetacritic,
  };

  const renderJournalist = (j: AlignmentJournalist, i: number) => {
    const disparity = getDisparity(j, platform) ?? 0;
    return (
      <Link
        key={j.id}
        href={buildEntityPath("journalists", j.name, j.publicId)}
        className="flex items-center justify-between p-3 rounded-lg transition-colors"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = colors.hoverBg}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "transparent"}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm w-5 text-right flex-shrink-0" style={{ color: colors.muted }}>{i + 1}</span>
          {j.imageUrl ? (
            <img src={j.imageUrl} alt={j.name} className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
          ) : (
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: colors.avatarBg }}
            >
              <span className="text-xs" style={{ color: colors.avatarText }}>{j.name.charAt(0)}</span>
            </div>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: colors.textStrong }}>{j.name}</p>
            {j.outletName && (
              <p className="text-xs truncate" style={{ color: colors.text }}>{j.outletName}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0 ml-2">
          <span className="text-sm" style={{ color: colors.text }}>
            Score: {j.score.toFixed(0)}
          </span>
          <DisparityBadge disparity={disparity} size="sm" />
        </div>
      </Link>
    );
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <p className="text-sm" style={{ color: colors.text }}>
          How individual critics scored this game compared to user consensus
        </p>
        <div className="flex gap-2">
          {(["combined", "steam", "metacritic"] as PlatformFilter[]).map((p) => {
            const enabled = platformEnabled[p];
            const active = platform === p;
            const typeColor = getPlatformColor(p, colors);

            return (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                disabled={!enabled}
                className={`px-3 py-1.5 text-sm rounded-lg transition-all cursor-pointer ${
                  !enabled ? "opacity-40 cursor-not-allowed" : "hover:opacity-80"
                }`}
                style={{
                  backgroundColor: active ? typeColor : colors.inactiveBg,
                  color: active ? "white" : colors.text,
                  border: `2px solid ${enabled ? typeColor : "transparent"}`,
                }}
              >
                {PLATFORM_LABELS[p]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: colors.text }}>
            Scored Higher Than Users
          </h3>
          <div className="space-y-2">
            {topGenerous.length > 0 ? (
              topGenerous.map(renderJournalist)
            ) : (
              <p className="text-sm py-3" style={{ color: colors.muted }}>No critics scored higher than users</p>
            )}
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider mb-3" style={{ color: colors.text }}>
            Scored Lower Than Users
          </h3>
          <div className="space-y-2">
            {topCritical.length > 0 ? (
              topCritical.map(renderJournalist)
            ) : (
              <p className="text-sm py-3" style={{ color: colors.muted }}>No critics scored lower than users</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
