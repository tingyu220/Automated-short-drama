"""为模板价格与素材区间规则补充 key 列.

Revision ID: 20260806_0006
Revises: 20260806_0005
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260806_0006"
down_revision: Union[str, None] = "20260806_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "template_price_rule",
        sa.Column("key", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "material_rule_range",
        sa.Column("key", sa.String(128), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("template_price_rule", "key")
    op.drop_column("material_rule_range", "key")
