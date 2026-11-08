"""T-250 续：日线缓存键归一（daily 全量键）纯函数守卫。

⚠️ 状态说明（诚实标注，勿误读为「性能已改善」）：
本批新增的 ``daily_full`` / ``daily_fullcov`` 键型与日期窗口工具目前**尚未接线到
get_daily**，全仓零调用点，属于工具/基础设施层；因此本批**不改变任何运行时行为**，
也不会让缓存命中率立刻上升。接线是后续独立任务，接线时必须补端到端回归。

本文件钉死四条红线：
  1) ``daily`` 旧键输出逐字节不变（既有 SQLite 缓存必须继续命中）；
  2) 新键不含日期区间——换任何 start/end 都是同一把键（本次改造的目的）；
  3) 覆盖区间判定「拿不准就回源」：残缺 cov / 无界请求一律不得判为已覆盖，
     绝不拿残缺数据冒充完整区间；
  4) 回源窗口并集「只增不减」，且新窗口必须完整覆盖原请求区间；超宽则退回旧形态。

所有被测对象均为纯函数、零 IO、零网络。
"""
import pandas as pd
import pytest

from modules import fetcher_core as fc


# ── 1. 旧键逐字节不变（兼容红线）────────────────────────────────────────

@pytest.mark.parametrize(
    "symbol,start,end,adjust",
    [
        ("600519", "2026-01-01", "2026-03-31", "qfq"),
        ("000001", "2025-12-01", "2026-01-05", "hfq"),
        ("sh000001", "2024-02-29", "2024-03-01", ""),
        ("A_B", "", "", "none"),
    ],
)
def test_daily_key_is_byte_identical(symbol, start, end, adjust):
    """daily 键必须仍是迁移前的 f-string 形态，一个字符都不能变。"""
    expected = f"daily_{symbol}_{start}_{end}_{adjust}"
    got = fc._build_cache_key(
        "daily", symbol=symbol, start=start, end=end, adjust=adjust
    )
    assert got == expected


def test_legacy_daily_cache_key_matches_single_source():
    """兼容反查函数与单一真源输出一致——双读时不能拼出另一把键。"""
    for symbol, start, end, adjust in (
        ("600519", "2026-01-01", "2026-03-31", "qfq"),
        ("000001", "2025-12-01", "2026-01-05", "hfq"),
    ):
        assert fc._legacy_daily_cache_key(symbol, start, end, adjust) == \
            fc._build_cache_key(
                "daily", symbol=symbol, start=start, end=end, adjust=adjust
            )


def test_daily_key_still_needs_all_four_params():
    """新增键型不得放宽旧 daily 的必需参数校验。"""
    with pytest.raises(ValueError):
        fc._build_cache_key("daily", symbol="600519", start="a", end="b")


# ── 2. 新键形态：不含日期区间 ──────────────────────────────────────────

def test_daily_full_key_shape():
    assert fc._build_cache_key("daily_full", symbol="600519", adjust="qfq") == \
        "daily_full_600519_qfq"


def test_daily_fullcov_key_shape():
    assert fc._build_cache_key("daily_fullcov", symbol="600519", adjust="qfq") == \
        "daily_fullcov_600519_qfq"


def test_new_keys_ignore_date_range():
    """核心目的：换日期区间不得换键（旧形态必然 miss → 每次回源）。"""
    a = fc._build_cache_key(
        "daily_full", symbol="600519", adjust="qfq",
        start="2026-01-01", end="2026-03-31",
    )
    b = fc._build_cache_key(
        "daily_full", symbol="600519", adjust="qfq",
        start="2026-06-01", end="2026-09-30",
    )
    assert a == b == "daily_full_600519_qfq"

    c = fc._build_cache_key(
        "daily_fullcov", symbol="600519", adjust="qfq",
        start="2026-01-01", end="2026-03-31",
    )
    d = fc._build_cache_key(
        "daily_fullcov", symbol="600519", adjust="qfq",
        start="2026-06-01", end="2026-09-30",
    )
    assert c == d == "daily_fullcov_600519_qfq"


