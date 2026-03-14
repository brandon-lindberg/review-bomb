"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";
import { SiteSelect } from "@/components/SiteSelect";

interface YearFilterProps {
  years: number[];
  defaultValue: number | undefined;
  className?: string;
}

export function YearFilter({ years, defaultValue, className }: YearFilterProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const currentValue = searchParams.get("year") ?? (defaultValue?.toString() ?? "");

  const handleChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("year", value);
    } else {
      params.delete("year");
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
      options={[
        { value: "", label: "All Years" },
        ...years.map((y) => ({ value: y.toString(), label: y.toString() })),
      ]}
      value={currentValue}
      onChange={handleChange}
      className={className}
      disabled={isPending}
      pending={isPending}
    />
  );
}
