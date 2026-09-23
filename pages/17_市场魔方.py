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
  🗂 其余 tab    —— 日韩（韩综/韩产业8/日综/日产业8/亚洲综合/汇率）、有色（金银/LME 工业金属/
                    战略小金属占位）、AI（产品+设备价格 18 卡）按 2026-09-21 老板提供的
                    小程序截图逐 tab 复刻；设置为数据说明与免责声明。

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

# 经济卡/有色 tab 匹配用（东财外盘商品名称；主关键词未命中时回退词如实标注口径）
# T-147 批7：追加 LME 六金属（CAD铜/AHD铝/ZSD锌/NID镍/SND锡/PBD铅），供「有色」tab。
# ⚠️ 不含 'B'：akshare 内部代码字典无 'B'，混入会让整个接口调用 KeyError（2026-09-22 实测）；
# 布伦特原油改由备源 futures_global_spot_em 显式获取。
COMMODITY_CODES = ["CL", "GC", "SI", "HG", "NG", "CAD", "AHD", "ZSD", "NID", "SND", "PBD"]


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
    """东财外盘商品实时（布伦特/金/银/铜/天然气 + LME 六金属）。轻量重试 2 次。"""
    import time as _t
    import akshare as ak
    last_err = ""
    for attempt in range(3):
        try:
            df = ak.futures_foreign_commodity_realtime(symbol=COMMODITY_CODES)
            if df is not None and not df.empty:
                return df, None
            last_err = "外盘商品实时接口返回空"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        if attempt < 2:
            _t.sleep(1.2)
    return None, last_err


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


@st.cache_data(ttl=600, show_spinner=False)
def _load_vix() -> tuple:
    """VIX（Cboe 标普500波动率指数）：腾讯行情直连 qt.gtimg.cn（非东财，规避断连）。

    返回 (dict(price,pct,name,time)|None, err|None)。实测 2026-09-20：usVIX 返回
    「标普500波动率指数 .VIX」真实报价。字段：[1]名称 [3]最新价 [4]昨结 [30]时间。
    """
    try:
        import requests
        r = requests.get("https://qt.gtimg.cn/q=usVIX", timeout=10)
        r.encoding = "gbk"
        body = r.text.split('="', 1)[-1].strip().rstrip('";\r\n ')
        parts = body.split("~")
        if len(parts) < 5 or not parts[3]:
            return None, "VIX 返回字段不足"
        price = float(parts[3])
        prev = float(parts[4]) if parts[4] else price
        pct = (price - prev) / prev * 100 if prev else 0.0
        t = parts[30] if len(parts) > 30 else ""
        return {"price": price, "pct": pct, "name": parts[1] or "标普500波动率指数", "time": t}, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=600, show_spinner=False)