def test_new_keys_vary_by_symbol_and_adjust():
    """键必须仍能区分标的与复权口径，否则会串数据（比 miss 更危险）。"""
    base = fc._build_cache_key("daily_full", symbol="600519", adjust="qfq")
    assert fc._build_cache_key("daily_full", symbol="000001", adjust="qfq") != base
    assert fc._build_cache_key("daily_full", symbol="600519", adjust="hfq") != base
    assert fc._build_cache_key("daily_fullcov", symbol="600519", adjust="qfq") != base


@pytest.mark.parametrize("key_type", ["daily_full", "daily_fullcov"])
@pytest.mark.parametrize("params", [
    {"adjust": "qfq"},
    {"symbol": "600519"},
    {},
])
def test_new_keys_validate_required_params(key_type, params):
    with pytest.raises(ValueError):
        fc._build_cache_key(key_type, **params)


def test_new_key_types_registered_in_single_source():
    """必需参数集合钉死：只有 symbol + adjust，不得悄悄扩成带区间。"""
    assert fc._KEY_REQUIRED["daily_full"] == ("symbol", "adjust")
    assert fc._KEY_REQUIRED["daily_fullcov"] == ("symbol", "adjust")


def test_t250_constants_are_sane():
    """TTL 与窗口护栏常量关系：与改造前 get_daily 口径一致、上限 > 下限。"""
    assert fc.DAILY_TTL_HOURS_TODAY == 6
    assert fc.DAILY_FULL_MIN_SPAN_DAYS == 365
    assert fc.DAILY_FULL_MAX_SPAN_DAYS == 1095
    assert 0 < fc.DAILY_FULL_MIN_SPAN_DAYS < fc.DAILY_FULL_MAX_SPAN_DAYS
    # 覆盖元数据行「近乎不过期」，但仍须由数据行的 TTL 把关
    assert fc.CACHE_NO_EXPIRE_SECONDS > 10 ** 8


# ── 3. 日期归一 / 平移 ─────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("2026-10-16", "2026-10-16"),
    ("2026/10/16", "2026-10-16"),
    ("20261016", "2026-10-16"),
    (pd.Timestamp("2026-10-16"), "2026-10-16"),
])
def test_daily_date_str_normalizes(value, expected):
    assert fc._daily_date_str(value) == expected


@pytest.mark.parametrize("value", [None, "", "not-a-date", "昨天", pd.NaT])
def test_daily_date_str_invalid_returns_none(value):
    assert fc._daily_date_str(value) is None


def test_daily_shift_days():
    assert fc._daily_shift_days("2026-01-01", -365) == "2025-01-01"
    assert fc._daily_shift_days("2024-03-01", 1) == "2024-03-02"  # 闰年次日
    assert fc._daily_shift_days("2026/10/16", -30) == "2026-09-16"
    assert fc._daily_shift_days(None, -30) is None
    assert fc._daily_shift_days("not-a-date", -30) is None


# ── 4. 日期切片：闭区间 + 诚实空结果 ────────────────────────────────────

def _sample_daily_df():
    return pd.DataFrame({
        "date": ["2026-09-30", "2026-10-01", "2026-10-16", "2026-11-01"],
        "close": [10.0, 11.0, 12.0, 13.0],
    })


def test_slice_by_window_is_closed_interval():
    """两端都含，且不得改变行序 / 数值。"""
    got = fc._daily_slice_by_window(_sample_daily_df(), "2026-10-01", "2026-10-16")
    assert list(got["date"]) == ["2026-10-01", "2026-10-16"]
    assert list(got["close"]) == [11.0, 12.0]


