"""
Security middleware for production hardening.
"""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Shared counters for the lifespan heartbeat line (single-process uvicorn).
_request_count = 0
_slow_request_count = 0


def drain_request_counters() -> tuple[int, int]:
    """Return and reset (requests, slow requests) since the last heartbeat."""
    global _request_count, _slow_request_count
    counts = (_request_count, _slow_request_count)
    _request_count = 0
    _slow_request_count = 0
    return counts


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Log slow requests and count traffic for the heartbeat line.

    Render keeps recent stdout logs even across restarts but exposes no
    metrics; after a CPU/memory incident email, these lines are the only way
    to see which endpoints and callers were hot in the minutes before.
    """

    def __init__(self, app, *, slow_ms: int = 500):
        super().__init__(app)
        self.slow_ms = slow_ms

    async def dispatch(self, request: Request, call_next):
        global _request_count, _slow_request_count

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        _request_count += 1
        if self.slow_ms > 0 and elapsed_ms >= self.slow_ms:
            _slow_request_count += 1
            client_ip = request.client.host if request.client else "-"
            user_agent = request.headers.get("user-agent", "-")[:120]
            query = f"?{request.url.query}" if request.url.query else ""
            print(
                f"SLOW {int(elapsed_ms)}ms {response.status_code} "
                f'{request.method} {request.url.path}{query} ip={client_ip} ua="{user_agent}"',
                flush=True,
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    @staticmethod
    def _cache_control_for(request: Request, response: Response) -> str:
        """Return cache policy based on route and response status."""
        if request.method not in ("GET", "HEAD") or response.status_code >= 400:
            return "no-store, no-cache, must-revalidate"

        path = request.url.path
        if not path.startswith("/api/v1/"):
            return "no-store, no-cache, must-revalidate"

        if path.startswith("/api/v1/stats/sitemap-data"):
            return "public, max-age=3600, stale-while-revalidate=86400"
        if path == "/api/v1/news/sources":
            return "public, max-age=300, stale-while-revalidate=3600"
        if path.startswith("/api/v1/search"):
            return "public, max-age=30, stale-while-revalidate=120"

        # Default short cache for public read-only API responses.
        return "public, max-age=60, stale-while-revalidate=300"

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer policy - don't leak full URLs
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Cache policy (API is public/read-only; keep non-API endpoints uncached)
        cache_control = self._cache_control_for(request, response)
        response.headers["Cache-Control"] = cache_control
        if cache_control.startswith("no-store"):
            response.headers["Pragma"] = "no-cache"
        else:
            if "Pragma" in response.headers:
                del response.headers["Pragma"]

        # Content Security Policy for API (only JSON responses)
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # Permissions Policy - disable unnecessary browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response


class TrustedProxyMiddleware(BaseHTTPMiddleware):
    """
    Extract real client IP from Cloudflare/proxy headers.
    Cloudflare sets CF-Connecting-IP with the real client IP.
    This ensures rate limiting works on actual client IPs, not the proxy IP.
    """

    async def dispatch(self, request: Request, call_next):
        # Cloudflare-specific header (most reliable)
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            # Store the real IP so slowapi's get_remote_address can use it
            request.scope["client"] = (cf_ip, request.scope.get("client", ("", 0))[1])
        else:
            # Fall back to X-Forwarded-For (Render also sets this)
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                # Take the first IP (original client)
                real_ip = forwarded_for.split(",")[0].strip()
                request.scope["client"] = (real_ip, request.scope.get("client", ("", 0))[1])

        return await call_next(request)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Redirect HTTP to HTTPS in production.
    Checks X-Forwarded-Proto since Render/Cloudflare terminate TLS at their edge.
    """

    async def dispatch(self, request: Request, call_next):
        proto = request.headers.get("X-Forwarded-Proto", "https")
        if proto == "http" and request.url.path not in ("/health",):
            url = request.url.replace(scheme="https")
            return Response(
                status_code=301,
                headers={"Location": str(url)},
            )
        return await call_next(request)
