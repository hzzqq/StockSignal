"""
页面B：技术形态选股器
在用户自选股 / 手动输入的股票池中扫描技术形态（金叉、突破、背离等），
输出命中标的与多维技术评分，辅助盘前筛选。纯前端计算，不改动任何主功能。

修复记录（#253）：
- 修复 pandas 未导入导致「开始扫描」直接崩溃（NameError: pd）的致命 bug。
- 扩充形态库：在原有 K 线形态基础上新增 MACD金叉/死叉、均线金叉、KDJ金叉/死叉、
  底背离/顶背离，使「金叉 / 突破 / 背离」等关键词筛选真正可用。
- 新增 🔍 匹配结果搜索框（stock_search_input），支持代码/名称/拼音模糊匹配 +
  下拉结果选择，并可「加入扫描池」批量管理。
- 结果展示改为「形态概述（名称·偏向）」，更易读。
"""
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_kline
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.search_ui import multi_stock_search_input, stock_search_input

apply_page_config(page_title="形态选股", page_icon="🧭", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("🧭 技术形态选股器")
st.caption("在股票池中扫描技术形态并给出多维技术评分；结果仅供参考，非投资建议。")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()

import concurrent.futures as _cf


def _norm_code(c: str) -> str:
    """规整股票代码：去掉 sh/sz/bj 等交易所前缀，保留 6 位纯数字代码。"""
    c = str(c).strip().lower()
    for p in ("sh", "sz", "bj"):
        if c.startswith(p):
            c = c[len(p):]
    return c.upper()


# ───────────────────────── 选择股票池 ─────────────────────────
source = st.radio("股票池来源", ["我的自选股", "手动输入代码"], horizontal=True)

universe = []
if source == "我的自选股":
    sc, body = api_get("/api/watchlist", timeout=10)
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        universe = [_norm_code(w["stock_code"]) for w in (body.get("data", []) or []) if w.get("stock_code")]
        if universe:
            st.caption(
                f"✅ 已从自选股加载 **{len(universe)}** 只："
                f"{', '.join(universe[:12])}{' …' if len(universe) > 12 else ''}"
            )
        else:
            st.warning("自选股为空，请先到「我的 / 自选股」添加，或切换为「手动输入代码」。")
    else:
        msg = body.get("message", "") if isinstance(body, dict) else ""
        st.error(f"❌ 加载自选股失败（HTTP {sc}）{msg}；可切换为「手动输入代码」继续。")
else:
    # 手动模式：🔍 搜索添加 + 批量文本输入，二者合并为扫描池
    if "screener_pool" not in st.session_state:
        st.session_state["screener_pool"] = []

    # ── 🔍 搜索添加 ──
    st.subheader("🔍 搜索添加", divider="gray")
    st.caption("支持 6 位代码 / 中文名称 / 拼音首字母（gzmt）/ 全拼（maotai）/ 首字（茅）。")
    picked = stock_search_input(
        label="输入代码 / 名称 / 拼音搜索",
        key="screener_search",
        default="600519",
    )
    c_add, c_clr = st.columns([1, 4])
    with c_add:
        if st.button("➕ 加入扫描池", key="screener_add", use_container_width=True):
            if picked and picked not in st.session_state["screener_pool"]:
                st.session_state["screener_pool"].append(picked)
                st.rerun()
    if st.session_state["screener_pool"]:
        if _theme_is_dark():
            chip_bg, chip_border, chip_color = "#1a1a2e", "#2d2d44", "#e2e8f0"
        else:
            chip_bg, chip_border, chip_color = "#eef2ff", "#c7d2fe", "#1e3a8a"
        chips = "".join(
            f'<span style="display:inline-block;background:{chip_bg};border:1px solid {chip_border};'
            f'border-radius:12px;padding:4px 10px;margin:3px 3px 3px 0;font-size:12px;color:{chip_color};"'
            f'>{code}</span>'
            for code in st.session_state["screener_pool"]
        )
        st.markdown(f"<div style='margin:8px 0;'>{chips}</div>", unsafe_allow_html=True)
        with c_clr:
            if st.button("🗑️ 清空扫描池", key="screener_clear", use_container_width=True):
                st.session_state["screener_pool"] = []
                st.rerun()

    # ── 批量文本输入 ──
    st.subheader("批量输入", divider="gray")
    raw = multi_stock_search_input(
        label="或直接粘贴多只股票（代码/名称，逗号分隔，可留空）",
        key="screener_stocks",
        default="",
    )
    manual_codes = [_norm_code(c) for c in (raw or [])]
    # 合并搜索池 + 批量输入，去重保序
    universe = list(dict.fromkeys(st.session_state["screener_pool"] + manual_codes))
    if universe:
        st.caption(f"📋 当前扫描池共 **{len(universe)}** 只：{', '.join(universe[:20])}"
                   f"{' …' if len(universe) > 20 else ''}")

keyword = st.text_input("形态关键词筛选（留空=显示所有命中形态，如：金叉 / 突破 / 背离）", "").strip()


# ───────────────────────── 形态识别（扩充版） ─────────────────────────
def _detect_advanced_patterns(df: pd.DataFrame) -> list:
    """
    在最近窗口内识别趋势类形态：MACD金叉/死叉、均线金叉、KDJ金叉/死叉、底/顶背离。
    返回与 modules.technical.detect_patterns 同构的 dict 列表，便于合并展示。
    """
    pats: list = []
    if df is None or df.empty or len(df) < 35:
        return pats
    try:
        df = df.reset_index(drop=True)  # 确保 idxmin 标签 == iloc 位置，避免错位
        close = df["close"]

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()

        def _latest_cross(a, b, up_name, up_bias, down_name, down_bias, win=6):
            """扫描全部交叉点，仅上报最近 win 日内的「最后一次」交叉方向，避免金叉死叉同时出现。"""
            last = None
            for i in range(1, len(df)):
                if a.iloc[i - 1] <= b.iloc[i - 1] and a.iloc[i] > b.iloc[i]:
                    last = (i, up_name, up_bias)
                elif a.iloc[i - 1] >= b.iloc[i - 1] and a.iloc[i] < b.iloc[i]:
                    last = (i, down_name, down_bias)
            if last and last[0] >= len(df) - win:
                i, name, bias = last
                pats.append({"date": df["date"].iloc[i], "name": name, "bias": bias,
                             "desc": f"{name}：最近一次交叉信号"})
                return True
            return False

        # MACD 金叉/死叉
        _latest_cross(dif, dea, "MACD金叉", "看涨", "MACD死叉", "看跌")

        # 均线金叉 MA5 上穿 MA20
        if "ma5" in df.columns and "ma20" in df.columns:
            _latest_cross(df["ma5"], df["ma20"], "均线金叉", "看涨", "均线死叉", "看跌")

        # KDJ 金叉 / 死叉（9,3,3）
        low9 = df["low"].rolling(9).min()
        high9 = df["high"].rolling(9).max()
        rsv = (close - low9) / (high9 - low9).replace(0, pd.NA) * 100
        rsv = rsv.fillna(50)
        K = rsv.rolling(3).mean()
        D = K.rolling(3).mean()
        _latest_cross(K, D, "KDJ金叉", "看涨", "KDJ死叉", "看跌")

        # 底背离 / 顶背离（价格 vs DIF，近 60 日）
        if len(df) >= 60:
            recent = df.tail(30)
            pl = float(recent["close"].min())
            idx_low = int(recent["close"].idxmin())
            prev = df.iloc[:idx_low]
            if len(prev) >= 20:
                prev_low = float(prev["close"].tail(20).min())
                if pl < prev_low and dif.iloc[-1] > dif.iloc[idx_low]:
                    pats.append({"date": df["date"].iloc[-1], "name": "底背离", "bias": "看涨",
                                 "desc": "价格新低而 MACD 未新低，下跌动能衰竭"})
            ph = float(recent["close"].max())
            idx_high = int(recent["close"].idxmax())
            prev2 = df.iloc[:idx_high]
            if len(prev2) >= 20:
                prev_high = float(prev2["close"].tail(20).max())
                if ph > prev_high and dif.iloc[-1] < dif.iloc[idx_high]:
                    pats.append({"date": df["date"].iloc[-1], "name": "顶背离", "bias": "看跌",
                                 "desc": "价格新高而 MACD 未新高，上涨动能衰竭"})
    except Exception:
        pass
    return pats


def _merge_patterns(df: pd.DataFrame) -> list:
    """合并 K 线形态（来自 technical 模块）与趋势类形态（本页扩充）。"""
    base = technical_full_analysis(df).get("patterns", []) or []
    if isinstance(base, str):
        base = [base]
    adv = _detect_advanced_patterns(df)
    merged = list(base) + list(adv)
    # 按日期倒序去重（同名同偏向只保留一个）
    seen = set()
    out = []
    for p in sorted(merged, key=lambda x: str(x.get("date", "")), reverse=True):
        key = (p.get("name"), p.get("bias"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out[:8]


def _scan_fetch_one(code: str, start: str, end: str):
    """并行抓取单只股票日线：优先后端 K 线接口（带缓存与多源回落），失败回退本地 fetcher。"""
    try:
        recs = api_kline(code, start=start, end=end) or fetcher.get_daily(code, start=start, end=end)
        df = pd.DataFrame(recs) if recs else None
        df = DataCleaner.full_pipeline(df)
        if df is None or df.empty or len(df) < 20:
            return code, None
        return code, df
    except Exception:
        return code, None


if st.button("🚀 开始扫描", type="primary", use_container_width=True) and universe:
    universe = list(dict.fromkeys(universe))[:40]  # 安全上限，避免过慢
    today = datetime.now().date()
    start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    # 并行抓取 K 线（网络 I/O 是瓶颈），再逐只做技术分析
    with st.spinner(f"并行抓取 {len(universe)} 只股票日线…"):
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            fetched = list(ex.map(lambda c: _scan_fetch_one(c, start, end), universe))

    results = []
    prog = st.progress(0, text="分析形态中…")
    for i, (code, df) in enumerate(fetched):
        try:
            if df is None:
                continue
            composite = SignalEngine().price_score(df)
            patterns = _merge_patterns(df)
            pat_overview = "；".join(f"{p.get('name', '?')}·{p.get('bias', '')}" for p in patterns) if patterns else "—"
            if keyword:
                hay = " ".join(str(p.get("name", "")) + " " + str(p.get("bias", "")) for p in patterns)
                if keyword.lower() not in hay.lower():
                    continue
            results.append({
                "代码": code,
                "名称": fetcher.get_stock_name(code) or code,
                "技术评分": int(round(composite)),
                "形态概述": pat_overview,
            })
        except Exception:
            continue
        prog.progress((i + 1) / len(fetched), text=f"分析形态中… {i+1}/{len(fetched)}")
    prog.empty()

    if not results:
        st.info("未命中任何形态（或股票池无可用日线数据，可尝试「手动输入代码」或检查网络）。")
    else:
        st.success(f"✅ 扫描完成，命中 {len(results)} 只")
        results.sort(key=lambda r: r["技术评分"], reverse=True)
        st.dataframe(results, use_container_width=True, height=480)
elif not universe:
    st.info("请选择股票池（或先搜索加入扫描池）后点击「开始扫描」。")
