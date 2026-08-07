"""平台登录态 API：状态检查、storage 导入与清理。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.application.services.session_service import SessionService
from backend.application.services.session_login import SessionLoginManager

router = APIRouter(tags=["sessions"])


class StorageImportBody(BaseModel):
    """浏览器导出的 storage_state。"""

    storage_state: dict


def _service() -> SessionService:
    return SessionService()


_login_manager = SessionLoginManager()


@router.get("/sessions")
def list_sessions():
    """返回四平台登录态。"""
    return _service().list_statuses()


@router.post("/sessions/{platform}/check")
def check_session(platform: str):
    """重新检查指定平台登录态。"""
    return _service().check(platform).__dict__


@router.post("/sessions/{platform}/storage")
def import_session_storage(platform: str, body: StorageImportBody):
    """导入浏览器 storage_state 到本地 Session 目录。"""
    path = _service().import_storage(platform, body.storage_state)
    return {"platform": platform, "storage_path": str(path)}


@router.post("/sessions/{platform}/clear")
def clear_session(platform: str):
    """清除指定平台本地 Session（调用方自行确认）。"""
    service = _service()
    service.clear(platform)
    return {"platform": platform, "cleared": True}


@router.post("/sessions/{platform}/login")
def start_login(platform: str):
    """启动 Playwright 登录任务，打开浏览器完成登录并自动保存。"""
    started = _login_manager.start(platform)
    return {
        "platform": platform,
        "started": started,
        "running": _login_manager.is_running(platform),
    }


@router.post("/sessions/{platform}/finish")
def finish_login(platform: str):
    """用户确认已完成登录，立即保存当前 Session。"""
    finished = _login_manager.finish(platform)
    return {"platform": platform, "finished": finished}
