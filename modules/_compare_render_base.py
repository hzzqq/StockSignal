"""多股票横向对比 —— 共享渲染基元（_compare_render 二级拆分·叶子底座）。

职责：主题检测 / 样式令牌与 CSS / 标签与徽章小工具 / 数值格式化 / 安全取值。
零业务逻辑改动：源码自 ``modules/_compare_render.py`` 按函数名原样搬运。
"""
from __future__ import annotations

import datetime as _dt
import logging
import re

import numpy as np
from modules.colors import _hex_to_rgba
from modules.time_utils import now_cst_str

logger = logging.getLogger(__name__)

SERIES_COLORS = ["#009e60", "#dc2626", "#4f46e5", "#d97706", "#7c3aed",
                 "#0891b2", "#ca8a04", "#9333ea"]

_INDUSTRY_GROUPS = {
    "电子半导体": ["半导体", "消费电子", "元件", "光学光电子", "电子制造", "其他电子", "电子"],
    "工程建筑": ["工程", "建设", "建筑", "装修", "设计"],
    "金属材料": ["金属", "材料"],
    "医药生物": ["医药", "生物", "医疗", "制药", "疫苗"],
    "汽车": ["汽车", "零部件"],
    "金融": ["银行", "证券", "保险", "金融"],
    "消费": ["白酒", "饮料", "食品", "家电", "零售", "消费"],
    "电力能源": ["电力", "能源", "煤炭", "燃气", "光伏", "电池"],
    "化工": ["化工", "化学"],
    "计算机": ["计算机", "软件", "通信", "互联网"],
    "机械军工": ["机械", "军工", "设备"],
}

_CSS_CACHE: Dict[bool, str] = {}

def _is_dark() -> bool:
    """检测当前页面是否处于暗色主题。"""
    try:
        from modules.ui_theme import _theme_is_dark

        return _theme_is_dark()
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        return False

def _sf() -> Dict[str, str]:
    """返回当前主题下的配色与样式令牌。"""
    if _is_dark():
        return {
            "up": "#00d4aa", "down": "#ff4757", "hold": "#ffa502",
            "acc1": "#667eea", "acc2": "#764ba2",
            "bg": "#0f0f23", "card": "#1a1a2e", "border": "#2d2d44",
            "txt": "#e2e8f0", "txt2": "#94a3b8",
            "th_bg": "#15152a", "vsbox_bg": "#15152a",
            "header_bg": "#1a1a2e", "header_bg2": "#241b3a",
            "one_line_bg": "rgba(0,212,170,.08)",
            "one_line_bg_hold": "rgba(255,165,2,.08)",
            "tag_win_bg": "rgba(0,212,170,.16)",
            "tag_win_border": "rgba(0,212,170,.4)",
            "tag_mid_bg": "rgba(255,165,2,.16)",
            "tag_mid_border": "rgba(255,165,2,.4)",
            "tag_weak_bg": "rgba(255,71,87,.14)",
            "tag_weak_border": "rgba(255,71,87,.4)",
            "tag_neu_bg": "rgba(148,163,184,.12)",
            "tag_neu_border": "var(--border)",
            "verdict_b_bg": "rgba(0,212,170,.12)",
            "verdict_o_bg": "rgba(255,165,2,.12)",
            "alert_risk_bg": "rgba(255,71,87,.10)",
            "alert_risk_border": "rgba(255,71,87,.45)",
            "alert_risk_color": "#ffb3bb",
            "alert_cat_bg": "rgba(0,212,170,.10)",
            "alert_cat_border": "rgba(0,212,170,.45)",
            "alert_cat_color": "#9af0dd",
            "disclaimer_color": "#6b7280",
        }
    return {
        "up": "#009e60", "down": "#dc2626", "hold": "#d97706",
        "acc1": "#4f46e5", "acc2": "#7c3aed",
        "bg": "#f5f7fa", "card": "#ffffff", "border": "#e2e8f0",
        "txt": "#1e293b", "txt2": "#64748b",
        "th_bg": "#f8fafc", "vsbox_bg": "#f8fafc",
        "header_bg": "#f0f1ff", "header_bg2": "#ede9fe",
        "one_line_bg": "rgba(0,158,96,.07)",
        "one_line_bg_hold": "rgba(217,119,6,.07)",
        "tag_win_bg": "rgba(0,158,96,.10)",
        "tag_win_border": "rgba(0,158,96,.35)",
        "tag_mid_bg": "rgba(217,119,6,.10)",
        "tag_mid_border": "rgba(217,119,6,.35)",
        "tag_weak_bg": "rgba(220,38,38,.08)",
        "tag_weak_border": "rgba(220,38,38,.35)",
        "tag_neu_bg": "rgba(100,116,139,.08)",
        "tag_neu_border": "var(--border)",
        "verdict_b_bg": "rgba(0,158,96,.08)",
        "verdict_o_bg": "rgba(217,119,6,.08)",
        "alert_risk_bg": "rgba(220,38,38,.06)",
        "alert_risk_border": "rgba(220,38,38,.25)",
        "alert_risk_color": "#991b1b",
        "alert_cat_bg": "rgba(0,158,96,.06)",
        "alert_cat_border": "rgba(0,158,96,.25)",
        "alert_cat_color": "#166534",
        "disclaimer_color": "#94a3b8",
    }

