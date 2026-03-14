"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";
import { SiteSelect } from "@/components/SiteSelect";

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

  const handleChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());

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
      router.replace(nextUrl, { scroll: false });
    });
  };

  return (
    <SiteSelect
      options={options}
      value={currentValue}
      onChange={handleChange}
      className={className}
      disabled={isPending}
      pending={isPending}
    />
  );
}
