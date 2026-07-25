"""
页面4：策略回测
支持三种策略：趋势动量多因子（推荐）、均线交叉、事件驱动

模块独立化（@st.fragment）：
  - fragment_manual_backtest：手动回测（选股 + 参数 + 运行 + 结果）
  - fragment_daily_picker：每日选股回测（重计算，1~5 分钟）
  两个模块各自独立 rerun：点「开始选股回测」只重跑每日选股 fragment，
  不会重渲染/重算上方的手动回测；反之亦然。符合「一个模块运行不影响同页其他模块」。
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from modules.ui_theme import apply_page_config
apply_page_config(page_title="策略回测", page_icon="⚙️", layout="wide")
st.session_state["_active_page"] = __file__
st.title("⚙️ 策略回测")

from modules.backtest import Backtester
from modules.visualizer import Visualizer, UP_COLOR, DOWN_COLOR, _is_dark, SF_GRID, SF_BORDER, SF_TXT, SF_TXT2
from modules.search_ui import stock_search_input
from modules.fetcher import StockFetcher
from modules.session import require_auth, render_user_badge
from modules.page_guard import safe_fragment
from modules.page_widgets import _empty_info

# 鉴权门禁
require_auth()
render_user_badge(sidebar=True)

bt = Backtester()

# ------------------------------------------------------------------
# 强势上涨股样本（用于快捷预设 & 批量回测对比）
# 选取 A 股中长期具备强趋势特征的知名标的作为示例样本；
# 真实强弱随行情变化，回测结果仅作策略覆盖度验证，不构成投资建议。
# ------------------------------------------------------------------
STRONG_BULL_PRESETS = [
    ("600519", "贵州茅台"),
    ("300750", "宁德时代"),
    ("002594", "比亚迪"),
    ("601012", "隆基绿能"),
    ("600036", "招商银行"),
    ("000858", "五粮液"),
    ("601318", "中国平安"),
    ("600900", "长江电力"),
]


# ------------------------------------------------------------------
# 策略说明
# ------------------------------------------------------------------
with st.expander("📖 策略方法论说明", expanded=False):
    st.markdown("""
#### 趋势动量多因子策略 V5（推荐）

综合了以下**市场成熟量化方法**：

| 方法来源 | 核心思想 | 在本策略中的应用 |
|---------|---------|-----------------|
| **Larry Connors RSI(2)** | 短期超跌后均值回归概率高 | RSI(2) 极低时给予动量加分 |
| **经典趋势跟踪** | 顺势而为，不逆势交易 | 以 MA20 为核心趋势基准，MA60 作为加分项，兼容短区间数据 |
| **布林带均值回归** | 价格偏离均值后会回归 | 从布林带下轨反弹时给予波动率加分 |
| **ATR 波动率过滤** | 过滤异常波动，避免假突破 | ATR/Close 越低得分越高，强势股波动大也保底给分 |

**因子池（共 100 分）**：
- 趋势因子（最高 50）：close > MA20 为基础，MA20 向上、MA20>MA60、close>MA60 额外加分
- 动量因子（最高 30）：RSI14 健康区间 40-70 得高分；RSI2 低位仅作加分
- 波动/风险因子（最高 15）：ATR 比率、布林带下轨反弹
- 量能因子（最高 15）：成交量/MA20 比值

**买入条件**：综合评分 ≥ 55，收盘价在 MA20 上方，且 RSI14 未进入极端超买（≤98，允许强势股主升浪续涨；V5 将上限由 85 放宽至 98，覆盖长电科技式强势上涨股）。

**离场条件**（满足其一）：
- close < MA20 且 MA20 拐头向下：趋势走坏，止损离场（V5 增加拐头判定，避免单日毛刺误杀）
- RSI14 从 92 以上回落至 90 以下：超买回落，获利了结（V5 阈值由 80/75 上移至 92/90，让利润奔跑）

**交易成本**：买入佣金 + 滑点；卖出佣金 + 印花税 + 滑点。

**风险管理**（可在下方参数中调整）：
- 止盈 3%：小利润目标，提高胜率
- 止损 5%：截断亏损
- 最大持仓 15 个交易日：避免资金被长期占用

