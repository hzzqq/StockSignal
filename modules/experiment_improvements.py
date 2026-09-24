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
def shap_style_attribution(contributions: list[dict]) -> dict:
    """把 derive_position(explain=True) 的 contributions 转成标准因子归因表。

    contributions 形如 [{"factor": str, "delta": float, "running": float}, ...]
    返回 {factor: 累计贡献 delta} 并按贡献绝对值降序。

    这是 XAI 热点方向（开题 #4）的安全落地：不训练新模型，只是把现有决策的
    可解释性**标准化**成 SHAP 式归因表，直接可用作毕设"可解释融合"的实证证据。
    """
    if not contributions:
        return {}
    out: dict[str, float] = {}
    for c in contributions:
        f = c.get("factor")
        d = c.get("delta") or 0.0
        if f is None:
            continue
        out[f] = out.get(f, 0.0) + float(d)
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
