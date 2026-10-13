"""
tests/test_source_metrics_persist.py
====================================
T-273D：数据源/缓存层指标长周期落盘——快照幂等 / 趋势汇总 / 坏文件容错 /
诚实语义（缺失日不插值）+ 调度链与 82 页接线守卫。
"""
import json
from pathlib import Path

from modules import source_metrics_persist as smp

_PROJECT = Path(__file__).resolve().parents[1]


def _seed_obs(tmp_path: Path, day: str, payload: dict):
    d = tmp_path / "health_observations"
    d.mkdir(exist_ok=True)
    (d / f"source_metrics_{day}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sample(day: str, rate: float):
    return {"date": day, "saved_at": f"{day} 15:30:00", "process_hint": "app.py",
            "source_metrics": {"sina": {"calls": 10, "success": 8,
                                        "success_rate": rate, "avg_latency_ms": 1.0,
                                        "last_error": None}},
            "cache_metrics": {"L0": {"hits": 80, "misses": 20, "calls": 100,
                                     "hit_rate": 0.8}}}


def test_snapshot_writes_and_idempotent(tmp_path, monkeypatch):
    """快照落盘：同日重复调用覆盖（幂等），文件结构完整。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    r1 = smp.snapshot_metrics_to_disk()
    r2 = smp.snapshot_metrics_to_disk()
    assert r1["ok"] and r2["ok"], f"落盘失败: {r1['note']} / {r2['note']}"
    p = tmp_path / "health_observations"
    files = list(p.glob("source_metrics_*.json"))
    assert len(files) == 1, "同日快照应幂等覆盖为单文件"
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert "source_metrics" in data and "cache_metrics" in data
    assert data["process_hint"], "process_hint（仅本进程口径）必须如实记录"


def test_trend_reads_series_and_marks_missing(tmp_path, monkeypatch):
    """趋势汇总：逐日拼接 + 缺失日如实列入 missing_days（不插值）。"""
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    _seed_obs(tmp_path, "2026-10-11", _sample("2026-10-11", 0.7))
    _seed_obs(tmp_path, "2026-10-13", _sample("2026-10-13", 0.9))
    tr = smp.metrics_trend(days=7)
    assert "2026-10-11" in tr["days_available"] and "2026-10-13" in tr["days_available"]
    assert tr["missing_days"], "无快照日应如实列入 missing_days"
    series = tr["source_trend"]["sina"]
    assert [p["success_rate"] for p in series] == [0.7, 0.9], "成功率时间序列按日拼接"
    assert tr["cache_trend"]["L0"][0]["hit_rate"] == 0.8
    # 缺失日绝不编造数据点：序列长度 == 有快照天数
    assert len(series) == len(tr["days_available"])


def test_trend_skips_corrupt_files(tmp_path, monkeypatch):
    """坏文件容错跳过、合法空结构进 found，绝不抛错、绝不编造（时钟相对）。"""
    from datetime import datetime, timedelta
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path))
    today = datetime.now().strftime("%Y-%m-%d")
    yday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    d2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    d = tmp_path / "health_observations"
    d.mkdir(exist_ok=True)
    (d / f"source_metrics_{d2}.json").write_text("{corrupt!!", encoding="utf-8")  # 坏文件 → missing
    _seed_obs(tmp_path, yday, {"date": yday})  # 合法结构但无指标 → found、趋势为空
    tr = smp.metrics_trend(days=3)
    assert tr["source_trend"] == {} and tr["cache_trend"] == {}
    assert d2 in tr["missing_days"] and today in tr["missing_days"], \
        f"坏文件日/无文件日应计入缺失: {tr['missing_days']}"
    assert yday in tr["days_available"], "合法空结构快照属 found（不假装有指标数据）"


def test_scheduler_wiring_persists_snapshot():
    """调度链接线守卫：_warm_once 落盘调用不回退（T-273D 每日快照来源）。"""
    src = (_PROJECT / "backend" / "recommend_scheduler.py").read_text(encoding="utf-8")
    assert "snapshot_metrics_to_disk" in src, "调度链指标快照落盘接线被删（T-273D 回潮）"
    assert "T-273D" in src


def test_page82_trend_section_wiring():
    """82 页趋势区接线守卫（additive 展示不回退）。"""
    src = (_PROJECT / "pages" / "82_数据时效性看板.py").read_text(encoding="utf-8")
    assert "metrics_trend" in src, "82 页缺少 7 日趋势接线"
    assert "缺失日（无快照，不插值）" in src, "趋势展示必须保留缺失日诚实口径"
