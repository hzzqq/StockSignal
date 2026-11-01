"""tests/test_p1_signal_quality.py —— P1 信号数据质量体检模块单测（方向 3）。

零网络、零真实数据依赖：全部用 tmp_path 构造信号文件，不断言线上真实文件，
避免把真实数据滞后状态固化进测试（真实体检由 scripts/p1_signal_quality_report.py 输出）。
"""
from __future__ import annotations

import json
from datetime import date

from modules import p1_signal_quality as q


def _write_signal(d, name: str, payload: dict):
    p = d / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _healthy_payload(latest: str = "2026-10-26", n: int = 20) -> dict:
    top_long = [{"symbol": f"sh60{i:04d}", "pred": 1.0 - i * 0.01, "rank": 1.0 - i / 100.0}
                for i in range(n)]
    top_short = [{"symbol": f"sz60{i:04d}", "pred": -0.5 - i * 0.01, "rank": 0.01 + i / 100.0}
                 for i in range(min(n, 10))]
    return {
        "model": "ev", "latest_date": latest, "horizon": 10,
        "top_long": top_long, "top_short": top_short,
        "daily": [{"date": "2026-10-26", "symbol": "sh600001", "score": 0.1, "signal": "看多"}],
    }


TODAY = date(2026, 11, 1)


# ───────────────────────── 模型键提取 ─────────────────────────
class TestExtractModelKey:
    def test_plain(self):
        assert q.extract_model_key("signal_ev_h10.json") == "ev"
        assert q.extract_model_key("signal_baseline_h10.json") == "baseline"

    def test_ens_long_prefix(self):
        assert q.extract_model_key("signal_ens_v39gru_w025_h10.json") == "ens"

    def test_fusion(self):
        assert q.extract_model_key("signal_fusion_h10.json") == "fusion"

    def test_non_signal_returns_none(self):
        assert q.extract_model_key("README.md") is None
        assert q.extract_model_key("signal_ev_h10.json.bak") is None


# ───────────────────────── 符号格式 ─────────────────────────
class TestSymbol:
    def test_valid(self):
        assert q.is_valid_symbol("sh600176") and q.is_valid_symbol("sz000001") and q.is_valid_symbol("bj430047")

    def test_invalid(self):
        for bad in ("600176", "SH600176", "sh60017", "sh600176x", "", None):
            assert not q.is_valid_symbol(bad), f"{bad!r} 应非法"


# ───────────────────────── 滞后天数 ─────────────────────────
class TestAgeDays:
    def test_normal(self):
        assert q.age_days("2026-10-26", TODAY) == 6

    def test_iso_with_time_takes_date_part(self):
        assert q.age_days("2026-10-26 17:17:05", TODAY) == 6

    def test_bad_returns_none(self):
        for bad in (None, "", "unknown", "2026/10/26", 123):
            assert q.age_days(bad, TODAY) is None

    def test_future_clamped_zero(self):
        assert q.age_days("2026-11-10", TODAY) == 0


