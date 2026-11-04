"""质量数字口径文档一致性守卫（P0-1 落地，2026-11-04）。

背景：论文第 6 章、README、仓库实测长期并存三套规模数字（测试函数 4,394 / 用例 4,979→5,086、
py 文件 131 / 881、端点 89 / 35+9、页面 72 / 74）。文档一旦写成静态快照，随代码增长必然过期——
这本身就是「数字不可复核」的根源。

本测试守住三件事：

    A. 结构：`docs/质量数字口径说明_2026-11-04.md` 必须存在，且含 AUTO:METRICS 标记块
       （否则 `--write` 回填机制失效，文档会静默退化为手写快照）；
    B. 一致性：数字块每个数字必须等于同批生成的快照 `docs/quality_metrics_snapshot.json`，
       且快照必须带「生成时点 + 基线 commit」——没有时点的数字等于没有口径的数字；
    C. 实时性：结构类数字（页面数 / 业务模块数 / REST 端点）必须等于**此刻**的实测值。
       这三项是答辩最容易被追问、也最不该过期的（端点 89 vs 35 vs 101）。

为什么不把行数、文件数也钉在实时值上：LOC 每次改一行代码就变，钉死会让整套测试在任何人提交后
都变红，那不是「守住真实」，而是把 CI 变成噪音。规模类数字用「快照 + 时点」表达，
结构类数字用「实时比对」表达，各司其职。

失败时的正确修法只有一条（不要手改文档数字）：
    python scripts/quality_metrics.py --fast --write docs/质量数字口径说明_2026-11-04.md \
        --snapshot docs/quality_metrics_snapshot.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_REL = "docs/质量数字口径说明_2026-11-04.md"
SNAP_REL = "docs/quality_metrics_snapshot.json"
SCRIPT = os.path.join(ROOT, "scripts", "quality_metrics.py")

BEGIN = "<!-- AUTO:METRICS:BEGIN -->"
END = "<!-- AUTO:METRICS:END -->"

FIX_HINT = (
    "修法：python scripts/quality_metrics.py --fast "
    f"--write {DOC_REL} --snapshot {SNAP_REL}（勿手改数字）"
)

# 文档行标签 → 快照 stats 字段（全部 12 行都核对，含收集口径）
ROWS = {
    "Python 文件（全仓）": "py_files_total",
    "业务源码文件": "src_files",
    "业务源码行数": "src_loc",
    "功能页面": "pages",
    "业务模块": "modules",
    "REST 端点": "rest_routes_total",
    "测试文件": "test_files",
    "测试代码行数": "test_loc",
    "测试函数（静态口径 A）": "test_defs_static",
    "测试用例（收集口径 B）": "tests_collected",
    "AST 静态守卫文件": "guard_files",
}

# 必须与「此刻实测值」一致的结构类数字（答辩最易被追问、最不该过期）
STRUCTURAL_LIVE = ("功能页面", "业务模块", "REST 端点")


def _load_metrics():
    spec = importlib.util.spec_from_file_location("quality_metrics", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _doc_text() -> str:
    path = os.path.join(ROOT, DOC_REL)
    assert os.path.exists(path), f"缺少 {DOC_REL}：论文第 6 章数字口径说明必须有落盘文档（P0-1）"
    with open(path, encoding="utf-8") as f:
        return f.read()


def _block_rows(text: str) -> dict[str, str]:
    assert BEGIN in text and END in text, (
        f"{DOC_REL} 缺少 AUTO:METRICS 标记块：数字块无法由脚本回填，必然退化成手写快照"
    )
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    rows: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("指标", "---") or set(cells[0]) <= {"-", ":"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


@pytest.fixture(scope="module")
def metrics_mod():
    return _load_metrics()


@pytest.fixture(scope="module")
def snapshot():
    path = os.path.join(ROOT, SNAP_REL)
    assert os.path.exists(path), (
        f"缺少快照 {SNAP_REL}：文档数字必须能追到一次可复跑的生成记录，{FIX_HINT}"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def doc_rows():
    return _block_rows(_doc_text())


def test_doc_has_auto_metrics_block(doc_rows):
    """A：文档与回填标记必须存在（防止文档退化为手写快照）。"""
    assert len(doc_rows) >= len(ROWS), f"数字块行数不足，实际只有：{sorted(doc_rows)}"


def test_snapshot_records_time_and_commit(snapshot):
    """B0：快照必须带生成时点与基线 commit——否则「当前实测」无法验真。"""
    meta = snapshot.get("meta") or {}
    assert meta.get("generated_at"), "快照缺 generated_at（生成时点）"
    assert meta.get("git_head"), "快照缺 git_head（基线 commit）"
    assert snapshot.get("stats"), "快照缺 stats"


@pytest.mark.parametrize("label", sorted(ROWS))
def test_doc_number_matches_snapshot(label, metrics_mod, snapshot, doc_rows):
    """B：文档数字必须等于同批生成的快照值（格式与 `--write` 输出一致）。"""
    assert label in doc_rows, f"数字块缺少「{label}」行；{FIX_HINT}"
    key = ROWS[label]
    expected_raw = (snapshot["stats"] or {}).get(key)
    expected = metrics_mod._fmt(expected_raw)
    actual = doc_rows[label].strip()
    if expected_raw is None:
        assert actual == "—", f"「{label}」快照无值时应写 —，实际写 {actual!r}"
        return
    assert actual == expected, f"「{label}」文档写 {actual!r}，快照为 {expected!r}；{FIX_HINT}"


@pytest.mark.parametrize("label", STRUCTURAL_LIVE)
def test_structural_numbers_match_live(label, metrics_mod, doc_rows):
    """C：结构类数字必须等于此刻实测值（页面/模块/端点，答辩最易被追问）。"""
    live = metrics_mod.collect(fast=True)
    expected = metrics_mod._fmt(live[ROWS[label]])
    actual = doc_rows[label].strip()
    assert actual == expected, (
        f"「{label}」文档写 {actual!r}，此刻实测 {expected!r}；{FIX_HINT}。"
        "该数字属结构类，必须实时正确——历史上正是这里出现过 89/35/101 三套并存"
    )


def test_collected_metric_is_labelled_not_guessed(doc_rows):
    """收集口径允许为 —（需 pytest 收集），但不得出现无来源的裸数字。"""
    value = doc_rows["测试用例（收集口径 B）"].strip()
    assert value == "—" or re.fullmatch(r"\d{1,3}(,\d{3})*", value), (
        f"收集口径取值非法：{value!r}；须为千分位数字或 —（收集失败时如实留空）"
    )


def test_script_declares_exclude_scope(metrics_mod):
    """口径必须写死在脚本里（否则数字不可比）：排除目录与测试三目录不得为空。"""
    assert {"__pycache__", ".pytest_cache", ".ruff_cache", "backups", "data"} <= set(metrics_mod.EXCLUDE_DIRS)
    assert set(metrics_mod.TEST_DIRS) == {"tests", "backend/tests", "modules/tests"}, (
        "测试范围必须覆盖三处；modules/tests 曾被漏数导致少报约 35 用例"
    )
