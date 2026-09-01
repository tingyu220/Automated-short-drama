"""番茄 Network Provider（Phase 5–6）。

从 Playwright 捕获的网络响应中解析推广链接数据，
一次获取整部剧所有推广候选，使用 PromotionMatcher 精确匹配。

核心原则：
- 不猜接口，只从真实捕获的响应中解析
- 匹配优先级：external_drama_id → promotion_id → template_id
  → ConfirmedDramaMatch → 精确剧名 → 模糊剧名
- 同类型多个候选 → AMBIGUOUS，不自动选第一条
- 模糊剧名只能产生候选，不能直接进入生产
- 0 个候选 → NOT_FOUND
"""
from __future__ import annotations

import uuid
from typing import Any

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.promotion_matcher import (
    MatchConfidence,
    MatchResult,
    PromotionMatcher,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.network.network_listener import NetworkCapture
from backend.platforms.tomato.network.response_parser import (
    ParsedPromotion,
    TomatoResponseParser,
)


class NetworkProvider:
    """从网络监听器捕获的响应中解析推广链接候选。

    输入：NetworkListener（或兼容的 listener 接口）
    输出：AcquisitionResult（candidates 全部来自 Network 响应）
    """

    def __init__(
        self,
        listener: Any,
        price_rules: list[TemplatePriceRule],
        *,
        parser: TomatoResponseParser | None = None,
    ) -> None:
        self._listener = listener
        self._price_rules = price_rules
        self._parser = parser or TomatoResponseParser()

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """从已捕获的网络响应中解析推广候选。"""
        captures = getattr(self._listener, "captures", [])
        grouped = getattr(self._listener, "grouped_captures", {})

        # 收集所有推广列表中的候选
        all_parsed: list[ParsedPromotion] = []
        list_captures = grouped.get("PROMOTION_LIST", [])
        for capture in list_captures:
            parsed_items = self._parser.parse_promotion_list(
                capture.response_body
            )
            all_parsed.extend(parsed_items)

        # 也加上详情接口的结果（去重）
        detail_captures = grouped.get("PROMOTION_DETAIL", [])
        seen_ids: set[str] = {p.promotion_id or "" for p in all_parsed if p.promotion_id}
        for capture in detail_captures:
            parsed = self._parser.parse_promotion_detail(capture.response_body)
            if parsed is not None and parsed.promotion_id and parsed.promotion_id not in seen_ids:
                all_parsed.append(parsed)
                seen_ids.add(parsed.promotion_id)

        # 规范化档位并转换为 PromotionAsset 候选
        all_assets: list[PromotionAsset] = []
        for p in all_parsed:
            normalized_type = self._normalize_type(p)
            p.link_type = normalized_type
            asset = _to_asset(task, p, normalized_type)
            all_assets.append(asset)

        # 使用 PromotionMatcher 精确匹配每个档位
        expected_types = ["IAA", "2.9", "9.9"]
        matcher = PromotionMatcher(task, expected_link_type="2.9")
        match_results = matcher.match_all_types(all_assets, expected_types)

        # 从匹配结果构造 candidates / selected / missing
        candidates: list[PromotionAsset] = []
        selected: list[PromotionAsset] = []
        missing: dict[str, str] = {}
        matched_types: list[str] = []
        per_type_diag: dict[str, dict] = {}

        for link_type in expected_types:
            result = match_results[link_type]
            diag: dict[str, Any] = {
                "status": _match_status(result),
                "confidence": result.confidence.name if result.confidence else None,
                "reason": result.reason,
            }

            if result.is_matched and result.selected is not None:
                matched_types.append(link_type)
                selected.append(result.selected)
                candidates.append(result.selected)
                diag["selected_promotion_id"] = result.selected.promotion_id
            elif result.is_ambiguous:
                missing[link_type] = "AMBIGUOUS"
                for c in result.ambiguous_candidates:
                    c.acquisition_status = AssetStatus.AMBIGUOUS
                    candidates.append(c)
                diag["ambiguous_count"] = len(result.ambiguous_candidates)
            else:
                missing[link_type] = "NOT_FOUND"
                diag["reason"] = result.reason or "no candidates"

            per_type_diag[link_type] = diag

        # 确定整体状态：全部匹配才 COMPLETE
        if not all_assets:
            status = AcquisitionStatus.NOT_FOUND
        elif len(matched_types) == len(expected_types):
            status = AcquisitionStatus.COMPLETE
        elif missing:
            status = AcquisitionStatus.PARTIAL
        elif matched_types:
            status = AcquisitionStatus.PARTIAL
        else:
            status = AcquisitionStatus.NOT_FOUND

        # diagnostics
        endpoint_counts = {
            endpoint_type: len(caps)
            for endpoint_type, caps in grouped.items()
        }
        parsed_by_type: dict[str, int] = {}
        for asset in all_assets:
            parsed_by_type[asset.link_type] = parsed_by_type.get(asset.link_type, 0) + 1

        return AcquisitionResult(
            status=status,
            expected_types=list(expected_types),
            candidates=candidates,
            selected=selected,
            missing=missing,
            warnings=[],
            diagnostics={
                "network_provider": {
                    "provider": "NETWORK",
                    "candidate_count": len(all_assets),
                    "endpoint_counts": endpoint_counts,
                    "parsed_by_type": parsed_by_type,
                    "list_response_count": len(list_captures),
                    "detail_response_count": len(detail_captures),
                    "per_type": per_type_diag,
                }
            },
        )

    def _normalize_type(self, parsed: ParsedPromotion) -> str:
        """用价格规则校验并规范化链接类型。"""
        if parsed.link_type == "IAA":
            return "IAA"

        if parsed.price is not None and parsed.price > 0:
            for rule in self._price_rules:
                if rule.min_price <= parsed.price <= rule.max_price:
                    # 匹配到价格规则 → 使用规则对应的档位（2.9 / 9.9 等）
                    return rule.key.replace("iap_", "").replace("_", ".")

        # 没有价格规则匹配，保持原分类
        return parsed.link_type


def _match_status(result: MatchResult) -> str:
    """将 MatchResult 转换为字符串状态标识。"""
    if result.is_matched:
        return "MATCHED"
    if result.is_ambiguous:
        return "AMBIGUOUS"
    return "NOT_FOUND"


def _to_asset(
    task: DramaTask,
    parsed: ParsedPromotion,
    link_type: str,
) -> PromotionAsset:
    """将 ParsedPromotion 转换为 PromotionAsset。"""
    return PromotionAsset(
        id=str(uuid.uuid4()),
        task_id=task.id,
        source_platform=task.platform,
        drama_name=parsed.drama_name,
        link_type=link_type,
        promotion_url=parsed.promotion_url,
        external_drama_id=parsed.external_drama_id,
        promotion_id=parsed.promotion_id,
        episode=parsed.episode,
        template_id=parsed.template_id,
        template_name=parsed.template_name,
        price=parsed.price,
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.DISCOVERED,
        created_or_existing=CreationStatus.EXISTING,
        raw_data=dict(parsed.raw_data),
    )
