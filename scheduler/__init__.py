"""
Scheduler package for Meow OS.
"""

from .jobs import (
    generate_daily_briefing,
    generate_evening_review,
    generate_weekly_review,
    check_upcoming_deadlines,
    sync_external_services,
    check_inactive_projects,
    discover_opportunities
)
from .sync_queue import SyncQueue

__all__ = [
    "generate_daily_briefing",
    "generate_evening_review",
    "generate_weekly_review",
    "check_upcoming_deadlines",
    "sync_external_services",
    "check_inactive_projects",
    "discover_opportunities",
    "SyncQueue"
]
