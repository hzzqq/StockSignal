import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import concurrent.futures
from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, safe_switch_page, api_get
from modules.fetcher import StockFetcher
fetcher = StockFetcher()
from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.fundflow import get_individual_fund_flow
from modules.portfolio import PortfolioManager
from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info

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

# 信号灯风险配色（独立于 A股 红涨绿跌）：机会=绿、中性=琥珀、风险=红
_PRIORITY_COLOR = {"HIGH": "#1aa260", "WATCH": "#f5a623", "ATTENTION": "#ee2a2a"}
_PRIORITY_EMOJI = {"HIGH": "🟢", "WATCH": "🟡", "ATTENTION": "🔴"}


# ─────────────────────────── 数据准备 ───────────────────────────
def build_stock_list(scope: str) -> dict:
    """返回 {code: name}，按 code 去重。名称强制解析，不信任后端可能返回的代码占位。"""
    codes: dict = {}

    def _coerce_name(code: str, raw_name) -> str:
        """优先使用后端/持仓返回的真实名称；若为空或与代码相同，则强制走 fetcher 解析。"""
        code = str(code).strip().zfill(6)
        if raw_name and str(raw_name).strip() and str(raw_name).strip() != code:
            return str(raw_name).strip()
        try:
            return fetcher.get_name_only(code)
        except Exception:
            return code

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
                    raw_name = it.get("stock_name") or it.get("name")
                    if code:
                        codes[str(code)] = _coerce_name(str(code), raw_name)
    except Exception:
        pass

    try:
        if scope in ("组合持仓", "全部"):
            pm = PortfolioManager()
            df = pm.get_positions()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = row.get("ticker")
                    raw_name = row.get("name")
                    if code:
                        codes[str(code)] = _coerce_name(str(code), raw_name)
    except Exception:
        pass

    return codes


# ─────────────────────── 多维打分（0-100，越高越健康） ───────────────────────
def _tech_score(analysis) -> float:
    """技术面：趋势(0.4)+动量(0.3)+量能(0.3) 加权。"""
    if not isinstance(analysis, dict):
        return None
    t = (analysis.get("trend") or {}).get("trend_score")
    m = (analysis.get("momentum") or {}).get("momentum_score")
    v = (analysis.get("volume") or {}).get("volume_price_score")
    num = den = 0.0
    for val, w in ((t, 0.4), (m, 0.3), (v, 0.3)):
        if isinstance(val, (int, float)):
            num += float(val) * w
            den += w
    return round(num / den, 1) if den else None


def _valuation_score(pe, pb, dv) -> float:
    """估值：PE 越低越好(0.55)+PB(0.25)+股息率(0.20)。全缺失返 None。"""
    parts = []
    if isinstance(pe, (int, float)) and pe > 0:
        s = 90 if pe <= 15 else 75 if pe <= 25 else 60 if pe <= 40 else 45 if pe <= 60 else 30 if pe <= 100 else 20
        parts.append((s, 0.55))
    if isinstance(pb, (int, float)) and pb > 0:
        s = 90 if pb <= 1.5 else 72 if pb <= 3 else 55 if pb <= 5 else 40 if pb <= 8 else 25
        parts.append((s, 0.25))
    if isinstance(dv, (int, float)) and dv >= 0:
        s = 95 if dv >= 5 else 80 if dv >= 3 else 65 if dv >= 1.5 else 55 if dv > 0 else 45
        parts.append((s, 0.20))
    if not parts:
        return None
    num = sum(s * w for s, w in parts)
    den = sum(w for _, w in parts)
    return round(num / den, 1)


def _finance_score(roe, rev_yoy, profit_yoy) -> float:
    """财务健康：ROE(0.4)+营收同比(0.3)+净利同比(0.3)。全缺失返 None。"""
    parts = []
    if isinstance(roe, (int, float)):
        s = 95 if roe >= 20 else 85 if roe >= 15 else 70 if roe >= 10 else 55 if roe >= 5 else 40 if roe >= 0 else 20
        parts.append((s, 0.4))
    for v, w in ((rev_yoy, 0.3), (profit_yoy, 0.3)):
        if isinstance(v, (int, float)):
            s = 90 if v >= 30 else 78 if v >= 15 else 65 if v >= 5 else 52 if v >= 0 else 38 if v >= -10 else 22
            parts.append((s, w))
    if not parts:
        return None
    num = sum(s * w for s, w in parts)
    den = sum(w for _, w in parts)
    return round(num / den, 1)


