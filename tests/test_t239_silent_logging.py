"""T-239 round1 守卫：取数层静默点补 logger.warning 留痕（运行时 + 源码落地双保险）。

覆盖：
- data_health：_csv_last_date_col / _json_date_field / _mtime_date 读取失败必须 logger.warning
  （运行时 caplog 验证，避免「源故障被误读为无数据 / 假新鲜」）
- event_factor / p1_signal / shepherd_ladder 关键静默点已补留痕（源码文本断言，确保改动落地、不静默回退）
- pages/54 已挂 render_data_degradation_banner（G1 缺口补齐）
"""
import importlib
import logging
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mod(name):
    return importlib.import_module(name)


def test_csv_last_date_col_logs_on_read_error(caplog):
    dh = _mod("modules.data_health")
    with caplog.at_level(logging.WARNING, logger="modules.data_health"):
        # ROOT 是目录，open() 会抛 IsADirectoryError -> 必须留痕而非静默 return None
        dh._csv_last_date_col(str(ROOT))
    assert any("CSV" in r.message for r in caplog.records), caplog.text


def test_json_date_field_logs_on_read_error(caplog, tmp_path):
    dh = _mod("modules.data_health")
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="modules.data_health"):
        dh._json_date_field(str(bad), "date")
    assert any("JSON" in r.message for r in caplog.records), caplog.text


def test_mtime_date_logs_on_error(monkeypatch, caplog, tmp_path):
    dh = _mod("modules.data_health")
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        os.path, "getmtime", lambda p: (_ for _ in ()).throw(OSError("boom"))
    )
    with caplog.at_level(logging.WARNING, logger="modules.data_health"):
        dh._mtime_date(str(f))
    assert any("mtime" in r.message for r in caplog.records), caplog.text


def test_event_factor_silent_points_logged():
    src = (ROOT / "modules" / "event_factor.py").read_text(encoding="utf-8")
    assert "[event_factor] top_long/top_short 读取异常" in src
    assert "[event_factor] daily_df 读取失败" in src


def test_p1_signal_silent_points_logged():
    src = (ROOT / "modules" / "p1_signal.py").read_text(encoding="utf-8")
    assert "P1 信号文件解析失败，跳过" in src
    assert "P1 模型 %s 摘要加载失败" in src
    # 警告必须有归属 logger，否则不生效
    assert "logger = logging.getLogger(__name__)" in src


def test_shepherd_ladder_bad_key_logged():
    src = (ROOT / "modules" / "shepherd_ladder.py").read_text(encoding="utf-8")
    assert "[shepherd_ladder] 坏档位 key 丢弃" in src


def test_page54_degradation_banner_mounted():
    src = (ROOT / "pages" / "54_今日决策面板.py").read_text(encoding="utf-8")
    assert "from modules.page_guard import safe_fragment, render_data_degradation_banner" in src
    assert "render_data_degradation_banner()" in src
