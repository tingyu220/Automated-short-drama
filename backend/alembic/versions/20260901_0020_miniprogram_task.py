"""新增小程序任务表。

与 Native 业务表完全隔离，只通过 album_id 关联。
"""
from alembic import op
import sqlalchemy as sa


revision = "20260901_0020"
down_revision = "20260831_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "miniprogram_task",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False, unique=True),
        sa.Column("drama_name", sa.String(256), nullable=False),
        sa.Column("operator_name", sa.String(64), nullable=False),
        sa.Column("operator_code", sa.String(32), nullable=False),
        sa.Column("organization_group", sa.String(128), nullable=False),
        sa.Column("organization_path", sa.String(256), nullable=False),
        sa.Column("drama_short_name", sa.String(128), nullable=True),
        sa.Column("album_id", sa.String(128), nullable=True),
        sa.Column("workflow_status", sa.String(32), nullable=False, server_default="NOT_STARTED"),
        sa.Column("extra_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_miniprogram_task_task_id", "miniprogram_task", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_miniprogram_task_task_id", table_name="miniprogram_task")
    op.drop_table("miniprogram_task")
