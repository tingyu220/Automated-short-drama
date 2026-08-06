"""SQLAlchemy 声明式基类."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 基类，所有模型继承自此。"""
