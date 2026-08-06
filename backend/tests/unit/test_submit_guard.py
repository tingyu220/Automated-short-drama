"""提交安全开关与 DryRunWorkflow 接线测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services.dry_run_workflow import DRY_RUN, DryRunWorkflow
from backend.application.services.submit_guard import SubmitDecision, can_submit
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter


class TestCanSubmit:
    """双开关组合决策。"""

    def test_allows_when_both_enabled(self) -> None:
        decision = can_submit(True, True)

        assert decision.allowed is True
        assert decision.reason == ""

    def test_denies_when_final_submit_disabled(self) -> None:
        decision = can_submit(False, True)

        assert decision.allowed is False
        assert decision.reason == "FINAL_SUBMIT_DISABLED"

    def test_denies_when_real_adapters_disabled(self) -> None:
        decision = can_submit(True, False)

        assert decision.allowed is False
        assert decision.reason == "REAL_ADAPTERS_DISABLED"

    def test_denies_when_both_disabled(self) -> None:
        decision = can_submit(False, False)

        assert decision.allowed is False
        assert decision.reason == "FINAL_SUBMIT_DISABLED"


class CountingDeliveryAdapter(MockDeliverySystemAdapter):
    """记录 submit_plan 调用次数的观察 Mock。"""

    def __init__(self) -> None:
        super().__init__()
        self.submit_calls = 0

    def submit_plan(self, plan_spec):
        self.submit_calls += 1
        return super().submit_plan(plan_spec)


def _tomato_task() -> DramaTask:
    return DramaTask(
        id="task-guard-001",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )


class TestDryRunWorkflowGuard:
    """工作流在禁用组合下停在 DRY_RUN 且不调用提交。"""

    def test_final_submit_disabled_skips_submit(self) -> None:
        delivery = CountingDeliveryAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            [],
            allow_final_submit=False,
            use_real_adapters=True,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == DRY_RUN
        submit_step = next(step for step in result.steps if step.step == "SUBMIT")
        assert submit_step.status == "SKIPPED"
        assert "FINAL_SUBMIT_DISABLED" in submit_step.detail
        assert delivery.submit_calls == 0

    def test_real_adapters_disabled_skips_submit(self) -> None:
        delivery = CountingDeliveryAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            [],
            allow_final_submit=True,
            use_real_adapters=False,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == DRY_RUN
        submit_step = next(step for step in result.steps if step.step == "SUBMIT")
        assert submit_step.status == "SKIPPED"
        assert "REAL_ADAPTERS_DISABLED" in submit_step.detail
        assert delivery.submit_calls == 0

    def test_guard_decision_is_used(self) -> None:
        delivery = CountingDeliveryAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            [],
            submit_guard=lambda allow, real: SubmitDecision(
                False, "CUSTOM_REASON"
            ),
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == DRY_RUN
        submit_step = next(step for step in result.steps if step.step == "SUBMIT")
        assert submit_step.status == "SKIPPED"
        assert "CUSTOM_REASON" in submit_step.detail
        assert delivery.submit_calls == 0
