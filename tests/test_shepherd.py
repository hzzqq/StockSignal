"""
tests/test_shepherd.py — 牧羊人情绪温度计（modules/shepherd.py）单元测试

目标：锁住「牧羊人指标」核心逻辑的正确性，防止后续重构/降级链改动悄悄破坏：
- THRESHOLDS 17 指标结构与方向（dir）符号（含 dir=0 观察项）
- shepherd_temperature 三路径：退化输入 / 阈值线性 / 历史分位（观察项不打分）
- _compute_spot_indicators / _compute_zt_pool_indicators 纯函数口径（杨哥视频方法论）
- 炸板率杨哥口径：炸板/(涨停+炸板)×100
- _cached 进程内缓存 TTL（命中 / 过期）
- get_shepherd_today 多源合并 + red_ratio 补算 + 炸板率覆盖 + meta 标记
- get_shepherd_history 网络失败 → 持久 CSV 降级
- get_shepherd_indicators 空历史的 meta 标注

全程离线：用 monkeypatch 替换 _fetch_* 与 get_shepherd_history，绝不触网。
"""
import pandas as pd
import pytest

from modules import shepherd


# ─────────────────────────────────────────────────────────────
#  THRESHOLDS 结构（v2：8 项经典 + 7 项打分新增 + 2 项观察）
# ─────────────────────────────────────────────────────────────
EXPECTED_KEYS = {
    # 核心 8 项（v1 情绪温度计）
    "up_count", "down_count", "limit_up", "limit_down",
    "zt_prev_ret", "red_ratio", "connect_hl", "zt_fail_ratio",
    # 复盘方法论新增（打分项）
    "real_limit_up", "median_chg", "hb_wave10", "zt_fail_count",
    "connect_2b", "touch_down", "fc_ratio",
    # 观察项（dir=0，不打分）
    "avg_price", "turnover_amt",
}


def test_thresholds_keys_complete():
    assert set(shepherd.THRESHOLDS.keys()) == EXPECTED_KEYS


def test_thresholds_dir_signs():
    # 越高越热（看涨类）dir=+1
    for k in ("up_count", "limit_up", "zt_prev_ret", "red_ratio", "connect_hl",
              "real_limit_up", "median_chg", "connect_2b", "fc_ratio"):
        assert shepherd.THRESHOLDS[k]["dir"] == 1, f"{k} 应为高温方向 dir=+1"
    # 越高越冷（看跌/防守类）dir=-1
    for k in ("down_count", "limit_down", "zt_fail_ratio",
              "hb_wave10", "zt_fail_count", "touch_down"):
        assert shepherd.THRESHOLDS[k]["dir"] == -1, f"{k} 应为低温方向 dir=-1"
    # 观察项 dir=0（不参与温度计打分）
    for k in ("avg_price", "turnover_amt"):
        assert shepherd.THRESHOLDS[k]["dir"] == 0, f"{k} 应为观察项 dir=0"


def test_thresholds_hot_warm_ordering():
    for k, th in shepherd.THRESHOLDS.items():
        if th["dir"] > 0:
            assert th["hot"] > th["warm"], f"{k}: 高温阈值应大于常温阈值"
        elif th["dir"] < 0:
            assert th["hot"] < th["warm"], f"{k}: 低温阈值应小于常温阈值"
        # dir=0 观察项无序要求，跳过


# ─────────────────────────────────────────────────────────────
#  shepherd_temperature 三路径
# ─────────────────────────────────────────────────────────────
def test_temperature_degenerate_input():
    assert shepherd.shepherd_temperature({}) == 50.0
    assert shepherd.shepherd_temperature(None) == 50.0
    assert shepherd.shepherd_temperature({"up_count": float("nan")}) == 50.0


def test_temperature_threshold_fallback_high(monkeypatch):
    # 无历史 → 阈值线性打分；全部高热值应得接近满分
    shepherd._CACHE.clear()
    monkeypatch.setattr(shepherd, "get_shepherd_history", lambda days=60: None)
    today = {
        "up_count": 5000, "down_count": 500, "limit_up": 80, "limit_down": 2,
        "zt_prev_ret": 5.0, "red_ratio": 85.0, "connect_hl": 9, "zt_fail_ratio": 10.0,
    }
    score = shepherd.shepherd_temperature(today)
    assert 80.0 <= score <= 100.0


