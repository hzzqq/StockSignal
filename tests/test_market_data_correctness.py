"""市场数据「正确性」断言（#锐评整改 任务2）。

把正确性覆盖从行情/K线扩到全市场维度：指数 / 板块 / 概念 / 宏观 / 商品 / 财务。
全部离线——monkeypatch 数据源入口（_retry_request / _UrllibFetcher / _BaoStockFetcher）
喂「脏」合成输入，验证转换后输出满足契约：
  - 板块全零/全同向/超 20% 校验（_validate_sector_data 纯函数 5 分支）
  - fetch_sector_list 脏输入 → 干净输出（change_pct numeric、空 sector 剔除）
  - 成分股中文列 → code/name/close/change_pct/market_cap 契约
  - fetch_index 乱序超范围输入 → 升序 + [start,end] 范围过滤
  - fetch_macro 列重命名 + tail(60)
  - fetch_commodity_price 品种过滤 + 日期转换
  - fetch_financial report_type 映射 + head(8) 截断
"""
import sys
import types

import numpy as np
import pandas as pd
import pytest

from modules import _feed_io
from modules import _market_data_io as mdi
from modules import fetcher as fetcher_mod
from modules._feed_io import _validate_sector_data
from modules.fetcher import StockFetcher


# ───────────────────────────── 工具 ─────────────────────────────

def _make_fetcher(tmp_path, name="config.yaml"):
    """构造指向临时库的 StockFetcher，隔离数据源全挂时写入的缓存。"""
    config_path = str(tmp_path / name)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(
            f"default:\n  cache_days: 7\n"
            f"database:\n  path: {tmp_path / 'cache.db'}\n"
        )
    return StockFetcher(config_path)


def _sector_df(n=6):
    """构造能通过 _validate_sector_data 的板块数据（≥5 行、涨跌混合、|max|≤20）。"""
    names = ["银行", "煤炭", "钢铁", "白酒", "医药", "地产"][:n]
    pcts = [1.2, -0.8, 0.5, -1.1, 2.0, -0.3][:n]
    return pd.DataFrame({"sector": names, "change_pct": pcts})


# ─────────────────────── 1. 板块校验纯函数 ───────────────────────

def test_sector_validate_full_zero_blocked():
    """全零涨跌幅（BaoStock 兜底硬编码 0.0）必须被判无效，防污染主缓存。"""
    df = pd.DataFrame({"sector": ["a"] * 6, "change_pct": [0.0] * 6})
    assert _validate_sector_data(df) is False


def test_sector_validate_all_same_dir_blocked():
    """全部同向（全涨/全跌）异常 → 无效。"""
    up = pd.DataFrame({"sector": [f"s{i}" for i in range(6)], "change_pct": [3.0] * 6})
    down = pd.DataFrame({"sector": [f"s{i}" for i in range(6)], "change_pct": [-2.0] * 6})
    assert _validate_sector_data(up) is False
    assert _validate_sector_data(down) is False


def test_sector_validate_extreme_blocked():
    """|max|>20%（异常值，正常板块日涨跌 <20%）→ 无效。"""
    df = pd.DataFrame({"sector": [f"s{i}" for i in range(6)], "change_pct": [1, -1, 2, -2, 0.5, 25.0]})
    assert _validate_sector_data(df) is False


def test_sector_validate_too_few_rows_blocked():
    """不足 5 行 → 无效（样本太少无统计意义）。"""
    df = _sector_df(n=4)
    assert _validate_sector_data(df) is False


def test_sector_validate_missing_col_blocked():
    """缺 change_pct 列 → 无效（接口改版/错列时不能当有效数据）。"""
    df = pd.DataFrame({"sector": ["银行", "煤炭"]})
    assert _validate_sector_data(df) is False


def test_sector_validate_normal_passes():
    """涨跌混合且幅度合理 → 有效。"""
    assert _validate_sector_data(_sector_df()) is True


# ─────────────────── 2. fetch_sector_list 后处理 ───────────────────

