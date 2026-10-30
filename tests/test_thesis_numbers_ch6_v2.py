"""论文 6.2/6.3/6.4 数字对账守卫（T-233 论文升级收口）。

论文正文（thesis/正文/StockSignal_毕业论文_完整稿.md）的 6.2/6.3 数字必须与
`thesis/素材/ch6_eval/metrics.json`（eval_ch6.py 重跑产物）逐项一致；
6.4 数字必须与 `thesis/素材/ch6_eval/backtest_cost_metrics.json`
（gen_backtest_eval.py 重跑产物）逐格一致。数字漂移即红。
诚实边界：6.6 的 4092/49.1% 口径由 test_thesis_numbers_consistency 单独钉死，本文件不重复。
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MD = ROOT / "thesis" / "正文" / "StockSignal_毕业论文_完整稿.md"
METRICS = ROOT / "thesis" / "素材" / "ch6_eval" / "metrics.json"
BACKTEST = ROOT / "thesis" / "素材" / "ch6_eval" / "backtest_cost_metrics.json"


def _md() -> str:
    return MD.read_text(encoding="utf-8")


def _metrics() -> dict:
    return json.loads(METRICS.read_text(encoding="utf-8"))


def _backtest() -> dict:
    return json.loads(BACKTEST.read_text(encoding="utf-8"))


# ── 6.2 决策闭环评估（n=17）──
def test_62_snapshot_stats():
    m, md = _metrics(), _md()
    assert "n = 17" in md
    assert f"[{m['temperature_min_max'][0]}, {m['temperature_min_max'][1]}]" in md
    assert f"[{m['position_min_max'][0]}, {m['position_min_max'][1]}]" in md
    cyc = m["cycle_distribution"]
    assert f"修复试探 {cyc['修复试探']} 天" in md
    assert f"主升高潮 {cyc['主升高潮']} 天" in md
    assert f"退潮 {cyc['退潮']} 天" in md
    assert f"修复确认 {cyc['修复确认']} 天" in md
    assert f"预测记录 **{m['prediction_count']} 条**" in md
    assert f"已评分 **{m['prediction_scored']} 条**" in md
    assert f"命中率 {round(m['prediction_hit_rate'] * 100, 1)}%" in md


def test_62_64_sample_scale_4798():
    """摘要与 6.6 数据规模必须为 4798（T-222 回填口径），4094 不得作为样本规模残留。

    收窄说明（2026-10-30 老板批准方案 B，DECISIONS 备案）：原「全 md 禁 4094 字面」
    过宽，误伤 3.5 节口径治理叙述中的历史段长（「主体自 2009-11-02 起共 4094 个
    交易日」，b93ad96 引入）。现收窄为仅禁「样本规模表述形态」：中文口径
    「4094 个真实交易日」与英文口径「4,094 个 real trading days」及其变体；
    治理叙述使用「个交易日」（无「真实」）不属样本规模主张，放行。
    """
    md = _md()
    assert "4,798 个 real trading days" in md or "4798 个真实交易日" in md
    for banned in (
        "4094 个真实交易日",
        "4094个真实交易日",
        "4,094 个真实交易日",
        "4,094个真实交易日",
        "4094 个 real trading days",
        "4094个 real trading days",
        "4,094 个 real trading days",
        "4,094个 real trading days",
    ):
        assert banned not in md, f"4094 旧样本规模表述残留: {banned}"


# ── 6.3 刻度校准（by_group）──
def _table_cell(md: str, row_key: str, col: int) -> float:
    """从 md 表格抽指定行第 col 列的数值（容忍呈现层小数位/百分号/单位差异）。"""
    for line in md.splitlines():
        if line.strip().startswith("|") and row_key in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            raw = cells[col].replace("%", "").replace("**", "").replace(" pt", "")
            return float(raw.replace("−", "-"))
    raise AssertionError(f"表格行未找到: {row_key}")


def test_63_grouped_stats():
    m, md = _metrics(), _md()
    by_group = {g["group"]: g for g in m["grouped_stats"]["by_group"]}
    atk, dfn = by_group["进攻期"], by_group["防守期"]
    assert _table_cell(md, "进攻期", 1) == atk["n_call"]
    assert _table_cell(md, "进攻期", 2) == atk["accuracy"]
    assert _table_cell(md, "防守期", 1) == dfn["n_call"]
    assert _table_cell(md, "防守期", 2) == dfn["accuracy"]
    # 修复期 null 语义保留
    assert "| 0 | **null** |" in md


# ── 6.4 回测成本（300750 双组）──
def test_64_backtest_table():
    b, md = _backtest(), _md()
    assert b["ticker"] == "300750" and b["strategy"] == "multi_factor"
    a, z = b["with_cost"], b["zero_cost"]
    assert f"n = {a['trade_count']} 笔" in md
    # 数值级比对（容忍呈现层小数位差异）：从表 6-2 抽行与 JSON 对账
    assert abs(_table_cell(md, "总收益率", 1) - a["total_return_pct"]) < 0.005
    assert abs(_table_cell(md, "总收益率", 2) - z["total_return_pct"]) < 0.005
    assert abs(_table_cell(md, "总收益率", 3) - (-b["cost_drag_pct"])) < 0.005
    assert abs(_table_cell(md, "年化收益率", 1) - a["annualized_return_pct"]) < 0.005
    assert abs(_table_cell(md, "年化收益率", 2) - z["annualized_return_pct"]) < 0.005
    assert abs(_table_cell(md, "最大回撤", 1) - a["max_drawdown_pct"]) < 0.005
    assert abs(_table_cell(md, "最大回撤", 2) - z["max_drawdown_pct"]) < 0.005
    assert abs(_table_cell(md, "胜率", 1) - a["win_rate_pct"]) < 0.005
    assert abs(_table_cell(md, "胜率", 2) - z["win_rate_pct"]) < 0.005
    assert abs(_table_cell(md, "盈亏比", 1) - a["profit_factor"]) < 0.005
    assert abs(_table_cell(md, "盈亏比", 2) - z["profit_factor"]) < 0.005
    assert _table_cell(md, "交易笔数", 1) == a["trade_count"] == z["trade_count"]
    drag = b["cost_drag_pct"]
    assert f"−{drag} pt" in md


def test_64_sample_disclaimer_present():
    """样例选取说明必须在场（诚实边界：正收益代表标的，绝对收益非论证目标）。"""
    assert "样例取自系统策略库在同期回测中的正收益代表标的" in _md()
