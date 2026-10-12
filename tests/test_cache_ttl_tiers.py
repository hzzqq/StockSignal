"""
tests/test_cache_ttl_tiers.py
=============================
T-272③：页面层 TTL 分级契约——TTL_TIERS 单源常量 + 存量裸 TTL 快照守卫（增量守门）。

策略（诚实边界）：全仓 ~78 处存量裸 TTL 一律**维持现状**（改值即改行为、动静过大
且无行为收益），本守卫只拦「新增未登记裸 TTL」——新增 st.cache_data(ttl=<数字>)
而未登记快照即红，逼新代码引用 cache_utils.TTL_TIERS 或登记并说明理由。
快照：tests/fixtures/ttl_snapshot.json（AST 扫描 pages/ + modules/ + app.py）。
"""
import ast
import json
from collections import Counter
from pathlib import Path

from modules.cache_utils import TTL_TIERS

_PROJECT = Path(__file__).resolve().parents[1]
SNAPSHOT = _PROJECT / "tests" / "fixtures" / "ttl_snapshot.json"


def _scan() -> Counter:
    """扫描当前仓库的裸 ttl 装饰器多重集合 {(file, ttl): count}（与快照生成器同口径）。"""
    targets = []
    for d in ("pages", "modules"):
        targets.extend(sorted((_PROJECT / d).glob("*.py")))
    app = _PROJECT / "app.py"
    if app.exists():
        targets.append(app)

    counter: Counter = Counter()
    for p in targets:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            for dec in getattr(node, "decorator_list", []):
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not (isinstance(func, ast.Attribute) and func.attr == "cache_data"):
                    continue
                for kw in dec.keywords:
                    if kw.arg == "ttl" and isinstance(kw.value, ast.Constant) \
                            and isinstance(kw.value.value, (int, float)):
                        rel = str(p.relative_to(_PROJECT)).replace("\\", "/")
                        counter[(rel, kw.value.value)] += 1
    return counter


def test_ttl_tiers_structure():
    """TTL_TIERS 四档常量：结构、数值、语义锚点（对齐 P1SignalLoader ttl=300）。"""
    assert set(TTL_TIERS) == {"realtime", "quote", "sentiment", "fundamental"}
    assert all(isinstance(v, (int, float)) and v > 0 for v in TTL_TIERS.values())
    assert TTL_TIERS["sentiment"] == 300, "sentiment 档应与 P1SignalLoader ttl 对齐"
    assert TTL_TIERS["realtime"] < TTL_TIERS["quote"] \
        < TTL_TIERS["sentiment"] < TTL_TIERS["fundamental"], "档位必须单调递增"


def test_snapshot_exists_and_nonempty():
    """快照文件存在且非空（防守卫自我静音：快照被删/清空时红）。"""
    assert SNAPSHOT.exists(), "裸 TTL 快照文件缺失——守卫失效，请用 E:/tmp 生成脚本重建"
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data.get("entries"), "快照 entries 为空——守卫形同虚设"
    assert sum(e["count"] for e in data["entries"]) >= 50, \
        "快照规模骤降（全仓裸 TTL 应约 78 处）——疑似扫描口径被改窄"


def test_no_new_unregistered_bare_ttl():
    """增量守门：当前仓库裸 TTL 集合 ⊆ 快照（新增未登记即红，删除不拦）。"""
    snapshot = Counter()
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for e in data["entries"]:
        snapshot[(e["file"], e["ttl"])] += e["count"]

    current = _scan()
    fresh = current - snapshot  # 新增部分
    assert not fresh, (
        "发现未登记的新增裸 TTL——请改用 cache_utils.TTL_TIERS 档位，"
        f"或更新 tests/fixtures/ttl_snapshot.json 并说明理由。新增项：{dict(fresh)}"
    )
