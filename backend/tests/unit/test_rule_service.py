"""rule_service 单元测试：使用 fake 仓储验证草稿/校验/模拟/发布/快照/审计."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.application.services.rule_service import (
    create_config_snapshot,
    create_draft,
    list_versions,
    log_change,
    publish_version,
    save_draft_payload,
    simulate_price,
    update_draft,
    validate_rule,
)
from backend.domain.errors.domain_error import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.domain.rules.config_change_log import ConfigChangeLog
from backend.domain.rules.config_snapshot import ConfigSnapshot
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.rules.rule_set import RuleSet, RuleStatus
from backend.domain.rules.rule_version import RuleVersion, RuleVersionStatus
from backend.domain.rules.template_price_rule import TemplatePriceRule


def _ts(hour: int) -> datetime:
    return datetime(2026, 8, 6, hour, tzinfo=timezone.utc)


def _rule_set(
    rule_set_id: str = "rs-1",
    status: str = RuleStatus.DRAFT,
    key: str = "iap_2_9",
) -> RuleSet:
    return RuleSet(
        id=rule_set_id,
        key=key,
        name="IAP 2.9",
        category="价格模板",
        description="",
        status=status,
    )


def _draft_version(
    rule_set_id: str = "rs-1",
    version: str = "1",
    payload: dict | None = None,
    version_id: str = "rv-1",
    created_at: datetime | None = None,
) -> RuleVersion:
    return RuleVersion(
        id=version_id,
        rule_set_id=rule_set_id,
        version=version,
        payload_json=payload or {},
        status=RuleVersionStatus.DRAFT,
        created_at=created_at or _ts(10),
    )


class FakeRuleRepository:
    """模拟 RuleRepository：内存字典存储."""

    def __init__(
        self,
        rule_sets: dict[str, RuleSet] | None = None,
        versions: dict[str, RuleVersion] | None = None,
    ) -> None:
        self.rule_sets = rule_sets or {}
        self.versions = versions or {}
        self.change_logs: list[ConfigChangeLog] = []

    def add_rule_set(self, rule_set: RuleSet) -> RuleSet:
        self.rule_sets[rule_set.id] = rule_set
        return rule_set

    def get_rule_set(self, rule_set_id: str) -> RuleSet | None:
        return self.rule_sets.get(rule_set_id)

    def get_rule_set_by_key(self, key: str) -> RuleSet | None:
        for rule_set in self.rule_sets.values():
            if rule_set.key == key:
                return rule_set
        return None

    def update_rule_set(self, rule_set: RuleSet) -> RuleSet:
        self.rule_sets[rule_set.id] = rule_set
        return rule_set

    def add_rule_version(self, version: RuleVersion) -> RuleVersion:
        self.versions[version.id] = version
        return version

    def update_rule_version(self, version: RuleVersion) -> RuleVersion:
        self.versions[version.id] = version
        return version

    def list_rule_versions(self, rule_set_id: str) -> list[RuleVersion]:
        return [v for v in self.versions.values() if v.rule_set_id == rule_set_id]

    def append_change_log(self, log: ConfigChangeLog) -> ConfigChangeLog:
        self.change_logs.append(log)
        return log


class FakePriceRepository:
    """模拟 PriceRuleRepository."""

    def __init__(self, rules: list[TemplatePriceRule] | None = None) -> None:
        self.rules = rules or []

    def list_template_price_rules(self) -> list[TemplatePriceRule]:
        return self.rules


class FakeMaterialRepository:
    """模拟 MaterialRuleRepository."""

    def __init__(self, ranges: list[MaterialRuleRange] | None = None) -> None:
        self.ranges = ranges or []

    def list_material_rule_ranges(self) -> list[MaterialRuleRange]:
        return self.ranges


class FakeSnapshotRepository:
    """模拟 SnapshotRepository."""

    def __init__(self, versions: dict[str, RuleVersion] | None = None) -> None:
        self.versions = versions or {}
        self.snapshots: dict[str, ConfigSnapshot] = {}
        self._by_task: dict[str, ConfigSnapshot] = {}

    def get_rule_version(self, rule_version_id: str) -> RuleVersion | None:
        return self.versions.get(rule_version_id)

    def add(self, snapshot: ConfigSnapshot) -> ConfigSnapshot:
        self.snapshots[snapshot.id] = snapshot
        self._by_task[snapshot.task_id] = snapshot
        return snapshot

    def get_by_task(self, task_id: str) -> ConfigSnapshot | None:
        return self._by_task.get(task_id)


class FakeChangeLogRepository:
    """模拟 ChangeLogRepository."""

    def __init__(self) -> None:
        self.logs: list[ConfigChangeLog] = []

    def add(self, log: ConfigChangeLog) -> ConfigChangeLog:
        self.logs.append(log)
        return log


class TestCreateDraft:
    """create_draft 测试."""

    def test_create_draft_returns_draft(self):
        repo = FakeRuleRepository()
        rule_set = create_draft(repo, "new_rule", "新规则", "价格模板", "描述")

        assert rule_set.id
        assert rule_set.status == RuleStatus.DRAFT
        assert repo.rule_sets[rule_set.id].status == RuleStatus.DRAFT


class TestUpdateDraft:
    """update_draft 测试."""

    def test_update_draft_allowed_for_draft(self):
        rule_set = _rule_set()
        repo = FakeRuleRepository(rule_sets={rule_set.id: rule_set})

        updated = update_draft(
            repo, rule_set.id, {"name": "新名字", "description": "新描述"}
        )

        assert updated.name == "新名字"
        assert updated.description == "新描述"
        assert repo.rule_sets[rule_set.id].name == "新名字"

    def test_update_draft_rejects_non_draft(self):
        rule_set = _rule_set(status=RuleStatus.PUBLISHED)
        repo = FakeRuleRepository(rule_sets={rule_set.id: rule_set})

        with pytest.raises(ConflictError):
            update_draft(repo, rule_set.id, {"name": "改"})

    def test_update_draft_missing_raises_not_found(self):
        repo = FakeRuleRepository()

        with pytest.raises(NotFoundError):
            update_draft(repo, "missing", {"name": "改"})


class TestValidateRule:
    """validate_rule 测试."""

    def _repo_with_draft(self) -> FakeRuleRepository:
        rule_set = _rule_set()
        version = _draft_version(payload={"target_price": 2.9})
        return FakeRuleRepository(
            rule_sets={rule_set.id: rule_set},
            versions={version.id: version},
        )

    def _valid_price_repo(self) -> FakePriceRepository:
        return FakePriceRepository(
            [
                TemplatePriceRule(
                    id="p1",
                    key="iap_2_9",
                    target_price=2.9,
                    min_price=2.6,
                    max_price=5.0,
                )
            ]
        )

    def _valid_material_repo(self) -> FakeMaterialRepository:
        return FakeMaterialRepository(
            [
                MaterialRuleRange(
                    id="m1",
                    min_material_count=0,
                    max_material_count=30,
                    strategy="BASE_1_COPY_2",
                    base_group_count=1,
                    copy_count=2,
                    group_size_cap=30,
                    target_project_count=3,
                )
            ]
        )

    def test_validate_creates_validating_version(self):
        repo = self._repo_with_draft()
        version = validate_rule(
            repo, self._valid_price_repo(), self._valid_material_repo(), "rs-1"
        )

        assert version.status == RuleVersionStatus.VALIDATING
        assert version.version == "2"
        assert version.payload_json == {"target_price": 2.9}
        assert repo.versions[version.id] is version

    def test_validate_invalid_price_raises(self):
        repo = self._repo_with_draft()
        price_repo = FakePriceRepository(
            [
                TemplatePriceRule(
                    id="p1",
                    key="bad",
                    target_price=10.0,
                    min_price=2.6,
                    max_price=5.0,
                )
            ]
        )

        with pytest.raises(ValidationError):
            validate_rule(repo, price_repo, self._valid_material_repo(), "rs-1")
        assert len(repo.versions) == 1, "校验失败时不应新增版本"

    def test_validate_overlapping_material_ranges_raises(self):
        repo = self._repo_with_draft()
        material_repo = FakeMaterialRepository(
            [
                MaterialRuleRange(
                    id="m1",
                    min_material_count=0,
                    max_material_count=30,
                    strategy="S",
                    base_group_count=1,
                    copy_count=2,
                    group_size_cap=30,
                    target_project_count=3,
                ),
                MaterialRuleRange(
                    id="m2",
                    min_material_count=20,
                    max_material_count=50,
                    strategy="S",
                    base_group_count=2,
                    copy_count=2,
                    group_size_cap=30,
                    target_project_count=3,
                ),
            ]
        )

        with pytest.raises(ValidationError):
            validate_rule(repo, self._valid_price_repo(), material_repo, "rs-1")

    def test_validate_missing_draft_raises_not_found(self):
        rule_set = _rule_set()
        repo = FakeRuleRepository(rule_sets={rule_set.id: rule_set})

        with pytest.raises(NotFoundError):
            validate_rule(repo, self._valid_price_repo(), self._valid_material_repo(), "rs-1")

    def test_validate_uses_draft_payload_instead_of_global_table(self):
        """校验必须绑定草稿参数，而不是仅校验全局表。"""
        rule_repo = FakeRuleRepository(
            rule_sets={"rs-1": _rule_set()},
            versions={
                "rv-1": _draft_version(
                    payload={
                        "price_rules": [
                            {
                                "key": "iap_x",
                                "target_price": 10.0,
                                "min_price": 0.0,
                                "max_price": 5.0,
                            }
                        ]
                    }
                )
            },
        )

        with pytest.raises(ValidationError):
            validate_rule(
                rule_repo,
                FakePriceRepository(),
                FakeMaterialRepository(),
                "rs-1",
            )

    def test_validate_accepts_camel_case_draft_payload(self):
        """前端 camelCase 草稿参数可直接校验并生成版本。"""
        rule_repo = FakeRuleRepository(
            rule_sets={"rs-1": _rule_set()},
            versions={
                "rv-1": _draft_version(
                    payload={
                        "key": "iap_9_9",
                        "targetPrice": 9.9,
                        "minPrice": 8.8,
                        "maxPrice": 13.8,
                    }
                )
            },
        )

        version = validate_rule(
            rule_repo,
            FakePriceRepository(),
            FakeMaterialRepository(),
            "rs-1",
        )

        assert version.status == RuleVersionStatus.VALIDATING
        assert version.payload_json == rule_repo.versions["rv-1"].payload_json


class TestSaveDraftPayload:
    """save_draft_payload 单元测试。"""

    def test_updates_existing_draft(self):
        rule_repo = FakeRuleRepository(
            rule_sets={"rs-1": _rule_set()},
            versions={"rv-1": _draft_version()},
        )

        version = save_draft_payload(
            rule_repo, "rs-1", {"target_price": 3.5}
        )

        assert version.id == "rv-1"
        assert version.payload_json == {"target_price": 3.5}

    def test_creates_draft_when_missing(self):
        rule_repo = FakeRuleRepository(rule_sets={"rs-1": _rule_set()})

        version = save_draft_payload(
            rule_repo, "rs-1", {"target_price": 3.5}
        )

        assert version.status == RuleVersionStatus.DRAFT
        assert version.payload_json == {"target_price": 3.5}
        assert version.version == "1"


class TestSimulatePrice:
    """simulate_price 测试."""

    def _default_price_repo(self) -> FakePriceRepository:
        return FakePriceRepository(
            [
                TemplatePriceRule(
                    id="p1",
                    key="iap_2_9",
                    target_price=2.9,
                    min_price=2.6,
                    max_price=5.0,
                ),
                TemplatePriceRule(
                    id="p2",
                    key="iap_9_9",
                    target_price=9.9,
                    min_price=8.8,
                    max_price=13.8,
                ),
            ]
        )

    def test_matches_and_no_match(self):
        result = simulate_price(self._default_price_repo(), [2.9, 9.9, 100.0])

        assert result.inputs == [2.9, 9.9, 100.0]
        assert len(result.outputs) == 3
        assert result.outputs[0].matched_rule_key == "iap_2_9"
        assert result.outputs[0].target_price == 2.9
        assert result.outputs[0].distance == 0.0
        assert result.outputs[0].selection_reason == "MATCHED_DISTANCE"
        assert result.outputs[1].matched_rule_key == "iap_9_9"
        assert result.outputs[2].matched_rule_key is None
        assert result.outputs[2].target_price is None
        assert result.outputs[2].distance is None
        assert result.outputs[2].selection_reason == "NO_MATCH"

    def test_same_distance_higher_price_wins(self):
        repo = FakePriceRepository(
            [
                TemplatePriceRule(
                    id="pa",
                    key="low",
                    target_price=5.0,
                    min_price=0.0,
                    max_price=10.0,
                ),
                TemplatePriceRule(
                    id="pb",
                    key="high",
                    target_price=7.0,
                    min_price=0.0,
                    max_price=10.0,
                ),
            ]
        )

        result = simulate_price(repo, [6.0])

        assert result.outputs[0].matched_rule_key == "high"

    def test_same_price_lower_id_wins(self):
        repo = FakePriceRepository(
            [
                TemplatePriceRule(
                    id="id-b",
                    key="b",
                    target_price=5.0,
                    min_price=0.0,
                    max_price=10.0,
                ),
                TemplatePriceRule(
                    id="id-a",
                    key="a",
                    target_price=5.0,
                    min_price=0.0,
                    max_price=10.0,
                ),
            ]
        )

        result = simulate_price(repo, [5.0])

        assert result.outputs[0].matched_rule_key == "a"

    def test_disabled_rule_ignored(self):
        repo = FakePriceRepository(
            [
                TemplatePriceRule(
                    id="p1",
                    key="off",
                    target_price=2.9,
                    min_price=2.6,
                    max_price=5.0,
                    enabled=False,
                )
            ]
        )

        result = simulate_price(repo, [2.9])

        assert result.outputs[0].selection_reason == "NO_MATCH"


class TestPublishVersion:
    """publish_version 测试."""

    def _repo_with_validating(self) -> FakeRuleRepository:
        rule_set = _rule_set()
        draft = _draft_version(created_at=_ts(10))
        validating = RuleVersion(
            id="rv-2",
            rule_set_id="rs-1",
            version="2",
            payload_json={"target_price": 2.9},
            status=RuleVersionStatus.VALIDATING,
            created_at=_ts(11),
        )
        return FakeRuleRepository(
            rule_sets={rule_set.id: rule_set},
            versions={draft.id: draft, validating.id: validating},
        )

    def test_publish_validating_version_and_write_log(self):
        repo = self._repo_with_validating()

        published = publish_version(repo, "rs-1", actor="admin")

        assert published.status == RuleVersionStatus.PUBLISHED
        assert published.published_at is not None
        assert repo.versions["rv-2"].status == RuleVersionStatus.PUBLISHED
        assert len(repo.change_logs) == 1
        log = repo.change_logs[0]
        assert log.action == "PUBLISH"
        assert log.rule_set_id == "rs-1"
        assert log.from_version is None
        assert log.to_version == "2"
        assert log.actor == "admin"

    def test_publish_default_actor_is_system(self):
        repo = self._repo_with_validating()

        publish_version(repo, "rs-1")

        assert repo.change_logs[0].actor == "system"

    def test_publish_records_previous_published_as_from_version(self):
        rule_set = _rule_set()
        published_v1 = RuleVersion(
            id="rv-1",
            rule_set_id="rs-1",
            version="1",
            payload_json={},
            status=RuleVersionStatus.PUBLISHED,
            published_at=_ts(10),
            created_at=_ts(10),
        )
        validating_v2 = RuleVersion(
            id="rv-2",
            rule_set_id="rs-1",
            version="2",
            payload_json={},
            status=RuleVersionStatus.VALIDATING,
            created_at=_ts(11),
        )
        repo = FakeRuleRepository(
            rule_sets={rule_set.id: rule_set},
            versions={published_v1.id: published_v1, validating_v2.id: validating_v2},
        )

        publish_version(repo, "rs-1", actor="admin")

        assert repo.change_logs[0].from_version == "1"
        assert repo.change_logs[0].to_version == "2"

    def test_publish_without_pending_version_raises_conflict(self):
        rule_set = _rule_set()
        published = RuleVersion(
            id="rv-1",
            rule_set_id="rs-1",
            version="1",
            payload_json={},
            status=RuleVersionStatus.PUBLISHED,
            published_at=_ts(10),
            created_at=_ts(10),
        )
        repo = FakeRuleRepository(
            rule_sets={rule_set.id: rule_set},
            versions={published.id: published},
        )

        with pytest.raises(ConflictError):
            publish_version(repo, "rs-1")


class TestListVersions:
    """list_versions 测试."""

    def test_versions_sorted_newest_first(self):
        repo = FakeRuleRepository(
            versions={
                "rv-1": _draft_version(version="1", created_at=_ts(10)),
                "rv-2": _draft_version(
                    version="2", version_id="rv-2", created_at=_ts(11)
                ),
            }
        )

        versions = list_versions(repo, "rs-1")

        assert [v.version for v in versions] == ["2", "1"]


class TestCreateConfigSnapshot:
    """create_config_snapshot 测试."""

    def test_snapshot_uses_version_payload(self):
        version = RuleVersion(
            id="rv-pub",
            rule_set_id="rs-1",
            version="2",
            payload_json={"target_price": 2.9, "min_price": 2.6},
            status=RuleVersionStatus.PUBLISHED,
        )
        repo = FakeSnapshotRepository(versions={version.id: version})

        snapshot = create_config_snapshot(repo, "task-1", version.id)

        assert isinstance(snapshot, ConfigSnapshot)
        assert snapshot.task_id == "task-1"
        assert snapshot.rule_version_id == version.id
        assert snapshot.snapshot_json == {"target_price": 2.9, "min_price": 2.6}
        assert repo.get_by_task("task-1") is snapshot

    def test_snapshot_missing_version_raises(self):
        repo = FakeSnapshotRepository()

        with pytest.raises(NotFoundError):
            create_config_snapshot(repo, "task-1", "missing")


class TestLogChange:
    """log_change 测试."""

    def test_log_change_writes_audit(self):
        repo = FakeChangeLogRepository()

        log = log_change(
            repo,
            "UPDATE",
            "rs-1",
            "1",
            "2",
            "admin",
            detail={"reason": "调价"},
        )

        assert isinstance(log, ConfigChangeLog)
        assert log.action == "UPDATE"
        assert log.rule_set_id == "rs-1"
        assert log.from_version == "1"
        assert log.to_version == "2"
        assert log.actor == "admin"
        assert log.detail_json == {"reason": "调价"}
        assert repo.logs[0] is log
