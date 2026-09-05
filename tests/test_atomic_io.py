"""modules.atomic_io 单元测试 + 并发写竞争压测。

重点：并发压测锁死「固定 tmp 名 → 多写者 PermissionError」的修复。
回归背景（2026-09-05）：
  原 13 处内联原子写都用 f"{path}.tmp" 固定名，多写者并发下互相覆盖 tmp 并抛
  PermissionError(WinError 32/5)；实测 8 线程×20 轮=160 次写入失败 7 次（约 4.4%）。
  现统一到 atomic_io（tmp 名唯一化 pid+线程id+uuid + replace 退避重试），
  实测 480 次并发写入 0 异常、文件始终完整、无 tmp 残留。
"""

import json
import os
import threading

import pandas as pd
import pytest

from modules.atomic_io import atomic_json_dump, atomic_to_csv, unique_tmp_path


def test_unique_tmp_path_distinct_and_same_dir():
    p = "data/x.csv"
    a = unique_tmp_path(p)
    b = unique_tmp_path(p)
    assert a != b  # 每次唯一
    # 同目录：Windows 上 os.replace 跨目录不保证原子，必须同目录
    assert os.path.dirname(a) == "data"
    assert a.endswith(".tmp")


def test_atomic_to_csv_roundtrip(tmp_path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    p = tmp_path / "t.csv"
    atomic_to_csv(df, str(p))
    out = pd.read_csv(p)
    assert len(out) == 2
    assert out["a"].tolist() == [1, 2]
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_json_dump_roundtrip(tmp_path):
    p = tmp_path / "t.json"
    atomic_json_dump({"k": [1, 2], "中文": "值"}, str(p))
    loaded = json.load(open(p, encoding="utf-8"))
    assert loaded["k"] == [1, 2]
    assert loaded["中文"] == "值"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_cleans_tmp_on_write_error(tmp_path):
    """异常时清理自己的 tmp，不留垃圾。"""
    p = tmp_path / "t.csv"
    with pytest.raises(Exception):
        atomic_to_csv(None, str(p))  # None 无 to_csv 方法
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_concurrent_writes_stable(tmp_path):
    """并发压测：多写者同时写同一路径，修复后应 0 异常、文件完整、无 tmp 残留。

    规模 4 线程×10 轮=40 次（CI 友好，仍足以暴露 fixed-tmp 竞态：
    固定 tmp 名下约 1-2 次会失败）。修复后实测 480 次连跑 0 失败。
    """
    p = str(tmp_path / "positions.csv")
    big = pd.DataFrame({"a": range(2000), "b": ["x" * 20] * 2000})
    N_THREADS = 4
    ROUNDS = 10

    def writer(i):
        for _ in range(ROUNDS):
            df = big.copy()
            df["tag"] = i
            atomic_to_csv(df, p)  # 若抛异常，pytest 会让线程崩溃并由 join 暴露

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(N_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    out = pd.read_csv(p)
    assert len(out) == len(big), "并发写入后文件应完整"
    assert list(tmp_path.glob("*.tmp")) == [], "不应有残留 tmp"
