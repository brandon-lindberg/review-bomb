"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  getCompareMetricOptions,
  serializeCompareMetricSelection,
  type CompareMetricId,
  type CompareType,
} from "@/lib/compare-metrics";

interface CompareMetricControlsProps {
  type: CompareType;
  selectedMetricIds: CompareMetricId[];
}

export function CompareMetricControls({
  type,
  selectedMetricIds,
}: CompareMetricControlsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isNavigating, startTransition] = useTransition();
  const metricOptions = getCompareMetricOptions(type);

  const navigateWithMetrics = (metricIds: CompareMetricId[]) => {
    const params = new URLSearchParams(searchParams.toString());
    const serialized = serializeCompareMetricSelection(type, metricIds);

    if (serialized) {
      params.set("metrics", serialized);
    } else {
      params.delete("metrics");
    }

    params.set("type", type);
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    startTransition(() => {
      router.replace(nextUrl, { scroll: false });
    });
  };

  const handleShowAll = () => {
    if (isNavigating) return;
    navigateWithMetrics(metricOptions.map((metric) => metric.id));
  };

  const hiddenCount = metricOptions.length - selectedMetricIds.length;
  if (hiddenCount === 0) {
    return null;
  }

  return (
    <div className="flex justify-end">
      <button
        type="button"
        onClick={handleShowAll}
        disabled={isNavigating}
        className="inline-flex items-center gap-3 rounded-full border px-4 py-2 disabled:opacity-60"
        style={{
          borderColor: "color-mix(in srgb, var(--color-rust) 36%, transparent)",
          backgroundColor: "color-mix(in srgb, var(--background-card-strong) 84%, var(--color-rust) 16%)",
          color: "var(--foreground)",
        }}
        aria-label={`Show ${hiddenCount} hidden row${hiddenCount === 1 ? "" : "s"}`}
      >
        <span className="text-sm font-medium">
          {`Show ${hiddenCount} hidden row${hiddenCount === 1 ? "" : "s"}`}
        </span>
        <span
          className="relative inline-flex h-6 w-11 shrink-0 rounded-full border"
          style={{
            borderColor: "color-mix(in srgb, var(--color-rust) 42%, transparent)",
            backgroundColor: "color-mix(in srgb, var(--color-rust) 32%, var(--background-card-strong) 68%)",
          }}
          aria-hidden="true"
        >
          <span
            className="absolute top-0.5 h-5 w-5 rounded-full translate-x-5"
            style={{
              backgroundColor: "var(--background-card-strong)",
              boxShadow: "0 2px 8px rgba(0, 0, 0, 0.18)",
            }}
          />
        </span>
      </button>
    </div>
  );
}