def test_slice_by_window_open_bounds():
    assert len(fc._daily_slice_by_window(_sample_daily_df(), None, None)) == 4
    assert len(fc._daily_slice_by_window(_sample_daily_df(), "2026-10-16", None)) == 2


def test_slice_by_window_empty_never_fabricates():
    """窗口内无数据 → 空 DataFrame，绝不补 0 / 编造行。"""
    got = fc._daily_slice_by_window(_sample_daily_df(), "2030-01-01", "2030-12-31")
    assert isinstance(got, pd.DataFrame)
    assert got.empty
    assert len(got) == 0


@pytest.mark.parametrize("df", [None, pd.DataFrame(), pd.DataFrame({"close": [1.0]})])
def test_slice_by_window_bad_input_returns_empty(df):
    assert fc._daily_slice_by_window(df, "2026-01-01", "2026-12-31").empty


def test_slice_by_window_invalid_window_returns_empty():
    """非法日期窗口走降级分支：不得抛异常、不得返回全量冒充切片。"""
    got = fc._daily_slice_by_window(_sample_daily_df(), "not-a-date", "2026-12-31")
    assert isinstance(got, pd.DataFrame)
    assert got.empty


def test_slice_by_window_bad_date_rows_are_dropped():
    """date 列含脏值时，无法解析的行不得混进结果（fillna(False) 生效）。"""
    df = pd.DataFrame({"date": ["2026-10-01", "garbage", None], "close": [1, 2, 3]})
    got = fc._daily_slice_by_window(df, "2026-01-01", "2026-12-31")
    assert list(got["date"]) == ["2026-10-01"]


# ── 5. 覆盖区间判定：诚实红线 ──────────────────────────────────────────

def test_interval_covers_true_when_fully_contained():
    cov = {"start": "2025-01-01", "end": "2026-12-31"}
    assert fc._daily_interval_covers(cov, "2026-01-01", "2026-03-31") is True
    assert fc._daily_interval_covers(cov, "2025-01-01", "2026-12-31") is True


def test_interval_covers_false_on_partial_overlap():
    cov = {"start": "2026-01-01", "end": "2026-06-30"}
    # 左越界 / 右越界 / 全越界，任一不满足都必须回源
    assert fc._daily_interval_covers(cov, "2025-12-01", "2026-03-31") is False
    assert fc._daily_interval_covers(cov, "2026-01-01", "2026-09-30") is False
    assert fc._daily_interval_covers(cov, "2027-01-01", "2027-03-31") is False


@pytest.mark.parametrize("cov", [
    None,
    [],
    {"start": "2026-01-01"},
    {"end": "2026-12-31"},
    {"start": None, "end": "2026-12-31"},
    {"start": "bad", "end": "2026-12-31"},
    {},
])
def test_interval_covers_rejects_incomplete_cov(cov):
    """cov 任一边缺省/非法 → 未覆盖（拿不准就回源）。"""
    assert fc._daily_interval_covers(cov, "2026-01-01", "2026-03-31") is False


@pytest.mark.parametrize("start,end", [
    (None, None),
    (None, "2026-03-31"),
    ("2026-01-01", None),
])
def test_interval_covers_rejects_unbounded_request(start, end):
    """⚠️ 诚实红线：无界请求 = 全时间轴，任何有限 cov 都无法证明完整包含。

    必须返回 False 强制回源；返回 True 会让残缺序列被当成完整区间返回给调用方。
    """
    cov = {"start": "2025-01-01", "end": "2026-12-31"}
    assert fc._daily_interval_covers(cov, start, end) is False


# ── 6. 回源窗口：并集只增不减 / 限宽护栏 / 边界缺省 ──────────────────────