def _fund_score(main_net) -> float:
    """资金面：主力净流入(元)。缺失返 None。"""
    if not isinstance(main_net, (int, float)):
        return None
    yi = float(main_net) / 1e8
    if yi >= 3:
        return 90.0
    if yi >= 1:
        return 78.0
    if yi >= 0.2:
        return 65.0
    if yi > -0.2:
        return 50.0
    if yi >= -1:
        return 38.0
    if yi >= -3:
        return 25.0
    return 12.0


_DIM_WEIGHTS = {"技术面": 0.30, "资金面": 0.25, "财务健康": 0.25, "估值": 0.20}


def _composite(dims: dict) -> float:
    """综合体检分：对已获取的维度按权重归一化。全缺失返 None。"""
    num = den = 0.0
    for k, w in _DIM_WEIGHTS.items():
        v = dims.get(k)
        if isinstance(v, (int, float)):
            num += float(v) * w
            den += w
    return round(num / den, 1) if den else None


def scan_one(code: str, name):
    """单只股票体检，返回 entry dict（含多维打分）。"""
    entry = {"code": str(code), "name": name, "patterns": [], "main_net": None,
             "dims": {}, "composite": None, "pe": None, "roe": None,
             "rev_yoy": None, "error": None}
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
        entry["dims"]["技术面"] = _tech_score(analysis)
    except Exception as e:
        entry["error"] = f"分析失败: {e}"

    # 资金面
    try:
        ff = get_individual_fund_flow(code)
        if isinstance(ff, dict):
            entry["main_net"] = ff.get("main_net")
            entry["dims"]["资金面"] = _fund_score(ff.get("main_net"))
    except Exception:
        pass

    # 估值（PE 来自 fetcher；PB/股息率 best-effort 补充）
    pe = pb = dv = None
    try:
        fd = StockFetcher().get_fundamentals(code)
        if isinstance(fd, dict):
            pe = fd.get("pe_ttm")
            entry["pe"] = pe
    except Exception:
        pass
    try:
        import akshare as ak
        for ind, setter in (("市净率", "pb"), ("股息率TTM", "dv")):
            try:
                vdf = ak.stock_zh_valuation_baidu(symbol=str(code).zfill(6),
                                                  indicator=ind, period="近一年")
                if vdf is not None and not vdf.empty:
                    val = float(str(vdf.iloc[-1].get("value")).replace(",", ""))
                    if setter == "pb":
                        pb = val
                    else:
                        dv = val
            except Exception:
                pass
    except Exception:
        pass
    vs = _valuation_score(pe, pb, dv)
    if vs is not None:
        entry["dims"]["估值"] = vs

    # 财务健康（同花顺财务指标 best-effort）
    try:
        import akshare as ak
        fdf = ak.stock_financial_analysis_indicator(
            symbol=str(code).zfill(6), start_year=str(datetime.now().year - 1))
        if fdf is not None and not fdf.empty:
            last = fdf.iloc[-1]

            def _pick(*names):
                for n in names:
                    for col in fdf.columns:
                        if n.replace(" ", "") in col.replace(" ", ""):
                            try:
                                return float(str(last[col]).replace(",", ""))
                            except Exception:
                                return None
                return None

            roe = _pick("净资产收益率", "ROE")
            rev = _pick("营业收入同比增长率", "营收同比")
            prof = _pick("净利润同比增长率", "净利润同比")
            entry["roe"] = roe
            entry["rev_yoy"] = rev
            fs = _finance_score(roe, rev, prof)
            if fs is not None:
                entry["dims"]["财务健康"] = fs
    except Exception:
        pass

    entry["composite"] = _composite(entry["dims"])
    return entry


