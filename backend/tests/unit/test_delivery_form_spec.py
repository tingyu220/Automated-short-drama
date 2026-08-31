"""真实投放表单契约测试。"""
from __future__ import annotations

import pytest

from backend.domain.errors.domain_error import ValidationError
from backend.domain.plans.delivery_form_spec import build_delivery_form_spec
from backend.domain.plans.plan_spec import MaterialPlan, PlanSpec


def _plan(**overrides) -> PlanSpec:
    values = {
        "drama_name": "剧A",
        "platform": "TOMATO",
        "task_name": "TOMATO#端免剧A20260810bxr-20260810-120000-1",
        "link_set": {"IAA": "aweme://iaa"},
        "account_cids": ["cid-1", "cid-2"],
        "promotion_configs": {"IAA": "iaa-番茄-剧A"},
        "material_groups": MaterialPlan(3, 2, 9, 3, 3),
        "expected_project_count": 3,
        "material_ids": [f"material-{index}" for index in range(300)],
        "title_packages": [f"title-package-{index}" for index in range(6)],
    }
    values.update(overrides)
    return PlanSpec(**values)


def _cid_configs() -> list[dict]:
    return [
        {
            "cid": cid,
            "delivery_type": "IAA",
            "douyin_account": f"douyin-{index}",
            "account_open_preset": f"open-{index}",
            "ad_preset": f"ad-{index}",
        }
        for index, cid in enumerate(("cid-1", "cid-2"), start=1)
    ]


def test_build_form_keeps_every_cid_material_title_and_fixed_rule() -> None:
    form = build_delivery_form_spec(_plan(), _cid_configs())

    assert [row.cid for row in form.cid_rows] == ["cid-1", "cid-2"]
    assert all(row.promotion_content == "iaa-番茄-剧A" for row in form.cid_rows)
    assert len(form.material_ids) == 300
    assert len(form.title_packages) == 6
    assert form.project_rule == "按广告数生成"
    assert form.ad_rule == "按素材组生成"
    assert form.material_average_enabled is False
    assert form.title_average_enabled is False


def test_build_form_rejects_missing_six_title_packages() -> None:
    with pytest.raises(ValidationError, match="6 个标题包"):
        build_delivery_form_spec(
            _plan(title_packages=["only-one"]),
            _cid_configs(),
        )


def test_build_form_rejects_promotion_content_for_another_drama() -> None:
    with pytest.raises(ValidationError, match="主剧不一致"):
        build_delivery_form_spec(
            _plan(promotion_configs={"IAA": "iaa-番茄-其他剧"}),
            _cid_configs(),
        )


def test_paid_cids_receive_their_exact_price_promotion_content() -> None:
    plan = _plan(
        link_set={"9.9": "aweme://99", "2.9": "aweme://29"},
        promotion_configs={
            "9.9": "9.9-番茄-剧A",
            "2.9": "2.9-番茄-剧A",
        },
    )
    configs = _cid_configs()
    configs[0]["delivery_type"] = "B1-9.9"
    configs[1]["delivery_type"] = "B2-2.9"

    form = build_delivery_form_spec(plan, configs)

    assert [row.promotion_content for row in form.cid_rows] == [
        "9.9-番茄-剧A",
        "2.9-番茄-剧A",
    ]
