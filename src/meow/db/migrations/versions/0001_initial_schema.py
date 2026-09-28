"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-28 18:43:20.912952
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.String(length=32), nullable=True),
        sa.Column("authority_level", sa.String(length=32), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_log_at"), ["at"], unique=False)

    op.create_table(
        "autonomy_levels",
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("kind"),
    )
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("account", sa.String(length=320), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("busy", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account", "calendar_id", "external_id"),
    )
    with op.batch_alter_table("calendar_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_calendar_events_start_at"), ["start_at"], unique=False)

    op.create_table(
        "source_items",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("account", sa.String(length=320), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=320), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "account", "external_id"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("authority_level", sa.String(length=32), nullable=False),
        sa.Column("source_item_id", sa.String(length=32), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.Column("result_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_index("ix_proposals_kind_status", ["kind", "status"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_proposals_source_item_id"), ["source_item_id"], unique=False
        )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("importance", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("course_code", sa.String(length=32), nullable=True),
        sa.Column("career_relevance", sa.Float(), nullable=False),
        sa.Column("source_item_id", sa.String(length=32), nullable=True),
        sa.Column("proposal_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_due_at"), ["due_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_status"), ["status"], unique=False)

    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("proposal_id", sa.String(length=32), nullable=True),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "start_at"),
    )
    with op.batch_alter_table("focus_sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_focus_sessions_start_at"), ["start_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_focus_sessions_task_id"), ["task_id"], unique=False)


def downgrade() -> None:

    with op.batch_alter_table("focus_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_focus_sessions_task_id"))
        batch_op.drop_index(batch_op.f("ix_focus_sessions_start_at"))

    op.drop_table("focus_sessions")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_status"))
        batch_op.drop_index(batch_op.f("ix_tasks_due_at"))

    op.drop_table("tasks")
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_source_item_id"))
        batch_op.drop_index("ix_proposals_kind_status")

    op.drop_table("proposals")
    op.drop_table("source_items")
    with op.batch_alter_table("calendar_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_calendar_events_start_at"))

    op.drop_table("calendar_events")
    op.drop_table("autonomy_levels")
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_log_at"))

    op.drop_table("audit_log")