# ───────────────────────── 单文件体检 ─────────────────────────
class TestCheckFile:
    def test_healthy(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload())
        rec = q.check_file(p, model_key="ev", today=TODAY)
        assert rec["ok"] is True and rec["freshness_ok"] is True
        assert rec["n_top_long"] == 20 and rec["n_daily"] == 1
        assert rec["errors"] == []

    def test_missing_file(self, tmp_path):
        rec = q.check_file(str(tmp_path / "nope.json"), model_key="ev")
        assert rec["ok"] is False and "不存在" in rec["errors"][0]

    def test_corrupt_json(self, tmp_path):
        p = tmp_path / "signal_ev_h10.json"
        p.write_text("{not valid json", encoding="utf-8")
        rec = q.check_file(str(p), model_key="ev")
        assert rec["ok"] is False and "JSON 解析失败" in rec["errors"][0]

    def test_missing_keys(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", {"model": "ev", "top_long": []})
        rec = q.check_file(p, model_key="ev", today=TODAY)
        assert rec["missing_keys"] and "缺字段" in rec["errors"][0]

    def test_bad_latest_date(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="not-a-date"))
        rec = q.check_file(p, model_key="ev", today=TODAY)
        assert rec["age_days"] is None and rec["ok"] is False

    def test_stale_exceeds_sla(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="2026-10-01"))
        rec = q.check_file(p, model_key="ev", today=TODAY)  # age=31 > 8
        assert rec["age_days"] == 31 and rec["freshness_ok"] is False and rec["ok"] is False

    def test_fresh_within_sla(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="2026-10-28"))
        rec = q.check_file(p, model_key="ev", today=TODAY)  # age=4 ≤ 8
        assert rec["freshness_ok"] is True and rec["ok"] is True

    def test_custom_max_age_overrides(self, tmp_path):
        p = _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="2026-10-26"))
        rec = q.check_file(p, model_key="ev", today=TODAY, max_age=2)  # age=6 > 2
        assert rec["freshness_ok"] is False

    def test_bad_symbol_format(self, tmp_path):
        payload = _healthy_payload()
        payload["top_long"] = [{"symbol": "600176", "pred": 1.0, "rank": 1.0}]
        p = _write_signal(tmp_path, "signal_ev_h10.json", payload)
        rec = q.check_file(p, model_key="ev", today=TODAY)
        assert rec["symbol_ok"] is False and rec["ok"] is False

    def test_rank_not_monotonic(self, tmp_path):
        payload = _healthy_payload()
        payload["top_long"] = [
            {"symbol": "sh600001", "pred": 1.0, "rank": 0.5},
            {"symbol": "sh600002", "pred": 0.9, "rank": 0.9},  # 升序 → 非单调
        ]
        p = _write_signal(tmp_path, "signal_ev_h10.json", payload)
        rec = q.check_file(p, model_key="ev", today=TODAY)
        assert rec["rank_ok"] is False and rec["ok"] is False


# ───────────────────────── Jaccard 数学 ─────────────────────────
class TestJaccard:
    def test_identical(self):
        assert q.jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint(self):
        assert q.jaccard(["a", "b"], ["c", "d"]) == 0.0

    def test_partial(self):
        assert abs(q.jaccard(["a", "b", "c"], ["b", "c", "d"]) - 2 / 4) < 1e-12

    def test_both_empty(self):
        assert q.jaccard([], []) == 0.0


# ───────────────────────── ens↔baseline 对齐守望 ─────────────────────────
class TestAlignment:
    def test_high_overlap_aligned(self, tmp_path):
        ens = _write_signal(tmp_path, "signal_ens_v39gru_w025_h10.json", _healthy_payload())
        base = _write_signal(tmp_path, "signal_baseline_h10.json", _healthy_payload())
        al = q.check_ens_baseline_alignment(ens, base, min_jaccard=0.5)
        assert al["aligned"] is True and al["status"] == "ok" and al["ok"] is True

    def test_low_overlap_yellow(self, tmp_path):
        ens_payload = _healthy_payload()
        base_payload = _healthy_payload()
        base_payload["top_long"] = [{"symbol": f"sz{i:06d}", "pred": 1.0, "rank": 1.0 - i / 100.0}
                                    for i in range(20)]
        ens = _write_signal(tmp_path, "signal_ens_v39gru_w025_h10.json", ens_payload)
        base = _write_signal(tmp_path, "signal_baseline_h10.json", base_payload)
        al = q.check_ens_baseline_alignment(ens, base, min_jaccard=0.75)
        assert al["aligned"] is False and al["ok"] is True, "黄灯不阻断"
        assert "黄灯" in al["note"]

    def test_missing_baseline_unavailable(self, tmp_path):
        ens = _write_signal(tmp_path, "signal_ens_v39gru_w025_h10.json", _healthy_payload())
        al = q.check_ens_baseline_alignment(ens, str(tmp_path / "nope.json"))
        assert al["status"] == "unavailable"


