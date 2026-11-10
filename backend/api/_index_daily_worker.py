# -*- coding: utf-8 -*-
"""指数日线取数的「独立解释器」子进程入口（py_mini_racer / V8 隔离）。

⚠️ 本文件禁止在 Flask 进程内被 import；它只作为独立 Python 解释器执行。

背景（2026-11-10 真后端浏览器联调实测）：
    akshare 新浪日线的解码链路会实例化 py_mini_racer(V8)。在 Flask 进程内用
    fetch_many 多线程并发调用时，V8 的
    ``[FATAL:partition_address_space.cc(243)] Check failed:
    !IsConfigurablePoolInitialized()`` 属于 native 级崩溃，Python try/except
    捕获不到，会直接杀死整个后端进程——用户打开 V2 首页（顺带请求
    /api/v2/read/index-quotes）即可能打挂 5050。

为什么不用 ProcessPoolExecutor：
    Windows 以 spawn 启动子进程会重新导入 __main__；项目已有守卫
    tests/test_refresh_main_guard.py 明确要求触发进程池的入口必须自带
    ``if __name__ == "__main__"``，Flask 入口不满足该约束，且 lambda /
    DataFrame 的 pickle 边界更脆。这里改用「独立解释器 + 纯 JSON 管道」：
    零 pickle、零 __main__ 重导入，崩溃与超时天然被 subprocess 边界隔离。

协议（stdout NDJSON，一行一只指数）：
    {"symbol": "sh000001", "rows": [{"日期": "2026-11-11", "收盘": 3955.9, ...}]}
    {"symbol": "sz399001", "rows": []}       # 取数失败：空数组，不补 0
    父进程只接受能解析成上述形状的行；akshare 打到 stdout 的日志一律忽略。
    逐只 flush 的意义：即使第 N 只触发 native 崩溃，前 N-1 只已输出的数据
    仍能被父进程诚实使用，不必整批作废。

调用方：backend/api/read_routes.py::_w4x_index_daily_batch
本文件必须只依赖 akshare + 标准库，绝不 import Flask / app，否则子进程会
连带拉起整套后端，隔离就失去意义。
"""
from __future__ import annotations

import json
import sys

# 只读端点 limit 上限为 200（_w4b_limit hi=200），留 40 根余量控制管道体积。
_MAX_ROWS = 240
_COLS = ("日期", "开盘", "收盘", "最高", "最低", "成交量")


def _rows_for(df) -> list[dict]:
    """DataFrame -> 可 JSON 化的中文列 records；只取尾部，避免全历史灌进管道。"""
    if df is None or not hasattr(df, "columns") or len(df) == 0:
        return []
    cols = [c for c in _COLS if c in df.columns]
    if not cols:
        return []
    d = df[cols].tail(_MAX_ROWS).copy()
    if "日期" in d.columns:
        # 统一成 'YYYY-MM-DD' 字符串：避免 Timestamp / date 的 to_json 口径漂移，
        # 也让父进程 sort_values('日期') 的字典序与日期序保持一致。
        d["日期"] = d["日期"].astype(str).str[:10]
    try:
        return json.loads(d.to_json(orient="records", force_ascii=False,
                                    date_format="iso"))
    except Exception:  # noqa: BLE001 - 单只序列化失败只让该只缺失
        return []


def main(argv: list[str]) -> int:
    try:
        symbols = json.loads(argv[1]) if len(argv) > 1 else []
    except Exception:  # noqa: BLE001
        symbols = []
    if not isinstance(symbols, list):
        symbols = []
    try:
        import akshare as ak
    except Exception:  # noqa: BLE001 - import 失败：逐只诚实空数组
        ak = None
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol:
            continue
        rows: list[dict] = []
        if ak is not None:
            try:
                rows = _rows_for(ak.stock_zh_index_daily(symbol=symbol))
            except Exception:  # noqa: BLE001 - 取数失败只让该只缺失，不假装有数据
                rows = []
        # 逐只 flush：native 崩溃时前序结果仍留在管道里可被父进程读到
        try:
            sys.stdout.write(json.dumps({"symbol": symbol, "rows": rows},
                                        ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
