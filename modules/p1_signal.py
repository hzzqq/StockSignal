"""P1 量化信号加载器（StockSignal 接入层）。

从 P1-QuantFactor 导出的 ``signal_*.json`` 读取「未来 N 日超额收益概率」信号，
供 StockSignal 页面展示看多/看空榜单与三信号 A/B 对比。

信号 JSON schema（由 P1 ``scripts/06_export_signal.py`` 产出）：

    {
      "model": "ev" | "gru" | "fusion" | "baseline",
      "latest_date": "2026-08-14",
      "horizon": 10,
      "top_long":  [{"symbol": "sh600869", "pred": 0.0298, "rank": 1.0}, ...],    # 看多（前 N）
      "top_short": [{"symbol": "sh603118", "pred": -0.0545, "rank": 0.0007}, ...], # 看空（后 N）
      "daily":     [{"date": "2026-05-18", "symbol": "sh600000",
                     "score": -0.014, "signal": "中性"}, ...]
    }

文件默认在 P1 仓库，StockSignal 通过可配置目录自动发现（见 ``discover_source_dirs``）。

⚠️ 口径说明（务必随页面展示）：
- 这是「统计意义上的超额收益概率」，**不是**「明天必涨/必跌」的预测。
- 2026 单年（湍流弱年）仍为负，真实价值在 2022–2025，**多年度复合才显正期望**。
- 信号为市场中性多空（看多/看空各 N 只）；A 股零售场景通常**仅取多头侧**或降权空头。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

try:
    import pandas as pd
except Exception:  # pragma: no cover - 页面已自带 pandas
    pd = None

# 模型中文名映射（用于 UI 展示）
MODEL_LABELS = {
    "ev": "EV 事件因子",
    "gru": "GRU",
    "fusion": "regime 融合",
    "baseline": "基线 LightGBM",
}


def discover_source_dirs():
    """返回候选信号目录列表（按优先级），自动发现 P1 导出的 ``signal_*.json``。

    优先级：环境变量 ``P1_SIGNAL_DIR`` → StockSignal 自托管目录 ``data/p1_signals``
    → P1-QuantFactor 默认产出目录（本地开发直连，免复制大文件）。
    """
    dirs: list[str] = []
    env = os.environ.get("P1_SIGNAL_DIR")
    if env:
        dirs.append(env)
    # 相对 StockSignal 根目录的 data/p1_signals（自托管首选，放这里可脱离 P1 路径依赖）
    try:
        root = Path(__file__).resolve().parent.parent
        dirs.append(str(root / "data" / "p1_signals"))
    except Exception:
        pass
    # P1-QuantFactor 默认产出目录（本地开发机直连，免复制 55MB 大文件）
    dirs.append(r"E:/project/sj/data/P1/processed/signals")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _load_one(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class P1SignalLoader:
    """懒加载、按 model 缓存的 P1 信号读取器。

    只在首次访问某模型时解析其 JSON（含daily大数组），并缓存解析结果，
    后续访问零成本。适合 ev(11MB)/gru(55MB)/fusion(55MB) 混合场景。
    """

    def __init__(self, source_dirs=None, ttl: int | None = 300):
        self.source_dirs = source_dirs or discover_source_dirs()
        # ttl：秒。None=永不过期。配合文件 mtime 检测，P1 重新导出信号即自动刷新（实时刷新）。
        self.ttl = ttl
        self._cache: dict[str, dict] = {}      # model -> {"path","mtime","ts","data"}
        self._files: dict[str, str] | None = None  # 扫描结果缓存

    # ---- 文件扫描 ----
    def _scan(self) -> dict[str, str]:
        if self._files is not None:
            return self._files
        found: dict[str, str] = {}
        for d in self.source_dirs:
            p = Path(d)
            if not p.exists():
                continue
            for fp in sorted(p.glob("signal_*.json")):
                try:
                    meta = _load_one(str(fp))
                except Exception:
                    continue
                model = (meta.get("model")
                         or fp.stem.replace("signal_", "").replace("_h10", ""))
                if model in found:
                    # 同 model 以文件体积更大者优先（更完整/更晚导出）
                    try:
                        if fp.stat().st_size > Path(found[model]).stat().st_size:
                            found[model] = str(fp)
                    except Exception:
                        pass
                else:
                    found[model] = str(fp)
        self._files = found
        return found

    def available_models(self) -> list[str]:
        return sorted(self._scan().keys())

    def load(self, model: str) -> dict:
        """加载某模型信号 JSON；带缓存 + 实时刷新（文件 mtime 变化或超 ttl 即重载）。"""
        files = self._scan()
        if model not in files:
            raise KeyError(
                f"未找到模型 {model} 的信号文件（已搜索：{self.source_dirs}）")
        path = files[model]
        cached = self._cache.get(model)
        if cached is not None and cached.get("path") == path:
            try:
                cur_mtime = os.path.getmtime(path)
            except Exception:
                cur_mtime = None
            # 文件被重新导出（mtime 变化）→ 立即重载；否则在 ttl 内复用
            fresh = (cur_mtime is not None and cached.get("mtime") == cur_mtime)
            if fresh and (self.ttl is None or (time.time() - cached["ts"]) <= self.ttl):
                return cached["data"]
        data = _load_one(path)
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = None
        self._cache[model] = {"path": path, "mtime": mtime, "ts": time.time(), "data": data}
        return data

    def invalidate(self, model: str | None = None) -> None:
        """手动清除缓存（🔄 刷新按钮用）。model=None 清除全部。"""
        if model is None:
            self._cache.clear()
        else:
            self._cache.pop(model, None)

    # ---- 视图 ----
    def top_long(self, model: str, n: int | None = None) -> list[dict]:
        rows = self.load(model).get("top_long", []) or []
        return rows[:n] if n else rows

    def top_short(self, model: str, n: int | None = None) -> list[dict]:
        rows = self.load(model).get("top_short", []) or []
        return rows[:n] if n else rows

    def latest_date(self, model: str):
        return self.load(model).get("latest_date")

    @staticmethod
    def model_label(model: str) -> str:
        return MODEL_LABELS.get(model, model)

    def daily_df(self, model: str):
        if pd is None:
            return None
        data = self.load(model).get("daily", []) or []
        return pd.DataFrame(data)

    def summary(self) -> dict:
        out: dict = {}
        for m in self.available_models():
            try:
                d = self.load(m)
            except Exception:
                continue
            out[m] = {
                "label": self.model_label(m),
                "latest_date": d.get("latest_date"),
                "horizon": d.get("horizon"),
                "n_top_long": len(d.get("top_long", []) or []),
                "n_top_short": len(d.get("top_short", []) or []),
                "n_daily": len(d.get("daily", []) or []),
            }
        return out

    # ---- A/B 对比 ----
    def top_overlap(self, model_a: str, model_b: str, n: int = 20):
        """两个模型 top_long（前 n 只）的 Jaccard 重叠度与重叠只数。"""
        a = {r["symbol"] for r in self.top_long(model_a, n)}
        b = {r["symbol"] for r in self.top_long(model_b, n)}
        if not a and not b:
            return 0.0, 0
        inter = len(a & b)
        union = len(a | b)
        return (inter / union if union else 0.0), inter
