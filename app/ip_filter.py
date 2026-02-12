"""
IP-based request filtering middleware.

Add IPs to BLOCKED_IPS to immediately reject requests from those addresses.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

BLOCKED_IPS: set[str] = set()


class IPFilterMiddleware(BaseHTTPMiddleware):
    """Block requests from known abusive IPs."""

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else None
        if client_ip in BLOCKED_IPS:
            return Response(status_code=444, headers={"Connection": "close"})
        return await call_next(request)
