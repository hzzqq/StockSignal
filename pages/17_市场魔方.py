"""
市场魔方（全球行情速览）
------------------------
复刻微信小程序「市场魔方助手」的「全球」tab（老板 2026-09-19 指定：
「市场魔方助手是这个微信小程序，不是立体魔方，照着这个小程序开发，原来的就不用了」）。

结构（1:1 复刻截图）：
  🧊 页头        —— 标题 + 更新时间 + 全球/美股暗盘胶囊（render_standard_page 统一骨架）
  💹 全球经济数据 —— 8 卡双列：布伦特原油/黄金/白银/铜/天然气（东财外盘商品实时）
                    + 美元指数（东财外汇，限流则降级）+ 恐慌指数（暂无稳定免费源→unavailable）
                    + 美债长债（bond_zh_us_rate 美国 30 年期国债收益率口径，与小程序 TLT 价格口径不同，如实标注）
  📊 涨跌统计条  —— 8 经济卡 + 24 产业卡涨跌汇总（上涨/下跌/平盘）
  🏭 全球产业数据 —— 24 卡双列（emoji + 板块名 + 涨跌幅），东财概念板块名称匹配，
                    未命中显性标注「未命中」，绝不编造
  🗂 其余 tab    —— 日韩/有色/AI/设置：素材待补占位（等小程序其余 tab 截图）

数据纪律（铁律五）：每路独立 try/except + st.cache_data(300s)；取数失败 → unavailable
显性标注，绝不编造、绝不默认 0。A股红涨绿跌（与小程序语义一致）+ ▲▼ 双编码。
"""
import streamlit as st
from datetime import datetime

from modules.page_utils import render_standard_page
from modules.ui_kit import (
    xc_empty_box,
    xc_error_box,
    xc_info_banner,
    xc_kpi_grid,
    xc_section_header,
    xc_warn_box,
)
from modules.page_guard import safe_fragment, render_data_degradation_banner
from modules.session import trading_autorefresh

dark = render_standard_page(
    title="市场魔方",
    icon="🧊",
    caption="全球行情 · 经济与产业一览（复刻微信小程序「市场魔方助手」全球 tab）。"
            "红涨绿跌 + ▲▼ 双编码；数据缺失显性标注，绝不编造。",
)

st.caption(f"🕒 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · 全球 · 美股暗盘（外盘商品按东财行情时间）")

# ───────────────────── 24 个全球产业卡清单（emoji, 显示名, 候选关键词依次匹配）─────────────────────
# 候选词按「东财概念 → 同花顺概念 → 同花顺行业」池顺序逐一尝试（2026-09-19 同花顺源实测命中 19/24，
# 补齐候选词与行业池后 24/24 可命中；个别仍未命中时如实 unavailable）。
INDUSTRIES = [
    ("🧠", "AI算力", ("AI算力", "算力", "东数西算")),
    ("💡", "CPO", ("CPO",)),
    ("🔬", "半导体", ("半导体",)),
    ("🗄", "存储", ("存储",)),
    ("🖥", "数据中心", ("数据中心", "IDC", "东数西算")),
    ("☁️", "云计算", ("云计算",)),
    ("🚀", "商业航天", ("商业航天", "航天")),
    ("🛰", "卫星", ("卫星",)),
    ("🤖", "机器人", ("机器人",)),
    ("🚗", "自动驾驶", ("自动驾驶", "无人驾驶", "智能驾驶")),
    ("⚛️", "核电", ("核电",)),
    ("⚡", "电网", ("电网",)),
    ("🛡", "军工", ("军工", "国防军工")),
    ("🔋", "新能源", ("新能源",)),
    ("☀️", "光伏", ("光伏",)),
    ("🧯", "锂电池", ("锂电池", "锂电")),
    ("🛢", "石油", ("石油", "油气", "油服")),
    ("🔥", "天然气", ("天然气",)),
    ("🟠", "铜 / 有色", ("有色金属", "工业金属", "铜", "有色")),
    ("🥇", "黄金", ("黄金",)),
    ("🏦", "银行金融", ("银行", "金融科技")),
    ("💊", "生物医药", ("生物医药", "创新药", "医药", "生物疫苗")),
    ("🛒", "消费", ("消费",)),
    ("🧲", "稀土", ("稀土",)),
]

