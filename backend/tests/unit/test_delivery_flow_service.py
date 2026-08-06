"""投放/巨量模拟服务单元测试：fake adapters."""
from __future__ import annotations

import pytest

from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.domain.errors.domain_error import ExternalAdapterError, ValidationError
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import DramaAsset


class FakeDeliverySystemAdapter:
    """记录调用并返回确定性结果的投放系统 fake。"""

    def __init__(self, poll_statuses: list[str] | None = None) -> None:
        self._assets: dict[tuple[str, str], DramaAsset] = {}
        self.config_calls: list[tuple[str, str, str, str, str]] = []
        self.submitted_plans: list[PlanSpec] = []
        self.poll_calls: list[str] = []
        self._poll_statuses = list(poll_statuses or [])

    def find_or_create_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        key = (drama_name, link)
        existing = self._assets.get(key)
        if existing is not None:
            return existing
        asset = DramaAsset(
            delivery_drama_id=f"dd-{len(self._assets) + 1}",
            drama_name=drama_name,
            link=link,
        )
        self._assets[key] = asset
        return asset

    def ensure_promotion_config(
        self,
        asset_id: str,
        link_type: str,
        link: str,
        drama_name: str,
        platform: str,
    ) -> str:
        self.config_calls.append((asset_id, link_type, link, drama_name, platform))
        return f"cfg-{asset_id}-{link_type}"

    def submit_plan(self, plan_spec: PlanSpec) -> str:
        self.submitted_plans.append(plan_spec)
        return "task-ext-1"

    def poll_task_status(self, external_task_id: str) -> str:
        self.poll_calls.append(external_task_id)
        return self._poll_statuses.pop(0) if self._poll_statuses else "COMPLETED"


class FakeOceanEngineAdapter:
    """记录创建调用并支持校验失败的巨量 fake。"""

    def __init__(self, verified: bool = True) -> None:
        self.verified = verified
        self.create_calls: list[tuple[str, dict]] = []
        self.verify_calls: list[str] = []

    def create_product(self, album_id: str, fields: dict) -> str:
        self.create_calls.append((album_id, fields))
        return f"prod-{album_id}"

    def verify_product(self, product_id: str) -> bool:
        self.verify_calls.append(product_id)
        return self.verified


def _plan_spec(**overrides: object) -> PlanSpec:
    payload: dict[str, object] = {
        "drama_name": "剧A",
        "platform": "TOMATO",
        "task_name": "番茄#端免剧A测试任务",
        "link_set": {"IAA": "mock://iaa/剧A"},
        "account_cids": ["cid-1"],
    }
    payload.update(overrides)
    return PlanSpec(**payload)


class TestEnsureDramaAsset:
    """ensure_drama_asset 委托与幂等测试。"""

    def test_delegates_and_is_idempotent(self) -> None:
        delivery = FakeDeliverySystemAdapter()
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        first = service.ensure_drama_asset("剧A", "mock://iaa/剧A")
        second = service.ensure_drama_asset("剧A", "mock://iaa/剧A")

        assert isinstance(first, DramaAsset)
        assert first == second
        assert first.delivery_drama_id == "dd-1"


class TestEnsurePromotionConfig:
    """ensure_promotion_config 委托测试。"""

    def test_passes_asset_id_and_returns_config_id(self) -> None:
        delivery = FakeDeliverySystemAdapter()
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())
        asset = service.ensure_drama_asset("剧A", "mock://iaa/剧A")

        config_id = service.ensure_promotion_config(
            asset, "IAA", "mock://iaa/剧A", "TOMATO"
        )

        assert config_id == "cfg-dd-1-IAA"
        assert delivery.config_calls == [
            ("dd-1", "IAA", "mock://iaa/剧A", "剧A", "TOMATO")
        ]


class TestCreateProduct:
    """create_product 委托与校验测试。"""

    def test_creates_and_verifies_product(self) -> None:
        ocean = FakeOceanEngineAdapter()
        service = DeliveryFlowService(FakeDeliverySystemAdapter(), ocean)

        product_id = service.create_product("album-1", {"name": "剧A"})

        assert product_id == "prod-album-1"
        assert ocean.create_calls == [("album-1", {"name": "剧A"})]
        assert ocean.verify_calls == ["prod-album-1"]

    def test_verify_failure_raises(self) -> None:
        ocean = FakeOceanEngineAdapter(verified=False)
        service = DeliveryFlowService(FakeDeliverySystemAdapter(), ocean)

        with pytest.raises(ExternalAdapterError):
            service.create_product("album-1", {"name": "剧A"})


class TestSubmitPlan:
    """submit_plan 校验与委托测试。"""

    def test_valid_plan_delegates(self) -> None:
        delivery = FakeDeliverySystemAdapter()
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())
        spec = _plan_spec()

        external_task_id = service.submit_plan(spec)

        assert external_task_id == "task-ext-1"
        assert delivery.submitted_plans == [spec]

    def test_missing_links_raises_validation_error(self) -> None:
        delivery = FakeDeliverySystemAdapter()
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        with pytest.raises(ValidationError):
            service.submit_plan(_plan_spec(link_set={}))

        assert delivery.submitted_plans == []

    def test_missing_cids_raises_validation_error(self) -> None:
        delivery = FakeDeliverySystemAdapter()
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        with pytest.raises(ValidationError):
            service.submit_plan(_plan_spec(account_cids=[]))

        assert delivery.submitted_plans == []


class TestPollUntilCompleted:
    """poll_until_completed 完成与超时测试。"""

    def test_completed_immediately(self) -> None:
        delivery = FakeDeliverySystemAdapter(poll_statuses=["COMPLETED"])
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        status = service.poll_until_completed("task-1", max_polls=5)

        assert status == "COMPLETED"
        assert delivery.poll_calls == ["task-1"]

    def test_completed_after_intermediate_polls(self) -> None:
        delivery = FakeDeliverySystemAdapter(
            poll_statuses=["SUBMITTED", "COMPLETED"]
        )
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        status = service.poll_until_completed("task-1", max_polls=5)

        assert status == "COMPLETED"
        assert delivery.poll_calls == ["task-1", "task-1"]

    def test_timeout_after_max_polls(self) -> None:
        delivery = FakeDeliverySystemAdapter(
            poll_statuses=["SUBMITTED", "SUBMITTED", "SUBMITTED"]
        )
        service = DeliveryFlowService(delivery, FakeOceanEngineAdapter())

        status = service.poll_until_completed("task-1", max_polls=3)

        assert status == "TIMEOUT"
        assert len(delivery.poll_calls) == 3
