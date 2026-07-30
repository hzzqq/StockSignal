"""
页面1：行情看板
指数迷你卡、行业板块涨跌榜（含涨跌排行/分布折叠区）、龙虎榜、个股相关性矩阵。
K 线、参数设置、技术面分析已迁移至「股票选取」模块。
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
import concurrent.futures as _cf
from datetime import datetime, timedelta, time

from modules.ui_theme import apply_page_config, _theme_is_dark
from modules.fetcher import StockFetcher
from modules.visualizer import Visualizer
from modules.search_ui import multi_stock_search_input, stock_search_input
from modules.session import (
    require_auth, render_user_badge, api_kline, safe_switch_page,
    fragment_market_alerts_panel, api_get, api_post, api_delete, get_token, API_BASE, clear_auth,
)
from modules.visualizer import UP_COLOR, DOWN_COLOR
from modules.widgets import render_index_compact
from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info, _fmt_yi, _toast, is_trading_now
from modules.fundamental_helpers import fund_one
from modules.format_helpers import safe_int

apply_page_config(page_title="行情看板", page_icon="📈", layout="wide")
st.session_state["_active_page"] = __file__

require_auth()
render_user_badge(sidebar=True)

st.title("📈 行情看板")

# 顶部主要指数收盘行情（轻量组件）
render_index_compact(cols_per_row=5)


# ------------------------------------------------------------------
# 搜索股票 · 加入自选（匹配结果内联显示在输入框下方，模仿图片1）
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("🔍 搜索股票 · 加入自选")
st.caption("输入代码 / 名称 / 拼音首字母，匹配结果直接显示在输入框下方（含市场标签），点击结果即选中；"
           "选中后可一键加入自选股，下方「自选行情」会实时同步。")
_wb_code = stock_search_input(label="输入代码 / 名称 / 拼音", key="wb_search", default="600519")
_wb_c1, _wb_c2 = st.columns([1, 3])
with _wb_c1:
    if st.button("☆ 加入自选股", key="wb_add_wl", use_container_width=True):
        if _wb_code:
            _sc, _body = api_post("/api/watchlist", {"stock_code": _wb_code}, timeout=5)
            if _sc == 200 and isinstance(_body, dict) and _body.get("status") == "ok":
                _toast(f"✅ 已加入自选股 {_wb_code}")
                st.rerun()
            else:
                _msg = _body.get("message", "添加失败") if isinstance(_body, dict) else "添加失败"
                st.warning(f"⚠️ {_msg}")


@st.cache_resource(show_spinner=False)
def _get_fetcher():
    return StockFetcher()


fetcher = _get_fetcher()


@st.cache_data(ttl=3600, show_spinner=False)
def _get_stock_concept(code: str) -> str:
    """获取个股所属概念/行业（用于龙虎榜表格）。

    优先尝试 fetcher.get_stock_concept；不存在或失败时，用 akshare 个股信息
    里的「行业」兜底；若仍失败则填充「—」但保留列。

    行业/概念属低频变化数据，@st.cache_data(ttl=3600) 缓存 1 小时，
    避免龙虎榜表格每只股票每次刷新都发起网络请求（交易时段每 60s 刷新的 N+1 问题）。
    """
    # 1) 优先 StockFetcher 的 get_stock_concept（如存在）
    try:
        f = _get_fetcher()
        if hasattr(f, "get_stock_concept"):
            res = f.get_stock_concept(code)
            if res:
                if isinstance(res, (list, tuple, set)):
                    return "、".join(str(x) for x in res) if res else "—"
                return str(res)
    except Exception:
        pass
    # 2) 兜底：akshare 个股信息中的「行业」
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=str(code))
        if info is not None and not info.empty and "item" in info.columns:
            rec = info[info["item"] == "行业"]
            if not rec.empty:
                val = rec["value"].iloc[0]
                if val:
                    return str(val)
    except Exception:
        pass
    return "—"


# ------------------------------------------------------------------
# 板块卡片网格
# ------------------------------------------------------------------
def _render_sector_cards(df, top_n=24):
    show = df.head(top_n) if top_n else df
    cards = []
    for _, row in show.iterrows():
        name = str(row.get("sector", ""))
        try:
            pct = float(row.get("change_pct", 0))
        except Exception:
            pct = 0.0
        up = pct >= 0
        color = UP_COLOR if up else DOWN_COLOR
        bg = "#fde8e6" if up else "#e8f9ef"
        arrow = "▲" if up else "▼"
        cards.append(
            f'<div style="background:{bg};border-left:3px solid {color};'
            f'border-radius:8px;padding:10px 12px;min-height:64px;'
            f'box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.05);">'
            f'<div style="color:#1f2937;font-size:12px;font-weight:700;'
            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>'
            f'<div style="color:{color};font-size:18px;font-weight:700;margin-top:2px;">'
            f'{arrow} {pct:+.2f}%</div></div>'
        )
    grid = "".join(cards)
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));'
        f'gap:8px;">{grid}</div>',
        unsafe_allow_html=True,
    )
    if top_n and len(df) > top_n:
        st.caption(f"仅显示涨幅前 {top_n} 名（共 {len(df)} 个行业）。")


def _get_market_status():
    now = datetime.now()
    t = now.time()
    weekday = now.weekday()
    if weekday >= 5:
        return False, "⚪ 已休市（周末），展示最后一交易日数据", 0
    am_start, am_end = time(9, 30), time(11, 30)
    pm_start, pm_end = time(13, 0), time(15, 0)
    after_close = time(16, 0)
    if am_start <= t <= am_end:
        return True, "🟢 上午交易中（实时数据）", 60 * 1000
    elif am_end < t < pm_start:
        return False, "🟡 午间休市，展示上午收盘数据", 60 * 1000
    elif pm_start <= t <= pm_end:
        return True, "🟢 下午交易中（实时数据）", 60 * 1000
    elif pm_end < t <= after_close:
        return False, "🔵 已收盘，展示今日全天数据", 0
    else:
        if t < am_start:
            return False, "⚪ 尚未开盘，展示上一交易日数据", 0
        return False, "⚪ 已休市，展示最后一交易日数据", 0


# ------------------------------------------------------------------
# 行业板块涨跌榜（卡片 + 折叠详情）
# ------------------------------------------------------------------
@safe_fragment("行业板块涨跌榜")
def fragment_sector_board():
    st.markdown("---")
    st.subheader("🏭 行业板块涨跌榜")

    try:
        from modules.autorefresh import st_autorefresh
        is_open, status_text, refresh_ms = _get_market_status()
        if refresh_ms > 0:
            st_autorefresh(interval=refresh_ms, key="sector_autorefresh")
    except Exception:
        is_open, status_text, _ = _get_market_status()

    st.caption(status_text)

    # ⚠️ 修复：原卡片区(L151)与折叠详情区(L166)各调一次 get_sector_list()，
    # 单轮运行重复发起两次网络请求。改为顶部统一取数一次，两处复用同一份 sector_df。
    try:
        sector_df = fetcher.get_sector_list()
    except Exception as e:
        sector_df = None
        st.error(f"获取板块数据失败: {e}")

    if sector_df is not None and not sector_df.empty:
        # ── 上游 schema 漂移守卫：列名可能为「板块/涨跌幅」等非预期名，做兼容映射，
        # 避免直接 sector_df["change_pct"] 抛 KeyError 使整个板块模块崩溃 ──
        _sec_col = next((c for c in sector_df.columns if c in ("sector", "板块", "行业", "名称")), None)
        if _sec_col and _sec_col != "sector":
            sector_df = sector_df.rename(columns={_sec_col: "sector"})
        _chg_col = next((c for c in sector_df.columns if c in ("change_pct", "涨跌幅", "涨跌幅(%)")), None)
        if _chg_col and _chg_col != "change_pct":
            sector_df = sector_df.rename(columns={_chg_col: "change_pct"})
        if "sector" not in sector_df.columns:
            sector_df["sector"] = ""
        if "change_pct" not in sector_df.columns:
            sector_df["change_pct"] = 0.0
            st.warning("⚠️ 板块涨跌幅字段缺失，已按 0 处理；数据源可能已变更字段名。")
        sector_df["change_pct"] = pd.to_numeric(sector_df["change_pct"], errors="coerce").fillna(0)
        sector_df = sector_df.sort_values("change_pct", ascending=False).reset_index(drop=True)
        if sector_df["change_pct"].abs().max() < 0.01:
            st.warning("⚠️ 当前数据源未返回板块涨跌幅，仅展示行业列表。交易时间或网络恢复后会自动获取真实数据。")
        _render_sector_cards(sector_df, top_n=24)
    else:
        st.warning("未获取到板块数据。可能处于非交易时段、数据源暂不可用或网络波动；交易时段会自动刷新，也可手动刷新页面重试。")

    # 折叠区：涨跌排行表格 + 涨跌分布（复用上方 sector_df，不再二次取数）
    with st.expander("📊 板块涨跌详情（点击展开）", expanded=False):
        if sector_df is not None and not sector_df.empty:
            try:
                detail_df = sector_df.copy()
                detail_df["排名"] = range(1, len(detail_df) + 1)

                col1, col2 = st.columns([1, 2])
                with col1:
                    st.markdown("#### 涨跌排行表格")
                    display_cols = ["排名", "sector", "change_pct"]
                    st.dataframe(
                        detail_df[display_cols].rename(columns={"sector": "板块", "change_pct": "涨跌幅"}),
                        use_container_width=True,
                        column_config={"涨跌幅": st.column_config.NumberColumn(format="%.2f%%")},
                        height=700,
                    )
                with col2:
                    st.markdown("#### 涨跌分布")
                    fig = Visualizer.sector_heatmap(detail_df, title="全部行业板块涨跌幅")
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"获取板块详情失败: {e}")
        else:
            st.warning("未获取到板块数据。可能处于非交易时段、数据源暂不可用或网络波动；交易时段会自动刷新，也可手动刷新页面重试。")


fragment_sector_board()


def _load_lhb(date_str: str):
    """获取龙虎榜数据。优先东方财富，其次新浪；失败返回 None。

    SSL 校验通过 ssl_bypass() 上下文管理器局部关闭，退出即恢复，
    不再污染进程全局 requests（历史隐患已修，#401/#404）。
    """
    import akshare as ak
    import concurrent.futures as _cf
    from modules.ssl_helper import ssl_bypass

    def _fetch_em():
        # ssl_bypass 在 worker 线程内局部关闭并退出即恢复，避免挂起主线程 fragment
        with ssl_bypass():
            start = (datetime.now().date() - timedelta(days=7)).strftime("%Y%m%d")
            end = datetime.now().date().strftime("%Y%m%d")
            return ak.stock_lhb_detail_em(start_date=start, end_date=end)

    # 1) 东方财富：akshare 调用无内置超时，用线程 + result(timeout=12) 兜底，
    # 超时/异常即降级到新浪，避免交易时段 60s 自动刷新下被网络挂起卡死 fragment。
    em_raw = None
    try:
        with _cf.ThreadPoolExecutor(max_workers=1) as _ex:
            _fut = _ex.submit(_fetch_em)
            em_raw = _fut.result(timeout=12)
    except Exception:
        em_raw = None

    if em_raw is not None and hasattr(em_raw, "empty") and not em_raw.empty:
        df = em_raw.rename(columns=lambda x: str(x).strip())
        # 过滤到目标日期（含前后一交易日兜底）
        if "上榜日" in df.columns:
            df["上榜日"] = df["上榜日"].astype(str).str.replace("-", "")
            filtered = df[df["上榜日"] <= date_str].sort_values("上榜日", ascending=False)
            if not filtered.empty:
                latest_date = filtered["上榜日"].iloc[0]
                df = df[df["上榜日"] == latest_date].copy()
        # 标准化列名
        col_map = {
            "代码": "股票代码",
            "名称": "股票名称",
            "上榜原因": "上榜原因",
            "龙虎榜买入额": "龙虎榜买入额",
            "龙虎榜卖出额": "龙虎榜卖出额",
            "龙虎榜净买额": "龙虎榜净买额",
            "涨跌幅": "涨跌幅",
            "收盘价": "收盘价",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "股票代码" in df.columns:
            df["股票代码"] = df["股票代码"].astype(str).str.replace(r"[^0-9]", "", regex=True).str[-6:]
            df = df[df["股票代码"].str.len() == 6]
        return df

    # 2) 新浪：按日期尝试最近 4 个交易日
    try:
        for offset in range(0, 4):
            d = (datetime.now().date() - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                df = ak.stock_lhb_detail_daily_sina(date=d)
                if df is not None and not df.empty:
                    df = df.rename(columns=lambda x: str(x).strip())
                    return df
            except Exception:
                continue
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# 龙虎榜
# ------------------------------------------------------------------
@safe_fragment("龙虎榜")
def fragment_lhb():
    st.markdown("---")
    # 交易时段每 60 秒自动刷新龙虎榜数据
    try:
        from modules.autorefresh import st_autorefresh
        is_open, _, _ = _get_market_status()
        if is_open:
            st_autorefresh(interval=60000, key="lhb_autorefresh")
    except Exception:
        pass
    with st.expander("🐉 龙虎榜（点击展开/收起）", expanded=True):
        st.caption("当日机构/游资活跃个股（数据来源：东方财富龙虎榜）")

        lhb_date = (datetime.now().date() - timedelta(days=0 if datetime.now().weekday() < 5 else 1)).strftime("%Y%m%d")
        lhb_df = _load_lhb(lhb_date)

        if lhb_df is not None and not lhb_df.empty:
            # 统一列名：尽量兼容不同数据源
            cols = list(lhb_df.columns)
            code_col = next((c for c in cols if "代码" in c), None) or cols[0]
            name_col = next((c for c in cols if "名称" in c or "简称" in c), None)
            reason_col = next((c for c in cols if "原因" in c or "上榜" in c), None)
            buy_col = next((c for c in cols if "买入" in c and "额" in c), None)
            sell_col = next((c for c in cols if "卖出" in c and "额" in c), None)
            net_col = next((c for c in cols if "净买" in c or "净额" in c), None)
            chg_col = next((c for c in cols if "涨跌幅" in c or "涨幅" in c), None)

            lhb_df["_code"] = lhb_df[code_col].astype(str).str.replace(r"[^0-9]", "", regex=True).str[-6:]
            if name_col is None:
                lhb_df["股票名称"] = lhb_df[code_col].map(lambda c: fetcher.get_name_only(c))
            else:
                lhb_df["股票名称"] = lhb_df[name_col].astype(str)

            # 1) 去重：按股票代码保留 |龙虎榜净买额| 最大的一行，保持原有顺序
            if net_col and net_col in lhb_df.columns:
                lhb_df["_net"] = pd.to_numeric(lhb_df[net_col], errors="coerce").fillna(0)
                lhb_df["_score"] = lhb_df["_net"].abs()
            else:
                lhb_df["_score"] = pd.Series(range(len(lhb_df)), index=lhb_df.index, dtype=float)
            lhb_df = lhb_df.reset_index(drop=True)
            lhb_df["_orig"] = range(len(lhb_df))
            lhb_df = (
                lhb_df.sort_values(["_code", "_score"], ascending=[True, False])
                .drop_duplicates("_code", keep="first")
                .sort_values("_orig")
                .reset_index(drop=True)
            )

            # 2) 标准化展示列：买方金额 / 卖方金额 / 龙虎榜净买额 / 涨跌幅
            lhb_df["股票代码"] = lhb_df["_code"]
            if buy_col:
                lhb_df["买方金额"] = lhb_df[buy_col]
            if sell_col:
                lhb_df["卖方金额"] = lhb_df[sell_col]
            if net_col:
                lhb_df["龙虎榜净买额"] = lhb_df[net_col]
            if chg_col:
                lhb_df["涨跌幅"] = lhb_df[chg_col]

            # 金额转 亿/万 显示（UI-only，不改原始数值）
            for _amt_c in ("买方金额", "卖方金额", "龙虎榜净买额"):
                if _amt_c in lhb_df.columns:
                    lhb_df[_amt_c + "(亿)"] = lhb_df[_amt_c].apply(
                        lambda v: _fmt_yi(v) if pd.notna(v) else "—"
                    )

            # 3) 所属概念：逐股获取（首次需回源网络/akshare，加 spinner 避免交易时段观感卡死）
            with st.spinner("正在获取个股所属概念 / 行业..."):
                lhb_df["所属概念"] = [_get_stock_concept(c) for c in lhb_df["股票代码"]]

            # 4) 友好列顺序
            display_cols = ["股票代码", "股票名称", "所属概念"]
            for c in ("涨跌幅", "买方金额", "卖方金额", "龙虎榜净买额"):
                if c in lhb_df.columns:
                    display_cols.append(c + "(亿)")
            if reason_col:
                display_cols.append(reason_col)

            # 清理临时列后展示
            _tmp_cols = [c for c in lhb_df.columns if c.startswith("_")]
            st.dataframe(lhb_df[[c for c in display_cols if c in lhb_df.columns]].drop(columns=_tmp_cols, errors="ignore"),
                         use_container_width=True, height=420)

            # 加法式 UX：一行复制所有龙虎榜代码，便于粘贴到自选/选股框批量关注
            with st.expander("📋 复制龙虎榜代码", expanded=False):
                _lhb_codes = "\n".join(str(c) for c in lhb_df["股票代码"].tolist() if str(c))
                st.code(_lhb_codes or "—", language="text")

            # 点击跳转股票选取（K 线查看）
            opts = [f"{row['股票代码']} {row['股票名称']}" for _, row in lhb_df.iterrows() if len(str(row['股票代码'])) == 6]
            sel = st.selectbox("选择龙虎榜股票查看 K 线", ["— 请选择 —"] + opts, key="lhb_jump_select",
                                help="选择一个标的后跳转到「股票选取」页查看其 K 线与详情。")
            if sel and sel != "— 请选择 —":
                code = sel.split()[0]
                st.query_params["pick_stock"] = code
                safe_switch_page("pages/1_股票选取.py")

            # 5) 热股榜：热度评分 = 归一化(买方+卖方) + 0.3*|涨跌幅| + 0.2*评论数(无则0)
            with st.expander("🔥 热股榜", expanded=False):
                _n = len(lhb_df)
                _amounts = []
                _chgs = []
                for _, _r in lhb_df.iterrows():
                    try:
                        _buy = float(pd.to_numeric(_r.get("买方金额"), errors="coerce") or 0)
                    except Exception:
                        _buy = 0.0
                    try:
                        _sell = float(pd.to_numeric(_r.get("卖方金额"), errors="coerce") or 0)
                    except Exception:
                        _sell = 0.0
                    try:
                        _chg = abs(float(pd.to_numeric(_r.get("涨跌幅"), errors="coerce") or 0))
                    except Exception:
                        _chg = 0.0
                    _amounts.append(abs(_buy) + abs(_sell))
                    _chgs.append(_chg)
                _amounts = pd.Series(_amounts, dtype=float)
                _amax = _amounts.max() if _n else 0.0
                _anorm = (_amounts / _amax) if _amax > 0 else pd.Series([0.0] * _n, dtype=float)
                _heat = _anorm + 0.3 * pd.Series(_chgs, dtype=float)
                heat_df = pd.DataFrame({
                    "股票代码": lhb_df["股票代码"].values,
                    "股票名称": lhb_df["股票名称"].values,
                    "热度": [round(float(x), 2) for x in _heat],
                    "买方金额": lhb_df["买方金额"].values if "买方金额" in lhb_df.columns else [0] * _n,
                    "卖方金额": lhb_df["卖方金额"].values if "卖方金额" in lhb_df.columns else [0] * _n,
                    "涨跌幅": lhb_df["涨跌幅"].values if "涨跌幅" in lhb_df.columns else [0] * _n,
                })
                heat_df = heat_df.sort_values("热度", ascending=False).reset_index(drop=True)
                st.dataframe(heat_df, use_container_width=True,
                             column_config={"热度": st.column_config.NumberColumn(format="%.2f")})

                # 热股榜内的 K 线跳转选择器
                heat_opts = [f"{row['股票代码']} {row['股票名称']}" for _, row in heat_df.iterrows() if len(str(row['股票代码'])) == 6]
                hsel = st.selectbox("选择热股榜股票查看 K 线", ["— 请选择 —"] + heat_opts, key="heat_jump_select",
                                     help="选择热股榜中的标的后跳转到「股票选取」页查看其 K 线与详情。")
                if hsel and hsel != "— 请选择 —":
                    code = hsel.split()[0]
                    st.query_params["pick_stock"] = code
                    safe_switch_page("pages/1_股票选取.py")
        else:
            _empty_info("暂无龙虎榜数据（非交易日晚间或数据源暂不可用）。可先到「📡 股票选取」查看个股 K 线，交易时段会自动刷新。")


fragment_lhb()


# ------------------------------------------------------------------
# 相关性矩阵
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("个股收益率相关性矩阵")
st.caption("💡 解释：数值越接近 1（深红）表示两只股票走势高度同向；越接近 -1（深绿）表示反向；"
           "接近 0 表示关系不大。可用于判断持仓是否过于集中、分散风险。")

with st.expander("📖 怎么看这张图？", expanded=False):
    st.markdown(
        "- **颜色**：红=正相关（同涨同跌），绿=负相关（你涨我跌），白=无关。\n"
        "- **对角线**恒为 1（自己和自己完全相关）。\n"
        "- **用法**：如果组合里多只股票相关性都接近 1，说明风险没有分散；"
        "可适当加入低相关或负相关的标的平衡。\n"
        "- **注意**：仅基于近期（默认 180 天）日收益率计算，长期关系可能变化。"
    )


def _today_str():
    return datetime.now().date().strftime("%Y-%m-%d")


_corr_tickers = multi_stock_search_input(
    label="输入多只股票（逗号分隔）",
    key="corr_stocks",
    default="600519,000858,601088,600036",
    placeholder="输入代码或名称，逗号分隔",
)
_ticker_list = [t.strip() for t in (_corr_tickers if isinstance(_corr_tickers, list) else []) if t.strip()]
if not _ticker_list and _corr_tickers:
    _ticker_list = [t.strip() for t in str(_corr_tickers).split(",") if t.strip()]

# 空态提示：用户清空输入时，直接在按钮上方给出引导，避免点完才报「需要至少 2 只」
if not _ticker_list:
    st.info("💡 请输入至少 2 只股票代码/名称（逗号分隔）后点击「计算相关性」。已默认预填 4 只示例，直接点击即可。")


def _fetch_one_corr(t, start, end):
    """单只股票取数（带超时兜底），返回 (label, df)。"""
    try:
        _records = api_kline(t, start=start, end=end)
        if _records is None:
            d = fetcher.get_daily(t, start=start, end=end)
        else:
            d = pd.DataFrame(_records)
        if d is None or d.empty:
            return None
        _nm = fetcher.get_name_only(t) or fetcher.get_stock_name(t)
        label = f"{t} {_nm}" if _nm else t
        return label, d
    except Exception:
        return None


if st.button("计算相关性", key="calc_corr", use_container_width=True,
             disabled=len(_ticker_list) < 2, help="请至少输入 2 只股票（逗号分隔）后再计算相关性"):
    with st.spinner("正在并行获取行情并计算相关性（最多约 12 秒）..."):
        _end = _today_str()
        _start = (datetime.now().date() - timedelta(days=180)).strftime("%Y-%m-%d")
        daily_dict = {}
        # 并行取数，避免串行逐个网络超时造成「卡死」观感；单只超时 12s 兜底
        _ex = __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
            max_workers=max(1, min(8, len(_ticker_list)))
        )
        try:
            _futs = {_ex.submit(_fetch_one_corr, t, _start, _end): t for t in _ticker_list}
            for _fut in __import__("concurrent.futures", fromlist=["as_completed"]).as_completed(_futs, timeout=15):
                _res = _fut.result(timeout=1)
                if _res:
                    _label, _d = _res
                    daily_dict[_label] = _d
        except Exception:
            pass
        finally:
            _ex.shutdown(wait=False, cancel_futures=True)

        if len(daily_dict) >= 2:
            try:
                fig = Visualizer.correlation_matrix(daily_dict)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                # ⚠️ 深层守卫：某只股票返回异常结构（缺 close 字段 / 仅单行无法计算协方差）
                # 会让 correlation_matrix 抛错，原代码无 try 包裹会直接炸掉「计算相关性」按钮分支。
                # 降级为空态提示，保留页面其余部分可用。
                st.warning(f"⚠️ 相关性矩阵渲染失败：{str(e)[:80]}。请检查输入代码或网络后重试。")
        else:
            st.warning("需要至少 2 只有效股票代码。请检查输入或网络后重试。")

# ------------------------------------------------------------------
# 自选行情（行情看板底部，模仿图片2：名称/代码/现价/涨跌幅/涨跌额/
# 今开/最高/最低/换手率/市盈率/总市值(亿)/操作，行可点看 K 线）
# ------------------------------------------------------------------
def _wl_quote_one(code: str, token):
    """并行取单只实时行情：优先后端 /api/quote，失败回退本地 fetcher。"""
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(f"{API_BASE}/api/quote?ticker={code}", headers=headers, timeout=5)
        if resp.status_code == 401:
            return code, {"__auth_error": True}
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict) and body.get("status") == "ok":
                data = body.get("data")
                if isinstance(data, dict) and data.get("current"):
                    return code, data
    except Exception:
        pass
    try:
        q = fetcher.get_realtime_quote(code)
        if isinstance(q, dict) and q.get("current"):
            return code, q
    except Exception:
        pass
    return code, None


@st.cache_data(ttl=3600, show_spinner=False)
def _wl_extra(code: str):
    """缓存 1h：返回 总股本/流通股（股），用于计算 总市值 与 换手率。失败返回 None。"""
    try:
        import akshare as ak
        from modules.ssl_helper import ssl_bypass
        with ssl_bypass():
            info = ak.stock_individual_info_em(symbol=str(code))
        if info is None or info.empty:
            return None
        d = dict(zip(info["item"], info["value"]))
        def _f(k):
            try:
                return float(str(d.get(k)).replace(",", "").replace("%", "").replace("亿", "").replace("万", ""))
            except Exception:
                return None
        return {"total_shares": _f("总股本"), "float_shares": _f("流通股")}
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _wl_pe(code: str):
    """缓存 1h：取市盈率(TTM)。"""
    try:
        _, pe, _ = fund_one(code, fetcher)
        return pe
    except Exception:
        return None


def _wl_render_table_html(rows, dark: bool):
    """渲染自选行情 HTML 表（深色/浅色自适应），操作列可点击看 K 线。返回 height。"""
    if dark:
        bg, border = "#16161e", "#2d2d44"
        head_bg, head_color = "#1f1f2e", "#cbd5e1"
        row_color, hover = "#e2e8f0", "#23233a"
        code_color = "#8b95a8"
        op_bg, op_color = "#2a2a44", "#a5b4fc"
    else:
        bg, border = "#ffffff", "#e2e8f0"
        head_bg, head_color = "#f8fafc", "#475569"
        row_color, hover = "#1e293b", "#f1f5f9"
        code_color = "#64748b"
        op_bg, op_color = "#eef2ff", "#4f46e5"
    up, down = UP_COLOR, DOWN_COLOR

    cols = ["名称", "代码", "现价", "涨跌幅", "涨跌额", "今开", "最高", "最低", "换手率", "市盈率", "总市值(亿)", "操作"]
    head = "".join(f'<th style="padding:7px 8px;white-space:nowrap;">{c}</th>' for c in cols)

    body = ""
    for r in rows:
        chg = r.get("chg")
        camt = r.get("change_amt")
        col = up if (chg is not None and chg > 0) else (down if (chg is not None and chg < 0) else "#9aa0a6")
        chg_s = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "—"
        camt_s = f"{camt:+.2f}" if isinstance(camt, (int, float)) else "—"
        cur_s = f"{r['cur']:.2f}" if isinstance(r.get("cur"), (int, float)) else "—"
        open_s = f"{r['open']:.2f}" if isinstance(r.get("open"), (int, float)) else "—"
        high_s = f"{r['high']:.2f}" if isinstance(r.get("high"), (int, float)) else "—"
        low_s = f"{r['low']:.2f}" if isinstance(r.get("low"), (int, float)) else "—"
        turn_s = r.get("turnover") if r.get("turnover") is not None else "—"
        pe_s = r.get("pe") if r.get("pe") is not None else "—"
        mv_s = r.get("mv_yi") if r.get("mv_yi") is not None else "—"
        body += (
            f'<tr style="color:{row_color};">'
            f'<td style="padding:6px 8px;white-space:nowrap;">{r["name"]}</td>'
            f'<td style="padding:6px 8px;color:{code_color};font-variant-numeric:tabular-nums;">{r["code"]}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{cur_s}</td>'
            f'<td style="padding:6px 8px;color:{col};font-weight:600;font-variant-numeric:tabular-nums;">{chg_s}</td>'
            f'<td style="padding:6px 8px;color:{col};font-variant-numeric:tabular-nums;">{camt_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{open_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{high_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{low_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{turn_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{pe_s}</td>'
            f'<td style="padding:6px 8px;font-variant-numeric:tabular-nums;">{mv_s}</td>'
            f'<td style="padding:6px 8px;"><span class="wl-op" data-code="{r["code"]}" '
            f'style="cursor:pointer;background:{op_bg};color:{op_color};font-size:12px;'
            f'padding:2px 8px;border-radius:10px;white-space:nowrap;">📈 看K线</span></td>'
            f'</tr>'
        )

    css = f"""
    <style>
    .wl-table{{width:100%;border-collapse:collapse;background:{bg};
      border:1px solid {border};border-radius:8px;font-size:13px;font-family:inherit;}}
    .wl-table th{{background:{head_bg};color:{head_color};text-align:right;font-weight:600;
      border-bottom:1px solid {border};position:sticky;top:0;}}
    .wl-table th:nth-child(1),.wl-table th:nth-child(2){{text-align:left;}}
    .wl-table td{{text-align:right;border-bottom:1px solid {border};}}
    .wl-table td:nth-child(1),.wl-table td:nth-child(2){{text-align:left;}}
    .wl-table tr:hover td{{background:{hover};}}
    </style>
    """
    html = (
        css
        + f'<div style="max-height:520px;overflow:auto;"><table class="wl-table">'
        + f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
        + '<script>'
        + 'var ops=document.querySelectorAll(".wl-op");'
        + 'for(var i=0;i<ops.length;i++){ops[i].onclick=function(){'
        + 'var s=window.parent&&window.parent.Streamlit;'
        + 'if(s&&s.setComponentValue){s.setComponentValue(this.getAttribute("data-code"));}'
        + '};}'
        + '</script>'
    )
    return html


@safe_fragment("自选行情")
def fragment_watchlist_quotes():
    st.markdown("---")
    st.subheader("📌 自选行情")
    st.caption("实时跟踪自选股现价与涨跌（A股红涨绿跌）；行情接口异常时自动回退本地源。点击操作列「📈 看K线」跳转个股 K 线。")

    # 交易时段自动刷新（仅本 fragment 重跑）
    try:
        from modules.autorefresh import st_autorefresh
        if is_trading_now():
            st_autorefresh(interval=60 * 1000, key="wl_quotes_autorefresh")
    except Exception:
        pass

    sc, body = api_get("/api/watchlist", timeout=10)
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("⚠️ 加载自选股失败，请稍后重试")
        return

    items = body.get("data", []) or []
    if not items:
        _empty_info("自选股为空。可在上方「🔍 搜索股票 · 加入自选」搜索后点击 ☆ 加入，或前往「📡 自选股监控」管理。")
        return

    codes = [it.get("stock_code") for it in items if isinstance(it, dict) and it.get("stock_code")]
    name_by_code = {it.get("stock_code"): it.get("stock_name") for it in items}
    id_by_code = {it.get("stock_code"): it.get("id") for it in items}

    # 并行解析名称（本地库兜底）
    names = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        _fut_map = {ex.submit(fetcher.get_name_only, c): c for c in codes}
        for _fut in _cf.as_completed(_fut_map):
            _c = _fut_map[_fut]
            try:
                names[_c] = _fut.result() or _c
            except Exception:
                names[_c] = _c

    # 并行拉取实时行情
    quotes = {}
    _tok = get_token()
    with st.spinner(f"并行获取 {len(codes)} 只自选股实时行情…"):
        with _cf.ThreadPoolExecutor(max_workers=4) as ex:
            for code, q in ex.map(lambda c: _wl_quote_one(c, _tok), codes):
                quotes[code] = q

    if any(isinstance(q, dict) and q.get("__auth_error") for q in quotes.values()):
        clear_auth()
        st.warning("🔐 登录已过期，请重新登录")
        return

    rows = []
    for code in codes:
        q = quotes.get(code)
        name = (q.get("name") if isinstance(q, dict) and q.get("name") else None) or names.get(code) or code
        if q and q.get("current"):
            cur = float(q["current"])
            prev = float(q.get("prev_close") or 0)
            high = float(q.get("high") or 0)
            low = float(q.get("low") or 0)
            open_ = float(q.get("open") or 0)
            volume = safe_int(q.get("volume"), 0)
            chg = (cur - prev) / prev * 100 if prev else 0.0
            change_amt = cur - prev if prev else 0.0
        else:
            cur = open_ = high = low = chg = change_amt = None
            volume = 0

        # 财务补充（缓存 1h）：市盈率 / 总市值 / 换手率
        pe = _wl_pe(code)
        extra = _wl_extra(code)
        total_shares = extra.get("total_shares") if extra else None
        float_shares = extra.get("float_shares") if extra else None
        mv_yi = (cur * total_shares / 1e8) if (cur and total_shares) else None
        turnover = None
        if volume and float_shares:
            _t = volume / float_shares * 100
            turnover = f"{_t:.2f}%" if 0 <= _t <= 100 else "—"

        rows.append({
            "code": code, "name": name, "cur": cur, "chg": chg, "change_amt": change_amt,
            "open": open_, "high": high, "low": low, "turnover": turnover,
            "pe": (f"{pe:.2f}" if isinstance(pe, (int, float)) and not pd.isna(pe) else None),
            "mv_yi": (f"{mv_yi:.2f}" if mv_yi is not None else None),
        })

    up_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] >= 0)
    down_n = sum(1 for r in rows if r["chg"] is not None and r["chg"] < 0)
    st.markdown(
        f"#### 共 {len(rows)} 只自选股 ｜ "
        f"<span style='color:{UP_COLOR};font-weight:600;'>▲ {up_n}</span> ／ "
        f"<span style='color:{DOWN_COLOR};font-weight:600;'>▼ {down_n}</span>",
        unsafe_allow_html=True,
    )

    # 操作列点击（components.html 内联表）
    picks = _wl_render_table_html(rows, _theme_is_dark())
    picked = components.html(picks, height=min(60 + len(rows) * 38, 540), key="wl_table_html")
    if picked and picked in codes:
        st.query_params["pick_stock"] = picked
        safe_switch_page("pages/1_股票选取.py")

    # 加法式兜底：K 线跳转（可靠 selectbox）+ 移除自选
    opts = [f"{r['code']} {r['name']}" for r in rows]
    _kc1, _kc2 = st.columns(2)
    with _kc1:
        sel = st.selectbox("选择股票查看 K 线", ["— 请选择 —"] + opts, key="wl_kline_jump")
        if sel and sel != "— 请选择 —":
            c = sel.split()[0]
            st.query_params["pick_stock"] = c
            safe_switch_page("pages/1_股票选取.py")
    with _kc2:
        rsel = st.selectbox("移除自选", ["— 请选择 —"] + opts, key="wl_remove_sel")
        if st.button("🗑 移除", key="wl_remove_btn", use_container_width=True):
            if rsel and rsel != "— 请选择 —":
                rc = rsel.split()[0]
                rid = id_by_code.get(rc)
                if rid is not None:
                    dsc, dbody = api_delete(f"/api/watchlist/{rid}", timeout=5)
                    if dsc == 200:
                        _toast(f"🗑 已移除 {rc}")
                        st.rerun(scope="fragment")
                    else:
                        st.warning("⚠️ 移除失败，请重试")


fragment_watchlist_quotes()


# 全局市场异动面板（与 P_市场情绪 页共享同一组件）
fragment_market_alerts_panel()
