"""test_whitebox_cleaner.py — DataCleaner 白盒测试
覆盖 fill_missing / remove_outliers / align_dates / normalize / calc_returns / calc_ma / full_pipeline
所有分支条件、边界值和异常路径。
"""

import numpy as np
import pandas as pd
import pytest
from modules.cleaner import DataCleaner


class TestFillMissing:
    """fill_missing 白盒测试。"""

    def test_ffill_basic(self):
        df = pd.DataFrame({"a": [1, None, 3, None, 5]})
        result = DataCleaner.fill_missing(df, method="ffill")
        assert result["a"].isna().sum() == 0
        assert result["a"].tolist() == [1, 1, 3, 3, 5]

    def test_ffill_leading_nan(self):
        """前向填充无法填充首行的 NaN。"""
        df = pd.DataFrame({"a": [None, 2, 3]})
        result = DataCleaner.fill_missing(df, method="ffill")
        assert result["a"].iloc[0] is None or pd.isna(result["a"].iloc[0])
        assert result["a"].iloc[1] == 2

    def test_bfill_basic(self):
        df = pd.DataFrame({"a": [1, None, 3]})
        result = DataCleaner.fill_missing(df, method="bfill")
        assert result["a"].iloc[1] == 3

    def test_bfill_trailing_nan(self):
        """后向填充无法填充末尾的 NaN。"""
        df = pd.DataFrame({"a": [1, 2, None]})
        result = DataCleaner.fill_missing(df, method="bfill")
        assert result["a"].iloc[2] is None or pd.isna(result["a"].iloc[2])

    def test_mean_fill(self):
        df = pd.DataFrame({"a": [10, None, 20, None, 30]})
        result = DataCleaner.fill_missing(df, method="mean")
        assert result["a"].iloc[1] == pytest.approx(20.0)
        assert result["a"].iloc[3] == pytest.approx(20.0)

    def test_median_fill(self):
        df = pd.DataFrame({"a": [1, None, 3, None, 100]})
        result = DataCleaner.fill_missing(df, method="median")
        assert result["a"].iloc[1] == pytest.approx(3.0)

    def test_invalid_method(self):
        """无效方法应抛出 ValueError。"""
        df = pd.DataFrame({"a": [1, 2]})
        with pytest.raises(ValueError, match="不支持的填充方法"):
            DataCleaner.fill_missing(df, method="invalid")

    def test_columns_filter(self):
        """指定 columns 时只处理指定列。"""
        df = pd.DataFrame({"a": [1, None, 3], "b": [None, 2, None]})
        result = DataCleaner.fill_missing(df, method="ffill", columns=["a"])
        assert result["a"].isna().sum() == 0
        assert result["b"].isna().sum() == 2  # b 列未处理

    def test_no_missing_values(self):
        """无缺失值时不改变数据。"""
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = DataCleaner.fill_missing(df, method="ffill")
        assert result["a"].tolist() == [1, 2, 3]

    def test_does_not_modify_original(self):
        """确认不会修改原始 DataFrame。"""
        df = pd.DataFrame({"a": [1, None, 3]})
        DataCleaner.fill_missing(df, method="ffill")
        assert df["a"].isna().sum() == 1  # 原始仍有一个 NaN


