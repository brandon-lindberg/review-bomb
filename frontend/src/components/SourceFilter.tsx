"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";

interface SourceFilterProps {
  sources: string[];
  defaultValue: string | undefined;
}

export function SourceFilter({ sources, defaultValue }: SourceFilterProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const currentValue = searchParams.get("source") ?? (defaultValue || "");

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const params = new URLSearchParams(searchParams.toString());
    if (e.target.value) {
      params.set("source", e.target.value);
    } else {
      params.delete("source");
    }
    params.delete("page");
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    emitNavigationStart();
    startTransition(() => {
      router.replace(nextUrl);
    });
  };

  return (
    <div className="relative">
      <select
        className="pl-4 pr-10 py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat disabled:opacity-80"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%235C574F' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
          backgroundPosition: "right 0.75rem center",
          backgroundSize: "1rem",
          cursor: isPending ? "progress" : undefined,
        }}
        value={currentValue}
        onChange={handleChange}
        disabled={isPending}
        aria-busy={isPending}
      >
        <option value="">All Sources</option>
        {sources.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      {isPending && (
        <span
          aria-hidden="true"
          className="absolute right-8 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin rounded-full border-2 border-solid border-t-transparent"
          style={{ borderColor: "var(--foreground-muted)", borderTopColor: "transparent" }}
        />
      )}
    </div>
  );
}
