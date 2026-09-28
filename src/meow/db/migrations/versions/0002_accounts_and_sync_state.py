"""accounts and sync state

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28 19:22:17.724937
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "connected_accounts",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("needs_reauth", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_table(
        "sync_state",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("account", sa.String(length=320), nullable=False),
        sa.Column("cursor", sa.String(length=255), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("items_new", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "account"),
    )


def downgrade() -> None:

    op.drop_table("sync_state")
    op.drop_table("connected_accounts")
