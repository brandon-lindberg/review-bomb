import { revalidatePath } from "next/cache";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const DEFAULT_PATHS = ["/", "/news"];

function normalizePaths(input: unknown): string[] {
  if (!Array.isArray(input)) return DEFAULT_PATHS;

  const seen = new Set<string>();
  const paths: string[] = [];

  for (const raw of input) {
    if (typeof raw !== "string") continue;
    let path = raw.trim();
    if (!path) continue;
    if (!path.startsWith("/")) path = `/${path}`;
    if (!seen.has(path)) {
      seen.add(path);
      paths.push(path);
    }
  }

  return paths.length > 0 ? paths : DEFAULT_PATHS;
}

function getBearerToken(request: NextRequest): string | null {
  const auth = request.headers.get("authorization");
  if (!auth) return null;
  const [scheme, token] = auth.split(" ", 2);
  if (scheme?.toLowerCase() !== "bearer" || !token) return null;
  return token;
}

export async function POST(request: NextRequest) {
  const expectedSecret = process.env.REVALIDATE_SECRET;
  if (!expectedSecret) {
    return NextResponse.json(
      { ok: false, error: "REVALIDATE_SECRET not configured" },
      { status: 503 }
    );
  }

  const token = getBearerToken(request);
  if (token !== expectedSecret) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  let body: { paths?: unknown; reason?: unknown } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    // Allow empty/invalid JSON and fall back to defaults.
  }

  const paths = normalizePaths(body.paths);

  for (const path of paths) {
    revalidatePath(path);
  }

  return NextResponse.json({
    ok: true,
    revalidated: paths,
    reason: typeof body.reason === "string" ? body.reason : null,
    timestamp: new Date().toISOString(),
  });
}

