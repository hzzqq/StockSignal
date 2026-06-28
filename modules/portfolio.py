"""
仓位管理模块
记录持仓、计算盈亏、导出 Excel 报告。
"""

import os
from datetime import datetime

import pandas as pd
import yaml

from .fetcher import StockFetcher, load_config


class PortfolioManager:
    """仓位管理器。"""

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        self.fetcher = StockFetcher(config_path)
        self.file_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.get("portfolio", {}).get("file", "data/portfolio.csv")
        )
        self._ensure_file()

    def _ensure_file(self):
        """确保持仓文件存在。"""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=[
                "ticker", "name", "buy_date", "buy_price", "shares",
                "cost", "note"
            ])
            df.to_csv(self.file_path, index=False, encoding="utf-8-sig")

    def _load(self):
        return pd.read_csv(self.file_path, encoding="utf-8-sig")

    def _save(self, df):
        df.to_csv(self.file_path, index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------
    # 持仓操作
    # ------------------------------------------------------------------
    def add_position(self, ticker, name, buy_date, buy_price, shares, note=""):
        """添加一条持仓记录。"""
        df = self._load()
        cost = buy_price * shares
        new_row = pd.DataFrame([{
            "ticker": str(ticker),
            "name": name,
            "buy_date": buy_date,
            "buy_price": float(buy_price),
            "shares": int(shares),
            "cost": round(cost, 2),
            "note": note
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        self._save(df)
        return new_row.iloc[0].to_dict()

    def remove_position(self, index):
        """删除指定索引的持仓。"""
        df = self._load()
        if 0 <= index < len(df):
            removed = df.iloc[index].to_dict()
            df = df.drop(index).reset_index(drop=True)
            self._save(df)
            return removed
        return None

    def get_positions(self):
        """获取全部持仓。"""
        return self._load()

    # ------------------------------------------------------------------
    # 盈亏计算
    # ------------------------------------------------------------------
    def calc_pnl(self):
        """
        计算每只持仓的当前盈亏。
        :return: DataFrame[ticker, name, buy_date, buy_price, shares, cost,
                          current_price, market_value, pnl, pnl_pct]
        """
        df = self._load()
        if df.empty:
            return df

        results = []
        for _, row in df.iterrows():
            try:
                # 获取最新价
                daily = self.fetcher.get_daily(row["ticker"],
                                               start=row["buy_date"],
                                               end=datetime.now().strftime("%Y-%m-%d"))
                current_price = float(daily.iloc[-1]["close"]) if not daily.empty else float(row["buy_price"])
            except Exception:
                current_price = float(row["buy_price"])

            market_value = current_price * row["shares"]
            cost = row["cost"]
            pnl = market_value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            results.append({
                "ticker": row["ticker"],
                "name": row["name"],
                "buy_date": row["buy_date"],
                "buy_price": row["buy_price"],
                "shares": row["shares"],
                "cost": round(cost, 2),
                "current_price": round(current_price, 2),
                "market_value": round(market_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })

        return pd.DataFrame(results)

    def summary(self):
        """返回持仓汇总信息。"""
        pnl_df = self.calc_pnl()
        if pnl_df.empty:
            return {
                "total_cost": 0, "total_market_value": 0,
                "total_pnl": 0, "total_pnl_pct": 0, "position_count": 0
            }

        total_cost = pnl_df["cost"].sum()
        total_mv = pnl_df["market_value"].sum()
        total_pnl = pnl_df["pnl"].sum()

        return {
            "total_cost": round(total_cost, 2),
            "total_market_value": round(total_mv, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "position_count": len(pnl_df)
        }

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_excel(self, output_path=None):
        """
        导出持仓盈亏报告到 Excel。
        :return: 输出文件路径
        """
        pnl_df = self.calc_pnl()
        summary = self.summary()

        if output_path is None:
            output_path = os.path.join(
                os.path.dirname(self.file_path),
                f"portfolio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            # 汇总 sheet
            summary_df = pd.DataFrame([summary])
            summary_df.to_excel(writer, sheet_name="汇总", index=False)

            # 明细 sheet
            if not pnl_df.empty:
                pnl_df.to_excel(writer, sheet_name="持仓明细", index=False)

        return output_path

    # ------------------------------------------------------------------
    # 盈亏归因
    # ------------------------------------------------------------------
    def pnl_attribution(self):
        """
        盈亏归因分析：按个股统计盈亏贡献占比。
        :return: DataFrame[ticker, name, pnl, pnl_pct, contribution]
        """
        pnl_df = self.calc_pnl()
        if pnl_df.empty:
            return pnl_df

        total_pnl = pnl_df["pnl"].sum()
        pnl_df["contribution"] = pnl_df["pnl"].apply(
            lambda x: round(x / total_pnl * 100, 2) if total_pnl != 0 else 0
        )
        return pnl_df.sort_values("pnl", ascending=False).reset_index(drop=True)
