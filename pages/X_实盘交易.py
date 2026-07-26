"""
页面 X：实盘交易
────────────────
接入真实券商 / 模拟账本的「实盘账户 + 手动下单」入口。

⚠️ 安全护栏（必须阅读）：
  - 默认 broker_type=sim → 所有下单走「模拟账本」（SimulatedBroker），不碰真实资金；
  - 仅当用户显式选择 qmt / easytrader 并开启 live_mode 时，才会尝试真实下单；
  - live_mode 开启前若未配置真实券商，后端会拒绝开启；
  - 每笔下单前过风控（交易时段 / 单笔金额上限 / 当日亏损停手线）；
  - 所有订单（成功 / 拒绝 / 失败）均写 real_orders 流水，可审计。

本页只调用 Flask 后端 /api/trade/*，绝不直连任何券商或 MCP 连接器。
"""
import json
from datetime import datetime, timedelta

import streamlit as st
from modules.ui_theme import (
    apply_page_config, dashboard_sf_css, _theme_is_dark,
)
from modules.session import (
    require_auth, render_user_badge,
    api_get, api_post, api_put,
    trading_autorefresh,
)
from modules.search_ui import stock_search_input
from modules.page_widgets import _empty_info, _toast
from modules.page_guard import safe_fragment
from modules.format_helpers import safe_int

apply_page_config(page_title="实盘交易", page_icon="💰", layout="wide")
st.session_state["_active_page"] = __file__
require_auth()
render_user_badge(sidebar=True)

dark = _theme_is_dark()
st.markdown(dashboard_sf_css(), unsafe_allow_html=True)

st.title("💰 实盘交易")
st.caption("真实券商 / 模拟账本 下单入口 · 全量订单落库可审计")
st.warning(
    "⚠️ **资金安全提示**：默认「模拟账本」模式仅做虚拟撮合、**不涉及真实资金**。\n"
    "只有当您在下方选择真实券商（QMT / 同花顺客户端）并显式开启「实盘模式」后，"
    "系统才会尝试真实下单——请务必确认券商配置与策略无误再开启。",
    icon="🔒",
)

# 同步：后端如果使用 akshare 经本地代理（行情/名称解析），确保代理环境生效
try:
    from modules.fundflow import _ensure_proxy_and_ssl
    _ensure_proxy_and_ssl()
except Exception:
    pass


# ─────────────────────────────── 账户总览 + 配置
def _load_account() -> dict | None:
    sc, body = api_get("/api/trade/account")
    if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
        return body.get("data") or {}
    return None


acc = _load_account()
if acc is None:
    _empty_info("账户加载失败，请稍后重试或刷新页面。")
    if st.button("🔄 重试加载账户", key="acc_retry"):
        st.rerun()
    st.stop()

live = bool(acc.get("live_mode"))
bt = acc.get("broker_type", "sim") or "sim"

# 账户总览指标卡
c_broker, c_mode, c_cash, c_assets, c_loss = st.columns(5)
with c_broker:
    st.metric("券商通道", {"sim": "模拟账本", "qmt": "QMT", "easytrader": "同花顺客户端"}.get(bt, bt))
with c_mode:
    st.metric("当前模式",
              "🟢 实盘" if live else "⚪ 模拟",
              help="实盘模式：触发真实资金下单")
with c_cash:
    st.metric("可用资金", f"¥{float(acc.get('cash') or 0):,.0f}")
with c_assets:
    st.metric("总资产", f"¥{float(acc.get('total_assets') or 0):,.0f}")
with c_loss:
    paused = acc.get("risk_paused_date")
    today = datetime.now().strftime("%Y-%m-%d")
    label = "已停手" if paused == today else f"¥{float(acc.get('daily_loss_limit') or 0):,.0f}"
    st.metric("当日亏损停手线", label,
              help="当日资金净流出异常时自动停手（可在配置区手动解除）")


