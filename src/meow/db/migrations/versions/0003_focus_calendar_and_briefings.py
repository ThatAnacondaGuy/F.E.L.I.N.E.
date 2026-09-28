"""focus calendar and briefings

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28 19:57:40.437086
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "briefings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "day"),
    )
    with op.batch_alter_table("connected_accounts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("focus_calendar_id", sa.String(length=255), nullable=True))


def downgrade() -> None:

    with op.batch_alter_table("connected_accounts", schema=None) as batch_op:
        batch_op.drop_column("focus_calendar_id")

    op.drop_table("briefings")
