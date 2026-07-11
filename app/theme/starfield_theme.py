"""
星辰决策仪表盘 · Streamlit 风格复刻（v2 · 暗夜修正版）
=====================================================
修复三处不满（来自 ks空间 StockSignal 反馈）：
  1. 方框/K线发白  → Plotly/ECharts 统一暗色模板，K线用红涨绿跌（A股）
  2. 卡片与布局     → 间距/圆角/留白收紧，加微光描边
  3. 图表风格       → 坐标轴/网格线统一 --border，标签用 --txt2

⚠️ 涨跌配色（A股默认：红涨绿跌）
   想切回 compare-analysis 的「绿涨红跌」，把下面两行对调即可：
      UP_COLOR   = "#00d4aa"   # 涨·绿
      DOWN_COLOR = "#ff4757"   # 跌·红

本地预览：streamlit run starfield_theme.py
移植：放进 StockSignal（如 app/theme/），页面里
    from starfield_theme import *
    inject_theme()                 # 每个页面顶部调一次
    inject_plotly_dark()           # 若用 Plotly，再调一次
    fig = kline_plotly(...)        # 画K线
    st.plotly_chart(fig, use_container_width=True)
"""

# ===== 涨跌配色（A股默认：红涨绿跌）=====
# 改一行即切回「绿涨红跌」：UP_COLOR="#00d4aa"; DOWN_COLOR="#ff4757"
UP_COLOR = "#ff4d4f"    # 涨 · 红
DOWN_COLOR = "#00d486"  # 跌 · 绿

import json
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# 主题 CSS —— 直接注入即可生效
# ---------------------------------------------------------------------------
STARFIELD_CSS = """
<style>
:root{
  --bg:#0f0f23; --card:#1a1a2e; --buy:#ff4d4f; --sell:#00d486;
  --hold:#ffa502; --acc1:#667eea; --acc2:#764ba2;
  --txt:#e2e8f0; --txt2:#94a3b8; --border:#2d2d44; --grid:#23233c;
}
/* 整页强制暗色底（覆盖 Streamlit 默认浅色） */
.stApp{background:var(--bg)!important}
.block-container{padding-top:1.1rem;max-width:1180px;padding-left:1.4rem;padding-right:1.4rem}

.sf-header{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;margin-bottom:20px;padding:16px 20px;
  background:linear-gradient(90deg,#1a1a2e,#241b3a);
  border:1px solid var(--border);border-radius:16px;
  box-shadow:0 0 0 1px rgba(102,126,234,.08),0 8px 24px rgba(0,0,0,.35)}
.sf-brand{font-size:15px;color:var(--txt2);letter-spacing:1px}
.sf-brand b{color:var(--acc1)}

.sf-card{background:var(--card);border:1px solid var(--border);
  border-radius:16px;padding:20px;margin-top:18px;
  box-shadow:0 0 0 1px rgba(102,126,234,.06),0 6px 20px rgba(0,0,0,.28)}
.sf-card h2{font-size:16px;margin:0 0 14px;display:flex;align-items:center;gap:8px;
  padding-bottom:10px;border-bottom:1px solid var(--border)}
.sf-card h2::before{content:"";width:4px;height:16px;
  background:linear-gradient(180deg,var(--acc1),var(--acc2));border-radius:3px}

.sf-one-line{font-size:14.5px;font-weight:700;color:var(--buy);
  background:rgba(255,77,79,.08);border-left:3px solid var(--buy);
  padding:10px 14px;border-radius:8px;margin-bottom:14px;line-height:1.7}
.sf-one-line.hold{color:var(--hold);border-left-color:var(--hold);
  background:rgba(255,165,2,.08)}

.sf-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}
.sf-table th,.sf-table td{padding:9px 8px;text-align:center;border-bottom:1px solid var(--border)}
.sf-table th{color:var(--txt2);font-weight:600;font-size:12px;background:#15152a}
.sf-table tr:hover td{background:rgba(102,126,234,.05)}
.sf-table td.l{text-align:left}
.sf-up{color:var(--buy);font-weight:700}
.sf-down{color:var(--sell);font-weight:700}

.sf-tag{display:inline-block;font-size:11px;padding:2px 9px;border-radius:14px;
  font-weight:600;margin:2px}
.sf-tag.win{background:rgba(0,212,170,.16);color:#00d4aa;border:1px solid rgba(0,212,170,.4)}
.sf-tag.mid{background:rgba(255,165,2,.16);color:var(--hold);border:1px solid rgba(255,165,2,.4)}
.sf-tag.weak{background:rgba(255,77,79,.14);color:var(--buy);border:1px solid rgba(255,77,79,.4)}
.sf-tag.neu{background:rgba(148,163,184,.12);color:var(--txt2);border:1px solid var(--border)}

.sf-vs{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}
@media(max-width:780px){.sf-vs{grid-template-columns:1fr}}
.sf-vsbox{background:#15152a;border:1px solid var(--border);border-radius:12px;padding:14px}
.sf-vsbox h3{font-size:14px;margin-bottom:8px}
.sf-verdict{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}
.sf-verdict.b{background:rgba(0,212,170,.12);color:#00d4aa}
.sf-verdict.o{background:rgba(255,165,2,.12);color:var(--hold)}
.sf-vsbox ul{margin:6px 0 0 16px;font-size:12.5px;color:var(--txt2)}
.sf-vsbox ul li{margin:3px 0}

.sf-alert{border-radius:12px;padding:12px 14px;margin-top:14px;font-size:13px;line-height:1.7}
.sf-alert.risk{background:rgba(255,77,79,.10);border:1px solid rgba(255,77,79,.45);color:#ffb3bb}
.sf-alert.cat{background:rgba(0,212,170,.10);border:1px solid rgba(0,212,170,.45);color:#9af0dd}
.sf-alert b{display:block;margin-bottom:4px;font-size:13.5px}

.sf-note{font-size:12.5px;color:var(--txt2);margin-top:10px;line-height:1.7}
.sf-disclaimer{margin-top:14px;font-size:11.5px;color:#6b7280;
  border-top:1px dashed var(--border);padding-top:10px}
</style>
"""

