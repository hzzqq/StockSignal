"""
modules/decision.py — 今日决策闭环的**单一真理源**（纯 Python，不依赖 streamlit）

为什么单独成模块：
    仓位推导逻辑被三处消费——① 决策面板页面（实时算）② 每日快照脚本（收盘落盘）
    ③ 首页 banner（读盘展示）。若各自实现一份，必然漂移成三套互相矛盾的仓位建议。
    这里收敛为唯一实现，三处共用。

设计约束：
    · **不 import streamlit** —— 快照脚本要在无 UI 的定时任务里跑。
    · 落盘/读取全用标准库，路径相对项目根 data/ 目录。
    · 任何单源失败都返回 None / 兜底值，绝不向上抛（脚本与首页都不能被它拖崩）。

红涨绿跌：偏多/激进=红(#ee2a2a)，偏空/防御=绿(#00d486)，中性=黄(#f59e0b)。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 项目根（modules/ 的上一级）
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
# SS_DATA_DIR 可重定向整个数据目录（测试隔离用；生产默认 data/）。
# conftest 在 pytest 启动时把它指到临时目录，避免测试写穿真实 data/。
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(ROOT, "data"))

# 每日决策快照落盘位置（首页 banner 与复盘回测都读它）
SNAPSHOT_PATH = os.path.join(DATA_DIR, "daily_snapshot.json")
SNAPSHOT_LOG = os.path.join(DATA_DIR, "daily_snapshot.log")
# 历史归档：一天一份，供「复盘归档 / 历史情绪回测」读，避免手动回填
ARCHIVE_DIR = os.path.join(DATA_DIR, "snapshots")


def archive_path(date: str) -> str:
    """历史快照文件路径：data/snapshots/YYYY-MM-DD.json"""
    return os.path.join(ARCHIVE_DIR, f"{date}.json")


def load_archive(date: str) -> dict | None:
    """读取指定日期的归档快照（复盘回测用）。"""
    try:
        with open(archive_path(date), "r", encoding="utf-8") as f:
            snap = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[decision] 归档读取失败 %s: %s", date, e)
        return None
    return snap if isinstance(snap, dict) else None


def list_archive_dates() -> list[str]:
    """列出已归档的日期（升序）。没有归档目录返回空列表，不抛。"""
    try:
        names = os.listdir(ARCHIVE_DIR)
    except OSError:
        return []
    return sorted(n[:10] for n in names if n.endswith(".json") and len(n) >= 10)

# 情绪周期六阶段 → 仓位调节（绝对百分点，叠加在温度基准之上）
# 取值依据（与主升/修复/退潮/冰点语义一致，且经过风控校准，见 I9）：
#   主升高潮 +5  ：趋势最一致、容错最高，可多扛一点
#   修复确认 +3  ：右侧拐点确认，顺势加
#   修复试探 0   ：方向未明，不加不减只观测
#   高潮分化 -5  ：一致预期末端、分歧加大，提前收
#   退潮   -10   ：亏钱效应扩散，最该防守的阶段，给最大负向
#   冰点   +5    ：情绪杀到极致=超卖，物极必反的试探性左侧买点
CYCLE_ADJ = {
    "主升高潮": 5, "修复确认": 3, "修复试探": 0,
    "高潮分化": -5, "退潮": -10, "冰点": 5,
}
BIAS_COLOR = {"偏多": "#ee2a2a", "偏空": "#00d486", "中性": "#f59e0b"}

# 仓位档位阈值（从高到低，pct 命中第一个 >= threshold 的档）
# 阈值刻度为「经验分档」，与红涨绿跌配色绑定（见 I9）：
#   80/60 偏多偏激进(红) · 40 中性(黄) · 20/0 偏空防御(绿)
_BANDS = [
    (80, "激进", "#ee2a2a"),
    (60, "偏多", "#ee2a2a"),
    (40, "中性", "#f59e0b"),
    (20, "偏空", "#00d486"),
    (0, "防御", "#00d486"),
]


# ───────────────────────── 仓位推导（唯一实现） ─────────────────────────
def derive_position(temp, score=None, bias=None, cycle_name=None, overall_promo=None,
                   event_adj: int | None = None) -> dict:
    """透明推导仓位建议。

    规则（逐条留痕，前端直接展示 reasons，让建议可解释而非黑箱）：
        base  = 市场温度(0-100) 当作基准仓位%
        + 方向调节（偏多 +8 / 偏空 -8）
        + 周期调节（主升 +5 / 修复确认 +3 / 高潮分化 -5 / 退潮 -10 / 冰点 +5 超卖试探）
        + 梯队晋级率调节（≥60% +5 / 40-60% 0 / 20-40% -3 / <20% -6）
        + 事件驱动催化调节（真实事件因子多头池广度映射，见 _event_position_adj）
        最终 clamp 到 5~95%。

    :param temp: 市场温度 0-100（None 时兜底 50）
    :param score: 次日情绪评分，仅留痕用，不参与计算（保持规则可解释）
    :param bias: 偏多/偏空/中性
    :param cycle_name: 情绪周期六阶段名，可能带括号后缀（如「主升高潮（加速）」）
    :param overall_promo: 连板梯队整体晋级率(%)，None 表示数据缺失（不加不减）
    :param event_adj: 事件驱动仓位调节(绝对百分点)；None/0 表示不调节。
                       来源为真实 P1 EV 事件因子多头池广度（见 _event_position_adj），
                       取不到真实信号时为 None —— 决策者不臆造事件催化。
    :return: dict(pct=int, band=str, color=str, reasons=list[str])
    """
    reasons: list[str] = []
    try:
        base = float(temp) if temp is not None else 50.0
    except (TypeError, ValueError):
        logger.warning("[decision] 温度入参非法 %r，兜底 50", temp)
        base = 50.0
    # 入参越界保护：温度语义是 0-100，异常源喂出 150/-20 会污染快照与展示。
    # 仅 clamp 基准仓位的输入；最终 pct 仍受 5~95 硬约束（双保险）。
    if base < 0.0 or base > 100.0:
        logger.warning("[decision] 温度 %s 越界[0,100]，已 clamp", base)
        base = max(0.0, min(100.0, base))
    pct = base
    reasons.append(f"市场温度 {base:.0f} 作为基准仓位")

    # 方向调节：次日方向是短周期最强信号，给固定 ±8pt 权重（偏多+8 / 偏空-8 / 中性0）
    b = (bias or "中性")
    if bias is not None and bias not in ("偏多", "偏空", "中性"):
        # 未知方向不静默当中性——告警让数据问题看得见，避免脏源悄悄改仓位
        logger.warning("[decision] 未知方向 %r，按中性处理", bias)
        b = "中性"
    badj = {"偏多": 8, "偏空": -8, "中性": 0}.get(b, 0)
    pct += badj
    reasons.append(f"次日方向「{b}」{'加' if badj >= 0 else '减'}仓 {abs(badj)}%")

    # 周期名可能带括号后缀，取括号前的核心名匹配
    cname_core = (cycle_name or "").split("（")[0].strip()
    cadj = CYCLE_ADJ.get(cname_core, 0)
    if cycle_name and cname_core not in CYCLE_ADJ:
        # 未知周期不静默按 0 调节——告警，避免 forecast 改了周期名而规则悄悄失效
        logger.warning("[decision] 未知情绪周期 %r，按 0 调节", cycle_name)
    pct += cadj
    if cadj:
        reasons.append(f"情绪周期「{cname_core}」{'加' if cadj >= 0 else '减'}仓 {abs(cadj)}%")

    if overall_promo is not None:
        # 梯队晋级率调节：接力强度是「赚钱效应能否延续」的硬指标（档位阈值见 I9）
        if overall_promo >= 60:
            padj, txt = 5, "梯队接力强（晋级率≥60%）"
        elif overall_promo >= 40:
            padj, txt = 0, "梯队晋级率中性"
        elif overall_promo >= 20:
            padj, txt = -3, "梯队偏薄（晋级率 20-40%）"
        else:
            padj, txt = -6, "梯队断档（晋级率<20%）"
        pct += padj
        reasons.append(f"{txt}：{'加' if padj >= 0 else '减'}仓 {abs(padj)}%")

    # 事件驱动催化调节：真实事件因子（P1 EV 多头池广度）映射的市场级仓位微调。
    # 接的是「事件驱动 + 市场情绪」决策主线的事件侧；取不到真实信号（event_adj=None）
    # 时不臆造催化。置于常规推导内、极端风控约束**内**——极端行情下沿/上沿（下面 165-172
    # 行）仍凌驾其上，所以事件催化也受极端风控封顶/兜底约束（注释修正：此前误写「约束外」）。
    if event_adj:
        pct += event_adj
        reasons.append(f"事件驱动催化：{'加' if event_adj >= 0 else '减'}仓 {abs(event_adj)}%")
    elif event_adj is None:
        # 事件信号不可用：明确留痕，让决策可解释「这次没靠事件催化」，也便于事后回测
        # 按 event_available 拆分命中率，回答「事件驱动到底有没有用」（见 decision_track.by_event）
        reasons.append("事件驱动信号不可用，未施加催化（不臆造）")

    pct = max(5.0, min(95.0, pct))

    # 极端行情硬约束（风控底线，凌驾于常规推导之上，见 I10）
    # · 冰点退潮双杀：温度<20 且处「退潮」周期 → 即使其他因子加仓也不许超过 30%
    #   （防止在流动性枯竭、接力资金缺席时重仓接飞刀；此约束在常规推导下多数已满足，
    #    作为极端行情的最后防线锁死上沿）
    # · 高潮分化过热：温度>=80 且处「高潮分化」周期 → 即使其他因子减仓也不许低于 40%
    #   （过热分歧期容易踏空主升末端，留底仓不空仓；同理作为下沿防线）
    if base < 20 and cname_core == "退潮":
        if pct > 30:
            reasons.append(f"⚠️ 极端风控：温度 {base:.0f}<20 且处退潮，仓位封顶 30%（原 {pct:.0f}%）")
            pct = 30.0
    if base >= 80 and cname_core == "高潮分化":
        if pct < 40:
            reasons.append(f"⚠️ 极端风控：温度 {base:.0f}≥80 且处高潮分化，仓位兜底 40%（原 {pct:.0f}%）")
            pct = 40.0

    band, color = "中性", "#f59e0b"
    for threshold, bname, bcolor in _BANDS:
        if pct >= threshold:
            band, color = bname, bcolor
            break

    return dict(pct=int(round(pct)), band=band, color=color, reasons=reasons)


def _cycle_name_of(forecast: dict | None) -> str:
    """从 forecast_next_day 的返回值里安全取周期名。"""
    if not isinstance(forecast, dict):
        return ""
    cyc = forecast.get("cycle")
    if isinstance(cyc, dict):
        return str(cyc.get("name") or "")
    return str(cyc or "")


def _event_position_adj(top_n: int = 50) -> dict | None:
    """用真实 P1 EV 事件因子多头池广度，映射成市场级仓位调节。

    返回 ``{"adj": int(0~5), "long_count": int}``；取不到真实信号（无目录 / 无文件 /
    异常 / 多头池空）返回 ``None`` —— 决策者绝不臆造事件催化。

    广度规则（透明、可解释）：
        事件驱动多头池每满 10 只高置信标的 → 仓位 +1pt，封顶 +5。
        多头池越宽 = 事件催化环境越旺 = 仓位越积极（与「事件驱动」主线一致）。
    """
    try:
        from modules.event_factor import event_driven_long_list
        longs = event_driven_long_list(top_n=top_n)
    except Exception as e:  # noqa: BLE001
        logger.warning("[decision] 事件因子多头池读取失败，跳过事件调节: %s", e)
        return None
    if not longs:
        return None
    n = len(longs)
    return {"adj": min(5, n // 10), "long_count": n}


def _age_days(date_str: str | None) -> int | None:
    """数据日期距今天的自然日数（仅用于「数据滞后」展示，不参与任何推导）。

    非交易日/周末跑出的快照 date 可能早于今天，这里如实反映滞后天数，
    让面板能显示「数据滞后 N 日」徽标——而不是直接假装是最新的。
    """
    if not date_str:
        return None
    try:
        from datetime import date as _d
        d = _d.fromisoformat(str(date_str)[:10])
        return (_d.today() - d).days
    except Exception:  # noqa: BLE001
        return None


# ───────────────────────── 快照构建 / 落盘 / 读取 ─────────────────────────
def build_snapshot(date: str, indicators: dict, temp, forecast: dict | None,
                   promo: dict | None, ladder: dict | None = None,
                   event_adj: int | None = None) -> dict:
    """把「今天的情绪信号 + 推导出的仓位建议」组装成一份可落盘的快照。

    :param date: 数据日期 YYYY-MM-DD（务必用**数据日期**而非 now()，否则周末/盘后
                 会记成非交易日，跨日晋级率递推直接算错 —— 这是踩过的坑）
    :param indicators: 牧羊人指标 dict
    :param temp: 市场温度
    :param forecast: shepherd_forecast.forecast_next_day 的返回
    :param promo: shepherd_ladder.ladder_promotion_rates 的返回
    :param ladder: get_zt_ladder 的原始返回（可选，存分布与最高板）
    :param event_adj: 事件驱动仓位调节(绝对百分点)；默认 None 时由真实事件因子
                      （P1 EV 多头池广度）自动计算。显式传值可覆盖/关闭(传 0)。
    """
    fc = forecast if isinstance(forecast, dict) else {}
    pm = promo if isinstance(promo, dict) else {}
    ld = ladder if isinstance(ladder, dict) else {}

    # 事件驱动催化：默认用真实事件因子多头池广度自动算；取不到则标记不可用（不臆造）
    ev = _event_position_adj() if event_adj is None else (
        {"adj": event_adj, "long_count": None} if event_adj else None)
    ev_info = {
        "available": bool(ev),
        "long_count": ev["long_count"] if ev else 0,
        "adj": ev["adj"] if ev else None,
    }
    if ev:
        event_adj = ev["adj"]

    cycle_name = _cycle_name_of(fc)
    overall = pm.get("overall")
    pos = derive_position(temp, fc.get("score"), fc.get("bias"), cycle_name, overall,
                          event_adj=event_adj)

    return {
        "date": date,
        "as_of": date,
        "data_age_days": _age_days(date),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "temperature": round(float(temp), 1) if temp is not None else None,
        "cycle": cycle_name,
        "score": fc.get("score"),
        "bias": fc.get("bias"),
        "confidence": fc.get("confidence"),
        "promo_overall": overall,
        "ladder": {
            "distribution": ld.get("distribution"),
            "max_boards": ld.get("max_boards"),
            "total_connect": ld.get("total_connect"),
        },
        "position": pos,
        "event_factor": ev_info,
        "indicators": dict(indicators or {}),
        "signals": fc.get("signals") or [],
        "scenario": fc.get("scenario") or [],
    }


def save_snapshot(snap: dict, archive_only: bool = False) -> bool:
    """落盘快照。同日期覆盖（幂等，一天跑多次只留最后一次）。失败返回 False 不抛。

    :param archive_only: True 时**只写历史归档** snapshots/<date>.json，不覆盖
                         data/daily_snapshot.json（历史回填专用：不能把补算的旧日期
                         顶掉「首页直读的最新快照」）。
    """
    if not isinstance(snap, dict) or not snap.get("date"):
        logger.warning("[decision] 快照缺 date，拒绝落盘")
        return False
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not archive_only:
            tmp = SNAPSHOT_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
            os.replace(tmp, SNAPSHOT_PATH)  # 原子替换，避免写一半被读到
            logger.info("[decision] 快照已落盘: %s (%s)", SNAPSHOT_PATH, snap["date"])
        # 历史归档（复盘回测的数据源）。归档失败不影响「最新快照可用」这一主目标。
        try:
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            apath = archive_path(snap["date"])
            atmp = apath + ".tmp"
            with open(atmp, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
            os.replace(atmp, apath)
        except Exception as e:  # noqa: BLE001
            logger.warning("[decision] 归档写入失败 %s: %s", snap["date"], e)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[decision] 快照落盘失败: %s", e)
        return False


def load_snapshot(date: str | None = None) -> dict | None:
    """读取快照。不传 date 返回当前落盘的那份（无论是否今天）。

    首页 banner 用它做到**零网络**：读本地 JSON，永不触发抓取。
    """
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[decision] 快照读取失败: %s", e)
        return None
    if not isinstance(snap, dict):
        return None
    if date and snap.get("date") != date:
        return None
    return snap


def append_log(line: str) -> None:
    """追加一行运行日志（便于 automation 跑完后肉眼核对有没有真的执行）。"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SNAPSHOT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {line}\n")
    except Exception:  # noqa: BLE001
        pass


def is_stale(max_age_hours: float = 20.0) -> bool:
    """快照是否过期（默认超过 20 小时没更新就算旧，覆盖不了一天一次收盘落盘的节奏）。"""
    try:
        mtime = os.path.getmtime(SNAPSHOT_PATH)
    except OSError:
        return True
    import time
    return (time.time() - mtime) > max_age_hours * 3600
