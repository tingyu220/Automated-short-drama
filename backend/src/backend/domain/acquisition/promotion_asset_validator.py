"""推广资产确定性验证规则。"""
from __future__ import annotations

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import (
    AssetStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.rules.drama_match import normalize_drama_name
from backend.domain.tasks.drama_task import DramaTask


class PromotionAssetValidator:
    """只选择唯一、身份一致且 URL 合法的推广资产。"""

    def validate(
        self,
        task: DramaTask,
        result: AcquisitionResult,
    ) -> AcquisitionResult:
        selected: list[PromotionAsset] = []
        missing = dict(result.missing)
        ambiguous = False

        for link_type in result.expected_types:
            typed = [
                item for item in result.candidates if item.link_type == link_type
            ]
            if len(typed) > 1:
                ambiguous = True
                missing[link_type] = "MULTIPLE_CANDIDATES"
                for item in typed:
                    item.acquisition_status = AssetStatus.AMBIGUOUS
                continue
            if not typed:
                missing.setdefault(link_type, "NOT_FOUND")
                continue

            candidate = typed[0]
            reason = self._invalid_reason(task, candidate)
            if reason is not None:
                candidate.acquisition_status = AssetStatus.FAILED
                candidate.verification_status = VerificationStatus.INVALID
                missing[link_type] = reason
                continue

            candidate.acquisition_status = AssetStatus.VALIDATED
            candidate.verification_status = VerificationStatus.VALIDATED
            selected.append(candidate)
            missing.pop(link_type, None)

        if ambiguous:
            status = AcquisitionStatus.AMBIGUOUS
        elif len(selected) == len(result.expected_types):
            status = AcquisitionStatus.COMPLETE
        elif selected:
            status = AcquisitionStatus.PARTIAL
        elif result.candidates:
            status = AcquisitionStatus.FAILED
        else:
            status = AcquisitionStatus.NOT_FOUND

        return AcquisitionResult(
            status=status,
            expected_types=list(result.expected_types),
            candidates=list(result.candidates),
            selected=selected,
            missing=missing,
            warnings=list(result.warnings),
            diagnostics=dict(result.diagnostics),
        )

    @staticmethod
    def _invalid_reason(
        task: DramaTask,
        candidate: PromotionAsset,
    ) -> str | None:
        if candidate.task_id != task.id:
            return "TASK_IDENTITY_MISMATCH"
        if candidate.source_platform != task.platform:
            return "PLATFORM_IDENTITY_MISMATCH"
        if normalize_drama_name(candidate.drama_name) != normalize_drama_name(
            task.drama_name
        ):
            return "DRAMA_IDENTITY_MISMATCH"
        if not _valid_url(candidate.source_platform, candidate.promotion_url):
            return "INVALID_URL"
        return None


def _valid_url(platform: str, url: str) -> bool:
    if url.startswith("mock://"):
        return True
    if platform == "TOMATO":
        return _valid_tomato_url(url)
    return bool(url.strip())


def _valid_tomato_url(url: str) -> bool:
    """番茄平台链接格式校验。

    接受以下格式：
    - aweme://playlet?playlet_id=...
    - aweme://playlist?playlist_id=...
    - 其他 aweme:// 协议且带查询参数的 URL
    """
    if not url.startswith("aweme://"):
        return False
    if "?" not in url:
        return False
    query = url.split("?", 1)[1]
    return "=" in query
