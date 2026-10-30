"""
modules/experiment_improvements.py — 毕设算法改进实验沙盒（纯函数骨架）

目的：把"向导师请求的算法改进点"落到**可验证的工程骨架**，而不是停留在开题 PPT。
所有本文件函数均为纯函数 / 不触发网络 / 不训练模型，可立即单测。

四个改进方向（对应开题清单）：
  #1 Attention/Transformer 增强 GRU  → transformer_signal（需 P1 侧训练，受数据滞后约束）
  #2 GNN 板块-个股传导               → gnn_factor（需图数据 + 训练）
  #3 RL 仓位决策                     → rl_position（替代规则式的对照实验，不直接替换生产）
  #4 SHAP 可解释融合                → shap_attribution（纯解释现有决策，零训练风险）

项目红线（来自 working memory）：
  · 任何改进必须接入 decision.derive_position 的融合逻辑，不得堆砌通用量化能力
  · 评估必须用严格留出评估，锚定论文 49.1%（1722/3507），不得自报过拟合数字
  · 不 kill 老板服务、data/ 不提交、改动走 FF
"""

from __future__ import annotations

from typing import Any


# ───────────────────────── #4 SHAP 风格因子归因（零训练，现在可跑） ─────────────────────────
def shap_style_attribution(contributions: list[dict],
                           baseline_split: bool = False):
    """把 derive_position(explain=True) 的 contributions 转成标准因子归因表。

    contributions 形如 [{"factor": str, "delta": float, "running": float}, ...]

    :param baseline_split: False（默认）→ 返回 {factor: 累计贡献 delta} 按
        绝对值降序（既有行为，向后兼容）。
        True → 按 SHAP 加性归因语义三段式拆解：
        ``f(x) = base + Σφi``，即「基准仓位 + 各因子调节 = 最终仓位」：
        ``{"baseline": 基准仓位(市场温度), "adjustments": {因子: φi},
           "adjustments_total": Σφi, "final_running": 最终仓位}``
        —— 这正是 SHAP 的 additive feature attribution 定义在决策闭环上的
        精确映射（教师 #4「可解释融合」的核心实证：决策不是黑箱，可加性可验）。

    验证口径（tests/test_experiment_improvements.py 钉住）：
        baseline + adjustments_total == final_running（加性可验，容差 0.05）
    """
    if not contributions:
        return {} if not baseline_split else {
            "baseline": None, "adjustments": {},
            "adjustments_total": 0.0, "final_running": None}
    out: dict[str, float] = {}
    baseline = 0.0
    final_running = None
    for c in contributions:
        f = c.get("factor")
        d = c.get("delta") or 0.0
        if f is None:
            continue
        out[f] = out.get(f, 0.0) + float(d)
        if c.get("running") is not None:
            final_running = float(c["running"])
    if baseline_split:
        # 基准 = 首条（市场温度基准，delta 恒 0，running 即基准仓位）
        first = contributions[0]
        baseline = float(first.get("running") or 0.0) if first.get("factor") else 0.0
        adjustments = {k: v for k, v in out.items()
                       if k != first.get("factor")}
        return {
            "baseline": round(baseline, 2),
            "adjustments": dict(sorted(adjustments.items(),
                                       key=lambda kv: abs(kv[1]), reverse=True)),
            "adjustments_total": round(sum(adjustments.values()), 2),
            "final_running": final_running,
        }
    return dict(sorted(out.items(), key=lambda kv: abs(kv[1]), reverse=True))


# ───────────────────────── 严格留出评估框架（对标论文 49.1%） ─────────────────────────
def strict_holdout_eval(predictions: list[float], labels: list[int],
                        test_idx: list[int] | None = None) -> dict:
    """严格留出评估：给定预测(连续值)与真实方向标签，按 test_idx 切分计算命中率。

    命中口径对齐论文：预测 >0 视作看多、<0 视作看空、=0 平盘不计；
    真实标签 >0 多 / <0 空 / =0 平盘不计入。

    :param predictions: 与 labels 同长的方向预测（可由 derive_position 或任何模型产出）
    :param labels: 真实次日方向（1 多 / -1 空 / 0 平盘不计）
    :param test_idx: 留出测试集索引；None 表示全样本（仅 sanity，不用于论文结论）
    :return: {"n", "accuracy", "n_long", "n_short"}
    """
    if not predictions or len(predictions) != len(labels):
        return {"n": 0, "accuracy": 0.0, "n_long": 0, "n_short": 0}
    idx = test_idx if test_idx is not None else list(range(len(labels)))
    n = hit = n_long = n_short = 0
    for i in idx:
        p = predictions[i]
        y = labels[i]
        if y == 0:
            continue
        n += 1
        if y > 0:
            n_long += 1
            if p > 0:
                hit += 1
        else:
            n_short += 1
            if p < 0:
                hit += 1
    return {
        "n": n,
        "accuracy": (hit / n) if n else 0.0,
        "n_long": n_long,
        "n_short": n_short,
    }


