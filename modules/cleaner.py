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
    def deduplicate(df, on="date", keep="last"):
        """按 on 列去重（默认保留最后一条），并保持原有行序。

        行情接口常返回重复日期行（如复权切分、源数据脏数据），重复行会令
        pct_change / 均线计算错位，故作为标准清洗步骤提供。
        """
        if on not in df.columns:
            return df.copy()
        return df.drop_duplicates(subset=[on], keep=keep).reset_index(drop=True)

    @staticmethod
    def align_dates(*dataframes, on="date"):
        """
        将多个 DataFrame 按日期对齐（取交集）。
        :param dataframes: 多个 DataFrame
        :param on: 对齐的列名
        """
        if not dataframes:
            raise ValueError("align_dates 至少需要一个 DataFrame")
        aligned = []
        common_dates = None
        for df in dataframes:
            if on not in df.columns:
                raise ValueError(f"对齐列 {on!r} 不存在于输入 DataFrame")
            dates = set(df[on].dt.strftime("%Y-%m-%d")) if pd.api.types.is_datetime64_any_dtype(df[on]) else set(df[on])
            if common_dates is None:
                common_dates = dates
            else:
                common_dates = common_dates & dates

        for df in dataframes:
            mask = df[on].dt.strftime("%Y-%m-%d").isin(common_dates) if pd.api.types.is_datetime64_any_dtype(df[on]) else df[on].isin(common_dates)
            sub = df[mask].copy()
            # 隐性缺陷修复：旧实现各帧保留各自原始行序，交集日期在两帧中的先后顺序可能不同，
            # 导致「对齐」后第 i 行在两帧里其实对应不同日期（静默错位，下游成对计算全错）。
            # 现统一按 on 升序排序，保证所有对齐帧按同一日期顺序一一对应。
            sub = sub.sort_values(on, kind="mergesort").reset_index(drop=True)
            aligned.append(sub)
        return tuple(aligned)

    @staticmethod
    def sort_by_date(df, on="date"):
        """把 date 列解析为 datetime 并按升序排序，返回排序后的副本。

        新能力：下游指标（均线 / 收益率 / ATR）普遍假设输入按时间升序；此前调用方
        各自重复 ``pd.to_datetime`` + ``sort_values``。本函数提供统一、可单测的入口，
        并供 ``align_dates`` 复用，保证对齐后行序一致。
        """
        if on not in df.columns:
            return df.copy()
        out = df.copy()
        out[on] = pd.to_datetime(out[on], errors="coerce")
        return out.sort_values(on, kind="mergesort").reset_index(drop=True)

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
    def calc_returns(df, price_col="close", periods=None):
        """
        计算收益率。
        :param periods: [1日, 5日(周), 20日(月)] 收益率；默认 [1, 5, 20]
        """
        if periods is None:
            periods = [1, 5, 20]
        df = df.copy()
        # 防御性数值化：脏值列（object dtype）先 coerce，避免 pct_change 内部除法抛 TypeError
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
        for p in periods:
            df[f"return_{p}d"] = df[price_col].pct_change(p) * 100
        return df

    @staticmethod
    def calc_ma(df, price_col="close", windows=None):
        """计算移动平均线。默认窗口 [5, 10, 20, 60]。"""
        if windows is None:
            windows = [5, 10, 20, 60]
        df = df.copy()
        # 防御性数值化：脏值列（object dtype）先 coerce，避免 rolling.mean 在对象列上报错
        if price_col in df.columns:
            df[price_col] = pd.to_numeric(df[price_col], errors="coerce")
        for w in windows:
            df[f"ma{w}"] = df[price_col].rolling(window=w).mean()
        return df

    @staticmethod
    def full_pipeline(df):
        """一键清洗：缺失值填充 + 异常值处理 + 收益率 + 均线。"""
        df = df.copy()
        # ══ 加法式健壮性（c41）：OHLCV 列强制数值化，脏值（'x'/'n/a'/空串/None）
        # 转为 NaN 而非保留 object dtype。否则后续 pct_change/rolling 除法会抛
        # `TypeError: unsupported operand type(s) for /: 'str' and 'int'` 崩整条
        # 清洗管线，导致该股票的 K线+技术分析全失败（真实脏数据：接口偶发坏值/手工CSV笔误）。
        for _c in ("open", "high", "low", "close", "volume"):
            if _c in df.columns:
                df[_c] = pd.to_numeric(df[_c], errors="coerce")
        df = DataCleaner.fill_missing(df, method="ffill")
        df = DataCleaner.fill_missing(df, method="bfill")
        df = DataCleaner.calc_returns(df)
        df = DataCleaner.calc_ma(df)
        return df
