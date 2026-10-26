# -*- coding: utf-8 -*-
"""守卫：回测成本口径披露一致性（T-329）。

背景：``modules/backtest.py::_simulate`` 已含三成本拆分（commission 双边 +
slippage_pct 买卖双侧 + stamp_tax_pct 仅卖出，默认各 0.1%），并有防重复扣费
守卫（test_backtest_cost_double_count.py）。但曾出现两处口径矛盾：

① ``pages/30_策略回测.py`` 风险提示写「未计手续费/滑点等局限」——与实际
   三成本模型直接矛盾，向用户传递过时且自我贬低的口径（用户信任点）；
② ``docs/algorithm_benchmark.md`` 标「无印花税/滑点拆分」——R10 落地后
   未更新状态。

契约：
AC1 策略回测页不得再声称「未计手续费」（矛盾口径必须消失）；
AC2 策略回测页成本说明必须覆盖「印花税」且明示默认费率（0.1%）与可调性；
AC3 benchmark 文档必须含落地状态附注，且 R10 行标注已落地（证据含
    stamp_tax_pct 参数名，防止文档空喊）。
"""

import io
import os

_ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGE = os.path.join(_ROOT, "pages", "30_策略回测.py")
DOC = os.path.join(_ROOT, "docs", "algorithm_benchmark.md")


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


class TestPageCostDisclosure:
    def test_no_stale_contradiction_in_disclaimer(self):
        """AC1：风险提示不得声称「未计手续费/滑点」（与三成本模型矛盾）。"""
        src = _read(PAGE)
        assert "未计手续费" not in src, (
            "30 页风险提示仍写「未计手续费」——与 _simulate 已计佣金/滑点/印花税的"
            "实际模型矛盾（T-329 纠偏点）"
        )

    def test_cost_line_discloses_stamp_tax_and_default_rates(self):
        """AC2：成本说明必须覆盖印花税 + 明示默认费率与可调性。"""
        src = _read(PAGE)
        assert "印花税" in src, "成本说明须覆盖印花税（仅卖出）"
        assert "默认各 0.1%" in src, "须明示三成本默认费率 0.1%"
        assert "可在下方参数中调整" in src, "须注明手续费率可调（诚实透明）"


class TestBenchmarkDocLandingStatus:
    def test_doc_has_landing_status_note(self):
        """AC3a：benchmark 文档须有落地状态附注（追加不篡改原文）。"""
        src = _read(DOC)
        assert "落地状态附注" in src, "缺少落地状态附注节"

    def test_r10_marked_landed_with_evidence(self):
        """AC3b：R10 行须标注已落地且给出参数名级证据。"""
        src = _read(DOC)
        r10_lines = [ln for ln in src.splitlines() if ln.startswith("| R10")]
        assert r10_lines, "落地状态附注中缺 R10 行"
        assert "已落地" in r10_lines[0], "R10 须标注已落地"
        assert "stamp_tax_pct" in r10_lines[0], "R10 证据须含 stamp_tax_pct 参数名"
