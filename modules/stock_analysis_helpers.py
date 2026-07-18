"""
个股分析页纯函数簇（从 pages/2_个股分析.py 抽出，#408 拆分超大文件）。

本模块只含「输入基础类型 / dict / DataFrame → 返回字符串 / 列表」的纯函数，
不依赖 streamlit / session_state / fetcher，可被页面按名导入，行为与原来完全一致。

配色常量与原页面保持一致（参考文档 002947：绿涨 / 红跌 / 琥珀中性）。
"""

import pandas as pd
import numpy as np

RED = "#009e60"      # 涨 / 利好 / 买入（文档：绿）
GREEN = "#dc2626"    # 跌 / 利空 / 卖出（文档：红）
AMBER = "#d97706"    # 中性 / 持有


def _sentiment_tag(label: str) -> str:
    """情绪标签 → CSS 类名。"""
    return {"正面": "up", "负面": "down", "中性": "mid"}.get(label, "neu")


def _tp_cls(score: float) -> str:
    """多周期技术评分 → CSS 类名（绿强 / 红弱 / 中性）。"""
    return "up" if score >= 60 else ("down" if score <= 40 else "mid")


def _score_ring_html(score: int, color: str) -> str:
    """生成 SVG 评分环：0-100 评分，环按比例填充，数字居中。"""
    score = max(0, min(100, int(score)))
    r = 54
    c = 2 * 3.1415926 * r
    dash = c * score / 100.0
    return f"""
    <div style="display:flex;justify-content:center;align-items:center;margin:6px 0 2px;">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <defs>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#667eea"/>
            <stop offset="100%" stop-color="#764ba2"/>
          </linearGradient>
        </defs>
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="#e2e8f0" stroke-width="12"/>
        <circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="12"
                stroke-linecap="round" stroke-dasharray="{dash:.1f} {c:.1f}"
                transform="rotate(-90 70 70)"/>
        <text x="70" y="64" text-anchor="middle" font-size="34" font-weight="700"
              fill="{color}" font-family="Fira Code, monospace">{score}</text>
        <text x="70" y="88" text-anchor="middle" font-size="12" fill="#64748b">综合评分</text>
      </svg>
    </div>
    """


def _verdict_color(composite: float):
    """根据综合评分返回 (信号文案, 颜色, css_class)。"""
    if composite >= 70:
        return "看多", RED, "win"
    elif composite <= 40:
        return "看空", GREEN, "weak"
    return "持有", AMBER, "mid"


def _price_color(pct: float) -> str:
    """涨红跌绿。"""
    if pct > 0:
        return RED
    if pct < 0:
        return GREEN
    return AMBER


def _support_resistance_bar(support: float, resistance: float, current: float,
                            markers=None) -> str:
    """支撑 → 压力 价格刻度条，标注当前价位置；
    markers=[(label, price, color), ...] 在条上方叠加标注点（MA5/MA10/MA20/套牢区 等）。"""
    if resistance <= support:
        return ""
    lo = support
    hi = resistance
    for _m in (markers or []):
        try:
            lo = min(lo, float(_m[1]))
            hi = max(hi, float(_m[1]))
        except Exception:  # noqa
            pass
    span = hi - lo if hi > lo else 1.0

    def _pos(p):
        return max(0.0, min(100.0, (float(p) - lo) / span * 100.0))

    pos = _pos(current)
    parts = [
        '<div style="margin:10px 0 4px;padding-top:24px;">',
        f'<div style="position:relative;height:26px;border-radius:13px;'
        f'background:linear-gradient(90deg,{GREEN}33,{AMBER}33,{RED}33);'
        f'border:1px solid #e2e8f0;">',
        f'<div style="position:absolute;top:-4px;left:{pos:.1f}%;'
        f'transform:translateX(-50%);width:2px;height:34px;background:#475569;"></div>',
        f'<div style="position:absolute;top:-22px;left:{pos:.1f}%;'
        f'transform:translateX(-50%);font-size:11px;color:#1e293b;white-space:nowrap;">'
        f'现价 ¥{current:.2f}</div>',
    ]
    for (lab, price, color) in (markers or []):
        mp = _pos(price)
        parts.append(
            f'<div style="position:absolute;top:-40px;left:{mp:.1f}%;'
            f'transform:translate(-50%,0);font-size:10px;color:{color};white-space:nowrap;">{lab}</div>'
        )
    parts.append('</div>')
    parts.append(
        f'<div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-top:6px;">'
        f'<span>支撑 ¥{support:.2f}</span>'
        f'<span>压力 ¥{resistance:.2f}</span>'
        f'</div>'
    )
    parts.append('</div>')
    return "".join(parts)


