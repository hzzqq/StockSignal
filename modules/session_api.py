"""后端 API 调用封装（session 拆分·接口域）。

职责：统一请求实现 _api_request（重试/401 清态/代理绕过）、HTTP 动词薄封装、
各业务端点 api_*（行情/异动提醒/垃圾股/用户评分/自选）。
循环导入说明：auth_headers / clear_auth 属主入口认证链，在 _api_request 内
函数级延迟导入（模块级导入会形成 session ↔ session_api 循环）。
零业务逻辑改动：源码自 ``modules/session.py`` 原样搬运。
"""
from __future__ import annotations

import logging
import time

import streamlit as st

from modules.site_config import API_BASE

# 与主入口共用同名 logger（getLogger 单例），既有按名打补丁/过滤继续生效
logger = logging.getLogger("modules.session")

def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception as e:
        logger.warning(f"[session] 处理异常: {e}")
        return {"message": f"非 JSON 响应 (HTTP {resp.status_code})"}



def _api_request(method: str, path: str, *, payload=None, timeout: int = 5, **kwargs):
    """统一的带重试后端请求（瞬态网络错误兜底），api_get/post/put/delete 的公共实现。

    行为契约与旧实现完全一致：
      - 成功：返回 (status_code, 响应 dict)
      - 网络异常（连接重置/超时/DNS 等瞬态错误）：重试 2 次（0.4s / 0.8s 退避），
        仍失败返回 (-1, {"message": ...})
      - 401：清登录态并 st.rerun(scope="app")（fragment 与顶层均安全），不在此重试
    仅对瞬态网络错误重试；401/4xx/5xx 属有效响应，立即交给调用方。
    """
    from modules.session import auth_headers, clear_auth  # 延迟导入：避 session ↔ 本模块循环
    import requests as _requests
    url = f"{API_BASE}{path}"
    # 后端地址恒为内网/本地（默认 127.0.0.1:5050 或容器同网主机），必须绕过本机
    # 正向代理（如 127.0.0.1:2945），否则请求被路由到代理导致连接被掐
    # （RemoteDisconnected），误报网络错误。仅当调用方未显式指定代理时生效。
    if "proxies" not in kwargs:
        kwargs["proxies"] = {"http": None, "https": None}
    last_exc = None
    for attempt in range(3):
        try:
            if method == "GET":
                resp = _requests.get(url, headers=auth_headers(), timeout=timeout, **kwargs)
            else:
                resp = _requests.request(
                    method, url, json=(payload or {}), headers=auth_headers(),
                    timeout=timeout, **kwargs
                )
        except _requests.exceptions.RequestException as e:
            logger.warning(f"[session] 处理异常: {e}")
            last_exc = e
            if attempt < 2:
                time.sleep(0.4 * (attempt + 1))
                continue
            return -1, {"message": f"网络错误: {e}"}
        if resp.status_code == 401:
            clear_auth()
            # token 失效：清登录态并强制整页重跑（st.rerun 在 fragment 与顶层均安全）。
            st.rerun(scope="app")
        return resp.status_code, _safe_json(resp)
    return -1, {"message": f"网络错误: {last_exc}"}



def api_get(path: str, timeout: int = 5, **kwargs):
    return _api_request("GET", path, timeout=timeout, **kwargs)



def api_post(path: str, payload: dict | None = None, timeout: int = 5, **kwargs):
    return _api_request("POST", path, payload=payload, timeout=timeout, **kwargs)



def api_put(path: str, payload: dict | None = None, timeout: int = 5, **kwargs):
    return _api_request("PUT", path, payload=payload, timeout=timeout, **kwargs)



def api_delete(path: str, timeout: int = 5, **kwargs):
    return _api_request("DELETE", path, timeout=timeout, **kwargs)



def api_market_alerts(limit: int = 50, offset: int = 0) -> dict:
    """返回 {items, unread_count, total, last_seen}；失败返回空 dict。"""
    code, body = api_get(f"/api/market-alerts?limit={limit}&offset={offset}", timeout=8)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return {}



