"""页面 76：实时强势榜 Top N（G8）

对标钱来终端的「实时榜」：Top N 自动刷新 + 奖牌图标 + 评分进度条（视觉化排序）。

差异化：在纯涨幅排序之上叠加**多因子强势评分**（涨幅/量比/换手/成交额），
按 A 股习惯红涨绿跌呈现；奖项只给前 3，其余按分数降序。

数据源与评分逻辑见 ``modules.spot_rank``（东财实时快照，缓存 60s）。
盘中（09:30-15:00）每 60 秒自动刷新（Streamlit 无 SSE，用 st_autorefresh 轮询近似）。

诚实性红线：
  · 评分为启发式加权，非预测模型；高换手/高量比亦伴随高波动风险；
  · 取不到快照时明示「未就绪」，绝不用陈旧数据假装「实时」。
"""
from __future__ import annotations

import logging

from modules.colors import UP_COLOR, DOWN_COLOR, _hex_to_rgba
from modules.page_utils import render_standard_page, import_autorefresh
from modules.spot_rank import _col, _num, load_spot, strong_score
import streamlit as st

logger = logging.getLogger(__name__)


def _score_bar(label, value, color):
    pct = max(0.0, min(100.0, float(value or 0)))
    return (
        "<div style='margin:3px 0'>"
        "<div style='display:flex;justify-content:space-between;font-size:11px;margin-bottom:1px'>"
        f"<span style='opacity:.75'>{label}</span>"
        f"<span style='color:{color};font-weight:700'>{pct:.0f}</span></div>"
        f"<div style='height:6px;background:{_hex_to_rgba(color,0.16)};border-radius:4px'>"
        f"<span style='display:block;height:100%;width:{pct:.1f}%;background:{color};border-radius:4px'></span>"
        "</div></div>"
    )


dark = render_standard_page(
    title="实时强势榜", icon="🏅",
    caption="全市场多因子强势 Top N：涨幅 0.40 + 量比 0.30 + 换手 0.20 + 成交额 0.10"
            "（启发式，非预测）。盘中每 60 秒自动刷新。数据源东财实时快照。",
)

_top_n = st.select_slider("显示数量", options=[10, 20, 30, 50], value=20, key="strong_n")
_only_up = st.toggle("仅看上涨", value=True, key="strong_up")

try:
    raw = load_spot()
except Exception as e:  # noqa: BLE001
    logger.warning(f"[strong-rank] 快照获取失败: {e}")
    st.error("⚠️ 实时行情快照获取失败（网络不可用或接口异常），请稍后重试。")
    st.stop()

if raw is None or raw.empty:
    st.info("📭 实时行情快照未就绪（可能非交易时段或接口暂不可用）。")
    st.stop()

df = strong_score(raw)
if _only_up:
    df = df[_num(df, "chg") > 0]
df = df.sort_values("_score", ascending=False).head(int(_top_n))

name_c, code_c = _col(df, "name"), _col(df, "code")
price_c, chg_c = _col(df, "price"), _col(df, "chg")

# 盘中自动刷新（无 SSE，轮询近似）
st_autorefresh = import_autorefresh()
try:
    from modules.page_widgets import is_trading_now
    _trading = is_trading_now()
except Exception:  # noqa: BLE001
    _trading = False
if st_autorefresh is not None and _trading:
    st_autorefresh(interval=60000, limit=240, key="strong_auto")

st.caption(f"共 {len(df)} 只（{'盘中 60s 自动刷新' if (_trading and st_autorefresh) else '静态'}）"
           " · 评分为启发式加权，非预测")

MEDALS = {0: "🥇", 1: "🥈", 2: "🥉"}
if name_c and len(df) > 0:
    rows_html = ""
    for i, (_, r) in enumerate(df.reset_index(drop=True).iterrows()):
        nm = str(r.get(name_c, ""))
        cd = str(r.get(code_c, "")) if code_c else ""
        price = r.get(price_c) if price_c else None
        chg = r.get(chg_c) if chg_c else None
        chg_f = float(chg) if chg == chg and chg is not None else 0.0
        cc = UP_COLOR if chg_f >= 0 else DOWN_COLOR
        sc = float(r["_score"])
        sc_color = UP_COLOR if sc >= 75 else ("#f59e0b" if sc >= 50 else "#94a3b8")
        medal = MEDALS.get(i, f"{i + 1:>2}")
        price_txt = f"价 {float(price):.2f}" if (price is not None and price == price) else ""
        bars = (
            _score_bar("涨幅", r["_s_chg"], "#dc2626")
            + _score_bar("量比", r["_s_vr"], "#f97316")
            + _score_bar("换手", r["_s_to"], "#8b5cf6")
            + _score_bar("成交额", r["_s_amt"], "#0ea5e9")
        )
        rows_html += (
            "<div style='border:1px solid rgba(148,163,184,.25);border-radius:12px;"
            "padding:9px 12px;margin:7px 0;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><span style='font-size:14px'>{medal}</span> "
            f"<span style='font-weight:700;font-size:15px'>{nm}</span> "
            f"<span style='opacity:.6;font-size:12px'>{cd}</span></div>"
            "<div style='text-align:right'>"
            f"<span style='font-size:13px;font-weight:700;color:{cc}'>{chg_f:+.2f}%</span> "
            f"<span style='font-size:18px;font-weight:800;color:{sc_color};margin-left:8px'>{sc:.1f}</span>"
            f"<div style='font-size:11px;opacity:.6'>{price_txt}</div></div></div>"
            f"<div style='margin-top:5px'>{bars}</div></div>"
        )
    st.markdown(rows_html, unsafe_allow_html=True)
else:
    st.info("无符合条件的标的。")

st.caption("⚠️ 说明：本榜为启发式强势评分排序，非预测模型，不构成投资建议；"
           "高换手/高量比亦伴随高波动风险。实时快照经 60 秒缓存，盘中读数可能有延迟。")
