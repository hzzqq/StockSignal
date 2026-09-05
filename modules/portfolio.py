"""
仓位管理模块
记录持仓、计算盈亏、导出 Excel 报告。
"""

import os
from datetime import datetime

import pandas as pd

from .atomic_io import atomic_to_csv
from .fetcher import StockFetcher, load_config
from .format_helpers import to_float, safe_pct
from .finance_contract import validate_position_schema, validate_pnl_output
import logging

logger = logging.getLogger(__name__)


def _atomic_to_csv(df: pd.DataFrame, path: str) -> None:
    """原子写 CSV：委托共享实现 modules/atomic_io.atomic_to_csv。

    共享版把 tmp 名唯一化（pid + 线程 id + uuid）。原因见 atomic_io 模块文档：
    固定 tmp 名在多写者并发下会互相覆盖 tmp 并抛 PermissionError(WinError 32)，
    压测实测 160 次写入失败 7 次。保留本包装是为避免改动全部调用点。
    """
    atomic_to_csv(df, path)



# ----------------------------------------------------------------------
# 纯逻辑函数（无网络 / 无 IO，便于单元测试）
# 统一处理缺失键、None、除零、NaN / inf，保证空或退化输入不报错、不产生 NaN。
# ----------------------------------------------------------------------
def market_value_of(position):
    """单条持仓的市值（current_price*remaining_shares 或 price*shares）。

    缺失键 / None / 非数字 / NaN / inf 一律按 0 处理，绝不抛异常或产生 NaN。
    """
    if not isinstance(position, dict):
        return 0.0
    price = position.get("current_price", position.get("price"))
    shares = position.get("remaining_shares", position.get("shares"))
    price = to_float(price, default=0.0) or 0.0
    shares = to_float(shares, default=0.0) or 0.0
    return price * shares


def total_market_value(positions):
    """一组持仓的总市值；空输入 / None 直接返回 0.0（不抛异常）。"""
    if not positions:
        return 0.0
    try:
        return sum(market_value_of(p) for p in positions)
    except (TypeError, ValueError):
        return 0.0


def position_weights(positions):
    """每只持仓的市值占比（%）。

    返回 {ticker: weight}，权重 = 市值 / 总市值 * 100。
    - 空输入 -> {}
    - 总市值为 0 -> 各持仓权重为 0.0（避免出现 NaN）
    """
    if not positions:
        return {}
    total = total_market_value(positions)
    weights = {}
    for p in positions:
        if not isinstance(p, dict):
            continue
        ticker = p.get("ticker", "")
        if total == 0:
            weights[ticker] = 0.0
        else:
            weights[ticker] = round(market_value_of(p) / total * 100, 2)
    return weights


def position_pnl(current_price, remaining_shares, cost):
    """单条持仓未实现盈亏（市值 - 成本）。

    任意参数缺失 / None / 非数字 / NaN / inf 一律按 0 处理。
    """
    current_price = to_float(current_price, default=0.0) or 0.0
    remaining_shares = to_float(remaining_shares, default=0.0) or 0.0
    cost = to_float(cost, default=0.0) or 0.0
    return current_price * remaining_shares - cost


