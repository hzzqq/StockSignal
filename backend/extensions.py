"""
backend/extensions.py
---------------------
SQLAlchemy 实例集中管理，便于拆分。
"""
from __future__ import annotations  # noqa: I001
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
