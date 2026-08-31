"""真实投放页面的完整、不可猜测表单契约。"""
from __future__ import annotations

from dataclasses import dataclass

from backend.domain.errors.domain_error import ValidationError
from backend.domain.plans.plan_spec import PlanSpec

_DELIVERY_TYPE_TO_LINK = {
    "IAA": "IAA",
    "B1": "IAA",
    "B4": "IAA",
    "B7": "IAA",
    "BX": "IAA",
    "B1-9.9": "9.9",
    "9.9": "9.9",
    "B2-2.9": "2.9",
    "2.9": "2.9",
}


@dataclass(frozen=True)
class CidFormRow:
    cid: str
    douyin_account: str
    account_open_preset: str
    ad_preset: str
    promotion_content: str
    link_type: str


@dataclass(frozen=True)
class DeliveryFormSpec:
    drama_name: str
    task_name: str
    plan_type: str
    cid_rows: tuple[CidFormRow, ...]
    material_ids: tuple[str, ...]
    title_packages: tuple[str, ...]
    material_group_count: int
    ad_limit_per_project: int
    project_count: int
    project_rule: str = "按广告数生成"
    ad_rule: str = "按素材组生成"
    material_average_enabled: bool = False
    title_average_enabled: bool = False
    shuffle_titles_once: bool = True


def build_delivery_form_spec(
    plan: PlanSpec,
    cid_configs: list[dict],
) -> DeliveryFormSpec:
    """把已验证计划与真实 CID 配置冻结成页面表单，缺值直接拒绝。"""
    by_cid: dict[str, list[dict]] = {}
    for config in cid_configs:
        by_cid.setdefault(str(config.get("cid", "")), []).append(config)

    rows: list[CidFormRow] = []
    for cid in plan.account_cids:
        matches = by_cid.get(cid, [])
        if len(matches) != 1:
            raise ValidationError(f"CID {cid} 缺少唯一真实配置")
        config = matches[0]
        link_type = _DELIVERY_TYPE_TO_LINK.get(
            str(config.get("delivery_type", ""))
        )
        if link_type is None or link_type not in plan.link_set:
            raise ValidationError(f"CID {cid} 的投放类型没有对应链接")
        promotion = str(plan.promotion_configs.get(link_type, "")).strip()
        if not promotion:
            raise ValidationError(f"CID {cid} 缺少推广内容配置")
        if not promotion.endswith(f"-{plan.drama_name}"):
            raise ValidationError(f"CID {cid} 推广内容与主剧不一致")
        values = {
            "douyin_account": str(config.get("douyin_account", "")).strip(),
            "account_open_preset": str(
                config.get("account_open_preset", "")
            ).strip(),
            "ad_preset": str(config.get("ad_preset", "")).strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValidationError(
                f"CID {cid} 配置不完整: {', '.join(missing)}"
            )
        rows.append(
            CidFormRow(
                cid=cid,
                promotion_content=promotion,
                link_type=link_type,
                **values,
            )
        )

    materials = tuple(item.strip() for item in plan.material_ids if item.strip())
    titles = tuple(item.strip() for item in plan.title_packages if item.strip())
    if not rows:
        raise ValidationError("真实投放至少需要一个 CID")
    if not materials or len(materials) != len(set(materials)):
        raise ValidationError("真实投放素材不能为空或重复")
    if len(titles) != 6 or len(set(titles)) != 6:
        raise ValidationError("真实投放必须配置 6 个标题包且不能重复")
    if plan.material_groups is None:
        raise ValidationError("真实投放缺少素材分组规则")

    plan_type = "端付" if set(plan.link_set) & {"9.9", "2.9"} else "端免"
    return DeliveryFormSpec(
        drama_name=plan.drama_name,
        task_name=plan.task_name,
        plan_type=plan_type,
        cid_rows=tuple(rows),
        material_ids=materials,
        title_packages=titles,
        material_group_count=plan.material_groups.final_group_count,
        ad_limit_per_project=plan.material_groups.ad_limit_per_project,
        project_count=plan.expected_project_count,
    )