> **适用场景**：本策略不再只买"超跌反弹"，而是**趋势确认后买入、趋势走坏时卖出**。
> 对深科技、长电科技这类强势趋势股也能产生信号。若希望单笔收益更大，可将止盈放大至 8-10%。
""")


# ==================================================================
# 模块一：手动回测（独立于每日选股回测）
# ==================================================================
@safe_fragment("手动回测")
def fragment_manual_backtest():
    st.subheader("回测参数")

    # ── 强势上涨股快捷预设（点击填入股票搜索）──
    st.caption("⚡ 强势上涨股快捷预设（点击一键填入上方股票搜索，验证多因子策略对强趋势股的覆盖）：")
    preset_cols = st.columns(len(STRONG_BULL_PRESETS))
    for i, (code, name) in enumerate(STRONG_BULL_PRESETS):
        if preset_cols[i].button(name, key=f"preset_{code}", help=f"代码 {code} · 一键填入"):
            st.session_state["bt_ticker_confirmed"] = code
            st.session_state["bt_ticker_query"] = code

    with st.form("backtest_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            bt_ticker = stock_search_input(
                label="股票搜索",
                key="bt_ticker",
                default="601088",
                placeholder="输入代码或名称搜索，如：601088 / 中国神华 / 煤炭",
            )
            bt_fetcher = StockFetcher()
            bt_label = bt_fetcher.get_name_only(bt_ticker) or bt_fetcher.get_stock_name(bt_ticker)
        with col2:
            strategy = st.selectbox(
                "策略",
                options=["multi_factor", "ma_cross", "event_driven"],
                format_func=lambda x: {
                    "multi_factor": "趋势动量多因子（推荐）",
                    "ma_cross": "均线交叉",
                    "event_driven": "事件驱动",
                }.get(x, x),
                help="趋势动量多因子策略综合 RSI 均值回归 + 趋势跟踪 + 布林带，胜率更优"
            )
        with col3:
            initial_capital = st.number_input("初始资金", value=100000, step=10000,
                                              help="回测起始投入资金，用于计算收益率、仓位与回撤。")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            bt_start = st.date_input("起始日期", value=datetime.now() - timedelta(days=365),
                                    help="回测区间起点，默认近 1 年。")
        with col_d2:
            bt_end = st.date_input("截止日期", value=datetime.now(),
                                  help="回测区间终点，默认今天。")

        keywords_input = ""
        if strategy == "event_driven":
            keywords_input = st.text_input(
                "事件关键词（逗号分隔）",
                value="煤炭,保供,电厂库存",
                key="bt_keywords"
            )

        with st.expander("⚙️ 风险管理参数", expanded=strategy == "multi_factor"):
            st.caption("默认参数已针对 A 股趋势行情优化：小止盈（3%）提高胜率，小止损（5%）截断亏损。")
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                stop_loss_pct = st.slider("止损比例(%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5,
                                           help="价格跌至买入价以下此比例时止损卖出") / 100
                take_profit_pct = st.slider("止盈比例(%)", min_value=0.0, max_value=30.0, value=3.0, step=0.5,
                                             help="价格涨至买入价以上此比例时止盈卖出。设小值提高胜率") / 100
            with col_r2:
                trailing_stop_pct = st.slider("移动止损回撤(%)", min_value=0.0, max_value=20.0, value=0.0, step=0.5,
                                               help="从持仓最高价回撤此比例时卖出。0=关闭") / 100
                max_holding = st.slider("最大持仓周期(交易日)", min_value=5, max_value=120, value=15, step=5)
            min_holding = st.slider("最小持仓周期(交易日)", min_value=0, max_value=20, value=2, step=1,
                                     help="买入后至少持有这么多天再考虑卖出，避免频繁进出")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            commission = st.slider("手续费率(%)", min_value=0.0, max_value=0.5, value=0.1, step=0.01) / 100
        with col_c2:
            show_benchmark = st.checkbox("显示基准（买入持有）", value=True)

        submitted = st.form_submit_button("开始回测")

    if submitted:
        if not bt_ticker or not str(bt_ticker).strip():
            st.warning("请先在「股票搜索」中选择一只股票，再点击「开始回测」。")
            return
        keywords = [k.strip() for k in keywords_input.split(",") if k.strip()] if keywords_input else []

        with st.spinner("正在回测，请稍候..."):
            try:
                result = bt.run(
                    ticker=bt_ticker,
                    start=bt_start.strftime("%Y-%m-%d"),
                    end=bt_end.strftime("%Y-%m-%d"),
                    strategy=strategy,
                    keywords=keywords,
                    initial_capital=initial_capital,
                    commission=commission,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    trailing_stop_pct=trailing_stop_pct,
                    max_holding=max_holding,
                    min_holding=min_holding,
                )

                # 摘要
                st.markdown("---")
                st.subheader("回测结果")

                s = result.summary()
                # 加法式健壮性：summary() 字典字段若因上游 schema 漂移缺失（如 'win_rate_pct'），
                # 直接 s['win_rate_pct'] 会抛 KeyError 让整个回测结果 fragment 崩溃。
                # 统一用 .get 兜底为 0/None，保证指标卡始终可渲染。
                _wr = s.get('win_rate_pct') or 0
                _tr = s.get('total_return_pct') or 0
                _md = s.get('max_drawdown_pct') or 0
                _sh = s.get('sharpe_ratio')
                # 加法式健壮性：夏普比率可能因无波动/除零返回 inf 或 NaN，
                # 直接格式化会显示 "inf"/"nan"，统一降级为 "—"。
                _sh_disp = (f"{_sh:.2f}" if isinstance(_sh, (int, float)) and _sh == _sh
                            and _sh not in (float('inf'), float('-inf')) else "—")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    win_color = "🟢" if _wr >= 60 else ("🟡" if _wr >= 40 else "🔴")
                    st.metric(f"{win_color} 胜率", f"{_wr:.1f}%")
                with col2:
                    st.metric("累计收益", f"{_tr:+.2f}%")
                with col3:
                    st.metric("最大回撤", f"{_md:.2f}%")
                with col4:
                    st.metric("夏普比率", _sh_disp)

                _tc = s.get('trade_count') or 0
                _pf = s.get('profit_factor')
                # 加法式健壮性：无亏损交易时盈亏比为 inf，统一降级为 "—"。
                _pf_disp = (f"{_pf:.2f}" if isinstance(_pf, (int, float)) and _pf == _pf
                            and _pf not in (float('inf'), float('-inf')) else "—")
                _atr = s.get('avg_trade_return_pct') or 0
                _fv = s.get('final_value')
                col5, col6, col7, col8 = st.columns(4)
                with col5:
                    st.metric("交易次数", f"{_tc}")
                with col6:
                    st.metric("盈亏比", _pf_disp)
                with col7:
                    st.metric("平均单笔", f"{_atr:+.2f}%")
                with col8:
                    st.metric("最终资产", f"¥{_fv:,.2f}" if _fv is not None else "¥—")

                st.code(result.summary_text().replace(f"[{bt_ticker}]", f"[{bt_label}]"), language="text")

                # 收益曲线
                st.markdown("---")
                st.subheader("收益曲线")

                benchmark = None
                if show_benchmark and not result.df.empty:
                    # 加法式健壮性：首根收盘价可能为 0（退市/异常数据）或 NaN，
                    # 直接相除会得到 inf/nan 污染整条基准曲线。先 coerce 再判非零。
                    try:
                        first_close = pd.to_numeric(result.df.iloc[0]["close"], errors="coerce")
                        if pd.notna(first_close) and first_close != 0:
                            benchmark = (result.df["close"] / first_close - 1) * 100
                    except Exception:
                        benchmark = None

                fig = Visualizer.backtest_curve(result.df, benchmark=benchmark,
                                                title=f"{bt_label} 策略收益曲线")
                st.plotly_chart(fig, width="stretch")

                # 回撤曲线
                st.markdown("---")
                st.subheader("回撤曲线")
                fig_dd = Visualizer.drawdown_curve(result.df)
                st.plotly_chart(fig_dd, width="stretch")

                # 交易明细
                st.markdown("---")
                st.subheader("交易明细")
                if result.trades:
                    trades_df = pd.DataFrame(result.trades)
                    trades_df["收益率"] = trades_df["profit_pct"].map(lambda x: f"{x:+.2f}%")
                    trades_df["持仓天数"] = trades_df["bars_held"]
                    display_df = trades_df[["entry_date", "exit_date", "entry_price", "exit_price", "收益率", "exit_reason", "持仓天数"]]
                    display_df.columns = ["买入日期", "卖出日期", "买入价", "卖出价", "收益率", "退出原因", "持仓天数"]
                    st.dataframe(display_df, width="stretch")

                    # 交易统计
                    wins = [t for t in result.trades if t["profit_pct"] > 0]
                    losses = [t for t in result.trades if t["profit_pct"] <= 0]
                    st.markdown("---")
                    st.subheader("交易统计")
                    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                    with stat_col1:
                        avg_win = sum(t["profit_pct"] for t in wins) / len(wins) if wins else 0
                        st.metric("平均盈利", f"+{avg_win:.2f}%")
                    with stat_col2:
                        avg_loss = sum(t["profit_pct"] for t in losses) / len(losses) if losses else 0
                        st.metric("平均亏损", f"{avg_loss:.2f}%")
                    with stat_col3:
                        max_win = max(t["profit_pct"] for t in result.trades) if result.trades else 0
                        st.metric("最大盈利", f"+{max_win:.2f}%")
                    with stat_col4:
                        max_loss = min(t["profit_pct"] for t in result.trades) if result.trades else 0
                        st.metric("最大亏损", f"{max_loss:.2f}%")
                else:
                    st.info("本区间没有产生完整交易。可能原因：该股票在此期间不满足强上升趋势条件，未产生买入信号。")

                # ── 回撤带（水下曲线） ──
                st.markdown("---")
                st.subheader("回撤带（水下曲线）")
                _dd = result.df["drawdown"] if "drawdown" in result.df.columns else None
                if _dd is not None and not _dd.dropna().empty:
                    fig_dd_band = go.Figure(go.Scatter(
                        x=result.df["date"], y=_dd,
                        fill="tozeroy",
                        fillcolor="rgba(26,162,96,0.25)",
                        line=dict(color=DOWN_COLOR, width=1),
                        name="回撤%",
                        hovertemplate="%{x}<br>回撤：%{y:.2f}%<extra></extra>",
                    ))
                    fig_dd_band.update_layout(
                        title="资金使用率回撤（水下）",
                        xaxis_title="日期", yaxis_title="回撤%",
                        height=320,
                        template="plotly_white" if not _is_dark() else "plotly_dark",
                        margin=dict(l=50, r=20, t=40, b=30),
                    )
                    st.plotly_chart(fig_dd_band, use_container_width=True)
                else:
                    _empty_info("暂无回撤数据。通常因回测区间过短，或策略未产生持仓净值波动导致；可拉长区间后重试。")

                # ── 逐笔交易收益分布 ──
                st.markdown("---")
                st.subheader("逐笔交易收益分布")
                if result.trades:
                    _profits = [t.get("profit_pct", 0) for t in result.trades]
                    fig_tr = go.Figure(go.Bar(
                        x=[f"#{i+1}" for i in range(len(_profits))],
                        y=_profits,
                        marker_color=[UP_COLOR if p > 0 else DOWN_COLOR for p in _profits],
                        hovertemplate="交易%{x}<br>收益率：%{y:.2f}%<extra></extra>",
                    ))
                    fig_tr.update_layout(
                        title="每笔交易收益率（红盈绿亏）",
                        xaxis_title="交易序号", yaxis_title="收益率%",
                        height=320,
                        template="plotly_white" if not _is_dark() else "plotly_dark",
                        margin=dict(l=50, r=20, t=40, b=30),
                    )
                    st.plotly_chart(fig_tr, use_container_width=True)
                else:
                    st.info("本区间没有产生完整交易。可能原因：该股票在此期间不满足强上升趋势条件，未产生买入信号。")

                # ── 参数敏感性分析 ──
                st.markdown("---")
                st.subheader("🎯 参数敏感性分析")
                st.caption("固定其余参数，扫描单一参数的不同取值，观察累计收益 / 胜率 / 最大回撤的变化，寻找参数拐点。")
                sens_choice = st.selectbox(
                    "选择扫描参数",
                    options=["stop_loss_pct", "take_profit_pct", "max_holding"],
                    format_func=lambda x: {
                        "stop_loss_pct": "止损比例(%)",
                        "take_profit_pct": "止盈比例(%)",
                        "max_holding": "最大持仓周期(交易日)",
                    }.get(x, x),
                    key="sens_param",
                )
                if st.button("🚀 运行敏感性扫描", key="sens_run"):
                    base = dict(
                        ticker=bt_ticker,
                        start=bt_start.strftime("%Y-%m-%d"),
                        end=bt_end.strftime("%Y-%m-%d"),
                        strategy=strategy,
                        keywords=keywords,
                        initial_capital=initial_capital,
                        commission=commission,
                        stop_loss_pct=stop_loss_pct,
                        take_profit_pct=take_profit_pct,
                        trailing_stop_pct=trailing_stop_pct,
                        max_holding=max_holding,
                        min_holding=min_holding,
                    )
                    if sens_choice == "stop_loss_pct":
                        grid = [0.03, 0.05, 0.07, 0.10, 0.15]
                        labels = [f"{g*100:.0f}%" for g in grid]
                    elif sens_choice == "take_profit_pct":
                        grid = [0.03, 0.05, 0.08, 0.12, 0.20]
                        labels = [f"{g*100:.0f}%" for g in grid]
                    else:
                        grid = [5, 10, 15, 20, 30]
                        labels = [str(g) for g in grid]
                    xs, ys_ret, ys_win, ys_dd = [], [], [], []
                    with st.spinner("正在扫描参数组合，请稍候…"):
                        # 加法式性能优化：原实现 5 次完整回测串行（每次约拉 180 天日线 + 计算），
                        # 单参数扫描要数十秒。改用线程池并行；子线程内仅调用 bt.run（只读 config，
                        # 无共享可变状态、无任何 st 调用），按 grid 下标回填结果以严格保持标签顺序。
                        from concurrent.futures import ThreadPoolExecutor, as_completed

                        def _run_grid(g):
                            try:
                                params = dict(base)
                                params[sens_choice] = g
                                r2 = bt.run(**params)
                                s2 = r2.summary()
                                return (s2["total_return_pct"], s2["win_rate_pct"], s2["max_drawdown_pct"])
                            except Exception:
                                return (None, None, None)

                        _res = {}
                        with ThreadPoolExecutor(max_workers=min(4, len(grid))) as _ex:
                            _futs = {_ex.submit(_run_grid, g): g for g in grid}
                            for _fut in as_completed(_futs):
                                _res[_futs[_fut]] = _fut.result()
                        for _i, g in enumerate(grid):
                            xs.append(labels[_i])
                            _r, _w, _d = _res.get(g, (None, None, None))
                            ys_ret.append(_r)
                            ys_win.append(_w)
                            ys_dd.append(_d)
                    fig_sens = go.Figure()
                    fig_sens.add_trace(go.Scatter(x=xs, y=ys_ret, mode="lines+markers",
                                                  name="累计收益%", line=dict(color=UP_COLOR, width=2)))
                    fig_sens.add_trace(go.Scatter(x=xs, y=ys_win, mode="lines+markers",
                                                  name="胜率%", line=dict(color="#2b8aef", width=2)))
                    fig_sens.add_trace(go.Scatter(x=xs, y=ys_dd, mode="lines+markers",
                                                  name="最大回撤%", line=dict(color=DOWN_COLOR, width=2)))
                    fig_sens.update_layout(
                        title=f"参数敏感性：{sens_choice}",
                        xaxis_title="参数取值", yaxis_title="指标%",
                        height=360,
                        template="plotly_white" if not _is_dark() else "plotly_dark",
                        margin=dict(l=50, r=20, t=50, b=70),
                        legend=dict(orientation="h", yanchor="top", y=-0.25, x=0.5, xanchor="center"),
                    )
                    st.plotly_chart(fig_sens, use_container_width=True)
                    st.caption("提示：曲线走平或反转处通常表示参数拐点，可据此微调风险管理参数。")

            except Exception as e:
                st.error(f"回测失败: {e}")
                st.exception(e)


# ==================================================================
# 模块二：每日选股回测（重计算，独立 fragment）
# ==================================================================
@safe_fragment("每日选股回测")
def fragment_daily_picker():
    st.markdown("---")
    st.subheader("📊 每日选股回测")
    st.caption("从 A 股股票池中每日筛选评分最高的股票，模拟短线持有收益。"
               "「今日推荐」= 基于昨日收盘数据选股、今日买入；"
               "「明日推荐」= 基于今日收盘数据选股、明日买入。")

    with st.expander("👶 第一次用？点这里看「每日选股回测」怎么玩（小白必读）", expanded=False):
        st.markdown(r"""
        **一句话理解**：回测 = 拿「过去的行情」模拟「如果你当时按规则买入，能赚多少」，
        用来检验选股策略管不管用。**它只看历史，不代表未来一定赚钱。**

        **三步上手**：
        1. 先填好下面几个参数（股票池大小、每日选股数、持有天数、并行线程数）和日期区间（默认最近 30 天）。
        2. 点 **🚀 开始选股回测**，程序会从 A 股随机抽一批股票打分、模拟买入卖出，通常需要 **1~5 分钟**，请耐心等待。
        3. 跑完后看上方指标卡 + 「今日推荐 / 明日推荐」清单。

        **参数怎么填？**
        - **股票池大小**：从全市场随机抽多少只来打分。默认 100 只足够看趋势；想更稳可设 300~500（但更慢）。
        - **每日选股数**：每天精选前 N 只。数字小更聚焦，大则更分散。
        - **持有天数**：买入后拿几天再算收益。1 天 = 隔日卖（超短线）；3~5 天 = 小波段。
        - **并行线程数**：电脑同时拉数据的「手」的数量，默认 4；如果卡顿就把调小。

        **结果怎么看？**
        - 🟢 **个股胜率 / 上涨日占比** ≥ 55~60% 算不错；🔴 低于 45% 说明这段行情里策略偏弱。
        - **累计收益** 为正（🟢）代表模拟盈利，为负（🔴）代表模拟亏损。
        - **今日推荐** = 用昨天数据选的，今天可买；**明日推荐** = 用今天数据选的，明天可买。

        ⚠️ **风险提示**：回测收益是历史模拟，存在未来函数偏差、未计手续费/滑点等局限，**仅供参考，不构成任何投资建议**。实盘请务必结合自身风险承受能力。
        """)

    with st.expander("📖 选股评分说明", expanded=False):
        st.markdown("""
