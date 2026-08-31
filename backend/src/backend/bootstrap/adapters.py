"""Adapter 工厂：按开关组装 Mock 或真实四件套。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backend.domain.errors.domain_error import ConfigurationError
from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    FeishuAdapter,
    OceanEngineAdapter,
    TomatoAdapter,
    YouxuanAdapter,
)
from backend.infrastructure.config.settings import Settings
from backend.platforms.delivery_system.delivery_system_adapter import (
    DeliverySystemAdapter as RealDeliverySystemAdapter,
)
from backend.platforms.feishu.feishu_adapter import FeishuAdapter as RealFeishuAdapter
from backend.platforms.feishu.drama_sheet_adapter import DramaSheetAdapter
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter
from backend.platforms.mock.mock_youxuan import MockYouxuanAdapter
from backend.platforms.ocean_engine.ocean_engine_adapter import (
    OceanEngineAdapter as RealOceanEngineAdapter,
)
from backend.platforms.tomato.tomato_adapter import TomatoAdapter as RealTomatoAdapter

_ENV_FEISHU_URL = "WORKBUDDY_FEISHU_TASK_SHEET_URL"
_ENV_FEISHU_NAME = "WORKBUDDY_FEISHU_TASK_SHEET_NAME"
_SELECTOR_FILES = {
    "tomato": "tomato_selectors.json",
    "delivery": "delivery_system_selectors.json",
    "ocean": "ocean_engine_selectors.json",
}


def build_scheduler_feishu(settings: Settings) -> tuple[FeishuAdapter, str]:
    """构造调度器使用的飞书 Adapter，并返回当前适配模式。"""
    raw = os.getenv("WORKBUDDY_USE_REAL_ADAPTERS", "").strip().lower()
    use_real_sheet = (
        raw in {"true", "1", "yes", "on"}
        or settings.use_real_adapters
        or bool(settings.feishu_private_sheet_url.strip())
    )
    if use_real_sheet:
        url = (
            settings.feishu_private_sheet_url.strip()
            or settings.feishu_task_sheet_url.strip()
            or os.getenv(_ENV_FEISHU_URL, "").strip()
        )
        if not url:
            raise ConfigurationError(
                "真实扫描需要 WORKBUDDY_FEISHU_TASK_SHEET_URL"
            )
        return RealFeishuAdapter(url, settings.feishu_private_sheet_name, dry_run=False), "real"
    return MockFeishuAdapter(), "mock"


@dataclass(frozen=True)
class AdapterBundle:
    """平台 Adapter 的组合。"""

    feishu: FeishuAdapter
    tomato: TomatoAdapter
    delivery: DeliverySystemAdapter
    ocean: OceanEngineAdapter
    youxuan: YouxuanAdapter | None = None


def build_drama_sheet_adapter(settings: Settings) -> DramaSheetAdapter:
    """构造公用表到私有表的导入适配器。"""
    source_url = settings.feishu_source_sheet_url.strip()
    private_url = settings.feishu_private_sheet_url.strip()
    if not source_url:
        raise ConfigurationError("缺少 WORKBUDDY_FEISHU_SOURCE_SHEET_URL")
    if not private_url:
        raise ConfigurationError("缺少 WORKBUDDY_FEISHU_PRIVATE_SHEET_URL")
    return DramaSheetAdapter(
        public_url=source_url,
        public_sheet_id=settings.feishu_source_sheet_id.strip(),
        private_url=private_url,
        private_sheet_id=settings.feishu_private_sheet_id.strip(),
    )


def build_adapters(
    settings: Settings,
    use_real: bool | None = None,
    page: Any = None,
) -> AdapterBundle:
    """按开关组装 Mock 或真实 Adapter 四件套。

    use_real 缺省读 WORKBUDDY_USE_REAL_ADAPTERS 环境变量，默认 false。
    """
    use_real_adapters = settings.use_real_adapters if use_real is None else use_real
    if not use_real_adapters:
        return AdapterBundle(
            feishu=MockFeishuAdapter(),
            tomato=MockTomatoAdapter(),
            delivery=MockDeliverySystemAdapter(),
            ocean=MockOceanEngineAdapter(),
            youxuan=MockYouxuanAdapter(),
        )
    if page is None:
        raise ConfigurationError("真实适配器需要传入 Playwright page")
    feishu = RealFeishuAdapter(
        task_sheet_url=_required_setting(
            settings.feishu_task_sheet_url,
            _ENV_FEISHU_URL,
            "飞书剧目表 URL",
        ),
        task_sheet_name=_required_setting(
            settings.feishu_task_sheet_name,
            _ENV_FEISHU_NAME,
            "飞书剧目表名称",
        ),
        dry_run=False,
    )
    selectors = _load_selectors(settings.config_defaults_dir)
    selectors["tomato"]["login_url"] = _with_base_origin(
        settings.tomato_base_url,
        selectors["tomato"]["login_url"],
    )
    selectors["delivery"]["base_url"] = settings.delivery_base_url
    _sync_delivery_urls(selectors["delivery"], settings.delivery_base_url)
    selectors["ocean"]["base_url"] = settings.ocean_base_url
    return AdapterBundle(
        feishu=feishu,
        tomato=RealTomatoAdapter(
            selectors=selectors["tomato"],
            page=page,
            dry_run=False,
            artifact_dir=settings.data_dir / "artifacts" / "tomato",
        ),
        delivery=RealDeliverySystemAdapter(
            selectors=selectors["delivery"], page=page, dry_run=False
        ),
        ocean=RealOceanEngineAdapter(
            selectors=selectors["ocean"], page=page, dry_run=False
        ),
    )
def _required_setting(value: str, environment_name: str, label: str) -> str:
    """从 Settings 读取真实适配器配置，兼容 .env 与进程环境。"""
    value = value.strip()
    if not value:
        raise ConfigurationError(
            f"真实适配器缺少配置 {environment_name}（{label}）"
        )
    return value


def _with_base_origin(base_url: str, configured_url: str) -> str:
    """使用环境配置的站点来源，同时保留已核验的业务页面路径。"""
    base = urlsplit(base_url)
    configured = urlsplit(configured_url)
    return urlunsplit(
        (base.scheme, base.netloc, configured.path, configured.query, "")
    )


def _sync_delivery_urls(selectors: dict[str, str], base_url: str) -> None:
    """确保投放系统所有页面 URL 使用一致的 base_url 来源。"""
    for key in ("config_page_url", "asset_page_url"):
        if key in selectors:
            selectors[key] = _with_base_origin(base_url, selectors[key])


def _load_selectors(config_dir: Path) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for key, filename in _SELECTOR_FILES.items():
        path = config_dir / filename
        try:
            with path.open(encoding="utf-8") as handle:
                loaded[key] = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"加载选择器配置失败: {path} ({exc})") from exc
    return loaded
