import { getSiteUrl } from "@/lib/site-url";

// Served as a route handler (instead of Next's MetadataRoute.Robots) because
// Next's typed robots generator cannot emit the Content-Signal directive.
// Keep the emitted rules byte-compatible with the previous robots.ts output.

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

// Content Signals (https://contentsignals.org/): no AI training, but search
// indexing and AI answering from live content are welcome — freshness is the
// moat, a training snapshot is not a substitute for the live site.
const CONTENT_SIGNAL = "ai-train=no, search=yes, ai-input=yes";

export const dynamic = "force-static";

export function GET(): Response {
  const siteUrl = getSiteUrl();

  const body = [
    "User-Agent: *",
    "Allow: /",
    "Disallow: /api/",
    `Content-Signal: ${CONTENT_SIGNAL}`,
    "",
    // Welcome AI crawlers to everything except API routes. We trade our
    // data for discovery — freshness is our moat, the live site is not
    // replaceable by a training snapshot. See SEO audit decision.
    ...AI_USER_AGENTS.map((userAgent) => `User-Agent: ${userAgent}`),
    "Allow: /",
    "Disallow: /api/",
    "",
    `Sitemap: ${siteUrl}/sitemap.xml`,
    "",
  ].join("\n");

  return new Response(body, {
    headers: {
      "Content-Type": "text/plain",
    },
  });
}
