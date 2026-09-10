"""用 BaoStock 重建 2007–2014（及任意区间）全市场广度历史。

为什么需要这个脚本（R33 发现 + R34 探活）：
    `scripts/run_shepherd_reconstruct` 依赖 akshare 新浪个股日线 + 牧羊人/legu 涨跌停池；
    上游免费 API 只回「最近 30 个交易日」的涨跌停池，故 2007–2014 历史广度**取不到**。
    BaoStock（已装在 envs/default venv、沙箱网络可达）提供逐股日线（含 pctChg），可反推广度：
        limit_up/down 家数（pctChg≥9.5 / ≤-9.5 近似）
        red_ratio（上涨家数占比）
        median_chg（中位数涨跌幅）
    从而补齐 2007–2014 这段缺失的历史广度。

性能设计（关键）：
    初版按「逐日 × 逐股」拉取 = O(交易日×个股) ≈ 数百万次请求，不可行。
    本版改为「逐股拉整段历史」= O(个股) ≈ 几千次请求：每只股票一次取 2007–2014 全段日线，
    再在客户端按日聚合广度。某股在某日无数据（未上市/已退市）则自然不计入该日分母。
    股票全集由「早期某日 + 末期某日」的 query_all_stock 取并集，尽量覆盖期间退市股。

用法：
    # 冒烟（限量股票 + 短区间，验证可取数）：
    python -m scripts.reconstruct_breadth_baostock --start 2007-01-01 --end 2007-03-31 --max-codes 40 --out /tmp/bs_smoke.csv

    # 全量（联网机后台长跑；输出到独立文件，并入主表前务必先备份 data/shepherd_history.csv）：
    python -m scripts.reconstruct_breadth_baostock --start 2007-01-01 --end 2014-12-31 \
        --out data/shepherd_history_baostock.csv

注意：
    - 全量 = 全市场个股 × 整段历史，量级几千次请求；内置每请求后 sleep 与失败重试 + 退避，避免频控。
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
import socket
import sys
import time

logger = logging.getLogger(__name__)


def _login():
    import baostock as bs  # 延迟导入，避免无网络时 import 失败拖垮整个模块
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"BaoStock 登录失败: {lg.error_code} {lg.error_msg}")
    # 关键护栏：给全部 socket 操作设默认超时。
    # 踩过的坑（2026-09-09）：无此超时时，某只股票的 query_history_k_data_plus 网络挂起会
    # 永久阻塞且不抛异常 -> fetch_stock_history 的 tries=3 重试永远触发不了 ->
    # 全量任务 47 分钟零进度（状态 running 却不出活，实为死锁）。
    socket.setdefaulttimeout(25)
    return bs


def _write_csv(out: str, daily: dict) -> int:
    """把按日聚合好的广度落盘（覆盖写、按日期排序）。运行中可多次调用做检查点。"""
    rows = 0
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "n_stocks", "limit_up", "limit_down", "red_ratio", "median_chg"])
        for d in sorted(daily):
            pcts = sorted(daily[d])
            n = len(pcts)
            if n == 0:
                continue
            ups = sum(1 for p in pcts if p >= 9.5)
            downs = sum(1 for p in pcts if p <= -9.5)
            reds = sum(1 for p in pcts if p > 0)
            median = pcts[n // 2] if n % 2 else (pcts[n // 2 - 1] + pcts[n // 2]) / 2.0
            w.writerow([d, n, ups, downs, round(reds / n * 100, 2), round(median, 4)])
            rows += 1
    return rows


def get_trade_dates(bs, start: str, end: str) -> list[str]:
    """返回 [start, end] 区间内的真实交易日列表（BaoStock 正确迭代写法）。"""
    rs = bs.query_trade_dates(start_date=start, end_date=end)
    dates: list[str] = []
    while rs.next():
        row = rs.get_row_data()
        if not row:
            break
        # row = [date, is_trading_day('1'/'0')]
        d, flag = row[0], row[1]
        if flag == "1":
            dates.append(d)
    logger.info("[bs_breadth] 区间内交易日 %d 个", len(dates))
    return dates


def get_universe(bs, seed_dates: list[str]) -> list[str]:
    """取多日股票全集的并集（覆盖期间退市股）。过滤指数代码。"""
    codes: set[str] = set()
    for d in seed_dates:
        try:
            rs = bs.query_all_stock(day=d)
        except Exception as e:  # noqa: BLE001
            logger.warning("[bs_breadth] query_all_stock(%s) 失败: %s", d, e)
            continue
        while rs.next():
            row = rs.get_row_data()
            if not row:
                break
            code = row[0]
            if code.startswith(("sh.000", "sz.399", "sh.950", "sz.395")):
                continue
            codes.add(code)
    logger.info("[bs_breadth] 股票全集 %d 只（种子日 %s）", len(codes), seed_dates)
    return sorted(codes)


def fetch_stock_history(bs, code: str, start: str, end: str, tries: int = 3) -> dict:
    """取单只股票整段日线，返回 {date: pctChg}。失败重试 + 退避。"""
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            rs = bs.query_history_k_data_plus(
                code, "date,pctChg",
                start_date=start, end_date=end,
                frequency="d", adjustflag="3",
            )
            out: dict = {}
            while rs.next():
                row = rs.get_row_data()
                if not row or not row[1]:
                    continue
                out[row[0]] = float(row[1])
            return out
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("[bs_breadth] %s 取数异常(第%d次): %s", code, attempt, e)
            time.sleep(2 * attempt)
    if last_err:
        logger.warning("[bs_breadth] %s 放弃: %s", code, last_err)
    return {}


def reconstruct(start: str, end: str, out: str, sleep: float = 0.05,
                max_codes: int | None = None) -> int:
    bs = _login()
    try:
        # 种子日必须是有交易的真实交易日，否则 query_all_stock 返回空
        trade_dates = get_trade_dates(bs, start, end)
        seeds = [trade_dates[0], trade_dates[-1]] if trade_dates else [start, end]
        universe = get_universe(bs, seeds)
        if max_codes:
            universe = universe[:max_codes]

        # 按日聚合广度
        daily: dict[str, list[float]] = {}
        total = len(universe)
        for i, code in enumerate(universe, 1):
            hist = fetch_stock_history(bs, code, start, end)
            for d, pct in hist.items():
                daily.setdefault(d, []).append(pct)
            time.sleep(sleep)
            # 每 50 只打一次进度（原为每 200：粒度太粗，死锁时 47 分钟都看不出是卡了还是慢）
            if i % 50 == 0 or i == total:
                logger.info("[bs_breadth] 进度 %d/%d，已聚合 %d 个交易日", i, total, len(daily))
            # 每 500 只落一次检查点：中途崩溃/被杀时保住已完成部分，不会整轮白跑
            if i % 500 == 0:
                chk = _write_csv(out, daily)
                logger.info("[bs_breadth] 检查点：已落盘 %d 交易日 -> %s", chk, out)

        rows = _write_csv(out, daily)
        logger.info("[bs_breadth] 完成：%d 个交易日 -> %s", rows, out)
        return rows
    finally:
        bs.logout()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="BaoStock 全市场广度历史重建（补齐 2007-2014）")
    p.add_argument("--start", default="2007-01-01")
    p.add_argument("--end", default="2014-12-31")
    p.add_argument("--out", default="data/shepherd_history_baostock.csv")
    p.add_argument("--max-codes", type=int, default=None, help="限制股票数（冒烟用）")
    p.add_argument("--sleep", type=float, default=0.05, help="每请求间隔秒（限速）")
    args = p.parse_args()
    n = reconstruct(args.start, args.end, args.out, args.sleep, args.max_codes)
    logger.info("[bs_breadth] 共写出 %d 行", n)


if __name__ == "__main__":
    main()
