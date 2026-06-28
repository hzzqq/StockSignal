"""
数据清洗与预处理模块
负责缺失值处理、复权调整、异常值识别、时间对齐等。
"""

import numpy as np
import pandas as pd


class DataCleaner:
    """行情数据清洗器。"""

    @staticmethod
    def fill_missing(df, method="ffill", columns=None):
        """
        填充缺失值。
        :param method: ffill(前向填充) / bfill(后向填充) / mean(均值) / median(中位数)
        :param columns: 指定列，None 则处理全部数值列
        """
        df = df.copy()
        target_cols = columns or df.select_dtypes(include=[np.number]).columns.tolist()

        if method == "ffill":
            df[target_cols] = df[target_cols].ffill()
        elif method == "bfill":
            df[target_cols] = df[target_cols].bfill()
        elif method == "mean":
            df[target_cols] = df[target_cols].fillna(df[target_cols].mean())
        elif method == "median":
            df[target_cols] = df[target_cols].fillna(df[target_cols].median())
        else:
            raise ValueError(f"不支持的填充方法: {method}")
        return df

    @staticmethod
    def remove_outliers(df, column, method="iqr", threshold=3.0):
        """
        异常值识别与剔除。
        :param column: 目标列名
        :param method: iqr(四分位距法) / zscore(Z分数法)
        :param threshold: iqr 模式为倍数(1.5)，zscore 模式为标准差倍数(3.0)
        """
        df = df.copy()
        if column not in df.columns:
            return df

        if method == "iqr":
            q1 = df[column].quantile(0.25)
            q3 = df[column].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            df = df[(df[column] >= lower) & (df[column] <= upper)]
        elif method == "zscore":
            mean = df[column].mean()
            std = df[column].std()
            if std > 0:
                z = np.abs((df[column] - mean) / std)
                df = df[z < threshold]
        else:
            raise ValueError(f"不支持的异常值方法: {method}")
        return df.reset_index(drop=True)

    @staticmethod
    def align_dates(*dataframes, on="date"):
        """
        将多个 DataFrame 按日期对齐（取交集）。
        :param dataframes: 多个 DataFrame
        :param on: 对齐的列名
        """
        aligned = []
        common_dates = None
        for df in dataframes:
            dates = set(df[on].dt.strftime("%Y-%m-%d")) if pd.api.types.is_datetime64_any_dtype(df[on]) else set(df[on])
            if common_dates is None:
                common_dates = dates
            else:
                common_dates = common_dates & dates

        for df in dataframes:
            mask = df[on].dt.strftime("%Y-%m-%d").isin(common_dates) if pd.api.types.is_datetime64_any_dtype(df[on]) else df[on].isin(common_dates)
            aligned.append(df[mask].reset_index(drop=True))
        return tuple(aligned)

    @staticmethod
    def normalize(df, columns, method="minmax"):
        """
        归一化处理。
        :param method: minmax(0-1归一化) / zscore(标准化)
        """
        df = df.copy()
        for col in columns:
            if col not in df.columns:
                continue
            if method == "minmax":
                min_val = df[col].min()
                max_val = df[col].max()
                if max_val > min_val:
                    df[col] = (df[col] - min_val) / (max_val - min_val)
            elif method == "zscore":
                mean = df[col].mean()
                std = df[col].std()
                if std > 0:
                    df[col] = (df[col] - mean) / std
        return df

    @staticmethod
    def calc_returns(df, price_col="close", periods=[1, 5, 20]):
        """
        计算收益率。
        :param periods: [1日, 5日(周), 20日(月)] 收益率
        """
        df = df.copy()
        for p in periods:
            df[f"return_{p}d"] = df[price_col].pct_change(p) * 100
        return df

    @staticmethod
    def calc_ma(df, price_col="close", windows=[5, 10, 20, 60]):
        """计算移动平均线。"""
        df = df.copy()
        for w in windows:
            df[f"ma{w}"] = df[price_col].rolling(window=w).mean()
        return df

    @staticmethod
    def full_pipeline(df):
        """一键清洗：缺失值填充 + 异常值处理 + 收益率 + 均线。"""
        df = DataCleaner.fill_missing(df, method="ffill")
        df = DataCleaner.fill_missing(df, method="bfill")
        df = DataCleaner.calc_returns(df)
        df = DataCleaner.calc_ma(df)
        return df
