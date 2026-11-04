"""pages/81_自然语言选股.py — 自然语言选股（仿 i问财「零门槛口语选股」，取长补短）。

用户用大白话描述选股意图（"创业板 市盈率<30 且 营收增长>20% 的票"），系统解析为结构化
条件并执行。核心创新点（学 i问财）：
- **零门槛**：不用记指标名/写公式，口语即可。
- **透明**：把"听懂了什么"原样摊开（板块/指标/排序/数量/概念 + 没听懂的词），不像黑盒。
- **诚实**：取数走既有 fetcher/akshare，取不到就如实说明，绝不编造候选池。

执行依赖联网（与 32_智能选股 同源）；本沙箱/离线环境只展示解析结果，不伪造筛选结果。
"""
from __future__ import annotations  # noqa: I001

import logging
import streamlit as st

from modules.page_utils import render_standard_page
from modules.ui_kit import xc_info_banner, xc_bento_kpi
from modules import nl_screen as ns
from modules.risk_gate import scan_and_gate  # T-245 二道闸

logger = logging.getLogger(__name__)


_OP_LABEL = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "eq": "="}
_FIELD_CN = {
    "pe": "市盈率", "pb": "市净率", "mktcap": "总市值(亿)", "float_mktcap": "流通市值(亿)",
    "rev_growth": "营收增长(%)", "profit_growth": "净利润增长(%)", "roe": "ROE(%)",
    "gross_margin": "毛利率(%)", "rev_cagr": "营收复合增长(%)", "profit_cagr": "利润复合增长(%)",
    "chg_pct": "涨跌幅(%)", "turnover": "换手率(%)", "volume_ratio": "量比", "amplitude": "振幅(%)",
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
    for b in spec.exclude_boards:
        chips.append(f"剔除板块={_BOARD_CN.get(b, b)}")
    for c in spec.exclude_concepts:
        chips.append(f"剔除≈{c}")
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
        except Exception as e:  # noqa: BLE001
            logger.warning("[81] 自选股池取数失败，按空池降级: %s", e, exc_info=True)
    elif scope == "自定义":
        codes = [c.strip().zfill(6) for c in custom_codes.replace("，", ",").split(",") if c.strip()]
    # 全市场：走 akshare（联网、慢）
    elif scope == "全市场":
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        codes = [str(c) for c in df["代码"].tolist()]

    if not codes:
        return []
    # 技术面/规模维度：东方财富全市场行情快照（一次调用，覆盖全候选池场景）
    # 仅取真实字段：涨跌幅/换手率/量比/振幅 + 流通市值（补足基本面缺的 float_mktcap）。
    # 取数失败→spot_map 空，技术面维度诚实降级为 None（过滤条件不会假通过）。
    spot_map: dict = {}
    try:
        import akshare as ak
        _spot = ak.stock_zh_a_spot_em()
        for _, _row in _spot.iterrows():
            spot_map[str(_row.get("代码"))] = _row
    except Exception as e:  # noqa: BLE001
        logger.warning("[81] 行情快照取数失败，技术面维度降级: %s", e)

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            # ui_audit_exempt: 输入类型/取值非法时返回空，防御性契约（非数据缺失）
            return None

    from modules.fetcher import StockFetcher
    fetcher = StockFetcher()
    recs: list[dict] = []
    for code in codes:
        try:
            fb = fetcher.get_fundamentals(code, use_cache=True) or {}
            rec = {
                "code": code,
                "name": fb.get("name") or fetcher.get_name_only(code) or code,
                "pe": fb.get("pe_ttm"), "pb": fb.get("pb"),
                "mktcap": fb.get("total_mv"),  # 亿元
                "float_mktcap": fb.get("float_mv"),
                "rev_growth": fb.get("rev_growth"), "profit_growth": fb.get("profit_growth"),
                "roe": fb.get("roe"), "gross_margin": fb.get("gross_margin"),
                "concepts": fb.get("concepts") or [],
            }
            sp = spot_map.get(code)
            if sp is not None:
                rec["chg_pct"] = _num(sp.get("涨跌幅"))
                rec["turnover"] = _num(sp.get("换手率"))
                rec["volume_ratio"] = _num(sp.get("量比"))
                rec["amplitude"] = _num(sp.get("振幅"))
                if rec["float_mktcap"] is None:
                    rec["float_mktcap"] = _num(sp.get("流通市值"))
            recs.append(rec)
        except Exception:  # noqa: BLE001
            continue
    return recs


def main():
    import pandas as pd
    dark = render_standard_page(title="自然语言选股", icon="💬", layout="wide")  # noqa: F841
    xc_info_banner("用大白话描述选股意图，系统解析为结构化条件并执行（仿 i问财零门槛选股）。"
                "解析结果完全透明展示；取数需联网，取不到会如实说明。", kind="info", icon="💬")

    # 历史方案（保存/复用）：只存原始查询文本，复用时重新 parse——spec 永远来自真实解析
    _presets = ns.load_query_presets(20)
    _pick = st.selectbox(
        "📂 历史方案（选择即填充）", ["（不使用）"] + [p["query"] for p in _presets],
        key="nl_preset_pick", index=0, disabled=not _presets,
        help="「💾 保存为方案」把当前查询存到本机 data/nl_presets.json（跨会话、按文本去重、上限 50）",
    )
    if _pick != "（不使用）" and st.session_state.get("nl_preset_applied") != _pick:
        st.session_state["nl_query"] = _pick
        st.session_state["nl_preset_applied"] = _pick

    q = st.text_area(
        "输入选股意图（口语即可）",
        value="创业板 市盈率小于30 且 营收增长大于20% 的票，按营收增长排序，取前10",
        height=80, placeholder="例如：主板 市盈率<25 净资产收益率>15% 且 总市值小于100亿 的票",
        key="nl_query",
    )

    _p1, _p2 = st.columns([1, 4])
    with _p1:
        if st.button("💾 保存为方案", key="nl_preset_save", disabled=not q.strip(),
                     help="把当前查询文本存为方案（按文本去重，同文换位置不重复）"):
            if ns.save_query_preset(q):
                st.toast("方案已保存")
            else:
                st.warning("方案保存失败（检查 data 目录权限）")
    with _p2:
        if _presets:
            _cfm = st.session_state.get("nl_preset_clear_cfm", False)
            if not _cfm:
                st.button("🗑️ 清空全部方案", key="nl_preset_clear",
                          on_click=lambda: st.session_state.__setitem__("nl_preset_clear_cfm", True),
                          help="⚠️ 点击后进入确认态（不可恢复的操作）")
            else:
                st.warning("⚠️ 即将清空全部方案（不可恢复）：", icon="⚠️")
                _c1, _c2 = st.columns(2)
                if _c1.button("确认清空", key="nl_preset_clear_yes", type="primary"):
                    _n = ns.clear_query_presets()
                    st.session_state.nl_preset_clear_cfm = False
                    st.toast(f"已清空 {_n} 条方案" if _n >= 0 else "清空失败（检查文件权限）")
                    st.rerun()
                if _c2.button("取消", key="nl_preset_clear_no"):
                    st.session_state.nl_preset_clear_cfm = False
                    st.rerun()

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
            xc_info_banner(f"取数失败（需联网获取基本面/行情）：{type(e).__name__} {e}。"
                        "解析结果如上，联网后重试。", kind="warning", icon="🚫")
            return
        if not recs:
            xc_info_banner("候选池为空或无代码（自选股可能未配置 / 自定义未填）。", kind="warning", icon="🚫")
            return
        result = ns.apply_filters(recs, spec)
        # T-245 二道闸：渲染前统一排雷
        _gsum = None  # KPI 带引用：闸异常/未执行时为 None（对应卡跳过，不编造）
        try:
            _gated, _gsum = scan_and_gate(
                [{"code": r.get("code", ""), "name": r.get("name", "")} for r in result],
                top_k=len(result) or 1,
            )
            _kicked = {str(k.get("code")) for k in _gsum.get("kicked", [])}
            result = [r for r in result if str(r.get("code", "")) not in _kicked]
            if _gsum.get("kicked"):
                with st.expander(f"🚫 二道闸已拦截 {len(_gsum['kicked'])} 只高危标的（不进入结果）", expanded=False):
                    for k in _gsum["kicked"]:
                        st.caption(f"🔴 {k.get('name')}（{k.get('code')}）："
                                   f"{'；'.join(k.get('reasons', []) or ['六维红旗'])}")
        except Exception as e:  # noqa: BLE001
            logger.warning("[81] 二道闸异常，降级放行: %s", e)
        if not result:
            st.warning("⚠️ 按当前条件无匹配（诚实结果：0 只）。可放宽阈值再试。")
            return
        df = pd.DataFrame([{
            "代码": r["code"], "名称": r["name"],
            "市盈率": r.get("pe"), "市净率": r.get("pb"), "总市值(亿)": r.get("mktcap"),
            "流通市值(亿)": r.get("float_mktcap"),
            "营收增长(%)": r.get("rev_growth"), "净利增长(%)": r.get("profit_growth"),
            "ROE(%)": r.get("roe"),
            "涨跌幅(%)": r.get("chg_pct"), "换手率(%)": r.get("turnover"),
            "量比": r.get("volume_ratio"), "振幅(%)": r.get("amplitude"),
        } for r in result])
        # ── B 类页五段式：KPI 带（数据 = 本次筛选的真实链路计数，仅在执行筛选后出现）──
        _kpi_cards = [{
            "label": "候选池", "value": str(len(recs)),
            "meta": f"范围：{scope}（真实取数）",
        }, {
            "label": "条件命中", "value": str(len(df)),
            "meta": "解析条件筛选后 · 排雷前",
        }]
        if _gsum is not None:
            _kpi_cards.append({
                "label": "二道闸拦截", "value": str(len(_gsum.get("kicked", []) or [])),
                "meta": "六维红旗排雷，拦截标的不进结果",
            })
        _n_parsed = len(spec.boards) + len(spec.filters) + (1 if spec.sort else 0) + len(spec.concepts)
        _kpi_cards.append({
            "label": "已理解条件", "value": str(_n_parsed),
            "meta": (f"未理解 {len(spec.unparsed)} 项已如实标注" if spec.unparsed else "全部口语已解析"),
        })
        xc_bento_kpi(_kpi_cards, template="1fr 1fr 1fr 1fr")
        st.success(f"✅ 命中 {len(df)} 只（诚实结果，来自真实取数）")
        st.dataframe(df, width="stretch", hide_index=True)

    # ── 方法学与来源注脚（B 类页五段式：收尾一段）──
    st.markdown("---")
    st.caption(
        "口径与来源：解析=modules/nl_screen 规则解析（听懂什么原样摊开，未理解词如实标注）；"
        "取数=fetcher/akshare 真实基本面接口（取不到如实提示，绝不伪造候选池）；"
        "二道闸=scan_and_gate 六维红旗排雷。结果为真实筛选，非投资建议。"
    )


if __name__ == "__main__":
    main()
