"""保存剧目导入预览与确认结果。"""
from alembic import op
import sqlalchemy as sa


revision = "20260817_0013"
down_revision = "20260816_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drama_import_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PREVIEWED"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("drama_import_run")
