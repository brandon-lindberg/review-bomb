"""
Main FastAPI application for Game Journalist Review Disparity Tracker.
"""

import asyncio
import resource
import sys
import time
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.cache import close_redis
from app.ip_filter import IPFilterMiddleware
from app.middleware import (
    RequestObservabilityMiddleware,
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
    HTTPSRedirectMiddleware,
    drain_request_counters,
)
from app.routers import journalists, outlets, games, leaderboards, search, stats, news, internal

settings = get_settings()

# Rate limiter - applies globally to all routes
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)


def _process_cpu_seconds(usage: resource.struct_rusage) -> float:
    return usage.ru_utime + usage.ru_stime


def _max_rss_mb(usage: resource.struct_rusage) -> float:
    # ru_maxrss is bytes on macOS, kilobytes on Linux (Render).
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return usage.ru_maxrss / divisor


async def _heartbeat_log_loop(interval_seconds: int) -> None:
    """Emit a periodic resource/traffic line so incident emails are diagnosable
    from Render's retained stdout logs (there are no platform metrics)."""
    last_usage = resource.getrusage(resource.RUSAGE_SELF)
    last_wall = time.monotonic()
    while True:
        await asyncio.sleep(interval_seconds)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        wall = time.monotonic()
        wall_delta = wall - last_wall
        cpu_delta = _process_cpu_seconds(usage) - _process_cpu_seconds(last_usage)
        # Sleep overshoot beyond the interval = event-loop scheduling lag.
        loop_lag = max(0.0, wall_delta - interval_seconds)
        requests, slow_requests = drain_request_counters()
        cpu_pct = (cpu_delta / wall_delta * 100) if wall_delta > 0 else 0.0
        print(
            f"HEARTBEAT cpu={cpu_delta:.1f}s/{wall_delta:.0f}s ({cpu_pct:.0f}%) "
            f"loop_lag={loop_lag:.2f}s req={requests} slow={slow_requests} "
            f"max_rss={_max_rss_mb(usage):.0f}MB",
            flush=True,
        )
        last_usage = usage
        last_wall = wall


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.app_name}...")
    startup_prewarm_task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None

    # Initialize Sentry if configured
    if settings.sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            environment=settings.environment,
        )

    async def _startup_prewarm():
        try:
            from app.services.cache_prewarm import prewarm_core_caches
            await prewarm_core_caches(top_journalist_details=10)
        except Exception as exc:
            # Never fail app startup due to prewarming; this is best-effort.
            print(f"Startup cache prewarm failed: {exc}")

    # Best-effort background prewarm for first-user experience after restart/deploy.
    startup_prewarm_task = asyncio.create_task(_startup_prewarm())

    if settings.heartbeat_log_seconds > 0:
        heartbeat_task = asyncio.create_task(
            _heartbeat_log_loop(settings.heartbeat_log_seconds)
        )

    yield

    # Shutdown
    for task in (startup_prewarm_task, heartbeat_task):
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    await close_redis()
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Track the disparity between game journalist review scores and user scores",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Middleware stack (order matters: last added = first executed) ---

# CORS middleware - restrict to GET only (API is read-only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type", "Accept"],
)

# Compress larger JSON responses (review lists, chart datasets, etc.)
app.add_middleware(GZipMiddleware, minimum_size=500)

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# Block known abusive IPs (runs after TrustedProxyMiddleware extracts real IP)
app.add_middleware(IPFilterMiddleware)

# Slow-request logging + traffic counters (runs after TrustedProxyMiddleware so
# logged IPs are real client IPs, before the rest so timings cover the stack)
app.add_middleware(
    RequestObservabilityMiddleware, slow_ms=settings.slow_request_log_ms
)

# Trusted proxy support (extract real IP from Cloudflare/Render headers)
app.add_middleware(TrustedProxyMiddleware)

# Production-only middleware
if settings.environment == "production":
    # HTTPS redirect (skip /health for Render health checks)
    app.add_middleware(HTTPSRedirectMiddleware)

    # Restrict to allowed hostnames (prevents host header attacks)
    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
        )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for deployment monitoring."""
    return {"status": "healthy", "app": settings.app_name}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    if settings.environment == "production":
        return {"status": "ok"}
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs" if settings.debug else "Disabled in production",
    }


# Register routers
app.include_router(journalists.router, prefix="/api/v1/journalists", tags=["journalists"])
app.include_router(outlets.router, prefix="/api/v1/outlets", tags=["outlets"])
app.include_router(games.router, prefix="/api/v1/games", tags=["games"])
app.include_router(leaderboards.router, prefix="/api/v1/leaderboards", tags=["leaderboards"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(internal.router, prefix="/api/v1/internal", tags=["internal"])


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    # In production, don't expose internal errors
    if settings.environment == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred"},
        )
    # In development, show the error
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
