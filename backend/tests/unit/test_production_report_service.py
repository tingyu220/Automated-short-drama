"""生产验证报告生成器测试。"""
from __future__ import annotations

from backend.application.services.production_report_service import (
    ProductionReportService,
)
from backend.application.services.production_validation_service import (
    LadderStepResult,
)


def _step(
    name: str,
    drama: str,
    status: str,
    passed: bool,
) -> LadderStepResult:
    return LadderStepResult(
        step_name=name,
        drama_name=drama,
        plan_type="both",
        status=status,
        external_task_id="task-1" if passed else None,
        ledger_id="ledger-1" if passed else None,
        passed=passed,
    )


def test_all_passed() -> None:
    service = ProductionReportService()
    report = service.generate(
        [_step("1", "剧A", "COMPLETED", True), _step("2", "剧B", "COMPLETED", True)],
        {"ladder": "3"},
    )
    assert report.overall_passed is True
    assert report.summary == {"total": 2, "passed": 2, "failed": 0}
    text = service.render_markdown(report)
    assert "**总体**: PASS" in text
    assert "PASS" in text


def test_mixed_pass_fail() -> None:
    service = ProductionReportService()
    report = service.generate(
        [
            _step("1", "剧A", "COMPLETED", True),
            _step("2", "剧B", "MANUAL_REVIEW", False),
        ],
        {},
    )
    assert report.overall_passed is False
    assert report.summary == {"total": 2, "passed": 1, "failed": 1}
    text = service.render_markdown(report)
    assert "**总体**: FAIL" in text
    assert "下一步建议" in text


def test_empty_results() -> None:
    service = ProductionReportService()
    report = service.generate([], {})
    assert report.overall_passed is False
    assert report.summary == {"total": 0, "passed": 0, "failed": 0}
