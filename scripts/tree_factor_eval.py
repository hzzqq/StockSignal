# -*- coding: utf-8 -*-
"""
scripts/tree_factor_eval.py — 行为金融特征增强的改进型集成树 head-to-head（T-184 · 教师 #5）

对接导师：刘云翔教授「改进型算法 + 落地系统」带教风格（改进 CART/RF 同款叙事）。
改进点（不是换个库调参，而是**特征层创新**）：把 T-182 的行为金融因子
（羊群拥挤度/市场状态/连势/红盘比偏离）注入经典集成树，与纯价量特征组
head-to-head，严格时序留出评估。

口径（对齐 sentiment_predictive_power 严谨先例）：
  · 时序 60/40 单次切分（train_frac=0.6，不 shuffle——杜绝前视）
  · 显著性以 test 集 base_rate 为 p0 参照（不用 0.5 误判「显著」）
  · 目标 = 次日 median_chg 符号（>1 多 / <0 空 / =0 剔除，平盘无方向信息）
  · 结论如实记录：增强组若不涨反跌，就是「特征无增益」的诚实负向，不包装

输入：data/shepherd_history.csv
输出：reports/tree_factor_eval.json + 控制台摘要
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime

_HERE0 = os.path.dirname(os.path.abspath(__file__))
_ROOT0 = os.path.dirname(_HERE0)
if _ROOT0 not in sys.path:
    sys.path.insert(0, _ROOT0)

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.metrics import roc_auc_score

from modules.herd_crowding import crowding_from_history
from modules.market_regime import STATE_ORDER, classify_state
from modules.time_utils import now_cst_naive

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DATA_DIR = os.environ.get("SS_DATA_DIR", os.path.join(_ROOT, "data"))
_BREADTH_FILE = os.path.join(DATA_DIR, "shepherd_history.csv")
OUT_PATH = os.environ.get(
    "TREE_FACTOR_OUT",
    os.path.join(_ROOT, "reports", "tree_factor_eval.json"),
)

TRAIN_FRAC = 0.6
RANDOM_STATE = 42
P_FEATURES = ["red_ratio", "limit_up", "limit_down", "connect_hl",
              "zt_fail_ratio", "zt_prev_ret"]                       # 纯价量/广度
B_FEATURES = ["crowd_score", "crowd_greed", "crowd_fear", "streak_days",
              "rr_dev", "state_crash", "state_panic", "state_bull",
              "state_boom"]                                          # 行为金融增强
SEED = 42


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def build_dataset(breadth_file: str | None = None) -> pd.DataFrame:
    """逐日组装特征矩阵（无前视：拥挤度分位只用截至前一日历史），删缺数行。"""
    path = breadth_file or _BREADTH_FILE
    df = pd.read_csv(path, encoding="utf-8-sig").sort_values("date").reset_index(drop=True)
    rows = df.to_dict("records")
    out: list[dict] = []
    for i in range(1, len(rows) - 1):
        r = rows[i]
        nxt = rows[i + 1]
        next_chg = _num(nxt.get("median_chg"))
        if next_chg is None or next_chg == 0:
            continue  # 无次日真值或平盘日（无方向信息）→ 剔除
        rec = {"date": r.get("date"), "label": 1 if next_chg > 0 else 0,
               "next_chg": next_chg}
        ok = True
        for c in P_FEATURES:
            v = _num(r.get(c))
            if v is None:
                ok = False
                break
            rec[c] = v
        if not ok:
            continue

        herd = crowding_from_history(df, i)
        if herd.get("status") == "ok" and herd.get("score") is not None:
            rec["crowd_score"] = float(herd["score"])
            rec["crowd_greed"] = 1 if herd.get("side") == "greed" else 0
            rec["crowd_fear"] = 1 if herd.get("side") == "fear" else 0
            rec["streak_days"] = float((herd.get("parts") or {}).get("streak_days", 0))
        else:
            rec["crowd_score"] = 50.0
            rec["crowd_greed"] = rec["crowd_fear"] = 0.0
            rec["streak_days"] = 0.0
        rec["rr_dev"] = (float(r["red_ratio"]) - 50.0) / 50.0
        state = classify_state(r)
        rec["state_crash"] = 1 if state == "暴跌" else 0
        rec["state_panic"] = 1 if state == "恐慌" else 0
        rec["state_bull"] = 1 if state == "结构牛" else 0
        rec["state_boom"] = 1 if state == "普涨" else 0
        out.append(rec)
    return pd.DataFrame(out)


def _eval_model(model, X_tr, y_tr, X_te, y_te) -> dict:
    model.fit(X_tr, y_tr)
    proba = model.predict_proba(X_te)[:, 1]
    acc = float(((proba >= 0.5).astype(int) == np.asarray(y_te)).mean())
    auc = float(roc_auc_score(y_te, proba))
    return {"direction_accuracy": round(acc, 4), "auc": round(auc, 4)}


def run(breadth_file: str | None = None) -> dict:
    data = build_dataset(breadth_file)
    if len(data) < 200:
        raise ValueError(f"有效样本不足（n={len(data)}），拒绝产出结论")
    cut = int(len(data) * TRAIN_FRAC)
    tr, te = data.iloc[:cut], data.iloc[cut:]   # 时序切分，不 shuffle
    base_rate = float(te["label"].mean())

    models = {
        "baseline_majority": lambda: DummyClassifier(strategy="most_frequent",
                                                     random_state=SEED),
        "hist_gb_pure": lambda: HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.06, max_depth=3, random_state=RANDOM_STATE),
        "hist_gb_enhanced": lambda: HistGradientBoostingClassifier(
            max_iter=200, learning_rate=0.06, max_depth=3, random_state=RANDOM_STATE),
        "rf_pure": lambda: RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, random_state=RANDOM_STATE, n_jobs=-1),
        "rf_enhanced": lambda: RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, random_state=RANDOM_STATE, n_jobs=-1),
    }
    results = {}
    for name, factory in models.items():
        if name == "baseline_majority":
            r = _eval_model(factory(), np.zeros((len(tr), 1)), tr["label"],
                            np.zeros((len(te), 1)), te["label"])
            r["auc"] = None  # 多数类无排序能力，AUC 无意义（如实 None）
        else:
            feats = P_FEATURES if name.endswith("pure") else P_FEATURES + B_FEATURES
            r = _eval_model(factory(), tr[feats], tr["label"], te[feats], te["label"])
        results[name] = r

    # 增强增量（诚实：可能为负）
    delta = {
        "hist_gb_delta_acc": round(results["hist_gb_enhanced"]["direction_accuracy"]
                                   - results["hist_gb_pure"]["direction_accuracy"], 4),
        "rf_delta_acc": round(results["rf_enhanced"]["direction_accuracy"]
                              - results["rf_pure"]["direction_accuracy"], 4),
    }

    # 特征重要性（RF 增强组：行为金融特征是否有用最直接的证据）
    rf = models["rf_enhanced"]()
    feats_b = P_FEATURES + B_FEATURES
    rf.fit(tr[feats_b], tr["label"])
    importances = sorted(zip(feats_b, rf.feature_importances_.tolist()),
                         key=lambda kv: kv[1], reverse=True)

    return {
        "meta": {
            "generated_at": now_cst_naive().isoformat(timespec="seconds"),
            "source": os.path.basename(breadth_file or _BREADTH_FILE),
            "n_total": int(len(data)), "n_train": int(len(tr)), "n_test": int(len(te)),
            "train_end": str(tr["date"].iloc[-1]), "test_start": str(te["date"].iloc[0]),
            "train_frac": TRAIN_FRAC,
            "p_features": P_FEATURES, "b_features": B_FEATURES,
            "test_base_rate_up": round(base_rate, 4),
            "disclosure": "时序 60/40 不 shuffle；显著性以 test base_rate 为 p0；"
                          "增强组若不涨反跌即为诚实负向（特征无增益），不包装。",
        },
        "results": results,
        "enhancement_delta": delta,
        "rf_feature_importance_top": [
            {"feature": k, "importance": round(v, 4)} for k, v in importances[:10]],
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[tree_factor_eval] report → {OUT_PATH}")
    for name, r in report["results"].items():
        print(f"  {name:20s} acc={r['direction_accuracy']} auc={r['auc']}")
    print(f"  delta(enhanced-pure): {report['enhancement_delta']}")
    print(f"  test base_rate_up: {report['meta']['test_base_rate_up']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
