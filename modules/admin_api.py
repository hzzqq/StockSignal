"""
modules/admin_api.py
--------------------
管理后台 API 封装，给 Streamlit 管理页面调用。
"""
from __future__ import annotations

from urllib.parse import urlencode

from .session import api_get, api_post, api_put, api_delete


def build_query(**params) -> str:
    """把查询参数安全编码为 URL 查询串（含前导 ``?``）。

    新能力：统一管理列表接口的查询串构造，自动跳过 ``None`` / 空字符串，
    并用 ``urlencode`` 编码，避免 ``keyword`` 含 ``&`` ``=`` 空格 中文 等破坏 URL 结构。
    旧实现用 ``f"?page={page}&keyword={keyword}"`` 直插，关键词里一旦出现
    ``&`` 会被拆成额外参数、空格/中文未编码导致后端解析错位（隐性 bug）。
    """
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    return ("?" + urlencode(clean)) if clean else ""


# ================================================================ 用户管理
def get_users(page=1, per_page=50, keyword=""):
    """获取用户列表。"""
    return api_get("/api/admin/users" + build_query(page=page, per_page=per_page, keyword=keyword), timeout=10)


def create_user(username: str, password: str, role: str = "user"):
    """创建用户。"""
    return api_post("/api/admin/users", {"username": username, "password": password, "role": role})


def update_user(user_id: int, **kwargs):
    """更新用户（role/password/is_active）。"""
    return api_put(f"/api/admin/users/{user_id}", kwargs)


def delete_user(user_id: int):
    """删除用户。"""
    return api_delete(f"/api/admin/users/{user_id}")


def get_logs(page=1, per_page=50):
    """获取操作日志。"""
    return api_get("/api/admin/logs" + build_query(page=page, per_page=per_page), timeout=10)


# ================================================================ 股票管理
def search_stocks(q: str, limit: int = 15):
    """搜索股票。"""
    return api_get("/api/stocks/search" + build_query(q=q, limit=limit), timeout=5)


def get_stock_list(page=1, per_page=50, keyword=""):
    """获取股票列表（管理）。"""
    return api_get("/api/stocks/list" + build_query(page=page, per_page=per_page, keyword=keyword), timeout=10)


def get_stock_stats():
    """获取股票统计。"""
    return api_get("/api/stocks/stats", timeout=5)


# ================================================================ 系统配置
def get_config():
    """获取系统配置列表。"""
    return api_get("/api/admin/config", timeout=5)


def update_config(key: str, value: str, description: str = ""):
    """更新系统配置。"""
    payload = {"value": value}
    if description:
        payload["description"] = description
    return api_put(f"/api/admin/config/{key}", payload)


def create_config(key: str, value: str, description: str = ""):
    """创建系统配置。"""
    return api_post("/api/admin/config", {"key": key, "value": value, "description": description})


def delete_config(key: str):
    """删除系统配置。"""
    return api_delete(f"/api/admin/config/{key}")


# ================================================================ 自选股
def get_watchlist():
    """获取自选股。"""
    return api_get("/api/watchlist", timeout=5)


def add_watchlist(stock_code: str, note: str = ""):
    """添加自选股。"""
    return api_post("/api/watchlist", {"stock_code": stock_code, "note": note})


def remove_watchlist(item_id: int):
    """移除自选股。"""
    return api_delete(f"/api/watchlist/{item_id}")
