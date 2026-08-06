"""rule_seed_service 单元测试：使用假仓储验证导入逻辑."""
from __future__ import annotations

import json

import pytest

from backend.application.services.rule_seed_service import (
    SeedResult,
    seed_rules_from_defaults,
)
from backend.domain.errors.domain_error import ConfigurationError


class FakeRuleRepo:
    """记录 rule_set / rule_version / rule_parameter 写入的假仓储."""

    def __init__(self) -> None:
        self.rule_sets: dict[str, object] = {}
        self.rule_versions: list[object] = []
        self.rule_parameters: list[object] = []

    def get_rule_set_by_key(self, key: str) -> object | None:
        return self.rule_sets.get(key)

    def add_rule_set(self, record: object) -> None:
        self.rule_sets[record.key] = record  # type: ignore[attr-defined]

    def add_rule_version(self, record: object) -> None:
        self.rule_versions.append(record)

    def add_rule_parameter(self, record: object) -> None:
        self.rule_parameters.append(record)


class FakePriceRepo:
    """记录 template_price_rule 写入的假仓储."""

    def __init__(self) -> None:
        self.rules: dict[str, object] = {}

    def get_template_price_rule_by_key(self, key: str) -> object | None:
        return self.rules.get(key)

    def add_template_price_rule(self, record: object) -> None:
        self.rules[record.key] = record  # type: ignore[attr-defined]


class FakeMaterialRepo:
    """记录 material_rule_range 写入的假仓储."""

    def __init__(self) -> None:
        self.rules: dict[str, object] = {}

    def get_material_rule_range_by_key(self, key: str) -> object | None:
        return self.rules.get(key)

    def add_material_rule_range(self, record: object) -> None:
        self.rules[record.key] = record  # type: ignore[attr-defined]


def _write_defaults(tmp_path: pytest.TempPathFactory, payload: object) -> str:
    """写入临时 defaults JSON 并返回路径。"""
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _sample_defaults() -> dict:
    return {
        "rule_sets": [
            {
                "key": "iaa_episode_threshold",
                "name": "IAA选集阈值",
                "category": "链接规则",
                "description": "总集数超过阈值选第2集",
                "version": "1",
                "parameters": [
                    {
                        "name": "episode_threshold",
                        "value": 50,
                        "data_type": "int",
                        "description": "超过该集数选第2集",
                    }
                ],
            }
        ],
        "template_price_rules": [
            {
                "key": "iap_2_9",
                "target_price": 2.9,
                "min_price": 2.6,
                "max_price": 5.0,
                "same_distance_strategy": "HIGHER_PRICE_FIRST",
            }
        ],
        "material_rule_ranges": [
            {
                "key": "n_leq_30",
                "min_material_count": 0,
                "max_material_count": 30,
                "strategy": "BASE_1_COPY_2",
                "base_group_count": 1,
                "copy_count": 2,
                "target_project_count": 3,
            }
        ],
    }


class TestSeedRulesFromDefaults:
    """seed_rules_from_defaults 单元测试。"""

    def test_first_seed_creates_all_rules(self, tmp_path):
        path = _write_defaults(tmp_path, _sample_defaults())
        rule_repo = FakeRuleRepo()
        price_repo = FakePriceRepo()
        material_repo = FakeMaterialRepo()

        result = seed_rules_from_defaults(
            session=object(),
            defaults_path=path,
            rule_repo=rule_repo,
            price_repo=price_repo,
            material_repo=material_repo,
        )

        assert isinstance(result, SeedResult)
        assert result.created_rules == 3
        assert result.skipped_rules == 0
        assert len(rule_repo.rule_sets) == 1
        assert len(rule_repo.rule_versions) == 1
        assert len(rule_repo.rule_parameters) == 1
        assert len(price_repo.rules) == 1
        assert len(material_repo.rules) == 1

    def test_second_seed_skips_existing(self, tmp_path):
        path = _write_defaults(tmp_path, _sample_defaults())
        rule_repo = FakeRuleRepo()
        price_repo = FakePriceRepo()
        material_repo = FakeMaterialRepo()
        kwargs = {
            "session": object(),
            "defaults_path": path,
            "rule_repo": rule_repo,
            "price_repo": price_repo,
            "material_repo": material_repo,
        }

        first = seed_rules_from_defaults(**kwargs)
        second = seed_rules_from_defaults(**kwargs)

        assert first.created_rules == 3
        assert second.created_rules == 0
        assert second.skipped_rules == 3
        assert len(rule_repo.rule_sets) == 1
        assert len(rule_repo.rule_versions) == 1
        assert len(rule_repo.rule_parameters) == 1
        assert len(price_repo.rules) == 1
        assert len(material_repo.rules) == 1

    def test_created_records_use_draft_and_json_values(self, tmp_path):
        path = _write_defaults(tmp_path, _sample_defaults())
        rule_repo = FakeRuleRepo()
        price_repo = FakePriceRepo()
        material_repo = FakeMaterialRepo()

        seed_rules_from_defaults(
            session=object(),
            defaults_path=path,
            rule_repo=rule_repo,
            price_repo=price_repo,
            material_repo=material_repo,
        )

        rule_set = list(rule_repo.rule_sets.values())[0]
        assert rule_set.status == "DRAFT"  # type: ignore[attr-defined]
        version = rule_repo.rule_versions[0]
        assert version.status == "DRAFT"  # type: ignore[attr-defined]
        parameter = rule_repo.rule_parameters[0]
        assert parameter.value_json == "50"  # type: ignore[attr-defined]
        price = price_repo.rules["iap_2_9"]
        assert price.target_price == 2.9  # type: ignore[attr-defined]
        material = material_repo.rules["n_leq_30"]
        assert material.group_size_cap == 30  # type: ignore[attr-defined]

    def test_missing_file_raises_configuration_error(self, tmp_path):
        with pytest.raises(ConfigurationError):
            seed_rules_from_defaults(
                session=object(),
                defaults_path=tmp_path / "missing.json",
            )

    def test_invalid_json_raises_configuration_error(self, tmp_path):
        path = tmp_path / "rules.json"
        path.write_text("{invalid", encoding="utf-8")

        with pytest.raises(ConfigurationError):
            seed_rules_from_defaults(session=object(), defaults_path=path)
