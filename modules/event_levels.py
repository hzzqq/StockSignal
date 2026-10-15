"""modules/event_levels.py — 事件强度五档标准（单一真理源，T-287）。

全站「事件分析」类判定（SentimentAnalyzer 情感分析、event_graph 事件传导图谱）
共享同一套五档标签与聚合权重，**改档位/阈值/配色只改这里**：

    大利好(+2) / 小利好(+1) / 中性(0) / 小利空(-1) / 大利空(-2)

口径：
- event_graph：标题情绪词净命中多数决方向，一线强词或净命中 ≥2 记「大」；
- SentimentAnalyzer：score 绝对值落带 —— |score| ≥ 0.4 记「大」（即既有 is_major 线）、
  0.15 < |score| < 0.4 记「小」（0.15 为既有三档判定线），无新魔法数；
- 多条标题/事件聚合按权重加总，±2 截断（``strength_label``）。

A 股语义：利好=红、利空=绿、中性=灰（与全站一致，不要反着写）。
"""

from __future__ import annotations

__all__ = [
    "NEUTRAL", "BULLISH", "BEARISH",
    "BIG_BULLISH", "SMALL_BULLISH", "SMALL_BEARISH", "BIG_BEARISH",
    "STRENGTH_ORDER", "STRENGTH_WEIGHT",
    "DIR_COLOR", "dir_color",
    "strength_label", "level_from_score",
]

# 旧三级标签（兼容既有引用：23 页徽章 / DB type 列 / 外部 import）
NEUTRAL, BULLISH, BEARISH = "中性", "利好", "利空"

# 五档：方向 × 幅度
BIG_BULLISH, SMALL_BULLISH = "大利好", "小利好"
SMALL_BEARISH, BIG_BEARISH = "小利空", "大利空"

# 展示序（强→弱）与净强度权重（±2/±1 对称零和）
STRENGTH_ORDER = (BIG_BULLISH, SMALL_BULLISH, NEUTRAL, SMALL_BEARISH, BIG_BEARISH)
STRENGTH_WEIGHT = {BIG_BULLISH: 2, SMALL_BULLISH: 1, NEUTRAL: 0,
                   SMALL_BEARISH: -1, BIG_BEARISH: -2}
_WEIGHT_TO_LABEL = {w: lab for lab, w in STRENGTH_WEIGHT.items()}

# 与 SentimentAnalyzer 既有判定线一致（勿改值——改了就是全站口径漂移）
_SENTIMENT_BAND = 0.15      # 三档判定线（score > 0.15 → 正面）
_MAJOR_BAND = 0.4           # is_major 线（|score| >= 0.4 → 重大）

# A 股语义色：「大」深一档（红-700 / 绿-700），「小」保持原值；旧三级键保留（additive）
DIR_COLOR = {
    BIG_BULLISH: "#b91c1c", SMALL_BULLISH: "#dc2626", NEUTRAL: "#94a3b8",
    SMALL_BEARISH: "#16a34a", BIG_BEARISH: "#15803d",
    BULLISH: "#dc2626", BEARISH: "#16a34a",
}


def dir_color(direction) -> str:
    """方向/档位 → 颜色（利好=红、利空=绿，其余一律灰）。"""
    return DIR_COLOR.get(str(direction), DIR_COLOR[NEUTRAL])


def strength_label(total) -> str:
    """净强度 → 五档标签（±2 截断：如两条「小利好」+2 合成「大利好」，反向同理）。"""
    try:
        t = int(total)
    except (TypeError, ValueError):
        return NEUTRAL
    return _WEIGHT_TO_LABEL[max(-2, min(2, t))]


def level_from_score(score) -> str:
    """连续情感分 score(-1~1) → 五档标签（SentimentAnalyzer 用，边界与既有判定一致）。

    |score| ≥ 0.4 → 大；0.15 < |score| < 0.4 → 小；其余（含 ±0.15 边界）→ 中性；
    None/NaN 等异常输入诚实归中性（不臆造档位）。
    """
    try:
        s = float(score)
    except (TypeError, ValueError):
        return NEUTRAL
    if s != s:  # NaN
        return NEUTRAL
    if s >= _MAJOR_BAND:
        return BIG_BULLISH
    if s > _SENTIMENT_BAND:
        return SMALL_BULLISH
    if s >= -_SENTIMENT_BAND:
        return NEUTRAL
    if s > -_MAJOR_BAND:
        return SMALL_BEARISH
    return BIG_BEARISH