def test_temperature_threshold_fallback_low(monkeypatch):
    shepherd._CACHE.clear()
    monkeypatch.setattr(shepherd, "get_shepherd_history", lambda days=60: None)
    today = {
        "up_count": 800, "down_count": 4000, "limit_up": 10, "limit_down": 40,
        "zt_prev_ret": -3.0, "red_ratio": 25.0, "connect_hl": 2, "zt_fail_ratio": 75.0,
    }
    score = shepherd.shepherd_temperature(today)
    assert 0.0 <= score <= 30.0


def test_temperature_percentile_path(monkeypatch):
    # 构造含 10 日真实序列的历史，验证「今日值」在历史时期分布中的分位打分
    shepherd._CACHE.clear()
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "up_count": [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000],
        "limit_up": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    })
    monkeypatch.setattr(shepherd, "get_shepherd_history", lambda days=60: df)

    # up_count=10000 为历史最大 → 经验分位≈1.0 → 接近满分（dir=+1）
    s = pd.to_numeric(df["up_count"], errors="coerce")
    hot_pct = float((s < 10000).mean()) * 100
    hot = shepherd.shepherd_temperature({"up_count": 10000})
    assert hot == pytest.approx(hot_pct, abs=1e-6)

    # up_count=1000 为历史最小 → 经验分位≈0 → 接近低温
    cold_pct = float((s < 1000).mean()) * 100
    cold = shepherd.shepherd_temperature({"up_count": 1000})
    assert cold == pytest.approx(cold_pct, abs=1e-6)
    assert cold < 20.0

    # 中间值 5500 → 分位≈0.5 → 温度居中
    mid = shepherd.shepherd_temperature({"up_count": 5500})
    assert 30.0 <= mid <= 70.0


def test_temperature_observation_items_not_scored(monkeypatch):
    # dir=0 观察项（平均股价/成交额）不参与温度打分：只有观察值时退化为中性 50
    shepherd._CACHE.clear()
    monkeypatch.setattr(shepherd, "get_shepherd_history", lambda days=60: None)
    t = shepherd.shepherd_temperature({"avg_price": 999.0, "turnover_amt": 21000.0})
    assert t == 50.0
    # 极端观察值也不影响已有打分
    base = shepherd.shepherd_temperature({"up_count": 5000})
    with_obs = shepherd.shepherd_temperature({"up_count": 5000, "avg_price": 1e9})
    assert with_obs == pytest.approx(base)


# ─────────────────────────────────────────────────────────────
#  纯函数口径（视频《如何复盘非常重要》新指标）
# ─────────────────────────────────────────────────────────────
def test_limit_pct_for_code():
    assert shepherd._limit_pct_for_code("sh600000") == 0.10   # 沪主板
    assert shepherd._limit_pct_for_code("sz000001") == 0.10   # 深主板
    assert shepherd._limit_pct_for_code("sz300750") == 0.20   # 创业板
    assert shepherd._limit_pct_for_code("sh688981") == 0.20   # 科创板
    assert shepherd._limit_pct_for_code("bj920001") == 0.30   # 北交所
    assert shepherd._limit_pct_for_code("600000") == 0.10     # 裸代码


def test_compute_spot_indicators():
    # 4 只股：1 只 ST（剔除中位数）、1 只回头波>10%、1 只盘中触跌停、1 只正常
    df = pd.DataFrame({
        "代码": ["sh600001", "sz000002", "sz300003", "sh600004"],
        "名称": ["正常A", "ST坏B", "高回落C", "倒跌停D"],
        "涨跌幅": [1.0, 9.0, -3.0, -10.0],
        "最新价": [10.1, 5.0, 8.0, 9.0],
        "昨收": [10.0, 4.6, 10.0, 10.0],
        "最高": [10.2, 5.0, 10.0, 10.0],
        "最低": [10.0, 4.6, 8.5, 9.0],
        "成交量": [1000, 2000, 3000, 4000],
        "成交额": [1e8, 2e8, 3e8, 4e8],
    })
    out = shepherd._compute_spot_indicators(df)
    # 中位数：剔除 ST 后 [1.0, -3.0, -10.0] → -3.0
    assert out["median_chg"] == pytest.approx(-3.0)
    # 平均股价：全部 4 只
    assert out["avg_price"] == pytest.approx((10.1 + 5.0 + 8.0 + 9.0) / 4)
    # 回头波：C (10-8)/10=20% >10% → 1 家
    assert out["hb_wave10"] == 1.0
    # 倒跌停：D 昨收10×(1-0.10)=9.0，最低 9.0 ≤ 9.0×1.005 → 触及
    # （C 为创业板 20% 幅，跌停价 8.0，最低 8.5 未触）
    assert out["touch_down"] == 1.0
    # 成交额合计 10 亿
    assert out["turnover_amt"] == pytest.approx(10.0)