class TestRemoveOutliers:
    """remove_outliers 白盒测试。"""

    def test_iqr_removes_extreme(self):
        df = pd.DataFrame({"v": [1, 2, 3, 4, 5, 100]})
        result = DataCleaner.remove_outliers(df, "v", method="iqr")
        assert 100 not in result["v"].values
        assert len(result) < len(df)

    def test_iqr_no_outliers(self):
        """无明显异常值时保留全部数据。"""
        df = pd.DataFrame({"v": [10, 11, 12, 11, 10]})
        result = DataCleaner.remove_outliers(df, "v", method="iqr")
        assert len(result) == 5

    def test_zscore_removes_outliers(self):
        df = pd.DataFrame({"v": [10, 10, 10, 10, 10, 10, 10, 10, 10, 100]})
        result = DataCleaner.remove_outliers(df, "v", method="zscore", threshold=2.0)
        assert 100 not in result["v"].values

    def test_zscore_zero_std(self):
        """标准差为0时不做任何剔除。"""
        df = pd.DataFrame({"v": [5, 5, 5, 5]})
        result = DataCleaner.remove_outliers(df, "v", method="zscore")
        assert len(result) == 4

    def test_column_not_found(self):
        """列不存在时返回原始 DataFrame。"""
        df = pd.DataFrame({"v": [1, 2, 3]})
        result = DataCleaner.remove_outliers(df, "nonexistent")
        assert len(result) == 3

    def test_invalid_method(self):
        df = pd.DataFrame({"v": [1, 2, 3]})
        with pytest.raises(ValueError, match="不支持的异常值方法"):
            DataCleaner.remove_outliers(df, "v", method="invalid")

    def test_index_reset(self):
        """确认结果 reset_index。"""
        df = pd.DataFrame({"v": [1, 2, 3, 100]})
        result = DataCleaner.remove_outliers(df, "v", method="iqr")
        assert result.index.tolist() == list(range(len(result)))


class TestAlignDates:
    """align_dates 白盒测试。"""

    def test_basic_intersection(self):
        df1 = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=5), "v": range(5)})
        df2 = pd.DataFrame({"date": pd.date_range("2025-01-03", periods=5), "v": range(5)})
        aligned = DataCleaner.align_dates(df1, df2)
        assert len(aligned[0]) == 3  # 交集为 01-03, 01-04, 01-05
        assert len(aligned[1]) == 3

    def test_no_overlap(self):
        """无交集时返回空 DataFrame。"""
        df1 = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=3), "v": range(3)})
        df2 = pd.DataFrame({"date": pd.date_range("2025-06-01", periods=3), "v": range(3)})
        aligned = DataCleaner.align_dates(df1, df2)
        assert len(aligned[0]) == 0
        assert len(aligned[1]) == 0

    def test_three_dataframes(self):
        df1 = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=10)})
        df2 = pd.DataFrame({"date": pd.date_range("2025-01-05", periods=10)})
        df3 = pd.DataFrame({"date": pd.date_range("2025-01-08", periods=10)})
        aligned = DataCleaner.align_dates(df1, df2, df3)
        assert len(aligned[0]) == len(aligned[1]) == len(aligned[2])

    def test_string_dates(self):
        """非 datetime 类型的日期列也能对齐。"""
        df1 = pd.DataFrame({"date": ["2025-01-01", "2025-01-02", "2025-01-03"]})
        df2 = pd.DataFrame({"date": ["2025-01-02", "2025-01-03", "2025-01-04"]})
        aligned = DataCleaner.align_dates(df1, df2)
        assert len(aligned[0]) == 2


class TestNormalize:
    """normalize 白盒测试。"""

    def test_minmax_basic(self):
        df = pd.DataFrame({"v": [0, 5, 10]})
        result = DataCleaner.normalize(df, ["v"], method="minmax")
        assert result["v"].min() == 0.0
        assert result["v"].max() == 1.0

    def test_minmax_constant(self):
        """max == min 时不做归一化。"""
        df = pd.DataFrame({"v": [5, 5, 5]})
        result = DataCleaner.normalize(df, ["v"], method="minmax")
        assert result["v"].tolist() == [5, 5, 5]

    def test_zscore_basic(self):
        df = pd.DataFrame({"v": [1, 2, 3, 4, 5]})
        result = DataCleaner.normalize(df, ["v"], method="zscore")
        assert result["v"].mean() == pytest.approx(0, abs=1e-10)
        assert result["v"].std() == pytest.approx(1, abs=1e-10)

    def test_zscore_zero_std(self):
        """std == 0 时不做标准化。"""
        df = pd.DataFrame({"v": [7, 7, 7]})
        result = DataCleaner.normalize(df, ["v"], method="zscore")
        assert result["v"].tolist() == [7, 7, 7]

    def test_column_not_found_skipped(self):
        """不存在的列被跳过，不报错。"""
        df = pd.DataFrame({"v": [1, 2, 3]})
        result = DataCleaner.normalize(df, ["nonexistent"], method="minmax")
        assert "v" in result.columns

    def test_multi_column(self):
        df = pd.DataFrame({"a": [0, 10], "b": [100, 200]})
        result = DataCleaner.normalize(df, ["a", "b"], method="minmax")
        assert result["a"].tolist() == [0.0, 1.0]
        assert result["b"].tolist() == [0.0, 1.0]


