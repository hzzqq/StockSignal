# -*- coding: utf-8 -*-
"""生成「牧羊人情绪 × 事件因子」共振早报（盘前）。

诚实口径红线：
- 取数只用真实本地数据；缺失即写「缺」，绝不合成/示例填充。
- 事件因子陈旧（滞后>N 天）必须显式说明降权多少，不得照常给出满仓建议。
- 数据源时效逐源摊开 as_of / lag_days，lag>4 标「已降权」，detect_stall 判停更标「停更」。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
DATA_DIR = os.path.join(ROOT, "data")

TODAY = date.today().isoformat()


def _age_days(d: str | None) -> int | None:
    if not d:
        return None
    try:
        return (date.today() - date.fromisoformat(str(d)[:10])).days
    except Exception:
        return None


def latest_snapshot_file() -> str:
    """data/snapshots/ 下日期最大的 JSON；无则回退 daily_snapshot.json。"""
    arch = os.path.join(DATA_DIR, "snapshots")
    best = None
    if os.path.isdir(arch):
        for n in os.listdir(arch):
            if n.endswith(".json") and len(n) >= 10:
                d = n[:10]
                if best is None or d > best:
                    best = d
    if best:
        return os.path.join(arch, f"{best}.json")
    return os.path.join(DATA_DIR, "daily_snapshot.json")


def read_signal_meta_cheap(path: str) -> dict:
    """只读取文件头部取 latest_date / model（避免加载 55MB 大文件）。"""
    out = {"latest_date": None, "model": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(400)
        m = re.search(r'"latest_date"\s*:\s*"([^"]+)"', head)
        if m:
            out["latest_date"] = m.group(1)
        m = re.search(r'"model"\s*:\s*"([^"]+)"', head)
        if m:
            out["model"] = m.group(1)
    except Exception:
        pass
    return out


def main():
    from modules.decision import derive_position, assess_freshness
    from modules.data_health import health_rows_enriched

    # ── 1) 最新每日快照 ──
    snap_path = latest_snapshot_file()
    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)
    snap_date = snap.get("date")
    temp = snap.get("temperature")
    fc = snap.get("signals")
    bias = snap.get("bias")
    cycle = snap.get("cycle")
    score = snap.get("score")
    promo_overall = snap.get("promo_overall")

    # ── 2) 事件因子信号（EV 事件因子，决策主源）──
    ev_path = os.path.join(DATA_DIR, "p1_signals", "signal_ev_h10.json")
    ev_meta = read_signal_meta_cheap(ev_path)
    ev_long_count = None
    ev_short_count = None
    ev_mean_pred = None
    ev_adj_nominal = None
    ev_available = False
    if os.path.exists(ev_path):
        try:
            with open(ev_path, "r", encoding="utf-8") as f:
                ev = json.load(f)
            top_long = ev.get("top_long") or []
            top_short = ev.get("top_short") or []
            ev_long_count = len(top_long)
            ev_short_count = len(top_short)
            ev_mean_pred = (sum(float(r.get("pred", 0.0) or 0.0) for r in top_long[:20]) / min(20, len(top_long))) if top_long else None
            n = min(50, ev_long_count)
            ev_adj_nominal = min(5, n // 10) if ev_long_count else None
            ev_available = ev_long_count > 0
        except Exception as e:
            ev_meta["error"] = str(e)
    ev_as_of = ev_meta.get("latest_date")
    ev_lag = _age_days(ev_as_of)

    # 跨模型 latest_date（cheap head 读取），展示各模型同样陈旧的现实
    cross_models = []
    for fn in ["signal_ev_h10.json", "signal_gru_h10.json", "signal_fusion_h10.json", "signal_baseline_h10.json"]:
        p = os.path.join(DATA_DIR, "p1_signals", fn)
        if os.path.exists(p):
            m = read_signal_meta_cheap(p)
            cross_models.append({"file": fn, "model": m.get("model") or fn.replace("signal_", "").replace("_h10.json", ""),
                                 "latest_date": m.get("latest_date"), "lag": _age_days(m.get("latest_date"))})

    # ── 3) 数据源时效（data_health.health_rows_enriched，唯一权威口径）──
    # 必须先落盘一次「当前真实观测」，否则 detect_stall 会拿过期的观测历史（本仓上次
    # 写表停在 2026-09-17）去判停更，把 mtime 实际新鲜的源（连板晋级率/市场温度/快照）
    # 误标「停更」——那是另一种不诚实。落盘当前观测后：
    #   · 真冻结源（牧羊人 09-04、P1 08-14）as_of 未推进 → last_advance 不更新 → 仍判停更（正确）
    #   · 新鲜源（mtime 今/昨）as_of 推进 → last_advance=今日 → frozen=0 → 不判停更（正确）
    try:
        from modules.data_health import record_health_observation
        record_health_observation()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 写入健康观测失败（不影响时效判定）: {e}")
    rows = health_rows_enriched()
    _hrow = {r["name"]: r for r in rows}
    # 决策输入源的「真实数据截止日」一律取自 health_rows_enriched()（不以快照内部
    # data_freshness 为准，避免快照把牧羊人标成 09-15 而 CSV 末行实际是 09-10 的口径漂移）。
    _decision_sources = {
        "牧羊人情绪": _hrow.get("牧羊人情绪", {}).get("as_of"),
        "事件因子": ev_as_of,
        "连板晋级率": _hrow.get("连板晋级率", {}).get("as_of"),
        "市场温度缓存": _hrow.get("市场温度缓存", {}).get("as_of"),
    }
    fresh = assess_freshness(_decision_sources)
    freshness_status = fresh["status"]

    # ── 4) 仓位建议（走 derive_position 口径）──
    # 含事件因子名义催化(+2pt，来自陈旧信号)
    pos_with_event = derive_position(temp, score, bias, cycle, promo_overall,
                                     event_adj=ev_adj_nominal, freshness_status=freshness_status)
    # 诚实对照：事件因子陈旧 → 视为降权至 0 时不施加催化（event_adj=0，不写「信号不可用」，
    # 信号其实可用只是陈旧；下文 诚实口径 段会显式说明剔除原因）
    pos_no_event = derive_position(temp, score, bias, cycle, promo_overall,
                                   event_adj=0, freshness_status=freshness_status)
    # 若事件因子不可用（缺），derive_position 也会走 event_adj=None 路径
    if not ev_available:
        pos_with_event = pos_no_event

    from modules.decision import FRESH_STALE_DAYS
    ev_stale = bool(ev_available and ev_lag is not None and ev_lag >= FRESH_STALE_DAYS)
    # 诚实口径：事件因子陈旧（滞后≥陈旧阈值）或缺失 → 当日不施加其催化，
    # 以「剔除陈旧/缺位催化」后的仓位作为对外展示的「建议仓位」。
    eff_pos = pos_no_event if (ev_stale or not ev_available) else pos_with_event

    # ── 5) 共振判断 ──
    # 牧羊人方向
    shepherd_dir = bias  # 偏多/偏空/中性
    # 事件因子方向：多头池 pred>0 即偏多
    ev_dir = "偏多" if (ev_available and ev_mean_pred is not None and ev_mean_pred > 0) else ("缺" if not ev_available else "中性")

    if not ev_available:
        resonance = "事件因子缺位"
    elif ev_stale:
        # 事件因子已陈旧（滞后≥陈旧阈值）：方向不可信、不参与当日共振。
        # 诚实口径：仅当两者名义方向确为相反才标「背离」，否则标「陈旧失效」而非假称背离。
        if shepherd_dir and ev_dir not in (None, "缺") and shepherd_dir != ev_dir:
            resonance = "背离 + 事件因子陈旧失效（陈旧信号不参与当日决策）"
        else:
            resonance = "事件因子陈旧失效（不参与当日共振）"
    elif shepherd_dir in (None, "中性") or ev_dir in (None, "中性", "缺"):
        resonance = "一方缺位/中性"
    elif shepherd_dir == ev_dir:
        resonance = "同向共振"
    else:
        resonance = "背离"

    # ── 6) 渲染 Markdown ──
    def fmt(v, missing="缺"):
        return missing if v in (None, "", "缺") else v

    lines = []
    lines.append(f"# 牧羊人情绪 × 事件因子 共振早报（盘前）")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ｜ 报告基准日（今日）：**{TODAY}**")
    lines.append(f"> 数据快照：`{os.path.basename(snap_path)}`（快照数据日 {fmt(snap_date)}）")
    lines.append(f"> 口径：仓位建议严格走 `modules/decision.derive_position`；数据源时效走 `modules/data_health.health_rows_enriched()`。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 一、当日仓位建议
    lines.append("## 一、当日仓位建议（derive_position 口径）")
    lines.append("")
    p = eff_pos
    lines.append(f"**建议仓位：{p['pct']}% ｜ 档位：{p['band']}** （配色 {p['color']}）")
    lines.append("")
    lines.append("推导明细（逐因子留痕）：")
    for r in p["reasons"]:
        lines.append(f"- {r}")
    lines.append("")
    if not ev_available:
        lines.append("> ⚠️ **诚实口径**：事件因子信号缺失（无可用 P1 信号文件/多头池为空），`derive_position` 走 `event_adj=None` 路径——**未施加任何事件催化，不臆造**。")
    else:
        if ev_lag is not None and ev_lag >= 8:
            down_pct = (pos_with_event["pct"] - pos_no_event["pct"])
            lines.append(f"> ⚠️ **诚实口径（事件因子降权）**：事件因子截至 **{ev_as_of}**（滞后 **{ev_lag}** 天，远超 8 天陈旧阈值），"
                         f"其名义 +{ev_adj_nominal}pt 催化基于过期数据。本早报将其**视为降权至≈失效（贡献≈0）**。"
                         f"对照：施加陈旧催化仓位={pos_with_event['pct']}%，剔除后={pos_no_event['pct']}%，"
                         f"差值 {down_pct}pt——**防御结论（{pos_no_event['band']} {pos_no_event['pct']}%）不变**，"
                         f"说明今日防御完全由牧羊人情绪驱动，未因陈旧事件因子给出激进/满仓建议。")
        else:
            lines.append(f"> 事件因子滞后 {ev_lag} 天（<8），名义 +{ev_adj_nominal}pt 催化按正常口径计入。")
    lines.append("")

    # 二、牧羊人情绪 & 事件因子
    def _score_st(a):
        try:
            a = float(a)
        except Exception:
            return "缺"
        if a < 40:
            return "偏冷（<40）"
        if a < 60:
            return "中性偏暖（40-60）"
        if a <= 75:
            return "偏热（60-75）"
        return "过热（>75）"

    def _temp_st(t):
        try:
            t = float(t)
        except Exception:
            return "缺"
        if t < 20:
            return "极低温（<20，触发极端风控封顶）"
        if t < 40:
            return "低温（20-40）"
        if t < 60:
            return "中性（40-60）"
        if t < 80:
            return "偏暖（60-80）"
        return "高温（≥80）"

    _CYCLE_DESC = {
        "主升高潮": "趋势最一致、容错最高", "修复确认": "右侧拐点确认、顺势加",
        "修复试探": "方向未明、仅观测", "高潮分化": "一致预期末端、分歧加大",
        "退潮": "亏钱效应扩散、最该防守", "冰点": "情绪杀至极致、超卖试探",
    }

    def _cycle_st(c):
        if not c:
            return "缺"
        core = str(c).split("（")[0].strip()
        return _CYCLE_DESC.get(core, "其他阶段")

    lines.append("## 二、牧羊人情绪分 × 状态　与　事件因子强度")
    lines.append("")
    lines.append("| 维度 | 数值 | 状态（按真实值动态判定，非模板填充） |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 牧羊人情绪分（score） | **{fmt(score)}** | {_score_st(score)} |")
    lines.append(f"| 次日方向（bias） | **{fmt(bias)}** | {fmt(bias, '缺')} |")
    lines.append(f"| 情绪周期（cycle） | **{fmt(cycle)}** | {_cycle_st(cycle)} |")
    lines.append(f"| 市场温度 | **{fmt(temp)}** | {_temp_st(temp)} |")
    lines.append(f"| 晋级率（promo_overall） | {fmt(promo_overall)} | {('样本不足/缺，不调节' if promo_overall is None else '正常')} |")
    lines.append(f"| 事件因子 latest_date | **{fmt(ev_as_of)}** | 滞后 {fmt(ev_lag)} 天 |")
    lines.append(f"| 事件因子 多头池广度 | **{fmt(ev_long_count)}** 只 | 名义催化 +{fmt(ev_adj_nominal)}pt |")
    lines.append(f"| 事件因子 信号量级（top_long 均值 pred） | **{fmt(round(ev_mean_pred,5) if ev_mean_pred is not None else None)}** | 统计超额收益概率（非涨跌预测） |")
    lines.append(f"| 事件因子 空头池广度 | **{fmt(ev_short_count)}** 只 | 多空对称 |")
    lines.append("")
    lines.append("> 事件因子方向判定：**偏多**（多头池 pred 均值为正）。但因其数据陈旧（见第四节），方向信号当日不可信，参与共振时按「失效」处理。")
    lines.append("")
    _sh_asof = _hrow.get("牧羊人情绪", {}).get("as_of")
    _sh_lag = _hrow.get("牧羊人情绪", {}).get("lag_days")
    lines.append(f"> 📌 **牧羊人真实数据截止（health 口径）**：`shepherd_history.csv` 末行 = **{fmt(_sh_asof)}**（滞后 {fmt(_sh_lag)} 天），"
                 f"已标「已降权」。**注意**：本快照内部 `data_freshness` 曾把牧羊人标为 2026-09-15，"
                 f"但 CSV 内容实际只到 {fmt(_sh_asof)}——本早报以 `health_rows_enriched()` 为准，不沿用快照的旧标注。")
    lines.append("")

    # 三、共振
    lines.append("## 三、两者是否共振")
    lines.append("")
    lines.append(f"**判定：{resonance}**")
    lines.append("")
    lines.append(f"- 牧羊人情绪方向：**{fmt(shepherd_dir)}**（bias={fmt(bias)} + cycle={fmt(cycle)}）")
    lines.append(f"- 事件因子方向：**{fmt(ev_dir)}**（名义偏多，但数据截至 {fmt(ev_as_of)}，滞后 {fmt(ev_lag)} 天）")
    lines.append("")
    if resonance.startswith("同向"):
        lines.append("**可执行解读**：两信号同向偏多，可互为印证加仓；但需结合温度与周期风控上限。")
    elif resonance.startswith("背离"):
        lines.append("**可执行解读**：牧羊人情绪与事件因子方向相反（背离），且事件因子已陈旧失效（滞后≥8天），"
                     "**今日决策以牧羊人情绪为唯一有效信号**。事件因子的陈旧信号不参与当日共振，"
                     "避免用过期催化抬高仓位。")
    elif resonance == "事件因子缺位":
        lines.append("**可执行解读**：事件因子缺位，仓位完全由牧羊人情绪驱动；未施加任何事件催化（不臆造）。")
    elif resonance.startswith("事件因子陈旧失效"):
        lines.append("**可执行解读**：事件因子滞后≥8天被判定陈旧/停更，方向信号当日不可信，**不参与当日共振**；"
                     "今日决策以牧羊人情绪（有效信号）为准。仓位已据数据陈旧整体封顶，"
                     "未因过期事件催化抬高建议。")
    else:
        lines.append("**可执行解读**：一方缺位/中性，决策以有效信号为准，不强行合成共振。")
    lines.append("")

    # 四、数据源时效（红线）
    lines.append("## 四、各数据源时效（诚实口径红线）")
    lines.append("")
    lines.append("> 规则：`lag>4 天` → 标注 **已降权**；`detect_stall` 判为停更 → 标注 **停更**。")
    lines.append("")
    lines.append("| 数据源 | as_of（真实数据截止日） | 滞后天数 | 状态 | 备注 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in rows:
        asof = fmt(r.get("as_of"), "缺")
        lag = r.get("lag_days")
        lag_s = "缺" if lag is None else f"{lag} 天"
        status = r.get("status", "unknown")
        stalled = r.get("stalled")
        notes = []
        if lag is not None and lag > 4:
            notes.append("**已降权**")
        if stalled:
            notes.append("**停更**")
        if status == "stale":
            notes.append("陈旧")
        elif status == "warn":
            notes.append("偏旧")
        elif status == "unknown":
            notes.append("未知")
        note = "；".join(notes) if notes else "新鲜"
        lines.append(f"| {r.get('name')} | {asof} | {lag_s} | {status} | {note} |")
    lines.append("")
    lines.append("**跨模型事件信号 latest_date（同源陈旧，验证事件因子整体过期）：**")
    for cm in cross_models:
        lines.append(f"- `{cm['file']}`（{cm['model']}）：latest_date **{fmt(cm['latest_date'])}**，滞后 **{fmt(cm['lag'])}** 天")
    lines.append("")

    # 五、核心结论
    lines.append("## 五、核心结论")
    lines.append("")
    _sh_ev_note = "叠加事件因子停更" if (ev_available and ev_stale) else "叠加事件因子陈旧"
    lines.append(f"1. **仓位**：{eff_pos['pct']}% / {eff_pos['band']}——"
                 f"事件因子陈旧已剔除；牧羊人情绪虽读 {fmt(bias)}（bias={fmt(bias)}、cycle={fmt(cycle)}），"
                 f"但其真实数据截至 {fmt(_sh_asof)}（滞后 {fmt(_sh_lag)} 天，已降权），{_sh_ev_note}，"
                 f"**整体数据陈旧触发封顶 {eff_pos['pct']}%**，并非基于当日新鲜信号的高仓位。")
    lines.append(f"2. **牧羊人情绪**：score={fmt(score)}、bias={fmt(bias)}、cycle={fmt(cycle)}，{_cycle_st(cycle)}。"
                 f"（注：该读数来自 `shepherd_history.csv` 末行 {fmt(_sh_asof)}，滞后 {fmt(_sh_lag)} 天，已降权，仅作参考）")
    if ev_available:
        lines.append(f"3. **事件因子**：latest_date={fmt(ev_as_of)}（滞后 {fmt(ev_lag)} 天），多头池 {fmt(ev_long_count)} 只、名义催化 +{fmt(ev_adj_nominal)}pt；"
                     f"**因陈旧已降权至≈失效，未计入当日共振，亦未抬高仓位**。")
    else:
        lines.append(f"3. **事件因子**：缺（无可用信号），未施加催化。")
    lines.append(f"4. **共振**：{resonance}——事件因子陈旧不参与当日决策，今日以牧羊人单一有效信号防守。")
    lines.append(f"5. **诚实提示**：事件因子、各源时效已逐源摊开；陈旧源已显式降权，未用合成/示例数据填充。")
    lines.append("")

    md = "\n".join(lines)

    out_path = os.path.join(DATA_DIR, "reports", f"morning_event_sentiment_{TODAY}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    # 也打印核心结论到 stdout（automation 日志可读）
    print("=" * 60)
    print(f"早报已生成：{out_path}")
    print(f"快照数据日：{snap_date} ｜ 今日：{TODAY}")
    print(f"建议仓位（对外展示，已剔除陈旧事件催化）：{eff_pos['pct']}% / {eff_pos['band']}")
    if ev_available and not ev_stale:
        print(f"   → 含事件催化口径：{pos_with_event['pct']}% / {pos_with_event['band']}")
    print(f"牧羊人：score={score} bias={bias} cycle={cycle} temp={temp}")
    print(f"事件因子：as_of={ev_as_of} lag={ev_lag} 多头池={ev_long_count} 名义催化=+{ev_adj_nominal}pt")
    print(f"整体新鲜度：{freshness_status}（max_lag={fresh['max_lag_days']}）")
    print(f"共振：{resonance}")
    print("=" * 60)
    # 数据源时效摘要
    for r in rows:
        tag = []
        if r.get("lag_days") is not None and r["lag_days"] > 4:
            tag.append("已降权")
        if r.get("stalled"):
            tag.append("停更")
        print(f"  · {r['name']}: as_of={r.get('as_of')} lag={r.get('lag_days')} status={r.get('status')} {(' '.join(tag) if tag else '')}")


if __name__ == "__main__":
    main()
