"""新增账户 CID 同日占用记录。"""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0011"
down_revision = "20260810_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("drama_name", sa.String(256), nullable=False),
        sa.Column("usage_day", sa.Date(), nullable=False),
        sa.Column("cid", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("sheet_kind", sa.String(16), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "usage_day", "cid", name="uq_account_usage_day_cid"
        ),
    )
    op.create_index("ix_account_usage_task_id", "account_usage", ["task_id"])
    op.create_index("ix_account_usage_usage_day", "account_usage", ["usage_day"])


def downgrade() -> None:
    op.drop_index("ix_account_usage_usage_day", table_name="account_usage")
    op.drop_index("ix_account_usage_task_id", table_name="account_usage")
    op.drop_table("account_usage")
