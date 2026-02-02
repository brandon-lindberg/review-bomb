import Link from "next/link";
import { getJournalists } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";
import { SortSelect } from "@/components/SortSelect";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{
    page?: string;
    sort?: string;
    order?: string;
  }>;
}

const sortOptions = [
  { value: "disparity-desc", label: "Highest Disparity" },
  { value: "disparity-asc", label: "Lowest Disparity" },
  { value: "review_count-desc", label: "Most Reviews" },
  { value: "review_count-asc", label: "Fewest Reviews" },
  { value: "name-asc", label: "Name (A-Z)" },
  { value: "name-desc", label: "Name (Z-A)" },
];

export default async function JournalistsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "disparity";
  const sortOrder = params.order || "desc";

  let journalists = null;
  try {
    journalists = await getJournalists(page, 20, sortBy, sortOrder);
  } catch (error) {
    console.error("Error fetching journalists:", error);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold" style={{ color: "var(--foreground)" }}>Journalists</h1>

        <div className="flex gap-2">
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
                  href={`/journalists?page=${page - 1}&sort=${sortBy}&order=${sortOrder}`}
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
                  href={`/journalists?page=${page + 1}&sort=${sortBy}&order=${sortOrder}`}
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
