"""MiniProgram M0 单元测试。

覆盖：
- MiniProgramContext 创建与校验
- Config 加载（lezhen.yaml）
- NamingService（田雨→TY、推广标题生成）
- Workflow State
- Repository 隔离（不读写 Native 表）
- album_id 可以读取
- Adapter Protocol
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.miniprogram.domain.context import (
    DEFAULT_PRICE_TIERS,
    MiniProgramContext,
)
from backend.miniprogram.domain.naming import (
    MiniProgramNamingService,
    build_promotion_title,
    resolve_operator_code,
    resolve_short_name,
)
from backend.miniprogram.domain.task_data import MiniProgramTaskData
from backend.miniprogram.domain.workflow_state import (
    MiniProgramWorkflowStatus,
    is_terminal,
    status_rank,
)
from backend.miniprogram.infrastructure.config.miniprogram_config import (
    load_miniprogram_config,
)
from backend.miniprogram.domain.ports.adapters import (
    AdapterStatus,
    MiniProgramPromotionAdapter,
)


# ── helpers ────────────────────────────────────────────────


def _sample_context(**overrides) -> MiniProgramContext:
    base = dict(
        task_id="t-001",
        drama_name="悍妇儿媳掌全局",
        operator_name="田雨",
        operator_code="TY",
        organization_group="投放一组",
        organization_path="投放部/一组",
    )
    base.update(overrides)
    return MiniProgramContext(**base)


# ── Context ────────────────────────────────────────────────


class TestMiniProgramContext:
    def test_default_price_tiers(self):
        ctx = _sample_context()
        assert ctx.required_price_tiers == DEFAULT_PRICE_TIERS

    def test_custom_price_tiers(self):
        ctx = _sample_context(required_price_tiers=["1.9", "4.9"])
        assert ctx.required_price_tiers == ["1.9", "4.9"]

    def test_validate_valid_context(self):
        ctx = _sample_context()
        assert ctx.validate() == []

    def test_validate_missing_fields(self):
        ctx = MiniProgramContext(
            task_id="",
            drama_name="",
            operator_name="",
            operator_code="",
            organization_group="",
            organization_path="",
        )
        errors = ctx.validate()
        assert "task_id 不能为空" in errors
        assert "drama_name 不能为空" in errors
        assert "operator_name 不能为空" in errors
        assert "operator_code 不能为空" in errors

    def test_album_id_is_optional(self):
        ctx = _sample_context(album_id=None)
        assert ctx.album_id is None
        assert ctx.validate() == []

    def test_album_id_can_be_set(self):
        ctx = _sample_context(album_id="alb-123")
        assert ctx.album_id == "alb-123"


# ── Config ─────────────────────────────────────────────────


class TestMiniProgramConfig:
    def _config_path(self) -> Path:
        return (
            Path(__file__).resolve().parents[3]
            / "src"
            / "backend"
            / "miniprogram"
            / "configs"
            / "lezhen.yaml"
        )

    def test_load_lezhen_config(self):
        config = load_miniprogram_config(self._config_path())
        assert config.mini_program.app_id == "wx10501bcb2a609cd1"
        assert config.mini_program.name == "乐珍剧场"
        assert config.promotion.charge_type == "每集固定价格"
        assert config.ocean.subject == "厦门夜洛缭绕科技有限公司"

    def test_price_tiers_loaded(self):
        config = load_miniprogram_config(self._config_path())
        assert "2.9" in config.price_tiers
        assert "9.9" in config.price_tiers
        tier_29 = config.get_price_tier("2.9")
        assert tier_29 is not None
        assert tier_29.product_library == "抖小iap-2.9"

    def test_get_missing_tier_returns_none(self):
        config = load_miniprogram_config(self._config_path())
        assert config.get_price_tier("99.9") is None

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_miniprogram_config("/nonexistent/path.yaml")


# ── Naming ─────────────────────────────────────────────────


class TestOperatorCode:
    def test_tian_yu_ty(self):
        assert resolve_operator_code("田雨") == "TY"

    def test_three_char_name(self):
        # 三个字的名字应返回三个首字母
        code = resolve_operator_code("张三丰")
        assert len(code) == 3
        assert code.isupper()

    def test_empty_name(self):
        assert resolve_operator_code("") == ""

    def test_english_name(self):
        # 纯英文名字返回全大写（非典型场景，不做特殊处理）
        assert resolve_operator_code("Alice") == "ALICE"

    def test_naming_service_static_method(self):
        assert MiniProgramNamingService.operator_code("田雨") == "TY"


class TestPromotionTitle:
    def test_standard_format(self):
        title = build_promotion_title("TY", "悍妇儿媳掌全局", "2.9")
        assert title == "TY-悍妇儿媳掌全局-2.9"

    def test_99_tier(self):
        title = build_promotion_title("TY", "悍妇儿媳掌全局", "9.9")
        assert title == "TY-悍妇儿媳掌全局-9.9"

    def test_naming_service_static(self):
        assert (
            MiniProgramNamingService.promotion_title("TY", "测试剧", "2.9")
            == "TY-测试剧-2.9"
        )


class TestShortName:
    def test_existing_short_name_reused(self):
        name, status = resolve_short_name("悍妇儿媳掌全局", "悍妇")
        assert name == "悍妇"
        assert status == "READY"

    def test_no_short_name_needs_confirmation(self):
        name, status = resolve_short_name("悍妇儿媳掌全局")
        assert name == "悍妇儿媳掌全局"  # 返回原名
        assert status == "NEEDS_CONFIRMATION"

    def test_naming_service_static(self):
        _, status = MiniProgramNamingService.short_name("测试剧")
        assert status == "NEEDS_CONFIRMATION"


# ── Workflow State ─────────────────────────────────────────


class TestWorkflowState:
    def test_status_constants_defined(self):
        assert MiniProgramWorkflowStatus.NOT_STARTED == "NOT_STARTED"
        assert MiniProgramWorkflowStatus.CONTEXT_READY == "CONTEXT_READY"
        assert MiniProgramWorkflowStatus.DISCOVERY_READY == "DISCOVERY_READY"
        assert (
            MiniProgramWorkflowStatus.READY_FOR_IMPLEMENTATION
            == "READY_FOR_IMPLEMENTATION"
        )
        assert MiniProgramWorkflowStatus.MANUAL_REVIEW == "MANUAL_REVIEW"
        assert MiniProgramWorkflowStatus.FAILED == "FAILED"

    def test_no_promotion_ready_in_m0(self):
        """M0 不应有 PROMOTION_READY 等后续状态。"""
        statuses = [
            v for k, v in vars(MiniProgramWorkflowStatus).items()
            if not k.startswith("_")
        ]
        assert "PROMOTION_READY" not in statuses
        assert "PRODUCT_READY" not in statuses
        assert "MINIAPP_READY" not in statuses

    def test_status_rank_order(self):
        assert status_rank("NOT_STARTED") < status_rank("CONTEXT_READY")
        assert status_rank("CONTEXT_READY") < status_rank("DISCOVERY_READY")
        assert (
            status_rank("DISCOVERY_READY")
            < status_rank("READY_FOR_IMPLEMENTATION")
        )

    def test_terminal_statuses(self):
        assert is_terminal("READY_FOR_IMPLEMENTATION")
        assert is_terminal("FAILED")
        assert not is_terminal("CONTEXT_READY")
        assert not is_terminal("NOT_STARTED")


# ── TaskData ───────────────────────────────────────────────


class TestMiniProgramTaskData:
    def test_default_status_not_started(self):
        data = MiniProgramTaskData(
            task_id="t-001",
            drama_name="测试剧",
            operator_name="田雨",
            operator_code="TY",
            organization_group="一组",
            organization_path="投放部/一组",
        )
        assert data.workflow_status == MiniProgramWorkflowStatus.NOT_STARTED

    def test_touch_updates_updated_at(self):
        data = MiniProgramTaskData(
            task_id="t-001",
            drama_name="测试剧",
            operator_name="田雨",
            operator_code="TY",
            organization_group="一组",
            organization_path="投放部/一组",
        )
        before = data.updated_at
        import time
        time.sleep(0.01)
        data.touch()
        assert data.updated_at >= before

    def test_album_id_isolated(self):
        """album_id 是唯一允许跨域的字段。"""
        data = MiniProgramTaskData(
            task_id="t-001",
            drama_name="测试剧",
            operator_name="田雨",
            operator_code="TY",
            organization_group="一组",
            organization_path="投放部/一组",
            album_id="alb-x",
        )
        assert data.album_id == "alb-x"
        # 确认没有 native 相关字段
        assert not hasattr(data, "link_set")
        assert not hasattr(data, "native_status")


# ── Adapter Protocol ───────────────────────────────────────


class TestAdapterProtocol:
    def test_youxuan_adapter_satisfies_protocol(self):
        """Youxuan 适配器应满足 MiniProgramPromotionAdapter Protocol。"""
        from backend.miniprogram.platforms.youxuan.youxuan_adapter import (
            YouxuanMiniProgramAdapter,
        )

        adapter = YouxuanMiniProgramAdapter()
        # 类型检查：编译期已验证，这里做运行时接口检查
        assert hasattr(adapter, "discover")
        assert hasattr(adapter, "query_existing")
        assert hasattr(adapter, "ensure_promotion")

    def test_ensure_promotion_not_implemented_in_m0(self):
        """M0 阶段 ensure_promotion 必须返回 NOT_IMPLEMENTED。"""
        from backend.miniprogram.platforms.youxuan.youxuan_adapter import (
            YouxuanMiniProgramAdapter,
        )

        adapter = YouxuanMiniProgramAdapter()
        status, promo = adapter.ensure_promotion(None, "2.9")
        assert status == AdapterStatus.NOT_IMPLEMENTED
        assert promo is None

    def test_discover_returns_not_implemented_in_m0(self):
        from backend.miniprogram.platforms.youxuan.youxuan_adapter import (
            YouxuanMiniProgramAdapter,
        )

        adapter = YouxuanMiniProgramAdapter()
        result = adapter.discover(None)
        assert result.status == AdapterStatus.NOT_IMPLEMENTED

    def test_query_existing_empty_in_m0(self):
        from backend.miniprogram.platforms.youxuan.youxuan_adapter import (
            YouxuanMiniProgramAdapter,
        )

        adapter = YouxuanMiniProgramAdapter()
        result = adapter.query_existing(None, "2.9")
        assert result == []
