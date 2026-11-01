# -*- coding: utf-8 -*-
"""tests/test_decision_model_adj.py — 毕设三算法诚实证据桥（model_adj）守卫。

锁四条不变量（诚实红线）：
1. live=False（P1_RESULTS_DIR 未配置/无外部结果）→ model_adj 对仓位贡献为 0，
   reasons 显式留痕「不施加」——离线锚定不冒充实时信号；
2. live=True 且 #1 modest 正向 → 仓位获得**有界**小正 Δ（≤ MODEL_ADJ_CAP_PP）；
3. #2 GNN / #3 RL 负向 → **任何情况下不产生负向仓位 Δ**，只在 reasons 留痕
   「仅记录不施加」；
4. model_adj 修正不绕过下游封顶——极端风控/状态门控/新鲜度封顶仍凌驾其上。
"""
import pytest

import modules.decision as decision


# ───────────────────────── _thesis_model_adj 单元 ─────────────────────────

def test_thesis_bridge_offline_by_default(monkeypatch):
    """不变量1：无证据目录 → adj=0、live=False、留痕显式「不施加」。

    机器状态隔离：本机真实 P1 processed 目录存在且含 experiment_findings.json
    （live 链路实测已通），必须显式断开目录发现，单元测试才不依赖机器状态。
    """
    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "discover_findings_dir", lambda: ["D:/nonexistent_stub_dir"])
    monkeypatch.delenv("P1_RESULTS_DIR", raising=False)
    out = decision._thesis_model_adj()
    assert out["adj"] == 0.0
    assert out["live"] is False
    joined = "\n".join(out["lines"])
    assert "离线锚定" in joined and "不施加" in joined
    assert "仅记录不施加" in joined  # #2/#3 留痕
    assert "0.4948" in joined, "#2 GNN 负向数字必须如实留痕"
    assert "-0.741" in joined, "#3 RL 负向 Sharpe 必须如实留痕"


def test_thesis_bridge_live_modest_edge_bounded(monkeypatch):
    """不变量2：live=True 且 #1 modest 正向（+0.33pp）→ 有界小正 Δ。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision._thesis_model_adj()
    assert out["live"] is True
    assert 0 < out["adj"] <= decision.MODEL_ADJ_CAP_PP
    # KNOWN 锚定边沿 = (0.5130-0.5097)*100 = 0.33pp
    assert abs(out["adj"] - 0.33) < 1e-9
    assert "有界加仓" in "\n".join(out["lines"])


def test_thesis_bridge_live_edge_capped_at_3pp(monkeypatch):
    """不变量2：即使实时证据边沿巨大（如 10pp），修正也封顶 ≤3pt。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["transformer_signal"]["direction_hit"] = 0.6097  # 边沿 +10pp
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision._thesis_model_adj()
    assert out["adj"] == decision.MODEL_ADJ_CAP_PP


def test_thesis_bridge_negative_findings_never_apply(monkeypatch):
    """不变量3：#2/#3 负向 → adj 恒 0，绝不因负向发现减仓（记录≠动作）。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["transformer_signal"]["direction_hit"] = 0.5097  # 边沿 = 0，无正向
        data["gnn_factor"]["direction_hit"] = 0.30  # 深度负向
        data["rl_position"]["sharpe"] = -2.0  # 深度负向
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision._thesis_model_adj()
    assert out["adj"] == 0.0
    joined = "\n".join(out["lines"])
    assert "仅记录不施加" in joined


def test_thesis_bridge_fault_degrades_gracefully(monkeypatch):
    """桥故障（导入/读取异常）→ 降级未接入、贡献 0、不崩决策环。"""
    import modules.experiment_improvements as ei

    def boom(results_dir=None):
        raise RuntimeError("stub bridge failure")

    monkeypatch.setattr(ei, "load_live_findings", boom)
    out = decision._thesis_model_adj()
    assert out["adj"] == 0.0 and out["live"] is False
    assert "桥故障" in "\n".join(out["lines"])


# ───────────────────────── derive_position 集成 ─────────────────────────

def test_derive_position_offline_unchanged_pct(monkeypatch):
    """不变量1（集成）：离线默认下 pct 与纯规则推导完全一致（model_adj 贡献 0）。"""
    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "discover_findings_dir", lambda: ["D:/nonexistent_stub_dir"])
    monkeypatch.delenv("P1_RESULTS_DIR", raising=False)
    out = decision.derive_position(temp=50, bias="偏多")
    # 50 + 方向偏多 8 = 58；离线 model_adj 不加不减
    assert out["pct"] == 58
    joined = "\n".join(out["reasons"])
    assert "不施加" in joined


def test_derive_position_live_gains_bounded_delta(monkeypatch):
    """不变量2（集成）：live #1 边沿 → pct 有界抬升（58 → 58+0.33 ≈ 58）。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision.derive_position(temp=50, bias="偏多", explain=True)
    # modest 边沿 0.33pp 在 int(round()) 后不落整（58.33→58）——有界小步长的诚实体现；
    # 修正本身必须经 contributions 留痕可审计
    assert out["pct"] == 58
    deltas = [c["delta"] for c in out["contributions"]
              if c["factor"] == "毕设#1 模型边沿(model_adj)"]
    assert deltas and 0 < deltas[0] <= decision.MODEL_ADJ_CAP_PP
    assert abs(deltas[0] - 0.33) < 1e-9
    assert out["pct"] >= 58  # 绝不因 modest 正向证据而减仓