# 经济卡匹配关键词（东财外盘商品名称；主关键词未命中时回退词如实标注口径）
COMMODITY_CODES = ["B", "CL", "GC", "SI", "HG", "NG"]


def _unavailable_card(label: str, reason: str) -> dict:
    """unavailable 诚实降级卡（铁律五：取数不足显性标注，绝不编造）。"""
    return {"label": label, "value": "—", "delta": "暂无数据", "delta_dir": "flat",
            "meta": reason, "_status": "unavailable"}


def _pct_card(label: str, price: float, pct: float, meta: str, with_price: bool = True) -> dict:
    up = pct >= 0
    arrow = "▲" if up else "▼"
    card = {"label": label,
            "value": f"{price:,.2f}" if with_price else f"{pct:+.2f}%",
            "delta": f"{arrow} {pct:+.2f}%",
            "delta_dir": "up" if up else "down",
            "meta": meta, "_status": "ok"}
    if not with_price:
        card["tone"] = "up" if up else "down"
    return card


# ───────────────────── 数据层：每路独立降级 + 缓存 ─────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_foreign_commodity() -> tuple:
    """东财外盘商品实时（含布伦特/金/银/铜/天然气）。返回 (df|None, err|None)。"""
    try:
        import akshare as ak
        df = ak.futures_foreign_commodity_realtime(symbol=COMMODITY_CODES)
        if df is None or df.empty:
            return None, "外盘商品实时接口返回空"
        return df, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=300, show_spinner=False)
def _load_global_futures_backup() -> tuple:
    """备源：东财全球期货商品列表（主源失败时兜底匹配布伦特/天然气等）。"""
    try:
        import akshare as ak
        df = ak.futures_global_spot_em()
        if df is None or df.empty:
            return None, "全球期货商品接口返回空"
        return df, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=600, show_spinner=False)
def _load_forex() -> tuple:
    """东财外汇实时（美元指数）。限流常见 → 轻量重试 2 次；仍失败返回 err（卡转 unavailable）。"""
    import time as _t
    import akshare as ak
    last_err = ""
    for attempt in range(3):
        try:
            df = ak.forex_spot_em()
            if df is not None and not df.empty:
                return df, None
            last_err = "外汇接口返回空"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        if attempt < 2:
            _t.sleep(1.2)
    return None, last_err


@st.cache_data(ttl=1800, show_spinner=False)
def _load_us_bond() -> tuple:
    """中美国债收益率（美国 30 年期口径）。返回 (df|None, err|None)。"""
    try:
        import akshare as ak
        df = ak.bond_zh_us_rate()
        if df is None or df.empty:
            return None, "美债收益率接口返回空"
        return df, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=300, show_spinner=False)
def _load_concept_board() -> tuple:
    """概念板块（24 产业卡匹配源）。降级链：东财概念实时 → 同花顺概念资金流（不同服务器）。

    统一输出列 (板块名称, 涨跌幅)，两源任一可用即返回；全挂返回 (None, err)。
    实测 2026-09-19：东财 push2 端点对运行环境间歇断连（RemoteDisconnected），
    同花顺源稳定（387 概念含涨跌幅）——故两源互为备份。
    """
    import akshare as ak
    try:
        df = ak.stock_board_concept_spot_em()
        if df is not None and not df.empty and "板块名称" in df.columns and "涨跌幅" in df.columns:
            return df[["板块名称", "涨跌幅"]], None
    except Exception:  # noqa: BLE001
        pass
    try:
        df = ak.stock_fund_flow_concept()
        if df is not None and not df.empty and "行业" in df.columns and "行业-涨跌幅" in df.columns:
            out = df.rename(columns={"行业": "板块名称", "行业-涨跌幅": "涨跌幅"})
            return out[["板块名称", "涨跌幅"]], None
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    return None, "概念板块两源均不可用"