def _compare_css_body() -> str:
    """实际构建对比页 CSS（无缓存，供 compare_css 按主题调用）。"""
    return f"""
<style>
.compare-wrap{{max-width:1200px;margin:0 auto;color:{_sf()['txt']};
  font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.55}}
.compare-wrap .header{{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:10px;margin-bottom:18px;padding:14px 18px;
  background:linear-gradient(90deg,{_sf()['header_bg']},{_sf()['header_bg2']});border:1px solid {_sf()['border']};border-radius:14px}}
.compare-wrap .header .brand{{font-size:15px;color:{_sf()['txt2']};letter-spacing:1px}}
.compare-wrap .header .brand b{{color:{_sf()['acc1']}}}
.compare-wrap .card{{background:{_sf()['card']};border:1px solid {_sf()['border']};
  border-radius:14px;padding:18px;margin-top:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.compare-wrap .card h2{{font-size:16px;margin-bottom:14px;display:flex;align-items:center;gap:8px}}
.compare-wrap .card h2::before{{content:"";width:4px;height:16px;
  background:linear-gradient(180deg,{_sf()['acc1']},{_sf()['acc2']});border-radius:3px}}
.compare-wrap .one-line{{font-size:14.5px;font-weight:700;color:{_sf()['up']};
  background:{_sf()['one_line_bg']};border-left:3px solid {_sf()['up']};padding:10px 14px;border-radius:8px;margin-bottom:14px}}
.compare-wrap .one-line.hold{{color:{_sf()['hold']};background:{_sf()['one_line_bg_hold']};border-left-color:{_sf()['hold']}}}
.compare-wrap table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
.compare-wrap th,.compare-wrap td{{padding:9px 8px;text-align:center;border-bottom:1px solid {_sf()['border']}}}
.compare-wrap th{{color:{_sf()['txt2']};font-weight:600;font-size:12px;background:{_sf()['th_bg']}}}
.compare-wrap td.l{{text-align:left}}
.compare-wrap .up{{color:{_sf()['up']};font-weight:700}}
.compare-wrap .down{{color:{_sf()['down']};font-weight:700}}
.compare-wrap .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:14px;font-weight:600}}
.compare-wrap .tag.win{{background:{_sf()['tag_win_bg']};color:{_sf()['up']};border:1px solid {_sf()['tag_win_border']}}}
.compare-wrap .tag.mid{{background:{_sf()['tag_mid_bg']};color:{_sf()['hold']};border:1px solid {_sf()['tag_mid_border']}}}
.compare-wrap .tag.weak{{background:{_sf()['tag_weak_bg']};color:{_sf()['down']};border:1px solid {_sf()['tag_weak_border']}}}
.compare-wrap .tag.neu{{background:{_sf()['tag_neu_bg']};color:{_sf()['txt2']};border:1px solid {_sf()['tag_neu_border']}}}
.compare-wrap .vs{{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px}}
.compare-wrap .vsbox{{flex:1 1 0;min-width:300px;background:{_sf()['vsbox_bg']};border:1px solid {_sf()['border']};border-radius:10px;padding:14px}}
/* 1:1 横向两两对比：左卡 | VS | 右卡，严格等宽，绝不纵向堆叠 */
.compare-wrap .pw-grid{{display:grid;grid-template-columns:1fr auto 1fr;align-items:stretch;gap:0;margin-top:8px}}
.compare-wrap .pw-box{{background:{_sf()['vsbox_bg']};border:1px solid {_sf()['border']};border-radius:10px;padding:14px}}
.compare-wrap .pw-vs{{display:flex;align-items:center;justify-content:center;font-weight:800;
  font-size:18px;color:{_sf()['acc1']};padding:0 16px;letter-spacing:2px}}
.compare-wrap .pw-vs span{{background:{_sf()['card']};border:1px solid {_sf()['border']};
  border-radius:50%;width:34px;height:34px;display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 14px var(--ss-glow-soft)}}
@media(max-width:780px){{.compare-wrap .pw-grid{{grid-template-columns:1fr}}.compare-wrap .pw-vs{{padding:8px 0}}.compare-wrap .pw-vs span{{width:30px;height:30px;font-size:15px}}}}
.compare-wrap .vsbox h3{{font-size:14px;margin-bottom:8px}}
.compare-wrap .vsbox .verdict{{font-size:13px;font-weight:700;margin:8px 0;padding:6px 10px;border-radius:8px}}
.compare-wrap .verdict.b{{background:{_sf()['verdict_b_bg']};color:{_sf()['up']}}}
.compare-wrap .verdict.o{{background:{_sf()['verdict_o_bg']};color:{_sf()['hold']}}}
.compare-wrap .vsbox .type{{font-size:12px;color:{_sf()['txt2']};margin-left:6px}}
.compare-wrap .vsbox .score-row{{display:flex;align-items:center;gap:10px;margin:8px 0}}
.compare-wrap .vsbox .score-badge{{font-size:13px;font-weight:700;padding:3px 10px;border-radius:14px}}
.compare-wrap .vsbox .score-badge.win{{background:{_sf()['tag_win_bg']};color:{_sf()['up']};border:1px solid {_sf()['tag_win_border']}}}
.compare-wrap .vsbox .score-badge.mid{{background:{_sf()['tag_mid_bg']};color:{_sf()['hold']};border:1px solid {_sf()['tag_mid_border']}}}
.compare-wrap .vsbox .score-badge.weak{{background:{_sf()['tag_weak_bg']};color:{_sf()['down']};border:1px solid {_sf()['tag_weak_border']}}}
.compare-wrap .vsbox ul{{margin:10px 0 0 0;padding:0;list-style:none;font-size:12.5px;color:{_sf()['txt2']};line-height:1.7}}
.compare-wrap .vsbox ul li{{padding:5px 0;border-bottom:1px dashed {_sf()['border']}}}
.compare-wrap .vsbox ul li:last-child{{border-bottom:none}}
.compare-wrap .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.compare-wrap .note{{font-size:12.5px;color:{_sf()['txt2']};margin-top:10px;line-height:1.7}}
.compare-wrap .alert{{border-radius:10px;padding:12px 14px;margin-top:12px;font-size:13px}}
.compare-wrap .alert.risk{{background:{_sf()['alert_risk_bg']};border:1px solid {_sf()['alert_risk_border']};color:{_sf()['alert_risk_color']}}}
.compare-wrap .alert.cat{{background:{_sf()['alert_cat_bg']};border:1px solid {_sf()['alert_cat_border']};color:{_sf()['alert_cat_color']}}}
.compare-wrap .alert b{{display:block;margin-bottom:4px;font-size:13.5px}}
.compare-wrap .foot{{font-size:12px;color:{_sf()['txt2']};margin-top:6px}}
.compare-wrap .disclaimer{{margin-top:14px;font-size:11.5px;color:{_sf()['disclaimer_color']};
  border-top:1px dashed {_sf()['border']};padding-top:10px}}
.compare-wrap .hl{{color:{_sf()['up']};font-weight:700}}
.compare-wrap .hr{{color:{_sf()['down']};font-weight:700}}
.compare-wrap .pair-select{{margin-bottom:8px}}
.compare-wrap .aggregate-table td.l{{text-align:left}}
.compare-wrap .aggregate-table td{{vertical-align:top}}
.compare-wrap .score-cloud{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}}
.compare-wrap .score-cloud .chip{{display:inline-flex;align-items:center;gap:6px;font-size:13px;
  padding:5px 12px;border-radius:16px;border:1px solid {_sf()['border']};
  background:{_sf()['vsbox_bg']};color:{_sf()['txt']}}}
@media(max-width:780px){{.compare-wrap .two-col{{grid-template-columns:1fr}}}}
</style>
"""

