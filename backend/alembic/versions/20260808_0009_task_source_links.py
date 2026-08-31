"""保存剧变表内链接源快照。"""
from alembic import op
import sqlalchemy as sa

revision = "20260808_0009"
down_revision = "20260808_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drama_task", sa.Column("source_links_json", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("drama_task", "source_links_json")
