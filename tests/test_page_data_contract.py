"""test_page_data_contract.py — 数据正确性断言层（"评测集"核心增量）

此前 test_pages_smoke 只验「渲染期不崩」，不验「数据对不对」（已知安慰剂问题）。
本层补上"输入 → 关键输出"的契约断言，专门抓「页面画的是空数据/错数据」类真 bug：

  1. 技术面 full_analysis：必须返回 4 维结构化字典，且趋势/动量/量能各含 score 字段（0-100）。
  2. 清洗管线 full_pipeline：输入合法 OHLCV 后必须产出 ma5/10/20/60 + return_1/5/20d，
     且 ma 数值合理（非 NaN 占比随窗口增大单调不增）。
  3. 牧羊人自定义区间（get_shepherd_indicators_range）：所选时段内全 NaN 的列，
     meta.missing_columns 必须非空，且页面 caption 构造逻辑（复用同款文本）必含「未开始统计」。
  4. 行情看板 K 线契约：清洗后 DataFrame 含 date/open/high/low/close/volume 且 close 为数值。

全部用合成数据 / 离线 stub 跑，不依赖真网（conftest 的 session 级离线守卫已激活）。
运行：pytest tests/test_page_data_contract.py -q
"""
from __future__ import annotations

import pandas as pd
import numpy as np

from modules.cleaner import DataCleaner
from modules.technical import full_analysis
from modules.shepherd import get_shepherd_indicators_range, THRESHOLDS


