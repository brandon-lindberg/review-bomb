import type { CSSProperties } from "react";

interface SkeletonProps {
  className?: string;
  style?: CSSProperties;
}

export function SkeletonBlock({ className = "", style }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md ${className}`.trim()}
      style={{
        backgroundColor: "var(--border)",
        opacity: 0.6,
        ...style,
      }}
    />
  );
}

export function ListPageLoading({
  rows = 8,
  showFilters = true,
}: {
  rows?: number;
  showFilters?: boolean;
}) {
  return (
    <div className="space-y-6" aria-label="Loading page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <SkeletonBlock className="h-9 w-40" />
        {showFilters && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center w-full sm:w-auto">
            <SkeletonBlock className="h-10 w-full sm:w-64" />
            <div className="flex gap-2">
              <SkeletonBlock className="h-10 flex-1 sm:w-32" />
              <SkeletonBlock className="h-10 flex-1 sm:w-40" />
            </div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="divide-y divide-gray-200">
          {Array.from({ length: rows }).map((_, index) => (
            <div key={index} className="p-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex-1 space-y-2">
                  <SkeletonBlock className="h-5 w-2/3" />
                  <div className="flex gap-2">
                    <SkeletonBlock className="h-4 w-24" />
                    <SkeletonBlock className="h-4 w-20" />
                  </div>
                </div>
                <div className="flex gap-3 sm:w-56">
                  <SkeletonBlock className="h-10 flex-1" />
                  <SkeletonBlock className="h-10 w-16" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-center gap-2">
        <SkeletonBlock className="h-10 w-24" />
        <SkeletonBlock className="h-10 w-28" />
        <SkeletonBlock className="h-10 w-24" />
      </div>
    </div>
  );
}

export function SimpleListPageLoading({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-6" aria-label="Loading page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <SkeletonBlock className="h-9 w-44" />
        <SkeletonBlock className="h-10 w-full sm:w-48" />
      </div>
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="divide-y divide-gray-200">
          {Array.from({ length: rows }).map((_, index) => (
            <div key={index} className="p-4">
              <div className="space-y-2">
                <SkeletonBlock className="h-5 w-2/3" />
                <SkeletonBlock className="h-4 w-1/2" />
                <SkeletonBlock className="h-4 w-5/6" />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="flex justify-center gap-2">
        <SkeletonBlock className="h-10 w-24" />
        <SkeletonBlock className="h-10 w-28" />
        <SkeletonBlock className="h-10 w-24" />
      </div>
    </div>
  );
}

export function NewsGridPageLoading({ cards = 9 }: { cards?: number }) {
  return (
    <div className="space-y-6" aria-label="Loading news">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <SkeletonBlock className="h-9 w-44" />
        <SkeletonBlock className="h-10 w-full sm:w-48" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Array.from({ length: cards }).map((_, index) => (
          <div key={index} className="bg-white rounded-lg shadow p-4 space-y-3">
            <SkeletonBlock className="h-40 w-full rounded-lg" />
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-5 w-5/6" />
            <SkeletonBlock className="h-4 w-full" />
            <SkeletonBlock className="h-4 w-2/3" />
          </div>
        ))}
      </div>
      <div className="flex justify-center gap-2">
        <SkeletonBlock className="h-10 w-24" />
        <SkeletonBlock className="h-10 w-28" />
        <SkeletonBlock className="h-10 w-24" />
      </div>
    </div>
  );
}

export function DetailPageLoading() {
  return (
    <div className="space-y-8" aria-label="Loading detail page">
      <section className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col md:flex-row gap-6">
          <div className="flex-1 space-y-3">
            <SkeletonBlock className="h-9 w-2/3" />
            <SkeletonBlock className="h-4 w-40" />
            <SkeletonBlock className="h-10 w-44" />
            <SkeletonBlock className="h-4 w-full" />
            <SkeletonBlock className="h-4 w-11/12" />
          </div>
          <div className="w-full md:w-64">
            <SkeletonBlock className="h-36 w-full rounded-lg" />
          </div>
        </div>
        <div className="mt-6 pt-6 border-t border-gray-200">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white rounded-lg shadow p-6">
        <SkeletonBlock className="h-6 w-48 mb-4" />
        <SkeletonBlock className="h-72 w-full rounded-lg" />
      </section>
    </div>
  );
}

export function ComparePageLoading() {
  return (
    <div className="space-y-6" aria-label="Loading compare page">
      <SkeletonBlock className="h-9 w-36" />
      <div className="border-b pb-2">
        <div className="flex gap-4">
          <SkeletonBlock className="h-8 w-24" />
          <SkeletonBlock className="h-8 w-20" />
        </div>
      </div>
      <section className="bg-white rounded-lg shadow p-6 space-y-4">
        <SkeletonBlock className="h-6 w-72" />
        <SkeletonBlock className="h-10 w-full" />
        <div className="flex gap-2">
          <SkeletonBlock className="h-8 w-32 rounded-full" />
          <SkeletonBlock className="h-8 w-28 rounded-full" />
        </div>
      </section>
      <section className="bg-white rounded-lg shadow overflow-hidden">
        <div className="p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="grid grid-cols-5 gap-3">
              <SkeletonBlock className="h-10 w-full" />
              <SkeletonBlock className="h-10 w-full" />
              <SkeletonBlock className="h-10 w-full" />
              <SkeletonBlock className="h-10 w-full" />
              <SkeletonBlock className="h-10 w-full" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function HomePageLoading() {
  return (
    <div className="space-y-12" aria-label="Loading home page">
      <section className="text-center py-12 space-y-4">
        <SkeletonBlock className="h-10 w-80 max-w-full mx-auto" />
        <SkeletonBlock className="h-5 w-[32rem] max-w-full mx-auto" />
        <SkeletonBlock className="h-5 w-[28rem] max-w-full mx-auto" />
      </section>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonBlock key={index} className="h-24 w-full rounded-lg" />
        ))}
      </section>

      <section className="grid md:grid-cols-2 gap-8">
        {Array.from({ length: 2 }).map((_, index) => (
          <div key={index} className="bg-white rounded-lg shadow p-6 space-y-4">
            <SkeletonBlock className="h-6 w-40" />
            {Array.from({ length: 5 }).map((__, row) => (
              <SkeletonBlock key={row} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ))}
      </section>

      <section className="bg-white rounded-lg shadow p-6 space-y-3">
        <SkeletonBlock className="h-6 w-32" />
        {Array.from({ length: 5 }).map((_, index) => (
          <SkeletonBlock key={index} className="h-16 w-full rounded-lg" />
        ))}
      </section>
    </div>
  );
}
