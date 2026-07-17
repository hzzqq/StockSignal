"""
页面9：自选股多维预警
支持四类预警：
  - 价格（price）：涨破/跌破目标价（实时比价）
  - 技术形态（pattern）：个股出现指定技术形态时触发
  - 成交量异动（volume）：当日量比 ≥ 阈值时触发
  - 公告（announcement）：近期新闻/公告含指定关键词时触发
触发检查在页面访问时于前端执行（与原有价格预警一致）；数据不足时标记为「待验证」。
"""
import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import (
    require_auth, render_user_badge,
    api_get, api_post, api_put, api_delete, api_quote, api_kline,
)
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.search_ui import stock_search_input
import modules.fundflow as _ff  # 副作用：确保 akshare 经本地代理访问（资金/新闻源）

apply_page_config(page_title="多维预警", page_icon="🔔", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🔔 自选股多维预警")
st.caption("价格 / 技术形态 / 成交量异动 / 公告 四类预警；触发状态为页面访问时实时比价与扫描结果。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()

PATTERN_OPTIONS = [
    "均线金叉", "均线死叉", "MACD金叉", "MACD死叉", "KDJ金叉", "KDJ死叉",
    "底背离", "顶背离", "放量突破", "缩量回调", "一阳穿多线", "十字星",
    "红三兵", "乌云盖顶", "锤头线", "倒锤头",
]
ALERT_TYPE_LABEL = {
    "price": "💲 价格",
    "pattern": "📐 技术形态",
    "volume": "📊 成交量异动",
    "announcement": "📢 公告",
}


def _current_price(code: str):
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


def _norm(s):
    return "".join(str(s).lower().split())


def _eval_pattern(code, pattern_name):
    """扫描个股日线，判断是否出现指定形态。返回 (triggered, detail)。"""
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        recs = api_kline(code, start=start, end=end)
        if not recs:
            recs = fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or len(df) < 20:
            return False, "日线数据不足"
        pats = full_analysis(df).get("patterns", []) or []
        names = [_norm(p.get("name", "")) for p in pats]
        chosen = _norm(pattern_name)
        hit = [n for n in names if chosen in n or n in chosen]
        if hit:
            return True, f"检测到：{hit[0]}"
        return False, "未出现该形态"
    except Exception as e:
        return False, f"扫描失败：{e}"


def _eval_volume(code, threshold):
    """当日量比 ≥ 阈值触发。返回 (triggered, detail)。"""
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        recs = api_kline(code, start=start, end=end)
        if not recs:
            recs = fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or "volume" not in df.columns or len(df) < 6:
            return False, "成交量数据不足"
        vols = pd.to_numeric(df["volume"], errors="coerce").dropna()
        if len(vols) < 6:
            return False, "成交量数据不足"
        today = float(vols.iloc[-1])
        prev = vols.iloc[:-1].tail(5)
        ma5 = float(prev.mean()) if len(prev) else float(vols.iloc[-2])
        if ma5 <= 0:
            return False, "基准量为0"
        ratio = today / ma5
        return ratio >= threshold, f"量比 {ratio:.2f}×（阈值 {threshold:.2f}×）"
    except Exception as e:
        return False, f"计算失败：{e}"


def _eval_announcement(code, keyword):
    """近期新闻/公告含关键词触发。返回 (triggered, detail)。"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return False, "新闻源暂无数据"
        text_cols = [c for c in df.columns if any(k in str(c) for k in ("标题", "内容", "新闻", "摘要"))]
        if not text_cols:
            text_cols = list(df.columns)
        text = " ".join(str(df[c].iloc[i]) for c in text_cols for i in range(min(len(df), 20)))
        if keyword in text:
            return True, f"新闻中出现「{keyword}」"
        return False, f"近 {min(len(df),20)} 条新闻未出现「{keyword}」"
    except Exception:
        return False, "新闻源不可用"


def _eval_alert(a):
    """按类型评估预警。返回 (triggered_bool, detail_text)。"""
    atype = a.get("alert_type", "price")
    code = a["stock_code"]
    if atype == "price":
        price = _current_price(code)
        if price is None:
            return None, "行情不可用"
        tp = float(a.get("target_price") or 0)
        cond = a.get("condition", "above")
        triggered = (price >= tp) if cond == "above" else (price <= tp)
        return triggered, f"现价 {price:.2f} / 目标 {tp:.2f}"
    elif atype == "pattern":
        pname = ""
        try:
            pname = json.loads(a.get("params") or "{}").get("pattern_name", "")
        except Exception:
            pass
        if not pname:
            return None, "未配置形态"
        return _eval_pattern(code, pname)
    elif atype == "volume":
        vr = 2.0
        try:
            vr = float(json.loads(a.get("params") or "{}").get("volume_ratio", 2.0))
        except Exception:
            pass
        return _eval_volume(code, vr)
    elif atype == "announcement":
        kw = ""
        try:
            kw = json.loads(a.get("params") or "{}").get("keyword", "")
        except Exception:
            pass
        if not kw:
            return None, "未配置关键词"
        return _eval_announcement(code, kw)
    return None, "未知类型"


def _eval_alert_parallel(alerts):
    """并行评估多条预警，避免串行网络请求阻塞页面。"""
    if not alerts:
        return []
    n_workers = min(8, max(1, len(alerts)))
    results = [None] * len(alerts)
    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        futures = {i: ex.submit(_eval_alert, a) for i, a in enumerate(alerts)}
        for i, fut in futures.items():
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = (False, f"评估失败：{e}")
    return results


# ───────────────────────── 新建预警 ─────────────────────────
with st.expander("➕ 新建预警", expanded=False):
    atype = st.radio(
        "预警类型", options=list(ALERT_TYPE_LABEL.keys()),
        format_func=lambda x: ALERT_TYPE_LABEL[x], horizontal=True, key="new_atype",
    )
    code = stock_search_input(label="选择股票", key="alert_stock", default="600519")
    params = {}
    if atype == "price":
        c1, c2 = st.columns(2)
        with c1:
            condition = st.selectbox("触发条件", ["above", "below"],
                                     format_func=lambda x: "涨破 ▲" if x == "above" else "跌破 ▼")
        with c2:
            target = st.number_input("目标价格 (元)", min_value=0.0, step=0.01, value=0.0)
    elif atype == "pattern":
        pattern_name = st.selectbox("技术形态", PATTERN_OPTIONS, index=0)
        params = {"pattern_name": pattern_name}
        st.caption("页面访问时扫描该股日线，若检测到所选形态即标记触发。")
    elif atype == "volume":
        vr = st.number_input("量比阈值（当日成交量 / 近5日均量）", min_value=0.1, step=0.1, value=2.0)
        params = {"volume_ratio": float(vr)}
        st.caption("当日量比 ≥ 阈值时触发（如 2.0 表示放量一倍）。")
    elif atype == "announcement":
        kw = st.text_input("关键词（如：增持、回购、中标、减持）")
        params = {"keyword": kw}
        st.caption("近期新闻/公告标题或内容包含该关键词即触发。")

    submitted = st.form_submit_button("保存预警", type="primary", use_container_width=True)
    if submitted:
        if not code:
            st.error("请选择股票")
        elif atype == "price" and target <= 0:
            st.error("目标价格必须大于 0")
        elif atype == "announcement" and not kw:
            st.error("请填写关键词")
        else:
            name = fetcher.get_name_only(code)
            body_payload = {
                "stock_code": code, "stock_name": name, "alert_type": atype,
                "params": params,
            }
            if atype == "price":
                body_payload["condition"] = condition
                body_payload["target_price"] = float(target)
            sc, body = api_post("/api/price-alerts", body_payload)
            if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                st.success("✅ 预警已创建")
                st.rerun()
            else:
                msg = body.get("message", "创建失败") if isinstance(body, dict) else "创建失败"
                st.error(f"❌ {msg}")


# ───────────────────────── 列表 + 触发检测 ─────────────────────────
sc, body = api_get("/api/price-alerts")
if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
    st.error("加载预警失败，请刷新重试。")
    st.stop()

alerts = body.get("data", []) or []

if not alerts:
    st.info("暂无预警。点击上方「新建预警」添加（支持价格 / 技术形态 / 成交量异动 / 公告）。")
else:
    st.markdown(f"#### 共 {len(alerts)} 条预警（页面访问时实时检测）")
    eval_results = _eval_alert_parallel(alerts)
    for idx, a in enumerate(alerts):
        atype = a.get("alert_type", "price")
        triggered, detail = eval_results[idx] if idx < len(eval_results) else (False, "评估异常")
        if atype == "price":
            cond_txt = "涨破 ▲" if a.get("condition") == "above" else "跌破 ▼"
            desc = f"当{cond_txt} **{float(a.get('target_price') or 0):.2f}**"
        elif atype == "pattern":
            pname = ""
            try:
                pname = json.loads(a.get("params") or "{}").get("pattern_name", "")
            except Exception:
                pass
            desc = f"出现形态 **{pname}**"
        elif atype == "volume":
            vr = 2.0
            try:
                vr = float(json.loads(a.get("params") or "{}").get("volume_ratio", 2.0))
            except Exception:
                pass
            desc = f"量比 ≥ **{vr:.2f}×**"
        elif atype == "announcement":
            kw = ""
            try:
                kw = json.loads(a.get("params") or "{}").get("keyword", "")
            except Exception:
                pass
            desc = f"新闻含「**{kw}**」"
        else:
            desc = ""

        if triggered is None:
            status_txt = "待验证"
            status_cls = "sf-pill mid"
        elif triggered:
            status_txt = "🔥 已触发"
            status_cls = "sf-pill down"
        else:
            status_txt = "监测中"
            status_cls = "sf-pill mid"

        col_info, col_status, col_toggle, col_del = st.columns([4, 2, 1.2, 1.2])
        with col_info:
            st.markdown(
                f"{ALERT_TYPE_LABEL.get(atype, atype)} **{a['stock_name'] or a['stock_code']}** "
                f"`{a['stock_code']}` ｜ {desc}",
                help=f"创建于 {a.get('created_at', '')[:19]}\n检测：{detail}",
            )
        with col_status:
            st.markdown(f'<span class="{status_cls}">{status_txt}</span>', unsafe_allow_html=True)
            st.caption(detail)
        with col_toggle:
            label = "停用" if a["active"] else "启用"
            if st.button(label, key=f"tog_{a['id']}", use_container_width=True):
                api_put(f"/api/price-alerts/{a['id']}/toggle")
        with col_del:
            if st.button("删除", key=f"del_{a['id']}", use_container_width=True):
                api_delete(f"/api/price-alerts/{a['id']}")

    st.caption("提示：触发检测在页面访问时于前端执行（价格实时比价、形态/量比扫描日线、公告检索新闻）。"
               "如需持续监控，可在本页保持打开或定时刷新。")