def test_sector_list_dirty_input_clean_output(tmp_path, monkeypatch):
    """L1 东财返回脏数据（含 NaN 涨跌幅、空 sector 行）→ 输出必须干净。"""
    dirty = pd.DataFrame({
        "sector": ["银行", "煤炭", "钢铁", "白酒", "医药", "", "   ", "地产"],
        "change_pct": [1.2, -0.8, 0.5, -1.1, 2.0, np.nan, np.nan, -0.3],
    })
    monkeypatch.setattr(_feed_io._UrllibFetcher, "fetch_sector_list", lambda: dirty)
    monkeypatch.setattr(fetcher_mod, "_AK_OK", False)  # 强制跳过 L2 同花顺
    fetcher = _make_fetcher(tmp_path)

    df = fetcher.get_sector_list(force_refresh=True)
    assert "sector" in df.columns and "change_pct" in df.columns
    assert df["change_pct"].notna().all(), "change_pct 仍含 NaN"
    assert pd.api.types.is_numeric_dtype(df["change_pct"]), "change_pct 非 numeric"
    assert (df["sector"].astype(str).str.strip() != "").all(), "存在空 sector"
    assert _validate_sector_data(df), "输出未通过板块校验"


# ─────────────────── 3. 成分股列映射契约 ───────────────────

@pytest.mark.parametrize("method,args", [
    ("get_sector_stocks", ("煤炭",)),
    ("get_concept_stocks", ("人工智能",)),
])
def test_cons_stocks_column_mapping(tmp_path, monkeypatch, method, args):
    """成分股中文列 → code/name/close/change_pct/market_cap 契约。"""
    raw = pd.DataFrame({
        "代码": ["600519", "000021"],
        "名称": ["贵州茅台", "深科技"],
        "涨跌幅": [1.5, -2.3],
        "最新价": [1700.0, 15.8],
        "总市值": [2.1e12, 2.4e10],
    })
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)
    monkeypatch.setattr(mdi, "_retry_request", lambda fn, **kw: raw)
    fetcher = _make_fetcher(tmp_path)

    out = getattr(fetcher, method)(*args)
    assert list(out.columns) == ["code", "name", "close", "change_pct", "market_cap"], \
        f"列契约偏离: {list(out.columns)}"
    assert out["code"].tolist() == ["600519", "000021"]
    assert out["change_pct"].tolist() == [1.5, -2.3]


# ─────────────────── 4. fetch_index 排序与范围过滤 ───────────────────

def test_index_kline_sorted_and_range_filtered(tmp_path, monkeypatch):
    """L2 BaoStock 返回乱序 + 超范围数据 → 输出升序且在 [start,end] 内。"""
    dates = pd.to_datetime([
        "2024-03-01", "2024-01-15", "2024-02-20", "2024-01-05", "2024-04-10", "2024-03-20",
    ])
    raw = pd.DataFrame({
        "date": dates,  # 乱序 + 含范围外（01-05 之前、04-10 之后）
        "open": [10, 11, 12, 13, 14, 15],
        "high": [11, 12, 13, 14, 15, 16],
        "low": [9, 10, 11, 12, 13, 14],
        "close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5],
        "volume": [100, 200, 300, 400, 500, 600],
    })
    monkeypatch.setattr(fetcher_mod, "_AK_OK", False)
    monkeypatch.setattr(_feed_io._BaoStockFetcher, "fetch_index_kline",
                        lambda sym, start, end: raw)
    monkeypatch.setattr(_feed_io._UrllibFetcher, "fetch_kline",
                        lambda *a, **k: None)  # 跳过 L3
    fetcher = _make_fetcher(tmp_path)

    out = fetcher.get_index("000001", start="2024-01-01", end="2024-03-31")
    d = pd.to_datetime(out["date"])
    assert d.is_monotonic_increasing, "指数 K线未按日期升序"
    assert d.is_unique, "指数 K线日期重复"
    assert (d >= "2024-01-01").all() and (d <= "2024-03-31").all(), "存在范围外日期"
    assert len(out) == 5, f"期望过滤后 5 行（仅 04-10 超界），实际 {len(out)}"
    assert out.iloc[0]["close"] == 13.5, "过滤+排序后首行应为最早日期 01-05"
    assert out.iloc[-1]["close"] == 15.5, "末行应为最晚日期 03-20"


