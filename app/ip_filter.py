"""
IP-based request filtering middleware.

Add IPs to BLOCKED_IPS to immediately reject requests from those addresses.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

BLOCKED_IPS: set[str] = {
    "74.220.52.254",
}


class IPFilterMiddleware(BaseHTTPMiddleware):
    """Block requests from known abusive IPs."""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else None
        if client_ip in BLOCKED_IPS:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden"},
            )
        return await call_next(request)
