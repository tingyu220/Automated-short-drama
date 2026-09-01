"""CreateSafetyGuard 单元测试（Phase 8）。

创建安全规则：
- Query → 不存在 → Create → 再次 Query → Validate
- Create 返回不确定 → 禁止再次 Create，必须重新 Query
- 仍无法确认 → RESULT_UNCERTAIN → MANUAL_REVIEW
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.create_safety_guard import (
    CreateOutcome,
    CreateSafetyGuard,
    CreateStep,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_asset(
    *,
    link_type: str = "2.9",
    promotion_id: str | None = "promo-1",
    promotion_url: str = "https://x.com/p/abc",
) -> PromotionAsset:
    return PromotionAsset(
        id="a1",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type=link_type,
        promotion_url=promotion_url,
        promotion_id=promotion_id,
        acquisition_method=AcquisitionMethod.API,
        acquisition_status=AssetStatus.VALIDATED,
        created_or_existing=CreationStatus.EXISTING,
    )


# ---------------------------------------------------------------------------
# CreateStep 枚举
# ---------------------------------------------------------------------------


def test_create_steps_exist() -> None:
    """创建流程步骤全部存在。"""
    assert CreateStep.QUERY
    assert CreateStep.CREATE
    assert CreateStep.REQUERY
    assert CreateStep.VALIDATE


# ---------------------------------------------------------------------------
# CreateOutcome 枚举
# ---------------------------------------------------------------------------


def test_create_outcomes_exist() -> None:
    """创建结果类型全部存在。"""
    assert CreateOutcome.REUSED          # 已存在 → 复用
    assert CreateOutcome.CREATED         # 创建成功
    assert CreateOutcome.UNCERTAIN       # 结果不确定
    assert CreateOutcome.NOT_FOUND       # 查不到
    assert CreateOutcome.AMBIGUOUS       # 多个结果


# ---------------------------------------------------------------------------
# 正常流程：Query → Reuse
# ---------------------------------------------------------------------------


def test_query_found_reuse() -> None:
    """Query 找到已有链接 → REUSED，不创建。"""
    guard = CreateSafetyGuard()
    existing = _make_asset()

    result = guard.execute(
        link_type="2.9",
        query_fn=lambda lt: [existing],
        create_fn=lambda lt: None,
    )

    assert result.outcome == CreateOutcome.REUSED
    assert result.asset == existing
    assert result.steps == [CreateStep.QUERY, CreateStep.VALIDATE]


# ---------------------------------------------------------------------------
# 正常流程：Query → Create → Requery → Validate
# ---------------------------------------------------------------------------


def test_query_not_found_create_then_requery_validate() -> None:
    """Query 没找到 → Create → Requery 找到 → VALIDATE。"""
    created = _make_asset(promotion_id="new-1")

    call_log: list[str] = []

    def query_fn(lt: str) -> list:
        call_log.append(f"query:{lt}")
        if len(call_log) == 1:
            return []  # 第一次查没有
        return [created]  # 第二次查（requery）找到

    def create_fn(lt: str):
        call_log.append(f"create:{lt}")
        return created  # 创建成功

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    assert result.outcome == CreateOutcome.CREATED
    assert result.asset == created
    assert CreateStep.QUERY in result.steps
    assert CreateStep.CREATE in result.steps
    assert CreateStep.REQUERY in result.steps
    assert CreateStep.VALIDATE in result.steps


# ---------------------------------------------------------------------------
# 安全规则：Create 不确定 → 禁止再次 Create，必须 Requery
# ---------------------------------------------------------------------------


def test_create_uncertain_requeries_not_recreates() -> None:
    """Create 返回不确定 → 必须 Requery，不能再次 Create。"""
    create_count = 0

    def query_fn(lt: str) -> list:
        if create_count == 0:
            return []  # 第一次没有
        return [_make_asset(promotion_id="created-1")]  # requery 找到

    def create_fn(lt: str):
        nonlocal create_count
        create_count += 1
        return None  # 返回不确定

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    # Create 只调用一次
    assert create_count == 1
    # 最终通过 Requery 确认
    assert result.outcome == CreateOutcome.CREATED
    assert CreateStep.REQUERY in result.steps


def test_create_uncertain_requery_still_missing_result_uncertain() -> None:
    """Create 不确定 → Requery 仍然没有 → RESULT_UNCERTAIN。"""
    def query_fn(lt: str) -> list:
        return []  # 始终没有

    def create_fn(lt: str):
        return None  # 不确定

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    assert result.outcome == CreateOutcome.UNCERTAIN
    assert CreateStep.REQUERY in result.steps
    assert CreateStep.VALIDATE not in result.steps


def test_create_uncertain_requery_multiple_ambiguous() -> None:
    """Create 不确定 → Requery 发现多个 → AMBIGUOUS。"""
    call_count = 0

    def query_fn(lt: str) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []
        return [_make_asset(promotion_id="a"), _make_asset(promotion_id="b")]

    def create_fn(lt: str):
        return None  # 不确定

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    assert result.outcome == CreateOutcome.AMBIGUOUS


# ---------------------------------------------------------------------------
# 安全规则：绝不连续 Create 两次
# ---------------------------------------------------------------------------


def test_never_creates_twice_in_a_row() -> None:
    """关键安全规则：绝不在 Create 后再次 Create。"""
    create_count = 0

    def query_fn(lt: str) -> list:
        return []

    def create_fn(lt: str):
        nonlocal create_count
        create_count += 1
        return None  # 不确定

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    assert create_count == 1  # 只 Create 一次


# ---------------------------------------------------------------------------
# Query 直接找到多个 → AMBIGUOUS
# ---------------------------------------------------------------------------


def test_query_multiple_results_ambiguous() -> None:
    """Query 直接返回多个 → AMBIGUOUS，不创建。"""
    assets = [
        _make_asset(promotion_id="a"),
        _make_asset(promotion_id="b"),
    ]

    create_count = 0
    def create_fn(lt: str):
        nonlocal create_count
        create_count += 1
        return None

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=lambda lt: assets,
        create_fn=create_fn,
    )

    assert result.outcome == CreateOutcome.AMBIGUOUS
    assert create_count == 0  # 没有创建


# ---------------------------------------------------------------------------
# 验证失败
# ---------------------------------------------------------------------------


def test_created_asset_validation_fails() -> None:
    """Create 后 Requery 找到，但验证失败 → VALIDATION_FAILED。"""
    created = _make_asset(promotion_id="new-1", promotion_url="")

    call_count = 0
    def query_fn(lt: str) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []
        return [created]

    def create_fn(lt: str):
        return created

    guard = CreateSafetyGuard(
        validate_fn=lambda asset: asset.promotion_url != "",
    )
    result = guard.execute(
        link_type="2.9",
        query_fn=query_fn,
        create_fn=create_fn,
    )

    assert result.outcome == CreateOutcome.UNCERTAIN
    assert CreateStep.VALIDATE in result.steps


# ---------------------------------------------------------------------------
# 诊断信息
# ---------------------------------------------------------------------------


def test_result_contains_step_trace() -> None:
    """结果包含执行步骤追踪。"""
    existing = _make_asset()

    guard = CreateSafetyGuard()
    result = guard.execute(
        link_type="2.9",
        query_fn=lambda lt: [existing],
        create_fn=lambda lt: None,
    )

    assert len(result.steps) > 0
    assert result.link_type == "2.9"