def allocate_fifo(positions, sold_map):
    """把每只股票的累计卖出股数按「先进先出」摊到各买入批次。

    ⚠️ 为什么必需（这是本函数存在的全部理由）：
    add_position 每买一次就 append 一行，所以**同一只股票分批建仓会有多行**
    （A 股最常见的加仓操作）。旧实现是

        remaining[ticker] = 该票总买入 - 该票总卖出
        df["remaining_shares"] = df["ticker"].map(remaining)

    即把「整只票的剩余股数」原封不动写进该票的**每一行**。两批建仓
    (100 股 + 200 股) 时两行的 remaining_shares 都是 300，于是 calc_pnl
    逐行算市值再求和 = 2×真实市值，成本按 cost_ratio=300/100=3 也一并放大，
    **持仓总市值 / 总成本 / 总盈亏全部成倍虚增**（实测 2.0x / 1.98x）。

    这里改为按买入日期升序、先买的批次先被卖出，逐行分配剩余股数，
    保证 Σ各行剩余 == 该票真实剩余。

    :param positions: 持仓 DataFrame（需含 ticker / shares，buy_date 可选）
    :param sold_map: {ticker: 累计已卖股数}
    :return: (remaining_per_row, consumed_per_row) 两个与 positions 行序对齐的列表
    """
    n = len(positions)
    remaining = [0] * n
    consumed = [0] * n
    if n == 0:
        return remaining, consumed

    shares = []
    for _, r in positions.iterrows():
        v = to_float(r.get("shares"), default=0.0) or 0.0
        shares.append(max(0, int(v)))

    # 按 ticker 分组；组内按买入日期升序，日期缺失/无法解析的排最后并保持原相对顺序
    groups = {}
    for pos, (_, r) in enumerate(positions.iterrows()):
        ticker = str(r.get("ticker", ""))
        dt = pd.to_datetime(r.get("buy_date"), errors="coerce")
        sort_key = (1, pos) if pd.isna(dt) else (0, dt.value)
        groups.setdefault(ticker, []).append((sort_key, pos))

    for ticker, entries in groups.items():
        entries.sort(key=lambda e: (e[0], e[1]))
        left = to_float(sold_map.get(ticker, 0), default=0.0) or 0.0
        left = max(0, int(left))
        for _, pos in entries:
            take = min(shares[pos], left)
            consumed[pos] = take
            remaining[pos] = shares[pos] - take
            left -= take
    return remaining, consumed


