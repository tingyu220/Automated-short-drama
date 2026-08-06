"""生产验证执行器单元测试：fakes 注入 builder/validation/delivery。"""
from __future__ import annotations

import json

import pytest

from backend.application.services.plan_validation_service import (
    ValidationIssue,
    ValidationReport,
)
from backend.application.services.production_validation_service import (
    COMPLETED,
    ERROR,
    VALIDATION_FAILED,
    LadderStepResult,
    ProductionStep,
    ProductionValidationRunner,
)
from backend.application.services.standard_delivery_service import (
    DeliveryOutcome,
    MANUAL_REVIEW,
)
from backend.domain.plans.plan_spec import PlanSpec
from backend.interfaces.cli import production_validation as cli


class FakePlanBuilder:
    """记录调用并返回固定 PlanSpec 的 builder fake。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def build(
        self,
        task,
        links,
        accounts,
        product_id,
        material_count,
        material_ranges,
        rule_version,
        include_test=False,
    ) -> PlanSpec:
        self.calls.append(
            {
                "task": task,
                "links": dict(links),
                "accounts": list(accounts),
                "product_id": product_id,
                "material_count": material_count,
                "material_ranges": list(material_ranges),
                "rule_version": rule_version,
                "include_test": include_test,
            }
        )
        return PlanSpec(
            drama_name=task.drama_name,
            platform=task.platform,
            task_name=f"{task.drama_name}-plan",
            link_set=dict(links),
            account_cids=[str(account["cid"]) for account in accounts],
            expected_project_count=3,
        )


class FakeValidation:
    """固定返回预置 ValidationReport 的校验 fake。"""

    def __init__(self, passed: bool = True) -> None:
        self.passed_flag = passed
        self.calls: list[tuple[PlanSpec, list[dict]]] = []

    def validate(
        self,
        spec: PlanSpec,
        cid_configs: list[dict],
    ) -> ValidationReport:
        self.calls.append((spec, cid_configs))
        issues = (
            []
            if self.passed_flag
            else [ValidationIssue(code="FAKE", message="fake fail", field="plan")]
        )
        return ValidationReport(passed=self.passed_flag, issues=issues)


class FakeDeliveryService:
    """按 task_id 返回预置 outcome 的 delivery fake。"""

    def __init__(self, outcomes: dict[str, DeliveryOutcome]) -> None:
        self._outcomes = outcomes
        self.calls: list[dict] = []

    def execute(self, **kwargs) -> DeliveryOutcome:
        self.calls.append(kwargs)
        return self._outcomes[kwargs["task_id"]]


class RaisingDeliveryService(FakeDeliveryService):
    """指定 task_id 抛异常的 delivery fake。"""

    def __init__(self, fail_task_id: str) -> None:
        super().__init__({})
        self._fail_task_id = fail_task_id

    def execute(self, **kwargs) -> DeliveryOutcome:
        self.calls.append(kwargs)
        if kwargs["task_id"] == self._fail_task_id:
            raise RuntimeError("delivery boom")
        return DeliveryOutcome(
            status=COMPLETED,
            external_task_id="ext-ok",
            ledger_id="ledger-ok",
        )


class FakeAdapters:
    """runner 的 adapters 参数占位 fake。"""


def _step(index: int = 1, task_id: str = "") -> ProductionStep:
    return ProductionStep(
        step_name=f"step-{index}",
        drama_name=f"剧{index}",
        plan_type="test",
        links={"IAA": f"mock://iaa/剧{index}"},
        accounts=[{"role": "B1", "cid": f"cid-{index}"}],
        cid_configs=[{"cid": f"cid-{index}"}],
        task_id=task_id or f"task-{index}",
        allow_final_submit=True,
        use_real_adapters=True,
    )


def _runner(
    builder=None,
    validation=None,
    delivery=None,
) -> ProductionValidationRunner:
    return ProductionValidationRunner(
        builder or FakePlanBuilder(),
        validation or FakeValidation(),
        delivery
        or FakeDeliveryService(
            {
                "task-1": DeliveryOutcome(
                    status=COMPLETED,
                    external_task_id="ext-1",
                    ledger_id="ledger-1",
                )
            }
        ),
        FakeAdapters(),
    )


class TestProductionValidationRunner:
    """阶梯执行器的逐级执行与失败隔离。"""

    def test_single_step_pass_records_completed(self) -> None:
        delivery = FakeDeliveryService(
            {
                "task-1": DeliveryOutcome(
                    status=COMPLETED,
                    external_task_id="ext-1",
                    ledger_id="ledger-1",
                )
            }
        )

        results = _runner(delivery=delivery).run_ladder([_step()])

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, LadderStepResult)
        assert result.step_name == "step-1"
        assert result.drama_name == "剧1"
        assert result.plan_type == "test"
        assert result.status == COMPLETED
        assert result.external_task_id == "ext-1"
        assert result.ledger_id == "ledger-1"
        assert result.passed is True
        assert len(delivery.calls) == 1
        call = delivery.calls[0]
        assert call["task_id"] == "task-1"
        assert call["allow_final_submit"] is True
        assert call["use_real_adapters"] is True

    def test_single_step_failure_marks_not_passed(self) -> None:
        delivery = FakeDeliveryService(
            {
                "task-1": DeliveryOutcome(
                    status=MANUAL_REVIEW,
                    external_task_id="ext-1",
                )
            }
        )

        results = _runner(delivery=delivery).run_ladder([_step()])

        assert results[0].status == MANUAL_REVIEW
        assert results[0].external_task_id == "ext-1"
        assert results[0].passed is False

    def test_validation_failure_skips_delivery(self) -> None:
        validation = FakeValidation(passed=False)
        delivery = FakeDeliveryService({})

        results = _runner(
            validation=validation,
            delivery=delivery,
        ).run_ladder([_step()])

        assert results[0].status == VALIDATION_FAILED
        assert results[0].passed is False
        assert delivery.calls == []
        assert len(validation.calls) == 1

    @pytest.mark.parametrize("size", [3, 5, 10])
    def test_ladder_runs_every_step(self, size: int) -> None:
        outcomes = {
            f"task-{index}": DeliveryOutcome(
                status=COMPLETED,
                external_task_id=f"ext-{index}",
                ledger_id=f"ledger-{index}",
            )
            for index in range(1, size + 1)
        }
        delivery = FakeDeliveryService(outcomes)

        results = _runner(delivery=delivery).run_ladder(
            [_step(index) for index in range(1, size + 1)]
        )

        assert len(results) == size
        assert all(result.passed for result in results)
        assert [result.step_name for result in results] == [
            f"step-{index}" for index in range(1, size + 1)
        ]
        assert len(delivery.calls) == size

    def test_single_step_failure_does_not_block_later_steps(self) -> None:
        delivery = FakeDeliveryService(
            {
                "task-1": DeliveryOutcome(
                    status=COMPLETED,
                    external_task_id="ext-1",
                    ledger_id="ledger-1",
                ),
                "task-2": DeliveryOutcome(
                    status=MANUAL_REVIEW,
                    external_task_id="ext-2",
                ),
                "task-3": DeliveryOutcome(
                    status=COMPLETED,
                    external_task_id="ext-3",
                    ledger_id="ledger-3",
                ),
            }
        )

        results = _runner(delivery=delivery).run_ladder(
            [_step(index) for index in range(1, 4)]
        )

        assert [result.passed for result in results] == [True, False, True]
        assert results[1].status == MANUAL_REVIEW
        assert len(delivery.calls) == 3

    def test_exception_in_step_does_not_block_later_steps(self) -> None:
        delivery = RaisingDeliveryService("task-2")

        results = _runner(delivery=delivery).run_ladder(
            [_step(index) for index in range(1, 4)]
        )

        assert [result.status for result in results] == [
            COMPLETED,
            ERROR,
            COMPLETED,
        ]
        assert [result.passed for result in results] == [True, False, True]
        assert len(delivery.calls) == 3


class TestProductionValidationCli:
    """CLI 的 Mock 阶梯与真实模式双开关。"""

    def test_mock_single_outputs_json_and_exits_zero(self, tmp_path, capsys) -> None:
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
        assert payload["mode"] == "mock"
        assert payload["ladder"] == "single"
        assert len(payload["steps"]) == 1
        assert payload["passed"] is True
        assert payload["steps"][0]["passed"] is True
        assert payload["steps"][0]["status"] == "COMPLETED"

    def test_mock_ten_plan_type_both(self, tmp_path, capsys) -> None:
        code = cli.main(
            [
                "--ladder",
                "ten",
                "--plan-type",
                "both",
                "--report-dir",
                str(tmp_path),
            ]
        )

        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["steps"]) == 10
        assert all(step["passed"] for step in payload["steps"])

    def test_real_mode_rejected_without_env(
        self,
        monkeypatch,
        tmp_path,
        capsys,
    ) -> None:
        monkeypatch.delenv("ALLOW_FINAL_SUBMIT", raising=False)

        code = cli.main(
            [
                "--real",
                "--ladder",
                "single",
                "--report-dir",
                str(tmp_path),
            ]
        )

        assert code == 1
        assert "ALLOW_FINAL_SUBMIT" in capsys.readouterr().err

    def test_real_mode_rejected_with_false_env(
        self,
        monkeypatch,
        tmp_path,
        capsys,
    ) -> None:
        monkeypatch.setenv("ALLOW_FINAL_SUBMIT", "false")

        code = cli.main(
            [
                "--real",
                "--ladder",
                "single",
                "--report-dir",
                str(tmp_path),
            ]
        )

        assert code == 1

    def test_real_mode_proceeds_with_both_switches(
        self,
        monkeypatch,
        tmp_path,
        capsys,
    ) -> None:
        monkeypatch.setenv("ALLOW_FINAL_SUBMIT", "true")
        from backend.bootstrap import adapters as adapters_module

        real_build = adapters_module.build_adapters

        def fake_build(settings, use_real, page=None):
            assert use_real is True
            return real_build(settings, use_real=False, page=None)

        monkeypatch.setattr(cli, "build_adapters", fake_build)

        code = cli.main(
            [
                "--real",
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
        assert payload["mode"] == "real"
