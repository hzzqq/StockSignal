"""
modules/admin_api.py
--------------------
管理后台 API 封装，给 Streamlit 管理页面调用。
"""
from __future__ import annotations
from .session import api_get, api_post, api_put, api_delete


# ================================================================ 用户管理
def get_users(page=1, per_page=50, keyword=""):
    """获取用户列表。"""
    params = f"?page={page}&per_page={per_page}"
    if keyword:
        params += f"&keyword={keyword}"
    return api_get(f"/api/admin/users{params}", timeout=10)


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
    return api_get(f"/api/admin/logs?page={page}&per_page={per_page}", timeout=10)


# ================================================================ 股票管理
def search_stocks(q: str, limit: int = 15):
    """搜索股票。"""
    return api_get(f"/api/stocks/search?q={q}&limit={limit}", timeout=5)


def get_stock_list(page=1, per_page=50, keyword=""):
    """获取股票列表（管理）。"""
    params = f"?page={page}&per_page={per_page}"
    if keyword:
        params += f"&keyword={keyword}"
    return api_get(f"/api/stocks/list{params}", timeout=10)


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
