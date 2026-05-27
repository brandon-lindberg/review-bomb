import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/lib/site-url";

// AI crawlers we explicitly welcome. These power AI search engines and
// chat assistants (citations + training). Listing them by name documents
// intent and avoids any ambiguity for bots that check for a specific UA.
const AI_USER_AGENTS = [
  // OpenAI: GPTBot (training), OAI-SearchBot (search index), ChatGPT-User (live browsing)
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  // Anthropic / Claude
  "ClaudeBot",
  "Claude-Web",
  "anthropic-ai",
  // Google Gemini / AI Overviews
  "Google-Extended",
  // Perplexity
  "PerplexityBot",
  // Apple Intelligence
  "Applebot-Extended",
  // Amazon, Common Crawl (feeds many models), Meta AI, ByteDance
  "Amazonbot",
  "CCBot",
  "meta-externalagent",
  "Bytespider",
  // Cohere
  "cohere-ai",
];

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/"],
      },
      // Welcome AI crawlers to everything except API routes. We trade our
      // data for discovery — freshness is our moat, the live site is not
      // replaceable by a training snapshot. See SEO audit decision.
      {
        userAgent: AI_USER_AGENTS,
        allow: "/",
        disallow: ["/api/"],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