def compare_css() -> str:
    """一次性注入对比页样式（与参考 HTML 同构，亮/暗双主题自适应）。

    按主题缓存：仅在主题切换时重建一次大段 CSS 字符串，避免每次 fragment
    轮询重渲染时重复格式化（原实现每次调用都重建 ~2KB f-string + 40 次主题查询）。
    """
    dark = _is_dark()
    cached = _CSS_CACHE.get(dark)
    if cached is None:
        cached = _compare_css_body()
        _CSS_CACHE[dark] = cached
    return cached

def _tag(text: str, kind: str) -> str:
    return f'<span class="tag {kind}">{text}</span>'

def _sig_tag(signal: str) -> str:
    if signal == "买入":
        return _tag("BUY", "win")
    if signal == "卖出":
        return _tag("SELL", "weak")
    return _tag("HOLD", "mid")

def _corr_tag(v: float) -> str:
    if v >= 70:
        return _tag(f"强·{v:.0f}", "win")
    if v >= 40:
        return _tag(f"中·{v:.0f}", "mid")
    return _tag(f"弱·{v:.0f}", "weak")

def _catalyst_tag(v: float) -> str:
    if v >= 70:
        return _tag(f"强·{v:.0f}", "win")
    if v >= 50:
        return _tag(f"中·{v:.0f}", "mid")
    return _tag(f"弱·{v:.0f}", "weak")

