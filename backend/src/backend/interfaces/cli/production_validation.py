"""生产验证 CLI：运行 Mock/真实模式阶梯验证，输出 JSON 并写入 Markdown 报告。"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.application.services import submit_guard
from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.application.services.plan_validation_service import PlanValidationService
from backend.application.services.production_report_service import (
    ProductionReportService,
)
from backend.application.services.production_validation_service import (
    ProductionStep,
    ProductionValidationRunner,
)
from backend.application.services.standard_delivery_service import (
    StandardDeliveryService,
)
from backend.bootstrap.adapters import build_adapters
from backend.domain.errors.domain_error import DomainError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.config.settings import Settings

# backend/src/backend/interfaces/cli/ -> parents[4]=backend, .parent=项目根
PROJECT_ROOT = Path(__file__).resolve().parents[4].parent
DEFAULT_REPORT_DIR = "data/production-validation"
LADDER_SIZES = {"single": 1, "three": 3, "five": 5, "ten": 10}
PLAN_TYPES = ("test", "free", "paid_9_9", "paid_2_9", "both")
ROLE_DELIVERY_TYPES = {
    "B1": "IAA",
    "B4": "IAA",
    "B7": "IAA",
    "BX": "IAA",
    "B1-9.9": "B1-9.9",
    "B2-2.9": "B2-2.9",
}

logger = logging.getLogger(__name__)


class _MemoryTaskRepository:
    """内存态 DramaTask 仓储，满足 TaskRepository 协议。"""

    def __init__(self) -> None:
        self._tasks: dict[str, DramaTask] = {}

    def add(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> DramaTask | None:
        return self._tasks.get(task_id)

    def update(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def list_by_state(self, state: str) -> list[DramaTask]:
        return [task for task in self._tasks.values() if task.status == state]

    def list_by_filters(self, **kwargs) -> list[DramaTask]:
        platform = kwargs.get("platform")
        status = kwargs.get("status")
        return [
            task
            for task in self._tasks.values()
            if (platform is None or task.platform == platform)
            and (status is None or task.status == status)
        ]


class _MemoryLedgerRepository:
    """内存态 TaskLedger 仓储，满足 LedgerRepository 协议。"""

    def __init__(self) -> None:
        self._ledgers: dict[str, TaskLedger] = {}

    def add(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def get(self, ledger_id: str) -> TaskLedger | None:
        return self._ledgers.get(ledger_id)

    def update(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str) -> list[TaskLedger]:
        return [
            ledger
            for ledger in self._ledgers.values()
            if ledger.task_id == task_id
        ]

    def list_all(self) -> list[TaskLedger]:
        return list(self._ledgers.values())


def main(argv: list[str] | None = None) -> int:
    """运行生产验证阶梯，输出 JSON；全部通过退出 0，否则退出 1。"""
    parser = argparse.ArgumentParser(description="生产验证阶梯执行器")
    parser.add_argument(
        "--ladder",
        choices=sorted(LADDER_SIZES),
        default="single",
        help="阶梯规模：single/three/five/ten",
    )
    parser.add_argument(
        "--plan-type",
        choices=PLAN_TYPES,
        default="test",
        help="计划类型：test/free/paid_9_9/paid_2_9/both",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        default=False,
        help="真实模式（需 WORKBUDDY_ALLOW_FINAL_SUBMIT=true 同时开启）",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Markdown 报告输出目录",
    )
    args = parser.parse_args(argv)

    if args.real and not Settings().allow_final_submit:
        _emit_error(
            "真实模式需要 WORKBUDDY_ALLOW_FINAL_SUBMIT=true 且 --real 同时开启"
        )
        return 1

    steps = _build_steps(LADDER_SIZES[args.ladder], args.plan_type)
    try:
        if args.real:
            with _open_real_page() as page:
                runner, mode = _build_pipeline(steps, real=True, page=page)
                results = runner.run_ladder(steps)
        else:
            runner, mode = _build_pipeline(steps, real=False)
            results = runner.run_ladder(steps)
    except DomainError as exc:
        _emit_error(f"{exc.message} (code={exc.code})")
        return 1
    except Exception as exc:
        if not args.real:
            raise
        _emit_error(f"真实模式启动失败: {exc}")
        return 1

    report_dir = _resolve_report_dir(args.report_dir)
    report_path = report_dir / f"{args.ladder}-{args.plan_type}-latest.md"
    try:
        report_service = ProductionReportService()
        report = report_service.generate(
            results,
            {
                "mode": mode,
                "ladder": args.ladder,
                "plan_type": args.plan_type,
            },
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            report_service.render_markdown(report),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("生产验证报告写入失败: path=%s", report_path)
        _emit_report_error(exc)
        return 1

    payload = _result_payload(
        mode,
        args.ladder,
        args.plan_type,
        results,
        report_path=str(report_path),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


@contextmanager
def _open_real_page() -> Any:
    """启动 Playwright 浏览器并生成真实 page；退出时由 CLI 负责关闭。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            yield page
        finally:
            browser.close()


def _resolve_report_dir(value: str | None) -> Path:
    """解析报告目录：未传时默认项目根 data/production-validation。"""
    if value is None:
        return (PROJECT_ROOT / DEFAULT_REPORT_DIR).resolve()
    return Path(value).resolve()