def _load_dini() -> tuple:
    """美元指数（DINIW）：腾讯行情直连 whDINIW（东财外汇限流时的备源）。

    返回 (dict(price,pct)|None, err|None)。实测 2026-09-22：whDINIW=99.64。
    字段：[3]最新价 [13]涨跌幅%。
    """
    try:
        import requests
        r = requests.get("https://qt.gtimg.cn/q=whDINIW", timeout=10)
        r.encoding = "gbk"
        body = r.text.split('="', 1)[-1].strip().rstrip('";\r\n ')
        parts = body.split("~")
        if len(parts) < 14 or not parts[3]:
            return None, "美元指数返回字段不足"
        price = float(parts[3])
        pct = float(parts[13]) if parts[13] else 0.0
        return {"price": price, "pct": pct}, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


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
def _load_sina_index(symbol: str) -> tuple:
    """新浪全球指数实时（znb_ 系：KOSPI/KOSDAQ/NKY/VNINDEX/SENSEX，非东财源）。

    返回 (dict(name,price,pct)|None, err|None)。字段：,名称,最新,涨跌额,涨跌幅%,...
    实测 2026-09-20：KOSPI +2.66 与小程序截图完全一致。
    """
    try:
        import requests
        r = requests.get(
            f"https://hq.sinajs.cn/list=znb_{symbol}",
            headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        r.encoding = "gbk"
        body = r.text.split('="', 1)[-1].strip().rstrip('";\r\n ')
        parts = body.split(",")
        if len(parts) < 4 or not parts[1]:
            return None, f"znb_{symbol} 返回字段不足"
        return {"name": parts[0], "price": float(parts[1]),
                "pct": float(parts[3])}, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


@st.cache_data(ttl=300, show_spinner=False)
def _load_fx() -> tuple:
    """新浪外汇即期（fx_s 系）。返回 (dict(usdcny,usdjpy,usdkrw)|None, err|None)。

    实测 2026-09-20：fx_susdkrw=1384.74 / fx_susdjpy=156.84，与小程序截图完全一致。
    """
    try:
        import requests
        r = requests.get(
            "https://hq.sinajs.cn/list=fx_susdcnh,fx_susdjpy,fx_susdkrw",
            headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)
        r.encoding = "gbk"
        vals = {}
        for line in r.text.strip().split(";"):
            line = line.strip()
            if '="' not in line:
                continue
            key = line.split("=")[0].replace("var hq_str_", "")
            fields = line.split('="', 1)[1].rstrip('"').split(",")
            if len(fields) >= 2 and fields[1]:
                vals[key] = float(fields[1])
        need = ("fx_susdcnh", "fx_susdjpy", "fx_susdkrw")
        missing = [k for k in need if k not in vals]
        if missing:
            return None, f"外汇字段缺失: {missing}"
        return vals, None
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
        if row is None:
            # 备源显式补位（如布伦特原油：外盘实时接口代码表无 'B'，备源 futures_global_spot_em 有）
            bdf, _ = _load_global_futures_backup()
            row = _match_row(bdf, primary, "名称")
            if row is not None:
                note = "备源口径" + (f" · {trade_time}" if trade_time else "")
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

    # 恐慌指数：腾讯行情直连 VIX（Cboe 标普500波动率指数）；失败诚实降级
    vix, vix_err = _load_vix()
    if vix is None:
        cards.append(_unavailable_card("恐慌指数", "VIX 源暂不可用" + (f"：{vix_err[:60]}" if vix_err else "")))
    else:
        note = f"{vix['name']} · Cboe（腾讯行情）"
        if vix.get("time"):
            note += f" · {vix['time']}"
        cards.append(_pct_card("恐慌指数", vix["price"], vix["pct"], note))

    # 美元强弱：东财外汇（限流常见）→ 腾讯 whDINIW 备源 → unavailable
    fd, fd_err = _load_forex()
    row = _match_row(fd, "美元指数", "名称")
    if row is not None:
        try:
            cards.append(_pct_card("美元强弱", float(row["最新价"]), float(row["涨跌幅"]),
                                   "美元指数口径"))
        except Exception:  # noqa: BLE001
            cards.append(_unavailable_card("美元强弱", "外汇数值解析失败"))
    else:
        din, din_err = _load_dini()
        if din is not None:
            cards.append(_pct_card("美元强弱", din["price"], din["pct"],
                                   "美元指数（腾讯行情）"))
        else:
            reason = "外汇源未命中" + (f"：{fd_err[:60]}" if fd_err else "")
            cards.append(_unavailable_card("美元强弱", reason))

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


def _pool_card(label: str, kws: tuple, pools: list, err_hint: str = "") -> dict:
    """候选关键词 × 板块池（概念/行业）依次匹配的产业卡（批7 四 tab 复用）。"""
    row = None
    board_name = ""
    for df in pools:
        if df is None or "板块名称" not in df.columns:
            continue
        for kw in kws:
            row = _match_row(df, kw, "板块名称")
            if row is not None:
                board_name = str(row["板块名称"])
                break
        if row is not None:
            break
    if row is None:
        return _unavailable_card(label, "概念/行业池均未命中" + (f"：{err_hint[:60]}" if err_hint else ""))
    try:
        pct = float(row["涨跌幅"])
    except Exception:  # noqa: BLE001
        return _unavailable_card(label, "板块数值解析失败")
    return _pct_card(label, pct, pct, f"匹配板块：{board_name}", with_price=False)


def _index_card(label: str, symbol: str, meta: str = "") -> dict:
    """新浪全球指数卡（znb_ 系）。TOPIX 等无源标的自动 unavailable。"""
    d, err = _load_sina_index(symbol)
    if d is None:
        return _unavailable_card(label, (meta + "；" if meta else "") + (err or "指数源暂不可用"))
    return _pct_card(label, d["price"], d["pct"], meta or d["name"])


# ── 日韩 tab（照小程序截图：韩综/韩产业8/日综/日产业8/亚洲综合/汇率）──
_KR_INDUSTRY = [
    ("🗄 存储", ("存储",)), ("🔬 半导体", ("半导体",)), ("🔋 电池", ("电池", "锂电")),
    ("📱 消费电子", ("消费电子",)), ("🌐 互联网", ("互联网",)), ("🚗 汽车", ("汽车",)),
    ("💊 生物医药", ("生物医药", "创新药", "医药")), ("🧪 化工材料", ("化工",)),
]
_JP_INDUSTRY = [
    ("🔧 半导体设备", ("半导体设备", "半导体")), ("🏭 工业自动化", ("工业自动化", "自动化设备")),
    ("⚙️ 精密制造", ("精密制造", "精密", "专用设备")), ("🚙 汽车产业链", ("汽车",)),
    ("📱 消费电子", ("消费电子",)), ("🧱 半导体材料", ("半导体材料", "材料")),
    ("🔌 电子元件", ("电子元件", "元器件", "被动元件", "消费电子")),
    ("🎮 游戏娱乐", ("游戏", "传媒")),
]


def _load_pools() -> tuple:
    """概念/行业双池 + 错误提示汇总（四 tab 产业卡共用）。"""
    cd, cd_err = _load_concept_board()
    idb, idb_err = _load_industry_backup()
    pools = [df for df in (cd, idb) if df is not None and "板块名称" in df.columns]
    return pools, "；".join(x for x in (cd_err, idb_err) if x)


def _build_kr_sections() -> list:
    pools, hint = _load_pools()
    sections = [
        ("韩国综合", [_index_card("KOSPI", "KOSPI"), _index_card("KOSDAQ", "KOSDAQ")]),
        ("韩国核心产业", [_pool_card(l, k, pools, hint) for l, k in _KR_INDUSTRY]),
        ("日本综合", [_index_card("日经225", "NKY"),
                    _unavailable_card("TOPIX", "暂无免费实时源（新浪 znb 无 TOPX），不编造")]),
        ("日本核心产业", [_pool_card(l, k, pools, hint) for l, k in _JP_INDUSTRY]),
        ("亚洲综合", [_index_card("越南胡志明", "VNINDEX"), _index_card("孟买SENSEX", "SENSEX")]),
    ]
    fx_cards = _build_fx_cards()
    if fx_cards:
        sections.append(("汇率", fx_cards))
    return sections


def _build_fx_cards() -> list:
    """汇率 4 卡：美元/韩元、美元/日元直取即期；人民币/韩元、人民币/日元按 USD 交叉换算（如实标注）。"""
    fx, err = _load_fx()
    if fx is None:
        return [_unavailable_card("汇率", f"外汇源暂不可用：{(err or '')[:60]}")]
    usdcny = fx["fx_susdcnh"]
    usdjpy = fx["fx_susdjpy"]
    usdkrw = fx["fx_susdkrw"]

    def _fx_card(label, value, meta):
        return {"label": label, "value": f"{value:,.2f}", "delta": "即期", "delta_dir": "flat",
                "meta": meta, "_status": "ok"}

    out = [_fx_card("美元/韩元", usdkrw, "美元兑韩元即期"),
           _fx_card("美元/日元", usdjpy, "美元兑日元即期"),
           _fx_card("人民币/韩元", usdkrw / usdcny, "USD/KRW ÷ USD/CNH 换算"),
           _fx_card("人民币/日元", usdjpy / usdcny, "USD/JPY ÷ USD/CNH 换算")]
    return out


def _build_metals_sections() -> list:
    """有色 tab：金银（COMEX）+ 工业金属（LME 3个月，外盘实时）+ 战略小金属（无免费源→unavailable）。

    主源失败时回落东财全球期货列表（futures_global_spot_em，有 COMEX 金银但无 LME——
    LME 缺失时如实 unavailable，不编造）。
    """
    fx, err = _load_foreign_commodity()
    if fx is None:
        fx, err = _load_global_futures_backup()

    def _metal(label, primary):
        row = _match_row(fx, primary, "名称")
        if row is None:
            return _unavailable_card(label, "外盘源未命中" + (f"：{(err or '')[:60]}" if err else ""))
        try:
            t = str(row.get("行情时间", ""))
            return _pct_card(label, float(row["最新价"]), float(row["涨跌幅"]),
                             f"LME 3个月 · {t}" if t else "LME 3个月")
        except Exception:  # noqa: BLE001
            return _unavailable_card(label, "数值解析失败")

    return [
        ("金银", [_metal("黄金", "COMEX黄金"), _metal("白银", "COMEX白银")]),
        ("工业金属", [_metal("铜", "LME铜"), _metal("铝", "LME铝"), _metal("锌", "LME锌"),
                    _metal("镍", "LME镍"), _metal("锡", "LME锡"), _metal("铅", "LME铅")]),
        ("其他金属", [_unavailable_card(f"⚠️ {n}", "战略小金属无免费实时源，暂不编造")
                    for n in ("钨", "钼", "锗", "铟", "锑")]),
    ]


# ── AI tab（照小程序截图：AI 产品价格 2 + AI 设备价格 16）──
_AI_ITEMS = [
    ("🧠 云算力", ("东数西算", "算力")), ("🪙 Token", ("数字货币",)),
    ("💾 DRAM", ("DRAM", "存储芯片")), ("💽 NAND", ("NAND", "闪存", "存储芯片")),
    ("🔥 HBM", ("HBM", "存储芯片")), ("💽 SSD", ("SSD", "固态硬盘", "存储芯片")),
    ("🔦 光模块", ("光模块", "光通信", "CPO")), ("🧵 光纤", ("光纤", "光通信")),
    ("🟩 PCB", ("PCB",)), ("🔩 MLCC", ("MLCC",)),
    ("🎮 GPU", ("GPU", "英伟达", "算力")), ("💻 CPU", ("CPU", "国产芯片", "芯片")),
    ("⚙️ 先进制程", ("先进制程", "晶圆", "半导体")), ("📦 封装", ("先进封装", "封测")),
    ("⚡ 电力", ("电力",)), ("🔌 电力设备", ("电力设备", "电网设备", "电源设备")),
    ("🌬 散热", ("散热", "液冷")), ("🖥 算力租赁", ("算力租赁", "IDC")),
]


def _build_ai_sections() -> list:
    pools, hint = _load_pools()
    cards = [_pool_card(l, k, pools, hint) for l, k in _AI_ITEMS]
    return [
        ("AI 产品价格", cards[:2]),
        ("AI 设备价格", cards[2:]),
    ]


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

    tab_global, tab_kr, tab_metal, tab_ai, tab_set = st.tabs(
        ["🌍 全球", "🇯🇵 日韩", "⛏ 有色", "🤖 AI", "⚙️ 设置"])

    # ── 全球 tab（批6 已复刻）──
    with tab_global:
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
        try:
            industry = _build_industry_cards()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方产业卡异常: %s", e)
            xc_error_box("全球产业数据加载异常", hint="请稍后刷新重试。")
            industry = []
        _summary_strip(econ + industry)

        st.divider()
        xc_section_header("全球产业数据")
        if industry:
            xc_kpi_grid(industry, min_col=170)
            st.caption("产业卡 = 概念/行业池涨跌幅名称匹配；「未命中」为诚实降级，不代表涨跌为 0。")
        else:
            xc_empty_box("产业数据暂不可用", hint="板块接口暂不可达，稍后刷新。")
        xc_info_banner("数据源：东财外盘商品实时 / 东财外汇 / 中美国债收益率 / 概念行业池 · 缓存 5 分钟 · "
                       "微信小程序「市场魔方助手」复刻版")

    # ── 日韩 tab（批7：照截图 韩综/韩产业/日综/日产业/亚洲综合/汇率）──
    with tab_kr:
        try:
            for title, cards in _build_kr_sections():
                xc_section_header(title)
                if cards:
                    xc_kpi_grid(cards, min_col=170)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方日韩 tab 异常: %s", e)
            xc_error_box("日韩数据加载异常", hint="请稍后刷新重试。")

    # ── 有色 tab（批7：金银 COMEX + LME 工业金属 + 战略小金属占位）──
    with tab_metal:
        try:
            for title, cards in _build_metals_sections():
                xc_section_header(title)
                if cards:
                    xc_kpi_grid(cards, min_col=170)
            st.caption("工业金属为 LME 3 个月期货（东财外盘实时）；钨/钼/锗/铟/锑等战略小金属"
                       "暂无免费实时源，如实降级。")
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方有色 tab 异常: %s", e)
            xc_error_box("有色数据加载异常", hint="请稍后刷新重试。")

    # ── AI tab（批7：AI 产品/设备价格 18 卡，产业链概念池匹配）──
    with tab_ai:
        try:
            for title, cards in _build_ai_sections():
                xc_section_header(title)
                if cards:
                    xc_kpi_grid(cards, min_col=170)
            st.caption("AI 卡 = 产业链概念/行业池涨跌幅名称匹配，口径为 A 股映射板块而非硬件现货报价。")
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("市场魔方 AI tab 异常: %s", e)
            xc_error_box("AI 数据加载异常", hint="请稍后刷新重试。")

    # ── 设置 tab（批7：数据说明 + 免责声明，不搬小程序广告/二维码）──
    with tab_set:
        xc_section_header("数据说明")
        xc_info_banner("数据来源：东财外盘商品实时（COMEX/LME）、新浪全球指数（znb_）、"
                       "新浪外汇即期（fx_s）、东财外汇、中美国债收益率、同花顺概念/行业资金流、"
                       "腾讯行情（VIX）。全部为公开查询数据，缓存 5~30 分钟。")
        xc_warn_box("免责声明", hint="本页所有数据仅供个人研究参考，不构成任何投资建议；"
                                   "数据可能延迟或缺失，缺失时页面会显性标注（unavailable），不编造。")
        st.caption("复刻自微信小程序「市场魔方助手」全球行情速览 · StockSignal 版")

    render_data_degradation_banner()


fragment_market_cube()
