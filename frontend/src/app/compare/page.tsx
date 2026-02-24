import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { getJournalist, getJournalistHistory, getOutlet, getOutletHistory } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { MiniDisparityChart } from "@/components/DisparityChart";
import { CompareSelector } from "@/components/CompareSelector";
import type { JournalistDetail, OutletWithStats, DisparitySnapshot } from "@/types";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Compare Critics",
  description:
    "Compare game journalists and outlets side by side. See how their review scores and disparity trends differ over time.",
  alternates: { canonical: "/compare" },
  openGraph: {
    title: "Compare Critics - ReviewDisparity",
    description:
      "Compare game journalists and outlets side by side. See how their review scores and disparity trends differ.",
    url: "/compare",
  },
};

interface PageProps {
  searchParams: Promise<{
    type?: string;
    ids?: string;
  }>;
}

interface CompareData {
  id: number;
  name: string;
  image_url: string | null;
  review_count: number;
  avg_disparity: number | null;
  avg_score: number | null;
  history: DisparitySnapshot[];
  linkHref: string;
}

export default async function ComparePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const type = params.type || "journalists";
  const ids = params.ids ? params.ids.split(",").map((id) => parseInt(id)).filter((id) => !isNaN(id)) : [];

  const tabs = [
    { id: "journalists", label: "Journalists" },
    { id: "outlets", label: "Outlets" },
  ];

  // Fetch data for selected items
  const compareData: CompareData[] = [];

  if (ids.length > 0) {
    try {
      if (type === "journalists") {
        const results = await Promise.all(
          ids.slice(0, 4).map(async (id) => {
            try {
              const [journalist, history] = await Promise.all([
                getJournalist(id),
                getJournalistHistory(id),
              ]);
              return { journalist, history };
            } catch {
              return null;
            }
          })
        );

        for (const result of results) {
          if (result) {
            compareData.push({
              id: result.journalist.id,
              name: result.journalist.name,
              image_url: result.journalist.image_url,
              review_count: result.journalist.review_count,
              avg_disparity: result.journalist.avg_disparity,
              avg_score: result.journalist.stats?.avg_score_given ?? null,
              history: result.history,
              linkHref: `/journalists/${result.journalist.id}`,
            });
          }
        }
      } else if (type === "outlets") {
        const results = await Promise.all(
          ids.slice(0, 4).map(async (id) => {
            try {
              const [outlet, history] = await Promise.all([
                getOutlet(id),
                getOutletHistory(id),
              ]);
              return { outlet, history };
            } catch {
              return null;
            }
          })
        );

        for (const result of results) {
          if (result) {
            compareData.push({
              id: result.outlet.id,
              name: result.outlet.name,
              image_url: result.outlet.logo_url,
              review_count: result.outlet.review_count ?? 0,
              avg_disparity: result.outlet.avg_disparity ?? null,
              avg_score: result.outlet.avg_score ?? null,
              history: result.history,
              linkHref: `/outlets/${result.outlet.id}`,
            });
          }
        }
      }
    } catch (error) {
      console.error("Error fetching compare data:", error);
    }
  }

  // Brand colors for comparison charts
  const colors = ["#BB3B0E", "#DD7631", "#708160", "#D8C593"];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Compare</h1>
      </div>

      {/* Tab Navigation */}
      <div className="border-b" style={{ borderColor: "var(--border)" }}>
        <nav className="flex gap-4">
          {tabs.map((t) => (
            <Link
              key={t.id}
              href={`/compare?type=${t.id}`}
              className="py-3 px-1 border-b-2 font-medium text-sm transition-colors"
              style={type === t.id
                ? { borderColor: "var(--color-rust)", color: "var(--color-rust)" }
                : { borderColor: "transparent", color: "var(--foreground-muted)" }
              }
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </div>

      {/* Selector */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Select {type === "journalists" ? "Journalists" : "Outlets"} to Compare
        </h2>
        <Suspense fallback={<CompareSelectorFallback />}>
          <CompareSelector
            type={type as "journalists" | "outlets"}
            selectedIds={ids}
            selectedItems={compareData.map((item) => ({
              id: item.id,
              name: item.name,
              image_url: item.image_url,
            }))}
            maxSelections={4}
          />
        </Suspense>
      </div>

      {/* Comparison Grid */}
      {compareData.length > 0 ? (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 w-40">
                    Metric
                  </th>
                  {compareData.map((item, index) => (
                    <th
                      key={item.id}
                      className="px-4 py-3 text-center text-sm font-medium text-gray-900 min-w-[200px]"
                    >
                      <div className="flex flex-col items-center gap-2">
                        {item.image_url ? (
                          <img
                            src={item.image_url}
                            alt={item.name}
                            className="w-12 h-12 rounded-full object-cover"
                          />
                        ) : (
                          <div
                            className="w-12 h-12 rounded-full flex items-center justify-center text-white font-medium"
                            style={{ backgroundColor: colors[index] }}
                          >
                            {item.name.charAt(0)}
                          </div>
                        )}
                        <Link
                          href={item.linkHref}
                          className="transition-colors hover:opacity-80"
                          style={{ color: "var(--color-rust)" }}
                        >
                          {item.name}
                        </Link>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {/* Disparity Row */}
                <tr>
                  <td className="px-4 py-4 text-sm font-medium text-gray-700">
                    Avg Disparity
                  </td>
                  {compareData.map((item) => (
                    <td key={item.id} className="px-4 py-4 text-center">
                      <div className="flex justify-center">
                        <DisparityBadge disparity={item.avg_disparity} />
                      </div>
                    </td>
                  ))}
                </tr>

                {/* Review Count Row */}
                <tr className="bg-gray-50">
                  <td className="px-4 py-4 text-sm font-medium text-gray-700">
                    Total Reviews
                  </td>
                  {compareData.map((item) => (
                    <td
                      key={item.id}
                      className="px-4 py-4 text-center text-gray-900 font-medium"
                    >
                      {item.review_count.toLocaleString()}
                    </td>
                  ))}
                </tr>

                {/* Avg Score Row */}
                <tr>
                  <td className="px-4 py-4 text-sm font-medium text-gray-700">
                    Avg Score Given
                  </td>
                  {compareData.map((item) => (
                    <td
                      key={item.id}
                      className="px-4 py-4 text-center text-gray-900 font-medium"
                    >
                      {item.avg_score != null
                        ? Number(item.avg_score).toFixed(1)
                        : "N/A"}
                    </td>
                  ))}
                </tr>

                {/* Trend Chart Row */}
                <tr className="bg-gray-50">
                  <td className="px-4 py-4 text-sm font-medium text-gray-700">
                    <div>Disparity Trend</div>
                    <div className="text-xs font-normal text-gray-500 mt-1">
                      Combined disparity over time
                    </div>
                  </td>
                  {compareData.map((item, index) => (
                    <td key={item.id} className="px-4 py-4">
                      <MiniDisparityChart
                        data={item.history}
                        color={colors[index]}
                        height={100}
                      />
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ) : ids.length > 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Unable to load comparison data. Please try again.
          </p>
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-500">
            Select up to 4 {type === "journalists" ? "journalists" : "outlets"} to
            compare their disparity metrics side by side.
          </p>
        </div>
      )}
    </div>
  );
}

function CompareSelectorFallback() {
  return (
    <div className="space-y-4" aria-busy="true">
      <div className="h-10 w-full rounded-lg bg-gray-100 animate-pulse" />
      <div className="flex flex-wrap gap-2">
        <div className="h-8 w-24 rounded-full bg-gray-100 animate-pulse" />
        <div className="h-8 w-28 rounded-full bg-gray-100 animate-pulse" />
      </div>
    </div>
  );
}
