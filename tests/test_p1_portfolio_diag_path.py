"""tests/test_p1_portfolio_diag_path.py

D2 真理源统一：P1 组合诊断 JSON 路径必须复用
``modules.p1_signal.discover_source_dirs()`` 的候选解析，
不得在本模块单独读 P1_SIGNAL_DIR / 硬编码机器绝对路径。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_diag_path_uses_discover_source_dirs(monkeypatch, tmp_path):
    """候选目录含 portfolio_diag.json 时，_diag_path() 必须命中它。"""
    from modules import p1_signal as ps
    from modules.p1_portfolio_diag import _diag_path

    diag = tmp_path / "portfolio_diag.json"
    diag.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ps, "discover_source_dirs", lambda: [str(tmp_path)])

    assert _diag_path() == diag


def test_diag_path_picks_existing_candidate(monkeypatch, tmp_path):
    """多个候选里存在真实文件时应挑存在的那个，而不是盲取首位。"""
    from modules import p1_signal as ps
    from modules.p1_portfolio_diag import _diag_path

    missing = tmp_path / "missing"
    real = tmp_path / "real"
    real.mkdir()
    diag = real / "portfolio_diag.json"
    diag.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ps, "discover_source_dirs", lambda: [str(missing), str(real)])

    assert _diag_path() == diag


def test_diag_path_does_not_read_env_directly(monkeypatch, tmp_path):
    """P1_SIGNAL_DIR 仅由 discover_source_dirs() 消费；本模块不得再单独读 env。"""
    from modules import p1_signal as ps
    from modules.p1_portfolio_diag import _diag_path

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    env_dir = tmp_path / "envdir"
    env_dir.mkdir()
    env_diag = env_dir / "portfolio_diag.json"
    env_diag.write_text("{}", encoding="utf-8")

    # discover_source_dirs 返回一个没有 diag 的目录；若 _diag_path 自己读 env，
    # 就会错误命中 env_dir → 断言失败。
    monkeypatch.setenv("P1_SIGNAL_DIR", str(env_dir))
    monkeypatch.setattr(ps, "discover_source_dirs", lambda: [str(empty_dir)])

    fallback = (Path(ps.__file__).resolve().parent.parent
                / "data" / "p1_signals" / "portfolio_diag.json")
    assert _diag_path() == fallback
    assert _diag_path() != env_diag