def _safe(v, d: float = 0.0) -> float:
    try:
        f = float(v)
        return f if (not np.isnan(f)) else d
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        return d

def _norm(vals: List[float]) -> List[float]:
    """把一组值线性映射到 [50,100]，保持组内相对强弱。

    健壮性（R2）：空列表安全返回 []；输入中的 None/NaN 退化为 0.0，
    不会因非有限值传播 NaN 或触发除零崩溃。有效输入行为与改动前完全一致。
    """
    if not vals:
        return []
    safe = [_safe(v, 0.0) for v in vals]
    lo, hi = min(safe), max(safe)
    if hi - lo < 1e-9:
        return [50.0 for _ in safe]
    return [50 + (v - lo) / (hi - lo) * 50 for v in safe]

def _row_score(r: Dict[str, Any], key: str, default: float = 50.0) -> float:
    """安全提取单只股票四维/综合评分；scores 缺失、为 None 或具体子项缺失时返回 default。

    用于多股对比在「部分股票数据缺失」场景下仍可正常评分与排序（R1/R2）。
    有效输入（scores 为含该 key 的 dict）行为与直接取值完全一致。
    """
    sc = r.get("scores")
    if not isinstance(sc, dict):
        return default
    return _safe(sc.get(key), default)

def _fmt(v, is_num: bool = False):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if is_num:
        try:
            return f"{float(v):.1f}"
        except Exception as e:
            logger.warning(f"[compare] 未处理异常: {e}")
            return str(v)
    return str(v)

def _fmt_pct(v):
    """主力占比等百分比：兼容「百分比数字(0-100)」与「小数(0-1)」两种输入。"""
    if v is None:
        return "—"
    try:
        f = float(str(v).replace(",", ""))
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        return str(v)
    s = f * 100 if abs(f) < 1.6 else f
    return f"{s:.2f}%"

def _fund_yi_cell(r, key: str) -> str:
    """主力/大单净流入：元 → 亿元，红涨(流入)/绿跌(流出)。"""
    v = r.get(key)
    if v is None:
        return "<td>—</td>"
    try:
        yi = float(str(v).replace(",", "")) / 1e8
    except Exception as e:
        logger.warning(f"[compare] 未处理异常: {e}")
        return "<td>—</td>"
    cls = "up" if yi >= 0 else "down"
    return f'<td class="{cls}">{yi:,.2f}</td>'

def _elasticity_label(v: float) -> str:
    if v >= 40:
        return f"高弹性·{v:.0f}%"
    if v >= 20:
        return f"中弹性·{v:.0f}%"
    return f"稳健·{v:.0f}%"

def _stock_type_label(r: Dict[str, Any]) -> str:
    """根据得分、弹性、估值给一个定性标签。"""
    comp = _safe(r.get("scores", {}).get("composite"), 50)
    elas = _safe(r.get("elasticity"), 0)
    cap = _safe(r.get("market_cap"), 0)
    sig = r.get("signal", "持有")
    if comp >= 75 and elas >= 30:
        return "赛道龙头"
    if comp >= 65 and cap >= 1000:
        return "大盘蓝筹"
    if comp >= 60 and elas >= 35:
        return "高弹性进攻"
    if sig == "买入" and comp >= 60:
        return "趋势强势"
    if elas >= 35:
        return "题材博弈"
    if comp < 45:
        return "防御观望"
    if cap >= 500:
        return "稳健成长"
    return "均衡配置"

def _score_badge(r: Dict[str, Any]) -> str:
    comp = int(round(_safe(r.get("scores", {}).get("composite"), 50)))
    sig = r.get("signal", "持有")
    if sig == "买入":
        label, cls = f"{comp}分 · 看多(BUY)", "win"
    elif sig == "卖出":
        label, cls = f"{comp}分 · 谨慎(WATCH)", "weak"
    else:
        label, cls = f"{comp}分 · 持有(HOLD)", "mid"
    return f'<span class="score-badge {cls}">{label}</span>'

def _biz_groups(industry: str) -> List[str]:
    return [g for g, kws in _INDUSTRY_GROUPS.items()
            if any(k in industry for k in kws)]
