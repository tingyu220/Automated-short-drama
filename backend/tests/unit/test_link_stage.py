"""链接准备阶段与运行终点规则。"""
from __future__ import annotations

from backend.domain.workflow.link_stage import LinkStage, RunTarget


def test_link_ready_target_reaches_every_link_stage() -> None:
    """防止默认终点跳过剧目或推广内容搭建。"""
    assert RunTarget.reaches(RunTarget.LINK_READY, LinkStage.LINK_EXTRACTION)
    assert RunTarget.reaches(RunTarget.LINK_READY, LinkStage.DELIVERY_DRAMA)
    assert RunTarget.reaches(RunTarget.LINK_READY, LinkStage.PROMOTION_CONFIG)


def test_link_extraction_target_stops_before_delivery_system() -> None:
    """防止“仅提取链接”继续访问投放系统。"""
    assert RunTarget.reaches(
        RunTarget.LINK_EXTRACTION, LinkStage.LINK_EXTRACTION
    )
    assert not RunTarget.reaches(
        RunTarget.LINK_EXTRACTION, LinkStage.DELIVERY_DRAMA
    )


def test_invalid_run_target_is_rejected() -> None:
    """防止未知终点被静默当作完整执行。"""
    try:
        RunTarget.validate("SUBMIT_PLAN")
    except ValueError as exc:
        assert "SUBMIT_PLAN" in str(exc)
    else:
        raise AssertionError("未知运行终点必须被拒绝")
