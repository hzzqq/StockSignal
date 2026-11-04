"""P1 单向同步（modules/p1_sync + scripts/refresh_p1_signals）守卫测试。

钉住四类不变量：
  1. 结构有效性判定**排除新鲜度**（fusion 存在设计性滞后，新鲜度不是同步闸）
  2. 候选选择按 latest_date 降序，mtime 仅作并列次键（禁止用 mtime 当数据新旧）
  3. 全部候选无效 → 拒绝写入（保留既有副本）；绝不降级覆盖更新数据
  4. 新模块与新脚本**不含机器绝对路径字面量**（单一真理源纪律）
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
import sys  # noqa: E402

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from modules.p1_sync import (  # noqa: E402
    collect_candidates,
    pick_latest,
    plan_sync,
    structural_ok,
    sync_once,
)

HEALTHY_KEYS = ("model", "latest_date", "horizon", "top_long", "top_short", "daily")


def _payload(model: str, latest_date: str, rank: float = 1.0) -> dict:
    """构造一个结构合法（键齐全 / symbol 合法 / rank 单调）的信号体。"""
    return {
        "model": model,
        "latest_date": latest_date,
        "horizon": 10,
        "top_long": [{"symbol": "sh600519", "rank": 1.0},
                     {"symbol": "sz300750", "rank": 0.9}],
        "top_short": [{"symbol": "sz000001", "rank": 0.001},
                      {"symbol": "sh601318", "rank": 0.002}],
        "daily": [],
        "generated_at": f"{latest_date}T16:00:00",
    }


def _write(d: Path, name: str, payload: dict) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ── 1. 结构有效性：新鲜度不算结构错误 ──────────────────────────────
def test_structural_ok_excludes_freshness_error():
    rec = {"parseable": True, "missing_keys": [], "latest_date": "2026-01-01",
           "symbol_ok": True, "rank_ok": True,
           "errors": ["数据滞后 40 自然日（SLA ≤ 8）"]}
    ok, errs = structural_ok(rec)
    assert ok is True, "新鲜度滞后不应判定为结构无效"
    assert errs == []


def test_structural_ok_rejects_missing_keys():
    rec = {"parseable": True, "missing_keys": ["daily"], "latest_date": "2026-01-01",
           "symbol_ok": True, "rank_ok": True, "errors": ["缺字段: daily"]}
    ok, errs = structural_ok(rec)
    assert ok is False
    assert errs


def test_structural_ok_rejects_bad_latest_date():
    rec = {"parseable": True, "missing_keys": [], "latest_date": None,
           "symbol_ok": True, "rank_ok": True,
           "errors": ["latest_date 缺失或非法 ISO 日期"]}
    ok, _ = structural_ok(rec)
    assert ok is False


# ── 2. 候选选择：latest_date 优先，mtime 仅并列次键 ──────────────────
def test_pick_latest_prefers_latest_date_over_mtime():
    """老数据但 mtime 更新 → 仍选数据日新的（禁止用 mtime 当数据新旧）。"""
    cands = [
        {"ok": True, "latest_date": "2026-10-10", "mtime": 9999.0, "name": "signal_gru_h10.json"},
        {"ok": True, "latest_date": "2026-10-16", "mtime": 1.0, "name": "signal_gru_h10.json"},
    ]
    best = pick_latest(cands)
    assert best["latest_date"] == "2026-10-16"


def test_pick_latest_tiebreak_by_mtime():
    cands = [
        {"ok": True, "latest_date": "2026-10-16", "mtime": 1.0, "name": "a.json"},
        {"ok": True, "latest_date": "2026-10-16", "mtime": 2.0, "name": "b.json"},
    ]
    assert pick_latest(cands)["mtime"] == 2.0


def test_pick_latest_returns_none_when_all_invalid():
    assert pick_latest([{"ok": False, "latest_date": "2026-10-16", "mtime": 1.0}]) is None
    assert pick_latest([]) is None


# ── 3. 同步计划：幂等 / 拒绝写入 / 绝不降级 ──────────────────────────
def test_plan_sync_copies_newer_source(tmp_path):
    src = tmp_path / "p1_out"
    tgt = tmp_path / "self_hosted"
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-10-16"))
    plan = plan_sync([str(src)], tgt)
    assert plan["all_invalid"] is False
    item = next(i for i in plan["items"] if i["model_key"] == "gru")
    assert item["action"] == "copy"
    assert item["latest_date"] == "2026-10-16"


def test_sync_once_writes_and_is_idempotent(tmp_path):
    src = tmp_path / "p1_out"
    tgt = tmp_path / "self_hosted"
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-10-16"))
    r1 = sync_once([str(src)], tgt)
    assert r1["written_any"] is True
    assert (tgt / "signal_gru_h10.json").exists()
    r2 = sync_once([str(src)], tgt)
    assert r2["written_any"] is False
    assert any(i["action"] == "unchanged" for i in r2["plan"]["items"])


def test_plan_sync_never_downgrades_newer_target(tmp_path):
    src = tmp_path / "p1_out"
    tgt = tmp_path / "self_hosted"
    _write(src, "signal_gru_h10.json", _payload("gru", "2026-10-01"))
    _write(tgt, "signal_gru_h10.json", _payload("gru", "2026-10-16"))
    plan = plan_sync([str(src)], tgt)
    item = next(i for i in plan["items"] if i["model_key"] == "gru")
    assert item["action"] == "target_newer"
    sync_once([str(src)], tgt)
    # 目标仍是较新数据日
    kept = json.loads((tgt / "signal_gru_h10.json").read_text(encoding="utf-8"))
    assert kept["latest_date"] == "2026-10-16"


def test_plan_sync_refuses_write_when_all_candidates_invalid(tmp_path):
    src = tmp_path / "p1_out"
    tgt = tmp_path / "self_hosted"
    src.mkdir(parents=True, exist_ok=True)
    (src / "signal_gru_h10.json").write_text("{ broken json", encoding="utf-8")
    _write(tgt, "signal_gru_h10.json", _payload("gru", "2026-10-16"))
    plan = plan_sync([str(src)], tgt)
    assert plan["all_invalid"] is True
    res = sync_once([str(src)], tgt)
    assert res["written_any"] is False
    kept = json.loads((tgt / "signal_gru_h10.json").read_text(encoding="utf-8"))
    assert kept["latest_date"] == "2026-10-16", "全部无效时不得覆盖既有副本"


def test_skip_reason_carries_structural_detail(tmp_path):
    """被跳过的候选必须如实带出结构错误（不笼统说「无效」）。"""
    src = tmp_path / "p1_out"
    tgt = tmp_path / "self_hosted"
    src.mkdir(parents=True, exist_ok=True)
    # 非模型信号 schema（缺 horizon/top_short/daily/latest_date）
    (src / "signal_rotation.json").write_text(
        json.dumps({"as_of": "2026-10-16", "method": "x", "top_long": []}),
        encoding="utf-8")
    plan = plan_sync([str(src)], tgt)
    item = next(i for i in plan["items"] if i["model_key"] == "rotation")
    assert item["action"] == "skip"
    assert "结构无效" in item["reason"]
    assert ("latest_date" in item["reason"]) or ("缺字段" in item["reason"])


def test_collect_candidates_skips_target_dir(tmp_path):
    tgt = tmp_path / "self_hosted"
    _write(tgt, "signal_gru_h10.json", _payload("gru", "2026-10-16"))
    cands = collect_candidates([str(tgt)], tgt)
    assert cands == []


# ── 4. 单一真理源：新模块 / 新脚本不含机器绝对路径 ───────────────────
@pytest.mark.parametrize("rel", [
    "modules/p1_sync.py",
    "scripts/refresh_p1_signals.py",
])
def test_no_hardcoded_drive_letter(rel):
    """AST 只看字符串常量（排除 docstring）；机器绝对路径只允许在 p1_signal.py。"""
    p = REPO / rel
    assert p.exists(), f"缺失约定文件: {rel}"
    tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    doc_ids: set[int] = set()
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                doc_ids.add(id(first.value))
    drive = re.compile(r"[A-Za-z]:[\\/]")
    offenders: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Constant) or not isinstance(n.value, str):
            continue
        if id(n) in doc_ids:
            continue
        if drive.search(n.value):
            offenders.append(f"{rel}:{n.lineno} {n.value[:60]}")
    assert not offenders, offenders


def test_script_cli_help_runs():
    """CLI 入口可解析（--help 正常退出，参数契约不破）。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "refresh_p1_signals.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-400:]
    assert "--check" in r.stdout
