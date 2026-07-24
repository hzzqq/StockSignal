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
import re
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, api_get, api_kline, get_user_setting, save_user_setting, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.technical import full_analysis as technical_full_analysis
from modules.signal import SignalEngine
from modules.search_ui import multi_stock_search_input, stock_search_input
from modules.page_widgets import _empty_info

apply_page_config(page_title="形态选股", page_icon="🧭", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
trading_autorefresh(key="pattern_autorefresh")
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)


def _section_title(text: str, accent: str = "#5b6cff"):
    """渲染带强调色的分区标题胶囊，使交互区与描述文字明显区分。"""
    st.markdown(
        f"<div style='display:inline-block;background:{accent};color:#fff;"
        f"padding:4px 12px;border-radius:8px;font-weight:600;font-size:14px;"
        f"margin-bottom:2px;'>{text}</div>", unsafe_allow_html=True)


# ── 本地样式：区分可点击元素与描述文字 ──
st.markdown("""
<style>
/* 按钮：阴影 + hover 上浮，明确「可点击」 */
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-primary"] {
    box-shadow: 0 1px 3px rgba(0,0,0,0.18);
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}
button[data-testid="stBaseButton-secondary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.22);
}
/* radio 选项：指针 + hover 背景 */
div[data-testid="stRadio"] label,
.stRadio label {
    cursor: pointer;
    padding: 4px 10px;
    border-radius: 6px;
    transition: background 0.12s ease;
}
div[data-testid="stRadio"] label:hover,
.stRadio label:hover {
    background: rgba(91,108,255,0.12);
}
/* 文本/多行输入框：加强边框，提示「可输入」 */
.stTextInput input,
.stTextArea textarea {
    border: 1.5px solid #9aa4ff !important;
    border-radius: 8px !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus {
    border-color: #5b6cff !important;
    box-shadow: 0 0 0 2px rgba(91,108,255,0.18) !important;
}
</style>
""", unsafe_allow_html=True)

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


# ───────────────────────── 股票池来源 ─────────────────────────
with st.container(border=True):
    _section_title("📂 股票池来源")
    st.caption("选择待扫描股票的来源：自选股或手动输入。")
    source = st.radio(
        "股票池来源", ["我的自选股", "手动输入代码"],
        horizontal=True, label_visibility="collapsed",
    )

universe = []
if source == "我的自选股":
    sc, body = api_get("/api/watchlist", timeout=10)
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        universe = [_norm_code(w["stock_code"]) for w in (body.get("data", []) or [])
                     if isinstance(w, dict) and w.get("stock_code")]
        if universe:
            # 名称优先，显示 "名称(代码)"，超过 12 只省略
            def _name_code(c):
                n = fetcher.get_name_only(c)
                return f"{n}({c})" if n else c
            # 并行解析名称（本地 fetcher，线程安全），避免逐只串行拖慢页面加载
            with st.spinner("解析自选股名称…"):
                with _cf.ThreadPoolExecutor(max_workers=4) as ex:
                    labels = list(ex.map(_name_code, universe))
            display = ", ".join(labels[:12])
            st.caption(
                f"✅ 已从自选股加载 **{len(universe)}** 只："
                f"{display}{' …' if len(universe) > 12 else ''}"
            )
        else:
            st.warning("自选股为空，请先到「我的 / 自选股」添加，或切换为「手动输入代码」。")
    else:
        msg = body.get("message", "") if isinstance(body, dict) else ""
        st.error(f"❌ 加载自选股失败（HTTP {sc}）{msg}；可切换为「手动输入代码」继续。")