# ─────────────────── 5. fetch_macro 列重命名 ───────────────────

def test_macro_pmi_rename_and_tail(tmp_path, monkeypatch):
    """宏观列重命名（月份→date、制造业-Loss→pmi_mfg）+ 只保留最近 60 期。"""
    n = 70
    raw = pd.DataFrame({
        "月份": pd.date_range("2019-01-01", periods=n, freq="ME").strftime("%Y-%m"),
        "制造业-Loss": np.linspace(49.0, 52.0, n),
        "其他噪声列": list(range(n)),
    })
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)
    monkeypatch.setattr(mdi, "_retry_request", lambda fn, **kw: raw)
    fetcher = _make_fetcher(tmp_path)

    out = fetcher.get_macro("pmi_mfg")
    assert "date" in out.columns and "pmi_mfg" in out.columns, f"列映射缺失: {list(out.columns)}"
    assert len(out) == 60, f"tail(60) 未生效: {len(out)}"
    assert pd.api.types.is_numeric_dtype(out["pmi_mfg"]), "pmi_mfg 非 numeric"
    assert out["pmi_mfg"].between(40, 60).all(), "pmi 数值超出 sane 区间"


def test_macro_invalid_indicator_raises(tmp_path, monkeypatch):
    """不支持的指标抛 ValueError（白盒契约）。"""
    fetcher = _make_fetcher(tmp_path)
    with pytest.raises(ValueError, match="不支持的指标"):
        fetcher.get_macro("gdp")


# ─────────────────── 6. fetch_commodity_price 品种过滤 ───────────────────

def test_commodity_filter_by_name(tmp_path, monkeypatch):
    """spot_price_qsx 全品种 → 只保留名称含 '煤炭' 的行，日期转 datetime、列契约。"""
    raw = pd.DataFrame({
        "日期": ["2024-06-01", "2024-06-01", "2024-06-02", "2024-06-02"],
        "品种": ["煤炭", "焦炭", "煤炭", "原油"],
        "价格": [800.0, 2000.0, 810.0, 500.0],
    })
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)
    monkeypatch.setattr(mdi, "_retry_request", lambda fn, **kw: raw)
    fetcher = _make_fetcher(tmp_path)

    out = fetcher.get_commodity_price("煤炭")
    assert set(out["name"]) == {"煤炭"}, f"品种过滤失效: {set(out['name'])}"
    assert list(out.columns) == ["date", "name", "price"], f"列契约偏离: {list(out.columns)}"
    assert pd.api.types.is_datetime64_any_dtype(out["date"]), "date 未转 datetime"
    assert out["price"].tolist() == [800.0, 810.0]


# ─────────────────── 7. fetch_financial 映射与截断 ───────────────────

def test_financial_report_type_map_and_head8(tmp_path, monkeypatch):
    """report_type → 报表名映射 + head(8) 截断（假 akshare 模块离线验证）。"""
    fake_ak = types.ModuleType("akshare")
    calls = {}

    def _sina(stock, symbol):
        calls["symbol"] = symbol
        return pd.DataFrame({"报告日期": [f"2024Q{i}" for i in range(12)], "净利润": range(12)})

    fake_ak.stock_financial_report_sina = _sina
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    monkeypatch.setattr(fetcher_mod, "_AK_OK", True)
    fetcher = _make_fetcher(tmp_path)

    out = fetcher.get_financial("600519", "income")
    assert calls.get("symbol") == "利润表", f"report_type 映射错误: {calls.get('symbol')}"
    assert len(out) == 8, f"head(8) 未生效: {len(out)}"
