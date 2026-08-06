"""Phase 8 集成验收：临时 DB + seed + Mock adapters 的标准投放全场景。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy.orm import Session

from backend.application.services import submit_guard as submit_guard_module
from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.application.services.plan_validation_service import (
    PlanValidationService,
)
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.standard_delivery_service import (
    COMPLETED,
    DRY_RUN,
    MANUAL_REVIEW,
    VALIDATION_FAILED,
    StandardDeliveryService,
)
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"
UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
TASK_ID = "task-phase8-001"


class NeverCompletedDeliveryAdapter(MockDeliverySystemAdapter):
    """Mock 投放系统：提交后一直保持 SUBMITTED，用于轮询超时验收。"""

    def poll_task_status(self, external_task_id: str) -> str:
        return "SUBMITTED"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """临时 SQLite + Alembic 迁移 + 默认规则 seed + 固定 DramaTask。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_url = f"sqlite:///{Path(tmpdir) / 'phase8.db'}"
        run_migrations(db_url)
        engine = create_app_engine(db_url)
        session = Session(engine)
        try:
            seed_rules_from_defaults(session, DEFAULTS_PATH)
            task_repo = SqlAlchemyTaskRepository(session)
            task_repo.add(_task())
            session.commit()
            yield session
        finally:
            session.close()
            engine.dispose()


def _task() -> DramaTask:
    return DramaTask(
        id=TASK_ID,
        drama_name="验收短剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )


def _accounts() -> list[dict]:
    return [
        {"role": "B1", "cid": "cid-b1"},
        {"role": "B4", "cid": "cid-b4"},
        {"role": "B7", "cid": "cid-b7"},
        {"role": "BX", "cid": "cid-bx"},
        {"role": "B1-9.9", "cid": "cid-iap-9-9"},
        {"role": "B2-2.9", "cid": "cid-iap-2-9"},
    ]


def _links() -> dict[str, str]:
    return {
        "IAA": "https://iaa/1",
        "9.9": "https://iap/9.9",
        "2.9": "https://iap/2.9",
    }


def _build_spec(session: Session) -> PlanSpec:
    """用 PlanSpecBuilder + seed 规则 + 账户生成完整 PlanSpec。"""
    ranges = SqlAlchemyMaterialRuleRepository(
        session
    ).list_material_rule_ranges()
    builder = PlanSpecBuilder(
        AccountRoutingRule(),
        PromotionContentMappingRule(),
        MaterialGroupRule(),
        TaskNameRule(),
    )
    return builder.build(
        _task(),
        _links(),
        _accounts(),
        None,
        20,
        ranges,
        "v1",
    )


def _cid_config(cid: str, delivery_type: str) -> dict:
    return {
        "subject": "主体A",
        "delivery_type": delivery_type,
        "cid": cid,
        "ad_preset": "预设A",
        "douyin_account": "B1",
        "account_open_preset": "开户A",
        "effective_from": NOW - timedelta(days=1),
        "enabled": True,
    }


def _cid_configs(spec: PlanSpec) -> list[dict]:
    delivery_types = {
        "cid-b1": "IAA",
        "cid-b4": "IAA",
        "cid-b7": "IAA",
        "cid-bx": "IAA",
        "cid-iap-9-9": "B1-9.9",
        "cid-iap-2-9": "B2-2.9",
    }
    return [
        _cid_config(cid, delivery_types[cid])
        for cid in spec.account_cids
    ]


def _service(
    session: Session,
    feishu: MockFeishuAdapter,
    delivery: MockDeliverySystemAdapter | None = None,
) -> StandardDeliveryService:
    return StandardDeliveryService(
        PlanValidationService(now_provider=lambda: NOW),
        delivery or MockDeliverySystemAdapter(poll_rounds_before_completed=1),
        MockOceanEngineAdapter(),
        submit_guard_module,
        feishu,
        SqlAlchemyLedgerRepository(session),
        SqlAlchemyTaskRepository(session),
    )


class TestPhase8FullScenario:
    """Phase 8 标准投放端到端验收。"""

    def test_builder_and_validation_pass(self, db_session: Session) -> None:
        spec = _build_spec(db_session)

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            spec, _cid_configs(spec)
        )

        assert spec.link_set == _links()
        assert spec.account_cids == [
            "cid-b1",
            "cid-b4",
            "cid-b7",
            "cid-bx",
            "cid-iap-9-9",
            "cid-iap-2-9",
        ]
        assert spec.rule_version == "v1"
        assert report.passed is True
        assert report.issues == []

    def test_success_completes_m_and_ledger(self, db_session: Session) -> None:
        feishu = MockFeishuAdapter()
        service = _service(db_session, feishu)
        spec = _build_spec(db_session)

        outcome = service.execute(
            spec,
            _cid_configs(spec),
            TASK_ID,
            True,
            True,
            "worker-1",
        )

        assert outcome.status == COMPLETED
        assert outcome.external_task_id
        assert outcome.ledger_id
        assert feishu.read_status(TASK_ID) == "OK"
        ledgers = SqlAlchemyLedgerRepository(db_session).list_by_task(TASK_ID)
        assert len(ledgers) == 1
        assert ledgers[0].final_status == COMPLETED

    def test_guard_disabled_is_dry_run(self, db_session: Session) -> None:
        feishu = MockFeishuAdapter()
        service = _service(db_session, feishu)
        spec = _build_spec(db_session)

        outcome = service.execute(
            spec,
            _cid_configs(spec),
            TASK_ID,
            False,
            True,
            "worker-1",
        )

        assert outcome.status == DRY_RUN
        assert outcome.external_task_id is None
        assert outcome.ledger_id is None
        assert feishu.read_status(TASK_ID) == "PENDING"
        assert SqlAlchemyLedgerRepository(db_session).list_by_task(TASK_ID) == []

    def test_missing_cid_configs_is_validation_failed(
        self, db_session: Session
    ) -> None:
        feishu = MockFeishuAdapter()
        service = _service(db_session, feishu)
        spec = _build_spec(db_session)

        outcome = service.execute(
            spec,
            [],
            TASK_ID,
            True,
            True,
            "worker-1",
        )

        assert outcome.status == VALIDATION_FAILED
        assert outcome.external_task_id is None
        assert any(
            issue.code == "CID_CONFIG_MISSING" for issue in outcome.issues
        )
        assert feishu.read_status(TASK_ID) == "PENDING"
        assert SqlAlchemyLedgerRepository(db_session).list_by_task(TASK_ID) == []

    def test_poll_timeout_is_manual_review(self, db_session: Session) -> None:
        feishu = MockFeishuAdapter()
        service = _service(db_session, feishu, NeverCompletedDeliveryAdapter())
        spec = _build_spec(db_session)

        outcome = service.execute(
            spec,
            _cid_configs(spec),
            TASK_ID,
            True,
            True,
            "worker-1",
        )

        assert outcome.status == MANUAL_REVIEW
        assert outcome.external_task_id
        assert feishu.read_status(TASK_ID) == "PENDING"
        assert SqlAlchemyLedgerRepository(db_session).list_by_task(TASK_ID) == []
