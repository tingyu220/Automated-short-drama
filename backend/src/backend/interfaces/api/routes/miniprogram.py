"""MiniProgram API 路由。

提供接口：
- GET /api/miniprogram/tasks — 列出 MiniProgram 任务
- GET /api/miniprogram/tasks/{task_id} — 任务详情
- GET /api/miniprogram/config — 剧场配置
- GET /api/miniprogram/discovery/{task_id} — Discovery 结果
- POST /api/miniprogram/sync — 从飞书表同步剧目
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import (
    MiniProgramConfigView,
    MiniProgramDiscoveryCaptureView,
    MiniProgramDiscoveryView,
    MiniProgramTaskView,
)
from backend.miniprogram.application.sync_service import MiniprogramSyncService
from backend.miniprogram.domain.naming import MiniProgramNamingService
from backend.miniprogram.infrastructure.config.miniprogram_config import (
    list_available_configs,
    load_miniprogram_config,
)
from backend.miniprogram.infrastructure.database.repositories.miniprogram_repository import (
    SqlAlchemyMiniProgramTaskRepository,
)
from backend.miniprogram.platforms.youxuan.network.discovery_storage import (
    load_captures_from_artifacts,
)

router = APIRouter(prefix="/miniprogram", tags=["miniprogram"])


def get_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session


def _configs_dir() -> Path:
    """返回 MiniProgram configs 目录。"""
    here = Path(__file__).resolve()
    # here = .../backend/src/backend/interfaces/api/routes/miniprogram.py
    # parents[3] = .../backend/src/backend
    return here.parents[3] / "miniprogram" / "configs"


@router.get("/tasks", response_model=list[MiniProgramTaskView])
def list_miniprogram_tasks(db: Session = Depends(get_db)):
    """列出所有 MiniProgram 任务，按更新时间倒序。"""
    repo = SqlAlchemyMiniProgramTaskRepository(db)
    tasks = repo.list_all()
    return [MiniProgramTaskView.model_validate(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=MiniProgramTaskView)
def get_miniprogram_task(task_id: str, db: Session = Depends(get_db)):
    """获取指定 MiniProgram 任务详情。"""
    repo = SqlAlchemyMiniProgramTaskRepository(db)
    task = repo.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"MiniProgram 任务不存在: {task_id}")
    return MiniProgramTaskView.model_validate(task)


@router.get("/config", response_model=list[MiniProgramConfigView])
def list_miniprogram_configs():
    """列出所有可用的 MiniProgram 剧场配置。"""
    configs_dir = _configs_dir()
    config_names = list_available_configs(configs_dir)
    views: list[MiniProgramConfigView] = []
    for name in config_names:
        config_path = configs_dir / f"{name}.yaml"
        try:
            config = load_miniprogram_config(config_path)
            views.append(
                MiniProgramConfigView(
                    config_name=name,
                    mini_program=config.mini_program.model_dump(),
                    promotion=config.promotion.model_dump(),
                    ocean=config.ocean.model_dump(),
                    price_tiers={
                        tier: cfg.model_dump()
                        for tier, cfg in config.price_tiers.items()
                    },
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"加载配置 {name} 失败: {exc}",
            )
    return views


@router.get("/discovery/{task_id}", response_model=MiniProgramDiscoveryView)
def get_miniprogram_discovery(task_id: str):
    """获取指定任务的 Network Discovery 结果（从 artifacts 加载）。"""
    captures = load_captures_from_artifacts(task_id)
    if not captures:
        raise HTTPException(
            status_code=404,
            detail=f"未找到任务 {task_id} 的 Discovery 数据",
        )

    endpoint_counts: dict[str, int] = {}
    for cap in captures:
        endpoint_counts[cap.endpoint_type] = endpoint_counts.get(cap.endpoint_type, 0) + 1

    return MiniProgramDiscoveryView(
        task_id=task_id,
        capture_count=len(captures),
        endpoint_counts=endpoint_counts,
        endpoint_types=sorted(endpoint_counts.keys()),
        captures=[
            MiniProgramDiscoveryCaptureView(
                url=cap.url,
                method=cap.method,
                status=cap.status,
                endpoint_type=cap.endpoint_type,
                response_body=cap.response_body,
                captured_at=cap.captured_at,
            )
            for cap in captures
        ],
    )


@router.post("/sync")
def sync_miniprogram_tasks(db: Session = Depends(get_db)) -> dict[str, Any]:
    """从飞书 2NgJYM 表同步小程序剧目到数据库。"""
    repo = SqlAlchemyMiniProgramTaskRepository(db)
    service = MiniprogramSyncService(repo, MiniProgramNamingService())
    try:
        result = service.sync()
        db.commit()
        return {"ok": True, **result}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"同步失败: {exc}")
