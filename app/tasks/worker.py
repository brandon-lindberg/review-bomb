"""
Dramatiq worker configuration.

This module sets up the Dramatiq broker and middleware for background task processing.

To run the worker:
    dramatiq app.tasks.worker

Or with auto-reload for development:
    dramatiq app.tasks.worker --watch .
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import (
    AgeLimit,
    TimeLimit,
    Callbacks,
    Pipelines,
    Retries,
)

from app.config import get_settings

settings = get_settings()

# Configure Redis broker
broker = RedisBroker(url=settings.redis_url)

# Configure middleware
broker.add_middleware(AgeLimit())           # Drop messages older than max_age
broker.add_middleware(TimeLimit())          # Kill actors that run too long
broker.add_middleware(Callbacks())          # Support for callbacks
broker.add_middleware(Pipelines())          # Support for pipelines
broker.add_middleware(Retries(max_retries=3))  # Retry failed tasks

# Set the broker as default
dramatiq.set_broker(broker)


# Import tasks to register them with the broker
# These imports must come after broker setup
from app.tasks import sync  # noqa: F401, E402
from app.tasks import disparity  # noqa: F401, E402
from app.tasks import performance  # noqa: F401, E402
