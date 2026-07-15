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
import json
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
    avatar = db.Column(db.Text, nullable=True)  # 头像数据 URL（base64），按用户持久化
    settings = db.Column(db.Text, nullable=True)  # 用户偏好 JSON（主题/字号等），按账号持久化

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw, method="pbkdf2:sha256")

    def verify_password(self, raw: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

    @staticmethod
    def _settings_dict(raw) -> dict:
        """把 settings 列（JSON 文本）安全解析为 dict。"""
        if not raw:
            return {}
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}

    def to_public(self) -> dict:
        """对外可见字段——绝不返回 password_hash。"""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() + "Z",
            "is_active": self.is_active,
            "avatar": self.avatar,
            "settings": User._settings_dict(self.settings),
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


# ------------------------------------------------------------------ PriceAlert
class PriceAlert(db.Model):
    """用户自选股价格预警（涨/跌到目标价提醒）。"""
    __tablename__ = "price_alert"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(16), nullable=False, index=True)
    stock_name = db.Column(db.String(64), default="")
    condition = db.Column(db.String(8), nullable=False, default="above")  # above / below
    target_price = db.Column(db.Float, nullable=False)
    active = db.Column(db.Boolean, default=True)
    triggered = db.Column(db.Boolean, default=False)
    triggered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "condition": self.condition,
            "target_price": self.target_price,
            "active": self.active,
            "triggered": self.triggered,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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


# ------------------------------------------------------------------ JunkStock
class JunkStock(db.Model):
    """用户标记的「垃圾股」列表（与自选股对称）。"""
    __tablename__ = "junk_stocks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(16), nullable=False, index=True)
    note = db.Column(db.String(256), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "stock_code", name="uq_user_junk_stock"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stock_code": self.stock_code,
            "note": self.note,
            "created_at": self.created_at.isoformat() + "Z",
        }


# ------------------------------------------------------------------ UserStockScore
class UserStockScore(db.Model):
    """用户对单只股票的自定义打分（0–100），在股票选取/自选股/垃圾股表格中展示。"""
    __tablename__ = "user_stock_scores"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stock_code = db.Column(db.String(16), nullable=False, index=True)
    stock_name = db.Column(db.String(64), default="")
    score = db.Column(db.Integer, nullable=False, default=50)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "stock_code", name="uq_user_stock_score"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "score": self.score,
            "updated_at": self.updated_at.isoformat() + "Z",
        }


# ------------------------------------------------------------------ ChatHistory
class ChatHistory(db.Model):
    """星辰 AI 对话历史（按用户维度，单条记录）。

    说明：会话持久化必须走后端，不能依赖浏览器 localStorage。
    components.html 运行在 srcdoc sandbox iframe 中（origin 为 null），
    既无法直接回读父窗口 localStorage，也无法把数据回传给 Python（该构建
    下 components.html 返回 DeltaGenerator 而非组件值，且不支持 key= 参数）。
    故对话历史以 JSON 文本存数据库，按 user_id 唯一。
    """
    __tablename__ = "chat_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    messages = db.Column(db.Text, nullable=False, default="[]")  # JSON 数组
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ------------------------------------------------------------------ ForumPost（股吧帖子）
class ForumPost(db.Model):
    """股吧帖子 / 文章：用户可发表言论和文章，其他用户可查看、评论。

    可选关联某只股票（stock_code），便于按股票聚合讨论与跳转个股页。
    """
    __tablename__ = "forum_posts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False, default="")
    title = db.Column(db.String(200), nullable=False, default="")
    content = db.Column(db.Text, nullable=False, default="")
    stock_code = db.Column(db.String(16), default="", index=True)   # 可选：关联股票代码
    stock_name = db.Column(db.String(64), default="")
    likes = db.Column(db.Integer, nullable=False, default=0)
    views = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, with_content: bool = True) -> dict:
        author = db.session.get(User, self.user_id)
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "avatar": author.avatar if (author and author.avatar) else "",
            "title": self.title,
            "stock_code": self.stock_code or "",
            "stock_name": self.stock_name or "",
            "likes": self.likes,
            "views": self.views,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
        if with_content:
            d["content"] = self.content
        else:
            d["excerpt"] = (self.content or "")[:80]
        return d


# ------------------------------------------------------------------ ForumComment（股吧评论）
class ForumComment(db.Model):
    """股吧帖子的评论。"""
    __tablename__ = "forum_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("forum_posts.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    username = db.Column(db.String(64), nullable=False, default="")
    content = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self) -> dict:
        author = db.session.get(User, self.user_id)
        return {
            "id": self.id,
            "post_id": self.post_id,
            "user_id": self.user_id,
            "username": self.username,
            "avatar": author.avatar if (author and author.avatar) else "",
            "content": self.content,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
        }
