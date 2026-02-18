const DEFAULT_SITE_URL = "https://reviewdisparity.com";
const CANONICAL_HOST = "reviewdisparity.com";

function parseSiteUrl(rawSiteUrl?: string): URL | null {
  if (!rawSiteUrl) return null;

  const trimmed = rawSiteUrl.trim();
  if (!trimmed) return null;

  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;

  try {
    return new URL(candidate);
  } catch {
    return null;
  }
}

export function getSiteUrl(): string {
  const parsed = parseSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);
  if (!parsed) return DEFAULT_SITE_URL;

  const hostname = parsed.hostname.toLowerCase();

  if (hostname === "localhost" || hostname === "127.0.0.1") {
    return `${parsed.protocol}//${parsed.host}`;
  }

  if (hostname === CANONICAL_HOST || hostname === `www.${CANONICAL_HOST}`) {
    return DEFAULT_SITE_URL;
  }

  return `${parsed.protocol}//${parsed.host}`;
}

export { CANONICAL_HOST, DEFAULT_SITE_URL };
