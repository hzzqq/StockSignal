"""pages/84_宏观数据.py — 宏观指标看板（轻量化增强版）。

``app.py`` 的功能表写着「宏观数据 | PMI、CPI、社融等关键宏观指标」，
但一直没有对应页面；投研圆桌的历史交付物也反复标注「宏观 PMI / 社融未取到，
下一轮需补宏观景气与政策变量」。本页把这块补上并做了轻量化增强。

2026-09 扩展：新增 12 个全球指标（美国宏观 / 美债 / 美元 / 汇率 / 美股港股），
并按「国内 / 全球」分组；顶部增加「全球风险偏好 / 流动性评分」卡片。

2026-11 增强（界面减负系列收尾）：
- 顶部 **全球核心 KPI 带**（标普500 / 纳斯达克 / 恒生 / 美债10Y / 美元兑人民币 /
  美元指数 DXY），一眼看外部风险环境，涨红跌绿。
- **全球风险评分可视化卡**：替代原 success 横幅——大数字 0-100 + 档位 + 进度条
  + 4 分项真实值 / 折算分，比一行文字清晰、轻量。
- 国内 / 全球分组卡片 2 列 → 3 列，更紧凑。

红线（不可动）：
- 取不到的指标显示「取不到」，**不臆造数值**。
- 「通俗解读」与「全球风险评分」是 modules.macro_data 里**规则生成**的确定性结论，
  不是大模型输出，页面上明确标注，避免把一行 if/else 当 AI 洞见。
"""
from __future__ import annotations

import streamlit as st

from modules.page_utils import render_standard_page
from modules import macro_data as md
from modules.ui_kit import xc_kpi_grid


# ── 全球风险评分卡样式（令牌化，随七风格联动；注入一次）──
_REGIME_CSS = """
<style>
.xcm-card{background:var(--card);border:1px solid var(--border);
  border-radius:var(--ss-radius-card,14px);padding:1.1rem 1.3rem;margin:0 0 .8rem}
.xcm-head{font-size:.85rem;color:var(--txt2);font-weight:600;margin-bottom:.35rem}
.xcm-score{font-size:2.4rem;font-weight:800;line-height:1;display:inline-block}
.xcm-max{font-size:1rem;color:var(--txt2);font-weight:600;margin-left:.15rem}
.xcm-band{font-size:.85rem;font-weight:700;margin:.15rem 0 .6rem}
.xcm-bar{height:8px;background:color-mix(in srgb,var(--txt) 10%,transparent);
  border-radius:999px;overflow:hidden;margin-bottom:.7rem}
.xcm-fill{height:100%;border-radius:999px;transition:width .4s ease}
.xcm-subs{display:grid;grid-template-columns:repeat(2,1fr);gap:.35rem .9rem}
.xcm-sub{display:flex;justify-content:space-between;align-items:baseline;
  font-size:.78rem;color:var(--txt2)}
.xcm-sub .xcm-pv{color:var(--txt);font-weight:600}
.xcm-sub .xcm-ps{color:var(--acc1);font-weight:700;font-size:.72rem}
.xcm-note{font-size:.7rem;color:var(--txt2);margin-top:.5rem;line-height:1.45}
@media(max-width:640px){.xcm-subs{grid-template-columns:1fr}}
</style>
"""

# 顶部全球核心 KPI 带的指标顺序（最影响 A 股外部风险环境的 6 个）
_GLOBAL_CORE = ["us_sp500", "us_nasdaq", "hsi", "us_treasury_10y", "usd_cny", "dxy"]


@st.cache_data(ttl=3600, show_spinner="正在拉取宏观数据…")
def _load() -> dict:
    return md.fetch_all()


@st.cache_data(ttl=3600, show_spinner="正在计算全球风险评分…")
def _load_regime() -> dict | None:
    return md.global_regime_score()


def _render_card(spec: dict, item):
    with st.container(border=True):
        st.markdown(f"**{spec['name']}**　`{spec['freq']}度` · {spec['source']}")
        if not item:
            st.warning("取不到（不臆造）")
            st.caption("口径：" + spec["desc"])
            return
        _chg = item.get("change")
        _delta, _dir = "", "flat"
        if _chg is not None:
            _delta = f"{_chg:+.2f}"
            # A 股惯例：涨红跌绿（原 st.metric delta_color="inverse"：正红负绿）
            _dir = "up" if _chg > 0 else ("down" if _chg < 0 else "flat")
        xc_kpi_grid([{
            "label": "最新值", "value": f"{item['value']}{item['unit']}",
            "delta": _delta, "delta_dir": _dir}])
        st.caption(
            f"数据日期 {item['date']}　"
            f"前值 {item['prev'] if item['prev'] is not None else '—'}"
        )
        st.caption("口径：" + item["desc"])
        st.markdown(
            "**解读（规则）：** "
            + md.interpret(spec["key"], item["value"], item["prev"])
        )


def _render_section(title: str, emoji: str, specs, data):
    st.subheader(f"{emoji} {title}")
    specs = list(specs)
    # 轻量化：3 列网格（原 2 列），更紧凑
    for i in range(0, len(specs), 3):
        cols = st.columns(3)
        for j, spec in enumerate(specs[i:i + 3]):
            with cols[j]:
                _render_card(spec, data.get(spec["key"]))


