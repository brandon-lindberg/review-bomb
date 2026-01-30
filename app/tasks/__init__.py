"""Background tasks for the Game Journalist Review Disparity Tracker."""

from app.tasks.worker import broker

__all__ = ["broker"]
