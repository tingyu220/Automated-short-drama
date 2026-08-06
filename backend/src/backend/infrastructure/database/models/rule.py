"""规则配置 ORM 模型."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class RuleSetRecord(Base):
    """规则集记录，表名 rule_set."""

    __tablename__ = "rule_set"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RuleVersionRecord(Base):
    """规则版本记录，表名 rule_version."""

    __tablename__ = "rule_version"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rule_set.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
    )
    payload_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RuleParameterRecord(Base):
    """规则参数记录，表名 rule_parameter."""

    __tablename__ = "rule_parameter"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rule_version.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class MaterialRuleRangeRecord(Base):
    """素材数量区间规则记录，表名 material_rule_range."""

    __tablename__ = "material_rule_range"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    min_material_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_material_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    base_group_count: Mapped[int] = mapped_column(Integer, nullable=False)
    copy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    group_size_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    target_project_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class TemplatePriceRuleRecord(Base):
    """模板价格规则记录，表名 template_price_rule."""

    __tablename__ = "template_price_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    min_price: Mapped[float] = mapped_column(Float, nullable=False)
    max_price: Mapped[float] = mapped_column(Float, nullable=False)
    same_distance_strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="HIGHER_PRICE_FIRST",
        server_default=text("'HIGHER_PRICE_FIRST'"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class PresetMappingRecord(Base):
    """投放预设映射记录，表名 preset_mapping."""

    __tablename__ = "preset_mapping"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cid: Mapped[str] = mapped_column(String(128), nullable=False)
    ad_preset: Mapped[str] = mapped_column(String(128), nullable=False)
    douyin_account: Mapped[str] = mapped_column(String(128), nullable=False)
    account_open_preset: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class DouyinAccountRecord(Base):
    """抖音账号记录，表名 douyin_account."""

    __tablename__ = "douyin_account"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    douyin_account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class PlatformResourceConfigRecord(Base):
    """平台资源配置记录，表名 platform_resource_config."""

    __tablename__ = "platform_resource_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ConfigSnapshotRecord(Base):
    """配置快照记录，表名 config_snapshot."""

    __tablename__ = "config_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rule_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rule_version.id"), nullable=False
    )
    snapshot_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ConfigChangeLogRecord(Base):
    """配置变更日志记录，表名 config_change_log."""

    __tablename__ = "config_change_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rule_set.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