# ───────────────────────── 四个方向的接口桩（数据依赖明确标注） ─────────────────────────
class ImprovementDirection:
    """算法改进方向的统一描述，供实验注册与论文方法章节复用。"""

    def __init__(self, key: str, title: str, replaces: str,
                 innovation_hook: str, data_requirement: str, trainable: bool):
        self.key = key
        self.title = title
        self.replaces = replaces
        self.innovation_hook = innovation_hook
        self.data_requirement = data_requirement
        self.trainable = trainable

    def as_dict(self) -> dict:
        return {
            "key": self.key, "title": self.title, "replaces": self.replaces,
            "innovation_hook": self.innovation_hook,
            "data_requirement": self.data_requirement, "trainable": self.trainable,
        }


# 顺序即优先级：#4 最易出成果（零训练），#1/#2/#3 需数据恢复后训练。
DIRECTIONS = [
    ImprovementDirection(
        "shap_attribution", "#4 SHAP 可解释融合",
        "derive_position 现有 contributions",
        "可解释 AI(XAI) 热点，评委友好，零训练风险",
        "无（纯解释现有决策/信号）", False),
    ImprovementDirection(
        "transformer_signal", "#1 纯 Transformer 对照（补 GRUAttention 空白）",
        "P1 侧 GRUAttention 预测头（已含加性注意力，可解释性卖点）",
        "补齐纯 Transformer 变体空白：nn.TransformerEncoder + 加性注意力池化，与 GRUAttention 做 head-to-head 对照",
        "需 P1 dataset_h10 训练（数据 2026-08-14 文件齐全，待 baostock 增量恢复新鲜度）", True),
    ImprovementDirection(
        "gnn_factor", "#2 GNN 板块-个股传导因子",
        "新增因子源（类比 event_adj 注入）",
        "拓扑关系建模，区别于平面多因子",
        "需板块-个股关系图（行业归属/相关性）+ torch-geometric", True),
    ImprovementDirection(
        "rl_position", "#3 RL 仓位决策",
        "derive_position 规则式（对照实验，不直接替换生产）",
        "'用XX算法做动态仓位'叙事强",
        "需环境 reward 定义 + 历史滚动回测，训练耗时", True),
]


def list_directions() -> list[dict]:
    """返回四个方向的清单（开题方向可直接序列化进论文/汇报）。"""
    return [d.as_dict() for d in DIRECTIONS]


# ───────────────────────── 毕设三算法诚实证据桥（对齐新方向） ─────────────────────────
# 新方向（2026-10 Trae 改稿）：创新主轴 = 决策闭环（derive_position 可解释 + 刻度校准），
# 三算法（#1/#2/#3）定位为「诚实实验证据」——#1 边缘但一致的正向、#2/#3 诚实负向
# （方法学反例 / 边界界定），而非生产信号。本桥把已验证的真实数字接入平台，并支持
# 从 P1-QuantFactor 结果 JSON 实时覆盖；任何缺失一律返回 None（诚实红线：不编造、不臆造填充）。
#
# 来源：thesis/素材/毕设素材/毕设_导师沟通与算法改进清单.md（2026-09-25 同口径 head-to-head）。

# 三算法已验证诚实证据（不可变事实，非模型实时输出）
KNOWN_FINDINGS = {
    "transformer_signal": {
        "title": "#1 纯 Transformer 对照 GRUAttention",
        "advisor": "陈丽琼",
        "direction_hit": 0.5130, "direction_hit_baseline": 0.5097,
        "ic": 0.0465, "ic_baseline": 0.0374,
        "icir": 0.3796, "icir_baseline": 0.3462,
        "verdict": "modest_positive",
        "verdict_cn": "一致但小幅占优（方向命中 +0.33pp、IC +24%、ICIR +10%），如实标注幅度有限",
        "provenance": "P1-QuantFactor head-to-head (n=1,583,338, walk-forward 2022–2026), 2026-09-25",
    },
    "gnn_factor": {
        "title": "#2 GNN 板块-个股传导因子",
        "advisor": "陈丽琼",
        "direction_hit": 0.4948, "direction_hit_baseline": 0.5097,
        "ic": 0.0076, "ic_baseline": 0.0374,
        "icir": 0.1047, "icir_baseline": 0.3462,
        "verdict": "negative",
        "verdict_cn": "三项全落后 GRU；IC 仅为 GRU 约 1/5，因子交互更接近可加/时序主导，图结构偏置不成立",
        "provenance": "P1-QuantFactor head-to-head (n=1,583,338), 2026-09-25",
    },
    "rl_position": {
        "title": "#3 RL 仓位决策",
        "advisor": "刘云翔",
        "sharpe": -0.741, "sharpe_baseline_sign": 0.997, "sharpe_baseline_tanh": 1.145,
        "turnover": 0.026,
        "verdict": "negative",
        "verdict_cn": "在已很强的 GRU 信号上叠加轻量 Actor-Critic 无正收益增量，动作被压缩低幅区丢失暴露；方法学反例 / 边界界定",
        "provenance": "P1-QuantFactor RL 对照 (w_rl vs w_sign/w_tanh), 2026-09-25",
    },
}

