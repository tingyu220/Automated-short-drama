"""创建任务队列五张表.

Revision ID: 20260806_0003
Revises: 20260806_0002
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260806_0003"
down_revision: Union[str, None] = "20260806_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drama_task",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("sheet_row", sa.Integer(), nullable=True),
        sa.Column("drama_name", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("available_time", sa.DateTime(), nullable=False),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="WAITING_TIME"
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "queue_item",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column(
            "state", sa.String(32), nullable=False, server_default="WAITING_TIME"
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("claimed_by", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["drama_task.id"]),
    )

    op.create_table(
        "workflow_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="PENDING"
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["drama_task.id"]),
    )

    op.create_table(
        "step_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="PENDING"
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_run.id"]),
    )

    op.create_table(
        "task_ledger",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("drama_name", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("album_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_id", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "external_task_id", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("task_name", sa.String(256), nullable=False, server_default=""),
        sa.Column(
            "final_status", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "rule_version", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "config_version", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("task_ledger")
    op.drop_table("step_run")
    op.drop_table("workflow_run")
    op.drop_table("queue_item")
    op.drop_table("drama_task")
