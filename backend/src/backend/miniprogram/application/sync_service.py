"""小程序剧目同步服务：从飞书 2NgJYM 表读取数据写入 miniprogram_task。"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.miniprogram.domain.task_data import MiniProgramTaskData
from backend.miniprogram.infrastructure.database.repositories.miniprogram_repository import (
    SqlAlchemyMiniProgramTaskRepository,
)
from backend.miniprogram.domain.naming import MiniProgramNamingService
from backend.platforms.feishu.sheet_parser import parse_annotated_rows


logger = logging.getLogger(__name__)

_SHEET_URL = "https://e60nf37yjb.feishu.cn/wiki/Z0p3wf26Mi7ZxWkHIQ0c5D3SnGc"
_SHEET_ID = "2NgJYM"
_READ_RANGE = "A1:AI50"


class MiniprogramSyncService:
    """从飞书表同步小程序剧目到数据库。"""

    def __init__(
        self,
        repo: SqlAlchemyMiniProgramTaskRepository,
        naming_service: MiniProgramNamingService | None = None,
    ) -> None:
        self._repo = repo
        self._naming = naming_service or MiniProgramNamingService()

    def sync(self) -> dict[str, int]:
        """读取飞书表并同步到数据库，返回统计信息。"""
        rows = self._fetch_sheet_rows()
        created = 0
        updated = 0
        skipped = 0

        for row in rows:
            drama_name = _cell(row, 0)
            operator_name = _cell(row, 1)
            operator_code = _cell(row, 2)
            org_group = _cell(row, 3)
            org_path = _cell(row, 4)
            album_id = _cell(row, 5)
            short_name = _cell(row, 6)

            if not drama_name or not operator_name:
                skipped += 1
                continue

            if not operator_code:
                operator_code = self._naming.generate_operator_code(operator_name)

            task_id = f"mp-{drama_name}-{operator_name}"

            existing = self._repo.get_by_task_id(task_id)
            now = datetime.now(timezone.utc)

            if existing:
                existing.drama_name = drama_name
                existing.operator_name = operator_name
                existing.operator_code = operator_code
                existing.organization_group = org_group or ""
                existing.organization_path = org_path or ""
                if album_id:
                    existing.album_id = album_id
                if short_name:
                    existing.drama_short_name = short_name
                existing.updated_at = now
                self._repo.save(existing)
                updated += 1
            else:
                data = MiniProgramTaskData(
                    id=str(uuid4()),
                    task_id=task_id,
                    drama_name=drama_name,
                    operator_name=operator_name,
                    operator_code=operator_code,
                    organization_group=org_group or "",
                    organization_path=org_path or "",
                    drama_short_name=short_name or None,
                    album_id=album_id or None,
                    workflow_status="NOT_STARTED",
                    created_at=now,
                    updated_at=now,
                )
                self._repo.save(data)
                created += 1

        logger.info(
            "小程序剧目同步完成: created=%d updated=%d skipped=%d",
            created,
            updated,
            skipped,
        )
        return {"created": created, "updated": updated, "skipped": skipped}

    def _fetch_sheet_rows(self) -> list[list[str]]:
        """通过 lark-cli 读取飞书表 CSV 数据。"""
        command = self._build_read_command()
        completed = self._run(command)
        envelope = json.loads(completed.stdout)
        annotated_csv = (envelope.get("data") or {}).get("annotated_csv", "")
        if not annotated_csv:
            return []

        rows: list[list[str]] = []
        for row_number, cells in parse_annotated_rows(annotated_csv):
            if row_number == 1:
                continue
            if any(cell.strip() for cell in cells):
                rows.append(cells)
        return rows

    def _build_read_command(self) -> list[str]:
        return [
            "lark-cli",
            "sheets",
            "+csv-get",
            "--url",
            _SHEET_URL,
            "--sheet-id",
            _SHEET_ID,
            "--range",
            _READ_RANGE,
            "--as",
            "user",
            "--format",
            "json",
        ]

    def _run(self, command: list[str]) -> Any:
        command = self._resolve_command(command)
        try:
            completed = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=30,
            )
        except Exception as exc:
            raise RuntimeError(f"lark-cli 执行失败: {exc}") from exc
        if completed.returncode != 0:
            raise RuntimeError(
                f"lark-cli 命令失败: {' '.join(command)} stderr={completed.stderr}"
            )
        return completed

    @staticmethod
    def _resolve_command(command: list[str]) -> list[str]:
        if sys.platform != "win32" or not command or command[0] != "lark-cli":
            return command
        wrapper = shutil.which("lark-cli.cmd")
        if wrapper is None:
            return ["lark-cli.cmd", *command[1:]]
        script = Path(wrapper).parent / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
        return [shutil.which("node.exe") or "node.exe", str(script), *command[1:]]


def _cell(row: list[str], index: int) -> str:
    if index < len(row):
        return row[index].strip()
    return ""