# ─────────────────────────────── 配置区
st.markdown("#### ⚙️ 账户配置")
with st.container(border=True):
    col_cfg1, col_cfg2 = st.columns([1.4, 1])
    with col_cfg1:
        broker_type = st.selectbox(
            "券商通道", ["sim", "qmt", "easytrader"],
            index=["sim", "qmt", "easytrader"].index(bt),
            format_func=lambda x: {
                "sim": "模拟账本（默认，虚拟撮合）",
                "qmt": "QMT（迅投极速交易）",
                "easytrader": "同花顺客户端（easytrader）",
            }[x],
            help="选择 QMT / 同花顺客户端 后需填写连接参数并开启实盘模式",
        )
        live_mode = st.toggle(
            "开启实盘模式（真实下单）", value=live,
            help="⚠️ 开启后将以真实资金下单！仅当已正确配置真实券商时启用。",
        )

    with col_cfg2:
        max_order_amount = st.number_input(
            "单笔金额上限 (元)", min_value=1000.0, step=1000.0,
            value=float(acc.get("max_order_amount") or 50000.0),
            help="单笔委托金额超过该值将被风控拒绝",
        )
        daily_loss_limit = st.number_input(
            "当日亏损停手线 (元)", min_value=1000.0, step=1000.0,
            value=float(acc.get("daily_loss_limit") or 20000.0),
            help="当日净流出触发该线后自动停手（保守保护）",
        )

    # 券商连接参数
    cfg = acc.get("broker_config") or {}
    if broker_type in ("qmt", "easytrader"):
        st.markdown("**券商连接参数**")
        cc1, cc2 = st.columns(2)
        if broker_type == "qmt":
            with cc1:
                qmt_path = st.text_input(
                    "QMT 客户端路径", value=str(cfg.get("qmt_path") or ""),
                    placeholder="如 C:/国金QMT/userdata_mini",
                    help="QMT 客户端 userdata_mini 目录",
                )
            with cc2:
                account_id = st.text_input(
                    "资金账号", value=str(cfg.get("account_id") or ""),
                    placeholder="您的券商资金账号",
                )
            broker_config = {"qmt_path": qmt_path, "account_id": account_id}
        else:
            with cc1:
                use = st.text_input(
                    "客户端类型", value=str(cfg.get("use") or "ths"),
                    placeholder="ths / universal / joinquant",
                    help="easytrader 的客户端标识",
                )
                exe_path = st.text_input(
                    "客户端 exe 路径", value=str(cfg.get("exe_path") or ""),
                    placeholder="如 C:/同花顺/xiadan.exe",
                )
            with cc2:
                prepare_file = st.text_input(
                    "自动登录配置文件", value=str(cfg.get("prepare_file") or ""),
                    placeholder="可选，自动登录 prepare 文件",
                )
                # 密码框：默认占位，后端对 ****** 不覆盖旧值
                old_pwd = cfg.get("password", "")
                pwd_placeholder = old_pwd if old_pwd and old_pwd != "******" else "******"
                password = st.text_input(
                    "交易密码", value=pwd_placeholder, type="password",
                    help="留空或保持 ****** 表示沿用已保存密码",
                )
            broker_config = {
                "use": use, "exe_path": exe_path,
                "prepare_file": prepare_file, "password": password,
            }
        st.caption("⚠️ 密码以 ****** 显示；如要沿用已保存密码，请勿修改此框。")
    else:
        broker_config = None

    col_save, col_health, col_clear = st.columns([1, 1, 1])
    save_msg = None
    with col_save:
        if st.button("💾 保存配置", type="primary", use_container_width=True):
            payload = {
                "broker_type": broker_type,
                "live_mode": live_mode,
                "max_order_amount": max_order_amount,
                "daily_loss_limit": daily_loss_limit,
            }
            if broker_config is not None:
                # 密码未改动（仍是 ******）时不覆盖旧值：后端已处理，这里直接传
                payload["broker_config"] = broker_config
            sc, body = api_put("/api/trade/account", payload)
            if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                _toast("配置已保存")
                st.session_state["_trade_acc_cache"] = None
                st.rerun()
            else:
                msg = body.get("message", "保存失败") if isinstance(body, dict) else "保存失败"
                save_msg = f"❌ {msg}"
    with col_health:
        if st.button("🔌 券商通道自检", use_container_width=True):
            sc, body = api_post("/api/trade/account/health")
            if sc == 200 and isinstance(body, dict):
                d = (body.get("data") or {}) if body.get("status") == "ok" else None
                if d is None:
                    d = body.get("data") or {}
                ok_flag = d.get("ok", False)
                st.success(f"✅ {d.get('message','通道可用')}") if ok_flag else st.error(f"❌ {d.get('message','通道不可用')}")
            else:
                st.error("自检失败")
    with col_clear:
        if st.button("🟢 解除当日停手", use_container_width=True,
                     help="手动清除当日亏损停手标记"):
            sc, body = api_put("/api/trade/account", {"clear_risk_pause": True})
            if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                _toast("已解除停手")
                st.rerun()
            else:
                st.error("操作失败")
    if save_msg:
        st.error(save_msg)

st.divider()


# ─────────────────────────────── 手动下单
st.markdown("#### 📝 手动下单")
with st.container(border=True):
    o1, o2, o3, o4 = st.columns([1.4, 0.8, 0.8, 1])
    with o1:
        order_code = stock_search_input(label="选择股票", key="trade_order_stock", default="600519")
    with o2:
        side = st.selectbox("方向", ["buy", "sell"],
                            format_func=lambda x: "买入 ▲" if x == "buy" else "卖出 ▼")
    with o3:
        quantity = st.number_input("数量 (股)", min_value=100, step=100, value=100,
                                   help="须为 100 的整数倍")
    with o4:
        price = st.number_input("限价 (元，0=市价)", min_value=0.0, step=0.01, value=0.0)
    if st.button("🚀 提交委托", type="primary", use_container_width=True, key="trade_submit"):
        if not order_code:
            st.error("请选择股票")
        elif quantity <= 0 or quantity % 100 != 0:
            st.error("数量须为 100 的整数倍")
        else:
            name = ""
            try:
                from modules.fetcher import StockFetcher
                name = StockFetcher().get_name_only(order_code) or ""
            except Exception:
                pass
            payload = {
                "stock_code": order_code, "stock_name": name,
                "side": side, "quantity": int(quantity),
                "price": price if price > 0 else None,
            }
            sc, body = api_post("/api/trade/orders", payload)
            if sc == 200 and isinstance(body, dict) and body.get("status") == "ok":
                od = body.get("data") or {}
                if od.get("status") == "rejected":
                    st.warning(f"⚠️ 被风控拦截：{od.get('message','')}")
                elif od.get("status") == "failed":
                    st.error(f"❌ 下单失败：{od.get('message','')}")
                else:
                    _toast(f"委托已受理（{od.get('status')}）")
                st.rerun()
            else:
                msg = body.get("message", "下单失败") if isinstance(body, dict) else "下单失败"
                st.error(f"❌ {msg}")

