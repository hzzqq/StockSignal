"""
backend/models.py
-----------------
全部数据模型。
- User        用户（admin / user 两种角色）
- Stock       股票基础信息（代码/名称/市场/拼音索引）
- Watchlist   用户自选股
- SystemConfig 系统键值配置
- OperationLog 操作审计日志
"""
from __future__ import annotations
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db


# ------------------------------------------------------------------ User
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="user")  # user / admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw, method="pbkdf2:sha256")

    def verify_password(self, raw: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

    def to_public(self) -> dict:
        """对外可见字段——绝不返回 password_hash。"""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() + "Z",
            "is_active": self.is_active,
        }


# ------------------------------------------------------------------ Stock
class Stock(db.Model):
    """A股基础信息表，支持拼音首字母 + 全拼搜索。"""
    __tablename__ = "stocks"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False, index=True)  # 600519
    name = db.Column(db.String(64), nullable=False, index=True)               # 贵州茅台
    market = db.Column(db.String(8), nullable=False, default="A")             # SH / SZ / A
    asset_type = db.Column(db.String(16), nullable=False, default="stock")     # stock/index/fund/etf/bond
    pinyin_initials = db.Column(db.String(32), nullable=False, default="", index=True)  # gzmt
    pinyin_full = db.Column(db.String(128), nullable=False, default="", index=True)     # guizhoumaotai
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "asset_type": self.asset_type,
            "pinyin_initials": self.pinyin_initials,
            "pinyin_full": self.pinyin_full,
        }


# ------------------------------------------------------------------ Watchlist
class Watchlist(db.Model):
    """用户自选股。"""
    __tablename__ = "watchlist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(16), nullable=False, index=True)
    note = db.Column(db.String(256), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "stock_code", name="uq_user_stock"),)


# ------------------------------------------------------------------ SystemConfig
class SystemConfig(db.Model):
    """系统键值配置，管理员可在线编辑。"""
    __tablename__ = "system_config"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False, default="")
    description = db.Column(db.String(256), default="")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
            "updated_by": self.updated_by,
        }


# ------------------------------------------------------------------ OperationLog
class OperationLog(db.Model):
    """操作审计日志。"""
    __tablename__ = "operation_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False)
    action = db.Column(db.String(64), nullable=False)        # create_user / delete_user / update_config ...
    target = db.Column(db.String(128), default="")
    detail = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() + "Z",
        }
