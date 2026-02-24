"""
Security middleware for production hardening.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


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

        if path == "/api/v1/stats/sitemap-data":
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
