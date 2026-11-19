"""POST /api/v2/nl-screen/execute —— 自然语言选股执行端点（81 页 V2 化 · 执行链路）。

承接 v1 pages/81_自然语言选股.py 的执行链路（语义解析层已由 GET /api/v2/read/nl-screen 承接）：
  parse_query（纯函数）→ 候选池按 scope 三级降级取数 → apply_filters 过滤排序 →
  scan_and_gate 二道闸排雷（T-245）→ 诚实返回。

设计要点：
  * **取数函数全部依赖注入**：模块级 _UNIVERSE_SOURCES 注册表，路由装载时 import 真实现
    注册（api_get 自选股 → akshare 全市场快照 → StockFetcher 逐只基本面，v1 同源三级降级）；
    测试可 monkeypatch 注入假源，全程零联网可测。
  * **诚实红线（照 v1 口径）**：候选池获取失败/为空 → 200 + available=false + 真实原因，
    绝不伪造筛选结果行；解析全未理解 → 不执行、spec 原样摊开；
    解析了什么原样返回、未理解词如实标注（unparsed）。
  * **服务端兜底**：执行链路整体 try/except，异常 200 + available=false + reason（截 180 字），
    除 422（校验失败）/ 401（无 token）外不抛非 200——执行失败属业务降级，不 500 裸崩。

红线：本端点为只读筛选，不含任何下单/持仓语义。
"""
from __future__ import annotations

import logging
import math
import time
from typing import Callable

from flask import Blueprint, request

from ..auth.decorators import jwt_required
from ..utils.response import fail, ok

logger = logging.getLogger(__name__)

bp = Blueprint("nl_execute", __name__, url_prefix="/api/v2")

_MAX_QUERY_LEN = 200
_MAX_ROWS = 100          # rows 上限（前 100）
_MAX_GATE_ITEMS = 50     # gated_out 明细上限
_MAX_EXC_REASON = 180    # 异常 reason 截断（契约口径）
_UNIVERSE_REASON_CAP = 500  # 候选池失败 reason 上限（保信息量）
_VALID_SCOPES = ("local_api", "akspot", "all")

_NOTE = (
    "v2 承接自然语言选股「执行链路」：解析(parse_query 纯函数) → 候选池按 scope 三级降级取数"
    "（api_get 自选股 → akshare 全市场快照 → StockFetcher 逐只基本面，全部依赖注入）→ "
    "条件过滤排序 → 二道闸排雷。候选池取不到时如实返回 available=false 与真实原因，"
    "绝不伪造筛选结果；结果为真实筛选，非投资建议。"
)

# ───────────── 取数源注册表（依赖注入）─────────────
# 键：源名（"local_api"=api_get 自选股 / "akspot"=akshare 全市场快照 /
#          "custom"=custom_codes 逐只 StockFetcher 基本面）
# 值：fn(custom_codes: str) -> list[dict]，返回已水合候选记录（code/name/pe/...），
#     失败须抛异常（由调用方按「该源失败」如实记录并降级）。测试 monkeypatch 注入假源。
_UNIVERSE_SOURCES: dict[str, Callable[[str], list[dict]]] = {}

# scope → 取数源降级链（v1 _fetch_universe 同源三级降级：api_get → akshare 直接 → StockFetcher）：
#   local_api：自选股池优先，失败降级 akshare 快照，再降级 custom（需 custom_codes）；
#   akspot：全市场快照优先，失败降级 custom；
#   all：三源合并（按 code 去重），任一源失败只记录不中断。
# custom_codes 非空时 custom 源插到链首（用户显式给代码 = v1「自定义」池语义，优先级最高）。
_SCOPE_CHAIN = {
    "local_api": ("local_api", "akspot", "custom"),
    "akspot": ("akspot", "custom"),
    "all": ("local_api", "akspot", "custom"),
}


def _parse_custom_codes(custom_codes: str) -> list[str]:
    """逗号分隔代码 → 6 位右对齐代码列表（v1 同口径）。"""
    return [c.strip().zfill(6) for c in str(custom_codes or "").replace("，", ",").split(",") if c.strip()]


