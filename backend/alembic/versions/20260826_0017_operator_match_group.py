"""运行环境表增加剧目匹配模式字段。"""
from alembic import op
import sqlalchemy as sa


revision = "20260826_0017"
down_revision = "20260819_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_environment",
        sa.Column(
            "operator_match_group",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("runtime_environment", "operator_match_group")
