"""T-287 五档事件强度标准单一真理源守卫（modules/event_levels.py）。

事件分析器（SentimentAnalyzer，23_事件追踪）与事件传导图谱（event_graph，75_题材热点）
共享同一五档标准：大利好(+2) / 小利好(+1) / 中性(0) / 小利空(-1) / 大利空(-2)。
- ``level_from_score`` 复用分析器既有阈值 ±0.15（三档线）与 ±0.4（is_major 线），无新魔法数；
- event_graph 全部常量改为 re-export，公开 API 零变化（断链 / 重定义即红）；
- 23 页 additive 接线以 AST 守卫钉住（挑列含 level、type_col 诚实回退、徽章子串判定）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import modules.event_graph as eg  # noqa: E402
import modules.event_levels as el  # noqa: E402


def test_five_labels_and_order():
    """五档标签与展示序（强→弱）。"""
    assert el.STRENGTH_ORDER == (el.BIG_BULLISH, el.SMALL_BULLISH, el.NEUTRAL,
                                 el.SMALL_BEARISH, el.BIG_BEARISH)
    assert (el.BIG_BULLISH, el.SMALL_BULLISH) == ("大利好", "小利好")
    assert (el.SMALL_BEARISH, el.BIG_BEARISH) == ("小利空", "大利空")
    assert el.NEUTRAL == "中性" and (el.BULLISH, el.BEARISH) == ("利好", "利空")


def test_strength_weight_zero_sum_and_symmetry():
    """权重 ±2/±1 对称零和（聚合口径单一源）。"""
    assert set(el.STRENGTH_WEIGHT) == set(el.STRENGTH_ORDER)
    assert sum(el.STRENGTH_WEIGHT.values()) == 0
    assert el.STRENGTH_WEIGHT[el.BIG_BULLISH] == 2 and el.STRENGTH_WEIGHT[el.BIG_BEARISH] == -2
    assert el.STRENGTH_WEIGHT[el.SMALL_BULLISH] == 1 and el.STRENGTH_WEIGHT[el.SMALL_BEARISH] == -1


def test_level_from_score_boundaries():
    """score → 五档边界矩阵（±0.15/±0.4 既有阈值，边界归属与既有判定一致）。"""
    assert el.level_from_score(1.0) == el.BIG_BULLISH
    assert el.level_from_score(0.4) == el.BIG_BULLISH        # is_major 线起记「大」
    assert el.level_from_score(0.399) == el.SMALL_BULLISH
    assert el.level_from_score(0.1501) == el.SMALL_BULLISH
    assert el.level_from_score(0.15) == el.NEUTRAL           # 既有判定 score > 0.15 严格不等
    assert el.level_from_score(0.0) == el.NEUTRAL
    assert el.level_from_score(-0.15) == el.NEUTRAL
    assert el.level_from_score(-0.1501) == el.SMALL_BEARISH
    assert el.level_from_score(-0.399) == el.SMALL_BEARISH
    assert el.level_from_score(-0.4) == el.BIG_BEARISH
    assert el.level_from_score(-1.0) == el.BIG_BEARISH


def test_level_from_score_bad_input_neutral():
    """异常输入（None/NaN）诚实归中性，不臆造档位。"""
    assert el.level_from_score(None) == el.NEUTRAL
    assert el.level_from_score(float("nan")) == el.NEUTRAL


def test_strength_label_clamps_to_two():
    """净强度 ±2 截断（多条加权合成的口径与 event_graph 一致）。"""
    assert el.strength_label(2) == el.BIG_BULLISH
    assert el.strength_label(5) == el.BIG_BULLISH
    assert el.strength_label(1) == el.SMALL_BULLISH
    assert el.strength_label(0) == el.NEUTRAL
    assert el.strength_label(-1) == el.SMALL_BEARISH
    assert el.strength_label(-3) == el.BIG_BEARISH


def test_dir_color_a_share_semantics():
    """A 股语义：利好=红、利空=绿，「大」深一档；旧三级标签与未知值兼容。"""
    assert el.dir_color(el.BIG_BULLISH) == "#b91c1c"
    assert el.dir_color(el.SMALL_BULLISH) == "#dc2626"
    assert el.dir_color(el.NEUTRAL) == "#94a3b8"
    assert el.dir_color(el.SMALL_BEARISH) == "#16a34a"
    assert el.dir_color(el.BIG_BEARISH) == "#15803d"
    assert el.dir_color(el.BULLISH) == "#dc2626"      # 旧标签兼容
    assert el.dir_color(el.BEARISH) == "#16a34a"
    assert el.dir_color("未知") == "#94a3b8"


def test_event_graph_reexports_shared_constants():
    """event_graph 常量与共享源等值（re-export 断链 / 本地重定义即红）。"""
    for name in ("NEUTRAL", "BULLISH", "BEARISH", "BIG_BULLISH", "SMALL_BULLISH",
                 "SMALL_BEARISH", "BIG_BEARISH", "STRENGTH_ORDER", "STRENGTH_WEIGHT"):
        assert getattr(eg, name) == getattr(el, name), name
    assert eg.DIR_COLOR == el.DIR_COLOR
    assert eg.dir_color is el.dir_color               # 同一函数对象（非拷贝）


def test_page23_renders_five_level_badges():
    """23 页 additive 接线：实时事件挑列含 level、type_col 诚实回退、徽章子串判定。"""
    src = (Path(__file__).resolve().parents[1] / "pages" / "23_事件追踪.py").read_text(
        encoding="utf-8")
    assert "['sentiment', 'score', 'level']" in src, "实时事件挑列未加 level"
    assert "type_col='level' if 'level' in events_realtime.columns else 'sentiment'" in src, \
        "实时列表未接 level（缺诚实回退）"
    assert "'大利好' in etype or '小利好' in etype or etype == '正面'" in src, \
        "徽章判定未兼容五档利好系"
    assert "'大利空' in etype or '小利空' in etype or etype == '负面'" in src, \
        "徽章判定未兼容五档利空系"
    assert "elif etype in ('利好', '利空', '中性'):" in src, "旧值灰色分支不得改动（additive）"
