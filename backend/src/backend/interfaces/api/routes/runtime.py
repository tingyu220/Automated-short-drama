"""运行环境读取与切换接口。"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.domain.runtime.environment import RuntimeMode
from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.repositories.runtime_environment_repository import (
    SqlAlchemyRuntimeEnvironmentRepository,
)
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import (
    OperatorMatchUpdate,
    RuntimeEnvironmentUpdate,
    RuntimeEnvironmentView,
)

router = APIRouter(tags=["runtime"])


class FinalSubmitUpdate(BaseModel):
    """最终提交开关请求体。"""

    allow: bool


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


@router.get("/runtime/environment", response_model=RuntimeEnvironmentView)
def get_runtime_environment(db: Session = Depends(get_db)):
    """读取目标环境及 Worker 当前生效环境。"""
    return _to_view(SqlAlchemyRuntimeEnvironmentRepository(db).get())


@router.put("/runtime/environment", response_model=RuntimeEnvironmentView)
def update_runtime_environment(
    body: RuntimeEnvironmentUpdate,
    db: Session = Depends(get_db),
):
    """更新目标环境；Worker 在安全边界重建运行时后确认生效。"""
    if body.mode == RuntimeMode.REAL:
        if not body.confirm_real:
            raise HTTPException(status_code=422, detail="切换真实环境需要确认")
        _validate_real_configuration(Settings())
    state = SqlAlchemyRuntimeEnvironmentRepository(db).set_desired_mode(body.mode)
    return _to_view(state)


@router.put("/runtime/operator-match", response_model=RuntimeEnvironmentView)
def update_operator_match(body: OperatorMatchUpdate, db: Session = Depends(get_db)):
    """切换剧目匹配范围：仅本人 或 同组+本人。"""
    repo = SqlAlchemyRuntimeEnvironmentRepository(db)
    state = repo.set_operator_match_group(body.match_group)
    return _to_view(state)


@router.put("/runtime/final-submit")
def update_final_submit(body: FinalSubmitUpdate):
    """切换最终计划提交开关。"""
    import os

    env_key = "WORKBUDDY_ALLOW_FINAL_SUBMIT"
    os.environ[env_key] = "true" if body.allow else "false"
    return {"allow_final_submit": body.allow}


def _validate_real_configuration(settings: Settings) -> None:
    missing = []
    if not settings.feishu_task_sheet_url.strip():
        missing.append("飞书剧目表 URL")
    if not settings.tomato_base_url.strip():
        missing.append("番茄平台地址")
    if not settings.delivery_base_url.strip():
        missing.append("投放系统地址")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"真实环境配置不完整: {', '.join(missing)}",
        )


def _to_view(state) -> RuntimeEnvironmentView:
    return RuntimeEnvironmentView(
        desired_mode=state.desired_mode,
        worker_mode=state.worker_mode,
        switching=state.switching,
        operator_match_group=state.operator_match_group,
    )