def classify(patterns, main_net, composite=None):
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

    # 有综合分时以其为主，形态/资金作为增强信号
    if isinstance(composite, (int, float)):
        if composite >= 68 or has_bull:
            return "HIGH", names, mn
        if composite < 45 or has_bear:
            return "ATTENTION", names, mn
        return "WATCH", names, mn

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
        prio, names, mn = classify(e.get("patterns", []), e.get("main_net"),
                                   e.get("composite"))
        results.append({
            "code": e["code"],
            "name": e["name"],
            "priority": prio,
            "names": names,
            "main_net": mn,
            "dims": e.get("dims", {}),
            "composite": e.get("composite"),
            "pe": e.get("pe"),
            "roe": e.get("roe"),
            "rev_yoy": e.get("rev_yoy"),
        })

    # 综合分优先降序，其次按优先级
    def _sort_key(r):
        comp = r.get("composite")
        comp_rank = -comp if isinstance(comp, (int, float)) else 999
        return (PRIORITY_RANK.get(r["priority"], 9), comp_rank, r["code"])

    results.sort(key=_sort_key)
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

# 新手引导：体检结果怎么看（#545-17 风险等级颜色统一 + 新手文案）
with st.expander("ℹ️ 怎么看体检结果？", expanded=False):
    st.markdown(
        "体检按 **技术面 30% · 资金面 25% · 财务健康 25% · 估值 20%** 加权得出综合分，"
        "再结合技术形态与主力资金给出三档优先级：\n"
        f"- {_PRIORITY_EMOJI['HIGH']} **高优先级（绿）**：综合分 ≥ 68 或出现看涨形态 / 主力净流入，是值得重点跟踪的机会标的。\n"
        f"- {_PRIORITY_EMOJI['WATCH']} **关注（琥珀）**：信号中性，综合分在 45–68 之间，列入观察即可。\n"
        f"- {_PRIORITY_EMOJI['ATTENTION']} **警惕（红）**：综合分 < 45 或出现看跌 / 顶背离等风险信号，注意规避或严格控制仓位。\n\n"
        "维度评分条与综合分遵循「绿=好、琥珀=中性、红=偏弱」的**健康语义**，与行情的"
        "「红涨绿跌」配色相互独立，切勿混淆。"
    )