def _battle_plan_scale(support: float, resistance: float, current: float,
                       target: float, stop: float, entry: float, verdict: str) -> str:
    """作战计划价格刻度条（参考 HTML .scale）：仅关键价位，无 MA 重叠标记。"""
    if resistance <= support:
        resistance = current * 1.10
        support = current * 0.90
    lo = support * 0.95
    hi = resistance * 1.05
    span = hi - lo if hi > lo else 1.0

    def _pos(p):
        return max(3.0, min(97.0, (float(p) - lo) / span * 100.0))

    c_left = GREEN   # 下方/利空
    c_mid = AMBER
    c_right = RED    # 上方/利多
    cur_color = c_right if verdict == "看多" else (c_left if verdict == "看空" else "#475569")

    markers = [
        ("支撑", support, c_left),
        ("入场", entry, c_mid),
        ("现价", current, cur_color),
        ("目标", target, c_right),
        ("止损", stop, c_right),
    ]
    # 去重：避免 price 太接近导致文字重叠
    used = set()
    filtered = []
    for lab, price, color in markers:
        if price is None or price <= 0:
            continue
        key = round(price / span * 100.0)
        if key in used:
            continue
        used.add(key)
        filtered.append((lab, price, color))

    parts = [
        '<div class="sf-scale">',
        f'<div class="sf-scale-bar" style="background:linear-gradient(90deg,{c_left},{c_mid},{c_right});"></div>',
    ]
    for lab, price, color in filtered:
        p = _pos(price)
        parts.append(
            f'<div class="sf-scale-mk" style="left:{p:.1f}%;">'
            f'<b style="color:{color};">¥{price:.2f}</b>{lab}</div>'
        )
    parts.append('<div class="sf-scale-lab" style="left:14px;">下方支撑</div>')
    parts.append('<div class="sf-scale-lab" style="right:14px;">压力/止损</div>')
    parts.append('</div>')
    return "".join(parts)


def _build_risk_iron_rules(R: dict) -> list[dict]:
    """基于分析结果生成风险铁律（风控铁律）。"""
    items = []
    current_price = float(R.get("current_price", 0) or 0)
    stop_price = float(R.get("stop_price", 0) or 0)
    target_price = float(R.get("target_price", 0) or 0)
    support = float(R.get("support", 0) or 0)
    resistance = float(R.get("resistance", current_price * 1.10) or 0)
    entry_price = float(R.get("entry_price", current_price) or 0)
    verdict = R.get("verdict", "持有")
    atr14 = float(R.get("atr14", current_price * 0.02) or 0)
    arrangement = (R.get("trend", {}) or {}).get("arrangement", "")

    if verdict == "看空":
        items.append({
            "title": "绝不裸追下方",
            "desc": f"当前价 ¥{current_price:.2f} 处偏空区域，无明确反弹信号前不追空；等反弹至 ¥{resistance:.2f} 附近再布局。",
            "level": "core",
        })
    elif verdict == "看多":
        items.append({
            "title": "绝不追高",
            "desc": f"当前价 ¥{current_price:.2f} 处偏多区域，等回踩 ¥{entry_price:.2f} 附近或缩量回调再建仓。",
            "level": "core",
        })
    else:
        items.append({
            "title": "不押注方向",
            "desc": f"当前处于震荡/持有状态，等待价格明确突破 ¥{resistance:.2f} 或跌破 ¥{support:.2f} 后再加仓。",
            "level": "core",
        })

    items.append({
        "title": "止损必设",
        "desc": f"硬止损 ¥{stop_price:.2f}（ATR14≈¥{atr14:.2f}），破则无条件离场，禁止补仓摊平。",
        "level": "warn",
    })
    items.append({
        "title": "仓位纪律",
        "desc": "单标的 ≤ 总仓位 30%；首仓试探，确认趋势后再加；亏损单不加仓。",
        "level": "warn",
    })
    if arrangement:
        items.append({
            "title": "盯结构变化",
            "desc": f"当前均线形态「{arrangement}」，若形态破坏（如多头排列走平/空头排列被突破），立即重新评估。",
            "level": "info",
        })
    return items


