"""增加全局运行环境配置。"""
from alembic import op
import sqlalchemy as sa


revision = "20260817_0015"
down_revision = "20260817_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_environment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("desired_mode", sa.String(16), nullable=False, server_default="MOCK"),
        sa.Column("worker_mode", sa.String(16), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("runtime_environment")
