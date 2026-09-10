"""tests/test_sentiment_edge.py

情绪「有统计依据的极值信号层」守卫（2026-09-10）。

背景（老板反馈「项目还是没做到准确预测情绪」，于是做了实证）
------------------------------------------------------------
``scripts/analyze_sentiment_predictive_power.py`` 把 2009–2026 的 4094 天逐日喂给
``forecast_next_day``，得到三个必须写进代码的结论：

  1. **方向不可预测**：偏多 n=296 次日上涨 48.3%（基准 46.5%，z=+0.61）；偏空 n=128
     上涨 53.9%（z=+1.67）；5 日尺度偏多 38.6% vs 基准 38.6%（z=+0.03）。
     0-100「次日情绪评分」与次日收益 IC=**-0.031**（负），十分位单调性 IC≈0.02。
  2. **手工家数阈值死于量纲**：历史基座是逐年长大的**采样**（2009 年 26 只 → 2025 年
     1669 只），"跌停>100家" 触发率 0.32%（n=5）、"涨停≥80家" 0.52%（n=8）——
     写了但从不生效。故新层**只用尺度无关的占比类特征**。
  3. **唯一经样本外 + Bonferroni 校正活下来的规律**：极端恐慌 → 次日反弹
     （walk-forward：跌停占比前10% 触发 78 天 66.7% vs 46.5% z=+3.57；
                  触及跌停占比前10% 触发 65 天 63.1% vs 46.5% z=+2.68）。

本文件锁死：尺度无关、无未来信息、只在有依据时表态、缺失时优雅降级。
"""
import ast
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from modules import sentiment_edge as se          # noqa: E402
from modules import shepherd_forecast as sf        # noqa: E402

CAL_PATH = os.path.join(ROOT, "data", "sentiment_edge_calibration.json")
CAL_SCRIPT = os.path.join(ROOT, "scripts", "calibrate_sentiment_edge.py")


def _cal(features, base=0.4651):
    return dict(
        generated_at="2026-09-10 00:00:00", method="walk-forward", warmup=500,
        quantile=0.9, min_trigger_samples=20, base_next_day_up_rate=base,
        date_range=["2020-04-20", "2026-09-02"], features=features,
        strength_ic={"touch_down_ratio": 0.1556},
    )


def _feat(key, thr, pub=True, up_rate=0.667, n=78, z=3.57):
    return {key: dict(
        key=key, name=key, how="ratio", sign="high", expected_direction="up",
        why="panic reversal", production_threshold=thr, publishable=pub,
        walk_forward=dict(trigger_days=n, up_days=int(up_rate * n), up_rate=up_rate,
                          base_rate=0.4651, mean_next_day=0.9, z=z, p=0.0004,
                          significant=True),
    )}


@pytest.fixture
def cal_file(tmp_path, monkeypatch):
    """写出临时校准件并把环境变量指过去（避免污染真实 data/）。"""
    def _write(payload):
        p = tmp_path / f"cal_{len(list(tmp_path.iterdir()))}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv(se.ENV_PATH, str(p))
        return p
    return _write


# ── 1. 优雅降级 ─────────────────────────────────────────────────

def test_missing_calibration_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv(se.ENV_PATH, str(tmp_path / "nope.json"))
    r = se.panic_reversal({"limit_down": 90, "up_count": 100, "down_count": 1500})
    assert r["available"] is False
    assert r["triggered"] is False
    assert r["abstain"] is True
    assert "校准件" in r["reason"] or "不存在" in r["reason"]
    assert r["statement"]


