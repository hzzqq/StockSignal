# -*- coding: utf-8 -*-
"""行业清单与成分股抓取。

- 清单基准：同花顺 ``stock_board_industry_summary_ths()``（实测 90 行稳定）。
- 成分股：东财 clist ``fs=b:{board_code}``，urllib 直连（清代理）。
- 限频现实：约 7 次请求后断连 → 限速 + 指数退避 + 断点续传（resume）。
- 诚实：抓不到成分股一律记 failed，绝不写空成分股冒充成功。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request

logger = logging.getLogger(__name__)

_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
_BOARD_FS = "m:90+t:3"
# 东财 554「行业」混入的概念名特征（酿酒概念 / 算力租赁…）；只过滤明确概念词，
# 不误伤同花顺 90 个纯行业名。
_CONCEPT_HINTS = ("概念", "算力租赁")
_BOARD_DELAY = 1.5


def _urlopen(url, timeout=15):
    """唯一的 HTTP 边界：用空 ProxyHandler 绕开环境里的 127.0.0.1:9224 干扰。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url, timeout=timeout)


def _http_get_json(url):
    with _urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def _board_names_from_df(df) -> list:
    """从 akshare DataFrame 提取「板块」列（兼容少量常见列名/首列）。"""
    columns = list(getattr(df, "columns", []))
    col = next((c for c in ("板块", "板块名称", "name", "名称") if c in columns), None)
    if col is None and columns:
        col = columns[0]
    if col is None:
        return []
    out = []
    for v in df[col]:
        s = str(v).strip()
        if s and s not in ("板块", "板块名称", "name", "名称"):
            out.append(s)
    return out


def fetch_industry_names() -> list:
    """同花顺 90 个纯行业名；失败降级东财 clist（过滤概念名）。"""
    try:
        import akshare as ak

        df = ak.stock_board_industry_summary_ths()
        names = _board_names_from_df(df)
        if len(names) >= 60:
            return [{"name": n, "source": "ths"} for n in names]
        logger.warning("[sector_map_fetch] 同花顺行业清单仅 %d 行，降级东财", len(names))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sector_map_fetch] 同花顺行业清单失败，降级东财: %s", exc)

    index = _fetch_em_board_index()
    out = [{"name": n, "code": c, "source": "em"} for n, c in sorted(index.items())]
    logger.warning("[sector_map_fetch] 东财降级清单仅 %d 个行业（非权威基准）", len(out))
    return out


def _fetch_em_board_index(needed_names=None, delay=0.0, max_pages=6) -> dict:
    """东财 clist m:90+t:3 → {行业名: BK代码}；集齐 needed_names 即提前停止。"""
    wanted = set(needed_names) if needed_names else None
    out = {}
    for pn in range(1, max_pages + 1):
        url = (f"{_CLIST}?pn={pn}&pz=100&po=1&np=1"
               f"&fields=f2,f3,f12,f14&fs={_BOARD_FS}")
        try:
            data = _http_get_json(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[sector_map_fetch] 东财板块清单第 %d 页失败: %s", pn, exc)
            break
        items = ((data or {}).get("data") or {}).get("diff") or []
        for it in items:
            name = str(it.get("f14") or "").strip()
            code = str(it.get("f12") or "").strip()
            if not name or not code or any(h in name for h in _CONCEPT_HINTS):
                continue
            out[name] = code
        if wanted and wanted.issubset(out.keys()):
            break
        if not items:
            break
        if delay and pn < max_pages:
            time.sleep(delay)
    return out


def fetch_members(board_code, *, delay=1.5, retries=3) -> list:
    """东财成分股 ``[{code,name},...]``；失败退回 [] 并记日志，绝不编造。"""
    code = str(board_code or "").strip()
    if not code:
        logger.warning("[sector_map_fetch] 空 board_code，无法抓成分股")
        return []
    url = (f"{_CLIST}?pn=1&pz=100&po=1&np=1"
           f"&fields=f2,f3,f12,f14&fs=b:{code}")
    attempts = max(1, int(retries))
    last_err = None
    for k in range(attempts):
        try:
            data = _http_get_json(url)
            items = ((data or {}).get("data") or {}).get("diff") or []
            out = []
            for it in items:
                sc = str(it.get("f12") or "").strip()
                sn = str(it.get("f14") or "").strip()
                if not sc:
                    continue
                out.append({"code": sc.zfill(6) if sc.isdigit() else sc, "name": sn})
            if out:
                return out
            logger.warning("[sector_map_fetch] %s 成分股为空（第 %d 次）", code, k + 1)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("[sector_map_fetch] %s 成分股失败(%d/%d): %s",
                           code, k + 1, attempts, exc)
        if k < attempts - 1:
            time.sleep(delay * (2 ** k))
    logger.warning("[sector_map_fetch] %s 成分股最终失败: %s", code, last_err)
    return []


def refresh_sector_map(limit=None, resume=True) -> dict:
    """拉清单 → 逐个抓成分股 → upsert；一期上限 90 行业。

    resume=True 时只重抓 sector_entity_map 中 failed/stale/不存在的行业，
    已完成（ok 且 member_count>0）的行业跳过。
    """
    from modules import sector_map as sm

    cap = 90
    if limit is None:
        n = cap
    else:
        try:
            n = min(max(int(limit), 0), cap)
        except (TypeError, ValueError):
            logger.warning("[sector_map_fetch] 非法 limit=%r，按 90 处理", limit)
            n = cap

    items = fetch_industry_names()
    source = items[0].get("source", "none") if items else "none"
    result = {"total": len(items), "ok": 0, "failed": 0, "skipped": 0,
              "source": source}
    if n == 0 or not items:
        result["skipped"] = len(items)
        return result

    existing = {r["board_name"]: r for r in sm.list_sectors()}
    targets = []
    for it in items[:n]:
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        row = existing.get(name)
        mc = row.get("member_count") if row else None
        if resume and row and row.get("fetch_status") == "ok" and mc is not None and mc > 0:
            result["skipped"] += 1
            continue
        targets.append(it)
    result["skipped"] += max(len(items) - n, 0)

    code_by_name = {}
    needed = set()
    for it in targets:
        name = str(it.get("name") or "").strip()
        if it.get("code"):
            code_by_name[name] = str(it["code"]).strip()
        else:
            needed.add(name)
    if needed:
        code_by_name.update(_fetch_em_board_index(needed_names=needed, delay=0.3))

    for it in targets:
        name = str(it.get("name") or "").strip()
        code = code_by_name.get(name)
        if not code:
            logger.warning("[sector_map_fetch] 行业 %s 无东财板块代码，记 failed", name)
            sm.mark_failed(name)
            result["failed"] += 1
            continue
        time.sleep(_BOARD_DELAY)
        members = fetch_members(code, delay=_BOARD_DELAY)
        if not members:
            sm.mark_failed(name)
            result["failed"] += 1
            continue
        ok = sm.upsert_sector({
            "board_name": name,
            "board_code": code,
            "board_type": "industry",
            "stock_codes": ",".join(m["code"] for m in members),
            "member_count": len(members),
            "fetch_status": "ok",
        })
        if ok:
            result["ok"] += 1
        else:
            logger.warning("[sector_map_fetch] 行业 %s upsert 失败", name)
            result["failed"] += 1
    return result
