"""MiniProgram 配置加载。

从 YAML 文件加载剧场固定配置，使用 Pydantic 模型校验结构。
固定业务配置不得硬编码在 Python 中。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class MiniProgramAppConfig(BaseModel):
    """小程序基础信息。"""

    app_id: str
    original_id: str
    name: str


class PromotionConfig(BaseModel):
    """推广配置。"""

    landing_channel: str
    monetization_type: str
    promotion_channel: str
    unlock_type: str
    callback_template: str
    charge_type: str


class OceanConfig(BaseModel):
    """巨量引擎相关配置。"""

    subject: str
    copyright_owner: str
    category: dict[str, str]


class PriceTierConfig(BaseModel):
    """单个价格档位配置。"""

    recharge_template: str
    product_library: str


class MiniProgramConfig(BaseModel):
    """MiniProgram 完整配置。"""

    mini_program: MiniProgramAppConfig
    promotion: PromotionConfig
    ocean: OceanConfig
    price_tiers: dict[str, PriceTierConfig] = Field(default_factory=dict)

    def get_price_tier(self, tier: str) -> PriceTierConfig | None:
        """获取指定价格档位配置。"""
        return self.price_tiers.get(tier)


def load_miniprogram_config(config_path: str | Path) -> MiniProgramConfig:
    """从 YAML 文件加载 MiniProgram 配置。

    Args:
        config_path: YAML 配置文件路径

    Returns:
        校验后的 MiniProgramConfig

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML 解析失败
        pydantic.ValidationError: 配置结构校验失败
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"MiniProgram 配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return MiniProgramConfig.model_validate(raw)


def list_available_configs(configs_dir: str | Path | None = None) -> list[str]:
    """列出所有可用的 MiniProgram 剧场配置文件名（不含扩展名）。

    Args:
        configs_dir: 配置目录，默认使用包内 configs/

    Returns:
        配置名称列表，如 ["lezhen"]
    """
    if configs_dir is None:
        configs_dir = Path(__file__).resolve().parents[2] / "configs"
    else:
        configs_dir = Path(configs_dir)

    if not configs_dir.is_dir():
        return []

    return sorted(
        p.stem for p in configs_dir.glob("*.yaml") if p.is_file()
    )
