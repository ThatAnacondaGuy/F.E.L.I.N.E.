"""Configuration: where Meow keeps its files, and the user's profile.

The profile (schedule, courses, weights, ...) comes from the packaged ``defaults.toml``
merged with an optional user file. Nothing here is a global singleton: callers build a
``Settings`` and pass it down, which keeps tests isolated.
"""

from __future__ import annotations

import os
import tomllib
from datetime import time
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from meow.types import AuthorityLevel, BlockKind, CoursePriority, ProposalKind

DEFAULTS_PATH = Path(__file__).with_name("defaults.toml")

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UserConfig(_Model):
    name: str
    timezone: str
    github: str = ""
    career_goal: str = ""

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class ScheduleBlock(_Model):
    name: str
    kind: BlockKind
    days: tuple[Weekday, ...]
    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start


class Course(_Model):
    code: str
    name: str
    priority: CoursePriority = CoursePriority.STANDARD
    why: str = ""
    # How much work for this course advances the career goal (applied to synced coursework).
    career_relevance: float = Field(default=0.0, ge=0, le=1)
    # Other names the course goes by, e.g. its Google Classroom title ("TE AI 2026").
    aliases: tuple[str, ...] = ()


class ScoringWeights(_Model):
    urgency: float = Field(ge=0)
    importance: float = Field(ge=0)
    career: float = Field(ge=0)
    academic: float = Field(ge=0)
    quick_win: float = Field(ge=0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Self:
        total = self.urgency + self.importance + self.career + self.academic + self.quick_win
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total:.3f}")
        return self


class ScoringConfig(_Model):
    urgency_half_life_hours: float = Field(gt=0)
    quick_win_minutes: int = Field(gt=0)
    default_estimate_minutes: int = Field(gt=0)
    weights: ScoringWeights


class PlannerConfig(_Model):
    horizon_days: int = Field(ge=1, le=31)
    min_session_minutes: int = Field(ge=5)
    max_session_minutes: int = Field(ge=5)
    buffer_minutes: int = Field(ge=0)
    max_focus_hours_per_day: float = Field(gt=0, le=24)
    granularity_minutes: int = Field(ge=1, le=60)

    @model_validator(mode="after")
    def _session_bounds(self) -> Self:
        if self.min_session_minutes > self.max_session_minutes:
            raise ValueError("min_session_minutes must not exceed max_session_minutes")
        return self


class LLMConfig(_Model):
    base_url: str
    extract_model: str
    timeout_seconds: float = Field(gt=0)
    # Reasoning ("thinking") models: None leaves the model's default, False turns it off.
    think: bool | None = None

    def client_options(self) -> dict[str, Any]:
        return {"timeout": self.timeout_seconds, "think": self.think}


class AutonomyKindConfig(_Model):
    level: AuthorityLevel
    most_autonomous: AuthorityLevel

    @model_validator(mode="after")
    def _within_ceiling(self) -> Self:
        if self.level.rank < self.most_autonomous.rank:
            raise ValueError("level is more autonomous than most_autonomous allows")
        return self


class AutonomyConfig(_Model):
    promotion_min_decisions: int = Field(ge=1)
    promotion_min_acceptance: float = Field(ge=0, le=1)
    auto_approve_min_confidence: float = Field(ge=0, le=1)
    kinds: dict[ProposalKind, AutonomyKindConfig]

    @model_validator(mode="after")
    def _every_kind_configured(self) -> Self:
        missing = set(ProposalKind) - set(self.kinds)
        if missing:
            raise ValueError(f"autonomy.kinds is missing {sorted(missing)}")
        return self


class SyncConfig(_Model):
    interval_minutes: int = Field(ge=0)  # 0 turns background sync off
    gmail_query: str
    gmail_lookback_days: int = Field(ge=1, le=365)
    gmail_max_messages: int = Field(ge=1, le=2000)
    calendar_ids: tuple[str, ...]
    classroom_lookback_days: int = Field(ge=1, le=365)
    extract_batch: int = Field(ge=1, le=500)
    push_focus_blocks: bool
    focus_calendar_name: str
    focus_calendar_account: str | None = None  # default: the first account syncing calendar
    focus_reminder_minutes: int = Field(ge=0, le=120)


class BriefingsConfig(_Model):
    morning: time
    evening: time
    notify: bool
    grace_hours: float = Field(gt=0, le=12)  # don't send a morning briefing at midnight


class ServerConfig(_Model):
    host: str
    port: int = Field(ge=1, le=65535)


class Profile(_Model):
    user: UserConfig
    schedule: tuple[ScheduleBlock, ...]
    courses: tuple[Course, ...]
    scoring: ScoringConfig
    planner: PlannerConfig
    llm: LLMConfig
    autonomy: AutonomyConfig
    sync: SyncConfig
    briefings: BriefingsConfig
    server: ServerConfig

    @model_validator(mode="after")
    def _sanity(self) -> Self:
        codes = [c.code for c in self.courses]
        if len(codes) != len(set(codes)):
            raise ValueError("course codes must be unique")
        if not any(b.kind is BlockKind.FOCUS for b in self.schedule):
            raise ValueError("schedule needs at least one focus block")
        return self

    def course(self, code: str | None) -> Course | None:
        if not code:
            return None
        return next((c for c in self.courses if c.code == code), None)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_profile(user_file: Path | None = None) -> Profile:
    with DEFAULTS_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    if user_file is not None and user_file.exists():
        with user_file.open("rb") as fh:
            data = _deep_merge(data, tomllib.load(fh))
    return Profile.model_validate(data)


class Settings:
    """File locations. ``MEOW_HOME`` relocates everything (tests use a temp dir)."""

    def __init__(self, home: Path | None = None) -> None:
        env_home = os.environ.get("MEOW_HOME")
        self.home = Path(
            home or env_home or platformdirs.user_data_dir("MeowOS", appauthor=False)
        ).expanduser()

    @property
    def db_path(self) -> Path:
        return self.home / "meow.db"

    @property
    def config_file(self) -> Path:
        return self.home / "config.toml"

    @property
    def google_client_file(self) -> Path:
        return self.home / "google" / "client_secret.json"

    @property
    def token_file(self) -> Path:
        return self.home / "api_token"

    @property
    def google_dir(self) -> Path:
        return self.home / "google"

    @cached_property
    def profile(self) -> Profile:
        return load_profile(self.config_file)

    def ensure_home(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