@st.cache_data(ttl=300, show_spinner=False)
def _load_industry_backup() -> tuple:
    """同花顺行业资金流（概念池未命中时的行业级补充匹配池，不同服务器）。"""
    try:
        import akshare as ak
        df = ak.stock_fund_flow_industry()
        if df is not None and not df.empty and "行业" in df.columns and "行业-涨跌幅" in df.columns:
            out = df.rename(columns={"行业": "板块名称", "行业-涨跌幅": "涨跌幅"})
            return out[["板块名称", "涨跌幅"]], None
        return None, "同花顺行业源返回空"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def _match_row(df, keyword: str, name_col: str):
    """名称精确/包含匹配第一行；无命中返回 None。"""
    if df is None or df.empty or name_col not in df.columns:
        return None
    names = df[name_col].astype(str).str.strip()
    hit = df[names == keyword]
    if hit.empty:
        hit = df[names.str.contains(keyword, na=False)]
    if hit.empty:
        return None
    return hit.iloc[0]


def _build_econ_cards() -> list:
    """全球经济数据 8 卡（布伦特/黄金/白银/铜/天然气/美元指数/恐慌指数/美债长债）。"""
    cards = []
    fx, fx_err = _load_foreign_commodity()
    if fx is None:
        fx, fx_err = _load_global_futures_backup()
    trade_time = ""
    if fx is not None and "行情时间" in fx.columns:
        try:
            trade_time = str(fx["行情时间"].iloc[0])
        except Exception:  # noqa: BLE001
            trade_time = ""

    def _commodity(label: str, primary: str, fallback: str = "", price_note: str = "") -> dict:
        src_df = fx
        row = _match_row(src_df, primary, "名称")
        note = price_note + (f" · 行情时间 {trade_time}" if trade_time else "")
        if row is None and fallback:
            row = _match_row(src_df, fallback, "名称")
            if row is not None:
                note = f"{fallback} 口径" + (f" · {trade_time}" if trade_time else "")
        if row is None:
            reason = "外盘商品源未命中" + (f"：{fx_err[:60]}" if fx_err else "")
            return _unavailable_card(label, reason)
        try:
            price = float(row["最新价"])
            pct = float(row["涨跌幅"])
        except Exception:  # noqa: BLE001
            return _unavailable_card(label, "外盘商品数值解析失败")
        return _pct_card(label, price, pct, note)

    cards.append(_commodity("布伦特原油", "布伦特", fallback="原油"))
    cards.append(_commodity("黄金盎司", "COMEX黄金"))
    cards.append(_commodity("白银盎司", "COMEX白银"))
    cards.append(_commodity("铜", "COMEX铜"))

    # 恐慌指数：暂无稳定免费源（spec 钉死，诚实降级）
    cards.append(_unavailable_card("恐慌指数", "暂无稳定免费数据源（VIX），接入后补"))

    # 美元强弱：东财外汇（限流常见，失败 unavailable）
    fd, fd_err = _load_forex()
    row = _match_row(fd, "美元指数", "名称")
    if row is None:
        reason = "外汇源未命中" + (f"：{fd_err[:60]}" if fd_err else "")
        cards.append(_unavailable_card("美元强弱", reason))
    else:
        try:
            cards.append(_pct_card("美元强弱", float(row["最新价"]), float(row["涨跌幅"]), "美元指数口径"))
        except Exception:  # noqa: BLE001
            cards.append(_unavailable_card("美元强弱", "外汇数值解析失败"))

    # 美债长债：bond_zh_us_rate 美国 30 年期收益率（口径与小程序 TLT 价格不同，如实标注）
    bd, bd_err = _load_us_bond()
    col = "美国国债收益率30年"
    if bd is not None and col in bd.columns:
        ser = bd[["日期", col]].dropna().tail(2)
        if len(ser) == 2:
            cur, prev = float(ser[col].iloc[-1]), float(ser[col].iloc[-2])
            diff = cur - prev
            up = diff >= 0
            cards.append({
                "label": "美债长债",
                "value": f"{cur:.2f}%",
                "delta": f"{'▲' if up else '▼'} {diff:+.2f}pct",
                "delta_dir": "up" if up else "down",
                "meta": "美国 30 年期国债收益率口径（非 TLT 价格）",
                "_status": "ok",
            })
        else:
            cards.append(_unavailable_card("美债长债", "收益率序列不足两天"))
    else:
        cards.append(_unavailable_card("美债长债", "收益率源缺失" + (f"：{bd_err[:60]}" if bd_err else "")))

    # 天然气（外盘 NG）
    cards.append(_commodity("天然气", "天然气"))
    return cards


