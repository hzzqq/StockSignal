"""save_history 防覆盖护栏测试。

背景（R25/R27）：shepherd_cache_v2 已被覆盖成每只股票仅 6 行近期残缓存，盲跑
build_shepherd_history(reconstruct=True) 会把 data/shepherd_history.csv（4094 行好表）
覆盖成 6 行且因 .gitignore 不可恢复。护栏默认拒绝这种退化覆盖；force 时先备份。
"""
import pandas as pd
import pytest

from modules.shepherd_reconstruct import save_history, _BREADTH_FILE


def _write_good_csv(path, n_rows):
    """写一个含表头、首列为 date 的 '好表'。"""
    df = pd.DataFrame({"date": [f"2020-01-{i:02d}" for i in range(1, n_rows + 1)],
                       "up_count": range(n_rows)})
    df.to_csv(path, index=False, encoding="utf-8-sig")


def test_save_history_guard_refuses_degraded_overwrite(tmp_path, monkeypatch):
    """新表行数远低于现有好表 → 默认拒绝覆盖（抛 RuntimeError，原表不动）。"""
    good = tmp_path / "shepherd_history.csv"
    _write_good_csv(good, 100)
    monkeypatch.setattr("modules.shepherd_reconstruct._BREADTH_FILE", str(good))

    tiny = pd.DataFrame({"date": ["2020-01-01"], "up_count": [1]})
    with pytest.raises(RuntimeError):
        save_history(tiny, path=str(good), force=False)

    # 原表未被覆盖
    remained = pd.read_csv(good, encoding="utf-8-sig")
    assert len(remained) == 100


def test_save_history_force_backs_up_then_overwrites(tmp_path, monkeypatch):
    """force=True 时先备份现有好表（.bak-before-rerun），再覆盖为主表。"""
    good = tmp_path / "shepherd_history.csv"
    _write_good_csv(good, 100)
    monkeypatch.setattr("modules.shepherd_reconstruct._BREADTH_FILE", str(good))

    tiny = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "up_count": [1, 2]})
    save_history(tiny, path=str(good), force=True)

    # 主表被覆盖为 2 行
    main = pd.read_csv(good, encoding="utf-8-sig")
    assert len(main) == 2
    # 备份存在且保留了 100 行好表
    bak = tmp_path / "shepherd_history.csv.bak-before-rerun"
    assert bak.exists()
    bak_df = pd.read_csv(bak, encoding="utf-8-sig")
    assert len(bak_df) == 100


def test_save_history_passes_normal_sized_output(tmp_path, monkeypatch):
    """新表规模 >= 现有表 * 0.5 → 正常落盘，不触发护栏、不备份。"""
    good = tmp_path / "shepherd_history.csv"
    _write_good_csv(good, 100)
    monkeypatch.setattr("modules.shepherd_reconstruct._BREADTH_FILE", str(good))

    okay = pd.DataFrame({"date": [f"2020-02-{i:02d}" for i in range(1, 80)],
                         "up_count": range(79)})
    save_history(okay, path=str(good), force=False)

    main = pd.read_csv(good, encoding="utf-8-sig")
    assert len(main) == 79
    assert not (tmp_path / "shepherd_history.csv.bak-before-rerun").exists()


def test_save_history_refuses_empty_overwrite(tmp_path, monkeypatch):
    """新表为空 → 拒绝覆盖真实历史（空表会清掉主档）。"""
    good = tmp_path / "shepherd_history.csv"
    _write_good_csv(good, 100)
    monkeypatch.setattr("modules.shepherd_reconstruct._BREADTH_FILE", str(good))

    empty = pd.DataFrame({"date": pd.Series([], dtype=str), "up_count": pd.Series([], dtype=int)})
    with pytest.raises(RuntimeError):
        save_history(empty, path=str(good), force=False)
    assert len(pd.read_csv(good, encoding="utf-8-sig")) == 100