def test_malformed_calibration_does_not_raise(tmp_path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(se.ENV_PATH, str(p))
    r = se.panic_reversal({"limit_down": 90})
    assert r["available"] is False
    assert r["abstain"] is True


def test_calibration_without_features_key_rejected(tmp_path, monkeypatch):
    p = tmp_path / "nofeat.json"
    p.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    monkeypatch.setenv(se.ENV_PATH, str(p))
    assert se.load_calibration()["available"] is False


# ── 2. 数值安全：缺失不得被当成 0（0 会造成假触发/假安全）────────

def test_num_rejects_missing_and_nan():
    assert se._num({}, "k") is None
    assert se._num({"k": None}, "k") is None
    assert se._num({"k": "abc"}, "k") is None
    assert se._num({"k": float("nan")}, "k") is None
    assert se._num({"k": 0.0}, "k") == 0.0          # 真 0 是有效值
    assert se._num({"k": "3.5"}, "k") == 3.5


def test_day_sample_requires_positive():
    assert se.day_sample({"up_count": 100, "down_count": 200, "flat_count": 0}) == 300
    assert se.day_sample({"up_count": 0, "down_count": 0, "flat_count": 0}) is None
    assert se.day_sample({}) is None


def test_ratios_are_scale_invariant():
    """占比必须与采样规模无关：同样的比例、10 倍样本量 → 同样的占比。"""
    small = {"up_count": 80, "down_count": 90, "flat_count": 10,
             "limit_down": 8, "touch_down": 12}
    big = {"up_count": 800, "down_count": 900, "flat_count": 100,
           "limit_down": 80, "touch_down": 120}
    r1, r2 = se.ratios(small), se.ratios(big)
    assert r1 and r2
    for k in r1:
        assert r1[k] == pytest.approx(r2[k], rel=1e-9), f"{k} 未随样本规模保持不变"


def test_ratios_without_sample_returns_empty():
    assert se.ratios({"limit_down": 5}) == {}


# ── 3. 只在极值区表态 / 其余弃权 ─────────────────────────────────

def test_trigger_on_extreme_panic(cal_file):
    cal_file(_cal(_feat("limit_down_ratio", 0.334)))
    r = se.panic_reversal({"limit_down": 95, "up_count": 120, "down_count": 1500,
                           "flat_count": 20, "touch_down": 0})
    assert r["triggered"] is True
    assert r["abstain"] is False
    assert r["prob"] == pytest.approx(0.667, abs=1e-6)
    assert r["base_rate"] == pytest.approx(0.4651, abs=1e-6)
    assert r["edge_pp"] == pytest.approx(20.2, abs=0.1)
    assert r["hits"][0]["n"] == 78 and r["hits"][0]["z"] == 3.57
    assert "统计概率" in r["statement"]


def test_abstain_on_normal_day(cal_file):
    cal_file(_cal(_feat("limit_down_ratio", 0.334)))
    r = se.panic_reversal({"limit_down": 2, "up_count": 800, "down_count": 700,
                           "flat_count": 50, "touch_down": 1})
    assert r["triggered"] is False
    assert r["abstain"] is True
    assert r["prob"] is None and r["edge_pp"] is None
    assert "不表态" in r["statement"]


def test_non_publishable_feature_never_triggers(cal_file):
    """样本不足/不显著的特征必须被忽略——这是「有依据才说话」的硬门槛。"""
    cal_file(_cal(_feat("limit_down_ratio", 0.001, pub=False)))
    r = se.panic_reversal({"limit_down": 999, "up_count": 1, "down_count": 1,
                           "flat_count": 0})
    assert r["triggered"] is False
    assert r["hits"] == []


def test_missing_indicator_does_not_trigger(cal_file):
    cal_file(_cal(_feat("limit_down_ratio", 0.334)))
    # 缺 limit_down → 占比算不出来 → 不得触发
    r = se.panic_reversal({"up_count": 100, "down_count": 1500, "flat_count": 20})
    assert r["triggered"] is False


def test_strength_hint_is_labelled_as_weak(cal_file):
    cal_file(_cal(_feat("limit_down_ratio", 0.334)))
    r = se.panic_reversal({"up_count": 800, "down_count": 700, "flat_count": 50,
                           "touch_down": 30})
    assert r["strength_hint"] is not None
    assert "弱信号" in r["strength_hint"]["hint"]
    assert "仅风险提示" in r["strength_hint"]["hint"]


# ── 4. 与引擎的接线 ─────────────────────────────────────────────

def test_forecast_next_day_exposes_edge_key():
    r = sf.forecast_next_day({"zt_fail_ratio": 15.0, "connect_hl": 6.0,
                              "limit_down": 3.0, "up_count": 800,
                              "down_count": 700, "flat_count": 50})
    assert "edge" in r, "forecast_next_day 必须暴露 edge（极值信号层）"
    assert isinstance(r["edge"], dict)
    assert "abstain" in r["edge"] and "triggered" in r["edge"]


def test_forecast_empty_input_edge_is_none():
    assert sf.forecast_next_day({})["edge"] is None


# ── 5. 生产校准件自身必须站得住 ─────────────────────────────────

def test_shipped_calibration_exists_and_is_evidence_backed():
    """随仓库发布的校准件必须存在，且每个可发布特征都真的显著（z≥1.96）。"""
    if not os.path.exists(CAL_PATH):
        pytest.skip("校准件未生成（运行 scripts/calibrate_sentiment_edge.py）")
    cal = json.load(open(CAL_PATH, encoding="utf-8"))
    assert cal.get("base_next_day_up_rate") is not None
    pub = {k: v for k, v in cal["features"].items() if v.get("publishable")}
    assert pub, "校准件里没有任何可发布特征，等于该层失效"
    for k, v in pub.items():
        wf = v["walk_forward"]
        assert wf["trigger_days"] >= cal["min_trigger_samples"], f"{k} 样本不足却标记可发布"
        assert abs(wf["z"]) >= 1.96, f"{k} 不显著却标记可发布（z={wf['z']}）"
        assert wf["up_rate"] > cal["base_next_day_up_rate"], f"{k} 边际方向不对"


def test_shipped_calibration_uses_ratio_features_only():
    """尺度无关铁律：特征必须是占比类，不得回到绝对家数阈值。"""
    if not os.path.exists(CAL_PATH):
        pytest.skip("校准件未生成")
    cal = json.load(open(CAL_PATH, encoding="utf-8"))
    for k in cal["features"]:
        assert k.endswith("_ratio"), f"特征 {k} 不是占比类，会与采样规模错配"


def test_calibration_script_has_no_lookahead():
    """源码守卫：阈值只允许用第 i 天之前的数据（walk-forward），不得用未来信息。

    历史教训：把全样本分位数当阈值再回测，会得到虚假的显著性。
    """
    src = open(CAL_SCRIPT, encoding="utf-8").read()
    assert "hist[:i]" in src, "阈值必须只用过去数据 hist[:i]"
    assert "quantile(Q)" in src
    tree = ast.parse(src)
    fns = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert "main" in fns
    # 目标可以使用未来（y1 = 次日收益是标签），但阈值段不得出现 shift(-1) 参与分位计算
    thr_block = src[src.index("for i in range(WARMUP"):src.index("# 触发日的次日结果")]
    assert "shift(-1)" not in thr_block, "阈值计算段混入了未来信息"


def test_no_absolute_count_thresholds_in_edge_layer():
    """新增信号层不得引入绝对家数阈值（本项目历史数据的家数被低估约 3 倍）。"""
    src = open(os.path.join(ROOT, "modules", "sentiment_edge.py"), encoding="utf-8").read()
    assert "limit_down > " not in src and "limit_up > " not in src
    assert "占比" in src

# ── 7. 「不知道」不等于「没有」（2026-09-10 修） ─────────────────
#   关键指标全缺时，ratios() 返回空 → 所有特征被跳过 → 若直接走「未触发」分支，
#   就会把「没数据」说成「未进入历史极值区间」——把未知包装成结论。

def test_missing_key_indicators_reports_unknown_not_below(cal_file):
    """指标全缺时必须说「无法判定」，不得说「未进入极值区间」。"""
    cal_file(_cal(_feat("limit_down_ratio", 0.3342)))
    r = se.panic_reversal({})                      # 什么都没给
    assert r["available"] is True
    assert r["triggered"] is False
    assert r["evaluated"] is False, "指标缺失时应标记为「没看过」，而非「看了没到」"
    assert r["abstain"] is True
    assert "无法判定" in r["statement"]
    assert "未进入历史极值区间" not in r["statement"], (
        "指标缺失被当成了「未进入极值」——把未知包装成了结论"
    )


def test_below_threshold_marks_evaluated_true(cal_file):
    """拿到了值、未达阈值 → evaluated=True，才可以说「未进入极值区间」。"""
    cal_file(_cal(_feat("limit_down_ratio", 0.3342)))
    r = se.panic_reversal({"up_count": 2000, "down_count": 2500, "limit_down": 5})
    assert r["evaluated"] is True
    assert r["triggered"] is False
    assert r["abstain"] is True
    assert "未进入历史极值区间" in r["statement"]
    assert "无法判定" not in r["statement"]


def test_triggered_day_is_evaluated(cal_file):
    """触发日同样属于「看过了」。"""
    cal_file(_cal(_feat("limit_down_ratio", 0.3342)))
    r = se.panic_reversal({"up_count": 500, "down_count": 4300, "limit_down": 990})
    assert r["triggered"] is True
    assert r["evaluated"] is True


def test_every_return_branch_of_panic_reversal_carries_evaluated():
    """不变量守卫（AST）：panic_reversal 的每个 return 分支都必须带 evaluated。

    否则新增分支时容易漏掉，页面就会把「没带标志」当成「未触发」展示，
    重演「把未知说成没有」的老毛病。
    """
    src = open(se.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "panic_reversal":
            fn = node
    assert fn is not None, "未找到 panic_reversal"

    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    assert returns, "panic_reversal 没有 return 分支？解析逻辑已失效"
    missing = []
    for r in returns:
        call = r.value
        assert isinstance(call, ast.Call), f"第 {r.lineno} 行 return 不是 dict(...) 调用"
        keys = {kw.arg for kw in call.keywords}
        if "evaluated" not in keys:
            missing.append(r.lineno)
    assert not missing, f"这些 return 分支缺少 evaluated 字段：{missing} 行"

# ── 8. 校准件必须随仓库发布 + 不可用时页面不能默不作声 ─────────────
#   背景（2026-09-10）：校准件原先只写 data/，而 data/ 被 .gitignore 忽略 →
#   换机器 / 新克隆后这层会「静默消失」（模块降级为 available=False，页面连一句提示都没有）。

def test_calibration_falls_back_to_reports_when_data_missing(tmp_path, monkeypatch):
    """data/ 缺失时必须回退到 reports/ 里随仓库发布的那份，能力不丢。"""
    import shutil

    data_p = tmp_path / "cal_data.json"
    rep_p = tmp_path / "cal_reports.json"
    shutil.copyfile(CAL_PATH, data_p)          # 用真实校准件做样本
    shutil.copyfile(CAL_PATH, rep_p)

    monkeypatch.setattr(se, "CANDIDATE_PATHS", [str(data_p), str(rep_p)])
    monkeypatch.delenv(se.ENV_PATH, raising=False)
    se._cache.update(path=None, mtime=None, data=None)

    assert se.calibration_path() == str(data_p)
    assert se.load_calibration().get("available") is True

    data_p.unlink()                            # 模拟「另一台机器没有 data/」
    se._cache.update(path=None, mtime=None, data=None)
    assert se.calibration_path() == str(rep_p), "data/ 缺失时未回退到 reports/"
    assert se.load_calibration().get("available") is True


def test_both_calibration_copies_missing_degrades_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr(se, "CANDIDATE_PATHS",
                        [str(tmp_path / "a.json"), str(tmp_path / "b.json")])
    monkeypatch.delenv(se.ENV_PATH, raising=False)
    se._cache.update(path=None, mtime=None, data=None)
    r = se.panic_reversal({"up_count": 100, "down_count": 200, "limit_down": 300})
    assert r["available"] is False and r["abstain"] is True
    assert r["evaluated"] is False


def test_reports_calibration_mirror_is_shipped_and_in_sync():
    """随仓库发布的那份必须存在，且与 data/ 版本内容一致（防只更新一处）。"""
    mirror = os.path.join(ROOT, "reports", "sentiment_edge_calibration.json")
    assert os.path.exists(mirror), (
        "reports/sentiment_edge_calibration.json 缺失 → 换机器后情绪极值层会静默失效"
    )
    if os.path.exists(CAL_PATH):
        a = json.load(open(CAL_PATH, encoding="utf-8"))
        b = json.load(open(mirror, encoding="utf-8"))
        assert a == b, "data/ 与 reports/ 两份校准件不一致（改了要同时重新生成）"


def test_pages_surface_notice_when_edge_unavailable():
    """AST 守卫：50_/54_ 必须有「校准件不可用」分支。

    否则 available=False 时代码什么都不渲染 —— 用户根本不知道有这层能力，
    正是「静默失效」比「明确弃权」更坏的地方。
    """
    pages = {"50_市场情绪.py": os.path.join(ROOT, "pages", "50_市场情绪.py"),
             "54_今日决策面板.py": os.path.join(ROOT, "pages", "54_今日决策面板.py")}
    for name, path in pages.items():
        tree = ast.parse(open(path, encoding="utf-8").read())
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            for sub in ast.walk(node.test):
                # 形如 not _edge.get("available") 或 _edge.get("available") is False
                if (isinstance(sub, ast.UnaryOp) and isinstance(sub.op, ast.Not)
                        and isinstance(sub.operand, ast.Call)
                        and isinstance(sub.operand.func, ast.Attribute)
                        and sub.operand.func.attr == "get"):
                    found = True
                if (isinstance(sub, ast.Compare)
                        and any(isinstance(c, ast.Constant) and c.value is False
                                for c in sub.comparators)):
                    found = True
        assert found, f"{name} 缺少「情绪极值层不可用」的提示分支（会静默失效）"
