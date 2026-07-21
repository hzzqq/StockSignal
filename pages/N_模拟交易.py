"""
模拟交易组合（Paper Trading）
--------------------------------
一个完全自包含的模拟交易模块：用虚拟资金买卖 A 股，跟踪持仓、盈亏与净值曲线。

  • 持仓 / 成交记录持久化到本地 data/paper_{user}.json（刷新不丢失，模块独立运行）
  • 现价取自实时行情，失败降级到日线收盘价
  • 支持买入 / 卖出 / 重置账户，展示总资产、累计盈亏、胜率与净值曲线

不接入真实券商，仅用于策略演练与学习。
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime

from modules.ui_theme import apply_page_config, dashboard_sf_css, _theme_is_dark
from modules.session import require_auth, render_user_badge, get_user, trading_autorefresh
from modules.fetcher import StockFetcher
from modules.page_guard import safe_section, safe_fragment
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast, UP, DOWN

apply_page_config(page_title="模拟交易", page_icon="🎮", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)
dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)
st.title("🎮 模拟交易组合")
st.caption("虚拟资金练习；持仓持久化到本地，模块独立运行，不影响真实账户。")

FETCHER = StockFetcher()
INIT_CASH = 1_000_000.0
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _book_path(user):
    return os.path.join(DATA_DIR, f"paper_{user}.json")


def _load_book(user):
    p = _book_path(user)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"init_cash": INIT_CASH, "cash": INIT_CASH, "positions": {}, "trades": [], "equity": []}


def _save_book(user, book):
    json.dump(book, open(_book_path(user), "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def _snapshot(book, assets):
    """记录一个净值快照（按分钟去重），用于绘制净值曲线。"""
    t = datetime.now().strftime("%Y-%m-%d %H:%M")
    eq = book.setdefault("equity", [])
    if eq and eq[-1][0] == t:
        eq[-1] = (t, round(assets, 2))
    else:
        eq.append((t, round(assets, 2)))
    if len(eq) > 500:
        eq[:] = eq[-500:]


@st.cache_data(ttl=20, show_spinner=False)
def _price(code):
    try:
        q = FETCHER.get_realtime_quote(code)
        if q and q.get("current"):
            return float(q["current"]), q.get("name") or code
    except Exception:
        pass
    try:
        d = FETCHER.get_daily(code, start="2024-01-01")
        if d is not None and not d.empty:
            return float(d.iloc[-1]["close"]), FETCHER.get_name_only(code)
    except Exception:
        pass
    return None, code


def _recompute(book):
    total_mv = 0.0
    rows = []
    for code, pos in book["positions"].items():
        price, name = _price(code)
        price = price if price is not None else pos["avg_cost"]
        qty = pos["qty"]
        mv = price * qty
        cost = pos["avg_cost"] * qty
        pnl = mv - cost
        total_mv += mv
        rows.append({
            "代码": code, "名称": name, "持仓(股)": qty,
            "成本价": round(pos["avg_cost"], 2), "现价": round(price, 2),
            "市值": round(mv, 2),
            "盈亏": round(pnl, 2),
            "盈亏%": round((price / pos["avg_cost"] - 1) * 100, 2) if pos["avg_cost"] else 0.0,
        })
    assets = book["cash"] + total_mv
    return rows, assets, total_mv


@safe_fragment("模拟交易")
def fragment_paper():
    trading_autorefresh(key="paper_autorefresh")
    user = (get_user() or {}).get("username", "guest")
    book = _load_book(user)

    with safe_section("账户概览"):
        rows, assets, mv = _recompute(book)
        pnl_total = assets - book["init_cash"]
        pnl_pct = pnl_total / book["init_cash"] * 100
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总资产", f"¥{assets:,.0f}")
        c2.metric("可用现金", f"¥{book['cash']:,.0f}")
        c3.metric("持仓市值", f"¥{mv:,.0f}")
        c4.metric("累计盈亏", f"¥{pnl_total:,.0f}", delta=f"{pnl_pct:+.2f}%")

    # ───────────────────────── 交易操作 ─────────────────────────
    st.markdown("---")
    st.subheader("💱 交易")
    col_b, col_s = st.columns(2)
    with col_b:
        st.markdown("**买入**")
        bcode = stock_search_input("买入标的", key="pt_buy")
        bqty = st.number_input("买入股数", min_value=100, step=100, value=100, key="pt_bqty")
        if st.button("确认买入", type="primary", key="pt_buy_btn", use_container_width=True):
            code = (bcode or "").strip().zfill(6)
            if len(code) != 6 or not code.isdigit():
                st.error("请输入有效的 6 位股票代码。")
            else:
                price, name = _price(code)
                if price is None:
                    st.error("无法获取现价，买入失败。")
                else:
                    cost = price * bqty
                    if cost > book["cash"]:
                        st.error(f"现金不足：需要 ¥{cost:,.0f}，可用 ¥{book['cash']:,.0f}。")
                    else:
                        book["cash"] -= cost
                        pos = book["positions"].get(code)
                        if pos:
                            tot_qty = pos["qty"] + bqty
                            pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + cost) / tot_qty
                            pos["qty"] = tot_qty
                        else:
                            book["positions"][code] = {"name": name, "qty": bqty, "avg_cost": price}
                        book["trades"].append({
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "code": code,
                            "name": name, "side": "买", "price": round(price, 2), "qty": bqty,
                            "amount": round(cost, 2),
                        })
                        rows, assets, mv = _recompute(book)
                        _snapshot(book, assets)
                        _save_book(user, book)
                        _toast(f"已买入 {name}({code}) {bqty} 股 @ ¥{price:.2f}")
    with col_s:
        st.markdown("**卖出**")
        scode = stock_search_input("卖出标的", key="pt_sell")
        sqty = st.number_input("卖出股数", min_value=100, step=100, value=100, key="pt_sqty")
        if st.button("确认卖出", key="pt_sell_btn", use_container_width=True):
            code = (scode or "").strip().zfill(6)
            pos = book["positions"].get(code)
            if not pos:
                st.error("当前未持有该标的。")
            elif sqty > pos["qty"]:
                st.error(f"持仓不足：持有 {pos['qty']} 股。")
            else:
                price, name = _price(code)
                if price is None:
                    st.error("无法获取现价，卖出失败。")
                else:
                    proceeds = price * sqty
                    book["cash"] += proceeds
                    pos["qty"] -= sqty
                    if pos["qty"] <= 0:
                        del book["positions"][code]
                    book["trades"].append({
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "code": code,
                        "name": name, "side": "卖", "price": round(price, 2), "qty": sqty,
                        "amount": round(proceeds, 2),
                    })
                    rows, assets, mv = _recompute(book)
                    _snapshot(book, assets)
                    _save_book(user, book)
                    _toast(f"已卖出 {name}({code}) {sqty} 股 @ ¥{price:.2f}")

    # ───────────────────────── 持仓 / 成交 / 净值 ─────────────────────────
    st.markdown("---")
    tab_p, tab_t, tab_e = st.tabs(["📦 当前持仓", "🧾 成交记录", "📈 净值曲线"])

    with tab_p:
        if rows:
            dfp = pd.DataFrame(rows)
            # 盈亏着色
            def _color_row(r):
                c = UP if r["盈亏"] >= 0 else DOWN
                return [f"color:{c}"] * len(r)
            st.dataframe(dfp.style.apply(_color_row, axis=1), use_container_width=True, hide_index=True)
        else:
            _empty_info("暂无持仓。先在上方搜索框输入代码（如 600519 贵州茅台），设置数量后点「买入」开始你的第一笔模拟交易。")

    with tab_t:
        if book["trades"]:
            dft = pd.DataFrame(book["trades"])
            st.dataframe(dft, use_container_width=True, hide_index=True)
        else:
            _empty_info("暂无成交记录。买入成功后，这里会逐笔显示你的成交明细。")

    with tab_e:
        # 净值曲线：基于每笔成交后的总资产快照绘制
        eq = [("起始", book["init_cash"])] + book.get("equity", [])
        if len(eq) >= 2:
            xs = [e[0] for e in eq]
            ys = [e[1] for e in eq]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name="总资产",
                                     line=dict(color=UP if ys[-1] >= book["init_cash"] else DOWN, width=2)))
            fig.add_hline(y=book["init_cash"], line_dash="dot", line_color="#888",
                          annotation_text="初始资金", annotation_position="bottom right")
            fig.update_layout(height=360, template="plotly_dark" if dark else "plotly_white",
                              xaxis_title="时间", yaxis_title="总资产(元)",
                              margin=dict(t=20, l=60, r=20, b=40))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("完成至少一笔交易后生成净值曲线。")
        st.caption("💡 在上方「💱 交易」买入或卖出后，这里会基于每笔成交后的总资产快照绘制净值曲线。")

    st.markdown("---")
    if st.button("🗑️ 重置模拟账户", key="pt_reset", help="清空持仓与成交，恢复初始资金"):
        if st.confirm("确定重置？此操作不可撤销。"):
            book = {"init_cash": INIT_CASH, "cash": INIT_CASH, "positions": {}, "trades": [], "equity": []}
            _save_book(user, book)
            _toast("账户已重置。")


fragment_paper()