# Plotly 暗色模板：修复白底/白网格/白K线（方框发白的根因）
PLOTLY_DARK = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#94a3b8", "family": "system-ui, -apple-system, 'PingFang SC', sans-serif"},
    "xaxis": {"gridcolor": "#23233c", "zerolinecolor": "#2d2d44",
              "linecolor": "#2d2d44", "tickcolor": "#2d2d44",
              "title": {"font": {"color": "#94a3b8"}}},
    "yaxis": {"gridcolor": "#23233c", "zerolinecolor": "#2d2d44",
              "linecolor": "#2d2d44", "tickcolor": "#2d2d44",
              "title": {"font": {"color": "#94a3b8"}}},
    "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#94a3b8"}},
}


def inject_theme():
    """每个页面顶部调用一次，注入主题样式。"""
    st.markdown(STARFIELD_CSS, unsafe_allow_html=True)


def inject_plotly_dark():
    """若页面用到 Plotly（st.plotly_chart / K线），调用一次本函数
    让 Plotly 默认走暗色，根除白底白框。"""
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
        if "starfield_dark" not in pio.templates:
            pio.templates["starfield_dark"] = go.layout.Template(layout=PLOTLY_DARK)
        pio.templates.default = "starfield_dark"
    except Exception:
        pass  # 没装 plotly 也不影响其余组件


