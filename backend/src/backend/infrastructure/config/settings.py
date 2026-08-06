"""应用配置，基于 pydantic-settings BaseSettings.

所有配置项可通过环境变量 WORKBUDDY_<FIELD> 覆盖。
"""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    """向上查找 .git 目录定位项目根。"""
    start = Path(__file__).resolve().parents[5]
    root = start
    while root.parent != root:
        if (root / ".git").exists():
            return root
        root = root.parent
    return Path.cwd().resolve()


PROJECT_ROOT: Path = _resolve_project_root()


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_prefix="WORKBUDDY_",
        case_sensitive=False,
    )

    app_name: str = "short-drama-delivery-workbuddy"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: str = "sqlite:///data/database/app.db"
    allow_final_submit: bool = False
    config_defaults_dir: Path = Path("configs/defaults")
    data_dir: Path = Path("data")
    log_level: str = "INFO"

    @field_validator("allow_final_submit", mode="before")
    @classmethod
    def _validate_allow_final_submit(cls, v: object) -> bool:
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
        raise ValueError(f"allow_final_submit 必须是严格布尔值，收到: {v!r}")

    @field_validator("config_defaults_dir", "data_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: object) -> Path:
        """将相对路径解析为项目根下的绝对路径。"""
        p = Path(v) if not isinstance(v, Path) else v
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p

    @property
    def is_development(self) -> bool:
        """开发模式快捷判断。"""
        return self.debug


settings = Settings()
