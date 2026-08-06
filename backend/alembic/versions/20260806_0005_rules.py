"""创建规则配置十张表.

Revision ID: 20260806_0005
Revises: 20260806_0004
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260806_0005"
down_revision: Union[str, None] = "20260806_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rule_set",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rule_version",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rule_set_id", sa.String(36), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_set.id"]),
    )

    op.create_table(
        "rule_parameter",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rule_version_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_version_id"], ["rule_version.id"]),
    )

    op.create_table(
        "material_rule_range",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("min_material_count", sa.Integer(), nullable=False),
        sa.Column("max_material_count", sa.Integer(), nullable=True),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("base_group_count", sa.Integer(), nullable=False),
        sa.Column("copy_count", sa.Integer(), nullable=False),
        sa.Column("group_size_cap", sa.Integer(), nullable=False),
        sa.Column("target_project_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "template_price_rule",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=False),
        sa.Column("min_price", sa.Float(), nullable=False),
        sa.Column("max_price", sa.Float(), nullable=False),
        sa.Column(
            "same_distance_strategy",
            sa.String(64),
            nullable=False,
            server_default="HIGHER_PRICE_FIRST",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "preset_mapping",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("delivery_type", sa.String(64), nullable=False),
        sa.Column("cid", sa.String(128), nullable=False),
        sa.Column("ad_preset", sa.String(128), nullable=False),
        sa.Column("douyin_account", sa.String(128), nullable=False),
        sa.Column("account_open_preset", sa.String(128), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "douyin_account",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("douyin_account_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "platform_resource_config",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "config_snapshot",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("rule_version_id", sa.String(36), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_version_id"], ["rule_version.id"]),
    )

    op.create_table(
        "config_change_log",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("rule_set_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_version", sa.String(64), nullable=True),
        sa.Column("to_version", sa.String(64), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column(
            "changed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_set_id"], ["rule_set.id"]),
    )


def downgrade() -> None:
    op.drop_table("config_change_log")
    op.drop_table("config_snapshot")
    op.drop_table("platform_resource_config")
    op.drop_table("douyin_account")
    op.drop_table("preset_mapping")
    op.drop_table("template_price_rule")
    op.drop_table("material_rule_range")
    op.drop_table("rule_parameter")
    op.drop_table("rule_version")
    op.drop_table("rule_set")
