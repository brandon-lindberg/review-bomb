import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getServerApiUrl } from "@/lib/api-base-url";
import {
  encodeEntityPathname,
  type EntityRouteType,
} from "@/lib/entity-paths";
import { resolveEntityRequest } from "@/lib/entity-request-policy";

const API_URL = getServerApiUrl();
const ENTITY_TYPES = new Set<EntityRouteType>(["games", "journalists", "outlets"]);
const ENTITY_CACHE_CONTROL = "public, max-age=0, s-maxage=60, stale-while-revalidate=300";

// Content negotiation: requests that explicitly list text/markdown in Accept
// get a Markdown rendering of the same public page (homepage and entity
// detail pages), served by /md/... route handlers via rewrite. Browsers never
// send text/markdown, so normal traffic is untouched.
function acceptsMarkdown(request: NextRequest): boolean {
  if (request.method !== "GET") return false;
  const accept = request.headers.get("accept");
  if (!accept) return false;
  return accept
    .split(",")
    .some((part) => part.split(";")[0].trim().toLowerCase() === "text/markdown");
}

// Signal that negotiated routes vary by Accept. Note: Next currently owns the
// Vary header on HTML/RSC responses and may drop this append there; the
// Markdown responses set their own `Vary: Accept` (see the /md route handler),
// which is the variant a shared cache must never serve to browsers. The
// negotiation decision itself is made per-request here, before any Next cache.
function passThroughWithVary(cacheEntityHtml = false): NextResponse {
  const response = NextResponse.next();
  response.headers.append("Vary", "Accept");
  if (cacheEntityHtml) {
    response.headers.set("Cache-Control", ENTITY_CACHE_CONTROL);
  }
  return response;
}

function entityErrorResponse(request: NextRequest, status: 404 | 503): NextResponse {
  const isUnavailable = status === 503;
  const title = isUnavailable ? "Temporarily unavailable" : "Page not found";
  const message = isUnavailable
    ? "This page is temporarily unavailable. Please try again shortly."
    : "The requested page does not exist.";
  const body = request.method === "HEAD"
    ? null
    : `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, follow"><title>${title} | ReviewDisparity</title></head><body><main><h1>${title}</h1><p>${message}</p></main></body></html>`;
  const response = new NextResponse(body, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": isUnavailable ? "no-store" : "public, max-age=0, s-maxage=60",
      "X-Robots-Tag": "noindex, follow",
      Vary: "Accept",
      ...(isUnavailable ? { "Retry-After": "60" } : {}),
    },
  });
  return response;
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const segments = pathname.split("/").filter(Boolean);
  const wantsMarkdown = acceptsMarkdown(request);

  if (segments.length === 0) {
    if (wantsMarkdown) {
      return NextResponse.rewrite(new URL("/md", request.url));
    }
    return passThroughWithVary();
  }

  if (segments.length !== 2) {
    return NextResponse.next();
  }

  const [entityType, entitySegment] = segments;
  if (!ENTITY_TYPES.has(entityType as EntityRouteType)) {
    return NextResponse.next();
  }

  if (wantsMarkdown) {
    // The /md handler resolves slugs/legacy identifiers itself, so rewrite
    // directly instead of round-tripping agents through canonical redirects.
    return NextResponse.rewrite(new URL(`/md/${entityType}/${entitySegment}`, request.url));
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    return passThroughWithVary();
  }

  const resolution = await resolveEntityRequest({
    apiUrl: API_URL,
    entityType: entityType as EntityRouteType,
    entitySegment,
    signal: AbortSignal.timeout(5_000),
  });

  if (resolution.kind === "not_found") {
    return entityErrorResponse(request, 404);
  }
  if (resolution.kind === "unavailable") {
    return entityErrorResponse(request, 503);
  }
  const canonicalPathname = encodeEntityPathname(resolution.canonicalPath);
  if (canonicalPathname === pathname) {
    return passThroughWithVary(true);
  }

  const redirectUrl = request.nextUrl.clone();
  redirectUrl.pathname = canonicalPathname;
  return NextResponse.redirect(redirectUrl, 308);
}

export const config = {
  matcher: ["/", "/games/:path*", "/journalists/:path*", "/outlets/:path*"],
};
