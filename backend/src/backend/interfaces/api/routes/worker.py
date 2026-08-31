"""Worker 进程管理端点。"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import select

from backend.infrastructure.config.settings import PROJECT_ROOT, Settings
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.models.worker import WorkerLeaseRecord

router = APIRouter(prefix="/worker", tags=["worker"])

_WORKER_MODULE = "backend.bootstrap.automation_worker"
_WORKER_CWD = str(PROJECT_ROOT / "backend")


@router.get("/status")
def worker_status():
    """返回 Worker 详细状态。"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = SessionLocal()
    try:
        lease = (
            session.execute(
                select(WorkerLeaseRecord)
                .where(
                    WorkerLeaseRecord.status == "RUNNING",
                    WorkerLeaseRecord.lease_until > now,
                )
                .limit(1)
            )
            .scalars()
            .first()
        )
        if lease is None:
            return {"online": False, "worker_id": None, "pid": None, "host": None}
        return {
            "online": True,
            "worker_id": lease.worker_id,
            "pid": lease.pid,
            "host": lease.host,
            "heartbeat_at": lease.heartbeat_at.isoformat() if lease.heartbeat_at else None,
            "lease_until": lease.lease_until.isoformat() if lease.lease_until else None,
        }
    finally:
        session.close()


@router.post("/restart")
def restart_worker():
    """杀掉现有 Worker 进程并启动新的。

    通过命令行匹配查找 automation_worker 进程，终止后重新启动。
    """
    killed = _kill_worker_processes()
    new_pid = _spawn_worker()
    return {
        "killed": killed,
        "new_pid": new_pid,
        "message": "Worker 正在重启" if new_pid else "Worker 启动失败",
    }


def _kill_worker_processes() -> int:
    """终止所有 automation_worker 进程，返回杀掉的进程数。"""
    killed = 0
    system = platform.system()
    if system == "Windows":
        killed = _kill_worker_windows()
    else:
        killed = _kill_worker_posix()
    return killed


def _kill_worker_windows() -> int:
    """Windows 下通过 PowerShell CIM 终止 Worker 进程。"""
    killed = 0
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"CommandLine LIKE '%automation_worker%'\" | "
                "Where-Object { $_.ProcessId -ne $PID } | "
                "Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                pid = int(line)
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                )
                killed += 1
            except ValueError:
                pass
    except Exception:
        pass
    return killed


def _kill_worker_posix() -> int:
    """Linux/macOS 下通过 ps/pkill 终止 Worker 进程。"""
    killed = 0
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            pid_str, args = parts[0], parts[1]
            if _is_worker_cmd(args):
                try:
                    pid = int(pid_str)
                    os.kill(pid, 9)
                    killed += 1
                except (OSError, ValueError, ProcessLookupError):
                    pass
    except Exception:
        pass
    return killed


def _is_worker_cmd(cmd: str) -> bool:
    """判断命令行是否为 automation_worker 进程。"""
    if not cmd:
        return False
    return "automation_worker" in cmd


def _spawn_worker() -> int | None:
    """启动新的 Worker 进程，返回 PID。"""
    python_exe = sys.executable or "python"
    args = [python_exe, "-m", _WORKER_MODULE, "--mode-check-interval", "1"]
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stdout_path = log_dir / f"worker-restart-{timestamp}.log"
    stderr_path = log_dir / f"worker-restart-{timestamp}.err"
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = subprocess.CREATE_NO_WINDOW
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
            proc = subprocess.Popen(
                args,
                cwd=_WORKER_CWD,
                stdout=stdout_file,
                stderr=stderr_file,
                creationflags=creationflags,
                env=env,
            )
        return proc.pid
    except Exception:
        return None
