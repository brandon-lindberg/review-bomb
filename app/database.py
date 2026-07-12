"""
Database connection and session management.
"""

import ssl
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

# Configure SSL for asyncpg (required for Render external connections)
connect_args = {}
if settings.environment == "production":
    # Create SSL context for asyncpg
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ssl_context
    connect_args["timeout"] = 30  # Connection timeout in seconds

# Bound runaway queries so slow-DB periods (sync pipeline, mirror writes) fail
# individual requests fast instead of piling up connections. Opt-in per process
# via DB_STATEMENT_TIMEOUT_MS — set it on the web service, never on the pipeline.
if settings.db_statement_timeout_ms > 0:
    connect_args.setdefault("server_settings", {})[
        "statement_timeout"
    ] = str(settings.db_statement_timeout_ms)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
