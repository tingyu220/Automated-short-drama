"""规则 API 路由：列表、版本、校验、发布与价格模拟。"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.application.services import rule_service
from backend.domain.errors.domain_error import NotFoundError
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
    SqlAlchemyRuleRepository,
)
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import (
    MaterialRuleRangeView,
    RuleSetView,
    RuleVersionDetailView,
    RuleVersionView,
    SimulationOutputView,
    SimulationResultView,
    TemplatePriceRuleView,
)

router = APIRouter(tags=["rules"])


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


class PriceSimulationBody(BaseModel):
    """价格模拟请求体。"""

    candidates: list[float]


class SaveDraftBody(BaseModel):
    """保存规则草稿请求体。"""

    payload: dict


def _require_rule_set(
    db: Session, rule_set_id: str
) -> SqlAlchemyRuleRepository:
    """校验规则集存在并返回规则仓储。"""
    rule_repo = SqlAlchemyRuleRepository(db)
    if rule_repo.get_rule_set(rule_set_id) is None:
        raise NotFoundError(f"规则集不存在: {rule_set_id}")
    return rule_repo


@router.get("/rules", response_model=list[RuleSetView])
def list_rules(db: Session = Depends(get_db)):
    """返回全部规则集视图。"""
    rule_sets = SqlAlchemyRuleRepository(db).list_rule_sets()
    return [RuleSetView.model_validate(rule_set) for rule_set in rule_sets]


@router.get("/rules/price-rules", response_model=list[TemplatePriceRuleView])
def list_price_rules(db: Session = Depends(get_db)):
    """返回当前生效的 IAP 模板价格规则。"""
    rules = SqlAlchemyPriceRuleRepository(db).list_template_price_rules()
    return [TemplatePriceRuleView.model_validate(rule) for rule in rules]


@router.get("/rules/material-rules", response_model=list[MaterialRuleRangeView])
def list_material_rules(db: Session = Depends(get_db)):
    """返回当前生效的素材数量区间规则。"""
    ranges = SqlAlchemyMaterialRuleRepository(db).list_material_rule_ranges()
    return [MaterialRuleRangeView.model_validate(item) for item in ranges]


@router.get("/rules/{rule_set_id}/versions", response_model=list[RuleVersionView])
def list_rule_versions(rule_set_id: str, db: Session = Depends(get_db)):
    """返回规则集版本列表，按创建时间倒序。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    versions = rule_service.list_versions(rule_repo, rule_set_id)
    return [RuleVersionView.model_validate(version) for version in versions]


@router.get("/rules/{rule_set_id}/versions/{version_id}", response_model=RuleVersionDetailView)
def get_rule_version(
    rule_set_id: str, version_id: str, db: Session = Depends(get_db)
):
    """获取指定版本详情（含 payload）。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    version = rule_service.get_version(rule_repo, rule_set_id, version_id)
    return RuleVersionDetailView.model_validate(version)


@router.post("/rules/{rule_set_id}/validate", response_model=RuleVersionView)
def validate_rule_set(rule_set_id: str, db: Session = Depends(get_db)):
    """校验当前规则并创建 VALIDATING 版本。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    price_repo = SqlAlchemyPriceRuleRepository(db)
    material_repo = SqlAlchemyMaterialRuleRepository(db)
    version = rule_service.validate_rule(
        rule_repo, price_repo, material_repo, rule_set_id
    )
    return RuleVersionView.model_validate(version)


@router.post("/rules/{rule_set_id}/draft", response_model=RuleVersionView)
def save_rule_draft(
    rule_set_id: str,
    body: SaveDraftBody,
    db: Session = Depends(get_db),
):
    """保存规则集草稿参数到最新 DRAFT 版本。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    version = rule_service.save_draft_payload(
        rule_repo, rule_set_id, body.payload
    )
    return RuleVersionView.model_validate(version)


@router.post("/rules/{rule_set_id}/publish", response_model=RuleVersionView)
def publish_rule_set(rule_set_id: str, db: Session = Depends(get_db)):
    """发布最新待发布版本并写入审计日志。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    price_repo = SqlAlchemyPriceRuleRepository(db)
    material_repo = SqlAlchemyMaterialRuleRepository(db)
    version = rule_service.publish_version(
        rule_repo, rule_set_id, actor="dashboard"
    )
    rule_service.apply_published_payload(
        price_repo, material_repo, version.payload_json
    )
    return RuleVersionView.model_validate(version)


@router.delete("/rules/{rule_set_id}/versions/{version_id}")
def delete_rule_version(
    rule_set_id: str, version_id: str, db: Session = Depends(get_db)
):
    """删除指定版本（仅 DRAFT / VALIDATING 可删除）。"""
    rule_repo = _require_rule_set(db, rule_set_id)
    rule_service.delete_version(
        rule_repo, rule_set_id, version_id, actor="dashboard"
    )
    return {"deleted": True}


@router.post("/rules/simulate-price", response_model=SimulationResultView)
def simulate_price(body: PriceSimulationBody, db: Session = Depends(get_db)):
    """按候选价格模拟 IAP 模板匹配。"""
    price_repo = SqlAlchemyPriceRuleRepository(db)
    result = rule_service.simulate_price(price_repo, body.candidates)
    return SimulationResultView(
        inputs=result.inputs,
        outputs=[
            SimulationOutputView(
                candidate=output.candidate,
                matched_rule_key=output.matched_rule_key,
                target_price=output.target_price,
                distance=output.distance,
                selection_reason=output.selection_reason,
            )
            for output in result.outputs
        ],
    )