def _risk_iron_html(title: str, items: list[dict]) -> str:
    """渲染风险铁律框（参考 HTML .warnbox）。"""
    if not items:
        items = [{"title": "暂无", "desc": "未识别到明确风险铁律，建议遵守通用止损与仓位纪律。", "level": "info"}]
    rows = "".join(f"<li><b>{it['title']}</b>：{it['desc']}</li>" for it in items)
    return f'<div class="sf-risk-iron"><h3>⚠ {title}</h3><ul>{rows}</ul></div>'


def _build_plan_rows(verdict: str, current: float, support: float, resistance: float,
                     target: float, stop: float, entry: float, ma20: float) -> list[tuple]:
    """根据研判生成 A/B 两方案（参考 HTML 作战计划表）。"""
    if verdict == "看空":
        return [
            ("A 反弹空", f"反弹至 {entry:.2f}–{resistance:.2f} 受阻", f"{entry:.2f}–{resistance:.2f} 分批", f"{stop:.2f}（破则认错）", f"{support:.2f} → {target:.2f}"),
            ("B 破位追空", f"{support:.2f} 有效跌破（收盘+放量）", "跟空", f"{current:.2f}", f"{target:.2f} → {support*0.97:.2f}"),
        ]
    elif verdict == "看多":
        return [
            ("A 回踩建仓", f"回调至 {support:.2f}–{entry:.2f} 企稳", f"{support:.2f}–{entry:.2f} 分批", f"{stop:.2f}（破则认错）", f"{target:.2f} → {resistance:.2f}"),
            ("B 突破加仓", f"放量突破 {resistance:.2f}", "跟多", f"{entry:.2f}", f"{resistance:.2f} → {resistance*1.05:.2f}"),
        ]
    else:
        return [
            ("A 区间低吸", f"回调至 {support:.2f} 附近企稳", f"{support:.2f}–{entry:.2f} 分批", f"{stop:.2f}", f"{target:.2f} 附近减仓"),
            ("B 观望", f"等方向明确：突破 {resistance:.2f} 或跌破 {support:.2f}", "不进场", "—", "等更清晰拐点"),
        ]


def _section_header(title: str, subtitle: str = "", icon: str = "📊") -> str:
    """生成轻量化模块标题（图标 + 标题），与参考文档 .card h2 一致。subtitle 已废弃，仅保留兼容。"""
    return f"<h2>{icon} {title}</h2>"


