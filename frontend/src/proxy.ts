import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getServerApiUrl } from "@/lib/api-base-url";
import { buildEntityPath, type EntityRouteType } from "@/lib/entity-paths";

const API_URL = getServerApiUrl();
const ENTITY_TYPES = new Set<EntityRouteType>(["games", "journalists", "outlets"]);

function getEntityLabel(entityType: EntityRouteType, payload: Record<string, unknown>): string | null {
  if (entityType === "games") {
    return typeof payload.title === "string" ? payload.title : null;
  }

  return typeof payload.name === "string" ? payload.name : null;
}

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
function passThroughWithVary(): NextResponse {
  const response = NextResponse.next();
  response.headers.append("Vary", "Accept");
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

  if (entitySegment.includes("--")) {
    return passThroughWithVary();
  }

  try {
    const response = await fetch(`${API_URL}/${entityType}/${encodeURIComponent(entitySegment)}`, {
      headers: {
        Accept: "application/json",
      },
      // A slow backend must not stall every legacy-URL request in middleware;
      // on timeout we fall through and let the page resolve the entity itself.
      signal: AbortSignal.timeout(5_000),
    });

    if (!response.ok) {
      return passThroughWithVary();
    }

    const payload = await response.json() as Record<string, unknown>;
    const publicId =
      typeof payload.public_id === "string" && payload.public_id.trim().length > 0
        ? payload.public_id
        : entitySegment;
    const label = getEntityLabel(entityType as EntityRouteType, payload);
    const canonicalPath = buildEntityPath(entityType as EntityRouteType, label, publicId);

    if (canonicalPath === pathname) {
      return passThroughWithVary();
    }

    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = canonicalPath;
    return NextResponse.redirect(redirectUrl, 308);
  } catch {
    return passThroughWithVary();
  }
}

export const config = {
  matcher: ["/", "/games/:path*", "/journalists/:path*", "/outlets/:path*"],
};