def test_model_adj_cannot_escape_freshness_cap(monkeypatch):
    """不变量4：model_adj 不绕过新鲜度封顶——stale 输入下仍封顶 40%。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["transformer_signal"]["direction_hit"] = 0.6097  # +10pp → 封顶 3pt
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision.derive_position(temp=90, bias="偏多", freshness_status="stale")
    assert out["pct"] == int(round(decision.FRESHNESS_CAPS["stale"])), (
        "model_adj 修正不得绕过数据陈旧封顶"
    )


def test_model_adj_cannot_escape_regime_cap(monkeypatch):
    """不变量4：model_adj 不绕过状态门控——暴跌封顶 50% 仍生效。"""
    import modules.experiment_improvements as ei

    def fake_live(results_dir=None):
        data = ei.get_known_findings()
        data["transformer_signal"]["direction_hit"] = 0.6097
        data["_meta"] = {"live": True, "sources": ["stub"]}
        return data

    monkeypatch.setattr(ei, "load_live_findings", fake_live)
    out = decision.derive_position(temp=80, bias="偏多",
                                   regime_state="暴跌", regime_confidence=0.9)
    assert out["pct"] <= int(decision.REGIME_CAPS["暴跌"])


# ───────────────────────── 证据目录发现 + 真实文件 live 链路 ─────────────────────────

def test_discover_findings_dir_env_priority(monkeypatch):
    """P1_FINDINGS_DIR 最高优先；fallback 可被 P1_FINDINGS_FALLBACK_DIR 覆盖；去重保序。"""
    import modules.p1_signal as p1
    monkeypatch.setenv("P1_FINDINGS_DIR", "D:/stub/findings")
    monkeypatch.delenv("P1_FINDINGS_FALLBACK_DIR", raising=False)
    dirs = p1.discover_findings_dir()
    assert dirs[0] == "D:/stub/findings"
    assert len(dirs) == 2  # env + 默认 fallback
    monkeypatch.setenv("P1_FINDINGS_FALLBACK_DIR", "D:/stub/fb")
    dirs2 = p1.discover_findings_dir()
    assert dirs2[1] == "D:/stub/fb"
    monkeypatch.setenv("P1_FINDINGS_DIR", "D:/stub/fb")  # 与 fallback 相同 → 去重
    assert len(p1.discover_findings_dir()) == 1


def test_live_chain_via_real_findings_file(monkeypatch, tmp_path):
    """端到端：P1 导出的 experiment_findings.json 被 decision 桥读成 live=True。

    用真实 schema（load_live_findings 消费格式）在 tmp 造文件——数字用 KNOWN 锚定值，
    证明「文件存在→live→有界施加」链路，而非 mock 桥函数本身。
    """
    import json
    import modules.experiment_improvements as ei

    findings = ei.get_known_findings()  # 数字=KNOWN 锚定真值
    findings.pop("_meta", None)
    (tmp_path / "experiment_findings.json").write_text(
        json.dumps(findings, ensure_ascii=False), encoding="utf-8")

    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "discover_findings_dir", lambda: [str(tmp_path)])
    monkeypatch.delenv("P1_RESULTS_DIR", raising=False)

    out = decision.derive_position(temp=50, bias="偏多", explain=True)
    deltas = [c["delta"] for c in out["contributions"]
              if c["factor"] == "毕设#1 模型边沿(model_adj)"]
    assert deltas and abs(deltas[0] - 0.33) < 1e-9, "live 证据文件必须被桥读成 +0.33pp 有界修正"
    assert any("有界加仓" in r for r in out["reasons"])


def test_live_chain_missing_dir_degrades_offline(monkeypatch):
    """发现目录都不存在 → results_dir=None → live=False 离线锚定（不崩、不编造）。"""
    import modules.p1_signal as p1
    monkeypatch.setattr(p1, "discover_findings_dir", lambda: ["D:/nonexistent_stub_dir"])
    monkeypatch.delenv("P1_RESULTS_DIR", raising=False)
    out = decision._thesis_model_adj()
    assert out["adj"] == 0.0 and out["live"] is False
    assert "离线锚定" in "\n".join(out["lines"])
