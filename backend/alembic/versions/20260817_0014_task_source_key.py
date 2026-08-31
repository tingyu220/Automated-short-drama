"""为飞书顶部插行引入稳定任务来源键。"""
from alembic import op
import sqlalchemy as sa


revision = "20260817_0014"
down_revision = "20260817_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drama_task", sa.Column("source_key", sa.String(64), nullable=True))
    op.create_index("ix_drama_task_source_key", "drama_task", ["source_key"])


def downgrade() -> None:
    op.drop_index("ix_drama_task_source_key", table_name="drama_task")
    op.drop_column("drama_task", "source_key")
