"""推广链接精确匹配器（Phase 6）。

匹配优先级（从高到低）：
    EXTERNAL_ID → PROMOTION_ID → TEMPLATE_ID → CONFIRMED_MATCH
    → EXACT_NAME → FUZZY_NAME

核心规则：
    0 条 → NOT_FOUND
    1 条 → MATCHED
    >1 条 → AMBIGUOUS（绝不自动选第一条）
    模糊剧名只能产生 Candidate，不能直接选中进入生产
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum

from backend.domain.assets.promotion_asset import PromotionAsset
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class MatchConfidence(IntEnum):
    """匹配置信度，数值越大越可靠。"""

    FUZZY_NAME = 10       # 模糊剧名匹配（不能直接进入生产）
    EXACT_NAME = 20       # 精确剧名匹配
    CONFIRMED_MATCH = 30  # 人工确认的剧目匹配
    TEMPLATE_ID = 40      # 模板 ID 匹配
    PROMOTION_ID = 50     # 推广 ID 匹配
    EXTERNAL_ID = 60      # 外部剧目 ID 匹配


# ---------------------------------------------------------------------------
# 名称规范化
# ---------------------------------------------------------------------------

_COMMON_SUFFIXES = ("全集", "完整版", "独家", "高清", "正版")


def _normalize_name(name: str) -> str:
    """规范化剧名用于比较：去空格、转小写、去常见后缀。"""
    if not name:
        return ""
    result = name.strip().lower().replace(" ", "").replace("　", "")
    for suffix in _COMMON_SUFFIXES:
        if result.endswith(suffix):
            result = result[: -len(suffix)]
    return result


def _names_match_exact(name_a: str, name_b: str) -> bool:
    """精确剧名匹配（去掉首尾空白后完全相同）。"""
    if not name_a or not name_b:
        return False
    return name_a.strip() == name_b.strip()


def _names_match_fuzzy(name_a: str, name_b: str) -> bool:
    """模糊剧名匹配（规范化后相同即算匹配）。"""
    norm_a = _normalize_name(name_a)
    norm_b = _normalize_name(name_b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b


# ---------------------------------------------------------------------------
# 匹配结果
# ---------------------------------------------------------------------------


@dataclass
class MatchResult:
    """单个档位的匹配结果。"""

    is_matched: bool = False
    is_ambiguous: bool = False
    selected: PromotionAsset | None = None
    ambiguous_candidates: list[PromotionAsset] = field(default_factory=list)
    confidence: MatchConfidence | None = None
    reason: str = ""

    @classmethod
    def matched(
        cls,
        candidate: PromotionAsset,
        confidence: MatchConfidence,
        reason: str = "",
    ) -> "MatchResult":
        return cls(
            is_matched=True,
            selected=candidate,
            confidence=confidence,
            reason=reason,
        )

    @classmethod
    def ambiguous(
        cls,
        candidates: list[PromotionAsset],
        confidence: MatchConfidence,
        reason: str = "",
    ) -> "MatchResult":
        return cls(
            is_ambiguous=True,
            ambiguous_candidates=list(candidates),
            confidence=confidence,
            reason=reason,
        )

    @classmethod
    def not_found(cls, reason: str = "no candidates") -> "MatchResult":
        return cls(reason=reason)


# ---------------------------------------------------------------------------
# 匹配器
# ---------------------------------------------------------------------------


class PromotionMatcher:
    """推广链接精确匹配器。

    为指定档位从候选集中找出唯一匹配的推广资产，
    或返回 AMBIGUOUS / NOT_FOUND。
    """

    def __init__(
        self,
        task: DramaTask,
        expected_link_type: str,
    ) -> None:
        self._task = task
        self._expected_link_type = expected_link_type
        self._confirmed_match = task.confirmed_drama_match
        self._task_name = task.drama_name

    def match(self, candidates: list[PromotionAsset]) -> MatchResult:
        """对当前档位执行匹配。"""
        # 先按 link_type 过滤
        same_type = [c for c in candidates if c.link_type == self._expected_link_type]
        if not same_type:
            return MatchResult.not_found(
                f"no {self._expected_link_type} candidates"
            )

        # 按优先级逐级尝试匹配
        # 注意：FUZZY_NAME 层级即使唯一也不算 matched，必须 ambiguous
        matchers = [
            (MatchConfidence.EXTERNAL_ID, self._match_by_external_id, False),
            (MatchConfidence.PROMOTION_ID, self._match_by_promotion_id, False),
            (MatchConfidence.TEMPLATE_ID, self._match_by_template_id, False),
            (MatchConfidence.CONFIRMED_MATCH, self._match_by_confirmed, False),
            (MatchConfidence.EXACT_NAME, self._match_by_exact_name, False),
            (MatchConfidence.FUZZY_NAME, self._match_by_fuzzy_name, True),
        ]

        for confidence, matcher_fn, always_ambiguous in matchers:
            matched = matcher_fn(same_type)
            if matched is None:
                continue  # 这一层没匹配到，继续下一层

            if len(matched) == 1 and not always_ambiguous:
                return MatchResult.matched(
                    matched[0],
                    confidence=confidence,
                    reason=f"matched by {confidence.name}",
                )

            # 歧义 / 始终歧义的层级
            return MatchResult.ambiguous(
                matched,
                confidence=confidence,
                reason=(
                    f"{len(matched)} candidates at {confidence.name} level"
                    if len(matched) > 1
                    else f"fuzzy name match requires manual review"
                ),
            )

        # 所有层级都没匹配到
        return MatchResult.not_found("no matching candidate at any level")

    def match_all_types(
        self,
        candidates: list[PromotionAsset],
        expected_types: list[str],
    ) -> dict[str, MatchResult]:
        """批量匹配多个档位，返回 {link_type: MatchResult}。"""
        results: dict[str, MatchResult] = {}
        for link_type in expected_types:
            # 为每个档位创建独立匹配器
            matcher = PromotionMatcher(self._task, link_type)
            results[link_type] = matcher.match(candidates)
        return results

    # ------------------------------------------------------------------
    # 各层级匹配方法
    # ------------------------------------------------------------------

    def _match_by_external_id(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按 external_drama_id 匹配。

        如果有 confirmed_match，优先用其 locator_key 匹配；
        否则找出所有带 external_drama_id 且剧名匹配的候选。
        剧名不匹配的 external_id 候选不能直接选（可能是别的剧）。
        """
        with_id = [c for c in candidates if c.external_drama_id]
        if not with_id:
            return None

        # 如果有确认信息，用确认的 external_id 过滤
        if self._confirmed_match and self._confirmed_match.locator_key:
            key = self._confirmed_match.locator_key
            filtered = [c for c in with_id if c.external_drama_id == key]
            if filtered:
                return filtered
            return None  # 有确认但没匹配到，不降级到模糊匹配

        # 没有确认信息：只保留剧名匹配的候选
        # 剧名完全不匹配的 external_id 候选，即使唯一也不能选（可能是别的剧）
        name_matched = self._filter_by_best_name_match(with_id)
        if not name_matched:
            return None

        # 如果只有一个 drama_id，返回这些候选（同剧可能有多个推广）
        drama_ids = {c.external_drama_id for c in name_matched}
        if len(drama_ids) == 1:
            return name_matched

        # 多个不同 drama_id 但剧名都匹配 → 仍然返回，让上层判断歧义
        return name_matched

    def _match_by_promotion_id(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按 promotion_id 匹配（通常只有一个）。"""
        with_promo_id = [c for c in candidates if c.promotion_id]
        if not with_promo_id:
            return None
        # promotion_id 是唯一的，有多少返回多少
        # 同档位下多个不同 promotion_id 就是歧义
        return with_promo_id

    def _match_by_template_id(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按 template_id 匹配。"""
        with_tpl_id = [c for c in candidates if c.template_id]
        if not with_tpl_id:
            return None
        return with_tpl_id

    def _match_by_confirmed(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按 ConfirmedDramaMatch 匹配。

        locator_key 可能是 external_drama_id、promotion_id 或其他标识。
        已在 EXTERNAL_ID 层优先处理过，这里处理其他形式的 locator。
        """
        if not self._confirmed_match:
            return None
        key = self._confirmed_match.locator_key
        if not key:
            return None

        # 尝试各种字段匹配 locator_key
        matched: list[PromotionAsset] = []
        for c in candidates:
            if c.promotion_id == key:
                matched.append(c)
            elif c.template_id == key:
                matched.append(c)
            elif c.drama_name.strip() == key:
                matched.append(c)

        return matched if matched else None

    def _match_by_exact_name(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按精确剧名匹配。"""
        matched = [
            c for c in candidates
            if _names_match_exact(c.drama_name, self._task_name)
        ]
        return matched if matched else None

    def _match_by_fuzzy_name(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset] | None:
        """按模糊剧名匹配。

        注意：模糊匹配只能产生候选，不能直接选中。
        调用方看到 FUZZY_NAME 置信度的 AMBIGUOUS 结果时，
        必须进入人工确认流程。
        """
        matched = [
            c for c in candidates
            if _names_match_fuzzy(c.drama_name, self._task_name)
        ]
        return matched if matched else None

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _filter_by_best_name_match(
        self, candidates: list[PromotionAsset]
    ) -> list[PromotionAsset]:
        """从候选中找出剧名最匹配的子集（精确优先，其次模糊）。"""
        exact = [
            c for c in candidates
            if _names_match_exact(c.drama_name, self._task_name)
        ]
        if exact:
            return exact

        fuzzy = [
            c for c in candidates
            if _names_match_fuzzy(c.drama_name, self._task_name)
        ]
        if fuzzy:
            return fuzzy

        return []
