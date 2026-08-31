"""任务表增加端类型字段，区分端原生与微信小程序产线。"""
from alembic import op
import sqlalchemy as sa


revision = "20260829_0018"
down_revision = "20260826_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drama_task",
        sa.Column(
            "end_type",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'NATIVE'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("drama_task", "end_type")
