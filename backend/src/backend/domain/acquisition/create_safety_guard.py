"""创建安全守卫（Phase 8）。

强制执行推广链接创建的安全规则：

    Query → 不存在 → Create → 再次 Query → Validate

核心安全规则：
- Create 返回不确定时，禁止再次 Create，必须先重新 Query
- 仍无法确认 → RESULT_UNCERTAIN → MANUAL_REVIEW
- Query 直接返回多个 → AMBIGUOUS，不创建
- 验证失败 → 不进入生产
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from backend.domain.assets.promotion_asset import PromotionAsset

logger = logging.getLogger(__name__)


class CreateStep(Enum):
    """创建流程步骤。"""

    QUERY = "QUERY"
    CREATE = "CREATE"
    REQUERY = "REQUERY"
    VALIDATE = "VALIDATE"


class CreateOutcome(Enum):
    """创建结果。"""

    REUSED = "REUSED"            # 已存在，直接复用
    CREATED = "CREATED"          # 创建成功并通过验证
    UNCERTAIN = "UNCERTAIN"      # 结果不确定
    NOT_FOUND = "NOT_FOUND"      # 查不到
    AMBIGUOUS = "AMBIGUOUS"      # 多个结果


@dataclass
class CreateResult:
    """一次创建安全流程的执行结果。"""

    outcome: CreateOutcome
    asset: PromotionAsset | None = None
    link_type: str = ""
    steps: list[CreateStep] = field(default_factory=list)
    reason: str = ""


class CreateSafetyGuard:
    """强制执行创建安全规则的守卫。

    用法：
        guard = CreateSafetyGuard()
        result = guard.execute(
            link_type="2.9",
            query_fn=lambda lt: query_promotion(lt),
            create_fn=lambda lt: create_promotion(lt),
        )
    """

    def __init__(
        self,
        *,
        validate_fn: Callable[[PromotionAsset], bool] | None = None,
    ) -> None:
        self._validate_fn = validate_fn or _default_validate

    def execute(
        self,
        link_type: str,
        query_fn: Callable[[str], list[PromotionAsset]],
        create_fn: Callable[[str], PromotionAsset | None],
    ) -> CreateResult:
        """执行 Query → Create → Requery → Validate 流程。"""
        steps: list[CreateStep] = []

        # Step 1: Query
        steps.append(CreateStep.QUERY)
        found = query_fn(link_type)

        if len(found) > 1:
            return CreateResult(
                outcome=CreateOutcome.AMBIGUOUS,
                link_type=link_type,
                steps=steps,
                reason=f"query returned {len(found)} results",
            )

        if len(found) == 1:
            asset = found[0]
            steps.append(CreateStep.VALIDATE)
            if self._validate_fn(asset):
                return CreateResult(
                    outcome=CreateOutcome.REUSED,
                    asset=asset,
                    link_type=link_type,
                    steps=steps,
                    reason="found existing and validated",
                )
            return CreateResult(
                outcome=CreateOutcome.UNCERTAIN,
                asset=asset,
                link_type=link_type,
                steps=steps,
                reason="found existing but validation failed",
            )

        # Step 2: Create
        steps.append(CreateStep.CREATE)
        create_fn(link_type)

        # Step 3: Requery（无论 Create 返回什么，都必须重新 Query 确认）
        # 安全规则：不信任 Create 的返回值，以 Requery 结果为准
        steps.append(CreateStep.REQUERY)
        requeried = query_fn(link_type)

        if len(requeried) > 1:
            return CreateResult(
                outcome=CreateOutcome.AMBIGUOUS,
                link_type=link_type,
                steps=steps,
                reason=f"requery returned {len(requeried)} results",
            )

        if len(requeried) == 1:
            asset = requeried[0]
            steps.append(CreateStep.VALIDATE)
            if self._validate_fn(asset):
                return CreateResult(
                    outcome=CreateOutcome.CREATED,
                    asset=asset,
                    link_type=link_type,
                    steps=steps,
                    reason="requery found and validated",
                )
            return CreateResult(
                outcome=CreateOutcome.UNCERTAIN,
                asset=asset,
                link_type=link_type,
                steps=steps,
                reason="requery found but validation failed",
            )

        # Requery 也没找到 → UNCERTAIN
        return CreateResult(
            outcome=CreateOutcome.UNCERTAIN,
            link_type=link_type,
            steps=steps,
            reason="create uncertain and requery found nothing",
        )


def _default_validate(asset: PromotionAsset) -> bool:
    """默认验证规则：URL 非空。"""
    return bool(asset.promotion_url)
