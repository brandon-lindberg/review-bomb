"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";

interface SortOption {
  value: string;
  label: string;
}

interface SortSelectProps {
  options: SortOption[];
  defaultValue: string;
  paramName?: string;
  paramName2?: string;
  className?: string;
}

export function SortSelect({
  options,
  defaultValue,
  paramName = "sort",
  paramName2,
  className,
}: SortSelectProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const currentValue = paramName2
    ? (() => {
        const value1 = searchParams.get(paramName);
        const value2 = searchParams.get(paramName2);
        return value1 && value2 ? `${value1}-${value2}` : defaultValue;
      })()
    : (searchParams.get(paramName) ?? defaultValue);

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const params = new URLSearchParams(searchParams.toString());
    const value = e.target.value;

    if (paramName2) {
      // Split value for two params (e.g., "disparity-desc" -> sort=disparity, order=desc)
      const [val1, val2] = value.split("-");
      params.set(paramName, val1);
      params.set(paramName2, val2);
    } else {
      params.set(paramName, value);
    }

    params.delete("page");
    const nextUrl = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    emitNavigationStart();
    startTransition(() => {
      router.replace(nextUrl);
    });
  };

  return (
    <div className={`relative${className ? ` ${className}` : ""}`}>
      <select
        className="w-full pl-4 pr-10 py-2 border border-gray-300 rounded-lg text-sm appearance-none bg-no-repeat disabled:opacity-80"
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
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
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
