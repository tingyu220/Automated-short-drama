"""保存链接准备阶段与投放系统产物。"""
from alembic import op
import sqlalchemy as sa


revision = "20260816_0012"
down_revision = "20260810_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drama_task",
        sa.Column(
            "current_stage",
            sa.String(64),
            nullable=False,
            server_default="WAITING_AVAILABLE_TIME",
        ),
    )
    op.add_column(
        "drama_task",
        sa.Column(
            "target_stage",
            sa.String(64),
            nullable=False,
            server_default="LINK_READY",
        ),
    )
    op.add_column(
        "drama_task",
        sa.Column("delivery_drama_id", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "drama_task",
        sa.Column(
            "promotion_configs_json",
            sa.Text,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("drama_task", "promotion_configs_json")
    op.drop_column("drama_task", "delivery_drama_id")
    op.drop_column("drama_task", "target_stage")
    op.drop_column("drama_task", "current_stage")
