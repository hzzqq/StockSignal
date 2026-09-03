# -*- coding: utf-8 -*-
"""治本方案外部 runner 清理脚本 (scripts/clean_test_tmp.py) 的验证。

核心诉求：用 os 级 shutil.rmtree 真正删除测试临时目录（绕过 genie-trash，不进回收站），
且绝不误删安全边界之外的路径。全部用临时目录，不触碰真实 E:\tmp。
"""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "clean_test_tmp.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("clean_test_tmp", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_safe_base_rejects_outside_root(tmp_path):
    mod = _load_module()
    assert mod._safe_base(os.path.join(tmp_path, "pt_fix"), str(tmp_path)) is True
    # 安全边界之外（即使是 pt_fix 前缀）应被拒
    assert mod._safe_base(r"C:\windows\pt_fix", str(tmp_path)) is False
    # 非 pt_fix 前缀应被拒
    assert mod._safe_base(os.path.join(tmp_path, "other"), str(tmp_path)) is False


def test_collect_finds_siblings(tmp_path):
    mod = _load_module()
    base = tmp_path / "pt_fix"
    base.mkdir()
    (tmp_path / "pt_fix_2026").mkdir()
    (tmp_path / "pt_fix_xyz").mkdir()
    (tmp_path / "other_dir").mkdir()
    found = mod._collect(str(base))
    names = {os.path.basename(f) for f in found}
    assert "pt_fix" in names
    assert "pt_fix_2026" in names
    assert "pt_fix_xyz" in names
    assert "other_dir" not in names


def test_delete_removes_dir(tmp_path):
    mod = _load_module()
    base = tmp_path / "pt_fix"
    base.mkdir()
    (base / "sub.lock").write_text("x")
    rc = mod.main(["--root", str(tmp_path), "--target", str(base)])
    assert rc == 0
    assert not base.exists()


def test_dry_run_keeps_dir(tmp_path):
    mod = _load_module()
    base = tmp_path / "pt_fix"
    base.mkdir()
    (base / "sub.db").write_text("x")
    rc = mod.main(["--root", str(tmp_path), "--target", str(base), "--dry-run"])
    assert rc == 0
    assert base.exists()


def test_unsafe_target_returns_one(tmp_path):
    mod = _load_module()
    rc = mod.main(["--root", str(tmp_path), "--target", r"C:\windows\pt_fix"])
    assert rc == 1


def test_cli_delete_via_subprocess(tmp_path):
    base = tmp_path / "pt_fix"
    base.mkdir()
    (base / "a.lock").write_text("x")
    r = __import__("subprocess").run(
        [sys.executable, SCRIPT, "--root", str(tmp_path), "--target", str(base)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert not base.exists()
