"use client";

import { useEffect } from "react";
import { saveRecentPageView } from "@/lib/recent-page-history";

interface RecentEntityViewSyncProps {
  href: string;
  imageUrl?: string | null;
  subtitle: string;
  title: string;
}

export function RecentEntityViewSync({
  href,
  imageUrl,
  subtitle,
  title,
}: RecentEntityViewSyncProps) {
  useEffect(() => {
    saveRecentPageView({
      href,
      imageUrl: imageUrl ?? undefined,
      subtitle,
      title,
    });
  }, [href, imageUrl, subtitle, title]);

  return null;
}