def _build_rise_fall_factors(R: dict) -> tuple[list[dict], list[dict]]:
    """基于分析结果 R 构建上涨/下跌因素列表（含强度 1–3 星、标签、更丰富的数据描述）。"""
    rise, fall = [], []
    technical_profile = R.get("technical_profile", {}) or {}
    sector_score = float(R.get("sector_score", 50))
    volume_info = R.get("volume_info", {}) or {}
    trend = R.get("trend", {}) or {}
    momentum = R.get("momentum", {}) or {}
    current_price = float(R.get("current_price", 0))
    support = float(R.get("support", 0))
    resistance = float(R.get("resistance", current_price * 1.1))
    deviation = float(R.get("deviation", 0))
    pos52 = float(R.get("pos52", 50))
    patterns = R.get("patterns", []) or []
    news_rows = R.get("news", []) or []
    pos_news = [r for r in news_rows if r.get("sentiment") == "正面"]
    neg_news = [r for r in news_rows if r.get("sentiment") == "负面"]

    short = float(technical_profile.get("short", 50))
    mid = float(technical_profile.get("mid", 50))
    long = float(technical_profile.get("long", 50))
    vol_ratio = float(volume_info.get("vol_ratio", 1.0))
    trend_score = float(trend.get("trend_score", 50))
    arrangement = trend.get("arrangement", "")
    rets = momentum.get("returns", {})
    r5 = float(rets.get("5日", 0))
    r20 = float(rets.get("20日", 0))

    # 上涨因素
    if arrangement == "多头排列":
        rise.append({"title": "均线多头排列", "desc": f"短期/中期/长期均线呈多头排列，5日/10日/20日MA向上发散，趋势方向向上，支撑逐级抬升。", "stars": 3})
    elif arrangement == "震荡偏多":
        rise.append({"title": "均线震荡偏多", "desc": "均线系统总体偏向多头，价格运行于主要均线上方，但尚未完全发散。", "stars": 2})
    if trend_score >= 60:
        rise.append({"title": "趋势动能偏强", "desc": f"趋势得分 {trend_score:.0f}，价格运行在强势区间，短期均线斜率为正，回调受支撑。", "stars": 3 if trend_score >= 75 else 2})
    if vol_ratio >= 1.3:
        rise.append({"title": "量能明显放大", "desc": f"量比 {vol_ratio:.2f}，成交量高于近期平均水平 {vol_ratio*100-100:.0f}%，资金关注度提升，量价配合健康。", "stars": 3 if vol_ratio >= 2 else 2})
    if sector_score >= 60:
        rise.append({"title": "所属板块强势", "desc": f"板块强度得分 {sector_score:.0f}，行业热度居前，板块内资金流入明显，龙头带动效应突出。", "stars": 3 if sector_score >= 75 else 2})
    if pos_news:
        title = pos_news[0].get("title", "")[:36]
        rise.append({"title": "正面新闻催化", "desc": f"检测到 {len(pos_news)} 条正面新闻，最新一条：{title}...，形成事件催化，提升市场风险偏好。", "stars": 2})
    if current_price > 0 and resistance > current_price and (resistance - current_price) / current_price < 0.03:
        rise.append({"title": "临近压力位", "desc": f"现价 ¥{current_price:.2f} 已接近压力 ¥{resistance:.2f}（距突破仅 {(resistance-current_price)/current_price*100:.1f}%），突破后有望打开上行空间。", "stars": 2})
    if short >= 65 and mid >= 55:
        rise.append({"title": "短中期共振向上", "desc": f"短期 {short:.0f} 分 / 中期 {mid:.0f} 分 / 长期 {long:.0f} 分，多周期信号共振，方向一致。", "stars": 3})
    if r5 > 0 and r20 > 0:
        rise.append({"title": "近期收益为正", "desc": f"5日 {r5:+.2f}% / 20日 {r20:+.2f}%，短期与中期收益均录得上涨，跑赢同期大盘基准概率较高。", "stars": 2 if r5 + r20 < 10 else 3})
    if deviation < -5:
        rise.append({"title": "乖离率偏低", "desc": f"收盘价相对 MA20 偏离 {deviation:+.1f}%，短期超跌，存在技术性修复机会。", "stars": 2})
    if pos52 < 20:
        rise.append({"title": "处于52周低位", "desc": f"当前价处于近 52 周价格区间底部（{pos52:.0f}%），估值/价格安全边际较高。", "stars": 2})
    # K线形态
    if patterns:
        bull_patterns = [p for p in patterns if any(k in p for k in ["底", "金叉", "突破", "阳", "多", "红三", "启明"])]
        if bull_patterns:
            rise.append({"title": f"K线形态积极：{bull_patterns[0]}", "desc": f"近期形成 {', '.join(bull_patterns[:3])} 等偏多技术形态，短期结构改善。", "stars": 2})

    # 下跌因素
    if arrangement == "空头排列":
        fall.append({"title": "均线空头排列", "desc": "短期/中期/长期均线呈空头排列，5日/10日/20日MA向下发散，趋势方向向下。", "stars": 3})
    elif arrangement == "震荡偏空":
        fall.append({"title": "均线震荡偏空", "desc": "均线系统总体偏向空头，价格运行于主要均线下方，支撑尚不明显。", "stars": 2})
    if trend_score <= 40:
        fall.append({"title": "趋势动能偏弱", "desc": f"趋势得分 {trend_score:.0f}，价格运行在弱势区间，反弹受阻，重心下移。", "stars": 3 if trend_score <= 30 else 2})
    if vol_ratio <= 0.8:
        fall.append({"title": "量能持续萎缩", "desc": f"量比 {vol_ratio:.2f}，成交量低于近期平均水平 {100-vol_ratio*100:.0f}%，交投清淡，缺乏资金关注。", "stars": 3 if vol_ratio <= 0.5 else 2})
    if sector_score <= 40:
        fall.append({"title": "所属板块弱势", "desc": f"板块强度得分 {sector_score:.0f}，行业热度靠后，板块内资金流出，龙头走弱。", "stars": 3 if sector_score <= 30 else 2})
    if neg_news:
        title = neg_news[0].get("title", "")[:36]
        fall.append({"title": "负面新闻压制", "desc": f"检测到 {len(neg_news)} 条负面新闻，最新一条：{title}...，构成情绪压制与事件风险。", "stars": 2})
    if current_price > 0 and support > 0 and current_price < support:
        fall.append({"title": "跌破支撑位", "desc": f"现价 ¥{current_price:.2f} 已跌破支撑 ¥{support:.2f}，技术形态走弱，下方空间可能打开。", "stars": 3})
    if short <= 40 and mid <= 50:
        fall.append({"title": "短中期共振向下", "desc": f"短期 {short:.0f} 分 / 中期 {mid:.0f} 分 / 长期 {long:.0f} 分，多周期信号偏空，方向一致。", "stars": 3})
    if r5 < 0 and r20 < 0:
        fall.append({"title": "近期收益为负", "desc": f"5日 {r5:+.2f}% / 20日 {r20:+.2f}%，短期与中期收益均录得下跌，弱于同期大盘基准。", "stars": 2 if abs(r5 + r20) < 10 else 3})
    if deviation > 5:
        fall.append({"title": "乖离率偏高", "desc": f"收盘价相对 MA20 偏离 {deviation:+.1f}%，短期超买，存在技术性回调压力。", "stars": 2})
    if pos52 > 80:
        fall.append({"title": "处于52周高位", "desc": f"当前价处于近 52 周价格区间顶部（{pos52:.0f}%），高位回调与获利回吐风险加大。", "stars": 2})
    # K线形态
    if patterns:
        bear_patterns = [p for p in patterns if any(k in p for k in ["顶", "死叉", "跌破", "阴", "空", "黑三", "乌云"])]
        if bear_patterns:
            fall.append({"title": f"K线形态偏空：{bear_patterns[0]}", "desc": f"近期形成 {', '.join(bear_patterns[:3])} 等偏空技术形态，短期结构转弱。", "stars": 2})

    # 若因素过少，补充默认项保证展示不空
    if not rise:
        rise.append({"title": "暂无明显上涨驱动", "desc": "当前未检测到强势的做多信号，建议结合大盘与板块综合判断。", "stars": 1})
    if not fall:
        fall.append({"title": "暂无明显下跌风险", "desc": "当前未检测到强势的做空信号，但需关注支撑与量能变化。", "stars": 1})

    # 按强度排序，并为前两名打上「核心」标签
    rise.sort(key=lambda x: x["stars"], reverse=True)
    fall.sort(key=lambda x: x["stars"], reverse=True)
    for idx, f in enumerate(rise):
        f["tag"] = "核心" if idx < 2 else ""
    for idx, f in enumerate(fall):
        f["tag"] = "核心" if idx < 2 else ""
    return rise, fall


