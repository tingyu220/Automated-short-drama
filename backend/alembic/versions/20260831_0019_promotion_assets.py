"""新增推广资产事实表。"""
from alembic import op
import sqlalchemy as sa


revision = "20260831_0019"
down_revision = "20260829_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promotion_asset",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("source_platform", sa.String(32), nullable=False),
        sa.Column("drama_name", sa.String(256), nullable=False),
        sa.Column("external_drama_id", sa.String(128), nullable=True),
        sa.Column("link_type", sa.String(32), nullable=False),
        sa.Column("promotion_url", sa.Text(), nullable=False),
        sa.Column("promotion_id", sa.String(128), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.String(128), nullable=True),
        sa.Column("template_name", sa.String(256), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("acquisition_method", sa.String(32), nullable=False),
        sa.Column("acquisition_status", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("created_or_existing", sa.String(32), nullable=False),
        sa.Column(
            "raw_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_promotion_asset_task_id", "promotion_asset", ["task_id"]
    )
    op.create_index(
        "ix_promotion_asset_identity",
        "promotion_asset",
        ["source_platform", "external_drama_id", "link_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_promotion_asset_identity", table_name="promotion_asset")
    op.drop_index("ix_promotion_asset_task_id", table_name="promotion_asset")
    op.drop_table("promotion_asset")