def _register_real_sources() -> None:
    """路由装载时 import 真实现并注册（v1 _fetch_universe 同源）。

    此处只定义闭包，不触发任何网络调用；akshare / StockFetcher 均在请求期惰性 import。
    """

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None  # ui_audit_exempt(T-239R2): except 内数值解析失败降级 None-已审

    def _spot_map() -> dict:
        """行情快照（涨跌幅/换手率/量比/振幅/流通市值）；失败→空 map（技术面维度诚实降级为 None）。"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            return {str(row.get("代码")): row for _, row in df.iterrows()}
        except Exception as e:  # noqa: BLE001
            logger.warning("[nl-execute] 行情快照取数失败，技术面维度降级: %s", e)
            return {}

    def _hydrate(codes: list[str], spot_map: dict) -> list[dict]:
        """逐只水合基本面（v1 同源 StockFetcher）；单只失败跳过，不伪造该只数据。"""
        from modules.fetcher import StockFetcher
        fetcher = StockFetcher()
        recs: list[dict] = []
        for code in codes:
            try:
                fb = fetcher.get_fundamentals(code, use_cache=True) or {}
                rec = {
                    "code": code,
                    "name": fb.get("name") or fetcher.get_name_only(code) or code,
                    "pe": fb.get("pe_ttm"), "pb": fb.get("pb"),
                    "mktcap": fb.get("total_mv"),  # 亿元
                    "float_mktcap": fb.get("float_mv"),
                    "rev_growth": fb.get("rev_growth"), "profit_growth": fb.get("profit_growth"),
                    "roe": fb.get("roe"), "gross_margin": fb.get("gross_margin"),
                    "concepts": fb.get("concepts") or [],
                }
                sp = spot_map.get(code)
                if sp is not None:
                    rec["chg_pct"] = _num(sp.get("涨跌幅"))
                    rec["turnover"] = _num(sp.get("换手率"))
                    rec["volume_ratio"] = _num(sp.get("量比"))
                    rec["amplitude"] = _num(sp.get("振幅"))
                    if rec["float_mktcap"] is None:
                        rec["float_mktcap"] = _num(sp.get("流通市值"))
                recs.append(rec)
            except Exception:  # noqa: BLE001 - 单只失败跳过，不编造
                continue
        return recs

    def _local_api_source(custom_codes: str) -> list[dict]:
        """自选股池：api_get 取代码 → StockFetcher 水合（v1 同源）。"""
        from modules.session import api_get
        _, body = api_get("/api/watchlist", timeout=10)
        codes: list[str] = []
        if isinstance(body, dict) and body.get("status") == "ok":
            for it in (body.get("data") or []):
                codes.append(str(it.get("code", "")))
        codes = [c for c in codes if c]
        if not codes:
            raise RuntimeError("自选股为空或未配置")
        return _hydrate(codes, _spot_map())

    def _akspot_source(custom_codes: str) -> list[dict]:
        """全市场快照：akshare 一次调用直接成行（市值折算亿元，含技术面维度）。"""
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or len(df) == 0:
            raise RuntimeError("全市场快照为空")
        recs: list[dict] = []
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            if not code:
                continue
            mktcap = _num(row.get("总市值"))
            float_mv = _num(row.get("流通市值"))
            recs.append({
                "code": code,
                "name": str(row.get("名称", "")) or code,
                "pe": _num(row.get("市盈率-动态")), "pb": _num(row.get("市净率")),
                "mktcap": mktcap / 1e8 if mktcap is not None else None,
                "float_mktcap": float_mv / 1e8 if float_mv is not None else None,
                "chg_pct": _num(row.get("涨跌幅")), "turnover": _num(row.get("换手率")),
                "volume_ratio": _num(row.get("量比")), "amplitude": _num(row.get("振幅")),
                "concepts": [],
            })
        return recs

    def _custom_source(custom_codes: str) -> list[dict]:
        """自定义代码池：逐只 StockFetcher 水合（v1 同源）；未提供代码如实抛错。"""
        codes = _parse_custom_codes(custom_codes)
        if not codes:
            raise RuntimeError("custom_codes 未提供或解析后为空")
        return _hydrate(codes, _spot_map())

    _UNIVERSE_SOURCES["local_api"] = _local_api_source
    _UNIVERSE_SOURCES["akspot"] = _akspot_source
    _UNIVERSE_SOURCES["custom"] = _custom_source


_register_real_sources()


def _fetch_universe(scope: str, custom_codes: str) -> tuple[list[dict], str, list[str]]:
    """按 scope 走降级链取候选池。返回 (records, used_source, notes)。

    - local_api / akspot：链序**首个成功且非空**的源（三级降级）；
    - all：链序合并全部成功源（按 code 去重），任一源失败只记录不中断；
    - 全部失败/为空 → ([], "", notes)，notes 为真实逐源原因（绝不伪造候选池）。
    """
    notes: list[str] = []
    chain = _SCOPE_CHAIN.get(scope, _SCOPE_CHAIN["local_api"])
    if str(custom_codes or "").strip():
        chain = ("custom",) + chain

    if scope == "all":
        merged: dict[str, dict] = {}
        used: list[str] = []
        for name in chain:
            fn = _UNIVERSE_SOURCES.get(name)
            if fn is None:
                notes.append(f"{name}: 源未注册")
                continue
            try:
                recs = fn(custom_codes) or []
            except Exception as e:  # noqa: BLE001 - 单源失败如实记录，不中断合并
                notes.append(f"{name}: {type(e).__name__}: {e}")
                continue
            if not recs:
                notes.append(f"{name}: 返回空候选池")
                continue
            used.append(name)
            for r in recs:
                code = str(r.get("code", ""))
                if code and code not in merged:
                    merged[code] = r
        if not merged:
            return [], "", notes
        return list(merged.values()), "+".join(used), notes

    for name in chain:
        fn = _UNIVERSE_SOURCES.get(name)
        if fn is None:
            notes.append(f"{name}: 源未注册")
            continue
        try:
            recs = fn(custom_codes) or []
        except Exception as e:  # noqa: BLE001 - 该源失败，降级下一源
            notes.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if not recs:
            notes.append(f"{name}: 返回空候选池")
            continue
        return recs, name, notes
    return [], "", notes


def _nan_to_none(v):
    """NaN / NaT / Inf → None（合法 JSON），其余原样透传。"""
    if v is None or isinstance(v, (bool, int, str, dict, list)):
        return v
    try:  # pandas NaT / numpy NaN 等载体统一交给 pd.isna 判别
        import pandas as pd
        if pd.isna(v):
            return None
    except Exception as e:  # noqa: BLE001 - 判别失败降级 float 检查，留痕不静默
        logger.debug("[nl-execute] pd.isna 判别失败（%s: %s），降级 float 检查", type(e).__name__, e)
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
    except (TypeError, ValueError):  # ui_audit_exempt(T-239R3): float 判别失败保留原值透传-已审
        pass
    return v


def _sanitize_row(rec: dict) -> dict:
    """单行清洗：键转 str，值 NaN/NaT/Inf → None。"""
    if not isinstance(rec, dict):
        return {}
    return {str(k): _nan_to_none(v) for k, v in rec.items()}


def _spec_payload(spec) -> dict:
    """QuerySpec 原样摊开（解析了什么透明展示，未理解词如实标注）。"""
    return {
        "boards": spec.boards,
        "filters": spec.filters,
        "sort": spec.sort,
        "sort_dir": spec.sort_dir,
        "limit": spec.limit,
        "concepts": spec.concepts,
        "exclude_boards": spec.exclude_boards,
        "exclude_concepts": spec.exclude_concepts,
        "unparsed": spec.unparsed,
        "errors": spec.errors,
    }


@bp.post("/nl-screen/execute")
@jwt_required
def nl_screen_execute():
    """自然语言选股 · 执行（81 页 V2 化，执行链路）。

    body: {"query": str 必填 1..200,
           "scope"?: "local_api"|"akspot"|"all"（缺省 local_api）,
           "custom_codes"?: str（逗号分隔代码，非空时优先作为候选池）}
    校验失败 → 422 validation_error；无 token → 401。

    返回（恒 200，业务降级见 available=false + reason）：
      available=true:  spec + n_universe + n_matched + rows(前 100, NaN/NaT→None)
                       + gated_out(计数与原因摘要) + elapsed_ms
      available=false: 解析全未理解 / 候选池获取失败 / 执行异常（reason 截 180 字）——
                       绝不伪造筛选结果行。
    """
    t0 = time.perf_counter()

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return fail(message="body 必须是 JSON 对象", code="validation_error", http_status=422)

    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        return fail(message="query 必填（1~200 字口语选股条件）",
                    code="validation_error", http_status=422)
    q = query.strip()
    if len(q) > _MAX_QUERY_LEN:
        return fail(message=f"query 过长（上限 {_MAX_QUERY_LEN} 字）",
                    code="validation_error", http_status=422)

    scope = body.get("scope") or "local_api"
    if scope not in _VALID_SCOPES:
        return fail(message="scope 须为 local_api / akspot / all 之一",
                    code="validation_error", http_status=422)

    custom_codes = body.get("custom_codes")
    if custom_codes is not None and not isinstance(custom_codes, str):
        return fail(message="custom_codes 须为字符串（逗号分隔股票代码）",
                    code="validation_error", http_status=422)

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    try:
        from modules import nl_screen as ns

        # 1) 解析（纯函数，不触网）；全未理解 → 不执行、spec 原样摊开（诚实红线）
        spec = ns.parse_query(q)
        spec_data = _spec_payload(spec)
        n_conditions = (len(spec.boards) + len(spec.filters) + len(spec.concepts)
                        + len(spec.exclude_boards) + len(spec.exclude_concepts)
                        + (1 if spec.sort else 0))
        if n_conditions == 0:
            return ok(data={
                "available": False,
                "reason": "未能从语句解析出任何选股条件",
                "query": q, "scope": scope,
                "spec": spec_data,
                "n_universe": 0, "n_matched": 0, "rows": [],
                "gated_out": {"count": 0, "items": [], "note": None},
                "elapsed_ms": _elapsed_ms(),
                "note": _NOTE,
            }, message="nl-screen-execute")

        # 2) 候选池按 scope 三级降级取数；取不到 → 诚实说明，绝不伪造结果行
        universe, used_source, source_notes = _fetch_universe(scope, custom_codes or "")
        if not universe:
            reason = ("候选池获取失败（三级降级均未取得数据，执行需联网）："
                      + "；".join(source_notes))[:_UNIVERSE_REASON_CAP]
            return ok(data={
                "available": False,
                "reason": reason,
                "query": q, "scope": scope,
                "spec": spec_data,
                "n_universe": 0, "n_matched": 0, "rows": [],
                "gated_out": {"count": 0, "items": [], "note": None},
                "elapsed_ms": _elapsed_ms(),
                "note": _NOTE,
            }, message="nl-screen-execute")

        # 3) 条件过滤排序（纯函数）
        matched = ns.apply_filters(universe, spec)
        n_universe, n_matched = len(universe), len(matched)

        # 4) T-245 二道闸排雷；闸异常 → 降级放行并如实标注（不崩、不编造）
        rows = matched
        gated_out: dict = {"count": 0, "items": [], "note": None}
        try:
            from modules.risk_gate import scan_and_gate
            _, gsum = scan_and_gate(
                [{"code": r.get("code", ""), "name": r.get("name", "")} for r in matched],
                top_k=len(matched) or 1,
            )
            kicked = list(gsum.get("kicked", []) or [])
            kicked_codes = {str(k.get("code")) for k in kicked}
            rows = [r for r in matched if str(r.get("code", "")) not in kicked_codes]
            gated_out = {
                "count": len(kicked),
                "items": [{"code": k.get("code"), "name": k.get("name"),
                           "reasons": list(k.get("reasons") or [])}
                          for k in kicked[:_MAX_GATE_ITEMS]],
                "note": None,
            }
        except Exception as e:  # noqa: BLE001 - 二道闸异常：降级放行，说明保留
            logger.warning("[nl-execute] 二道闸异常，降级放行: %s", e)
            gated_out = {
                "count": 0, "items": [],
                "note": f"二道闸异常，降级放行：{type(e).__name__}: {e}"[:_MAX_EXC_REASON],
            }

        rows = rows[:_MAX_ROWS]
        return ok(data={
            "available": True,
            "query": q, "scope": scope,
            "spec": spec_data,
            "source_used": used_source,
            "source_notes": source_notes,
            "n_universe": n_universe,
            "n_matched": n_matched,
            "n_rows": len(rows),
            "rows": [_sanitize_row(r) for r in rows],
            "gated_out": gated_out,
            "elapsed_ms": _elapsed_ms(),
            "note": _NOTE,
        }, message="nl-screen-execute")
    except Exception as e:  # noqa: BLE001 - 执行链路整体兜底：业务降级，不 500 裸崩
        logger.warning("[nl-execute] 执行链路异常，诚实降级: %s", e, exc_info=True)
        reason = f"执行失败：{type(e).__name__}: {e}"[:_MAX_EXC_REASON]
        return ok(data={
            "available": False,
            "reason": reason,
            "query": q, "scope": scope,
            "n_universe": 0, "n_matched": 0, "rows": [],
            "gated_out": {"count": 0, "items": [], "note": None},
            "elapsed_ms": _elapsed_ms(),
            "note": _NOTE,
        }, message="nl-screen-execute")
