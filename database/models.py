"""Pydantic v2 data models for all Meow OS entities.

Every entity in the system has a corresponding Pydantic model used for
validation, serialization, and database interaction.
"""

from __future__ import annotations
import uuid
from datetime import datetime, date
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ── Enums ──────────────────────────────────────────────────────────────

class Status(str, Enum):
    DRAFT = "draft"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"
    OVERDUE = "overdue"
    SNOOZED = "snoozed"

class Priority(str, Enum):
    LOWEST = "lowest"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    HIGHEST = "highest"
    CRITICAL = "critical"

class AuthorityLevel(str, Enum):
    AUTOMATIC = "automatic"   # L1: safe, no approval needed
    CONFIRM = "confirm"       # L2: one-click approval
    EXPLICIT = "explicit"     # L3: full confirmation dialog

class EntityType(str, Enum):
    TASK = "task"
    EVENT = "event"
    PROJECT = "project"
    GOAL = "goal"
    PERSON = "person"
    SKILL = "skill"
    COURSE = "course"
    OPPORTUNITY = "opportunity"
    ORGANIZATION = "organization"
    RESOURCE = "resource"

class RelationType(str, Enum):
    REQUIRES = "requires"
    SUPPORTS = "supports"
    PRODUCES = "produces"
    BLOCKS = "blocks"
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"
    ALIGNS_WITH = "aligns_with"
    STRENGTHENS = "strengthens"
    PREREQUISITE_OF = "prerequisite_of"
    TEACHES = "teaches"
    BELONGS_TO = "belongs_to"

class SourceType(str, Enum):
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_CLASSROOM = "google_classroom"
    GITHUB = "github"
    RSS = "rss"
    WEB_SCRAPE = "web_scrape"
    USER_INPUT = "user_input"
    MESSAGE_FORWARD = "message_forward"
    SYSTEM = "system"
    FILESYSTEM = "filesystem"

class MemoryCategory(str, Enum):
    FACTS = "facts"
    PREFERENCES = "preferences"
    GOALS = "goals"
    HABITS = "habits"
    PROJECTS = "projects"
    TASK_HISTORY = "task_history"
    DECISIONS = "decisions"
    CONTEXT = "context"
    LEARNING_STATE = "learning_state"

class NotificationType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    DEADLINE = "deadline"
    OPPORTUNITY = "opportunity"
    OVERLOAD = "overload"
    REMINDER = "reminder"
    ACHIEVEMENT = "achievement"

class CoursePriority(str, Enum):
    HIGHEST = "highest"  # AI
    HIGH = "high"        # Robotics, Cloud Computing
    STANDARD = "standard"  # Networks, ToC, IPR
    RESEARCH = "research"  # Technical Seminar

class OpportunityStatus(str, Enum):
    DISCOVERED = "discovered"
    TRACKED = "tracked"
    REGISTERED = "registered"
    DISMISSED = "dismissed"
    EXPIRED = "expired"
    COMPLETED = "completed"

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    PLANNING = "planning"


# ── Helper ─────────────────────────────────────────────────────────────

def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Base Model ─────────────────────────────────────────────────────────

class BaseDBModel(BaseModel):
    """Base for all database-backed entities."""
    id: str = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "BaseDBModel":
        return cls(**{k: v for k, v in row.items() if v is not None})

    def to_db_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["updated_at"] = datetime.now().isoformat()
        return d


# ── Core Entities ──────────────────────────────────────────────────────

class TaskModel(BaseDBModel):
    title: str
    description: str = ""
    status: Status = Status.DRAFT
    priority: Priority = Priority.MEDIUM
    priority_score: float = 0.0
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    actual_minutes: int | None = None
    category: str = ""  # academic, career, personal, project, etc.
    tags: list[str] = Field(default_factory=list)
    project_id: str | None = None
    goal_ids: list[str] = Field(default_factory=list)
    source_type: SourceType | None = None
    source_id: str | None = None
    source_confidence: float = 1.0
    provenance_chain: list[str] = Field(default_factory=list)
    authority_level: AuthorityLevel = AuthorityLevel.AUTOMATIC
    snoozed_until: datetime | None = None
    completed_at: datetime | None = None