#### 评分维度（满分 100）

| 维度 | 满分 | 条件 |
|------|------|------|
| **趋势分** | 40 | close > MA20 > MA60 且均线向上（强趋势）；否则 close > MA20 得 20 分 |
| **超跌分** | 35 | RSI(2) < 5 得 35；< 10 得 30；< 15 得 20；< 25 得 10 |
| **健康分** | 15 | RSI(14) 在 35-55 健康区间得 15；30-35 回踩得 10 |
| **量能分** | 10 | 成交量 > 20日均量×1.2 得 10；> 均量 得 5 |

**过滤条件**：价格须在 MA20 上方，RSI(14) 不超过 65（避免超买）。
""")

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        pool_size = st.number_input("股票池大小", min_value=50, max_value=1000, value=100, step=50,
                                    help="从 A 股随机抽取的股票池规模，越大越准确但越慢")
    with col_p2:
        top_k = st.number_input("每日选股数", min_value=1, max_value=20, value=5, step=1,
                                help="每个交易日入选并持有的股票数量。")
    with col_p3:
        hold_days = st.number_input("持有天数", min_value=1, max_value=10, value=1, step=1,
                                   help="入选股票持有的交易日天数，到期次日换仓。")
    with col_p4:
        picker_workers = st.number_input("并行线程数", min_value=2, max_value=16, value=4, step=1,
                                         help="同时获取股票数据的线程数")

    col_pd1, col_pd2 = st.columns(2)
    with col_pd1:
        picker_start = st.date_input("选股起始日期", value=datetime.now() - timedelta(days=30), key="picker_start")
    with col_pd2:
        picker_end = st.date_input("选股截止日期", value=datetime.now(), key="picker_end")

    picker_btn = st.button("🚀 开始选股回测", type="primary")

    if picker_btn:
        with st.spinner(f"正在从 A 股股票池中获取 {pool_size} 只股票数据并评分，预计需要 1-5 分钟…"):
            try:
                picker_result = bt.daily_picker_backtest(
                    start=picker_start.strftime("%Y-%m-%d"),
                    end=picker_end.strftime("%Y-%m-%d"),
                    stock_pool_size=pool_size,
                    top_k=top_k,
                    hold_days=hold_days,
                    max_workers=picker_workers,
                )
                st.session_state["picker_result"] = picker_result
                st.session_state["picker_error"] = None
            except Exception as e:
                st.session_state["picker_result"] = None
                st.session_state["picker_error"] = str(e)

    # 从 session_state 恢复结果
    picker_result = st.session_state.get("picker_result")
    picker_error = st.session_state.get("picker_error")

    if picker_error:
        st.error(f"选股回测失败: {picker_error}")
    elif picker_result is not None:
        s = picker_result.summary()

        if s["total_days"] == 0:
            st.warning("选股回测未产生有效数据，请尝试扩大日期范围或增加股票池大小。")
        else:
            # ---- 汇总指标 ----
            st.markdown("---")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                win_color = "🟢" if s["win_pick_pct"] >= 60 else ("🟡" if s["win_pick_pct"] >= 40 else "🔴")
                st.metric(f"{win_color} 个股胜率", f"{s['win_pick_pct']:.1f}%")
            with m2:
                day_color = "🟢" if s["win_day_pct"] >= 55 else ("🟡" if s["win_day_pct"] >= 45 else "🔴")
                st.metric(f"{day_color} 上涨日占比", f"{s['win_day_pct']:.1f}%")
            with m3:
                # A股惯例：正收益=红、负收益=绿，与下方个股卡片(L731)保持一致
                ret_color = "🔴" if s["total_return_pct"] >= 0 else "🟢"
                st.metric(f"{ret_color} 累计收益", f"{s['total_return_pct']:+.2f}%")
            with m4:
                st.metric("日均收益", f"{s['avg_daily_return_pct']:+.2f}%")

            m5, m6 = st.columns(2)
            with m5:
                st.metric("回测天数", f"{s['total_days']:,}")
            with m6:
                st.metric("总选股数", f"{s['total_picks']:,}")

            # ---- 今日推荐（prev_picks：昨日选股 → 今日买入）----
            st.markdown("---")
            st.subheader("📌 今日推荐买入")
            today_picks = picker_result.prev_picks(n=top_k)
            if today_picks.empty:
                _empty_info("暂无今日推荐数据（可能昨日为非交易日或无股票满足选股条件）。")
            else:
                # 加法式健壮性：prev_picks 上游 schema 漂移可能缺列，直接下标选列会抛 KeyError
                # 导致整个 fragment 崩溃。缺列时降级提示，其余视图仍可展示。
                try:
                    display_today = today_picks[["code", "name", "score", "buy_price", "rsi2", "rsi14", "reasons"]].copy()
                    display_today.columns = ["代码", "名称", "评分", "买入价", "RSI(2)", "RSI(14)", "选股理由"]
                    st.dataframe(display_today, use_container_width=True, hide_index=True)
                except KeyError as _ke:
                    st.warning(f"今日推荐数据列结构异常，已跳过表格展示：{_ke}")
                st.caption("💡 以上为基于上一交易日收盘数据选出的股票，可在今日开盘/盘中择机买入。")

            # ---- 明日推荐（latest_picks：今日选股 → 明日买入）----
            st.markdown("---")
            st.subheader("📌 明日推荐买入")
            tomorrow_picks = picker_result.latest_picks(n=top_k)
            if tomorrow_picks.empty:
                _empty_info("暂无明日推荐数据。可尝试调大「每日选股数」或延长选股区间后重新运行选股。")
            else:
                try:
                    display_tmr = tomorrow_picks[["code", "name", "score", "buy_price", "rsi2", "rsi14", "reasons"]].copy()
                    display_tmr.columns = ["代码", "名称", "评分", "参考价", "RSI(2)", "RSI(14)", "选股理由"]
                    st.dataframe(display_tmr, use_container_width=True, hide_index=True)
                except KeyError as _ke:
                    st.warning(f"明日推荐数据列结构异常，已跳过表格展示：{_ke}")
                st.caption("💡 以上为基于今日收盘数据选出的股票，可在明日开盘/盘中择机买入。")

            # ---- 累计收益曲线 ----
            if not picker_result.returns_df.empty:
                st.markdown("---")
                st.subheader("累计收益曲线")
                import plotly.graph_objects as go
                _dark = _is_dark()
                fig = go.Figure()
                rdf = picker_result.returns_df
                fig.add_trace(go.Scatter(
                    x=rdf["date"], y=rdf["cumulative_return_pct"],
                    mode="lines+markers", name="累计收益(%)",
                    line=dict(color=UP_COLOR, width=2),
                    fill="tozeroy", fillcolor="rgba(255,77,79,0.1)",
                ))
                if _dark:
                    fig.update_layout(
                        title={"text": "每日选股组合累计收益", "font": {"color": SF_TXT, "size": 14}},
                        template="starfield_dark",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"color": SF_TXT2},
                        xaxis_title="日期", yaxis_title="累计收益(%)",
                        height=400, margin=dict(l=40, r=20, t=50, b=40),
                        xaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                                   tickfont={"color": SF_TXT2}),
                        yaxis=dict(showgrid=True, gridcolor=SF_GRID, linecolor=SF_BORDER,
                                   tickfont={"color": SF_TXT2}),
                    )
                else:
                    fig.update_layout(
                        title="每日选股组合累计收益",
                        xaxis_title="日期", yaxis_title="累计收益(%)",
                        height=400, template="plotly_white",
                        margin=dict(l=40, r=20, t=50, b=40),
                    )
                st.plotly_chart(fig, use_container_width=True)

            # ---- 全部选股记录 ----
            if not picker_result.picks_df.empty:
                st.markdown("---")
                st.subheader("全部选股记录")
                all_picks = picker_result.picks_df.copy()
                # 加法式健壮性：picks_df 上游 schema 漂移可能缺列，缺列时降级提示。
                try:
                    all_picks_display = all_picks[["date", "code", "name", "score", "buy_price", "sell_price",
                                                   "hold_return_pct", "rsi2", "rsi14", "reasons"]].copy()
                    all_picks_display.columns = ["选股日期", "代码", "名称", "评分", "买入价", "卖出价",
                                                 "持有收益(%)", "RSI(2)", "RSI(14)", "选股理由"]
                    # 加法式 UX：全部选股记录默认按选股日期倒序，最新一期排在最前
                    all_picks_display = all_picks_display.sort_values("选股日期", ascending=False)
                    st.dataframe(all_picks_display, use_container_width=True, hide_index=True)
                except KeyError as _ke:
                    st.warning(f"全部选股记录列结构异常，已跳过表格展示：{_ke}")


# ==================================================================
# 模块三：强势上涨股批量回测 vs 全市场（独立 fragment）
# ==================================================================
@safe_fragment("强势上涨股批量回测")
def fragment_strong_bull():
    st.markdown("---")
    st.subheader("🚀 强势上涨股批量回测 vs 全市场")
    st.caption("一键对「强势上涨股样本」跑多因子策略，聚合胜率/收益，并对比全市场基准，"
               "验证策略对强趋势股的覆盖度。**历史模拟，不构成投资建议。**")

    s_col1, s_col2 = st.columns(2)
    with s_col1:
        sb_start = st.date_input("样本起始日期", value=datetime.now() - timedelta(days=180), key="sb_start")
    with s_col2:
        sb_end = st.date_input("样本截止日期", value=datetime.now(), key="sb_end")
    sb_capital = st.number_input("初始资金（每只）", value=100000, step=10000, key="sb_capital")

    sb_with_market = st.checkbox(
        "同时计算全市场基准（每日选股回测，约 1–3 分钟）",
        value=False, key="sb_market",
        help="勾选后将额外运行一次全市场随机抽样回测作为对照；不勾选则复用本页『每日选股回测』结果（若有）。",
    )

    if st.button("🚀 运行强势上涨股批量回测", type="primary", key="sb_run"):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(code, name):
            try:
                r = bt.run(
                    ticker=code,
                    start=sb_start.strftime("%Y-%m-%d"),
                    end=sb_end.strftime("%Y-%m-%d"),
                    strategy="multi_factor",
                    initial_capital=sb_capital,
                    commission=0.001,
                    stop_loss_pct=0.05,
                    take_profit_pct=0.03,
                    max_holding=15,
                    min_holding=2,
                )
                s = r.summary()
                return {
                    "code": code, "name": name,
                    "win_rate": s["win_rate_pct"],
                    "total_return": s["total_return_pct"],
                    "max_dd": s["max_drawdown_pct"],
                    "trades": s["trade_count"],
                    "sharpe": s["sharpe_ratio"],
                }
            except Exception as e:
                return {"code": code, "name": name, "error": str(e)}

        # 加法式性能优化：原实现为 8 只样本串行回测（每次都拉取 ~180 天日线 + 计算），
        # 串行耗时可达数十秒。改用线程池并行，每个任务自包含 try/except 互不影响，
        # 子线程内无任何 st 调用、无共享可变状态（Backtester 仅读 config），线程安全。
        res_map = {}
        with st.spinner(f"正在对 {len(STRONG_BULL_PRESETS)} 只强势上涨股样本并行回测…"):
            with ThreadPoolExecutor(max_workers=min(8, len(STRONG_BULL_PRESETS))) as _ex:
                _futs = {_ex.submit(_run_one, code, name): code for code, name in STRONG_BULL_PRESETS}
                for _fut in as_completed(_futs):
                    _r = _fut.result()
                    res_map[_r["code"]] = _r
        results = [res_map[code] for code, _ in STRONG_BULL_PRESETS]
        st.session_state["sb_results"] = results
        st.session_state["sb_with_market"] = sb_with_market
        if sb_with_market:
            with st.spinner("正在计算全市场基准（每日选股回测）…"):
                try:
                    mkt = bt.daily_picker_backtest(
                        start=sb_start.strftime("%Y-%m-%d"),
                        end=sb_end.strftime("%Y-%m-%d"),
                        stock_pool_size=120, top_k=5, hold_days=1, max_workers=4,
                    )
                    st.session_state["sb_market"] = mkt
                    st.session_state.pop("sb_market_error", None)
                except Exception as e:
                    st.session_state["sb_market_error"] = str(e)

    results = st.session_state.get("sb_results")
    if not results:
        _empty_info("尚未运行批量回测。点击上方「🚀 运行强势上涨股批量回测」开始。")
        return

    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    avg_win = sum(r["win_rate"] for r in ok) / len(ok) if ok else 0
    avg_ret = sum(r["total_return"] for r in ok) / len(ok) if ok else 0
    avg_dd = sum(r["max_dd"] for r in ok) / len(ok) if ok else 0
    total_trades = sum(r["trades"] for r in ok) if ok else 0

    # 全市场基准：优先用本次勾选计算的结果，否则复用本页每日选股结果
    market = st.session_state.get("sb_market")
    if market is None and not st.session_state.get("sb_with_market", False):
        market = st.session_state.get("picker_result")
    market_summary = market.summary() if market is not None else None

    # ---- 对比表 ----
    st.markdown("---")
    st.subheader("📊 强势上涨股 vs 全市场 对比")
    cmp_rows = [{
        "样本": "强势上涨股样本(均值)",
        "胜率%": f"{avg_win:.1f}",
        "累计收益%": f"{avg_ret:+.2f}",
        "最大回撤%": f"{avg_dd:.2f}",
        "交易数": f"{total_trades}",
    }]
    if market_summary:
        cmp_rows.append({
            "样本": "全市场基准",
            "胜率%": f"{market_summary['win_pick_pct']:.1f}",
            "累计收益%": f"{market_summary['total_return_pct']:+.2f}",
            "最大回撤%": "—",
            "交易数": f"{market_summary['total_picks']}",
        })
    st.dataframe(pd.DataFrame(cmp_rows), use_container_width=True, hide_index=True)
    if market is None and st.session_state.get("sb_with_market", False) and "sb_market_error" in st.session_state:
        st.error(f"全市场基准计算失败: {st.session_state['sb_market_error']}")
    elif market is None:
        st.caption("💡 暂无全市场基准。可勾选上方复选框运行，或先在下方『每日选股回测』运行一次后回来查看。")

    # ---- 个股累计收益对比柱状图 ----
    if ok:
        st.markdown("---")
        st.subheader("📈 个股累计收益对比")
        fig = go.Figure()
        names = [r["name"] for r in ok]
        rets = [r["total_return"] for r in ok]
        fig.add_trace(go.Bar(
            x=names, y=rets,
            marker_color=[UP_COLOR if v > 0 else DOWN_COLOR for v in rets],
            hovertemplate="%{x}<br>累计收益：%{y:+.2f}%<extra></extra>",
        ))
        if market_summary:
            fig.add_hline(y=market_summary["total_return_pct"],
                          line_dash="dash", line_color="#2b8aef",
                          annotation_text=f"全市场基准 {market_summary['total_return_pct']:+.2f}%",
                          annotation_position="top right")
        fig.update_layout(
            title="强势上涨股样本累计收益（红涨绿跌）",
            xaxis_title="股票", yaxis_title="累计收益%",
            height=380,
            template="plotly_white" if not _is_dark() else "plotly_dark",
            margin=dict(l=50, r=20, t=50, b=80),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ---- 个股卡片 ----
        st.markdown("---")
        st.subheader("🧾 个股回测明细")
        cards = st.columns(min(4, len(ok)))
        for i, r in enumerate(ok):
            with cards[i % len(cards)]:
                ret_color = "🔴" if r["total_return"] >= 0 else "🟢"
                st.markdown(f"**{r['name']}** `{r['code']}`")
                st.metric(f"{ret_color} 累计收益", f"{r['total_return']:+.2f}%")
                st.caption(f"胜率 {r['win_rate']:.1f}% · 回撤 {r['max_dd']:.2f}% · 交易 {r['trades']}")

    if failed:
        st.markdown("---")
        st.warning("以下样本回测失败（已跳过）：" + "、".join(f"{r['name']}({r['code']})" for r in failed))
        for r in failed:
            st.caption(f"{r['name']} {r['code']}：{r['error']}")


# ==================================================================
# 调用三个独立模块
# ==================================================================
fragment_manual_backtest()
fragment_daily_picker()
fragment_strong_bull()