def _render_regime_card(regime: dict) -> None:
    """全球风险偏好 / 流动性评分可视化卡（替代原 success 横幅）。

    高分=宽松·风险偏好高（利好 A 股）→ 绿；中→accent；低=收紧→红。
    """
    score = regime["score"]
    band = ("宽松 · 风险偏好高" if score >= 60 else
            "中性" if score >= 45 else "收紧 · 风险偏好低")
    if score >= 60:
        col = "var(--ss-up)"      # 绿（宽松利好）
    elif score >= 45:
        col = "var(--acc1)"       # 中性 accent
    else:
        col = "var(--ss-down)"    # 红（收紧）
    sub = regime.get("sub", {})
    parts = regime.get("parts", {})
    _labels = {"dxy": "美元指数", "us_treasury_10y": "美债10Y",
               "us_cpi": "美国CPI", "usd_cny": "美元兑人民币"}
    _rows = "".join(
        f'<div class="xcm-sub"><span>{_labels.get(k, k)}</span>'
        f'<span class="xcm-pv">{parts.get(k) if parts.get(k) is not None else "—"}</span>'
        f'<span class="xcm-ps">{v:.0f}分</span></div>'
        for k, v in sub.items()
    )
    # ui_audit_exempt: unsafe-allow_html 评分卡，score/band 为本页计算数值、sub/parts 经 macro_data 真实返回
    st.markdown(
        f'<div class="xcm-card">'
        f'<div class="xcm-head">🌐 全球风险偏好 / 流动性评分</div>'
        f'<div class="xcm-score" style="color:{col}">{score}'
        f'<span class="xcm-max">/100</span></div>'
        f'<div class="xcm-band" style="color:{col}">{band}</div>'
        f'<div class="xcm-bar"><div class="xcm-fill" style="width:{score}%;background:{col}"></div></div>'
        f'<div class="xcm-subs">{_rows}</div>'
        f'<div class="xcm-note">规则合成（弱美元 + 低美债 + 低通胀 + 人民币偏强 → 高分）；'
        f'各分项为 0-100 折算分，详见 modules.macro_data.global_regime_score，非 AI 洞见。</div>'
        f'</div>',
        unsafe_allow_html=True,  # ui_audit_exempt: unsafe-allow_html
    )


def _render_global_kpi(data: dict) -> None:
    """顶部全球核心 KPI 带：标普 / 纳指 / 恒生 / 美债10Y / USD-CNY / DXY。"""
    cards = []
    for k in _GLOBAL_CORE:
        it = data.get(k)
        spec = md._SPEC.get(k, {})
        if not it:
            cards.append({"label": spec.get("name", k), "value": "取不到",
                          "delta": "", "delta_dir": "flat"})
            continue
        chg = it.get("change")
        d, dr = "", "flat"
        if chg is not None:
            d = f"{chg:+.2f}"
            dr = "up" if chg > 0 else ("down" if chg < 0 else "flat")
        cards.append({"label": it["name"], "value": f"{it['value']}{it['unit']}",
                      "delta": d, "delta_dir": dr})
    xc_kpi_grid(cards)


def main() -> None:
    render_standard_page(title="宏观数据", icon="🌍", layout="wide")
    st.markdown(_REGIME_CSS, unsafe_allow_html=True)  # ui_audit_exempt: 静态 <style> 注入，无动态内容

    st.caption(
        "数据源：akshare（国家统计局 / 央行 / 美国劳工部 / 美联储 / 东方财富 / 外汇交易中心）。"
        "「通俗解读」与「全球风险评分」均为 **规则生成的确定性结论**，不是大模型输出，请勿当作 AI 洞见。"
    )

    data = _load()
    ok_n = sum(1 for v in data.values() if v)
    total_n = len(data)
    if ok_n == 0:
        st.error(
            "全部宏观指标都取不到（akshare 不可用或网络受限）。"
            "这里**不会**用示例数据填充——请检查 akshare 安装与网络后重试。"
        )
        return
    st.caption(f"✅ 取到 {ok_n}/{total_n} 个宏观指标；未取到的显示「取不到」，不臆造。")

    # ---- 全球风险偏好 / 流动性评分卡 ----
    regime = _load_regime()
    if regime is not None:
        _render_regime_card(regime)
    else:
        st.info("全球风险评分所需的分项（美元指数 / 美债 / 美国CPI / 汇率）暂时都取不到，不臆造评分。")

    # ---- 顶部全球核心 KPI 带 ----
    _render_global_kpi(data)

    # ---- 国内 / 全球 分组 ----
    domestic = [m for m in md.MACRO_INDICATORS if m.get("region") == "国内"]
    global_ = [m for m in md.MACRO_INDICATORS if m.get("region") == "全球"]

    _render_section("国内宏观", "🇨🇳", domestic, data)
    st.divider()
    _render_section("全球宏观（美股 / 美债 / 美元 / 汇率）", "🌐", global_, data)

    # ── 方法学与来源注脚（B 类页五段式收尾）──
    st.markdown("---")
    st.caption("口径与来源：宏观指标=akshare（国家统计局 / 央行 / 美国劳工部 / 美联储 / 东方财富 / 外汇交易中心），1 小时缓存，按各指标官方发布频率更新（月度/日度不等，非实时行情），取不到如实标「取不到」；「通俗解读」与「全球风险评分」=modules.macro_data 规则生成的确定性结论。不构成投资建议。")


main()
