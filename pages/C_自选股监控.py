"""
页面C：自选股实时监控
────────────────────────
一览自选股实时现价与涨跌幅（A股红涨绿跌），并行拉取行情，异常自动回退本地源。
支持一键刷新、跳转「形态选股」对自选股做技术体检、跳转「个股分析」做深度诊断。
纯前端聚合，不改动任何主功能逻辑。
"""
import streamlit as st
import concurrent.futures as _cf
from datetime import datetime

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_quote, safe_switch_page
from modules.fetcher import StockFetcher

# A股配色：涨=红，跌=绿
_UP = "#f6465d"
_DOWN = "#2ebd85"

apply_page_config(page_title="自选股监控", page_icon="📡", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("📡 自选股监控")
st.caption("实时跟踪自选股现价与涨跌幅；行情接口异常时自动回退本地源。数据仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


def _quote_one(code: str):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。"""
    rt = api_quote(code)
    if isinstance(rt, dict) and rt.get("current"):
        return code, rt
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get("current"):
            return code, q
    except Exception:
        pass
    return code, None


# ── 加载自选股 ──
sc, body = api_get("/api/watchlist", timeout=10)
if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
    st.error("加载自选股失败，请刷新重试。")
    st.stop()

items = body.get("data", []) or []
if not items:
    st.info("自选股为空，请先到「行情看板 / 我的」添加，或前往「形态选股」用自选股池扫描。")
    if st.button("➡️ 去形态选股", use_container_width=True):
        safe_switch_page("pages/B_形态选股.py")
    st.stop()

codes = [it["stock_code"] for it in items]
names = {it["stock_code"]: it.get("stock_name") or it["stock_code"] for it in items}

# ── 并行拉取实时行情 ──
with st.spinner(f"并行获取 {len(codes)} 只自选股实时行情…"):
    quotes = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        for code, q in ex.map(_quote_one, codes):
            quotes[code] = q

rows = []
for code in codes:
    q = quotes.get(code)
    if q and q.get("current"):
        cur = float(q["current"])
        prev = float(q.get("prev_close") or 0)
        chg = (cur - prev) / prev * 100 if prev else 0.0
        name = q.get("name") or names[code]
    else:
        cur, chg, name = None, None, names[code]
    rows.append({"code": code, "name": name, "cur": cur, "chg": chg})

# ── 渲染监控表 ──
up_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] >= 0)
down_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] < 0)
st.markdown(
    f"#### 共 {len(rows)} 只自选股 ｜ "
    f"<span style='color:{_UP};font-weight:600;'>▲ {up_n}</span> ／ "
    f"<span style='color:{_DOWN};font-weight:600;'>▼ {down_n}</span>",
    unsafe_allow_html=True,
)

for r in rows:
    c1, c2, c3, c4 = st.columns([3, 2, 2.4, 1.6])
    with c1:
        st.markdown(f"**{r['name']}** &nbsp;<code>{r['code']}</code>")
    with c2:
        st.markdown(f"**{r['cur']:.2f}**" if r["cur"] is not None else "—")
    with c3:
        if r["chg"] is not None:
            color = _UP if r["chg"] >= 0 else _DOWN
            arrow = "▲" if r["chg"] >= 0 else "▼"
            st.markdown(
                f'<span class="sf-pill" style="color:{color};border-color:{color}55;'
                f'background:{color}1a;">{arrow} {r["chg"]:+.2f}%</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="sf-pill mid">行情不可用</span>', unsafe_allow_html=True)
    with c4:
        if st.button("诊断", key=f"diag_{r['code']}", use_container_width=True):
            safe_switch_page("pages/2_个股分析.py")

st.divider()
col_a, col_b = st.columns(2)
with col_a:
    if st.button("🔄 刷新行情", type="primary", use_container_width=True):
        st.rerun()
with col_b:
    if st.button("🧭 用自选股做技术体检", use_container_width=True):
        safe_switch_page("pages/B_形态选股.py")

st.caption(f"数据时间：{datetime.now().strftime('%H:%M:%S')} ｜ 红涨绿跌（A股惯例）")
