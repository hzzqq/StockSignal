"""fetcher_search — 名称/搜索/代码查询方法"""

import io
import json
import os
import re
import sqlite3
import threading
import time
import warnings
import logging as _logging
import urllib.request
import urllib.error
import urllib.parse
import contextlib
import socket  # 捕获瞬时网络错误（超时/连接重置/DNS）做重试兜底
from datetime import datetime, timedelta
import concurrent.futures as _cf
import yaml  # load_config 用到；原在抽离块内，抽到 _feed_io 后在此补回
import pandas as pd  # 原在抽离块内，StockFetcher 大量使用 DataFrame
import numpy as np  # 原在抽离块内，StockFetcher 用到 np.

from modules.time_utils import now_cst_str, now_cst_naive


# 底层 I/O 层已抽到 modules._feed_io（P2-1 降耦），此处 re-export 保持全站 import 兼容
from modules._feed_io import (  # noqa: F401
    _safe_urlopen,
    logger,
    _AK_OK,
    _BS_OK,
    CONFIG,
    SOURCE_METRICS,
    _record_source_metric,
    _observe_log,
    observe_source,
    observe_cache_fallback,
    observe_cache_hit,
    get_source_metrics,
    _is_market_open,
    _is_midday_break,
    _validate_sector_data,
    _retry_request,
    _symbol_to_secid,
    _index_to_secid,
    _symbol_to_bs,
    _symbol_to_sina,
    _BaoStockFetcher,
    _SinaFetcher,
    _UrllibFetcher,
)

# 市场数据 I/O 叶子模块（#锐评整改：从 StockFetcher 下沉，零循环依赖）
import modules._market_data_io as _mdi

# T-247 Tier1.1：纯函数真身迁 modules.fetcher_core，此处 re-export 同一对象
# （调用点零改动；AST 守卫 tests/test_fetcher_core_tier11.py 锁死防本地定义回潮）
from modules.fetcher_core import (  # noqa: F401
    _df_last_date,
    _get_sina_prefix,
    _get_stock_industry_keywords,
    _proc_cache_get,
    _proc_cache_set,
    _resample_kline,
    _resolve_cache_db_path,
    _safe_ident,
    _safe_kline_df,
    _synth_us_index_intraday,
    SAFE_IDENT_RE,
)

# 代理 IP 池（免费，best-effort 抗封禁）：仅当 SS_PROXY_POOL=1 时启用。
# 通过进程级 HTTPS_PROXY/HTTP_PROXY 让 akshare / requests 继承轮换出口 IP。
# 初始化失败绝不影响主流程（akshare 仍可直连）。baostock 是账号级限流，不受本池影响。
try:
    from modules.proxy_pool import get_proxy_pool as _get_proxy_pool
    _pp = _get_proxy_pool()
    if _pp.enabled:
        _pp.apply_to_env()
except Exception as _pp_err:  # noqa: BLE001
    logger.warning("代理 IP 池初始化失败（已忽略，回退直连）: %s", _pp_err)


# Tier1.1 安全拆分 pilot：纯函数 _safe_json_loads 迁入 modules.fetcher_core，
# 此处 re-export 保持行为零变化（fetcher.py 内部 509/519/547/1174 行调用不受影响）。
from modules.fetcher_core import _safe_json_loads  # noqa: F401



# R75 锁：flag 必须延迟读 modules.fetcher 模块对象（与 _feed_io._is_bs_available 同模式），
# 禁止 from _feed_io import _AK_OK（值拷贝会让 monkeypatch fetcher._AK_OK 失效）。
import modules.fetcher as _fetcher_mod


