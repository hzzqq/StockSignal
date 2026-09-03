# -*- coding: utf-8 -*-
"""事件因子选股池素材生成脚本 (scripts/gen_event_pool_brief.py) 的离线验证。

仅校验脚本可独立运行、产物格式正确，不依赖真实 P1 信号文件（离线时 event_driven_long_list 返回 []）。
"""
import importlib.util
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "gen_event_pool_brief.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_event_pool_brief", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_markdown_empty():
    mod = _load_module()
    md = mod._build_markdown([], "ev", "2026-09-03")
    assert "事件驱动看多榜" in md
    assert "今日无事件因子信号" in md


def test_build_markdown_rows():
    mod = _load_module()
    rows = [{"symbol": "sh600000", "score": 88.0, "source": "P1-ev-top_long"}]
    md = mod._build_markdown(rows, "ev", "2026-09-03")
    assert "sh600000" in md
    assert "88.0" in md


def test_build_json_shape():
    mod = _load_module()
    rows = [{"symbol": "sh600000", "score": 88.0, "raw_rank": 0.12,
             "raw_pred": 0.31, "signal": "看多", "source": "P1-ev-top_long"}]
    js = mod._build_json(rows, "ev", "2026-09-03")
    assert js["count"] == 1
    assert js["pool"][0]["rank"] == 1
    assert js["pool"][0]["symbol"] == "sh600000"
    assert js["date"] == "2026-09-03"


def test_cli_dry_run_exits_zero():
    """无真实信号时（离线），--dry-run 应返回 0 且不抛异常。"""
    r = subprocess.run([sys.executable, SCRIPT, "--dry-run"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr


def test_cli_top_n_exits_zero():
    r = subprocess.run([sys.executable, SCRIPT, "--dry-run", "--top-n", "5"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
