"""保存队列失败码与对账后的重试安全标记。"""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0010"
down_revision = "20260808_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("queue_item", sa.Column("failure_code", sa.String(64), nullable=True))
    op.add_column(
        "queue_item",
        sa.Column("retry_safe", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("queue_item", "retry_safe")
    op.drop_column("queue_item", "failure_code")
