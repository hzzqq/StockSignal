"""T-245 二道闸守卫：modules.risk_gate 通用排雷逻辑。

覆盖：
- to_6digit 代码形态规整
- apply_risk_gate：high 硬踢出、unknown≠guilty 保留、scan_map 空如实降级不阻塞
- scan_and_gate：封装扫描 + 还原原始代码 + 拦截原因
- 4 个即席出口（55/76/32/81）已挂接 scan_and_gate
- recommend_engine 已上提复用（去重，行为一致）
"""
import importlib
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

rg = importlib.import_module("modules.risk_gate")
sr = importlib.import_module("modules.stock_risk")


def test_to_6digit():
    assert rg.to_6digit("sh600869") == "600869"
    assert rg.to_6digit("600869.SH") == "600869"
    assert rg.to_6digit("600869") == "600869"
    assert rg.to_6digit("000001") == "000001"
    assert rg.to_6digit("") == ""
    assert rg.to_6digit(None) == ""


def _fake_scan(code: str, high: bool) -> dict:
    comps = {}
    for key, _cn, _u in sr.DIMENSIONS:
        is_high = high and key == "st"
        comps[key] = {
            "level": sr.RISK_HIGH if is_high else sr.RISK_UNKNOWN,
            "note": "ST警示" if is_high else "",
            "value": None,
        }
    return {"code": code, "name": "测试" + code, "components": comps,
            "report": sr.build_risk_report(comps), "errors": []}


def test_apply_risk_gate_kicks_high():
    scan_map = {
        "600001": _fake_scan("600001", True),
        "600002": _fake_scan("600002", True),
        "600003": _fake_scan("600003", False),
    }
    rows = [{"code": "600001", "name": "A"},
            {"code": "600002", "name": "B"},
            {"code": "600003", "name": "C"}]
    gated, summary = rg.apply_risk_gate(rows, scan_map, top_k=3, gate_n=3)
    assert summary["status"] == "ok"
    assert {k["code"] for k in summary["kicked"]} == {"600001", "600002"}
    # unknown≠guilty：600003 保留，承载 risk_scan 元数据
    kept = [r for r in gated if r["code"] == "600003"]
    assert kept and kept[0]["risk_scan"]["status"] == "scanned"
    assert kept[0]["risk_scan"]["reliable"] is False  # 含 unknown 维度 -> 不可靠


def test_apply_risk_gate_empty_scanmap_degrades():
    rows = [{"code": "600001", "name": "A"}]
    gated, summary = rg.apply_risk_gate(rows, {}, top_k=1, gate_n=1)
    assert summary["status"] == "unavailable"
    assert summary["kicked"] == []
    assert gated[0]["risk_scan"]["status"] == "not_scanned"  # 如实降级，不阻塞


def test_scan_and_gate_restores_code_and_reasons(monkeypatch):
    def fake_scan(items):
        out = []
        for code, name in items:
            out.append(_fake_scan(code, high=(code == "600001")))
        return out

    monkeypatch.setattr(rg, "_scan_many", fake_scan)
    cands = [{"code": "sh600001", "name": "A"}, {"code": "600002", "name": "B"}]
    gated, summary = rg.scan_and_gate(cands, top_k=2)
    # sh600001 -> 600001 high -> 踢出，但 code 还原为原始形态
    assert {k["code"] for k in summary["kicked"]} == {"sh600001"}
    assert len(gated) == 1
    assert gated[0]["code"] == "600002"


def test_pages_hook_risk_gate():
    for p in ("55_P1量化信号", "76_实时强势榜", "32_智能选股", "81_自然语言选股"):
        src = (ROOT / "pages" / f"{p}.py").read_text(encoding="utf-8")
        assert "scan_and_gate" in src, f"{p} 未挂接二道闸"
    # 76 页自动刷新，必须缓存扫描结果（否则 60s 刷新触发上百次网络调用）
    src76 = (ROOT / "pages" / "76_实时强势榜.py").read_text(encoding="utf-8")
    assert "_gate_strong_summary" in src76 and "cache_data" in src76


def test_recommend_engine_reuses_risk_gate():
    rec = importlib.import_module("modules.recommend_engine")
    assert rec.apply_risk_gate is rg.apply_risk_gate