# ───────────────────────── 目录汇总 ─────────────────────────
class TestSummarize:
    def test_all_green(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload())
        _write_signal(tmp_path, "signal_baseline_h10.json", _healthy_payload())
        _write_signal(tmp_path, "signal_ens_v39gru_w025_h10.json", _healthy_payload())
        s = q.summarize(str(tmp_path), today=TODAY)
        assert s["ok_all"] is True and s["models_found"] == ["baseline", "ens", "ev"]
        assert s["alignment"] is not None and s["alignment"]["aligned"] is True

    def test_stale_red(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="2026-10-01"))
        s = q.summarize(str(tmp_path), today=TODAY)
        assert s["ok_all"] is False

    def test_bak_skipped(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json.bak_20261030", _healthy_payload())
        s = q.summarize(str(tmp_path), today=TODAY)
        assert s["models_found"] == [] and s["ok_all"] is True, ".bak 不应参与体检"

    def test_non_signal_ignored(self, tmp_path):
        _write_signal(tmp_path, "README.md", {"x": 1})
        s = q.summarize(str(tmp_path), today=TODAY)
        assert s["models_found"] == [] and s["ok_all"] is True

    def test_max_age_override(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload(latest="2026-10-26"))
        s = q.summarize(str(tmp_path), today=TODAY, max_age_by_model={"ev": 2})
        assert s["ok_all"] is False, "覆盖阈值后 6 天应红灯"


# ───────────────────────── 推送链心跳体检 ─────────────────────────
def _ts_days_ago(days_ago: int) -> float:
    from datetime import datetime, timedelta
    return (datetime.combine(TODAY, datetime.min.time()) - timedelta(days=days_ago)).timestamp()


class TestHeartbeat:
    def _hb(self, tmp_path, body: str, mtime_days_ago: int = 0) -> str:
        p = tmp_path / "heartbeat.log"
        p.write_text(body, encoding="utf-8")
        if mtime_days_ago:
            import os as _os
            t = _ts_days_ago(mtime_days_ago)
            _os.utime(str(p), (t, t))
        return str(p)

    def test_healthy(self, tmp_path):
        p = self._hb(tmp_path, "2026-11-01 08:00:00 OK S13\n")
        rec = q.check_heartbeat(p, today=TODAY, max_idle_days=3)
        assert rec["ok"] is True and rec["last_ok"] is True and rec["idle_ok"] is True

    def test_missing_file(self, tmp_path):
        rec = q.check_heartbeat(str(tmp_path / "nope.log"), today=TODAY)
        assert rec["ok"] is False and "不存在" in rec["errors"][0]

    def test_last_line_no_ok(self, tmp_path):
        p = self._hb(tmp_path, "2026-10-31 00:00:50 FAIL S09\n")
        rec = q.check_heartbeat(p, today=TODAY, max_idle_days=3)
        assert rec["ok"] is False and "无 OK 标记" in rec["errors"][0]

    def test_stale_idle_exceeds(self, tmp_path):
        p = self._hb(tmp_path, "2026-10-26 00:00:00 OK S13\n", mtime_days_ago=6)
        rec = q.check_heartbeat(p, today=TODAY, max_idle_days=3)
        assert rec["idle_days"] == 6 and rec["idle_ok"] is False and rec["ok"] is False

    def test_idle_within(self, tmp_path):
        p = self._hb(tmp_path, "2026-10-31 00:00:50 OK S13\n", mtime_days_ago=1)
        rec = q.check_heartbeat(p, today=TODAY, max_idle_days=3)
        assert rec["idle_days"] == 1 and rec["idle_ok"] is True and rec["ok"] is True

    def test_summarize_includes_heartbeat(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload())
        hb = tmp_path / "heartbeat.log"
        hb.write_text("2026-11-01 08:00:00 OK S13\n", encoding="utf-8")
        s = q.summarize(str(tmp_path), today=TODAY, heartbeat_path=str(hb))
        assert s["heartbeat"] is not None and s["heartbeat"]["ok"] is True and s["ok_all"] is True

    def test_summarize_heartbeat_stale_red(self, tmp_path):
        hb = tmp_path / "heartbeat.log"
        hb.write_text("2026-10-20 00:00:00 OK S13\n", encoding="utf-8")
        t = _ts_days_ago(12)
        import os as _os
        _os.utime(str(hb), (t, t))
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload())
        s = q.summarize(str(tmp_path), today=TODAY, heartbeat_path=str(hb))
        assert s["ok_all"] is False and "心跳" in q.render_report(s)


# ───────────────────────── 报告渲染 ─────────────────────────
class TestRender:
    def test_render_contains_rows_and_conclusion(self, tmp_path):
        _write_signal(tmp_path, "signal_ev_h10.json", _healthy_payload())
        s = q.summarize(str(tmp_path), today=TODAY)
        text = q.render_report(s)
        assert "P1 信号数据质量体检" in text and "全绿" in text and "signal_ev_h10.json" in text
