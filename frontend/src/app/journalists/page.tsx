import type { Metadata } from "next";
import Link from "next/link";
import { getJournalists } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { SortSelect } from "@/components/SortSelect";
import { SearchInput } from "@/components/SearchInput";

export const dynamic = "force-dynamic";

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const { page: pageParam } = await searchParams;
  const page = parseInt(pageParam || "1");

  return {
    title: "Game Journalists",
    description:
      "Browse game journalists and see how their review scores compare to player opinions. Track critic-to-user score disparity.",
    alternates: { canonical: "/journalists" },
    ...(page > 1 && { robots: { index: false, follow: true } }),
    openGraph: {
      title: "Game Journalists - ReviewDisparity",
      description:
        "Browse game journalists and see how their review scores compare to player opinions.",
      url: "/journalists",
    },
  };
}

interface PageProps {
  searchParams: Promise<{
    page?: string;
    sort?: string;
    order?: string;
    search?: string;
  }>;
}

const sortOptions = [
  { value: "latest_review-desc", label: "Most Recent" },
  { value: "review_count-desc", label: "Most Reviews" },
  { value: "review_count-asc", label: "Fewest Reviews" },
  { value: "disparity-desc", label: "Highest Disparity" },
  { value: "disparity-asc", label: "Lowest Disparity" },
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
];

export default async function JournalistsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "latest_review";
  const sortOrder = params.order || "desc";
  const search = params.search || "";

  let journalists = null;
  try {
    journalists = await getJournalists(page, 20, sortBy, sortOrder, search || undefined);
  } catch (error) {
    console.error("Error fetching journalists:", error);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Journalists</h1>

        <div className="flex gap-2 items-center">
          <SearchInput defaultValue={search} placeholder="Search journalists..." />
          <SortSelect
            options={sortOptions}
            defaultValue={`${sortBy}-${sortOrder}`}
            paramName="sort"
            paramName2="order"
          />
        </div>
      </div>

      {journalists ? (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="divide-y divide-gray-200">
              {journalists.items.map((journalist) => (
                <Link
                  key={journalist.id}
                  href={`/journalists/${journalist.id}`}
                  className="block p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      {journalist.image_url ? (
                        <img
                          src={journalist.image_url}
                          alt={journalist.name}
                          className="w-12 h-12 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center">
                          <span className="text-gray-500 text-lg font-medium">
                            {journalist.name.charAt(0)}
                          </span>
                        </div>
                      )}
                      <div>
                        <h2 className="text-lg font-medium text-gray-900">
                          {journalist.name}
                        </h2>
                        <p className="text-sm text-gray-500">
                          {journalist.review_count} reviews
                        </p>
                      </div>
                    </div>

                    <DisparityBadge disparity={journalist.avg_disparity} />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Pagination */}
          {journalists.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/journalists?page=${page - 1}&sort=${sortBy}&order=${sortOrder}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  prefetch={false}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {journalists.total_pages}
              </span>
              {page < journalists.total_pages && (
                <Link
                  href={`/journalists?page=${page + 1}&sort=${sortBy}&order=${sortOrder}${search ? `&search=${encodeURIComponent(search)}` : ""}`}
                  prefetch={false}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Next
                </Link>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <p className="text-gray-600">
            Unable to load journalists. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
