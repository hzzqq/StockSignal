import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import concurrent.futures
from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page, api_get
from modules.fetcher import StockFetcher
from modules.search_ui import stock_search_input
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.fundflow import get_individual_fund_flow
from modules.portfolio import PortfolioManager

apply_page_config(page_title="体检扫描", page_icon="🩺", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("🩺 一键体检扫描台")

# ── A股色彩约定 ──
UP = "#ee2a2a"      # 涨 / 净流入
DOWN = "#1aa260"    # 跌 / 净流出
WATCH_COLOR = "#f5a623"  # 中性关注

# 关键词（兼容未来引擎返回字符串形态名）
BULLISH_KW = ["金叉", "突破", "买入", "底背离", "多头", "看涨", "锤子", "吞没", "上穿"]
BEARISH_KW = ["死叉", "跌破", "顶背离", "空头", "看跌", "上吊"]

PRIORITY_RANK = {"HIGH": 0, "WATCH": 1, "ATTENTION": 2}
PRIORITY_LABEL = {"HIGH": "高优先级", "WATCH": "关注", "ATTENTION": "警惕"}


# ─────────────────────────── 数据准备 ───────────────────────────
def build_stock_list(scope: str) -> dict:
    """返回 {code: name}，按 code 去重。"""
    codes: dict = {}
    try:
        if scope in ("自选股", "全部"):
            sc, body = api_get("/api/watchlist", timeout=10)
            data = None
            if isinstance(body, dict):
                if body.get("status") == "ok":
                    data = body.get("data")
                elif isinstance(body.get("data"), list):
                    data = body.get("data")
            elif isinstance(body, list):
                data = body
            if isinstance(data, list):
                for it in data:
                    if not isinstance(it, dict):
                        continue
                    code = it.get("stock_code") or it.get("code")
                    name = it.get("stock_name") or it.get("name") or code
                    if code:
                        codes[str(code)] = name
    except Exception:
        pass

    try:
        if scope in ("组合持仓", "全部"):
            pm = PortfolioManager()
            df = pm.get_positions()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = row.get("ticker")
                    name = row.get("name") or code
                    if code:
                        codes[str(code)] = name
    except Exception:
        pass

    return codes


def scan_one(code: str, name):
    """单只股票体检，返回 entry dict。"""
    entry = {"code": str(code), "name": name, "patterns": [], "main_net": None, "error": None}
    try:
        today = datetime.now()
        start = (today - timedelta(days=180)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        fetcher = StockFetcher()
        df = fetcher.get_daily(code, start=start, end=end)
        if df is None or (hasattr(df, "empty") and df.empty):
            entry["error"] = "无行情数据"
            return entry
        df = DataCleaner.full_pipeline(df)
        analysis = full_analysis(df)
        patterns = analysis.get("patterns") or []
        entry["patterns"] = patterns if isinstance(patterns, list) else []
    except Exception as e:
        entry["error"] = f"分析失败: {e}"

    try:
        ff = get_individual_fund_flow(code)
        if isinstance(ff, dict):
            entry["main_net"] = ff.get("main_net")
    except Exception:
        pass
    return entry


def classify(patterns, main_net):
    has_bull = False
    has_bear = False
    names = []
    try:
        for p in patterns:
            if isinstance(p, dict):
                n = str(p.get("name", ""))
                b = str(p.get("bias", ""))
            else:
                n = str(p)
                b = ""
            if n:
                names.append(n)
            if b == "看涨" or any(k in n for k in BULLISH_KW):
                has_bull = True
            if b == "看跌" or any(k in n for k in BEARISH_KW):
                has_bear = True
    except Exception:
        pass

    mn = None
    try:
        if main_net is not None:
            mn = float(main_net)
    except Exception:
        mn = None

    if has_bull or (mn is not None and mn > 0):
        return "HIGH", names, mn
    if has_bear or (mn is not None and mn < 0):
        return "ATTENTION", names, mn
    return "WATCH", names, mn


def fmt_money(v):
    """把元格式化为 亿/万 字符串，无符号。失败返回 None。"""
    try:
        v = float(v)
    except Exception:
        return None
    if v == 0:
        return "0"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万"
    return f"{v:.2f}"


def run_scan(scope: str):
    """执行批量体检，结果写入 session_state。"""
    stocks = build_stock_list(scope)
    if not stocks:
        st.session_state["scan_results"] = []
        st.session_state["scan_time"] = 0.0
        st.session_state["scan_count"] = 0
        st.session_state["scan_scope"] = scope
        return

    items = list(stocks.items())
    entries = []
    t0 = datetime.now()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(scan_one, code, name): code for code, name in items}
        for fut in concurrent.futures.as_completed(futs):
            try:
                entries.append(fut.result())
            except Exception:
                pass
    elapsed = (datetime.now() - t0).total_seconds()

    results = []
    for e in entries:
        if e.get("error") == "无行情数据":
            continue
        prio, names, mn = classify(e.get("patterns", []), e.get("main_net"))
        results.append({
            "code": e["code"],
            "name": e["name"],
            "priority": prio,
            "names": names,
            "main_net": mn,
        })

    results.sort(key=lambda r: (PRIORITY_RANK.get(r["priority"], 9), r["code"]))
    st.session_state["scan_results"] = results
    st.session_state["scan_time"] = elapsed
    st.session_state["scan_count"] = len(results)
    st.session_state["scan_scope"] = scope


# ─────────────────────────── 控件（顶层，触发整页重跑） ───────────────────────────
SCOPE_KEY = "scan_scope_sel"
if SCOPE_KEY not in st.session_state:
    st.session_state[SCOPE_KEY] = "自选股"

scope = st.radio(
    "扫描范围",
    ["自选股", "组合持仓", "全部"],
    index=["自选股", "组合持仓", "全部"].index(st.session_state[SCOPE_KEY]),
    horizontal=True,
    key=SCOPE_KEY,
)

# 范围切换则清空旧结果
if st.session_state.get("scan_scope") != scope:
    st.session_state.pop("scan_results", None)
    st.session_state.pop("scan_time", None)
    st.session_state.pop("scan_count", None)

col1, col2 = st.columns([1, 3])
with col1:
    if st.button("🚀 开始体检", type="primary", key="scan_run"):
        with st.spinner("正在为跟踪标的做批量体检，请稍候…"):
            run_scan(scope)
        st.toast("体检完成 ✅", icon="🩺")
with col2:
    st.caption("提示：体检会拉取近 180 日行情 + 技术形态 + 主力资金流向，并对标的范围去重。")


# ─────────────────────────── 结果板（fragment，独立刷新） ───────────────────────────
@st.fragment
def result_board():
    results = st.session_state.get("scan_results")

    # 重新扫描：仅清空 session，fragment 自然重跑，不调用 st.rerun
    if st.button("🔄 重新扫描", key="rescan"):
        st.session_state.pop("scan_results", None)
        st.session_state.pop("scan_time", None)
        st.session_state.pop("scan_count", None)
        st.session_state.pop("scan_scope", None)

    results = st.session_state.get("scan_results")

    if results is None:
        st.info("尚未体检，点击上方「🚀 开始体检」开始扫描。")
        return

    if results == []:
        st.info("当前范围没有可扫描的股票。先去「形态选股」挑选一些标的加入跟踪吧。")
        if st.button("➡️ 去形态选股", key="goto_shape_empty"):
            safe_switch_page("pages/B_形态选股.py")
        return

    scan_time = st.session_state.get("scan_time", 0.0)
    scan_count = st.session_state.get("scan_count", len(results))
    st.caption(f"共扫描 {scan_count} 只标的，耗时 {scan_time:.1f}s")

    # 表格（可排序）
    rows = []
    for r in results:
        mn = r["main_net"]
        if mn is None:
            flow_txt = "—"
        else:
            s = fmt_money(mn)
            flow_txt = (f"主力净流入 {s}" if (mn and mn > 0) else
                        f"主力净流出 {s}" if (mn and mn < 0) else "主力持平")
        reason = []
        if r["names"]:
            reason.append("形态：" + "/".join(r["names"]))
        if mn is not None and s is not None and s != "0":
            reason.append(flow_txt)
        reason_txt = "；".join(reason) if reason else "无明显信号"
        rows.append({
            "代码": r["code"],
            "名称": r["name"],
            "优先级": PRIORITY_LABEL[r["priority"]],
            "命中原因": reason_txt,
            "主力净流入": flow_txt,
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 卡片式待办列表（按优先级着色）
    st.markdown("### 📋 优先待办清单")
    for r in results:
        color = {"HIGH": UP, "ATTENTION": DOWN, "WATCH": WATCH_COLOR}[r["priority"]]
        mn = r["main_net"]
        flow_html = ""
        if mn is not None:
            s = fmt_money(mn)
            if s and s != "0":
                fc = UP if mn > 0 else DOWN
                label = "净流入" if mn > 0 else "净流出"
                flow_html = (f'<span style="color:{fc};font-weight:600;">'
                             f'主力{label} {s}</span>')
        pat_html = ""
        if r["names"]:
            pat_html = "形态：" + " / ".join(r["names"])
        card = f"""
        <div style="border-left:5px solid {color};border-radius:8px;
                    padding:10px 14px;margin:8px 0;background:rgba(128,128,128,0.08);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:700;font-size:15px;">{r['code']} {r['name']}</span>
            <span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;">{PRIORITY_LABEL[r['priority']]}</span>
          </div>
          <div style="margin-top:6px;font-size:13px;color:#888;">
            {pat_html}{(' ｜ ' if pat_html and flow_html else '') + flow_html if (pat_html or flow_html) else '无明显信号'}
          </div>
        </div>
        """
        st.markdown(card, unsafe_allow_html=True)

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("跳转", key=f"jump_{r['code']}"):
                safe_switch_page("pages/1_股票选取.py")
        with b2:
            if st.button("看技术形态", key=f"shape_{r['code']}"):
                safe_switch_page("pages/B_形态选股.py")
        with b3:
            if st.button("看资金", key=f"flow_{r['code']}"):
                safe_switch_page("pages/F_资金流向.py")


result_board()
