"""pages/81_自然语言选股.py — 自然语言选股（仿 i问财「零门槛口语选股」，取长补短）。

用户用大白话描述选股意图（"创业板 市盈率<30 且 营收增长>20% 的票"），系统解析为结构化
条件并执行。核心创新点（学 i问财）：
- **零门槛**：不用记指标名/写公式，口语即可。
- **透明**：把"听懂了什么"原样摊开（板块/指标/排序/数量/概念 + 没听懂的词），不像黑盒。
- **诚实**：取数走既有 fetcher/akshare，取不到就如实说明，绝不编造候选池。

执行依赖联网（与 32_智能选股 同源）；本沙箱/离线环境只展示解析结果，不伪造筛选结果。
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from modules.page_utils import render_standard_page
from modules.ui_kit import xc_kpi_grid, info_banner
from modules import nl_screen as ns


_OP_LABEL = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "eq": "="}
_FIELD_CN = {
    "pe": "市盈率", "pb": "市净率", "mktcap": "总市值(亿)", "float_mktcap": "流通市值(亿)",
    "rev_growth": "营收增长(%)", "profit_growth": "净利润增长(%)", "roe": "ROE(%)",
    "gross_margin": "毛利率(%)", "rev_cagr": "营收复合增长(%)", "profit_cagr": "利润复合增长(%)",
}
_BOARD_CN = {
    "cyb": "创业板", "kcb": "科创板", "main": "主板", "bse": "北交所",
    "hs300": "沪深300", "zz500": "中证500", "sz50": "上证50", "sme": "中小板",
}


def _show_spec(spec: ns.QuerySpec) -> None:
    """把解析结果透明展示（i问财式"听懂了什么"）。"""
    chips = []
    for b in spec.boards:
        chips.append(f"板块={_BOARD_CN.get(b, b)}")
    for f in spec.filters:
        chips.append(f"{_FIELD_CN.get(f['field'], f['field'])} {_OP_LABEL.get(f['op'], f['op'])} {f['value']}")
    if spec.sort:
        chips.append(f"排序={_FIELD_CN.get(spec.sort, spec.sort)} {'↓' if spec.sort_dir=='desc' else '↑'}")
    if spec.limit:
        chips.append(f"数量=前{spec.limit}")
    for c in spec.concepts:
        chips.append(f"概念≈{c}")
    if chips:
        st.markdown("**🧠 已理解：** " + "　".join(f"`{c}`" for c in chips))
    else:
        st.caption("未解析出任何结构化条件——试试「创业板 市盈率<30 且 营收增长>20%」")
    if spec.unparsed:
        st.caption("⚠️ 未理解：" + "；".join(spec.unparsed))
    if spec.errors:
        st.caption("⚠️ 解析提示：" + "；".join(spec.errors))


def _fetch_universe(scope: str, custom_codes: str) -> list[dict]:
    """取候选池（真实取数，失败抛异常由上层诚实处理）。小池优先，全市场慢。"""
    codes: list[str] = []
    if scope == "自选股":
        try:
            from modules.session import api_get
            _, body = api_get("/api/watchlist", timeout=10)
            if isinstance(body, dict) and body.get("status") == "ok":
                for it in (body.get("data") or []):
                    codes.append(str(it.get("code", "")))
        except Exception:  # noqa: BLE001
            pass
    elif scope == "自定义":
        codes = [c.strip().zfill(6) for c in custom_codes.replace("，", ",").split(",") if c.strip()]
    # 全市场：走 akshare（联网、慢）
    elif scope == "全市场":
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        codes = [str(c) for c in df["代码"].tolist()]

    if not codes:
        return []
    from modules.fetcher import StockFetcher
    fetcher = StockFetcher()
    recs: list[dict] = []
    for code in codes:
        try:
            fb = fetcher.get_fundamentals(code, use_cache=True) or {}
            recs.append({
                "code": code,
                "name": fb.get("name") or fetcher.get_name_only(code) or code,
                "pe": fb.get("pe_ttm"), "pb": fb.get("pb"),
                "mktcap": fb.get("total_mv"),  # 亿元
                "rev_growth": fb.get("rev_growth"), "profit_growth": fb.get("profit_growth"),
                "roe": fb.get("roe"), "gross_margin": fb.get("gross_margin"),
                "concepts": fb.get("concepts") or [],
            })
        except Exception:  # noqa: BLE001
            continue
    return recs


def main():
    dark = render_standard_page(title="自然语言选股", icon="💬", layout="wide")
    info_banner("用大白话描述选股意图，系统解析为结构化条件并执行（仿 i问财零门槛选股）。"
                "解析结果完全透明展示；取数需联网，取不到会如实说明。", kind="info", icon="💬")

    q = st.text_area(
        "输入选股意图（口语即可）",
        value="创业板 市盈率小于30 且 营收增长大于20% 的票，按营收增长排序，取前10",
        height=80, placeholder="例如：主板 市盈率<25 净资产收益率>15% 且 总市值小于100亿 的票",
    )

    spec = ns.parse_query(q)
    _show_spec(spec)

    scope = st.radio("候选池范围", ["自选股", "自定义", "全市场"], horizontal=True,
                     index=0)
    custom_codes = ""
    if scope == "自定义":
        custom_codes = st.text_input("输入代码（逗号分隔）", placeholder="600519, 300750")

    if st.button("🚀 执行筛选", type="primary"):
        try:
            recs = _fetch_universe(scope, custom_codes)
        except Exception as e:  # noqa: BLE001
            info_banner(f"取数失败（需联网获取基本面/行情）：{type(e).__name__} {e}。"
                        "解析结果如上，联网后重试。", kind="warning", icon="🚫")
            return
        if not recs:
            info_banner("候选池为空或无代码（自选股可能未配置 / 自定义未填）。", kind="warning", icon="🚫")
            return
        result = ns.apply_filters(recs, spec)
        if not result:
            st.warning("⚠️ 按当前条件无匹配（诚实结果：0 只）。可放宽阈值再试。")
            return
        df = pd.DataFrame([{
            "代码": r["code"], "名称": r["name"],
            "市盈率": r.get("pe"), "市净率": r.get("pb"), "总市值(亿)": r.get("mktcap"),
            "营收增长(%)": r.get("rev_growth"), "净利增长(%)": r.get("profit_growth"),
            "ROE(%)": r.get("roe"),
        } for r in result])
        st.success(f"✅ 命中 {len(df)} 只（诚实结果，来自真实取数）")
        st.dataframe(df, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
