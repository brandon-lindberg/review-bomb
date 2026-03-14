"use client";

import { useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { emitNavigationStart } from "@/lib/navigation-progress";
import { SiteSelect } from "@/components/SiteSelect";

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

  const handleChange = (value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("source", value);
    } else {
      params.delete("source");
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
        { value: "", label: "All Sources" },
        ...sources.map((source) => ({ value: source, label: source })),
      ]}
      value={currentValue}
      onChange={handleChange}
      disabled={isPending}
      pending={isPending}
    />
  );
}
