"""
页面9：自选股价格预警
为关注的股票设置「涨破 / 跌破」目标价提醒；页面实时比价并标记触发状态。
（与「每日晨报 / 技术形态选股」同属「先从不影响主功能的新功能」，本页最轻量，先行落地。）
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge,
    api_get, api_post, api_put, api_delete, get_user, api_quote,
)
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input

apply_page_config(page_title="价格预警", page_icon="🔔", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🔔 自选股价格预警")
st.caption("为关注的股票设置「涨破 / 跌破」目标价提醒；页面实时比价并标记触发状态。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _current_price(code: str):
    """优先后端实时行情，失败回退本地 fetcher。"""
    rt = api_quote(code)
    if isinstance(rt, dict) and rt.get("current"):
        return float(rt["current"])
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get("current"):
            return float(q["current"])
    except Exception:
        pass
    return None


# ───────────────────────── 新建预警 ─────────────────────────
with st.expander("➕ 新建价格预警", expanded=False):
    with st.form("new_alert", clear_on_submit=True):
        code = stock_search_input(label="选择股票", key="alert_stock", default="600519")
        c1, c2 = st.columns(2)
        with c1:
            condition = st.selectbox(
                "触发条件", ["above", "below"],
                format_func=lambda x: "涨破 ▲" if x == "above" else "跌破 ▼",
            )
        with c2:
            target = st.number_input("目标价格 (元)", min_value=0.01, step=0.01, value=0.0)
        submitted = st.form_submit_button("保存预警", type="primary", use_container_width=True)
        if submitted:
            if not code:
                st.error("请选择股票")
            elif target <= 0:
                st.error("目标价格必须大于 0")
            else:
                name = fetcher.get_stock_name(code) or code
                sc, body = api_post("/api/price-alerts", {
                    "stock_code": code,
                    "stock_name": name,
                    "condition": condition,
                    "target_price": float(target),
                })
                if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                    st.success("✅ 预警已创建")
                    st.rerun()
                else:
                    msg = body.get("message", "创建失败") if isinstance(body, dict) else "创建失败"
                    st.error(f"❌ {msg}")


# ───────────────────────── 列表 + 实时比价 ─────────────────────────
sc, body = api_get("/api/price-alerts")
if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
    st.error("加载预警失败，请刷新重试。")
    st.stop()

alerts = body.get("data", []) or []

if not alerts:
    st.info("暂无预警。点击上方「新建价格预警」添加第一条。")
else:
    st.markdown(f"#### 共 {len(alerts)} 条预警（实时比价）")
    for a in alerts:
        price = _current_price(a["stock_code"])
        triggered_now = None
        diff = None
        if price is not None:
            diff = price - a["target_price"]
            triggered_now = (price >= a["target_price"]) if a["condition"] == "above" else (price <= a["target_price"])

        cond_txt = "涨破 ▲" if a["condition"] == "above" else "跌破 ▼"
        if price is None:
            price_txt = "—"
            status_txt = "行情不可用"
            status_cls = "sf-pill mid"
        elif triggered_now:
            price_txt = f"{price:.2f}"
            status_txt = "🔥 已触发"
            status_cls = "sf-pill down" if a["condition"] == "above" else "sf-pill up"
        else:
            price_txt = f"{price:.2f}"
            status_txt = "监测中"
            status_cls = "sf-pill mid"

        col_info, col_status, col_toggle, col_del = st.columns([4, 2, 1.2, 1.2])
        with col_info:
            st.markdown(
                f"**{a['stock_name'] or a['stock_code']}** `{a['stock_code']}`  "
                f"当{cond_txt} **{a['target_price']:.2f}** ｜ 现价 {price_txt}",
                help=f"创建于 {a.get('created_at', '')[:19]}",
            )
        with col_status:
            st.markdown(f'<span class="{status_cls}">{status_txt}</span>', unsafe_allow_html=True)
        with col_toggle:
            label = "停用" if a["active"] else "启用"
            if st.button(label, key=f"tog_{a['id']}", use_container_width=True):
                api_put(f"/api/price-alerts/{a['id']}/toggle")
                st.rerun()
        with col_del:
            if st.button("删除", key=f"del_{a['id']}", use_container_width=True):
                api_delete(f"/api/price-alerts/{a['id']}")
                st.rerun()

    st.caption("提示：触发状态为页面访问时实时比价结果；如需持续监控，可在本页保持打开或定时刷新。")