def api_mark_alert_read(alert_id: int) -> tuple:
    return api_post(f"/api/market-alerts/{int(alert_id)}/read", timeout=8)



def api_mark_all_alerts_read() -> tuple:
    return api_post("/api/market-alerts/read-all", timeout=8)



def api_quote(ticker: str, timeout: int = 5) -> dict | None:
    """
    实时五档行情（后端 GET /api/quote?ticker=）。

    优先走后端；失败（网络错误 / 非 200 / 响应非 ok / data 非 dict）时返回 None，
    由调用方回退到本地 fetcher.get_realtime_quote。
    成功判定键为响应信封的 status=="ok"（见 backend/utils/response.py）。
    """
    if not ticker:
        return None
    code, body = api_get(f"/api/quote?ticker={ticker}", timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return None



def api_kline(symbol: str, start: str | None = None, end: str | None = None,
              period: str = "daily", adjust: str = "qfq", timeout: int = 5) -> list | None:
    """
    历史 K 线（后端 GET /api/kline?symbol=...）。支持 daily/weekly/monthly。

    返回 records 列表（与 StockFetcher.get_kline 的 df.to_dict("records") 一致），
    调用方需用 pd.DataFrame(records) 还原 DataFrame 用法。
    失败（网络错误 / 非 200 / 响应非 ok / data 非 list）时返回 None，
    由调用方回退到本地 fetcher.get_kline。
    """
    if not symbol:
        return None
    params = f"symbol={symbol}&start={start or '2024-01-01'}&period={period}&adjust={adjust}"
    if end:
        params += f"&end={end}"
    code, body = api_get(f"/api/kline?{params}", timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, list):
            return data
    return None



def api_intraday(symbol: str, trade_date: str | None = None, timeout: int = 5) -> dict | None:
    """
    个股分时数据（后端 GET /api/intraday?symbol=...）。

    返回 dict（含 records / prev_close / trade_date），或 None（失败/无数据）。
    失败由调用方回退到本地 fetcher.get_stock_intraday_sina。
    """
    if not symbol:
        return None
    params = f"symbol={symbol}"
    if trade_date:
        params += f"&date={trade_date}"
    code, body = api_get(f"/api/intraday?{params}", timeout=timeout)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return None



def api_junk_stocks() -> list:
    """GET /api/junk-stocks，返回当前用户的垃圾股列表。"""
    code, body = api_get("/api/junk-stocks", timeout=5)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, list):
            return data
    return []



def api_add_junk_stock(code: str, note: str = "") -> dict:
    """POST /api/junk-stocks"""
    code, body = api_post("/api/junk-stocks", {"stock_code": code, "note": note}, timeout=5)
    return body if isinstance(body, dict) else {}



def api_remove_junk_stock(item_id: int) -> dict:
    """DELETE /api/junk-stocks/{id}"""
    code, body = api_delete(f"/api/junk-stocks/{item_id}", timeout=5)
    return body if isinstance(body, dict) else {}



def api_user_score(code: str) -> int | None:
    """GET /api/user-scores/{code}，返回用户打分或 None。"""
    code, body = api_get(f"/api/user-scores/{code}", timeout=5)
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        data = body.get("data")
        if isinstance(data, dict):
            return int(data.get("score", 0))
    return None



@st.cache_data(ttl=30, show_spinner=False)
def get_watchlist() -> list:
    """获取当前用户自选股列表（缓存 30s，避免每页重复请求）。返回 data 列表，失败返回 []。"""
    code, body = api_get("/api/watchlist", timeout=5)
    if code == 200 and isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return data
    return []



def api_save_user_score(code: str, score: int, name: str = "") -> dict:
    """POST /api/user-scores"""
    code, body = api_post("/api/user-scores", {"stock_code": code, "stock_name": name, "score": score}, timeout=5)
    return body if isinstance(body, dict) else {}



def save_avatar_to_backend(data_url: str, timeout: int = 5) -> dict:
    """把头像 base64 data URL 保存到后端（按账号持久化）。返回后端响应 dict。"""
    return api_post("/api/auth/avatar", {"avatar": data_url}, timeout=timeout)
