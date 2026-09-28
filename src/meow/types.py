"""Enumerations shared by config, domain logic, storage and the API."""

from __future__ import annotations

from enum import StrEnum


class AuthorityLevel(StrEnum):
    """How much freedom Meow has for a kind of action.

    L1 acts on its own, L2 needs one click, L3 needs an explicit confirmation.
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"

    @property
    def rank(self) -> int:
        """Lower rank means more autonomous."""
        return int(self.value[1])

    @property
    def label(self) -> str:
        return {"L1": "automatic", "L2": "one-click", "L3": "explicit"}[self.value]

    def more_autonomous(self) -> AuthorityLevel | None:
        return AuthorityLevel(f"L{self.rank - 1}") if self.rank > 1 else None

    def less_autonomous(self) -> AuthorityLevel | None:
        return AuthorityLevel(f"L{self.rank + 1}") if self.rank < 3 else None


class Importance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(StrEnum):
    ACADEMIC = "academic"
    CAREER = "career"
    PROJECT = "project"
    PERSONAL = "personal"
    ADMIN = "admin"


class TaskStatus(StrEnum):
    TODO = "todo"
    DONE = "done"
    DROPPED = "dropped"


class ProposalKind(StrEnum):
    CREATE_TASK = "create_task"
    SCHEDULE_FOCUS_BLOCK = "schedule_focus_block"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    AUTO_APPROVED = "auto_approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # replaced by a newer plan before you decided; not a rejection
    EXPIRED = "expired"  # a focus block whose time passed before you decided; not a rejection


class SourceKind(StrEnum):
    MANUAL = "manual"
    GMAIL = "gmail"
    CLASSROOM = "classroom"
    CALENDAR = "calendar"
    GITHUB = "github"


class BlockKind(StrEnum):
    """How the planner treats a block of the weekly schedule."""

    SLEEP = "sleep"  # quiet hours: never scheduled, no notifications
    ROUTINE = "routine"  # busy
    COLLEGE = "college"  # busy
    FOCUS = "focus"  # the only time the planner may place work


class CoursePriority(StrEnum):
    HIGHEST = "highest"
    HIGH = "high"
    STANDARD = "standard"


class BriefingKind(StrEnum):
    MORNING = "morning"
    EVENING = "evening"
