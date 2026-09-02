"""历史回填（--backfill-date）单元测试（离线、零网络）。

锁死三条回填纪律：
1. 时点诚实：晋级率 as_of 只递推 ≤ 该日的历史，不偷看未来；
2. 归档不越权：archive_only 只写 snapshots/<date>.json，绝不覆盖今日 daily_snapshot.json；
3. 缺数据不编造：牧羊人无该日行 → 跳过，不硬算。
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import modules.decision as _dec
import modules.decision_track as _track
import modules.shepherd_ladder as _sl
from modules.shepherd_ladder import ladder_promotion_rates


@pytest.fixture
def ladder_file(tmp_path, monkeypatch):
    """3 日梯队历史：D1 → D2 → D3，分布可手算晋级率。"""
    p = tmp_path / "ladder_history.json"
    hist = {
        "2026-08-20": {"date": "2026-08-20", "distribution": {"1": 40, "2": 10},
                       "max_boards": 2, "total_connect": 10},
        "2026-08-21": {"date": "2026-08-21", "distribution": {"1": 50, "2": 5},
                       "max_boards": 2, "total_connect": 5},
        "2026-08-22": {"date": "2026-08-22", "distribution": {"1": 60, "2": 5, "3": 1},
                       "max_boards": 3, "total_connect": 6},
    }
    p.write_text(json.dumps(hist), encoding="utf-8")
    monkeypatch.setattr(_sl, "LADDER_FILE", str(p))
    return p


class TestPromoAsOf:
    def test_as_of_uses_only_history_up_to_date(self, ladder_file):
        """as_of=08-21 → 递推 08-20→08-21；2板晋级率 = 5/40 = 12.5%。"""
        pr = ladder_promotion_rates(as_of="2026-08-21")
        assert pr["ready"] is True
        assert pr["latest_date"] == "2026-08-21"
        assert pr["overall"] == pytest.approx(12.5)

    def test_as_of_latest_matches_default(self, ladder_file):
        """as_of=最后一天 与不传等价（回归保护）。"""
        assert ladder_promotion_rates(as_of="2026-08-22")["overall"] == \
            ladder_promotion_rates()["overall"]

    def test_as_of_before_all_dates_never_crashes(self, ladder_file):
        """as_of 早于所有日期 → 明确 not ready，绝不 IndexError。"""
        pr = ladder_promotion_rates(as_of="2020-01-01")
        assert pr["ready"] is False
        assert pr["overall"] is None
        assert pr["latest"] is None

    def test_all_suspect_history_never_crashes(self, tmp_path, monkeypatch):
        """全部被 mark_suspect 的历史 → not ready，而非 IndexError（顺手修的潜在 bug）。"""
        p = tmp_path / "l2.json"
        p.write_text(json.dumps({
            "2026-08-20": {"date": "2026-08-20", "distribution": {"1": 40, "2": 10},
                           "suspect": True},
        }), encoding="utf-8")
        monkeypatch.setattr(_sl, "LADDER_FILE", str(p))
        pr = ladder_promotion_rates()
        assert pr["ready"] is False
        assert pr["latest"] is None


class TestArchiveOnlySave:
    def test_archive_only_never_touches_latest_snapshot(self, tmp_path, monkeypatch):
        """archive_only=True 只写归档；daily_snapshot.json 不被创建/覆盖。"""
        monkeypatch.setattr(_dec, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(_dec, "SNAPSHOT_PATH", str(tmp_path / "daily_snapshot.json"))
        monkeypatch.setattr(_dec, "ARCHIVE_DIR", str(tmp_path / "snapshots"))
        snap = _dec.build_snapshot("2026-08-21", {"x": 1.0}, 33.0, {}, None, None)
        assert _dec.save_snapshot(snap, archive_only=True) is True
        assert not (tmp_path / "daily_snapshot.json").exists()
        assert (tmp_path / "snapshots" / "2026-08-21.json").exists()

    def test_normal_save_writes_both(self, tmp_path, monkeypatch):
        """默认行为回归：正常落盘 latest + 归档都在。"""
        monkeypatch.setattr(_dec, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(_dec, "SNAPSHOT_PATH", str(tmp_path / "daily_snapshot.json"))
        monkeypatch.setattr(_dec, "ARCHIVE_DIR", str(tmp_path / "snapshots"))
        snap = _dec.build_snapshot("2026-08-21", {"x": 1.0}, 33.0, {}, None, None)
        assert _dec.save_snapshot(snap) is True
        assert (tmp_path / "daily_snapshot.json").exists()
        assert (tmp_path / "snapshots" / "2026-08-21.json").exists()


class TestBackfillPipeline:
    """scripts/daily_snapshot._backfill 全流程（牧羊人/梯队历史/decision 全部桩掉）。"""

    @pytest.fixture
    def script(self):
        # 按绝对路径加载模块对象，彻底绕开 `scripts` 顶层包解析。
        # 根因：venv 的 site-packages/win32/scripts 与本项目 scripts/ 同名，整目录收集时
        # `import scripts` 可能被解析成命名空间包（含 win32/scripts portion，无 daily_snapshot）
        # 并缓存进 sys.modules，导致 `import scripts.daily_snapshot` 偶发 ModuleNotFoundError。
        # 仅 ROOT 置顶 + pop 缓存不足以根治（win32/scripts 仍会被并入 __path__），故改用
        # importlib 按文件路径直加载，与 sys.path 顺序完全解耦，确定性成功。
        import importlib.util
        import pathlib

        ROOT = pathlib.Path(__file__).resolve().parent.parent
        mod_path = ROOT / "scripts" / "daily_snapshot.py"
        spec = importlib.util.spec_from_file_location("scripts.daily_snapshot", str(mod_path))
        _s = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_s)
        return _s

    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_dec, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(_dec, "SNAPSHOT_PATH", str(tmp_path / "daily_snapshot.json"))
        monkeypatch.setattr(_dec, "ARCHIVE_DIR", str(tmp_path / "snapshots"))
        monkeypatch.setattr(_track, "PRED_PATH", str(tmp_path / "prediction_log.json"))
        return tmp_path

    @staticmethod
    def _shepherd_df() -> pd.DataFrame:
        """两日牧羊人指标（含日期列），供切片。"""
        return pd.DataFrame([
            {"date": "2026-08-20", "zt_count": 45.0, "dt_count": 3.0, "up_ratio": 0.6},
            {"date": "2026-08-21", "zt_count": 55.0, "dt_count": 2.0, "up_ratio": 0.7},
        ])

    def test_backfill_writes_archive_and_prediction(self, script, isolated,
                                                    tmp_path, monkeypatch, capsys):
        df = self._shepherd_df()
        monkeypatch.setattr(script, "get_shepherd_indicators",
                            lambda days=60: (df, {}))
        monkeypatch.setattr(script, "shepherd_temperature", lambda ind: 42.0)
        monkeypatch.setattr(script, "_sf", type("SF", (), {
            "forecast_next_day": staticmethod(lambda t, p: {"score": 0.5, "bias": "偏多"}),
        })())
        # 梯队历史只有 08-21 → 08-21 有梯队，08-20 没有
        lp = tmp_path / "ladder_history.json"
        lp.write_text(json.dumps({
            "2026-08-21": {"date": "2026-08-21", "distribution": {"1": 50, "2": 5},
                           "max_boards": 2, "total_connect": 5},
        }), encoding="utf-8")
        monkeypatch.setattr(_sl, "LADDER_FILE", str(lp))

        rc = script._backfill(["2026-08-21", "2026-08-19"], lambda m: print(m))
        out = capsys.readouterr().out
        assert rc == 0
        # 08-21 成功：归档 + 预测都有
        assert (tmp_path / "snapshots" / "2026-08-21.json").exists()
        recs = json.loads((tmp_path / "prediction_log.json").read_text(encoding="utf-8"))
        assert len(recs) == 1 and recs[0]["date"] == "2026-08-21"
        assert recs[0]["pct"] is None or 5 <= recs[0]["pct"] <= 95
        # 今日快照绝不被触碰
        assert not (tmp_path / "daily_snapshot.json").exists()
        # 08-19 无牧羊人行 → 跳过不编造
        assert "2026-08-19" in out and "skip" in out

    def test_backfill_empty_df_fails_cleanly(self, script, isolated, monkeypatch):
        monkeypatch.setattr(script, "get_shepherd_indicators",
                            lambda days=60: (None, {}))
        assert script._backfill(["2026-08-21"], lambda m: None) == 1
