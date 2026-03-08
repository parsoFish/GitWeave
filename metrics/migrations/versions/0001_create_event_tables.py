"""Create event tables: push_events, deployment_events, pr_events.

Revision ID: 0001
Revises:
Create Date: 2026-03-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("commits", sa.Text, nullable=False, server_default="[]"),
        sa.Column("extra", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_push_events_repo", "push_events", ["repo"])
    op.create_index("ix_push_events_created_at", "push_events", ["created_at"])

    op.create_table(
        "deployment_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(128), nullable=False),
        sa.Column("deployment_id", sa.BigInteger, nullable=True),
        sa.Column("extra", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deployment_events_repo", "deployment_events", ["repo"])
    op.create_index("ix_deployment_events_created_at", "deployment_events", ["created_at"])

    op.create_table(
        "pr_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=True),
        sa.Column("commit_sha", sa.String(255), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pr_events_repo", "pr_events", ["repo"])
    op.create_index("ix_pr_events_created_at", "pr_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("pr_events")
    op.drop_table("deployment_events")
    op.drop_table("push_events")
