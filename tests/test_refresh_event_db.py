# -*- coding: utf-8 -*-
"""scripts/refresh_event_db.py 离线单元测试。

只测 run_refresh 核心逻辑（注入假 engine，不触网、不写真实 data/events.csv），
外加脚本可被 importlib 加载、--help 可用。
"""
import importlib.util
import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "refresh_event_db.py")


def _load():
    spec = importlib.util.spec_from_file_location("refresh_event_db", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeEngine:
    """假 engine：记录真实入库 / dry-run 调用，返回预设 DataFrame。"""

    def __init__(self, mined_df):
        self._df = mined_df
        self.auto_save_calls = []
        self.dry_calls = []

    def auto_mine_events(self, keyword=None, source="eastmoney", limit=30):
        self.auto_save_calls.append((keyword, source, limit))
        return self._df

    @property
    def event_miner(self):
        return self

    def mine_events(self, keyword=None, source="eastmoney", limit=30, auto_save=False):
        self.dry_calls.append((keyword, source, limit, auto_save))
        return self._df

    @property
    def event_db_path(self):
        return os.path.join(ROOT, "data", "events.csv")


def test_run_refresh_real():
    mod = _load()
    eng = FakeEngine(pd.DataFrame({"title": ["x", "y"]}))
    code, info = mod.run_refresh(eng, keyword=None, source="eastmoney", limit=30)
    assert code == 0
    assert info["mined"] == 2
    # 真实刷新走 auto_mine_events（auto_save=True 路径），不触碰 dry-run 分支
    assert eng.auto_save_calls == [(None, "eastmoney", 30)]
    assert eng.dry_calls == []


def test_run_refresh_dry_run():
    mod = _load()
    eng = FakeEngine(pd.DataFrame({"title": ["x"]}))
    code, info = mod.run_refresh(
        eng, keyword="600519", source="eastmoney", limit=10, dry_run=True)
    assert code == 0
    assert info["dry_run"] is True
    # dry-run 走 mine_events(auto_save=False)，绝不触发真实入库
    assert eng.dry_calls == [("600519", "eastmoney", 10, False)]
    assert eng.auto_save_calls == []


def test_run_refresh_no_news():
    mod = _load()
    eng = FakeEngine(pd.DataFrame(columns=["title"]))
    code, info = mod.run_refresh(eng)
    assert code == 2
    assert info["mined"] == 0


def test_run_refresh_error():
    mod = _load()

    class BoomEngine:
        def auto_mine_events(self, *a, **k):
            raise RuntimeError("network down")

        @property
        def event_miner(self):
            return self

        def mine_events(self, *a, **k):
            raise RuntimeError("network down")

    code, info = mod.run_refresh(BoomEngine())
    assert code == 1
    assert "error" in info


def test_script_loads_and_help():
    r = subprocess.run([sys.executable, SCRIPT, "--help"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0
    assert "refresh" in r.stdout.lower() or "刷新" in r.stdout