# 组合级刻度回测的非对称发现（新方向核心论据，来源完整稿 §5.4.3）
ASYMMETRIC_FINDING = {
    "defensive_total_pp": 9.5,
    "offensive_total_pp": -8.0,
    "annualized_offensive_cost_pp": -0.5,
    "note": "闭环是风险缩放器而非收益放大器；有界修正与小步长使进攻侧误判代价可控",
    "provenance": "StockSignal_毕业论文_完整稿.md §5.4.3 组合级刻度回测（n=4092 交易日, 2007–2026）",
}

# 论文钉死的决策闭环命中率锚（1722/3507）
DECISION_CLOSURE_ANCHOR = {"accuracy": 0.491, "n": 3507, "n_hit": 1722}


def get_known_findings() -> dict:
    """返回三算法的已验证诚实证据（深拷贝，供论文/平台引用，防调用方误改常量）。"""
    import copy
    return copy.deepcopy(KNOWN_FINDINGS)


def load_live_findings(results_dir: str | None = None) -> dict:
    """尝试从 P1-QuantFactor 结果 JSON 实时覆盖已知证据；缺失/读不到→保留 KNOWN（live=False）。

    诚实红线：绝不臆造——任何文件缺失或解析失败都回落到已验证的 KNOWN_FINDINGS，
    绝不把「没查到」当「没效果」。返回结构额外携带 ``_meta.live`` 布尔（是否真的读到外部结果）。
    约定目录结构：``<results_dir>/experiment_findings.json``（{key: {...}}）或
    ``<results_dir>/<key>.json``（单条，需含 ``key`` 字段）。
    """
    import copy, json, os
    out = copy.deepcopy(KNOWN_FINDINGS)
    out["_meta"] = {"live": False, "sources": []}
    base = results_dir or os.environ.get("P1_RESULTS_DIR")
    if not base or not os.path.isdir(base):
        return out
    consolidated = os.path.join(base, "experiment_findings.json")
    files = [consolidated] if os.path.isfile(consolidated) else [
        os.path.join(base, f"{key}.json")
        for key in KNOWN_FINDINGS
        if os.path.isfile(os.path.join(base, f"{key}.json"))
    ]
    if not files:
        return out
    live = False
    numeric = ("direction_hit", "direction_hit_baseline", "ic", "ic_baseline",
               "icir", "icir_baseline", "sharpe", "sharpe_baseline_sign",
               "sharpe_baseline_tanh", "turnover")
    for fp in files:
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and any(k in KNOWN_FINDINGS for k in data):
            items = list(data.items())
        elif isinstance(data, dict) and data.get("key") in KNOWN_FINDINGS:
            items = [(data["key"], data)]
        else:
            items = []
        for key, vals in items:
            if key in out and isinstance(vals, dict):
                for nf in numeric:
                    if nf in vals and isinstance(vals[nf], (int, float)):
                        out[key][nf] = float(vals[nf])
                live = True
                out["_meta"]["sources"].append(fp)
    out["_meta"]["live"] = live
    return out


def summarize_findings() -> dict:
    """新方向叙事（数据层，不渲染 UI）：创新主轴 = 决策闭环；三算法 = 诚实证据；组合级非对称发现。

    返回结构供页面/论文方法章节直接消费。
    """
    return {
        "core_innovation": "decision_closure",
        "core_innovation_cn": "决策闭环（derive_position 可解释 + 刻度校准）为创新主轴，"
                              "三算法为诚实实验证据而非生产信号",
        "decision_closure_anchor": DECISION_CLOSURE_ANCHOR,
        "findings": get_known_findings(),
        "asymmetric_finding": ASYMMETRIC_FINDING,
        "honest_redline": "缺失数据返回 None 不编造；modest/负向如实记录，不包装成碾压式领先",
    }