def test_compute_spot_indicators_empty():
    assert shepherd._compute_spot_indicators(None) is None
    assert shepherd._compute_spot_indicators(pd.DataFrame()) is None


def test_compute_zt_pool_indicators():
    df = pd.DataFrame({
        "连板数": [1, 2, 7, 1],
        "炸板次数": [0, 1, 3, 0],
        "封板资金": [1e8, 2e8, 5e8, 5e7],
        "成交额": [2e8, 2e8, 1e9, 5e8],
    })
    out = shepherd._compute_zt_pool_indicators(df)
    assert out["limit_up"] == 4.0
    assert out["connect_hl"] == 7.0
    assert out["connect_2b"] == 2.0          # 2 板 + 7 板
    assert out["zt_fail_ratio"] == pytest.approx(50.0)  # 2/4 池内曾炸板
    assert out["fc_ratio"] == pytest.approx((0.5 + 1.0 + 0.5 + 0.1) / 4)


def test_compute_zt_pool_indicators_empty():
    assert shepherd._compute_zt_pool_indicators(None) is None
    assert shepherd._compute_zt_pool_indicators(pd.DataFrame()) is None


def test_get_shepherd_today_zt_fail_ratio_yang_ge_style(monkeypatch):
    # 杨哥口径：炸板率 = 炸板/(涨停+炸板)×100（视频案例 49/(79+49)=38%）
    monkeypatch.setattr(shepherd, "_fetch_legu", lambda: None, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zt_pool",
                        lambda date=None: {"limit_up": 79.0, "connect_hl": 5.0}, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_prev_pool", lambda date=None: None, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zbgc_pool",
                        lambda date=None: {"zt_fail_count": 49.0}, raising=False)
    monkeypatch.setattr(shepherd, "_get_spot_cached", lambda: None, raising=False)
    merged, _ = shepherd.get_shepherd_today()
    assert merged["zt_fail_ratio"] == pytest.approx(49.0 / (79.0 + 49.0) * 100.0)


# ─────────────────────────────────────────────────────────────
#  _cached TTL
# ─────────────────────────────────────────────────────────────
def test_cached_hits_within_ttl(monkeypatch):
    shepherd._CACHE.clear()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return 42

    assert shepherd._cached(1000, "k1", fn) == 42
    assert shepherd._cached(1000, "k1", fn) == 42  # 命中缓存
    assert calls["n"] == 1  # 仅计算一次


def test_cached_expires_after_ttl(monkeypatch):
    shepherd._CACHE.clear()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return 7

    # 首次写入，记录 now
    base = 1000.0
    monkeypatch.setattr(shepherd.time, "time", lambda: base)
    assert shepherd._cached(1000, "k2", fn) == 7
    assert calls["n"] == 1
    # 推进时间超过 TTL → 应重新计算
    monkeypatch.setattr(shepherd.time, "time", lambda: base + 2000.0)
    assert shepherd._cached(1000, "k2", fn) == 7
    assert calls["n"] == 2