def test_fetch_window_backtracks_at_least_min_span():
    """近 30 天请求也要至少取 365 天——一次取够，后续换区间才命中缓存。"""
    lo, hi, use_full = fc._daily_fetch_window(None, "2026-10-01", "2026-10-31")
    assert use_full is True
    assert hi == "2026-10-31"
    assert (pd.Timestamp(hi) - pd.Timestamp(lo)).days >= fc.DAILY_FULL_MIN_SPAN_DAYS
    assert fc._daily_interval_covers({"start": lo, "end": hi},
                                     "2026-10-01", "2026-10-31") is True


def test_fetch_window_union_is_monotonic():
    """并集只增不减：既有覆盖区间与新请求都必须落在新窗口内。"""
    cov = {"start": "2025-06-01", "end": "2026-08-31"}
    lo, hi, use_full = fc._daily_fetch_window(cov, "2026-01-01", "2026-10-31")
    assert use_full is True
    assert lo <= min(cov["start"], "2026-01-01")
    assert hi >= max(cov["end"], "2026-10-31")
    assert fc._daily_interval_covers({"start": lo, "end": hi},
                                     cov["start"], cov["end"]) is True
    assert fc._daily_interval_covers({"start": lo, "end": hi},
                                     "2026-01-01", "2026-10-31") is True


@pytest.mark.parametrize("cov", [
    {"start": "2020-01-01", "end": "2026-12-31"},
    {"start": "bad", "end": "bad"},
])
def test_fetch_window_too_wide_falls_back_to_legacy(cov):
    """并集超过护栏 → 退回旧形态，且原样返回请求区间（绝不裁掉调用方要的区间）。"""
    lo, hi, use_full = fc._daily_fetch_window(cov, "2026-01-01", "2026-10-31")
    assert use_full is False
    assert lo == "2026-01-01"
    assert hi == "2026-10-31"


@pytest.mark.parametrize("cov", [
    {"start": "2026-01-01"},
    {"end": "2026-12-31"},
    {"start": "2026-01-01", "end": "bad"},
    {"start": None, "end": "2026-12-31"},
])
def test_fetch_window_rejects_corrupt_cov_metadata(cov):
    """覆盖元数据残缺/损坏 → 退回旧形态。

    真缺陷守卫：早期实现会静默忽略坏元数据并启用新形态，用较窄窗口覆盖写入
    daily_full 全量行，把既有更长的序列截短（缓存数据被破坏）。
    """
    lo, hi, use_full = fc._daily_fetch_window(cov, "2026-01-01", "2026-10-31")
    assert use_full is False
    assert (lo, hi) == ("2026-01-01", "2026-10-31")


def test_fetch_window_empty_cov_still_uses_full_form():
    """空元数据 = 尚无覆盖信息（等价首次请求），不得误判为损坏而退回旧形态。"""
    lo, hi, use_full = fc._daily_fetch_window({}, "2026-10-01", "2026-10-31")
    assert use_full is True
    assert fc._daily_interval_covers({"start": lo, "end": hi},
                                     "2026-10-01", "2026-10-31") is True


@pytest.mark.parametrize("start,end", [
    (None, "2026-10-31"),
    ("2026-01-01", None),
    (None, None),
    ("bad", "2026-10-31"),
])
def test_fetch_window_missing_or_bad_bounds_falls_back(start, end):
    lo, hi, use_full = fc._daily_fetch_window(None, start, end)
    assert use_full is False
    assert lo == start
    assert hi == end


def test_fetch_window_custom_span_limits():
    """min/max 可注入（接线后按源端上限调参），护栏判定仍生效。"""
    lo, hi, use_full = fc._daily_fetch_window(
        None, "2026-01-01", "2026-01-31",
        min_span_days=30, max_span_days=60,
    )
    assert use_full is True
    assert (pd.Timestamp(hi) - pd.Timestamp(lo)).days <= 60

    lo2, hi2, use_full2 = fc._daily_fetch_window(
        None, "2026-01-01", "2026-01-31",
        min_span_days=30, max_span_days=10,
    )
    assert use_full2 is False
    assert (lo2, hi2) == ("2026-01-01", "2026-01-31")
