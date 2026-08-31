"""应用配置，基于 pydantic-settings BaseSettings.

所有配置项可通过环境变量 WORKBUDDY_<FIELD> 覆盖。
"""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    """从当前模块文件向上查找项目根标记（AGENTS.md / .git）。

    仓库根放置 AGENTS.md 与 .git，优先匹配 AGENTS.md。
    """
    root = Path(__file__).resolve().parent
    _markers = ("AGENTS.md", ".git")
    while root.parent != root:
        if any((root / m).exists() for m in _markers):
            return root
        root = root.parent
    return Path.cwd().resolve()


PROJECT_ROOT: Path = _resolve_project_root()


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_prefix="WORKBUDDY_",
        case_sensitive=False,
        env_file=str(PROJECT_ROOT / ".env"),
    )

    app_name: str = "short-drama-delivery-workbuddy"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: str = "sqlite:///data/database/app.db"
    allow_final_submit: bool = False
    use_real_adapters: bool = False
    poll_interval_seconds: int = 300
    poll_timeout_seconds: int = 7200
    tomato_base_url: str = "https://www.changdupingtai.com"
    delivery_base_url: str = "http://web.tjhaozew.top"
    ocean_base_url: str = "https://business.oceanengine.com"
    youxuan_base_url: str = "http://duanju.youxuan2.cn"
    config_defaults_dir: Path = Path("configs/defaults")
    data_dir: Path = Path("data")
    log_level: str = "INFO"
    changdu_account: str = ""
    changdu_password: str = ""
    feishu_source_sheet_url: str = ""
    feishu_source_sheet_id: str = "sM4NAq"
    feishu_source_sheet_name: str = "漫剧投放计划表"
    feishu_private_sheet_url: str = ""
    feishu_private_sheet_id: str = "a8d032"
    feishu_private_sheet_name: str = "剧目表"
    feishu_task_sheet_url: str = ""
    feishu_task_sheet_name: str = "剧目表"

    @field_validator("allow_final_submit", "use_real_adapters", mode="before")
    @classmethod
    def _validate_strict_bool(cls, v: object) -> bool:
        """严格解析布尔值，非法值直接校验失败。"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in ("true", "1", "yes", "on"):
                return True
            if v_lower in ("false", "0", "no", "off"):
                return False
        if isinstance(v, int):
            if v == 1:
                return True
            if v == 0:
                return False
        raise ValueError(f"配置项必须是严格布尔值，收到: {v!r}")

    @field_validator("config_defaults_dir", "data_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: object) -> Path:
        """将相对路径解析为项目根下的绝对路径。"""
        p = Path(v) if not isinstance(v, Path) else v
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    @field_validator("poll_interval_seconds", "poll_timeout_seconds")
    @classmethod
    def _validate_positive_seconds(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("轮询时间配置必须为正整数")
        return v

    @field_validator("tomato_base_url", "delivery_base_url", "ocean_base_url", "youxuan_base_url")
    @classmethod
    def _validate_platform_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("平台地址必须是 http(s) URL")
        return normalized

    @property
    def is_development(self) -> bool:
        """开发模式快捷判断。"""
        return self.debug


settings = Settings()
