"""生产验证报告生成：汇总阶梯结果并渲染 Markdown。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.application.services.production_validation_service import (
    LadderStepResult,
)


@dataclass
class ProductionReport:
    """一次生产验证阶梯的最终报告。"""

    generated_at: datetime
    meta: dict[str, Any]
    steps: list[LadderStepResult]
    summary: dict[str, int]
    overall_passed: bool


class ProductionReportService:
    """生成生产验证报告与 Markdown 文本。"""

    def generate(
        self,
        results: list[LadderStepResult],
        meta: dict[str, Any] | None = None,
    ) -> ProductionReport:
        """汇总结果并计算通过/失败统计。"""
        passed = sum(1 for step in results if step.passed)
        failed = len(results) - passed
        return ProductionReport(
            generated_at=datetime.now(timezone.utc),
            meta=meta or {},
            steps=list(results),
            summary={"total": len(results), "passed": passed, "failed": failed},
            overall_passed=len(results) > 0 and failed == 0,
        )

    def render_markdown(self, report: ProductionReport) -> str:
        """把报告渲染为可读 Markdown。"""
        lines = [
            "# 生产验证报告",
            "",
            f"- 生成时间：{report.generated_at.isoformat()}",
        ]
        for key, value in report.meta.items():
            lines.append(f"- {key}：{value}")
        lines += ["", "| 步骤 | 剧名 | 计划类型 | 状态 | 外部任务ID | 台账ID | 通过 |", "|---|---|---|---|---|---|---|"]
        for step in report.steps:
            lines.append(
                "| {step_name} | {drama_name} | {plan_type} | {status} | "
                "{external_task_id} | {ledger_id} | {passed} |".format(
                    step_name=step.step_name,
                    drama_name=step.drama_name,
                    plan_type=step.plan_type,
                    status=step.status,
                    external_task_id=step.external_task_id or "-",
                    ledger_id=step.ledger_id or "-",
                    passed="PASS" if step.passed else "FAIL",
                )
            )
        summary = report.summary
        lines += [
            "",
            f"**汇总**: 总 {summary['total']} / 通过 {summary['passed']} / 失败 {summary['failed']}",
            f"**总体**: {'PASS' if report.overall_passed else 'FAIL'}",
        ]
        if summary["failed"] > 0:
            lines.append("")
            lines.append("> 下一步建议：检查对应外部任务与异常中心。")
        return "\n".join(lines) + "\n"
