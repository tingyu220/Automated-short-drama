"""保存人工确认的番茄候选。"""
from alembic import op
import sqlalchemy as sa


revision = "20260819_0016"
down_revision = "20260817_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drama_task",
        sa.Column(
            "confirmed_drama_match_json",
            sa.Text,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("drama_task", "confirmed_drama_match_json")