def _build_industry_cards() -> list:
    """全球产业数据 24 卡：候选关键词 × 双池（概念/行业）依次匹配；未命中显性 unavailable。"""
    cd, cd_err = _load_concept_board()
    idb, idb_err = _load_industry_backup()
    pools = [df for df in (cd, idb) if df is not None and "板块名称" in df.columns]
    err_hint = "；".join(x for x in (cd_err, idb_err) if x)
    cards = []
    for emoji, label, kws in INDUSTRIES:
        disp = f"{emoji} {label}"
        row = None
        board_name = ""
        for df in pools:
            for kw in kws:
                row = _match_row(df, kw, "板块名称")
                if row is not None:
                    board_name = str(row["板块名称"])
                    break
            if row is not None:
                break
        if row is None:
            reason = "概念/行业池均未命中" + (f"：{err_hint[:60]}" if err_hint else "")
            cards.append(_unavailable_card(disp, reason))
            continue
        try:
            pct = float(row["涨跌幅"])
        except Exception:  # noqa: BLE001
            cards.append(_unavailable_card(disp, "板块数值解析失败"))
            continue
        cards.append(_pct_card(disp, pct, pct, f"匹配板块：{board_name}", with_price=False))
    return cards


def _summary_strip(cards: list) -> None:
    """涨跌统计条（上涨/下跌/平盘；unavailable 不计入）。"""
    ok = [c for c in cards if c.get("_status") == "ok"]
    up = sum(1 for c in ok if c.get("delta_dir") == "up")
    down = sum(1 for c in ok if c.get("delta_dir") == "down")
    flat = len(ok) - up - down
    na = len(cards) - len(ok)
    xc_kpi_grid([
        {"label": "上涨", "value": str(up), "delta": "▲", "delta_dir": "up", "tone": "up"},
        {"label": "下跌", "value": str(down), "delta": "▼", "delta_dir": "down", "tone": "down"},
        {"label": "平盘", "value": str(flat), "delta": "—", "delta_dir": "flat"},
        {"label": "数据缺失", "value": str(na), "delta": "诚实降级", "delta_dir": "flat",
         "meta": "unavailable 不计入涨跌"},
    ], min_col=120)


# ───────────────────── 主渲染 ─────────────────────
@safe_fragment("市场魔方")
def fragment_market_cube():
    trading_autorefresh(key="cube_global_autorefresh")

    tab_global, tab_jp, tab_metal, tab_ai, tab_set = st.tabs(
        ["🌍 全球", "🇯🇵 日韩", "⛏ 有色", "🤖 AI", "⚙️ 设置"])
    for t, name in ((tab_jp, "日韩"), (tab_metal, "有色"), (tab_ai, "AI"), (tab_set, "设置")):
        with t:
            xc_empty_box(f"{name} tab · 素材待补",
                         hint="等「市场魔方助手」其余 tab 截图后按同规格接入（不造假数据）。")

    with tab_global:
        # ---- 全球经济数据 ----
        xc_section_header("全球经济数据")
        try:
            econ = _build_econ_cards()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方经济卡异常: %s", e)
            xc_error_box("全球经济数据加载异常", hint="请稍后刷新重试；单源抖动不影响其余模块。")
            econ = []
        if econ:
            xc_kpi_grid(econ, min_col=170)
        else:
            xc_warn_box("经济卡全部不可用", hint="检查网络后刷新重试。")

        st.divider()
        # ---- 涨跌统计条 ----
        try:
            industry = _build_industry_cards()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方产业卡异常: %s", e)
            xc_error_box("全球产业数据加载异常", hint="请稍后刷新重试。")
            industry = []
        _summary_strip(econ + industry)

        st.divider()
        # ---- 全球产业数据 ----
        xc_section_header("全球产业数据")
        if industry:
            xc_kpi_grid(industry, min_col=170)
            st.caption("产业卡 = 东财概念板块涨跌幅名称匹配；「未命中」为诚实降级，不代表涨跌为 0。")
        else:
            xc_empty_box("产业数据暂不可用", hint="东财概念板块接口暂不可达，稍后刷新。")
        xc_info_banner("数据源：东财外盘商品实时 / 东财外汇 / 中美国债收益率 / 东财概念板块 · 缓存 5 分钟 · "
                       "微信小程序「市场魔方助手」复刻版")

    render_data_degradation_banner()


fragment_market_cube()
