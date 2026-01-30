import Link from "next/link";
import { notFound } from "next/navigation";
import { getOutlet, getJournalists } from "@/lib/api";
import { DisparityBadge } from "@/components/DisparityBadge";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function OutletDetailPage({ params }: PageProps) {
  const { id } = await params;

  let outlet = null;

  try {
    outlet = await getOutlet(parseInt(id));
  } catch (error) {
    console.error("Error fetching outlet:", error);
    notFound();
  }

  if (!outlet) {
    notFound();
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row md:items-start gap-6">
          <div className="flex-shrink-0">
            {outlet.logo_url ? (
              <img
                src={outlet.logo_url}
                alt={outlet.name}
                className="w-24 h-24 rounded object-contain bg-gray-100"
              />
            ) : (
              <div className="w-24 h-24 rounded bg-gray-200 flex items-center justify-center">
                <span className="text-gray-500 text-3xl font-medium">
                  {outlet.name.charAt(0)}
                </span>
              </div>
            )}
          </div>

          <div className="flex-1">
            <div className="flex items-center gap-4">
              <h1 className="text-3xl font-bold text-gray-900">
                {outlet.name}
              </h1>
              {outlet.website_url && (
                <a
                  href={outlet.website_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-800 text-sm"
                >
                  Visit Website
                </a>
              )}
            </div>

            {/* Stats Grid */}
            <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Overall Disparity"
                value={
                  outlet.avg_disparity !== null ? (
                    <DisparityBadge disparity={outlet.avg_disparity} size="lg" />
                  ) : (
                    "N/A"
                  )
                }
              />
              <StatCard
                label="Total Reviews"
                value={outlet.review_count?.toString() ?? "0"}
              />
              <StatCard
                label="Journalists"
                value={outlet.journalist_count?.toString() ?? "0"}
              />
              <StatCard
                label="Average Score"
                value={outlet.avg_score != null ? Number(outlet.avg_score).toFixed(1) : "N/A"}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Journalists at this outlet */}
      {outlet.journalists && outlet.journalists.length > 0 && (
        <section className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Journalists
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {outlet.journalists.map((journalist) => (
              <Link
                key={journalist.id}
                href={`/journalists/${journalist.id}`}
                className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {journalist.image_url ? (
                    <img
                      src={journalist.image_url}
                      alt={journalist.name}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                      <span className="text-gray-500 font-medium">
                        {journalist.name.charAt(0)}
                      </span>
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-gray-900">
                      {journalist.name}
                    </p>
                    <p className="text-sm text-gray-500">
                      {journalist.review_count} reviews
                    </p>
                  </div>
                </div>
                <DisparityBadge disparity={journalist.avg_disparity} />
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Recent reviews placeholder */}
      <section className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900">
            Recent Reviews
          </h2>
        </div>
        <p className="text-gray-500 text-center py-8">
          Review listings coming soon.
        </p>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="p-4 bg-gray-50 rounded-lg text-center">
      <div className="text-2xl font-bold text-gray-900 flex justify-center">
        {value}
      </div>
      <p className="text-sm text-gray-600 mt-1">{label}</p>
    </div>
  );
}
