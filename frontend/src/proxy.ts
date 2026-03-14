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

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length !== 2) {
    return NextResponse.next();
  }

  const [entityType, entitySegment] = segments;
  if (!ENTITY_TYPES.has(entityType as EntityRouteType) || entitySegment.includes("--")) {
    return NextResponse.next();
  }

  try {
    const response = await fetch(`${API_URL}/${entityType}/${encodeURIComponent(entitySegment)}`, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      return NextResponse.next();
    }

    const payload = await response.json() as Record<string, unknown>;
    const publicId =
      typeof payload.public_id === "string" && payload.public_id.trim().length > 0
        ? payload.public_id
        : entitySegment;
    const label = getEntityLabel(entityType as EntityRouteType, payload);
    const canonicalPath = buildEntityPath(entityType as EntityRouteType, label, publicId);

    if (canonicalPath === pathname) {
      return NextResponse.next();
    }

    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = canonicalPath;
    return NextResponse.redirect(redirectUrl, 308);
  } catch {
    return NextResponse.next();
  }
}

export const config = {
  matcher: ["/games/:path*", "/journalists/:path*", "/outlets/:path*"],
};
