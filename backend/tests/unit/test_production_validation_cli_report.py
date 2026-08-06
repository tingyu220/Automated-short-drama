"""生产验证 CLI 报告落盘测试。"""
from __future__ import annotations

import json

from backend.application.services.production_validation_service import (
    ERROR,
    LadderStepResult,
)
from backend.interfaces.cli import production_validation as cli

TABLE_HEADER = "| 步骤 | 剧名 | 计划类型 | 状态 | 外部任务ID | 台账ID | 通过 |"


class _FakeRunner:
    """固定返回预置阶梯结果的 runner fake。"""

    def __init__(self, results: list[LadderStepResult]) -> None:
        self._results = results

    def run_ladder(self, steps) -> list[LadderStepResult]:
        return self._results


def _failed_result() -> LadderStepResult:
    return LadderStepResult(
        step_name="test-01",
        drama_name="生产验证剧01",
        plan_type="test",
        status=ERROR,
    )


def _fake_pipeline(results: list[LadderStepResult]):
    def build(steps, *, real: bool = False):
        return _FakeRunner(results), "mock"

    return build


def test_mock_single_writes_markdown_report(tmp_path, capsys) -> None:
    code = cli.main(
        [
            "--ladder",
            "single",
            "--plan-type",
            "test",
            "--report-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    report_path = tmp_path / "single-test-latest.md"
    assert payload["report_path"] == str(report_path.resolve())
    assert report_path.is_file()
    text = report_path.read_text(encoding="utf-8")
    assert TABLE_HEADER in text
    assert "**汇总**: 总 1 / 通过 1 / 失败 0" in text
    assert "**总体**: PASS" in text


def test_default_report_dir_points_to_project_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "PROJECT_ROOT", tmp_path)

    assert cli._resolve_report_dir(None) == (
        tmp_path / "data" / "production-validation"
    ).resolve()


def test_failed_ladder_writes_fail_report_and_next_step(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "_build_pipeline",
        _fake_pipeline([_failed_result()]),
    )

    code = cli.main(
        [
            "--ladder",
            "single",
            "--plan-type",
            "test",
            "--report-dir",
            str(tmp_path),
        ]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    text = (tmp_path / "single-test-latest.md").read_text(encoding="utf-8")
    assert "**汇总**: 总 1 / 通过 0 / 失败 1" in text
    assert "**总体**: FAIL" in text
    assert "下一步建议" in text


def test_report_write_failure_emits_report_error(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "_build_pipeline",
        _fake_pipeline([LadderStepResult(
            step_name="test-01",
            drama_name="生产验证剧01",
            plan_type="test",
            status="COMPLETED",
            passed=True,
        )]),
    )

    def raise_render_error(self, report):
        raise RuntimeError("disk boom")

    monkeypatch.setattr(
        cli.ProductionReportService,
        "render_markdown",
        raise_render_error,
    )

    code = cli.main(
        [
            "--ladder",
            "single",
            "--plan-type",
            "test",
            "--report-dir",
            str(tmp_path),
        ]
    )

    assert code == 1
    assert "report_error" in capsys.readouterr().err