else:
    # 手动模式：扫描池管理（搜索添加 + 单条删除）+ 批量文本输入，二者合并为扫描池
    if "screener_pool" not in st.session_state:
        # 每个用户下次登录保留扫描池：从后端 settings 恢复（无则空）
        _restored = get_user_setting("screener_pool", [])
        st.session_state["screener_pool"] = list(_restored) if isinstance(_restored, list) else []

    # ── 🧺 扫描池管理 ──
    with st.container(border=True):
        _section_title("🧺 扫描池管理", accent="#f59e0b")
        st.caption("搜索加入股票；点击右侧「删除」可移除单只，点击「清空扫描池」全部清空。")

        c_search, c_add = st.columns([4, 1])
        with c_search:
            picked = stock_search_input(
                label="输入代码 / 名称 / 拼音搜索",
                key="screener_search",
                default="600519",
            )
        with c_add:
            # 让「加入」按钮与搜索输入框纵向对齐
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            if st.button("➕ 加入扫描池", key="screener_add", type="secondary", use_container_width=True):
                if picked and picked not in st.session_state["screener_pool"]:
                    st.session_state["screener_pool"].append(picked)
                    save_user_setting("screener_pool", st.session_state["screener_pool"])
                    st.rerun()

        pool = st.session_state["screener_pool"]
        if pool:
            for code in pool:
                col_code, col_name, col_del = st.columns([0.2, 0.6, 0.2])
                with col_code:
                    st.markdown(f"`{code}`")
                with col_name:
                    st.markdown(fetcher.get_stock_name(code) or code)
                with col_del:
                    _ck = f"screener_del_{code}"
                    if st.session_state.get(_ck):
                        if st.button("确认", key=f"del_cfm_{code}", type="primary", use_container_width=True):
                            st.session_state["screener_pool"].remove(code)
                            save_user_setting("screener_pool", st.session_state["screener_pool"])
                            st.session_state.pop(_ck, None)
                            st.rerun()
                        if st.button("取消", key=f"del_cancel_{code}", use_container_width=True):
                            st.session_state.pop(_ck, None)
                    else:
                        if st.button("删除", key=f"del_{code}", type="secondary", use_container_width=True):
                            st.session_state[_ck] = True
        else:
            st.caption("不知道选什么？一键载入示例大盘蓝筹池，立刻体验形态扫描。")
            _empty_info("扫描池为空，请在上方搜索并「加入扫描池」，或点击下方按钮体验示例。")
            if st.button("📥 载入示例股票池", key="screener_load_example", type="secondary", use_container_width=True):
                _ex = ["600519", "000858", "601318", "600036", "000333"]
                st.session_state["screener_pool"] = _ex
                save_user_setting("screener_pool", _ex)

        c_count, c_clear = st.columns([0.8, 0.2])
        with c_count:
            st.markdown(f"**扫描池共 {len(pool)} 只**")
        with c_clear:
            _ck = "screener_clear_pool"
            if st.session_state.get(_ck):
                if st.button("确认清空", key="screener_clear_cfm", type="primary", use_container_width=True):
                    st.session_state["screener_pool"] = []
                    save_user_setting("screener_pool", [])
                    st.session_state.pop(_ck, None)
                    st.rerun()
                if st.button("取消", key="screener_clear_cancel", use_container_width=True):
                    st.session_state.pop(_ck, None)
            else:
                if st.button("🗑️ 清空扫描池", key="screener_clear", type="secondary", use_container_width=True):
                    st.session_state[_ck] = True

    st.divider()

    # ── 📋 批量输入（真正支持粘贴一长串代码/名称）──
    with st.container(border=True):
        _section_title("📋 批量输入")
        st.caption("在下方文本框粘贴一串股票代码或名称，系统会自动识别并加入扫描池。")
        pasted = st.text_area(
            "粘贴股票代码或名称（逗号/空格/换行分隔）",
            placeholder="例如：000938, 603259, 600584, 600519 或 紫光股份, 贵州茅台",
            key="screener_paste_text",
            height=80,
        )
        # 解析：按逗号/空格/换行/分号/中文逗号分隔，去空去重
        raw_tokens = []
        if pasted:
            for token in re.split(r"[,\s;，；]+", str(pasted)):
                token = token.strip()
                if token:
                    raw_tokens.append(token)
        # 代码/名称 → 统一 6 位代码
        resolved_codes = []
        for tok in raw_tokens:
            code = _norm_code(tok)
            # 若本身是 6 位数字，直接保留
            if code.isdigit() and len(code) == 6:
                resolved_codes.append(code)
            else:
                # 尝试按名称反查代码
                found = fetcher.get_code_by_name(tok)
                if found and str(found).isdigit() and len(str(found)) == 6:
                    resolved_codes.append(_norm_code(found))
                else:
                    # 保留原 token，扫描阶段会自然失败/跳过
                    resolved_codes.append(code)
        resolved_codes = [c for c in resolved_codes if c]

        # 旧的搜索式批量输入保留，作为辅助
        st.caption("或继续使用搜索框逐条/批量添加（与上方扫描池合并去重）。")
        raw = multi_stock_search_input(
            label="或直接选择多只股票（代码/名称，与上方粘贴结果合并去重）",
            key="screener_stocks",
            default="",
        )
        search_codes = [_norm_code(c) for c in (raw or [])]

        # 合并：粘贴 + 搜索 + 扫描池，去重保序
        universe = list(dict.fromkeys(st.session_state["screener_pool"] + resolved_codes + search_codes))

        if resolved_codes or search_codes:
            st.caption(f"已识别 {len(resolved_codes)} 只（来自粘贴） + {len(search_codes)} 只（来自搜索），"
                       f"合并后扫描池共 **{len(universe)}** 只。")

    # 形态筛选 ─────────────────────────