# ─────────────────────────── 结果板（fragment，独立刷新） ───────────────────────────
@safe_fragment("体检结果")
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
        _empty_info("尚未体检，点击上方「🚀 开始体检」开始扫描。")
        return

    if results == []:
        _empty_info("当前范围没有可扫描的股票。先去「形态选股」挑选一些标的加入跟踪吧。")
        if st.button("➡️ 去形态选股", key="goto_shape_empty"):
            safe_switch_page("pages/B_形态选股.py")
        return

    scan_time = st.session_state.get("scan_time", 0.0)
    scan_count = st.session_state.get("scan_count", len(results))
    st.caption(f"共扫描 {scan_count} 只标的，耗时 {scan_time:.1f}s ｜ 综合分 = "
               "技术面 30% · 资金面 25% · 财务健康 25% · 估值 20%")

    # 概览指标：健康 / 关注 / 警惕 数量 + 平均综合分
    comps = [r["composite"] for r in results if isinstance(r.get("composite"), (int, float))]
    avg_comp = round(sum(comps) / len(comps), 1) if comps else None
    n_high = sum(1 for r in results if r["priority"] == "HIGH")
    n_watch = sum(1 for r in results if r["priority"] == "WATCH")
    n_att = sum(1 for r in results if r["priority"] == "ATTENTION")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{_PRIORITY_EMOJI['HIGH']} 高优先级", n_high)
    m2.metric(f"{_PRIORITY_EMOJI['WATCH']} 关注", n_watch)
    m3.metric(f"{_PRIORITY_EMOJI['ATTENTION']} 警惕", n_att)
    m4.metric("平均综合分", f"{avg_comp}" if avg_comp is not None else "—")

    def _fmt_score(v):
        return f"{v:.0f}" if isinstance(v, (int, float)) else "—"

    # 表格（可排序，含多维打分）
    rows = []
    for r in results:
        mn = r["main_net"]
        if mn is None:
            flow_txt = "—"
        else:
            s = fmt_money(mn)
            flow_txt = (f"净流入 {s}" if (mn and mn > 0) else
                        f"净流出 {s}" if (mn and mn < 0) else "持平")
        dims = r.get("dims", {})
        rows.append({
            "代码": r["code"],
            "名称": r["name"],
            "综合分": r.get("composite") if isinstance(r.get("composite"), (int, float)) else None,
            "优先级": PRIORITY_LABEL[r["priority"]],
            "技术面": dims.get("技术面"),
            "资金面": dims.get("资金面"),
            "财务健康": dims.get("财务健康"),
            "估值": dims.get("估值"),
            "主力净流入": flow_txt,
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={
            "综合分": st.column_config.ProgressColumn(
                "综合分", min_value=0, max_value=100, format="%.0f"),
        },
    )

    # 卡片式待办列表（按优先级着色 + 多维打分条）
    st.markdown("### 📋 优先待办清单")

    def _dim_bar(label, v):
        """单个维度的迷你评分条。"""
        if not isinstance(v, (int, float)):
            return (f'<div style="flex:1 1 0;min-width:110px;">'
                    f'<div style="font-size:11px;color:#999;">{label} —</div>'
                    f'<div style="height:6px;border-radius:3px;background:rgba(128,128,128,0.18);"></div></div>')
        c = _PRIORITY_COLOR["HIGH"] if v >= 65 else WATCH_COLOR if v >= 45 else _PRIORITY_COLOR["ATTENTION"]
        pct = max(0, min(100, v))
        return (f'<div style="flex:1 1 0;min-width:110px;">'
                f'<div style="font-size:11px;color:#888;">{label} '
                f'<b style="color:{c};">{v:.0f}</b></div>'
                f'<div style="height:6px;border-radius:3px;background:rgba(128,128,128,0.18);">'
                f'<div style="width:{pct}%;height:6px;border-radius:3px;background:{c};"></div></div></div>')

    for r in results:
        color = _PRIORITY_COLOR[r["priority"]]
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
        comp = r.get("composite")
        comp_html = ""
        if isinstance(comp, (int, float)):
            cc = _PRIORITY_COLOR["HIGH"] if comp >= 65 else WATCH_COLOR if comp >= 45 else _PRIORITY_COLOR["ATTENTION"]
            comp_html = (f'<span style="background:{cc};color:#fff;padding:2px 10px;'
                         f'border-radius:12px;font-size:12px;font-weight:700;margin-right:6px;">'
                         f'综合 {comp:.0f}</span>')
        dims = r.get("dims", {})
        bars = "".join(_dim_bar(k, dims.get(k)) for k in ("技术面", "资金面", "财务健康", "估值"))
        card = f"""
        <div style="border-left:5px solid {color};border-radius:8px;
                    padding:10px 14px;margin:8px 0;background:rgba(128,128,128,0.08);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:700;font-size:15px;">{r['code']} {r['name']}</span>
            <span>{comp_html}<span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;">{PRIORITY_LABEL[r['priority']]}</span></span>
          </div>
          <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;">{bars}</div>
          <div style="margin-top:8px;font-size:13px;color:#888;">
            {pat_html}{(' ｜ ' if pat_html and flow_html else '') + flow_html if (pat_html or flow_html) else '无明显信号'}
          </div>
        </div>
        """
        st.markdown(card, unsafe_allow_html=True)

        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("跳转", key=f"jump_{r['code']}"):
                safe_switch_page("pages/个股研究.py")
        with b2:
            if st.button("看技术形态", key=f"shape_{r['code']}"):
                safe_switch_page("pages/B_形态选股.py")
        with b3:
            if st.button("看资金", key=f"flow_{r['code']}"):
                safe_switch_page("pages/F_资金流向.py")


result_board()
