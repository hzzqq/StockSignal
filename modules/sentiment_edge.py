"""modules/sentiment_edge.py — 情绪「有统计依据的极值信号」层（无未来信息校准）

为什么需要这一层
================
老板反馈「项目还是没做到准确预测情绪」。用 ``scripts/analyze_sentiment_predictive_power.py``
把 2009–2026 的 4094 个交易日逐日喂给 ``forecast_next_day`` 实测后，结论是**残酷但清楚**的：

  ┌ 方向不可预测（全部噪音）
  │   · 偏多 n=296 次日上涨 48.3%（基准 46.5%）z=+0.61
  │   · 偏空 n=128 次日上涨 53.9%（基准 46.5%）z=+1.67
  │   · 5 日尺度：偏多 38.6% vs 基准 38.6%，z=+0.03
  │   · 0–100「次日情绪评分」与次日收益 IC = **-0.031**（负相关），十分位单调性 IC≈0.02
  ├ 手工规律大多无法验证
  │   · 注：limit_down/up_down/flat 已于 P1/P2 用 v1 缓存**全历史还原为真实值**，
  │     故「跌停>100家」在新基座上能触发（约 130 天 / 次日上涨 66.9% / z=+3.90，见实证报告）。
  │     但生产层**仍只用尺度无关的占比类特征**，原因不在「家数被低估」，而在
  │     **逐年长大的采样**（2009 年 26 只 → 2025 年 1669 只）：绝对阈值在早期小宇宙
  │     时代天然偏小、跨年代不可比，而占比类特征跨年代一致。
  └ 唯一的真信号：**极端恐慌 → 次日反弹**
      · walk-forward（第 i 天阈值只用第 i 天之前的数据）验证（2026-09-11 P3 修正，
        目标由缺失历史的 median_chg 改为全历史可比的「次日红盘日」= 次日上涨家数>下跌家数）：
          跌停占比前10%    触发 296 天 → 次日红盘 62.5%（基准 49.8%）z=+4.36 ✅ 可发布
          触及跌停占比前10% → 因 touch_down 全历史缺失（仅近窗 14 天有值），
                               触发 0 天，**不可验证、不发布**（待历史补齐后再评估）
      · 2015 年股灾、2018 年 2 月、2020 年新冠等极端日均落在触发集内，逐年稳定为正

本模块的设计原则
================
1. **只说有依据的话**：只在历史极值分位（恐慌出清）触发时表态，并附样本量 / 基准率 / z 值；
2. **其余时候明确弃权**：返回 ``abstain=True`` 与「方向不可预测」的说明，而不是硬猜一个偏多偏空；
3. **只用尺度无关特征**：占比类（跌停家数 / 当日有效样本数），避免家数阈值与采样规模错配；
4. **无未来信息**：阈值来自 walk-forward 校准件 ``data/sentiment_edge_calibration.json``，
   由 ``scripts/calibrate_sentiment_edge.py`` 生成，可随时重跑复核；
5. **纯函数 + 优雅降级**：校准件缺失/字段缺失时返回 ``available=False``，绝不抛异常。

明确的能力边界（写进产品文案，不藏）
------------------------------------
    ✅ 可信：极端恐慌（跌停占比前 10%）→ 次日红盘概率显著高于基准（约 +13pp，全历史 296 天 z=+4.36）
    ✅ 弱可信：次日「波动幅度」与当日占比类指标弱正相关（IC≈0.13~0.16）→ 只能做风险提示
    ❌ 不可信：普通日子里次日涨跌方向（现有引擎输出经检验无法超越基准率）
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# 校准件解析顺序（2026-09-10 加回退）：
#   ① 环境变量 SS_SENTIMENT_EDGE_PATH（测试/临时覆盖）
#   ② data/  —— 本地运行时目录，**被 .gitignore 忽略**
#   ③ reports/ —— 随仓库发布，保证换机器/新克隆也有这层能力
# 只放 data/ 的后果：另一台机器上这层会「静默消失」（页面连提示都没有），
# 故校准脚本同时写两处，读取端按序回退。
CANDIDATE_PATHS = [
    os.path.join(_ROOT, "data", "sentiment_edge_calibration.json"),
    os.path.join(_ROOT, "reports", "sentiment_edge_calibration.json"),
]
# ⚠️ 不要再写 `DEFAULT_PATH = CANDIDATE_PATHS[0]` 这种静态副本：
#    改候选表时会漂移（2026-09-10 被自己的单测抓到 —— 替换 CANDIDATE_PATHS 后
#    函数仍返回旧的静态路径，于是「两个候选都不存在」的降级用例被静默绕过）。
#    统一走 calibration_path() 动态取，DEFAULT_PATH 仅作向后兼容别名。
ENV_PATH = "SS_SENTIMENT_EDGE_PATH"

_cache: dict = {"path": None, "mtime": None, "data": None}


def calibration_path() -> str:
    """返回实际生效的校准件路径：环境变量 > 首个存在的候选 > 首个候选（用于报错提示）。"""
    env = os.environ.get(ENV_PATH)
    if env:
        return env
    for p in CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    return CANDIDATE_PATHS[0]


def load_calibration() -> dict:
    """加载校准件（按 mtime 缓存）。缺失或损坏时返回 {'available': False, ...}。"""
    path = calibration_path()
    if not os.path.exists(path):
        return {"available": False,
                "reason": f"校准件不存在：{path}；请先运行 scripts/calibrate_sentiment_edge.py"}
    try:
        mtime = os.path.getmtime(path)
        if _cache["data"] is not None and _cache["path"] == path and _cache["mtime"] == mtime:
            return _cache["data"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "features" not in data:
            return {"available": False, "reason": "校准件结构异常（缺 features 字段）"}
        data["available"] = True
        _cache.update(path=path, mtime=mtime, data=data)
        return data
    except Exception as exc:  # 校准件损坏不得让页面崩掉
        logger.warning("[sentiment_edge] 校准件读取失败: %s", exc)
        return {"available": False, "reason": f"校准件读取失败：{exc}"}


def _num(d: dict, key: str):
    """安全取数值：非数值/缺失返回 None（不用 0 冒充，避免把缺失当极值）。"""
    if not d:
        return None
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def day_sample(today: dict):
    """当日有效样本数 = 上涨 + 下跌 + 平盘家数（分母，用于把家数换算成占比）。"""
    parts = [_num(today, k) for k in ("up_count", "down_count", "flat_count")]
    got = [p for p in parts if p is not None]
    if not got:
        return None
    s = sum(got)
    return s if s > 0 else None


def ratios(today: dict, sample=None) -> dict:
    """把家数类指标换算为**尺度无关**的占比（%）。分母缺失则对应项为 None。"""
    s = sample if sample is not None else day_sample(today)
    out: dict = {}
    if not s:
        return out
    for key, col in (("limit_down_ratio", "limit_down"),
                     ("touch_down_ratio", "touch_down"),
                     ("limit_up_ratio", "limit_up"),
                     ("hb_wave_ratio", "hb_wave10")):
        v = _num(today, col)
        if v is not None:
            out[key] = round(v / s * 100, 4)
    return out


def panic_reversal(today: dict, sample=None) -> dict:
    """极端恐慌反弹信号：恐慌出清（跌停/触及跌停占比达历史前 10%）→ 次日上涨概率显著抬升。

    Returns:
        dict:
          available       校准件是否可用
          evaluated       是否真的「看过了」（False = 关键指标缺失 → 无法判定；
                          与 evaluated=True 且未触发 的「看了、没到极值」严格区分）
          triggered       是否触发（达到历史极值分位）
          hits            命中的特征列表 [{key,name,value,threshold,prob,n,z}]
          prob            触发时的次日上涨概率（walk-forward 实测）
          base_rate       无条件基准率（同期）
          edge_pp         相对基准的边际（百分点）
          strength_hint   波动提示（弱信号，仅风险提示）
          statement       可直接展示给用户的一句话
          abstain         是否弃权（未触发 → 无统计边际，不表态）
    """
    cal = load_calibration()
    if not cal.get("available"):
        return dict(available=False, triggered=False, evaluated=False, hits=[], prob=None,
                    base_rate=None, edge_pp=None, strength_hint=None, abstain=True,
                    statement="情绪极值信号校准件不可用，本次不做方向表态。",
                    reason=cal.get("reason", ""))

    base = cal.get("base_next_day_up_rate")
    r = ratios(today, sample)
    hits = []
    # 拿到了值、够格参与判定的特征。用于区分「看过了、没到极值」与「根本没法看」
    # —— 后者是「不知道」，绝不能报成「未进入极值区间」。
    evaluable = []
    for key, cfg in (cal.get("features") or {}).items():
        if not cfg.get("publishable"):
            continue
        v = r.get(key)
        thr = cfg.get("production_threshold")
        if v is None or thr is None:
            continue
        evaluable.append(key)
        if v >= float(thr):
            wf = cfg.get("walk_forward") or {}
            hits.append(dict(key=key, name=cfg.get("name", key), value=v,
                             threshold=float(thr), prob=wf.get("up_rate"),
                             n=wf.get("trigger_days"), z=wf.get("z"),
                             why=cfg.get("why", "")))

    strength = None
    sic = (cal.get("strength_ic") or {}).get("touch_down_ratio")
    td = r.get("touch_down_ratio")
    if sic is not None and td is not None and td > 0:
        # 仅作「次日波动偏大」的风险提示：IC≈0.13~0.16 是弱信号，不作方向依据
        strength = dict(ic=sic, value=td,
                        hint="次日波动可能偏大（弱信号 IC≈%.2f，仅风险提示）" % sic)

    if not hits:
        if not evaluable:
            # 一个可判定特征都没拿到 —— 这是「不知道」，而不是「没到极值」
            return dict(available=True, triggered=False, evaluated=False,
                        hits=[], prob=None, base_rate=base, edge_pp=None,
                        strength_hint=strength, abstain=True,
                        statement=("当日关键情绪指标缺失（跌停 / 触及跌停家数，或涨跌家数不全），"
                                   "**本次无法判定**是否处于历史极值区间，故不做任何方向表态。"),
                        ratios=r)
        return dict(available=True, triggered=False, evaluated=True, hits=[], prob=None,
                    base_rate=base, edge_pp=None, strength_hint=strength, abstain=True,
                        statement=("当日情绪未进入历史极值区间：**次日方向无统计边际，本模块不表态**"
                                   "（现有情绪评分与次日收益 IC≈0，经全历史检验无法超越基准率）。"),
                    ratios=r)

    prob = sum(h["prob"] for h in hits) / len(hits)
    edge = round((prob - base) * 100, 1) if (prob is not None and base is not None) else None
    names = "、".join(h["name"] for h in hits)
    return dict(
        available=True, triggered=True, evaluated=True, hits=hits, prob=round(prob, 4),
        base_rate=base, edge_pp=edge, strength_hint=strength, abstain=False,
        statement=(f"⚠️ **恐慌出清反弹信号触发**（{names} 达历史前 10% 分位）："
                   f"历史上该形态次日上涨概率 {prob:.1%}，基准 {base:.1%}，"
                   f"边际 +{edge}pp（样本 {hits[0]['n']} 天，z={hits[0]['z']}）。"
                   f"注意：这是**统计概率**，不是确定性预测。"),
        ratios=r,
    )


def calibration_summary() -> dict:
    """校准件摘要（供页面/报告展示证据链）。"""
    cal = load_calibration()
    if not cal.get("available"):
        return dict(available=False, reason=cal.get("reason", ""))
    return dict(
        available=True,
        generated_at=cal.get("generated_at"),
        method=cal.get("method"),
        base_next_day_up_rate=cal.get("base_next_day_up_rate"),
        date_range=cal.get("date_range"),
        universe_note=cal.get("universe_note"),
        strength_ic=cal.get("strength_ic"),
        strength_note=cal.get("strength_note"),
        features={k: dict(name=v.get("name"), threshold=v.get("production_threshold"),
                          walk_forward=v.get("walk_forward"), by_year=v.get("by_year"),
                          why=v.get("why"), publishable=v.get("publishable"))
                  for k, v in (cal.get("features") or {}).items()},
    )
