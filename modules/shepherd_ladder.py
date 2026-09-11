"""
modules/shepherd_ladder.py — 连板梯队晋级率（每日落盘 + 跨日晋级率递推）

牧羊人体系里「梯队厚度」只用家数（连板≥2板多少家），而**晋级率**比家数更精细：
  首板→二板晋级率 = 昨日首板今日有几成封住二板，是接力意愿最纯粹的度量。

本模块把每日各档连板家数落盘 data/shepherd_ladder_history.json，
再跨日递推各档晋级率，并把最新综合晋级率打包成 forecast 的派生指标
（ladder_promo），让「次日走势预判」能用上这一更细的接力信号。

设计原则：
  ✅ 纯函数与 IO 分离：ladder_promotion_rates / current_promo_as_indicators 吃文件出结果，可离线单测
  ✅ 文件损坏/缺失优雅降级，绝不抛异常到页面
  ✅ 历史不足 2 日时 ready=False，不误报晋级率
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta

from modules.atomic_io import atomic_json_dump
from modules.time_utils import now_cst, now_cst_str, now_cst_naive

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# SS_DATA_DIR 可重定向整个数据目录（测试隔离用；生产默认 data/）。
# conftest 在 pytest 启动时把它指到临时目录，避免测试写穿真实 data/。
LADDER_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
LADDER_FILE = os.path.join(LADDER_DIR, "shepherd_ladder_history.json")
_lock = threading.Lock()

# 晋级率进入「决策」所需的最小样本天数。
#
# 背景（2026-09-05 锐评发现）：ladder_promotion_rates() 只用「最近 2 天」快照算比率，
# 即 **1 个交易日对**；而 ready=True 仅代表"算得出来"，不代表"可信"。
# 实测曾出现 6 天样本、单日比率 8.6% 以 ready=True 身份经 current_promo_as_indicators()
# 注入 forecast 的 ladder_promo（weight=8）并驱动仓位建议——统计上属小样本过拟合。
#
# 对齐 modules/calibration.py 铁律 T3（n_call<8 不出观察行、<20 不 actionable），
# 取 10 作为「可驱动决策」门槛。未达标时 ladder_promotion_rates() **仍返回数值**供页面
# 展示（附 confidence="low"），只是不再进 forecast / 仓位推导。
MIN_PROMO_DAYS = 10


def _ensure_dir():
    try:
        os.makedirs(LADDER_DIR, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 建目录失败: {e}")


def _ds(v) -> str:
    """统一成 'YYYY-MM-DD'。"""
    try:
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        return str(v)[:10]
    except Exception:
        return str(v)[:10]


def trading_date(now=None) -> str:
    """推测「当前实时梯队该归属哪个交易日」：周六/周日回退到上周五。

    ⚠️ 为什么不能直接用 now()：
        get_zt_ladder() 抓的是**实时**梯队。周末跑脚本时它返回的是上周五收盘的数据，
        若按 now() 落盘就会记成周六/周日 → 跨日晋级率递推把非交易日当「昨日」，直接算错。

    ⚠️ 局限：只处理周末，**不处理法定节假日**（那需要交易日历）。
       节假日跑脚本仍会记一条，由 audit_history() 事后检出。
    """
    d = now or now_cst()
    if d.weekday() >= 5:  # 5=周六 6=周日
        d = d - timedelta(days=d.weekday() - 4)
    return d.strftime("%Y-%m-%d")


def _dist_to_map(distribution) -> dict:
    """distribution: [(boards, count), ...] -> {boards: count}。

    ⚠️ 锐评修复（R2）：原实现用两层 `except: pass` 把一切解析失败静默吞掉——
    distribution 结构异常时直接返回空 dict，而下游晋级率会在空数据上照常计算，
    结果是「静默算错且零报错」，正是本项目最危险的 bug 模式（与牧羊人二元组
    footgun 同源）。现改为：**容错仍在（绝不因脏数据崩溃），但每次丢弃或失败
    都 logger.warning 留痕**，让脏数据可被发现而不是无声消失。
    """
    out: dict = {}
    if not distribution:
        return out
    try:
        items = list(distribution)
    except Exception as e:  # noqa: BLE001
        logger.warning("[ladder] distribution 不可迭代，按空处理: %r (%s)", distribution, e)
        return out
    for idx, item in enumerate(items):
        try:
            b, c = item
            out[int(b)] = int(c)
        except Exception as e:  # noqa: BLE001
            logger.warning("[ladder] distribution 第 %d 项解析失败已丢弃: %r (%s)", idx, item, e)
    return out


def _int_keys(d) -> dict:
    """把 distribution 的档位 key 统一还原成 int。

    ⚠️ 坑：json.dump 会把 dict 的 int key 强制写成字符串（{"2": 25}），
    读回来 d.keys() 是 str，直接 `n - 1` / `max(keys)` 会炸或算错。
    所以每次从文件读都要过一遍这里，保证消费方拿到的永远是 int key。
    """
    out = {}
    try:
        for k, v in (d or {}).items():
            try:
                out[int(k)] = int(v)
            except Exception:
                continue
    except Exception:
        return {}
    return out


def load_history() -> dict:
    """{date: {date, distribution, max_boards, total_connect, updated_at}}。缺失/损坏返回 {}。

    返回的每条 distribution 已归一化成 {int 档位: int 家数}。
    """
    try:
        if not os.path.exists(LADDER_FILE):
            return {}
        with open(LADDER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        for _d, entry in data.items():
            if isinstance(entry, dict) and "distribution" in entry:
                entry["distribution"] = _int_keys(entry["distribution"])
        return data
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 读取历史失败: {e}")
        return {}


def _save_history(hist: dict) -> bool:
    try:
        _ensure_dir()
        atomic_json_dump(hist, LADDER_FILE)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_ladder] 保存历史失败: {e}")
        return False


def record_ladder_snapshot(date, distribution, max_boards=None, total_connect=None) -> bool:
    """落盘某日连板梯队快照（按日期覆盖更新）。

    无有效分布时不记录（避免污染历史）。
    """
    d = _ds(date)
    if not d:
        return False
    dist = _dist_to_map(distribution)
    if not dist:
        return False
    with _lock:
        hist = load_history()
        hist[d] = {
            "date": d,
            "distribution": dist,
            "max_boards": int(max_boards) if max_boards is not None else max(dist.keys()),
            "total_connect": int(total_connect) if total_connect is not None
            else sum(v for k, v in dist.items() if k >= 2),
            "updated_at": now_cst_naive().isoformat(timespec="seconds"),
        }
        return _save_history(hist)


def _promo_confidence(days: int) -> str:
    """样本天数 → 可信度档位（仅用于展示，不驱动决策）。"""
    if days >= 20:
        return "high"
    if days >= MIN_PROMO_DAYS:
        return "medium"
    if days >= 2:
        return "low"
    return "none"


def _promo_actionable(days: int, overall) -> bool:
    """晋级率是否可信到能驱动决策（对齐 calibration 铁律 T3：小样本不表态）。

    注意：晋级率只用最近 2 天算，days 是「已积累的快照天数」而非比率样本数；
    用 days 兜底是因为单日比率噪声极大，必须靠积累天数证明序列稳定。
    """
    return days >= MIN_PROMO_DAYS and overall is not None


def ladder_promotion_rates(as_of: str | None = None) -> dict:
    """算各档晋级率（跨日递推）。

    晋级率定义：某档 n（≥2板）的晋级率 = 当日 n板家数 / 昨日 (n-1)板家数。
      · 2板晋级率 = 当日2板家数 / 昨日首板家数（最能代表接力意愿）
      · 3板晋级率 = 当日3板 / 昨日2板，以此类推
    仅当存在「今日」与「昨日」两条快照时才有意义。

    :param as_of: 可选时点截止日（YYYY-MM-DD）。传入后只用 ≤ as_of 的历史快照递推
                  （历史回填的时点诚实口径：不偷看未来数据）；None = 最新（现行为）。

    返回：
      ready       bool（有任一档晋级率可算才有意义）
      days        int（历史天数）
      latest      dict（最新快照）
      latest_date str
      rates       {tier_label: rate_or_None}，tier_label 形如 "2b"(首板→二板) / "3b" / …
      overall     float|None（综合晋级率：优先取首板→二板，缺失则取可用档均值）
    """
    empty = dict(ready=False, days=0, latest=None, latest_date=None, rates={}, overall=None,
                 actionable=False, confidence="none")
    hist = load_history()
    if not hist:
        return empty
    # 跳过被标记为不可信的条目（audit_history 检出 + mark_suspect 标记，软处理可撤销）
    dates = sorted(d for d, e in hist.items()
                   if not (isinstance(e, dict) and e.get("suspect")))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if not dates:
        return empty
    if len(dates) < 2:
        return dict(ready=False, days=len(dates), latest=hist[dates[-1]],
                    latest_date=dates[-1], rates={}, overall=None,
                    actionable=False, confidence=_promo_confidence(len(dates)))
    latest = hist[dates[-1]]
    yest = hist[dates[-2]]
    d_cur = _int_keys(latest.get("distribution"))
    d_prev = _int_keys(yest.get("distribution"))
    max_tier = int(max(d_cur.keys())) if d_cur else 0
    rates = {}
    for n in range(2, max_tier + 1):
        prev_cnt = d_prev.get(n - 1)
        cur_cnt = d_cur.get(n)
        if prev_cnt is None or prev_cnt <= 0:
            rates[f"{n}b"] = None
        else:
            rates[f"{n}b"] = round(cur_cnt / prev_cnt * 100, 1) if cur_cnt is not None else None
    overall = rates.get("2b")
    if overall is None:
        avail = [v for v in rates.values() if v is not None]
        overall = round(sum(avail) / len(avail), 1) if avail else None
    return dict(ready=any(v is not None for v in rates.values()),
                days=len(dates), latest=latest, latest_date=dates[-1],
                rates=rates, overall=overall,
                actionable=_promo_actionable(len(dates), overall),
                confidence=_promo_confidence(len(dates)))


def current_promo_as_indicators() -> dict:
    """把最新综合晋级率打包成 forecast 派生指标 {ladder_promo: rate}。

    样本不足 MIN_PROMO_DAYS 天时返回 {}：晋级率只用最近 2 天算，样本太少时
    单日噪声会被当成趋势喂进 forecast（ladder_promo weight=8）并驱动仓位，
    属小样本过拟合。未达标时 ladder_promotion_rates() 仍返回数值供页面展示
    （confidence="low"），只是不进决策链路。
    """
    pr = ladder_promotion_rates()
    if not pr.get("actionable") or pr.get("overall") is None:
        return {}
    return {"ladder_promo": pr["overall"]}


def prev_overall(as_of: str | None = None) -> float | None:
    """倒数第二天的综合晋级率（用于首页/决策面板的环比 delta）。

    口径与 ladder_promotion_rates() 一致：取「最新-1 日 vs 最新-2 日」的 2板晋级率。
    :param as_of: 可选时点截止日——传入后只用 ≤ as_of 的历史（回填时点诚实口径）。
    历史不足 3 日返回 None（无法算环比）。
    """
    hist = load_history()
    dates = sorted(d for d, e in hist.items() if not (isinstance(e, dict) and e.get("suspect")))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if len(dates) < 3:
        return None
    d_cur = _int_keys(hist[dates[-2]].get("distribution"))
    d_prev = _int_keys(hist[dates[-3]].get("distribution"))
    prev_cnt = d_prev.get(1)
    cur_cnt = d_cur.get(2)
    if not prev_cnt or prev_cnt <= 0:
        return None
    return round(cur_cnt / prev_cnt * 100, 1) if cur_cnt is not None else None


# ────────────────── 历史数据体检：脏数据检测 + 软标记 ──────────────────
def audit_history() -> dict:
    """体检梯队历史，检出「不可信」条目。**只读，不改动任何数据。**

    两条判据：

    · **补记滞后（主判据，可靠）**：`updated_at` 的日期 ≠ 该条的 `date`。
      说明这条不是当天写的 —— 而 distribution 来自**实时抓取**，于是「那一天」名下
      记的其实是「补记那一刻」的梯队，日期张冠李戴。
      典型场景：8-30 打开情绪页，牧羊人数据还停在 8-27，页面就把 8-30 抓到的实时
      梯队记到了 8-27 名下（根因已在页面侧改用 trading_date() 修正）。

    · **重复分布（辅助，仅提示）**：与相邻日期的分布逐档完全相同。
      真实市场两天梯队完全一致的概率极低，通常意味着其中一条是陈旧/复制值。

    :return: {date: {date, severity, reason, detail, updated_at, distribution}}
             severity: "bad"（补记滞后，强烈建议排除）/ "warn"（仅提示）
    """
    hist = load_history()
    if not hist:
        return {}
    dates = sorted(hist.keys())
    out: dict = {}

    # 主判据：补记滞后
    for d in dates:
        entry = hist[d]
        if not isinstance(entry, dict):
            continue
        upd = str(entry.get("updated_at") or "")[:10]
        if upd and upd != d:
            out[d] = {
                "date": d, "severity": "bad", "reason": "补记滞后",
                "detail": (f"updated_at={entry.get('updated_at')} 与 date={d} 不符；"
                           f"分布来自实时抓取，实为补记当日的梯队"),
                "updated_at": entry.get("updated_at"),
                "distribution": entry.get("distribution"),
                "marked": bool(entry.get("suspect")),
            }

    # 辅助判据：与相邻日期分布完全相同
    for i, d in enumerate(dates):
        entry = hist[d]
        if not isinstance(entry, dict) or d in out:
            continue
        cur = _int_keys(entry.get("distribution") or {})
        if not cur:
            continue
        neighbours = [dates[i - 1] if i > 0 else None,
                      dates[i + 1] if i + 1 < len(dates) else None]
        for nb in neighbours:
            if not nb:
                continue
            other = hist.get(nb)
            if not isinstance(other, dict):
                continue
            if _int_keys(other.get("distribution") or {}) == cur:
                out[d] = {
                    "date": d, "severity": "warn", "reason": "分布与相邻日完全相同",
                    "detail": f"与 {nb} 的分布逐档一致 {cur}，疑似陈旧/复制值",
                    "updated_at": entry.get("updated_at"),
                    "distribution": cur,
                    "marked": bool(entry.get("suspect")),
                }
                break
    return out


def mark_suspect(dates, reason="人工标记") -> int:
    """给指定日期打 suspect 标记 —— **软处理，数据不删，随时可 unmark 撤销**。

    被标记的条目会被 ladder_promotion_rates() 跳过，不再污染晋级率。

    :param dates: 单个日期字符串或日期列表
    :return: 实际标记成功的条数
    """
    if isinstance(dates, str):
        dates = [dates]
    n = 0
    with _lock:
        hist = load_history()
        for d in dates:
            d = _ds(d)
            e = hist.get(d)
            if not isinstance(e, dict):
                continue
            e["suspect"] = True
            e["suspect_reason"] = reason
            e["suspect_at"] = now_cst_naive().isoformat(timespec="seconds")
            n += 1
        if n:
            _save_history(hist)
    return n


def unmark_suspect(dates) -> int:
    """撤销 suspect 标记，恢复参与晋级率计算（数据从未被删除，可完整恢复）。"""
    if isinstance(dates, str):
        dates = [dates]
    n = 0
    with _lock:
        hist = load_history()
        for d in dates:
            d = _ds(d)
            e = hist.get(d)
            if not isinstance(e, dict):
                continue
            for k in ("suspect", "suspect_reason", "suspect_at"):
                e.pop(k, None)
            n += 1
        if n:
            _save_history(hist)
    return n


# ────────────────── F4：连板龙头强度 + 事件×广度共振 ──────────────────
# 设计红线（诚实性）：
#   · 梯队历史只有逐日「家数分布」({boards:count})，**没有逐股名称/代码**，
#     因此「龙头」只能是**市场级**的连板高度/强度刻画，绝不冒充个股名单。
#   · 历史样本极短（生产环境仅 ~8 个交易日，含 1 条 suspect），任何「概率」
#     都只是即时观测值，必须明确标注「非稳定历史概率、小样本」。
#   · 事件源为本地 event_pool_brief.json（P1-QuantFactor EV 因子多头池），
#     属离线快照，须展示数据日期并提示时效性，不臆造实时事件。
#   · 全部函数纯函数 + 薄 IO，as_of 截断保证无前视泄漏，可离线单测。

def _clamp(x, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def _height_subscore(max_boards: int) -> float:
    """连板高度子分（0-100）：分段饱和映射，越高代表市场最高板越高。

    · <2 板：0（无连板梯队）
    · 2 板：20  3 板：35  4 板：50  5 板：65  6 板：80  7 板及以上：100
    """
    table = {0: 0, 1: 0, 2: 20, 3: 35, 4: 50, 5: 65, 6: 80}
    try:
        mb = int(max_boards)
    except Exception:
        return 0.0
    if mb <= 1:
        return 0.0
    if mb >= 7:
        return 100.0
    return float(table.get(mb, 0))


def _density_subscore(dist: dict) -> float:
    """高位集中度子分（0-100）：连板≥4板的家数 / 总连板家数。

    比值越高，说明资金抱团在高位龙头而非散在首板，接力结构更健康。
    总连板家数为 0 时返回 0。
    """
    try:
        d = _int_keys(dist)
    except Exception:
        return 0.0
    total = sum(v for k, v in d.items() if k >= 2)
    if total <= 0:
        return 0.0
    high = sum(v for k, v in d.items() if k >= 4)
    return _clamp(high / total * 100.0)


def leader_strength_index(as_of: str | None = None) -> dict:
    """市场级连板龙头强度指数（0-100），基于最新梯队分布刻画。

    ⚠️ 这是**市场级**强度（高度+高位集中度+接力意愿），不是个股名单。
       离线无逐股缓存，本函数不返回也不暗示任何具体个股。

    :param as_of: 截止日（YYYY-MM-DD）；传入只用 ≤ as_of 的快照（回填诚实口径）。
    返回：
      available   bool
      date        str（实际采用的最新快照日，≤ as_of）
      score       0-100（0.40*高度 + 0.35*高位集中度 + 0.25*2板晋级率）
      components  {height, density, promo}
      max_boards / total_connect / distribution / promo_rate
      note        诚实性声明
    """
    empty = dict(available=False, date=None, score=None, components={},
                 max_boards=None, total_connect=None, distribution={},
                 promo_rate=None, note="梯队历史为空或不可用")
    hist = load_history()
    if not hist:
        return empty
    dates = sorted(d for d, e in hist.items()
                   if isinstance(e, dict) and not e.get("suspect") and e.get("distribution"))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    if not dates:
        return empty
    entry = hist[dates[-1]]
    dist = _int_keys(entry.get("distribution") or {})
    max_boards = int(entry.get("max_boards") or (max(dist.keys()) if dist else 0))
    total_connect = int(entry.get("total_connect") if entry.get("total_connect") is not None
                        else sum(v for k, v in dist.items() if k >= 2))

    height = _height_subscore(max_boards)
    density = _density_subscore(dist)
    pr = ladder_promotion_rates(as_of=as_of)
    promo = _clamp(pr.get("overall") or 0.0)  # 2板晋级率(%)，上限 100

    score = _clamp(0.40 * height + 0.35 * density + 0.25 * promo)
    return dict(
        available=True,
        date=dates[-1],
        score=round(score, 1),
        components=dict(height=round(height, 1), density=round(density, 1), promo=round(promo, 1)),
        max_boards=max_boards,
        total_connect=total_connect,
        distribution=dist,
        promo_rate=pr.get("overall"),
        note=("市场级连板强度（高度+高位集中度+接力意愿），非个股名单；离线无逐股缓存。"
              if pr.get("overall") is None
              else "市场级连板强度（高度+高位集中度+接力意愿），非个股名单；晋级率由最近2日推算，小样本。"),
    )


def historical_promo_rate(as_of: str | None = None, min_pairs: int = 2) -> dict:
    """跨全部可用日对的历史平均 2板晋级率（比单日对更稳，但仍是小样本）。

    :param as_of: 截止日；只用 ≤ as_of 的日对（无前视泄漏）。
    :param min_pairs: 至少需多少个日对才视为 available。
    返回：{available, rate(%), n_pairs, note}
    """
    hist = load_history()
    dates = sorted(d for d, e in hist.items()
                   if isinstance(e, dict) and not e.get("suspect") and e.get("distribution"))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    rates = []
    for i in range(1, len(dates)):
        prev = _int_keys(hist[dates[i - 1]].get("distribution") or {})
        cur = _int_keys(hist[dates[i]].get("distribution") or {})
        p1 = prev.get(1)
        c2 = cur.get(2)
        if p1 and p1 > 0 and c2 is not None:
            rates.append(c2 / p1 * 100.0)
    if len(rates) < min_pairs:
        return dict(available=False, rate=None, n_pairs=len(rates),
                    note=f"可用日对仅 {len(rates)} 个（需≥{min_pairs}），样本过小不报告概率")
    avg = sum(rates) / len(rates)
    return dict(available=True, rate=round(avg, 1), n_pairs=len(rates),
                note=f"基于 {len(rates)} 个历史日对的平均 2板晋级率；样本仍偏小，仅供参考")


def next_day_promotion_probability(as_of: str | None = None) -> dict:
    """次日晋级概率概览（诚实标注：即时观测，非稳定历史概率）。

    由三部分构成：
      live_rate      最近一对快照的 2板晋级率（即时观测）
      hist_rate      跨全部日对的历史平均（稍稳，仍小样本）
      height_trend   最新 max_boards vs 近 5 日均值 → 高度扩张/持平/退潮
    返回：{available, live_rate, hist_rate, n_pairs, height_trend, max_boards, note}
    """
    pr = ladder_promotion_rates(as_of=as_of)
    hr = historical_promo_rate(as_of=as_of)
    hist = load_history()
    dates = sorted(d for d, e in hist.items()
                   if isinstance(e, dict) and not e.get("suspect") and e.get("distribution"))
    if as_of:
        dates = [d for d in dates if d <= as_of]
    max_boards = pr.get("latest", {}).get("max_boards") if pr.get("latest") else None
    height_trend = "无数据"
    if len(dates) >= 2 and max_boards is not None:
        recent = []
        for d in dates[-5:]:
            e = hist[d]
            mb = e.get("max_boards")
            if mb is None:
                mb = max((_int_keys(e.get("distribution") or {})).keys(), default=0)
            recent.append(int(mb))
        avg5 = sum(recent) / len(recent)
        if max_boards >= avg5 + 0.5:
            height_trend = "高度扩张"
        elif max_boards <= avg5 - 0.5:
            height_trend = "高度退潮"
        else:
            height_trend = "高度持平"
    return dict(
        available=pr.get("ready", False),
        live_rate=pr.get("overall"),
        hist_rate=hr.get("rate"),
        n_pairs=hr.get("n_pairs", 0),
        height_trend=height_trend,
        max_boards=max_boards,
        note="晋级率由最近2日推算、历史平均为小样本估计；高度趋势取近5日均值。历史相似 ≠ 预测，本读数仅描述接力意愿现状。",
    )


def event_breadth_resonance(regime_state: str, leader_score: float | None,
                            red_ratio: float | None = None) -> dict:
    """连板强度 × 市场状态 共振判定（纯函数，可单测）。

    :param regime_state: market_regime.STATE_ORDER 中的一档
    :param leader_score: leader_strength_index().score（0-100，None=未知）
    :param red_ratio: 红盘率(%)，仅用于文案补充
    返回：{resonance, label, color, detail, support}  support∈{bullish,neutral,bearish,none}
    """
    if not regime_state:
        return dict(resonance="无信号", label="状态未知", color="#94a3b8",
                    detail="市场状态缺失，无法判定共振。", support="none")
    band = "high" if (leader_score is not None and leader_score >= 60) else \
        ("mid" if (leader_score is not None and leader_score >= 30) else "low")
    # (regime, band) -> (label, color, support, detail)
    MATRIX = {
        ("结构牛", "high"): ("共振向上", "#16a34a", "bullish", "广度强 + 接力意愿强，龙头与趋势共振，容错率高。"),
        ("结构牛", "mid"):  ("广度强·接力中性", "#22c55e", "bullish", "趋势结构健康，但连板接力一般，注意内部轮动。"),
        ("结构牛", "low"):  ("广度强但接力弱", "#f59e0b", "neutral", "指数/板块强但连板断层，警惕高位分化、题材散乱。"),
        ("普涨",   "high"): ("共振向上", "#16a34a", "bullish", "普涨 + 高位抱团，赚钱效应与接力共振。"),
        ("普涨",   "mid"):  ("普涨·接力中性", "#22c55e", "bullish", "多数个股上涨，连板结构中性，可积极参与。"),
        ("普涨",   "low"):  ("普涨但无主线", "#f59e0b", "neutral", "指数普涨却无连板主线，行情偏补涨、持续性待验。"),
        ("震荡",   "high"): ("龙头抱团·看量能", "#f59e0b", "neutral", "震荡市中资金抱团高位龙头，成败看量能是否跟上。"),
        ("震荡",   "mid"):  ("弱平衡·观望", "#94a3b8", "neutral", "广度与接力均中性，方向不明，控仓等待。"),
        ("震荡",   "low"):  ("无共振·清淡", "#94a3b8", "neutral", "连板与广度双弱，市场清淡，多看少动。"),
        ("恐慌",   "high"): ("退潮风险·高位松动", "#dc2626", "bearish", "弱势中高位龙头易补跌，抱团松动信号，避险为上。"),
        ("恐慌",   "mid"):  ("弱势反弹·谨慎", "#f97316", "bearish", "恐慌未消，连板一般，反弹宜降仓快进快出。"),
        ("恐慌",   "low"):  ("全面退潮", "#dc2626", "bearish", "广度与连板双弱，空仓或极低仓避险。"),
        ("暴跌",   "high"): ("退潮风险·高位松动", "#dc2626", "bearish", "暴跌中高位抱团最危险，优先排雷而非追高。"),
        ("暴跌",   "mid"):  ("弱势反弹·谨慎", "#f97316", "bearish", "暴跌后技术性反抽，连板弱，不宜重仓。"),
        ("暴跌",   "low"):  ("全面退潮", "#dc2626", "bearish", "广度与连板双杀，空仓或极低仓避险。"),
    }
    key = (regime_state, band)
    if key not in MATRIX:
        # leader_score 未知（None）时 band 恒为 low，落入 (regime,low) 分支；
        # 若连 (regime,low) 都不在（未知市场状态），安全地降级而非抛 KeyError。
        key = (regime_state, "low")
    if key not in MATRIX:
        return dict(resonance="无信号", label="状态未知", color="#94a3b8",
                    detail=f"未识别的市场状态「{regime_state}」，无法判定共振。", support="none")
    label, color, support, detail = MATRIX[key]
    if red_ratio is not None:
        detail += f" 当前红盘率 {red_ratio:.0f}%。"
    return dict(resonance=label, label=label, color=color, support=support, detail=detail)


def load_event_pool(path: str | None = None) -> dict:
    """读本地事件因子多头池快照（P1-QuantFactor EV 因子）。

    离线快照，须展示数据日期与时效性，不臆造实时事件。缺失/损坏优雅降级。
    返回：{available, date, pool(list), stale(bool), note, source}
    """
    p = path or os.path.join(LADDER_DIR, "event_pool_brief.json")
    try:
        if not os.path.exists(p):
            return dict(available=False, date=None, pool=[], stale=False,
                        note="事件因子多头池快照缺失（data/event_pool_brief.json）", source=None)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not data.get("pool"):
            return dict(available=False, date=None, pool=[], stale=False,
                        note="事件因子多头池快照为空或结构异常", source=None)
        pool = data.get("pool", [])
        date_str = str(data.get("date") or "")[:10]
        stale = False
        try:
            from datetime import datetime as _dt
            if date_str:
                d0 = _dt.strptime(date_str, "%Y-%m-%d").date()
                age = (now_cst().date() - d0).days
                stale = age > 7
        except Exception:
            pass
        return dict(available=True, date=date_str, pool=pool, stale=stale,
                    note=("事件因子多头池为离线快照，数据日期 "
                          + (date_str or "未知")
                          + ("（已超过7天，时效性存疑）" if stale else "")
                          + "；仅代表统计超额收益概率排序，非买卖指令。"),
                    source=data.get("source"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ladder] 读取事件池失败: {e}")
        return dict(available=False, date=None, pool=[], stale=False,
                    note=f"读取事件池失败：{e}", source=None)
