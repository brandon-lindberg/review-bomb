"""
Main FastAPI application for Game Journalist Review Disparity Tracker.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.ip_filter import IPFilterMiddleware
from app.middleware import (
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
    HTTPSRedirectMiddleware,
)
from app.routers import journalists, outlets, games, leaderboards, search, stats, news

settings = get_settings()

# Rate limiter - applies globally to all routes
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.app_name}...")

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

    yield

    # Shutdown
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

# Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# Block known abusive IPs (runs after TrustedProxyMiddleware extracts real IP)
app.add_middleware(IPFilterMiddleware)

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