def _build_pipeline(
    steps: list[ProductionStep],
    *,
    real: bool,
    page: Any = None,
) -> tuple[ProductionValidationRunner, str]:
    """组装标准投放管线；Mock 模式用模拟适配器跑完整执行链。"""
    settings = Settings()
    if real:
        bundle = build_adapters(settings, use_real=True, page=page)
        mode = "real"
    else:
        bundle = build_adapters(settings, use_real=False)
        mode = "mock"

    task_repo = _MemoryTaskRepository()
    ledger_repo = _MemoryLedgerRepository()
    now = datetime.now(timezone.utc)
    for step in steps:
        task_repo.add(
            DramaTask(
                id=step.task_id or step.step_name,
                drama_name=step.drama_name,
                platform=step.platform,
                available_time=now,
            )
        )

    validation = PlanValidationService()
    delivery = StandardDeliveryService(
        validation,
        bundle.delivery,
        bundle.ocean,
        submit_guard,
        bundle.feishu,
        ledger_repo,
        task_repo,
        allow_final_submit=settings.allow_final_submit if real else True,
        use_real_adapters=True,
    )
    runner = ProductionValidationRunner(
        _build_plan_builder(),
        validation,
        delivery,
        bundle,
    )
    return runner, mode


def _build_plan_builder() -> PlanSpecBuilder:
    return PlanSpecBuilder(
        AccountRoutingRule(),
        PromotionContentMappingRule(),
        MaterialGroupRule(),
        TaskNameRule(),
    )


def _build_steps(size: int, plan_type: str) -> list[ProductionStep]:
    """生成确定性阶梯剧本：1/3/5/10 部剧，同一计划类型。"""
    effective_from = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    return [_build_step(index, plan_type, effective_from) for index in range(1, size + 1)]


def _build_step(index: int, plan_type: str, effective_from: str) -> ProductionStep:
    drama_name = f"生产验证剧{index:02d}"
    accounts = _accounts(plan_type, index)
    return ProductionStep(
        step_name=f"{plan_type}-{index:02d}",
        drama_name=drama_name,
        plan_type=plan_type,
        platform="TOMATO",
        links=_links(plan_type, index),
        accounts=accounts,
        cid_configs=_cid_configs(accounts, effective_from),
        material_count=3,
        material_ranges=[
            MaterialRuleRange(
                min_material_count=0,
                max_material_count=30,
                strategy="BASE_1_COPY_2",
                base_group_count=1,
                copy_count=2,
                group_size_cap=30,
                target_project_count=3,
            )
        ],
        rule_version="production-validation-mock",
        include_test=plan_type == "test",
        task_id=f"pv-task-{index:02d}",
        worker_id="production-validation",
    )


def _links(plan_type: str, index: int) -> dict[str, str]:
    drama_name = f"生产验证剧{index:02d}"
    if plan_type in ("test", "free"):
        return {"IAA": f"mock://iaa/{drama_name}?ep=1"}
    if plan_type == "paid_9_9":
        return {"9.9": f"mock://iap/9.9/{drama_name}"}
    if plan_type == "paid_2_9":
        return {"2.9": f"mock://iap/2.9/{drama_name}"}
    return {
        "9.9": f"mock://iap/9.9/{drama_name}",
        "2.9": f"mock://iap/2.9/{drama_name}",
    }


def _accounts(plan_type: str, index: int) -> list[dict]:
    accounts = [
        {"role": "B1", "cid": f"cid-b1-{index:02d}"},
        {"role": "B4", "cid": f"cid-b4-{index:02d}"},
        {"role": "B7", "cid": f"cid-b7-{index:02d}"},
        {"role": "BX", "cid": f"cid-bx-{index:02d}"},
        {"role": "B1-9.9", "cid": f"cid-99-{index:02d}"},
        {"role": "B2-2.9", "cid": f"cid-29-{index:02d}"},
    ]
    if plan_type == "test":
        accounts.append(
            {
                "role": "B4",
                "cid": f"cid-test-{index:02d}",
                "is_test": True,
            }
        )
    return accounts


def _cid_configs(accounts: list[dict], effective_from: str) -> list[dict]:
    return [
        {
            "cid": str(account["cid"]),
            "subject": "微智造",
            "delivery_type": ROLE_DELIVERY_TYPES[str(account["role"])],
            "enabled": True,
            "effective_from": effective_from,
            "effective_to": None,
            "douyin_account": f"dy-{account['cid']}",
            "ad_preset": f"ad-{account['cid']}",
            "account_open_preset": f"open-{account['cid']}",
        }
        for account in accounts
    ]


def _result_payload(
    mode: str,
    ladder: str,
    plan_type: str,
    results,
    report_path: str,
) -> dict:
    return {
        "mode": mode,
        "ladder": ladder,
        "plan_type": plan_type,
        "report_path": report_path,
        "steps": [
            {
                "step_name": result.step_name,
                "drama_name": result.drama_name,
                "plan_type": result.plan_type,
                "status": result.status,
                "external_task_id": result.external_task_id,
                "ledger_id": result.ledger_id,
                "passed": result.passed,
            }
            for result in results
        ],
        "passed": all(result.passed for result in results),
        "total": len(results),
        "passed_count": sum(1 for result in results if result.passed),
    }


def _emit_error(message: str) -> None:
    print(
        json.dumps({"error": message}, ensure_ascii=False),
        file=sys.stderr,
    )


def _emit_report_error(exc: Exception) -> None:
    print(
        json.dumps({"report_error": str(exc)}, ensure_ascii=False),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
