"""
Security middleware for production hardening.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

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

        # Prevent browsers from caching sensitive data
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"

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
