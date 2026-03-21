"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  getCompareMetricOptions,
  serializeCompareMetricSelection,
  type CompareMetricId,
  type CompareType,
} from "@/lib/compare-metrics";

interface CompareMetricRowToggleProps {
  type: CompareType;
  metricId: CompareMetricId;
  label: string;
  selectedMetricIds: CompareMetricId[];
}

export function CompareMetricRowToggle({
  type,
  metricId,
  label,
  selectedMetricIds,
}: CompareMetricRowToggleProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isNavigating, startTransition] = useTransition();
  const metricOptions = getCompareMetricOptions(type);
  const selectedSet = new Set(selectedMetricIds);
  const isSelected = selectedSet.has(metricId);
  const isDisabled = isNavigating;

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

  const handleToggle = () => {
    if (isDisabled) return;

    if (isSelected) {
      navigateWithMetrics(selectedMetricIds.filter((id) => id !== metricId));
      return;
    }

    const nextSelection = metricOptions
      .map((metric) => metric.id)
      .filter((id) => selectedSet.has(id) || id === metricId);
    navigateWithMetrics(nextSelection);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isSelected}
      aria-label={`${isSelected ? "Hide" : "Show"} ${label}`}
      onClick={handleToggle}
      disabled={isDisabled}
      className="relative inline-flex h-6 w-11 shrink-0 rounded-full border disabled:cursor-not-allowed disabled:opacity-60"
      style={{
        borderColor: isSelected
          ? "color-mix(in srgb, var(--color-rust) 42%, transparent)"
          : "var(--border)",
        backgroundColor: isSelected
          ? "color-mix(in srgb, var(--color-rust) 32%, var(--background-card-strong) 68%)"
          : "color-mix(in srgb, var(--background-soft) 80%, transparent)",
        boxShadow: isSelected ? "0 0 0 1px rgba(0, 0, 0, 0.04)" : "none",
      }}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full transition-transform ${
          isSelected ? "translate-x-5" : "translate-x-0.5"
        }`}
        style={{
          backgroundColor: "var(--background-card-strong)",
          boxShadow: "0 2px 8px rgba(0, 0, 0, 0.18)",
        }}
      />
    </button>
  );
}
