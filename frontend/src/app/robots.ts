import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/lib/site-url";

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/*?*page="],
      },
      {
        userAgent: "GPTBot",
        disallow: "/",
      },
      {
        userAgent: "ChatGPT-User",
        disallow: "/",
      },
      {
        userAgent: "CCBot",
        disallow: "/",
      },
      {
        userAgent: "anthropic-ai",
        disallow: "/",
      },
      {
        userAgent: "Claude-Web",
        disallow: "/",
      },
      {
        userAgent: "Bytespider",
        disallow: "/",
      },
      {
        userAgent: "ClaudeBot",
        disallow: "/",
      },
      {
        userAgent: "meta-externalagent",
        disallow: "/",
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