def _factor_list_html(title: str, factors: list[dict]) -> str:
    """1:1 仿参考图渲染「利好清单 / 利空清单」卡片：编号 + 标题 + 新增/核心标签 + 强度星级 + 详细描述。"""
    if not factors:
        return ""
    is_up = "利好" in title or "上涨" in title
    accent = "#009e60" if is_up else "#dc2626"
    tag_bg = "#059669" if is_up else "#dc2626"
    # 跟随全局主题：暗夜/白天 CSS 变量
    bg = "var(--card)"
    border = "var(--border)"
    txt = "var(--txt)"
    txt2 = "var(--txt2)"
    items = []
    for i, f in enumerate(factors[:8], 1):
        stars = "★" * f["stars"] + "☆" * (3 - f["stars"])
        tag = f.get("tag", "")
        tag_html = (
            f'<span style="display:inline-block;background:{tag_bg};color:#fff;'
            f'font-size:11px;font-weight:700;padding:1px 8px;border-radius:4px;margin-right:8px;">{tag}</span>'
        ) if tag else ""
        items.append(
            f'<div style="display:flex;gap:12px;padding:14px 16px;margin-bottom:10px;'
            f'background:var(--card2);border-radius:12px;border-left:4px solid {accent};">'
            f'<div style="min-width:28px;height:28px;border-radius:50%;background:{accent};'
            f'color:#fff;display:flex;align-items:center;justify-content:center;'
            f'font-size:14px;font-weight:800;">{i}</div>'
            f'<div style="flex:1;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">'
            f'<div style="font-size:15px;font-weight:700;color:{txt};line-height:1.4;">{tag_html}{f["title"]}</div>'
            f'<div style="font-size:12px;color:{accent};font-weight:700;white-space:nowrap;">强度 {stars}</div>'
            f'</div>'
            f'<div style="font-size:12.5px;color:{txt2};line-height:1.7;">{f["desc"]}</div>'
            f'</div></div>'
        )
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:18px;padding:18px;">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{accent};"></span>'
        f'<div style="font-size:17px;font-weight:700;color:{txt};">{title}</div></div>'
        f'{"".join(items)}</div>'
    )


