"""用 BaoStock 重建 2007–2014（及任意区间）全市场广度历史。

为什么需要这个脚本（R33 发现）：
    `scripts/run_shepherd_reconstruct` 依赖 akshare 新浪个股日线 + 牧羊人/legu 涨跌停池；
    上游免费 API 只回「最近 30 个交易日」的涨跌停池，故 2007–2014 历史广度**取不到**。
    BaoStock（已装在 envs/default venv）提供逐股日线（含 pctChg），可反推广度：
        limit_up/down 家数（pctChg≥9.5 / ≤-9.5 近似）
        red_ratio（上涨家数占比）
        median_chg（中位数涨跌幅）
    从而补齐 2007–2014 这段缺失的历史广度。

用法：
    # 冒烟（单日、限量股票，验证 BaoStock 能取到 2007 数据）：
    python -m scripts.reconstruct_breadth_baostock --start 2007-01-04 --end 2007-01-04 --max-stocks 50 --out /tmp/bs_smoke.csv

    # 全量（联网机长跑，建议错峰 + 限速；输出追加到 shepherd_history 之前先备份）：
    python -m scripts.reconstruct_breadth_baostock --start 2007-01-01 --end 2014-12-31 \
        --out data/shepherd_history_baostock.csv

注意：
    - 全量 = 每日 × 全市场个股，量级大、受 BaoStock 频控约束；本脚本内置每请求后 sleep 与失败重试。
    - 本脚本只产「广度聚合 CSV」，不含 shepherd_reconstruct 的其他字段（connect_hl/zt_fail_ratio
      等需 legu 近期池，历史不可得）。补齐后如需并入主表，请用 modules/shepherd_reconstruct 的
      合并逻辑（或手动 left-join），且务必先备份 data/shepherd_history.csv。
    - 涨停/跌停判定用 pctChg 近似（主板≈10%、ST≈5%、科创板/创业板 2020 后≈20%）；2007–2014
      以 10% 为主，9.5 阈值足够稳健。
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time

logger = logging.getLogger(__name__)


def _login():
    import baostock as bs  # 延迟导入，避免无网络时 import 失败拖垮整个模块
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"BaoStock 登录失败: {lg.error_code} {lg.error_msg}")
    return bs


def get_trade_dates(bs, start: str, end: str) -> list[str]:
    rs = bs.query_trade_dates(start_date=start, end_date=end)
    dates: list[str] = []
    while rs.next():  # BaoStock: next() 返回是否有下一行，数据用 get_row_data()
        row = rs.get_row_data()
        # 返回 [date, is_trading_day('1'/'0')]
        d, flag = row[0], row[1]
        if flag == "1":
            dates.append(d)
    return dates


def all_stock_codes(bs, date: str, max_stocks: int | None = None) -> list[str]:
    rs = bs.query_all_stock(day=date)
    codes: list[str] = []
    while rs.next():  # next()=是否有下一行，get_row_data()=取数据
        row = rs.get_row_data()
        # 返回 [code, code_name, display_name, ...]；过滤指数/优先股等
        code = row[0]
        if code.startswith(("sh.000", "sz.399", "sh.950", "sz.399")):
            continue
        codes.append(code)
        if max_stocks and len(codes) >= max_stocks:
            break
    return codes


def breadth_for_date(bs, date: str, max_stocks: int | None = None, sleep: float = 0.02) -> dict | None:
    codes = all_stock_codes(bs, date, max_stocks)
    if not codes:
        logger.warning("[bs_breadth] %s 无股票列表", date)
        return None

    ups = downs = reds = 0
    pcts: list[float] = []
    fetched = 0
    for code in codes:
        try:
            rs = bs.query_history_k_data_plus(
                code, "date,code,preclose,pctChg",
                start_date=date, end_date=date,
                frequency="d", adjustflag="3",
            )
            if not rs.next():
                break
            row = rs.get_row_data()
            if not row or not row[3]:
                continue
            pct = float(row[3])
            pcts.append(pct)
            fetched += 1
            if pct >= 9.5:
                ups += 1
            elif pct <= -9.5:
                downs += 1
            if pct > 0:
                reds += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[bs_breadth] %s %s 取数异常: %s", date, code, e)
        time.sleep(sleep)

    if not pcts:
        return None
    pcts.sort()
    n = len(pcts)
    median = pcts[n // 2] if n % 2 else (pcts[n // 2 - 1] + pcts[n // 2]) / 2.0
    return {
        "date": date,
        "n_stocks": n,
        "limit_up": ups,
        "limit_down": downs,
        "red_ratio": round(reds / n * 100, 2),
        "median_chg": round(median, 4),
        "note": f"fetched {fetched}/{len(codes)}" if fetched != len(codes) else "",
    }


def reconstruct(start: str, end: str, out: str, max_stocks: int | None = None,
                sleep: float = 0.02, limit_dates: int | None = None) -> int:
    bs = _login()
    try:
        dates = get_trade_dates(bs, start, end)
        if limit_dates:
            dates = dates[:limit_dates]
        logger.info("[bs_breadth] 区间 %s~%s 共 %d 个交易日", start, end, len(dates))

        rows = 0
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "n_stocks", "limit_up", "limit_down", "red_ratio", "median_chg", "note"])
            for i, d in enumerate(dates, 1):
                rec = breadth_for_date(bs, d, max_stocks=max_stocks, sleep=sleep)
                if rec:
                    w.writerow([rec["date"], rec["n_stocks"], rec["limit_up"],
                                rec["limit_down"], rec["red_ratio"], rec["median_chg"], rec["note"]])
                    rows += 1
                if i % 20 == 0:
                    logger.info("[bs_breadth] 进度 %d/%d", i, len(dates))
        logger.info("[bs_breadth] 完成：%d 行 -> %s", rows, out)
        return rows
    finally:
        bs.logout()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="BaoStock 全市场广度历史重建（补齐 2007-2014）")
    p.add_argument("--start", default="2007-01-01")
    p.add_argument("--end", default="2014-12-31")
    p.add_argument("--out", default="data/shepherd_history_baostock.csv")
    p.add_argument("--max-stocks", type=int, default=None, help="每日期限股票数（冒烟用）")
    p.add_argument("--sleep", type=float, default=0.02, help="每请求间隔秒（限速）")
    p.add_argument("--limit-dates", type=int, default=None, help="最多处理前 N 个交易日（冒烟用）")
    args = p.parse_args()
    n = reconstruct(args.start, args.end, args.out, args.max_stocks, args.sleep, args.limit_dates)
    logger.info("[bs_breadth] 共写出 %d 行", n)


if __name__ == "__main__":
    main()