def compute_realized_fifo(buy_batches, sell_trades):
    """按先进先出（FIFO）计算整只股票的已实现盈亏。

    与 ``allocate_fifo`` 同一套 FIFO 契约：先买的批次先被卖出。每笔卖出交易
    按其卖出价，沿买入批次升序吃货，已实现盈亏 = Σ(卖出价 - 该批次买入价) × 吃货股数。

    :param buy_batches: [(buy_price, shares), ...]，调用方需按买入时间升序传入
    :param sell_trades: [(sell_price, sell_shares), ...]，调用方需按卖出时间升序传入
    :return: 整票已实现盈亏（四舍五入 2 位）
    """
    realized = 0.0
    batches = [[to_float(bp, default=0.0), max(0, int(sh))] for bp, sh in buy_batches]
    bi = 0
    for sp, sh in sell_trades:
        sp = to_float(sp, default=0.0)
        left = max(0, int(sh))
        while left > 0 and bi < len(batches):
            bp, avail = batches[bi]
            take = min(avail, left)
            if take > 0:
                realized += (sp - bp) * take
                batches[bi][1] = avail - take
                left -= take
            if batches[bi][1] <= 0:
                bi += 1
    return round(realized, 2)


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
        _atomic_to_csv(df, self.file_path)

    def _load_trades(self):
        if not os.path.exists(self._trades_path()):
            return pd.DataFrame(columns=[
                "ticker", "name", "sell_date", "sell_price", "sell_shares",
                "proceeds", "note"
            ])
        return pd.read_csv(self._trades_path(), encoding="utf-8-sig", dtype={"ticker": str})

    def _save_trades(self, df):
        _atomic_to_csv(df, self._trades_path())

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
            except Exception as e:
                logger.warning(f"[portfolio] 处理异常: {e}")
                name = ticker
        price = to_float(buy_price)
        shares_n = to_float(shares)
        if price is None or price <= 0:
            raise ValueError("买入价格必须为正数")
        if shares_n is None or shares_n <= 0:
            raise ValueError("买入股数必须为正数")
        shares_int = int(shares_n)
        cost = price * shares_int
        new_row = pd.DataFrame([{
            "ticker": ticker,
            "name": name,
            "buy_date": buy_date,
            "buy_price": price,
            "shares": shares_int,
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
        # 契约层 fail-fast：落盘数据缺必需列立即报错，避免下游 FIFO/市值算错
        validate_position_schema(df)
        if df.empty:
            return df
        trades = self._load_trades()
        if not trades.empty:
            sold = trades.groupby("ticker")["sell_shares"].sum().to_dict()
        else:
            sold = {}
        # ⚠️ 必须逐行 FIFO 分配，不能用 df["ticker"].map(整票剩余)：
        # 同票分批建仓有多行，map 会让每行都拿到整票剩余 → 市值/成本成倍虚增。
        remaining_list, _ = allocate_fifo(df, sold)
        df["remaining_shares"] = remaining_list
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
                # FIFO 批次顺序：买入按买入日期升序，卖出按卖出日期升序
                pos_sorted = t_positions.copy()
                pos_sorted["_bd"] = pd.to_datetime(pos_sorted.get("buy_date"), errors="coerce")
                pos_sorted = pos_sorted.sort_values("_bd")
                buy_batches = [(r["buy_price"], r["shares"]) for _, r in pos_sorted.iterrows()]
                tr_sorted = t_trades.copy()
                tr_sorted["_sd"] = pd.to_datetime(tr_sorted.get("sell_date"), errors="coerce")
                tr_sorted = tr_sorted.sort_values("_sd")
                sell_list = [(r["sell_price"], r["sell_shares"]) for _, r in tr_sorted.iterrows()]
                realized[ticker] = compute_realized_fifo(buy_batches, sell_list)

        # ⚠️ 已实现盈亏同样不能整票金额逐行照抄：同票多批次时逐行相加会重复计数。
        # 按各批次「实际被 FIFO 卖出的股数」占比摊分，保证 Σ各行 == 整票已实现盈亏。
        consumed_total = {}
        for _, row in df.iterrows():
            t = row["ticker"]
            used = max(0, int(row.get("shares", 0)) - int(row.get("remaining_shares", 0)))
            consumed_total[t] = consumed_total.get(t, 0) + used

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
            except Exception as e:
                logger.warning(f"[portfolio] 处理异常: {e}")
                current_price = float(row["buy_price"])

            # 行情接口可能返回 NaN / inf，落入则静默污染盈亏；兜底回退到买入价
            current_price = to_float(current_price, default=float(row["buy_price"]))

            remaining = int(row.get("remaining_shares", row["shares"]))
            # 用纯逻辑函数计算市值，缺失键 / None / NaN 均安全
            market_value = market_value_of({
                "current_price": current_price,
                "remaining_shares": remaining,
            })
            # 按剩余股数比例分摊成本
            cost_ratio = remaining / row["shares"] if row["shares"] > 0 else 0
            cost = round(row["cost"] * cost_ratio, 2)
            pnl = position_pnl(current_price, remaining, cost)
            pnl_pct = safe_pct(pnl, cost)

            # 该批次被卖出的股数占整票已卖出的比例，用于摊分已实现盈亏
            used = max(0, int(row.get("shares", 0)) - remaining)
            used_total = consumed_total.get(row["ticker"], 0)
            row_realized = (
                realized.get(row["ticker"], 0.0) * (used / used_total)
                if used_total > 0 else 0.0
            )

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
                "realized_pnl": round(row_realized, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })

        out = pd.DataFrame(results)
        # 契约层 fail-fast：输出列必须严格等于 PNL_OUTPUT_COLUMNS，
        # 防止日后重构误增删列导致持仓页/汇总渲染错位
        validate_pnl_output(out)
        return out

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
        # total_pnl 含已实现盈亏（calc_pnl 已产出 realized_pnl 列），避免总盈亏漏算已平仓收益
        total_pnl = (pnl_df["pnl"] + pnl_df["realized_pnl"]).sum()

        return {
            "total_cost": round(total_cost, 2),
            "total_market_value": round(total_mv, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(safe_pct(total_pnl, total_cost), 2),
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
            lambda r: round(safe_pct(r["pnl"], r["cost"]), 2),
            axis=1
        )

        total_pnl = grouped["pnl"].sum()
        grouped["contribution"] = grouped["pnl"].apply(
            lambda x: round(x / total_pnl * 100, 2) if total_pnl != 0 else 0
        )
        return grouped.sort_values("pnl", ascending=False).reset_index(drop=True)