class EventModel(BaseDBModel):
    title: str
    description: str = ""
    event_type: str = "general"  # meeting, class, deadline, hackathon, etc.
    status: Status = Status.TODO
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str = ""
    is_all_day: bool = False
    is_fixed: bool = False  # fixed = cannot be moved
    source_type: SourceType | None = None
    source_ids: list[str] = Field(default_factory=list)
    dedup_hash: str = ""
    related_task_ids: list[str] = Field(default_factory=list)
    calendar_entry_id: str | None = None
    tags: list[str] = Field(default_factory=list)

class DeadlineModel(BaseDBModel):
    title: str
    description: str = ""
    due_date: datetime
    related_entity_id: str | None = None
    related_entity_type: EntityType | None = None
    source_type: SourceType | None = None
    source_id: str | None = None
    is_hard: bool = True  # hard deadline vs soft/flexible
    reminder_sent: bool = False

class ProjectModel(BaseDBModel):
    name: str
    objective: str = ""
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNING
    repository_url: str | None = None
    deadline: datetime | None = None
    last_activity_at: datetime | None = None
    next_action: str = ""
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    progress_pct: float = 0.0
    demo_readiness: str = "not_ready"  # not_ready, partial, ready
    resume_value_score: float = 0.0
    goal_id: str | None = None
    tags: list[str] = Field(default_factory=list)

class MilestoneModel(BaseDBModel):
    name: str
    description: str = ""
    project_id: str
    status: Status = Status.TODO
    target_date: date | None = None
    completed_at: datetime | None = None

class GoalModel(BaseDBModel):
    name: str
    description: str = ""
    priority: Priority = Priority.HIGH
    status: Status = Status.IN_PROGRESS
    target_date: date | None = None
    parent_id: str | None = None
    progress_pct: float = 0.0
    category: str = ""  # career, academic, personal, skill
    metrics: dict[str, Any] = Field(default_factory=dict)

class SkillModel(BaseDBModel):
    name: str
    category: str = ""  # programming, systems, ml, gpu, etc.
    current_level: str = "beginner"  # beginner, intermediate, advanced, expert
    target_level: str = "advanced"
    hours_invested: float = 0.0
    last_practiced: datetime | None = None
    prerequisites: list[str] = Field(default_factory=list)
    goal_ids: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)


# ── Academic ───────────────────────────────────────────────────────────

class CourseModel(BaseDBModel):
    code: str  # e.g. PCC301COM
    name: str
    priority: CoursePriority = CoursePriority.STANDARD
    career_alignment: str = ""  # how it aligns with NVIDIA career
    semester: str = ""
    instructor: str = ""
    status: Status = Status.IN_PROGRESS
    grade: str | None = None

class AssignmentModel(BaseDBModel):
    course_id: str
    title: str
    description: str = ""
    due_date: datetime | None = None
    estimated_hours: float | None = None
    status: Status = Status.TODO
    submission_url: str | None = None
    source_type: SourceType = SourceType.GOOGLE_CLASSROOM
    source_id: str | None = None
    work_plan_created: bool = False

class ExamModel(BaseDBModel):
    course_id: str
    title: str
    exam_date: datetime | None = None
    duration_minutes: int | None = None
    topics: list[str] = Field(default_factory=list)
    study_plan_created: bool = False


# ── Communication ──────────────────────────────────────────────────────

class EmailModel(BaseDBModel):
    gmail_id: str = ""  # Gmail message ID
    subject: str
    sender: str
    recipients: list[str] = Field(default_factory=list)
    body_preview: str = ""  # first 500 chars
    received_at: datetime | None = None
    labels: list[str] = Field(default_factory=list)
    is_processed: bool = False
    category: str = ""  # academic, career, opportunity, personal, etc.
    importance: Priority = Priority.MEDIUM
    extracted_tasks: list[str] = Field(default_factory=list)  # task IDs
    extracted_events: list[str] = Field(default_factory=list)  # event IDs
    detected_deadline: datetime | None = None
    career_relevance: float = 0.0
    academic_relevance: float = 0.0

class PersonModel(BaseDBModel):
    name: str
    email: str = ""
    role: str = ""  # professor, colleague, recruiter, etc.
    organization: str = ""
    relationship: str = ""  # how Aniket knows them
    last_contact: datetime | None = None
    notes: str = ""

class MeetingModel(BaseDBModel):
    title: str
    event_id: str | None = None
    organizer: str = ""
    participants: list[str] = Field(default_factory=list)
    agenda: str = ""
    notes: str = ""
    action_items: list[str] = Field(default_factory=list)
    meeting_date: datetime | None = None