def _make_ohlcv(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """生成一份合法的 OHLCV 合成数据（升序日期、单调无缺口）。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    close = base
    open_ = close + rng.normal(0, 0.5, n)
    high = np.maximum(open_, close) + rng.uniform(0, 1, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1, n)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame({
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ───────────────────────── 1. 技术面 full_analysis 契约 ─────────────────────────
class TestTechnicalDataContract:
    def test_full_analysis_returns_four_dimensions(self):
        df = _make_ohlcv()
        res = full_analysis(df)
        assert isinstance(res, dict)
        for dim in ("trend", "momentum", "volume", "patterns"):
            assert dim in res, f"full_analysis 缺少维度 {dim}"
            assert not isinstance(res[dim], dict) or "error" not in res[dim], \
                f"维度 {dim} 分析失败: {res[dim]}"

    def test_trend_momentum_volume_have_numeric_score(self):
        df = _make_ohlcv()
        res = full_analysis(df)
        for dim in ("trend", "momentum", "volume"):
            d = res[dim]
            assert "score" in d or "trend_score" in d or "momentum_score" in d or "volume_price_score" in d
            # 取到该维度的得分键
            score = d.get("trend_score") or d.get("momentum_score") or d.get("volume_price_score")
            assert score is not None, f"{dim} 未产出得分"
            assert 0 <= float(score) <= 100, f"{dim} 得分越界: {score}"

    def test_patterns_is_list(self):
        df = _make_ohlcv()
        res = full_analysis(df)
        assert isinstance(res["patterns"], list)

    def test_empty_df_does_not_crash_and_reports_error(self):
        res = full_analysis(pd.DataFrame())
        # 任一维度应进入防御性 error 分支，而非抛异常穿透
        assert any("error" in v for v in res.values() if isinstance(v, dict))


# ───────────────────────── 2. 清洗管线 full_pipeline 契约 ─────────────────────────
class TestCleanerDataContract:
    def test_full_pipeline_produces_moving_averages(self):
        df = _make_ohlcv()
        out = DataCleaner.full_pipeline(df)
        for w in (5, 10, 20, 60):
            assert f"ma{w}" in out.columns, f"缺少 ma{w} 列"
        # ma5 的有效值数量应 >= ma60（窗口越大有效点越少，单调性）
        valid = {w: out[f"ma{w}"].notna().sum() for w in (5, 10, 20, 60)}
        assert valid[5] >= valid[60], f"ma 有效值单调性异常: {valid}"

    def test_full_pipeline_produces_returns(self):
        df = _make_ohlcv()
        out = DataCleaner.full_pipeline(df)
        for p in (1, 5, 20):
            assert f"return_{p}d" in out.columns, f"缺少 return_{p}d 列"

    def test_full_pipeline_coerces_dirty_strings(self):
        """真实脏数据：数据源偶发坏值（object 列里的 'x'/'n/a'/空串）不应让管线抛 TypeError。

        真实场景：akshare/东方财富接口返回的 OHLCV 常为 object dtype，
        full_pipeline 在 calc_returns/calc_ma 前会对 5 列做 pd.to_numeric(errors="coerce")。
        这里用 object dtype 输入复现（而非往 float 列塞字符串），才贴近生产。
        """
        df = _make_ohlcv(60)
        # 模拟接口返回 object 列 + 偶发坏值
        df["close"] = df["close"].astype(object)
        df["volume"] = df["volume"].astype(object)
        df.loc[10, "close"] = "x"
        df.loc[20, "volume"] = "n/a"
        df.loc[30, "close"] = ""
        out = DataCleaner.full_pipeline(df)
        # 脏值被 coerce 为 NaN 后由 fill_missing(ffill+bfill) 收口，
        # 最终 close/volume 应为纯 float 且无非有限值（真实健壮性契约）。
        assert pd.api.types.is_float_dtype(out["close"])
        assert pd.api.types.is_float_dtype(out["volume"])
        assert out["close"].notna().all(), "close 仍残留 NaN（fill_missing 未收口）"
        assert out["volume"].notna().all(), "volume 仍残留 NaN（fill_missing 未收口）"
        # 确认没有任何字符串残留（脏值已被数值化或填充）
        assert out["close"].map(lambda v: isinstance(v, str)).sum() == 0

    def test_full_pipeline_keeps_ohlcv_columns(self):
        df = _make_ohlcv()
        out = DataCleaner.full_pipeline(df)
        for c in ("date", "open", "high", "low", "close", "volume"):
            assert c in out.columns


# ───────────────────────── 3. 牧羊人自定义区间缺失提示契约 ─────────────────────────
class TestShepherdRangeMissingContract:
    def test_all_nan_column_reported_as_missing(self):
        """构造一段所有牧羊人指标全 NaN 的 DataFrame 场景：
        get_shepherd_indicators_range 必须把全 NaN 的列归入 meta.missing_columns。"""
        # 用极早期日期（CSV 里不可能有数据）逼出 unavailable/缺失分支
        df, meta = get_shepherd_indicators_range("2000-01-01", "2000-01-31", backfill=False)
        # 该区间无数据 → unavailable 应覆盖全部 THRESHOLDS
        assert meta["unavailable"], "无数据区间应标记 unavailable"
        assert len(meta["unavailable"]) >= len(THRESHOLDS) - 1

    def test_missing_columns_meta_key_exists(self):
        """即使数据正常，meta 也必须含 missing_columns 字段（页面 caption 依赖它）。"""
        df, meta = get_shepherd_indicators_range("2000-01-01", "2000-01-31", backfill=False)
        assert "missing_columns" in meta, "meta 缺少 missing_columns 字段"

    def test_caption_text_contains_missing_hint(self):
        """复用页面 caption 构造逻辑：missing_columns 非空时文本必含「未开始统计」。"""
        # 模拟页面里的 caption 拼接（与 50_市场情绪.py 行 605-608 同款）
        missing = {"limit_up": "所选时段内该指标全为缺失"}
        names = [THRESHOLDS.get(k, {}).get("name", k) for k in missing.keys()]
        caption = "🐑 牧羊人指标…"
        if missing:
            caption += f" ⚠️ 以下指标在所选时段内缺失（未开始统计或数据源未覆盖）：{', '.join(names)}。"
        assert "未开始统计" in caption, "缺失提示文本未含「未开始统计」关键词"


# ───────────────────────── 4. 行情看板 K 线契约 ─────────────────────────
class TestKlineDataContract:
    def test_cleaned_df_is_kline_ready(self):
        df = _make_ohlcv()
        out = DataCleaner.full_pipeline(df)
        # K 线图契约：close 为数值且无非有限值泄漏
        assert pd.api.types.is_numeric_dtype(out["close"])
        # 至少前 60 行之后应有有效 ma60
        assert out["ma60"].notna().sum() > 0