# ---------------------------------------------------------------------------
# 文本组件
# ---------------------------------------------------------------------------
def header(brand, subtitle, meta):
    st.markdown(
        f"""<div class="sf-header">
          <div>
            <div class="sf-brand">★ <b>{brand}</b></div>
            <div style="font-size:12px;color:var(--txt2);margin-top:4px">{subtitle}</div>
          </div>
          <div style="font-size:12px;color:var(--txt2)">{meta}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def card(title, body_html, tags_items=None):
    tag_html = ""
    if tags_items:
        chips = "".join(
            f'<span class="sf-tag {k}">{t}</span>' for t, k in tags_items
        )
        tag_html = f'<div style="margin-top:10px">{chips}</div>'
    st.markdown(
        f'<div class="sf-card"><h2>{title}</h2>{body_html}{tag_html}</div>',
        unsafe_allow_html=True,
    )


def one_line(text, tone="buy"):
    cls = "" if tone == "buy" else " hold"
    st.markdown(
        f'<div class="sf-one-line{cls}">{text}</div>', unsafe_allow_html=True
    )


def tags(items):
    chips = "".join(f'<span class="sf-tag {k}">{t}</span>' for t, k in items)
    st.markdown(f'<div style="margin-top:10px">{chips}</div>', unsafe_allow_html=True)


def compare_table(headers, rows, first_col_left=True):
    cls_map = {"up": "sf-up", "down": "sf-down",
               "win": "sf-up", "weak": "sf-down"}
    def cell(c, left=False):
        if isinstance(c, tuple):
            text, tone = c
            if left:
                return f'<td class="l">{text}</td>'
            cls = cls_map.get(tone, "")
            return f'<td class="{cls}">{text}</td>' if cls else f"<td>{text}</td>"
        return f'<td class="l">{c}</td>' if left else f"<td>{c}</td>"

    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for r in rows:
        cells = [cell(c, left=(i == 0 and first_col_left)) for i, c in enumerate(r)]
        body += "<tr>" + "".join(cells) + "</tr>"
    st.markdown(
        f'<table class="sf-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )


def vs_box(title, verdict, verdict_kind, bullets):
    vk = "b" if verdict_kind == "b" else "o"
    lis = "".join(f"<li>{b}</li>" for b in bullets)
    return f"""<div class="sf-vsbox">
      <h3>{title}</h3>
      <div class="sf-verdict {vk}">{verdict}</div>
      <ul>{lis}</ul>
    </div>"""


def vs(box1_html, box2_html):
    st.markdown(
        f'<div class="sf-vs">{box1_html}{box2_html}</div>', unsafe_allow_html=True
    )


def alert(text, kind="cat", title=None):
    cls = "cat" if kind == "cat" else "risk"
    title_html = f"<b>{title}</b>" if title else ""
    st.markdown(
        f'<div class="sf-alert {cls}">{title_html}{text}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 图表组件（修复发白 + 统一暗色）
# ---------------------------------------------------------------------------
def echarts(option, height=380, div_id="sf-chart"):
    """嵌入 ECharts（CDN）。option 为 Python dict。"""
    opt = json.dumps(option, ensure_ascii=False)
    html = f"""
    <div id="{div_id}" style="width:100%;height:{height}px"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <script>
      var el = document.getElementById('{div_id}');
      var chart = echarts.init(el);
      chart.setOption({opt});
      window.addEventListener('resize', function(){{ chart.resize(); }});
    </script>
    """
    components.html(html, height=height + 20)


def kline_option(dates, ohlc, volumes=None, div_id="sf-kline"):
    """返回 ECharts K线（含成交量副图）的 option dict。
    ohlc: list of [open, close, low, high]（ECharts 顺序）
    涨跌色走全局 UP_COLOR / DOWN_COLOR。
    """
    return {
        "backgroundColor": "transparent",
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"},
                    "backgroundColor": "#1a1a2e", "borderColor": "#2d2d44",
                    "textStyle": {"color": "#e2e8f0"}},
        "axisPointer": {"link": [{"xAxisIndex": "all"}]},
        "grid": [{"left": "9%", "right": "6%", "top": 24, "height": "58%"},
                 {"left": "9%", "right": "6%", "top": "72%", "height": "16%"}],
        "xAxis": [
            {"type": "category", "data": dates, "boundaryGap": True,
             "axisLine": {"lineStyle": {"color": "#2d2d44"}},
             "axisLabel": {"color": "#94a3b8", "fontSize": 11},
             "axisTick": {"show": False}, "splitLine": {"show": False}},
            {"type": "category", "gridIndex": 1, "data": dates, "boundaryGap": True,
             "axisLine": {"lineStyle": {"color": "#2d2d44"}},
             "axisLabel": {"show": False}, "axisTick": {"show": False},
             "splitLine": {"show": False}},
        ],
        "yAxis": [
            {"scale": True,
             "axisLine": {"lineStyle": {"color": "#2d2d44"}},
             "axisLabel": {"color": "#94a3b8", "fontSize": 11},
             "splitLine": {"lineStyle": {"color": "#23233c"}}},
            {"gridIndex": 1, "scale": True,
             "axisLine": {"lineStyle": {"color": "#2d2d44"}},
             "axisLabel": {"show": False},
             "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "K线", "type": "candlestick", "data": ohlc,
             "itemStyle": {"color": UP_COLOR, "color0": DOWN_COLOR,
                           "borderColor": UP_COLOR, "borderColor0": DOWN_COLOR}},
            {"name": "成交量", "type": "bar", "xAxisIndex": 1, "yAxisIndex": 1,
             "data": volumes or [],
             "itemStyle": {"color": "#3a3a5c"}},
        ],
    }


def kline_plotly(dates, opens, highs, lows, closes, volumes=None, title="K线"):
    """返回 Plotly 暗色 K线 Figure（红涨绿跌）。
    用法：st.plotly_chart(kline_plotly(...), use_container_width=True)"""
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=list(dates), open=list(opens), high=list(highs),
        low=list(lows), close=list(closes),
        increasing={"line": {"color": UP_COLOR}, "fillcolor": UP_COLOR},
        decreasing={"line": {"color": DOWN_COLOR}, "fillcolor": DOWN_COLOR},
        name="K线",
    ))
    if volumes is not None:
        fig.add_trace(go.Bar(
            x=list(dates), y=list(volumes), name="成交量",
            marker_color="#3a3a5c", yaxis="y2",
        ))
    fig.update_layout(
        title={"text": title, "font": {"color": "#e2e8f0", "size": 14}},
        xaxis_rangeslider_visible=False,
        yaxis2=dict(overlaying="y", side="right", showgrid=False),
        margin=dict(l=40, r=20, t=40, b=30),
        **PLOTLY_DARK,
    )
    return fig


# ---------------------------------------------------------------------------
# 演示
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    st.set_page_config(page_title="星辰风格复刻 v2 Demo", layout="wide")
    inject_theme()
    inject_plotly_dark()

    header(
        brand="星辰",
        subtitle="五股横向对比 · 长鑫存储产业链视角",
        meta="分析时间：2026-07-10 09:47 (GMT+8) · 行情基准 2026-07-09 收盘",
    )

    card(
        "核心结论（一句话版）",
        """<div class="sf-one-line">从「长鑫存储扩产」这条线看：
        <b>柏诚股份 = 最纯正、弹性最大的直接受益者</b>；
        <b>太极实业 = 订单体量更大的稳健受益者</b>；
        <b>恒铭达几乎不在这条线上</b>。</div>""",
        tags_items=[
            ("柏诚股份：长鑫纯标的（首选弹性）", "win"),
            ("太极实业：长鑫总包+封测（稳健）", "win"),
            ("恒铭达：不在长鑫链（独立逻辑）", "mid"),
            ("东方锆业：题材透支（谨慎）", "weak"),
        ],
    )

    st.markdown('<div class="sf-card"><h2>关键指标横向对比</h2>', unsafe_allow_html=True)
    compare_table(
        ["维度", "太极实业 600667", "柏诚股份 601133", "恒铭达 002947"],
        [
            [("收盘价/涨跌", "l"), ("26.27 +10%", "up"), ("37.80 +10%", "up"), ("74.28 +3.2%", "up")],
            ["总市值", "549亿", "~200亿", "190亿"],
            ["核心业务", "洁净室EPC+封测", "洁净室系统集成", "消费电子功能件"],
            [("长鑫关联度", "l"),
             ("强·核心总包", "win"), ("最强·深度绑定", "win"), ("弱", "neu")],
            [("信号", "l"),
             ("BUY", "win"), ("BUY", "win"), ("WATCH", "weak")],
        ],
    )
    st.markdown('<div class="sf-note">注：市盈率为基于公开净利润预测的估算。</div></div>',
                unsafe_allow_html=True)

    # K线演示（ECharts，红涨绿跌，不再发白）
    st.markdown('<div class="sf-card"><h2>个股 K 线演示（暗色 · 红涨绿跌）</h2>',
                unsafe_allow_html=True)
    import datetime as _dt
    base = _dt.date(2026, 6, 1)
    dates = [(base + _dt.timedelta(days=i)).strftime("%m-%d") for i in range(12)]
    # [open, close, low, high]
    ohlc = [
        [10.0, 10.6, 9.8, 10.8], [10.6, 10.2, 10.0, 10.9], [10.2, 10.9, 10.1, 11.1],
        [10.9, 10.4, 10.2, 11.0], [10.4, 11.2, 10.3, 11.4], [11.2, 10.8, 10.6, 11.3],
        [10.8, 11.5, 10.7, 11.7], [11.5, 11.1, 10.9, 11.6], [11.1, 11.9, 11.0, 12.1],
        [11.9, 11.4, 11.2, 12.0], [11.4, 12.2, 11.3, 12.4], [12.2, 12.6, 12.0, 12.8],
    ]
    vols = [120, 98, 150, 110, 180, 95, 160, 105, 200, 130, 175, 210]
    echarts(kline_option(dates, ohlc, vols), height=420, div_id="demo-kline")
    st.markdown('</div>', unsafe_allow_html=True)

    # 雷达
    st.markdown('<div class="sf-card"><h2>综合评分雷达（五股四维对比）</h2>',
                unsafe_allow_html=True)
    echarts({
        "backgroundColor": "transparent",
        "tooltip": {},
        "legend": {"data": ["柏诚", "有研", "太极"],
                   "textStyle": {"color": "#94a3b8", "fontSize": 11}, "top": 0},
        "radar": {
            "indicator": [
                {"name": "长鑫关联", "max": 100}, {"name": "订单/催化", "max": 100},
                {"name": "业绩兑现", "max": 100}, {"name": "估值合理", "max": 100},
                {"name": "弹性空间", "max": 100}],
            "radius": "62%", "center": ["50%", "56%"],
            "axisName": {"color": "#e2e8f0", "fontSize": 11},
            "splitLine": {"lineStyle": {"color": "#2d2d44"}},
            "splitArea": {"areaStyle": {"color": ["#16162c", "#1a1a2e"]}},
            "axisLine": {"lineStyle": {"color": "#2d2d44"}}},
        "series": [{"type": "radar", "data": [
            {"value": [98, 90, 70, 35, 95], "name": "柏诚",
             "areaStyle": {"color": "rgba(255,77,79,.22)"},
             "lineStyle": {"color": "#ff4d4f"}, "itemStyle": {"color": "#ff4d4f"}},
            {"value": [60, 88, 85, 30, 70], "name": "有研",
             "areaStyle": {"color": "rgba(102,126,234,.25)"},
             "lineStyle": {"color": "#667eea"}, "itemStyle": {"color": "#667eea"}},
            {"value": [90, 92, 78, 55, 55], "name": "太极",
             "areaStyle": {"color": "rgba(255,165,2,.22)"},
             "lineStyle": {"color": "#ffa502"}, "itemStyle": {"color": "#ffa502"}},
        ]}]
    }, height=380)
    st.markdown('</div>', unsafe_allow_html=True)