# ─────────────────────────────────────────────────────────────
#  get_shepherd_today 多源合并
# ─────────────────────────────────────────────────────────────
def test_get_shepherd_today_merge(monkeypatch):
    monkeypatch.setattr(shepherd, "_fetch_legu",
                        lambda: {"up_count": 3000, "down_count": 1500, "limit_up": 50,
                                 "limit_down": 5, "flat_count": 200}, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zt_pool",
                        lambda date=None: {"limit_up": 55, "connect_hl": 7, "zt_fail_ratio": 20.0},
                        raising=False)
    monkeypatch.setattr(shepherd, "_fetch_prev_pool",
                        lambda date=None: {"zt_prev_ret": 4.0}, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zbgc_pool",
                        lambda date=None: {"zt_fail_count": 16.0}, raising=False)
    monkeypatch.setattr(shepherd, "_get_spot_cached",
                        lambda: {"median_chg": 0.3, "avg_price": 28.0, "hb_wave10": 18.0,
                                 "touch_down": 11.0, "turnover_amt": 21000.0}, raising=False)

    merged, meta = shepherd.get_shepherd_today()
    assert merged["up_count"] == 3000
    assert merged["connect_hl"] == 7
    assert merged["zt_prev_ret"] == 4.0
    # red_ratio 由 up/down 补算：3000/(3000+1500)*100 = 66.67
    assert abs(merged["red_ratio"] - (3000 / 4500 * 100)) < 1e-6
    # 涨停家数取 max 合并（legu 50 与 zt_pool 55 → 保留已有 legu 优先？逻辑是 zt 仅在未有时写入）
    # 实际：legu 先写入 limit_up=50；zt 仅当 key 不存在才写 → 仍是 50
    assert merged["limit_up"] == 50
    # 炸板率被杨哥口径覆盖：16/(50+16)×100（覆盖 zt_pool 旧口径 20%）
    assert merged["zt_fail_ratio"] == pytest.approx(16.0 / 66.0 * 100.0)
    # 新浪快照五项合入
    assert merged["median_chg"] == 0.3
    assert merged["hb_wave10"] == 18.0
    assert merged["avg_price"] == 28.0
    assert merged["turnover_amt"] == 21000.0
    assert meta["unavailable"] == []
    assert set(["up_count", "down_count", "limit_up", "limit_down", "connect_hl",
                "zt_fail_ratio", "zt_prev_ret", "red_ratio", "median_chg"]).issubset(set(meta["available"]))


def test_get_shepherd_today_partial_failure(monkeypatch):
    monkeypatch.setattr(shepherd, "_fetch_legu", lambda: None, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zt_pool",
                        lambda date=None: {"limit_up": 55}, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_prev_pool", lambda date=None: None, raising=False)
    monkeypatch.setattr(shepherd, "_fetch_zbgc_pool", lambda date=None: None, raising=False)
    monkeypatch.setattr(shepherd, "_get_spot_cached", lambda: None, raising=False)

    merged, meta = shepherd.get_shepherd_today()
    assert merged.get("limit_up") == 55
    # 无 up/down → 不补算 red_ratio
    assert "red_ratio" not in merged
    # 失败的源进入 unavailable
    unavailable_keys = {k for k, _ in meta["unavailable"]}
    assert "legu" in unavailable_keys
    assert "zt_prev_ret" in unavailable_keys


# ─────────────────────────────────────────────────────────────
#  get_shepherd_history CSV 降级
# ─────────────────────────────────────────────────────────────
def test_get_shepherd_history_csv_fallback(monkeypatch, tmp_path):
    shepherd._CACHE.clear()
    # 网络实时回测失败 → 空 DataFrame（columns 仅 date）
    monkeypatch.setattr(shepherd, "_fetch_shepherd_history",
                        lambda n_days=60: pd.DataFrame(columns=["date"]), raising=False)
    # 预备持久 CSV
    csv_path = tmp_path / "shepherd_history.csv"
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "limit_up": [20, 30, 25, 40, 35],
        "zt_prev_ret": [1.0, 2.0, -0.5, 3.0, 1.5],
    }).to_csv(csv_path, index=False, encoding="utf-8-sig")
    monkeypatch.setattr(shepherd, "_HISTORY_FILE", str(csv_path), raising=False)

    df = shepherd.get_shepherd_history(30)
    assert not df.empty
    assert "limit_up" in df.columns
    assert len(df) == 5


# ─────────────────────────────────────────────────────────────
#  get_shepherd_indicators 空历史 meta
# ─────────────────────────────────────────────────────────────
def test_get_shepherd_indicators_empty(monkeypatch):
    monkeypatch.setattr(shepherd, "get_shepherd_history",
                        lambda days=60: pd.DataFrame(columns=["date"]), raising=False)
    df, meta = shepherd.get_shepherd_indicators(30)
    assert df.empty
    unavailable_keys = {k for k, _ in meta["unavailable"]}
    assert unavailable_keys == EXPECTED_KEYS
