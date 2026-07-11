"""
仓位管理模块
记录持仓、计算盈亏、导出 Excel 报告。
"""

import os
from datetime import datetime

import pandas as pd

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
        """确保持仓文件和交易文件存在。"""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            df = pd.DataFrame(columns=[
                "ticker", "name", "buy_date", "buy_price", "shares",
                "cost", "note"
            ])
            df.to_csv(self.file_path, index=False, encoding="utf-8-sig")

        # 卖出交易记录表
        trades_path = self._trades_path()
        if not os.path.exists(trades_path):
            df = pd.DataFrame(columns=[
                "ticker", "name", "sell_date", "sell_price", "sell_shares",
                "proceeds", "note"
            ])
            df.to_csv(trades_path, index=False, encoding="utf-8-sig")

    def _trades_path(self):
        """卖出记录文件路径。"""
        base, ext = os.path.splitext(self.file_path)
        return f"{base}_trades{ext}"

    def _load(self):
        return pd.read_csv(self.file_path, encoding="utf-8-sig", dtype={"ticker": str})

    def _save(self, df):
        df.to_csv(self.file_path, index=False, encoding="utf-8-sig")

    def _load_trades(self):
        if not os.path.exists(self._trades_path()):
            return pd.DataFrame(columns=[
                "ticker", "name", "sell_date", "sell_price", "sell_shares",
                "proceeds", "note"
            ])
        return pd.read_csv(self._trades_path(), encoding="utf-8-sig", dtype={"ticker": str})

    def _save_trades(self, df):
        df.to_csv(self._trades_path(), index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------
    # 持仓操作
    # ------------------------------------------------------------------
    def add_position(self, ticker, name=None, buy_date=None, buy_price=None, shares=None, note=""):
        """添加一条持仓记录。name 可由调用方传入；若未传入，则根据 ticker 自动查询。"""
        df = self._load()
        # 统一保存为 6 位字符串，防止 000021 被存成 21
        ticker = str(ticker).strip().zfill(6)
        if name is None:
            try:
                name = self.fetcher.get_stock_name(ticker) or ticker
            except Exception:
                name = ticker
        cost = buy_price * shares
        new_row = pd.DataFrame([{
            "ticker": ticker,
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

    def get_sellable_shares(self, ticker):
        """
        计算某只股票的剩余可卖股数。
        :return: 可卖股数（买入总数 - 已卖出总数）
        """
        ticker = str(ticker).strip().zfill(6)
        df = self._load()
        trades = self._load_trades()
        total_bought = int(df[df["ticker"] == ticker]["shares"].sum()) if not df.empty else 0
        total_sold = int(trades[trades["ticker"] == ticker]["sell_shares"].sum()) if not trades.empty else 0
        return max(0, total_bought - total_sold)

    def sell_position(self, ticker, sell_date, sell_price, sell_shares, note=""):
        """
        记录一笔卖出交易。
        :param ticker: 股票代码
        :param sell_date: 卖出日期，格式 "YYYY-MM-DD"
        :param sell_price: 卖出成交价
        :param sell_shares: 卖出股数
        :param note: 备注
        :return: 卖出记录字典
        :raises ValueError: 可卖股数不足或参数非法
        """
        ticker = str(ticker).strip().zfill(6)
        sell_shares = int(sell_shares)
        sell_price = float(sell_price)
        if sell_shares <= 0:
            raise ValueError("卖出股数必须大于 0")
        if sell_price <= 0:
            raise ValueError("卖出价格必须大于 0")

        sellable = self.get_sellable_shares(ticker)
        if sell_shares > sellable:
            raise ValueError(
                f"{ticker} 可卖股数不足：剩余 {sellable:,} 股，尝试卖出 {sell_shares:,} 股"
            )

        name = self.fetcher.get_stock_name(ticker) or ticker
        proceeds = round(sell_price * sell_shares, 2)
        trades = self._load_trades()
        new_row = pd.DataFrame([{
            "ticker": ticker,
            "name": name,
            "sell_date": sell_date,
            "sell_price": round(sell_price, 2),
            "sell_shares": sell_shares,
            "proceeds": proceeds,
            "note": note
        }])
        trades = pd.concat([trades, new_row], ignore_index=True)
        self._save_trades(trades)
        return new_row.iloc[0].to_dict()

    def get_trades(self):
        """获取全部卖出交易记录。"""
        return self._load_trades()

    def get_positions(self):
        """获取全部持仓，并附加剩余可卖股数。"""
        df = self._load()
        if df.empty:
            return df
        trades = self._load_trades()
        remaining = {}
        if not trades.empty:
            sold = trades.groupby("ticker")["sell_shares"].sum().to_dict()
        else:
            sold = {}
        for ticker in df["ticker"].unique():
            bought = int(df[df["ticker"] == ticker]["shares"].sum())
            remaining[ticker] = max(0, bought - sold.get(ticker, 0))
        df["remaining_shares"] = df["ticker"].map(remaining)
        return df

    # ------------------------------------------------------------------
    # 盈亏计算
    # ------------------------------------------------------------------
    def calc_pnl(self):
        """
        计算每只持仓的当前盈亏（按剩余股数计算）。
        :return: DataFrame[ticker, name, buy_date, buy_price, shares,
                          remaining_shares, cost, current_price, market_value,
                          realized_pnl, pnl, pnl_pct]
        """
        df = self.get_positions()
        if df.empty:
            return df

        trades = self._load_trades()
        realized = {}
        if not trades.empty:
            for ticker in trades["ticker"].unique():
                t_trades = trades[trades["ticker"] == ticker]
                t_positions = df[df["ticker"] == ticker]
                total_bought_shares = int(t_positions["shares"].sum())
                total_bought_cost = float((t_positions["buy_price"] * t_positions["shares"]).sum())
                avg_cost = total_bought_cost / total_bought_shares if total_bought_shares > 0 else 0
                total_sold_shares = int(t_trades["sell_shares"].sum())
                total_sold_proceeds = float((t_trades["sell_price"] * t_trades["sell_shares"]).sum())
                realized[ticker] = round(total_sold_proceeds - avg_cost * total_sold_shares, 2)

        results = []
        for _, row in df.iterrows():
            try:
                # 获取最新价：多往前取几天，防止买入日数据不足或接口异常
                buy_dt = pd.to_datetime(row["buy_date"])
                fetch_start = (buy_dt - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
                daily = self.fetcher.get_daily(
                    row["ticker"],
                    start=fetch_start,
                    end=datetime.now().strftime("%Y-%m-%d")
                )
                current_price = float(daily.iloc[-1]["close"]) if not daily.empty else float(row["buy_price"])
            except Exception:
                current_price = float(row["buy_price"])

            remaining = int(row.get("remaining_shares", row["shares"]))
            market_value = current_price * remaining
            # 按剩余股数比例分摊成本
            cost_ratio = remaining / row["shares"] if row["shares"] > 0 else 0
            cost = round(row["cost"] * cost_ratio, 2)
            pnl = market_value - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0

            results.append({
                "ticker": row["ticker"],
                "name": row["name"],
                "buy_date": row["buy_date"],
                "buy_price": row["buy_price"],
                "shares": row["shares"],
                "remaining_shares": remaining,
                "cost": cost,
                "current_price": round(current_price, 2),
                "market_value": round(market_value, 2),
                "realized_pnl": round(realized.get(row["ticker"], 0.0), 2),
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
        盈亏归因分析：按个股聚合统计盈亏贡献占比。
        :return: DataFrame[ticker, name, pnl, pnl_pct, contribution]
        """
        pnl_df = self.calc_pnl()
        if pnl_df.empty:
            return pnl_df

        # 按 ticker 聚合，汇总同一股票的多笔持仓
        grouped = pnl_df.groupby("ticker").agg({
            "name": "first",
            "cost": "sum",
            "market_value": "sum",
            "pnl": "sum",
        }).reset_index()
        grouped["pnl_pct"] = grouped.apply(
            lambda r: round(r["pnl"] / r["cost"] * 100, 2) if r["cost"] > 0 else 0,
            axis=1
        )

        total_pnl = grouped["pnl"].sum()
        grouped["contribution"] = grouped["pnl"].apply(
            lambda x: round(x / total_pnl * 100, 2) if total_pnl != 0 else 0
        )
        return grouped.sort_values("pnl", ascending=False).reset_index(drop=True)