class SearchMixin:
    """Search 领域方法 mixin（机械搬移自 fetcher.py，签名/降级语义不变）。"""

    def get_all_codes(self, limit=None, random_seed=None):
        """
        返回本地股票库中所有 A 股代码列表。

        :param limit: 最多返回多少只（用于控制选股回测的股票池大小）
        :param random_seed: 如果指定，随机抽取 limit 只，保证可复现
        :return: list[str] 股票代码列表
        """
        self._warmup_stock_db()
        if self._stock_df is None or self._stock_df.empty:
            return []
        codes = self._stock_df["code"].astype(str).tolist()
        if random_seed is not None:
            import random
            rng = random.Random(random_seed)
            rng.shuffle(codes)
        if limit is not None and limit > 0:
            codes = codes[:limit]
        return codes

    def get_stock_basic(self, code):
        """根据代码返回 (code, name) 元组，未找到返回 (code, '')。"""
        self._warmup_stock_db()
        name = self._code_to_name.get(str(code), "")
        return str(code), name

    def get_name(self, code):
        """兼容旧调用：返回 (code, name) 元组，未找到名称时 name 回退为 code。"""
        c, n = self.get_stock_basic(code)
        return (c, n or code)

    def get_name_only(self, code):
        """返回纯股票名称（不含代码前缀）；本地库/BaoStock/akshare 强制获取名称，最后回退为代码本身。

        用于「名称」列展示，避免 get_stock_name 的「代码(名称)」格式把代码带进名称列。
        本函数会在本地库缺失时主动走网络源补全名称，而不是直接显示代码。
        """
        code = str(code).strip().zfill(6)
        if not code.isdigit() or len(code) != 6:
            return code

        # 1) 本地库命中
        name = self.get_stock_basic(code)[1]
        if name and name != code:
            return name

        # 2) 实例级缓存（避免同一进程内反复查网络）
        cache_key = f"_name_only_cache_{code}"
        cached = getattr(self, cache_key, None)
        if cached and cached != code:
            return cached

        # 3) BaoStock 查询
        try:
            if _fetcher_mod._BS_OK:
                bs_code = _symbol_to_bs(code)
                if _BaoStockFetcher._ensure_login():
                    rs = _BaoStockFetcher.bs.query_stock_basic(code=bs_code)
                    if rs.error_code == "0":
                        while rs.next():
                            row_data = rs.get_row_data()
                            if len(row_data) >= 2:
                                name = str(row_data[1]).strip()
                                if name and name != code:
                                    setattr(self, cache_key, name)
                                    return name
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")

        # 4) akshare 东方财富个股信息兜底
        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=code)
            if df is not None and not df.empty:
                info = dict(zip(df["item"], df["value"]))
                name = str(info.get("股票名称", "")).strip()
                if name and name != code:
                    setattr(self, cache_key, name)
                    return name
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")

        # 5) 记录缓存为“无名称”后回退代码
        setattr(self, cache_key, code)
        return code

    def get_stock_name(self, ticker):
        """
        根据股票代码查询股票名称。
        使用 BaoStock 查询，结果永久缓存（名称不会变）。
        返回 "代码(名称)" 格式，如 600519(贵州茅台)；查询失败仅返回代码。

        :param ticker: 股票代码，如 "600519" "000858"
        :return: 格式 "代码(名称)" 或 "代码"
        """
        if not ticker:
            return "<未知>"
        ticker = str(ticker).strip()

        # 从缓存读取
        conn = self._get_conn()
        try:
            name_table = "stock_name_cache"
            self._init_cache_table(conn, name_table)
            row = conn.execute(
                f"SELECT data_json FROM {name_table} WHERE cache_key = ?",
                (ticker,),
            ).fetchone()
            if row is not None:
                data = json.loads(row[0])
                name = data.get("name", "")
                if name:
                    return f"{ticker}({name})"

            # 缓存未命中 -> 查询 BaoStock（复用连接池）
            if _fetcher_mod._BS_OK:
                import baostock as bs  # 局部导入：与 _BS_OK 同源
                try:
                    if not _BaoStockFetcher._ensure_login():
                        name = self.get_name_only(ticker)
                        return f"{ticker}({name})" if name != ticker else ticker
                    bs_code = _symbol_to_bs(ticker)
                    rs = bs.query_stock_basic(code=bs_code)
                    if rs.error_code == "0":
                        while rs.next():
                            row_data = rs.get_row_data()
                            if len(row_data) >= 2:
                                name = row_data[1]
                                # 写入永久缓存
                                self._write_cache_raw(
                                    conn, name_table, ticker,
                                    json.dumps({"name": name, "code_name": row_data[0]}),
                                )
                                return f"{ticker}({name})"
                except Exception as e:
                    logger.info(f"[StockFetcher] 查询股票名称失败 ({ticker}): {e}")

            # BaoStock 失败或不可用：强制走本地库/akshare 兜底
            name = self.get_name_only(ticker)
            return f"{ticker}({name})" if name != ticker else ticker
        finally:
            conn.close()

    def get_name_code_map(self):
        """从内存缓存获取 {名称: 代码} 映射表。"""
        return dict(self._name_to_code) if self._name_to_code else {}

    def lookup_code(self, query, limit=15):
        """
        名称->代码 查找（高性能版：内存缓存 + 向量化）。
        输入中文名称/拼音，返回 [(code, name), ...]。
        """
        if not query or not query.strip():
            return []

        import time as _time
        t0 = _time.time()
        query = query.strip()
        q_upper = query.upper()
        q_lower = query.lower()
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in query)

        # ── L0: 纯6位数字 -> O(1) ──
        if query.isdigit() and len(query) == 6:
            name = self._code_to_name.get(query, "")
            logger.debug(f"[lookup_code] '{query}' -> ({query},{name}) ({(_time.time()-t0)*1000:.1f}ms)")
            return [(query, name)] if name else [(query, query)]

        # ── 使用内存缓存 ──
        df = self._stock_df
        if df is None or df.empty:
            df = self._ensure_stock_db()
        if df is None or df.empty:
            return []

        results = []
        seen_codes = set()

        # L1: 精确名称匹配 O(1)
        exact_code = self._name_to_code.get(query)
        if exact_code:
            results.append((exact_code, query, 1000))
            seen_codes.add(exact_code)

        # 如果已有精确匹配，快速返回（除非用户需要更多结果）
        has_exact = len(results) > 0 and results[0][2] == 1000

        # L2-L4: pandas 向量化（仅在需要更多结果时）
        names = df["name"].astype(str)
        codes = df["code"].astype(str)

        l2_l3_found = 0  # 记录L2/L3找到的结果数
        if len(query) >= 2 and len(results) < limit:
            mask_start = names.str.startswith(query, na=False)
            for idx in df.index[mask_start]:
                code = str(codes.iloc[idx])
                if code not in seen_codes:
                    name = str(names.iloc[idx])
                    results.append((code, name, 800))
                    seen_codes.add(code)
                    l2_l3_found += 1

            if len(results) < limit:
                mask_contain = names.str.contains(query, regex=False, na=False)
                for idx in df.index[mask_contain & ~mask_start]:
                    code = str(codes.iloc[idx])
                    if code not in seen_codes:
                        results.append((code, str(names.iloc[idx]), 600))
                        seen_codes.add(code)
                        l2_l3_found += 1

            # L4: 字符分散匹配（中文）— 仅在L2/L3完全没找到时才启用
            if has_chinese and l2_l3_found == 0 and len(results) < limit:
                for idx in range(len(df)):
                    code = str(codes.iloc[idx])
                    if code in seen_codes:
                        continue
                    name = str(names.iloc[idx])
                    if all(ch in name for ch in query):
                        results.append((code, name, 400))
                        seen_codes.add(code)

        # L5-L7: 拼音/Token — 仅在L1-L4都没找到 或 结果不足 时触发
        need_fuzzy = (
            len(results) < limit
            and len(query) >= 2
            and not has_exact
            and len(results) == 0  # 前面所有层都找不到时才用拼音兜底
        )
        if need_fuzzy:
            for idx in range(len(df)):
                code = str(codes.iloc[idx])
                if code in seen_codes:
                    continue
                name = str(names.iloc[idx])
                score = 0
                initials = self._pinyin_initials(name)
                if initials:
                    if q_upper == initials:
                        score = 500
                    elif q_upper in initials:
                        score = 350
                # 多音字首字母组合匹配
                if score == 0:
                    variants = self._pinyin_initials_variants_cache.get(name) or self._pinyin_initials_variants(name)
                    for v in variants:
                        if q_upper == v:
                            score = 500
                            break
                        elif q_upper in v:
                            score = 350
                if score == 0 and has_chinese:
                    tokens = self._name_tokens(name)
                    if query in tokens:
                        score = 450
                if score == 0:
                    full_py = self._pinyin_full(name)
                    if q_lower == full_py:
                        score = 300
                    elif q_lower in full_py:
                        score = 200
                if score > 0:
                    results.append((code, name, score))

        results.sort(key=lambda x: x[2], reverse=True)
        final = [(r[0], r[1]) for r in results[:limit]]
        logger.debug(f"[lookup_code] '{query}' -> {len(final)} 条 ({(_time.time()-t0)*1000:.1f}ms)")
        return final

    def get_stock_keywords(self, code_or_name, top_k=10):
        """
        为给定股票生成高频事件关键词。

        策略：
          1. 先根据名称做行业匹配（毫秒级）
          2. 如果代码是6位数字，尝试从事件库提取历史关联关键词

        :param code_or_name: 股票代码或名称
        :param top_k: 返回前 K 个关键词
        :return: str 逗号分隔的关键词字符串
        """
        # 1) 确定股票名称
        name = ""
        if code_or_name and code_or_name.isdigit() and len(code_or_name) == 6:
            name = self._lookup_name_for_code(code_or_name)
        else:
            name = code_or_name or ""

        # 2) 行业匹配关键词
        industry_kws = self._get_stock_industry_keywords(name)

        if not industry_kws:
            # 兜底：取股票名称本身的核心词（去掉常见后缀）
            core = name.replace("股份", "").replace("有限公司", "")
            core = core.replace("集团", "").replace("中国", "")
            if len(core) >= 2:
                industry_kws = [core]

        # 3) 截断到 top_k
        result = industry_kws[:top_k]
        return ",".join(result)

    def search_stocks(self, query, limit=15, with_price=False):
        """
        模糊搜索股票：代码 + 中文名称 + 拼音 + 同音字容错。

        匹配层级（从高到低）：
          1. 精确代码匹配 (1000)
          2. 代码前缀匹配 (900)
          3. 精确名称匹配 (800)
          4. 名称以关键词开头 (750)
          5. 名称包含完整查询词 (700)
          6. 全拼匹配 -> 同音字容错 (600)
          7. 拼音首字母匹配 (500)
          8. 名称分词Token匹配 -> 简称识别 (450)
          9. 名称子串包含 (400)
         10. 字符分散模糊匹配 (300)
         11. 全拼子串匹配 (250)
         12. Token近音匹配 (200)

        :param query: 搜索关键词
        :param limit: 最大返回数量
        :param with_price: 是否附带最近收盘价（1次DB查询/结果，慎用大量结果）
        :return: list[dict]，每项含 code, name, display, _matchType, _score
        """
        if not query or not query.strip():
            return []

        raw_query = query.strip()
        query_upper = raw_query.upper()
        all_stocks = self._ensure_stock_db()

        if all_stocks.empty:
            return []

        # 预计算查询的拼音形式（用于同音字容错）
        query_pinyin = self._pinyin_full(raw_query)
        has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in raw_query)

        results = []

        for _, row in all_stocks.iterrows():
            code = str(row["code"])
            name = str(row["name"])

            score = 0
            match_type = ""

            # ── 层级 1: 精确代码匹配 ──
            if query_upper == code:
                score = 1000
                match_type = "exact_code"

            # ── 层级 2: 代码前缀匹配 ──
            elif code.startswith(query_upper) and len(query_upper) >= 2:
                score = 900
                match_type = "code_prefix"

            # ── 层级 3: 精确名称匹配 ──
            elif raw_query == name:
                score = 800
                match_type = "exact_name"

            # ── 层级 4: 名称前缀匹配 ──
            elif name.startswith(raw_query) and len(raw_query) >= 2:
                score = 780
                match_type = "name_starts"

            # ── 层级 5: 名称包含完整查询词 ──
            elif raw_query in name and len(raw_query) >= 2:
                score = 720
                match_type = "name_contains_full"

            # ── 层级 6: 全拼匹配（同音字容错核心） ──
            # 中文查询时同音匹配降权：用户输入汉字时优先字符匹配，拼音仅作辅助
            elif len(raw_query) >= 2:
                name_pinyin = self._pinyin_full(name)
                hp_base = 350 if has_chinese else 650  # 中文输入降权
                if query_pinyin == name_pinyin:
                    score = hp_base + 50
                    match_type = "homophone_exact"
                elif query_pinyin in name_pinyin and len(query_pinyin) >= 3:
                    score = hp_base
                    match_type = "homophone_contains"

            # ── 层级 7: 拼音首字母匹配 ──
            if score == 0 and len(raw_query) >= 2:
                if all(c.isalpha() for c in raw_query) and not has_chinese:
                    py_init = self._pinyin_initials(name)
                    if py_init and query_upper in py_init:
                        score = 550
                        match_type = "pinyin_initials"
                    elif py_init and query_upper == py_init:
                        score = 580
                        match_type = "pinyin_initials_exact"

            # ── 层级 8: 分词 Token 匹配（简称识别） ──
            if score == 0 and has_chinese and len(raw_query) >= 2:
                tokens = self._name_tokens(name)
                if raw_query in tokens:
                    score = 500
                    match_type = "token_match"

            # ── 层级 9: 名称子串包含 ──
            if score == 0 and len(raw_query) >= 2 and raw_query in name:
                score = 450
                match_type = "name_contains"

            # ── 层级 10: 字符分散模糊匹配 ──
            if score == 0 and len(raw_query) >= 2 and has_chinese:
                chars = list(raw_query)
                name_idx = 0
                matched_positions = []
                found_all = True
                for ch in chars:
                    pos = name.find(ch, name_idx)
                    if pos == -1:
                        found_all = False
                        break
                    matched_positions.append(pos)
                    name_idx = pos + 1
                if found_all:
                    # 紧凑度得分：匹配字符越连续，分越高
                    max_gap = max(b - a for a, b in zip(matched_positions, matched_positions[1:])) if len(matched_positions) > 1 else 0
                    compactness = max(0, 100 - max_gap * 30)
                    score = 350 + compactness
                    match_type = "fuzzy_char"

            # ── 层级 11: 全拼子串匹配（非中文字符） ──
            if score == 0 and len(raw_query) >= 2 and not raw_query.isdigit():
                name_pinyin = self._pinyin_full(name)
                if query_pinyin and len(query_pinyin) >= 2 and query_pinyin in name_pinyin:
                    score = 280
                    match_type = "pinyin_substring"

            # ── 层级 12: Token 近音匹配 ──
            if score == 0 and len(raw_query) >= 2:
                query_py_token = self._pinyin_full(raw_query)
                name_py_token = self._pinyin_full(name)
                if query_py_token and name_py_token and (
                    query_py_token in name_py_token or name_py_token in query_py_token
                ):
                    score = 220
                    match_type = "pinyin_token"

            # ── 层级 13: 单字匹配（仅中文查询时） ──
            if score == 0 and len(raw_query) == 1 and has_chinese:
                if raw_query in name:
                    score = 150
                    match_type = "single_char"

            if score > 0:
                # 名称中含有数字/特殊标记，轻微降权
                if any(c.isdigit() or c == '*' for c in name):
                    score -= 20

                result = {
                    "code": code,
                    "name": name,
                    "display": f"{code}  {name}",
                    "score": score,
                    "_matchType": match_type,
                    "_score": score,
                }

                # 可选：附带当前价格
                if with_price:
                    price, price_date = self._get_latest_price(code)
                    result["price"] = price
                    result["price_date"] = price_date

                results.append(result)

        # 按 score 降序排列
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def stock_exists(self, symbol):
        """
        快速检查股票是否存在于数据源中（用 BaoStock 复用连接池）。
        返回 (是否存在, 名称或原因)。
        """
        if not _fetcher_mod._BS_OK:
            return True, ""  # BaoStock不可用时跳过检查

        try:
            # 复用 BaoStock 类级别的连接池（首次调用触发 login）
            if not _BaoStockFetcher._ensure_login():
                return True, "BaoStock登录失败"
            import baostock as bs  # 局部导入：与 _BS_OK 同源
            bs_code = _symbol_to_bs(symbol)
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                name = row[1] if len(row) >= 2 else ""
                return True, name
            # BaoStock 无此股票 -> 可能是退市/停牌/代码错误
            return False, "股票不存在、已退市或长期停牌（BaoStock无记录）"
        except Exception as e:
            logger.warning(f"[fetcher] 处理异常: {e}")
            # 检查失败时不阻塞（允许后续降级链尝试）
            return True, f"无法验证({e})"

