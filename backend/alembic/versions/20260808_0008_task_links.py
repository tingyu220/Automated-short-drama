"""保存任务链接快照与准备状态。"""
from alembic import op
import sqlalchemy as sa

revision = "20260808_0008"
down_revision = "20260807_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drama_task", sa.Column("link_set_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("drama_task", sa.Column("link_status", sa.String(32), nullable=False, server_default="NOT_STARTED"))


def downgrade() -> None:
    op.drop_column("drama_task", "link_status")
    op.drop_column("drama_task", "link_set_json")
