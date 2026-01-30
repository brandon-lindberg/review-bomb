import Link from "next/link";
import { getOutlets } from "@/lib/api";
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

export default async function OutletsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parseInt(params.page || "1");
  const sortBy = params.sort || "disparity";
  const sortOrder = params.order || "desc";

  let outlets = null;
  try {
    outlets = await getOutlets(page, 20, sortBy, sortOrder);
  } catch (error) {
    console.error("Error fetching outlets:", error);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-3xl font-bold text-gray-900">Outlets</h1>

        <div className="flex gap-2">
          <SortSelect
            options={sortOptions}
            defaultValue={`${sortBy}-${sortOrder}`}
            paramName="sort"
            paramName2="order"
          />
        </div>
      </div>

      {outlets ? (
        <>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="divide-y divide-gray-200">
              {outlets.items.map((outlet) => (
                <Link
                  key={outlet.id}
                  href={`/outlets/${outlet.id}`}
                  className="block p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      {outlet.logo_url ? (
                        <img
                          src={outlet.logo_url}
                          alt={outlet.name}
                          className="w-12 h-12 rounded object-contain bg-gray-100"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded bg-gray-200 flex items-center justify-center">
                          <span className="text-gray-500 text-lg font-medium">
                            {outlet.name.charAt(0)}
                          </span>
                        </div>
                      )}
                      <div>
                        <h2 className="text-lg font-medium text-gray-900">
                          {outlet.name}
                        </h2>
                        <p className="text-sm text-gray-500">
                          {outlet.review_count} reviews |{" "}
                          {outlet.journalist_count} journalists
                        </p>
                      </div>
                    </div>

                    <DisparityBadge disparity={outlet.avg_disparity} />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Pagination */}
          {outlets.total_pages > 1 && (
            <div className="flex justify-center gap-2">
              {page > 1 && (
                <Link
                  href={`/outlets?page=${page - 1}&sort=${sortBy}&order=${sortOrder}`}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              <span className="px-4 py-2 text-gray-600">
                Page {page} of {outlets.total_pages}
              </span>
              {page < outlets.total_pages && (
                <Link
                  href={`/outlets?page=${page + 1}&sort=${sortBy}&order=${sortOrder}`}
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
            Unable to load outlets. Make sure the backend API is running.
          </p>
        </div>
      )}
    </div>
  );
}
