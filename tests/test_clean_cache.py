# -*- coding: utf-8 -*-
"""clean_cache.py 核心逻辑单测：按 mtime 枚举旧缓存 + dry-run 不删 + --yes 才删。

锁住三条不变量：
1. collect_stale 只按 mtime 早于 cutoff 的文件枚举，目录外的文件永不入列；
2. --dry-run / 无 --yes 时 main 不删除任何文件；
3. --yes 时 main 真正删除且数量正确。
"""
import os
import sys
import time
from pathlib import Path

import pytest

# 让测试能 import 到仓库根的 clean_cache 模块
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clean_cache  # noqa: E402


def _touch(path: Path, days_ago: float):
    """把文件 mtime 设到 days_ago 天前（float 支持小数天，保证越过 cutoff 边界）。"""
    mtime = time.time() - days_ago * 86400
    os.utime(path, (mtime, mtime))


def _make_tree(tmp_path: Path):
    """在 tmp_path 下造 3 个 csv：2 旧 1 新，外加一个子目录里的旧文件。"""
    old_a = tmp_path / "old_a.csv"
    old_b = tmp_path / "old_b.csv"
    new_c = tmp_path / "new_c.csv"
    sub = tmp_path / "sub"
    sub.mkdir()
    old_d = sub / "old_d.csv"
    for f in (old_a, old_b, new_c, old_d):
        f.write_text("x,y\n1,2\n")
    _touch(old_a, 40)
    _touch(old_b, 35)
    _touch(old_d, 50)
    _touch(new_c, 1)  # 远在 30 天 cutoff 之内
    return old_a, old_b, new_c, old_d


def test_collect_stale_old_and_new(tmp_path):
    old_a, old_b, new_c, old_d = _make_tree(tmp_path)
    removed, freed = clean_cache.collect_stale(tmp_path, days=30)
    paths = set(removed)
    assert old_a in paths and old_b in paths and old_d in paths
    assert new_c not in paths  # 1 天前的文件不应入列
    assert len(removed) == 3
    assert freed == sum(f.stat().st_size for f in (old_a, old_b, old_d))


def test_collect_stale_none_old_when_all_recent(tmp_path):
    # 全部文件仅 0.1 天前，days=30 的 cutoff 远在过去 -> 无一过线
    for name in ("a.csv", "b.csv", "c.csv"):
        p = tmp_path / name
        p.write_text("x\n")
        _touch(p, 0.1)
    removed, freed = clean_cache.collect_stale(tmp_path, days=30)
    assert removed == []
    assert freed == 0


def test_main_dry_run_does_not_delete(tmp_path, capsys):
    old_a, old_b, new_c, old_d = _make_tree(tmp_path)
    with pytest.raises(SystemExit):
        clean_cache.main(["--cache-dir", str(tmp_path), "--days", "30"])  # 无 --yes/--dry-run -> error
    # 上面已抛错，文件还在；下面真正 dry-run
    clean_cache.main(["--cache-dir", str(tmp_path), "--days", "30", "--dry-run"])
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    # 文件一个都没少
    for f in (old_a, old_b, old_d):
        assert f.exists()


def test_main_yes_deletes_old_only(tmp_path, capsys):
    old_a, old_b, new_c, old_d = _make_tree(tmp_path)
    clean_cache.main(["--cache-dir", str(tmp_path), "--days", "30", "--yes"])
    out = capsys.readouterr().out
    assert "已清理 3/" in out
    # 旧的没了，新的还在
    assert not old_a.exists() and not old_b.exists() and not old_d.exists()
    assert new_c.exists()


def test_main_missing_confirm_errors(tmp_path):
    _make_tree(tmp_path)
    with pytest.raises(SystemExit):
        # 既无 --dry-run 也无 --yes -> argparse error 退出
        clean_cache.main(["--cache-dir", str(tmp_path), "--days", "30"])