# ───────────────────────── 形态筛选 ─────────────────────────
with st.container(border=True):
    _section_title("🧬 形态筛选", accent="#8b5bff")
    st.caption("留空表示显示所有命中形态；可输入关键词（如：金叉 / 突破 / 背离）筛选。")
    keyword = st.text_input("形态关键词筛选（留空=显示所有命中形态，如：金叉 / 突破 / 背离）", "",
                             help="仅显示名称或偏向含该关键词的形态，如「金叉」「突破」「背离」「看涨」。留空显示全部命中。").strip()


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
        if not isinstance(p, dict):
            # 二级嵌套兜底：technical 模块偶发返回非 dict 元素，跳过避免 .get 崩溃中断整个扫描结果
            continue
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


# ───────────────────────── 扫描结果 ─────────────────────────
with st.container(border=True):
    _section_title("🚀 扫描结果", accent="#10b981")
    st.caption("点击「开始扫描」对当前股票池执行形态识别与技术评分。")

    if st.button("🚀 开始扫描", type="primary", use_container_width=True, disabled=not universe) and universe:
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
                if composite is None or (isinstance(composite, float) and pd.isna(composite)):
                    # 评分缺失（上游未返回有效值）时跳过该股，而非 int(round(None)) 崩溃
                    continue
                patterns = _merge_patterns(df)
                pat_overview = "；".join(f"{p.get('name', '?')}·{p.get('bias', '')}" for p in patterns) if patterns else "—"
                if keyword:
                    hay = " ".join(str(p.get("name", "")) + " " + str(p.get("bias", "")) for p in patterns)
                    if keyword.lower() not in hay.lower():
                        continue
                results.append({
                    "代码": code,
                    "名称": fetcher.get_name_only(code) or code,
                    "技术评分": int(round(composite)),
                    "形态概述": pat_overview,
                })
            except Exception:
                continue
            prog.progress((i + 1) / len(fetched), text=f"分析形态中… {i+1}/{len(fetched)}")
        prog.empty()

        if not results:
            _empty_info("未命中任何形态（或股票池无可用日线数据，可尝试「手动输入代码」、检查网络，或先在上方「扫描池」载入示例股票池）。")
        else:
            st.success(f"✅ 扫描完成，命中 {len(results)} 只")
            results.sort(key=lambda r: r["技术评分"], reverse=True)
            st.dataframe(results, use_container_width=True, height=480)
    elif not universe:
        _empty_info("请选择股票池（或先搜索加入扫描池）后点击「开始扫描」；也可在上方「📥 载入示例股票池」一键体验。")
