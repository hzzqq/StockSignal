"""事件池实时桥接测试：P1 信号 → event_pool_brief 变换 + 优雅降级。

不依赖联网或 P1 真实产物；用临时目录构造最小 P1 信号文件验证变换正确性，
并验证「无产物 / 空 top_long」时拒绝覆盖既有快照。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import shepherd_ladder as sl  # noqa: E402


def _write_p1_signal(d: Path, *, top_long, latest_date="2026-09-10", model="gru"):
    d.mkdir(parents=True, exist_ok=True)
    sig = {
        "generated_at": "2026-09-10T15:00:00",
        "horizon": 10,
        "model": model,
        "latest_date": latest_date,
        "top_long": top_long,
        "top_short": [],
        "daily": [],
    }
    p = d / "signal_gru_h10.json"
    p.write_text(json.dumps(sig, ensure_ascii=False), encoding="utf-8")
    return p


def test_refresh_from_valid_p1_signal(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    out = tmp_path / "event_pool_brief.json"
    _write_p1_signal(sig_dir, top_long=[
        {"symbol": "sh600000", "score": 0.031, "rank": 1.0},
        {"symbol": "sz000001", "score": 0.028, "rank": 0.95},
        {"symbol": "sh601318", "score": 0.025, "rank": 0.90},
    ])
    # 既有离线快照不应被无效数据覆盖——先放一个占位，验证仅有效刷新才写
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")

    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir),
                                      out_path=str(out), max_age_days=30)
    assert st["refreshed"] is True
    assert st["live"] is True
    assert st["count"] == 3
    assert st["date"] == "2026-09-10"
    assert st["source"].startswith("P1-QuantFactor gru")

    brief = json.loads(out.read_text(encoding="utf-8"))
    assert brief["live"] is True
    assert len(brief["pool"]) == 3
    # 变换正确性：pct rank → 0-100 显示分；第一名应 100.0
    assert brief["pool"][0]["rank"] == 1
    assert brief["pool"][0]["symbol"] == "sh600000"
    assert brief["pool"][0]["score"] == 100.0
    assert brief["pool"][0]["raw_pred"] == 0.031
    assert brief["pool"][0]["signal"] == "看多"
    assert brief["pool"][0]["source"] == "P1-gru-top_long"
    # load_event_pool 能识别 live
    ep = sl.load_event_pool(path=str(out))
    assert ep["available"] is True
    assert ep["live"] is True
    assert ep["date"] == "2026-09-10"


def test_no_p1_signals_dir(tmp_path, monkeypatch):
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(tmp_path / "nope"),
                                      out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "no_p1_signals_dir"
    # 既有快照未被改动
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-09-03"


def test_no_p1_signal_file(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    sig_dir.mkdir()
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "no_p1_signal"


def test_empty_top_long_refused(tmp_path, monkeypatch):
    sig_dir = tmp_path / "signals"
    out = tmp_path / "event_pool_brief.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                  encoding="utf-8")
    _write_p1_signal(sig_dir, top_long=[])  # 空 top_long
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(sig_dir), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "p1_signal_empty"
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-09-03"


def test_load_event_pool_offline_snapshot_no_live_flag(tmp_path):
    p = tmp_path / "event_pool_brief.json"
    p.write_text(json.dumps({
        "date": "2026-09-03", "model": "ev",
        "source": "P1-QuantFactor EV 事件因子",
        "pool": [{"rank": 1, "symbol": "sh600869", "score": 100.0,
                  "raw_rank": 1.0, "raw_pred": 0.029, "signal": "看多",
                  "source": "P1-ev-top_long"}],
    }), encoding="utf-8")
    ep = sl.load_event_pool(path=str(p))
    assert ep["available"] is True
    assert ep["live"] is False
    assert ep["date"] == "2026-09-03"
    assert ep["source"] == "P1-QuantFactor EV 事件因子"

# ─────────────────── P1 信号目录解析（R1 守卫：防路径漂移回归） ───────────────────
def test_p1_signals_dir_default_is_a_canonical_candidate(monkeypatch):
    """无任何 env 时，默认目录必须落在 ``p1_signal.discover_source_dirs()`` 的候选里。

    历史缺陷（2026-09-17）：``shepherd_ladder`` 自己抄了一份默认路径
    ``<P1 仓>/data/P1/processed/signals``，与 ``p1_signal`` 的口径漂移，且该目录本机
    并不存在 → ``scripts/refresh_event_pool.py`` 的「缺省布局」**永远刷新不了**，
    事件池长期停在离线快照且无告警。本断言锁死「不得再出现第二份默认值」。
    """
    from modules import p1_signal as ps  # noqa: PLC0415

    for v in ("P1_PROJECT_DIR", "P1_SIGNAL_DIR", "P1_SIGNAL_FALLBACK_DIR"):
        monkeypatch.delenv(v, raising=False)
    cands = ps.discover_source_dirs()
    assert cands, "候选目录不应为空"
    got = sl._p1_signals_dir()
    assert got in cands, f"默认目录 {got!r} 不在候选 {cands!r} 中——又抄了一份默认值？"


def test_p1_signals_dir_prefers_existing_candidate(monkeypatch, tmp_path):
    """候选里存在真实目录时，必须挑「存在的」那个，而不是盲取首位。"""
    from modules import p1_signal as ps  # noqa: PLC0415

    monkeypatch.delenv("P1_PROJECT_DIR", raising=False)
    real = tmp_path / "real"
    real.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setattr(ps, "discover_source_dirs", lambda: [str(missing), str(real)])
    assert sl._p1_signals_dir() == str(real)


def test_p1_signals_dir_env_override_still_wins(monkeypatch, tmp_path):
    """``P1_PROJECT_DIR`` 是 refresh_event_pool.py 文档化的覆盖口，必须仍然优先。"""
    monkeypatch.setenv("P1_PROJECT_DIR", str(tmp_path))
    assert sl._p1_signals_dir() == os.path.join(
        str(tmp_path), "data", "P1", "processed", "signals"
    )


def test_no_module_hardcodes_p1_abs_path():
    """P1 的机器绝对路径只允许出现在单一真理源 ``modules/p1_signal.py``。

    AST 扫描**只看字符串常量、且排除 docstring**——注释/文档里写路径说明不算违规，
    但再抄一份**可执行的**默认路径就是漂移的开始（本模块的历史缺陷正是这么来的）。
    """
    import ast  # noqa: PLC0415
    import re  # noqa: PLC0415

    root = Path(__file__).resolve().parents[1]
    drive = re.compile(r"[A-Za-z]:[\\/]")
    offenders: list[str] = []
    for sub in ("modules", "pages", "scripts", "backend"):
        for p in (root / sub).rglob("*.py"):
            if p.name == "p1_signal.py":       # 单一真理源，允许有默认值
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            doc_ids: set[int] = set()
            for n in ast.walk(tree):
                body = getattr(n, "body", None)
                if isinstance(body, list) and body:
                    first = body[0]
                    if (isinstance(first, ast.Expr)
                            and isinstance(first.value, ast.Constant)
                            and isinstance(first.value.value, str)):
                        doc_ids.add(id(first.value))
            for n in ast.walk(tree):
                if not isinstance(n, ast.Constant) or not isinstance(n.value, str):
                    continue
                if id(n) in doc_ids:
                    continue
                if "P1" in n.value and drive.search(n.value):
                    offenders.append(f"{p.relative_to(root)}:{n.lineno}")
    assert not offenders, (
        "以下位置硬编码了 P1 的机器绝对路径，应改为复用 "
        "modules.p1_signal.discover_source_dirs()：\n  " + "\n  ".join(offenders)
    )

# ─────────────── 候选选择口径（R2 守卫：数据日优先 + 跳过无效候选） ───────────────
def _write_sig(d: Path, fname: str, *, latest_date, top_long, model="m"):
    d.mkdir(parents=True, exist_ok=True)
    p = d / fname
    p.write_text(json.dumps({
        "generated_at": "2026-09-10T15:00:00", "horizon": 10, "model": model,
        "latest_date": latest_date, "top_long": top_long, "top_short": [], "daily": [],
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_picks_by_latest_date_not_mtime(tmp_path):
    """候选必须按**数据日**选，不是文件 mtime。

    历史缺陷（2026-09-17）：按 mtime 取最新 → 选到 ``latest_date=2026-07-31`` 的旧导出
    （因为它的文件 mtime 更新），而同目录里存在 ``2026-08-14`` 的更新导出 ——
    **静默用了更旧的数据**。本断言把两类时间刻意错开，锁死「数据日为准」。
    """
    import time  # noqa: PLC0415

    d = tmp_path / "signals"
    stale = _write_sig(d, "signal_old_h10.json", latest_date="2026-07-31", model="old",
                       top_long=[{"symbol": "sh600000", "score": 0.01, "rank": 1.0}])
    fresh = _write_sig(d, "signal_new_h10.json", latest_date="2026-08-14", model="new",
                       top_long=[{"symbol": "sz000002", "score": 0.02, "rank": 1.0}])
    now = time.time()
    os.utime(stale, (now, now))                 # 旧数据却拥有更新的 mtime = 缺陷触发条件
    os.utime(fresh, (now - 86400, now - 86400))

    out = tmp_path / "b.json"
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(d), out_path=str(out))
    assert st["refreshed"] is True
    assert st["date"] == "2026-08-14", "选了 mtime 更新但数据日更旧的候选"
    assert st["picked"] == "signal_new_h10.json"


def test_skips_invalid_candidate_instead_of_giving_up(tmp_path):
    """最新候选无效时应跳过它继续找，而不是整体放弃。

    历史缺陷：P1 目录里最新的 ``signal_rotation.json`` 缺 latest_date，导致同目录
    其余 8 个有效导出全被无视 → 刷新永远失败（``p1_signal_empty``）且无告警。
    """
    import time  # noqa: PLC0415

    d = tmp_path / "signals"
    bad = _write_sig(d, "signal_rotation.json", latest_date=None, model="rotation",
                     top_long=[{"symbol": "sh600000", "score": 0.01, "rank": 1.0}])
    good = _write_sig(d, "signal_ens_h10.json", latest_date="2026-08-14", model="ens",
                      top_long=[{"symbol": "sz000002", "score": 0.02, "rank": 1.0}])
    now = time.time()
    os.utime(bad, (now, now))                    # 无效文件排在最前
    os.utime(good, (now - 3600, now - 3600))

    out = tmp_path / "b.json"
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(d), out_path=str(out))
    assert st["refreshed"] is True, f"无效候选卡死了整条链路：{st.get('reason')} {st.get('note')}"
    assert st["picked"] == "signal_ens_h10.json"
    assert st["skipped_invalid"] == 1, "被跳过的候选数未如实登记"


def test_all_candidates_invalid_refuses_and_keeps_snapshot(tmp_path):
    """**全部**候选都无效时仍要拒绝刷新，既有快照不得被覆盖（保安全语义）。"""
    d = tmp_path / "signals"
    _write_sig(d, "signal_a.json", latest_date=None, model="a", top_long=[{"symbol": "sh600000", "score": 1, "rank": 1.0}])
    _write_sig(d, "signal_b.json", latest_date="2026-08-14", model="b", top_long=[])
    out = tmp_path / "b.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": [{"rank": 1, "symbol": "x"}]}),
                   encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(d), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "p1_signal_empty"
    assert json.loads(out.read_text(encoding="utf-8"))["date"] == "2026-09-03"


def test_all_corrupt_reports_corrupt_not_empty(tmp_path):
    """全部无法解析时须报 ``p1_signal_corrupt``（与「字段不全」区分开，便于排障）。"""
    d = tmp_path / "signals"
    d.mkdir()
    (d / "signal_x.json").write_text("{ 不是合法 JSON", encoding="utf-8")
    (d / "signal_y.json").write_text("", encoding="utf-8")
    out = tmp_path / "b.json"
    out.write_text(json.dumps({"date": "2026-09-03", "pool": []}), encoding="utf-8")
    st = sl.refresh_event_pool_from_p1(p1_signals_dir=str(d), out_path=str(out))
    assert st["refreshed"] is False
    assert st["reason"] == "p1_signal_corrupt"


def test_pick_latest_valid_signal_helper_contract(tmp_path):
    """选择器契约：按 (latest_date, mtime) 降序；无有效候选时返回 None 而非硬编。"""
    d = tmp_path / "signals"
    a = _write_sig(d, "s_a.json", latest_date="2026-08-14", model="a",
                   top_long=[{"symbol": "sh600000", "score": 1, "rank": 1.0}])
    b = _write_sig(d, "s_b.json", latest_date="2026-08-14", model="b",
                   top_long=[{"symbol": "sh600001", "score": 1, "rank": 1.0}])
    import time  # noqa: PLC0415
    now = time.time()
    os.utime(a, (now, now))                      # 数据日并列时，mtime 更新的赢
    os.utime(b, (now - 60, now - 60))
    sig, path, bad, n_invalid = sl._pick_latest_valid_signal([str(a), str(b)])
    assert sig["model"] == "a" and path == str(a)
    assert bad == [] and n_invalid == 0
    assert sl._pick_latest_valid_signal([]) == (None, None, [], 0)
    assert sl._pick_latest_valid_signal([str(tmp_path / "nope.json")])[0] is None