st.divider()


# ─────────────────────────────── 持仓（fragment + 交易时段自动刷新）
@st.fragment
def fragment_positions():
    trading_autorefresh(key="trade_pos_autorefresh")
    sc, body = api_get("/api/trade/positions")
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("⚠️ 持仓加载失败")
        return
    rows = body.get("data", []) or []
    st.markdown(f"#### 📦 当前持仓（{len(rows)}）")
    if not rows:
        _empty_info("暂无持仓。手动买入成交后会出现在这里（模拟账本下为虚拟持仓）。")
        return
    for p in rows:
        code = p.get("stock_code", "")
        name = p.get("stock_name") or code
        qty = safe_int(p.get("quantity"), 0)
        mv = float(p.get("market_value") or 0)
        pnl = float(p.get("pnl") or 0)
        pnl_pct = float(p.get("pnl_pct") or 0)
        color = "#ff4d4f" if pnl >= 0 else "#00d486"
        with st.container(border=True):
            cc1, cc2, cc3, cc4 = st.columns([1.4, 1, 1, 1])
            with cc1:
                st.markdown(f"**{name}** `{code}`")
                st.caption(f"持仓 {qty} 股 · 可卖 {int(p.get('available') or 0)} 股")
            with cc2:
                st.markdown(f"成本价 {float(p.get('avg_cost') or 0):.3f}")
                st.caption(f"现价 {float(p.get('last_price') or 0):.3f}")
            with cc3:
                st.markdown(f"市值 ¥{mv:,.0f}")
            with cc4:
                st.markdown(f"<span style='color:{color};font-weight:700;'>"
                            f"{'+' if pnl >= 0 else ''}{pnl:,.0f} ({pnl_pct:+.2f}%)</span>",
                            unsafe_allow_html=True)


# ─────────────────────────────── 订单流水
@st.fragment
def fragment_orders():
    trading_autorefresh(key="trade_orders_autorefresh")
    sc, body = api_get("/api/trade/orders")
    if sc != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        st.error("⚠️ 订单加载失败")
        return
    rows = body.get("data", []) or []
    st.markdown(f"#### 🧾 订单流水（{len(rows)}）")
    if not rows:
        _empty_info("暂无订单。提交委托并成交后会出现在这里。")
        return
    for o in rows:
        code = o.get("stock_code", "")
        name = o.get("stock_name") or code
        side = o.get("side")
        status = o.get("status")
        mode = o.get("mode")
        src = o.get("source")
        st_color = "#ff4d4f" if side == "buy" else "#00d486"
        status_cls = {
            "filled": "sf-pill up",
            "rejected": "sf-pill down",
            "failed": "sf-pill down",
            "submitted": "sf-pill mid",
        }.get(status, "sf-pill mid")
        with st.container(border=True):
            cm1, cm2, cm3, cm4 = st.columns([1.4, 1, 1, 1.4])
            with cm1:
                st.markdown(f"**{name}** `{code}`")
                st.caption(f"{'买入' if side=='buy' else '卖出'} {int(o.get('quantity') or 0)} 股 "
                           f"@ {float(o.get('price') or 0):.3f}")
            with cm2:
                st.markdown(f"<span style='color:{st_color};font-weight:700;'>"
                            f"{'买入▲' if side=='buy' else '卖出▼'}</span>", unsafe_allow_html=True)
                st.caption(f"金额 ¥{float(o.get('amount') or 0):,.0f}")
            with cm3:
                st.markdown(f"<span class='{status_cls}'>{status}</span>", unsafe_allow_html=True)
                st.caption("实盘" if mode == "live" else "模拟")
            with cm4:
                st.caption(f"来源：{'条件单' if src=='conditional' else '手动'}"
                           + (f" · #{o.get('cond_order_id')}" if o.get('cond_order_id') else ""))
                msg = o.get("message")
                if msg:
                    st.caption(f"ℹ️ {msg}")


fragment_positions()
st.divider()
fragment_orders()

if st.button("↑ 回到顶部", key="trade_back_to_top"):
    st.components.v1.html("<script>window.scrollTo({top:0,behavior:'smooth'});</script>", height=0, scrolling=False)