# ── Calendar ───────────────────────────────────────────────────────────

class CalendarEntryModel(BaseDBModel):
    google_event_id: str = ""  # Google Calendar event ID
    calendar_id: str = "primary"
    event_id: str | None = None  # internal event ID
    sync_token: str = ""
    last_synced_at: datetime | None = None


# ── Opportunity ────────────────────────────────────────────────────────

class OpportunityModel(BaseDBModel):
    title: str
    description: str = ""
    source_url: str = ""
    source_name: str = ""  # devpost, kaggle, nvidia, etc.
    discovered_at: datetime = Field(default_factory=datetime.now)
    deadline_at: datetime | None = None
    status: OpportunityStatus = OpportunityStatus.DISCOVERED
    action_url: str = ""
    tags: list[str] = Field(default_factory=list)
    # Score breakdown
    relevance_score: float = 0.0
    career_score: float = 0.0
    nvidia_score: float = 0.0
    skill_scores: dict[str, float] = Field(default_factory=dict)
    learning_value: float = 0.0
    portfolio_value: float = 0.0
    networking_value: float = 0.0
    time_requirement_hours: float | None = None
    difficulty: str = ""  # easy, medium, hard
    eligibility: str = ""


# ── Learning ───────────────────────────────────────────────────────────

class LearningResourceModel(BaseDBModel):
    title: str
    url: str = ""
    resource_type: str = ""  # course, video, book, paper, tutorial, docs
    skill_ids: list[str] = Field(default_factory=list)
    status: Status = Status.TODO  # todo, in_progress, done
    progress_pct: float = 0.0
    estimated_hours: float | None = None
    notes: str = ""
    rating: int | None = None  # 1-5


# ── Memory ─────────────────────────────────────────────────────────────

class MemoryModel(BaseDBModel):
    category: MemoryCategory
    key: str  # short identifier
    value: str  # the actual memory content
    context: str = ""  # when/why this was stored
    source: str = ""  # where this came from
    confidence: float = 1.0
    is_sensitive: bool = False
    tags: list[str] = Field(default_factory=list)
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None


# ── Notifications ──────────────────────────────────────────────────────

class NotificationModel(BaseDBModel):
    title: str
    message: str
    notification_type: NotificationType = NotificationType.INFO
    priority: Priority = Priority.MEDIUM
    is_read: bool = False
    is_dismissed: bool = False
    action_url: str = ""
    action_label: str = ""
    related_entity_id: str | None = None
    related_entity_type: EntityType | None = None
    expires_at: datetime | None = None


# ── Audit ──────────────────────────────────────────────────────────────

class AuditEntryModel(BaseDBModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: str
    trigger: str  # what caused this action
    action: str  # what was done
    reason: str  # why
    source: str = ""  # where the trigger came from
    result: str = ""  # outcome
    confidence: float = 1.0
    user_approved: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Knowledge Graph ────────────────────────────────────────────────────

class KGEntityModel(BaseDBModel):
    entity_type: EntityType
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding_id: str | None = None

class KGRelationModel(BaseDBModel):
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


# ── User Profile ───────────────────────────────────────────────────────

class ScheduleBlock(BaseModel):
    name: str
    start: str  # HH:MM
    end: str    # HH:MM
    days: list[str] = Field(default_factory=lambda: ["mon","tue","wed","thu","fri"])
    is_fixed: bool = True
    is_dnd: bool = False

class UserProfileModel(BaseModel):
    name: str = "Aniket"
    github_username: str = "ThatAnacondaGuy"
    timezone: str = "Asia/Kolkata"
    career_target: str = "NVIDIA"
    schedule_blocks: list[ScheduleBlock] = Field(default_factory=lambda: [
        ScheduleBlock(name="Sleep", start="04:00", end="08:00", is_dnd=True,
                      days=["mon","tue","wed","thu","fri","sat","sun"]),
        ScheduleBlock(name="Morning Routine", start="08:00", end="09:15",
                      days=["mon","tue","wed","thu","fri","sat","sun"]),
        ScheduleBlock(name="College", start="09:15", end="16:30"),
        ScheduleBlock(name="Deep Focus", start="16:30", end="04:00", is_fixed=False),
    ])
    constraints: dict[str, Any] = Field(default_factory=lambda: {
        "max_daily_meetings": 4,
        "min_buffer_minutes": 15,
        "max_deep_work_block_hours": 2.5,
        "max_context_switches": 6,
    })