def _build_logic_lists(R: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """基于分析结果 R 构建 利好逻辑 / 利空逻辑 / 致命风险 条目（叙事级 + 高置信风险）。"""
    technical_profile = R.get("technical_profile", {}) or {}
    volume_info = R.get("volume_info", {}) or {}
    trend = R.get("trend", {}) or {}
    momentum = R.get("momentum", {}) or {}
    current_price = float(R.get("current_price", 0))
    support = float(R.get("support", 0))
    resistance = float(R.get("resistance", current_price * 1.1))
    deviation = float(R.get("deviation", 0))
    pos52 = float(R.get("pos52", 50))
    patterns = R.get("patterns", []) or []
    news_rows = R.get("news_rows", []) or []
    pos_news = [r for r in news_rows if r.get("sentiment") == "正面"]
    neg_news = [r for r in news_rows if r.get("sentiment") == "负面"]
    composite = float(R.get("composite", 50))
    verdict = R.get("verdict", "持有")
    sector_score = float(R.get("sector_score", 55))
    news_score = float(R.get("news_score", 50))
    arrangement = trend.get("arrangement", "")
    vol_ratio = float(volume_info.get("vol_ratio", 1.0))
    rets = momentum.get("returns", {})
    r5 = float(rets.get("5日", 0))
    r20 = float(rets.get("20日", 0))
    short = float(technical_profile.get("short", 50))
    mid = float(technical_profile.get("mid", 50))
    long = float(technical_profile.get("long", 50))

    # 利好逻辑（叙事）
    rise_logic = []
    if verdict == "看多":
        rise_logic.append({"title": "综合研判看多", "desc": f"综合评分 {composite:.0f} 分，系统判断当前处于偏多格局，建议以多头思路对待。", "core": True})
    if arrangement in ("多头排列", "震荡偏多"):
        rise_logic.append({"title": "趋势结构完整", "desc": f"均线{arrangement}，价格运行在中长期均线上方，趋势方向向上，支撑逐级抬升。", "core": True})
    if short >= 65 and mid >= 55:
        rise_logic.append({"title": "短中期共振向上", "desc": f"短期 {short:.0f} 分 / 中期 {mid:.0f} 分 / 长期 {long:.0f} 分，多周期信号同向，方向一致性高。", "core": True})
    if vol_ratio >= 1.3:
        rise_logic.append({"title": "资金放量推动", "desc": f"量比 {vol_ratio:.2f}，成交量高于近期均值，资金关注度提升，量价配合健康。", "core": False})
    if sector_score >= 60:
        rise_logic.append({"title": "板块景气向上", "desc": f"所属板块强度 {sector_score:.0f} 分，行业热度居前，龙头带动效应突出。", "core": True})
    if pos_news:
        rise_logic.append({"title": "正面事件催化", "desc": f"检测到 {len(pos_news)} 条正面新闻，事件驱动提升市场风险偏好。", "core": False})
    if patterns:
        bull_patterns = [p for p in patterns if any(k in p for k in ["底", "金叉", "突破", "阳", "多", "红三", "启明"])]
        if bull_patterns:
            rise_logic.append({"title": f"技术形态偏多：{bull_patterns[0]}", "desc": f"近期出现 {', '.join(bull_patterns[:3])} 等偏多信号，短期结构改善。", "core": False})
    if r5 > 0 and r20 > 0:
        rise_logic.append({"title": "短期/中期收益为正", "desc": f"5日 {r5:+.2f}% / 20日 {r20:+.2f}%，价格重心上移，跑赢同期大盘概率较高。", "core": False})
    if current_price > 0 and resistance > current_price and (resistance - current_price) / current_price < 0.03:
        rise_logic.append({"title": "临近压力位待突破", "desc": f"现价 ¥{current_price:.2f} 距压力 ¥{resistance:.2f} 仅 {(resistance-current_price)/current_price*100:.1f}%，突破后有望打开上行空间。", "core": False})
    if pos52 < 20:
        rise_logic.append({"title": "价格处于低位区间", "desc": f"当前价处于近 52 周底部（{pos52:.0f}%），估值/价格安全边际较高。", "core": False})
    if not rise_logic:
        rise_logic.append({"title": "暂无明确多头逻辑", "desc": "当前未形成强一致性的做多叙事，建议等待更清晰的催化或支撑确认。", "core": False})

    # 利空逻辑（叙事）
    fall_logic = []
    if verdict == "看空":
        fall_logic.append({"title": "综合研判看空", "desc": f"综合评分 {composite:.0f} 分，系统判断当前处于偏空格局，建议以防御思路对待。", "core": True})
    if arrangement in ("空头排列", "震荡偏空"):
        fall_logic.append({"title": "趋势结构走弱", "desc": f"均线{arrangement}，价格运行在中长期均线下方，反弹受阻，重心下移。", "core": True})
    if short <= 40 and mid <= 50:
        fall_logic.append({"title": "短中期共振向下", "desc": f"短期 {short:.0f} 分 / 中期 {mid:.0f} 分 / 长期 {long:.0f} 分，多周期信号偏空，方向一致性高。", "core": True})
    if vol_ratio <= 0.8:
        fall_logic.append({"title": "量能持续萎缩", "desc": f"量比 {vol_ratio:.2f}，成交低于近期均值，交投清淡，缺乏资金承接。", "core": False})
    if sector_score <= 40:
        fall_logic.append({"title": "板块景气向下", "desc": f"所属板块强度 {sector_score:.0f} 分，行业热度靠后，龙头走弱拖累个股。", "core": True})
    if neg_news:
        fall_logic.append({"title": "负面事件压制", "desc": f"检测到 {len(neg_news)} 条负面新闻，情绪面承压，构成事件风险。", "core": False})
    if patterns:
        bear_patterns = [p for p in patterns if any(k in p for k in ["顶", "死叉", "跌破", "阴", "空", "黑三", "乌云"])]
        if bear_patterns:
            fall_logic.append({"title": f"技术形态偏空：{bear_patterns[0]}", "desc": f"近期出现 {', '.join(bear_patterns[:3])} 等偏空信号，短期结构转弱。", "core": False})
    if r5 < 0 and r20 < 0:
        fall_logic.append({"title": "短期/中期收益为负", "desc": f"5日 {r5:+.2f}% / 20日 {r20:+.2f}%，价格重心下移，弱于同期大盘。", "core": False})
    if current_price > 0 and support > 0 and current_price < support:
        fall_logic.append({"title": "跌破关键支撑", "desc": f"现价 ¥{current_price:.2f} 已跌破支撑 ¥{support:.2f}，技术形态走弱，下方空间可能打开。", "core": True})
    if pos52 > 80:
        fall_logic.append({"title": "价格处于高位区间", "desc": f"当前价处于近 52 周顶部（{pos52:.0f}%），获利回吐与高位回调风险加大。", "core": False})
    if not fall_logic:
        fall_logic.append({"title": "暂无明确空头逻辑", "desc": "当前未形成强一致性的做空叙事，但仍需关注支撑与量能变化。", "core": False})

    # 致命风险（必须盯死）
    fatal = []
    if current_price > 0 and support > 0 and current_price < support and vol_ratio >= 1.3:
        fatal.append({"title": "破位放量杀跌", "desc": f"跌破支撑 ¥{support:.2f} 且量比 {vol_ratio:.2f} 放大，空头主导，可能引发连锁止损。", "core": True})
    if short <= 35 and mid <= 45 and vol_ratio <= 0.8:
        fatal.append({"title": "空头共振+流动性枯竭", "desc": "短中期趋势同步向下，且成交量萎缩，反弹无力，阴跌风险极高。", "core": True})
    if pos52 > 85 and (vol_ratio <= 0.8 or deviation > 5):
        fatal.append({"title": "高位滞涨/超买背离", "desc": f"处于 52 周高位（{pos52:.0f}%），量能不济或乖离过高，随时可能触发快速回调。", "core": True})
    if neg_news and news_score < 40:
        fatal.append({"title": "负面新闻+情绪恶化", "desc": f"负面新闻叠加情绪得分低至 {news_score:.0f}，短期风险偏好骤降，易现恐慌抛售。", "core": True})
    if sector_score < 30:
        fatal.append({"title": "板块系统性走弱", "desc": f"板块强度仅 {sector_score:.0f} 分，行业资金持续流出，个股难以独善其身。", "core": True})
    if not fatal:
        fatal.append({"title": "暂未识别到致命风险", "desc": "当前未触发高置信度的极端风险信号，但仍需遵守止损纪律与仓位管理。", "core": False})

    return rise_logic[:5], fall_logic[:5], fatal[:4]


def _logic_list_html(title: str, items: list[dict], accent: str, icon: str = "") -> str:
    """渲染叙事级逻辑卡片：标题 + 编号条目 + 核心标签 + 描述，适配暗夜/白天主题。"""
    if not items:
        return ""
    txt = "var(--txt)"
    txt2 = "var(--txt2)"
    parts = []
    for i, it in enumerate(items, 1):
        core = it.get("core", False)
        tag = f'<span style="display:inline-block;background:{accent};color:#fff;font-size:11px;font-weight:700;padding:1px 8px;border-radius:4px;margin-right:8px;">核心</span>' if core else ""
        parts.append(
            f'<div style="display:flex;gap:12px;padding:13px 14px;margin-bottom:8px;background:var(--card);border-radius:10px;border-left:3px solid {accent};">'
            f'<div style="min-width:26px;height:26px;border-radius:50%;background:{accent};color:#fff;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;">{i}</div>'
            f'<div style="flex:1;">'
            f'<div style="font-size:14.5px;font-weight:700;color:{txt};line-height:1.4;margin-bottom:4px;">{tag}{it["title"]}</div>'
            f'<div style="font-size:12px;color:{txt2};line-height:1.7;">{it["desc"]}</div>'
            f'</div></div>'
        )
    return (
        f'<div style="background:var(--card2);border:1px solid var(--border);border-radius:16px;padding:16px;border-left:5px solid {accent};margin-bottom:14px;">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">'
        f'<span style="font-size:20px;">{icon}</span>'
        f'<div style="font-size:17px;font-weight:700;color:{txt};">{title}</div></div>'
        f'{"".join(parts)}</div>'
    )


def _calc_trade_levels(current_price: float, df: pd.DataFrame, support: float, resistance: float):
    """
    基于 ATR 与支撑/压力，计算合理的入场/目标/止损价。
    止损价不超过现价 8%，避免低价股出现 ¥101 股票止损 ¥43 的荒谬结果。
    """
    if current_price is None or current_price <= 0:
        return current_price, resistance, support, 0.0

    # ATR14
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else current_price * 0.025
    if np.isnan(atr14) or atr14 <= 0:
        atr14 = current_price * 0.025

    # 止损：2.5*ATR 下方，但保底最多跌 8%（与支撑位取更严者）
    stop_atr = current_price - 2.5 * atr14
    stop_max_pct = current_price * 0.92
    # 若支撑位在 stop_max_pct 与 current_price 之间，采用支撑位；否则用 ATR 止损与 8% 的较大值（ closer to price）
    if support > 0 and support < current_price and support > stop_max_pct:
        stop_price = support
    else:
        stop_price = max(stop_atr, stop_max_pct)
    stop_price = max(stop_price, current_price * 0.80)  # 绝对下限 20%（极端保护）

    # 入场：比现价低 0.5 ATR 的回踩价，但不跌破止损
    entry_price = max(current_price - 0.5 * atr14, stop_price * 1.01)

    # 目标：3*ATR 上方，但不超过压力位与 15% 涨幅上限
    target_atr = current_price + 3 * atr14
    target_pct_cap = current_price * 1.15
    target_price = min(target_atr, resistance, target_pct_cap)
    target_price = max(target_price, current_price * 1.03)  # 至少 3% 空间

    return round(entry_price, 2), round(target_price, 2), round(stop_price, 2), round(atr14, 2)

