"""Worker 真实配置装配测试。"""
from __future__ import annotations

import pytest

from backend.application.services.worker_executor import (
    _account_assignment_failure,
    _link_preparation_failure,
    _real_cid_configs,
)
from backend.application.services.task_preparation_service import PreparationOutcome
from backend.domain.errors.domain_error import ValidationError
from backend.domain.tasks.drama_task import DramaTask
from datetime import datetime, timezone


def test_real_cid_configs_use_snapshot_values_without_fabricated_fallback() -> None:
    accounts = [
        {"cid": "cid-1", "role": "B1"},
        {"cid": "cid-2", "role": "B2-2.9"},
    ]
    mappings = [
        {
            "cid": "cid-1",
            "company": "主体甲",
            "ad_preset": "广告预设甲",
            "open_preset": "开户预设甲",
            "douyin_account": "抖音甲",
        },
        {
            "cid": "cid-2",
            "company": "主体乙",
            "ad_preset": "广告预设乙",
            "open_preset": "开户预设乙",
            "douyin_account": "抖音乙",
        },
    ]

    configs = _real_cid_configs(accounts, mappings)

    assert configs[0]["subject"] == "主体甲"
    assert configs[0]["delivery_type"] == "IAA"
    assert configs[0]["account_open_preset"] == "开户预设甲"
    assert configs[1]["delivery_type"] == "B2-2.9"
    assert not any("dy-cid" in str(value) for row in configs for value in row.values())


def test_real_cid_configs_reject_missing_snapshot_mapping() -> None:
    with pytest.raises(ValidationError, match="cid-2"):
        _real_cid_configs(
            [{"cid": "cid-1", "role": "B1"}, {"cid": "cid-2", "role": "B4"}],
            [
                {
                    "cid": "cid-1",
                    "company": "主体甲",
                    "ad_preset": "广告预设甲",
                    "open_preset": "开户预设甲",
                    "douyin_account": "抖音甲",
                }
            ],
        )


def test_partial_account_write_failure_code_is_preserved_for_queue() -> None:
    task = DramaTask(
        id="task-1",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    outcome = _account_assignment_failure(
        task,
        {"IAA": "link"},
        "PARTIAL_WRITE",
        "写后回读不一致",
        [],
    )

    assert outcome.status == "MANUAL_REVIEW"
    assert outcome.failure_code == "PARTIAL_WRITE"
    assert outcome.retry_safe is False
    assert "回读" in outcome.events[0].message


def test_drama_mismatch_failure_details_are_preserved_for_queue() -> None:
    """防止同名剧人工处理被降级成无原因的普通失败。"""
    task = DramaTask(
        id="task-match",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    preparation = PreparationOutcome(
        status="MANUAL_REVIEW",
        failure_code="DRAMA_MISMATCH",
        details={"stage": "DETAIL", "match_count": 0},
    )

    outcome = _link_preparation_failure(task, preparation)

    assert outcome.status == "MANUAL_REVIEW"
    assert outcome.failure_code == "DRAMA_MISMATCH"
    assert outcome.retry_safe is False
    assert outcome.events[0].event_type == "LINK_EXTRACTION"
    assert outcome.events[0].context_json["stage"] == "DETAIL"