class TestCalcReturns:
    """calc_returns 白盒测试。"""

    def test_default_periods(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=25),
            "close": range(25)
        })
        result = DataCleaner.calc_returns(df)
        assert "return_1d" in result.columns
        assert "return_5d" in result.columns
        assert "return_20d" in result.columns

    def test_first_row_nan(self):
        """第一行 1d 收益率应为 NaN。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "close": [10, 11, 12, 13, 14]
        })
        result = DataCleaner.calc_returns(df, periods=[1])
        assert pd.isna(result["return_1d"].iloc[0])

    def test_custom_periods(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=30),
            "close": range(30)
        })
        result = DataCleaner.calc_returns(df, periods=[3, 7])
        assert "return_3d" in result.columns
        assert "return_7d" in result.columns
        assert "return_1d" not in result.columns

    def test_percentage_format(self):
        """收益率应以百分比形式存储。"""
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=3),
            "close": [100, 110, 121]
        })
        result = DataCleaner.calc_returns(df, periods=[1])
        assert result["return_1d"].iloc[1] == pytest.approx(10.0)  # 10%
        assert result["return_1d"].iloc[2] == pytest.approx(10.0)  # 10%


class TestCalcMA:
    """calc_ma 白盒测试。"""

    def test_default_windows(self):
        df = pd.DataFrame({"close": range(70)})
        result = DataCleaner.calc_ma(df)
        assert "ma5" in result.columns
        assert "ma10" in result.columns
        assert "ma20" in result.columns
        assert "ma60" in result.columns

    def test_first_n_nan(self):
        """前 w-1 行 ma 应为 NaN。"""
        df = pd.DataFrame({"close": range(10)})
        result = DataCleaner.calc_ma(df, windows=[5])
        assert pd.isna(result["ma5"].iloc[0])
        assert pd.isna(result["ma5"].iloc[3])
        assert not pd.isna(result["ma5"].iloc[4])

    def test_ma_value_correctness(self):
        """验证 MA 计算值正确。"""
        df = pd.DataFrame({"close": [10, 20, 30, 40, 50]})
        result = DataCleaner.calc_ma(df, windows=[5])
        assert result["ma5"].iloc[4] == pytest.approx(30.0)  # (10+20+30+40+50)/5


class TestFullPipeline:
    """full_pipeline 白盒测试。"""

    def test_pipeline_adds_columns(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=70),
            "close": [10 + i * 0.3 for i in range(70)],
            "volume": [1000 + i * 10 for i in range(70)],
        })
        result = DataCleaner.full_pipeline(df)
        assert "ma5" in result.columns
        assert "ma20" in result.columns
        assert "return_1d" in result.columns
        assert "return_5d" in result.columns
        assert "return_20d" in result.columns

    def test_pipeline_fills_missing(self):
        """pipeline 应填充缺失值。"""
        n = 70
        closes = [10, None, 12, None, 14] + list(range(15, 80))  # 5 + 65 = 70
        vols = [100, None, 300, None, 500] + list(range(600, 665))  # 5 + 65 = 70
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n),
            "close": closes,
            "volume": vols,
        })
        result = DataCleaner.full_pipeline(df)
        assert result["close"].isna().sum() == 0
