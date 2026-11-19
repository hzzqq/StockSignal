# -*- coding: utf-8 -*-
"""政策原文抓取层（中国政府网政策频道 / 发改委）。

数据源（已实测）：
- 首选 gov.cn 政策频道 https://www.gov.cn/zhengce/ —— 列表页含标题、详情页
  URL、YYYY-MM-DD 日期；详情页含正文与文号。
- 补充 ndrc https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/ —— 标题带「20XX年第N号令」
  文号，正文主体在 PDF/OFD 附件（HTML 仅为说明）。
- 不用 akshare（无政策原文接口）、不用国务院搜索 JSON / 东财政策频道（实测不可用）。

诚实红线：
- publish_date 取自列表页原文日期，解析不到 → None，绝不拿 now() 兜底；
- 正文在 PDF/OFD 附件时 body_text=None + body_source='attachment'，不假装抓到全文；
- 两源都空 → 不写库、明确报 failed，绝不写假数据。
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

GOV_CN_URL = "https://www.gov.cn/zhengce/"
NDRC_URL = "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/"
REQ_TIMEOUT = 10
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

from modules import policy_store as _store  # noqa: E402

_DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
_DOC_NO_RE = re.compile(
    r"\d{4}\s*年\s*第\s*\d+\s*号"
    r"|[\u4e00-\u9fa5A-Za-z]{2,12}〔\d{4}〕\d+号"
    r"|第\s*\d+\s*号"
)
_ATTACH_RE = re.compile(r"href=[\"'][^\"']*\.(pdf|ofd|docx?|xlsx?)[\"']", re.I)
_A_TAG_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = REQ_TIMEOUT) -> str:
    """取页面文本。走 urllib 默认代理（环境 HTTPS_PROXY）；编码按 utf-8/gb18030/gbk 尝试。"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _norm_date(text: str) -> str | None:
    """从文本中解析 YYYY-MM-DD；解析不到 → None（不编造、不兜底 now）。"""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


# ── 列表解析 ─────────────────────────────────────────────────────────────────

class _ListParser(HTMLParser):
    """以 <li>/<tr> 为条目单位，收集首个链接的 href/锚文本及块内文本。"""

    def __init__(self, block_tags=("li", "tr")):
        super().__init__(convert_charrefs=True)
        self.block_tags = set(block_tags)
        self.blocks: list[dict] = []
        self._cur: dict | None = None
        self._depth = 0
        self._in_a = False
        self._a_href: str | None = None
        self._a_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in self.block_tags:
            self._depth += 1
            if self._cur is None:
                self._cur = {"href": None, "text": "", "raw": "", "raw_no_a": ""}
        if tag == "a" and d.get("href"):
            if self._cur is not None and self._cur["href"] is None:
                self._a_href = d["href"]
                self._a_text = []
                self._in_a = True

    def handle_data(self, data):
        s = data.strip()
        if not s:
            return
        if self._in_a:
            self._a_text.append(s)
        if self._cur is not None:
            self._cur["raw"] += " " + s
            if not self._in_a:
                self._cur["raw_no_a"] += " " + s

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            if self._cur is not None and self._cur["href"] is None:
                self._cur["href"] = self._a_href
                self._cur["text"] = "".join(self._a_text).strip()
            self._in_a = False
        if tag in self.block_tags and self._depth > 0:
            self._depth -= 1
            if self._depth == 0 and self._cur is not None:
                self.blocks.append(self._cur)
                self._cur = None


def _parse_blocks(html: str, base: str, source: str, limit: int) -> list[dict]:
    parser = _ListParser(("li", "tr"))
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001 - HTMLParser 对畸形 HTML 偶发抛错
        logger.warning(f"[policy_fetch] 列表解析失败 source={source}: {e}")
        return []
    out: list[dict] = []
    seen = set()
    for b in parser.blocks:
        title, href = b["text"], b["href"]
        if not title or not href or len(title) < 4:
            continue
        full = urllib.parse.urljoin(base, href)
        if full in seen:
            continue
        pub = _norm_date(b["raw_no_a"]) or _norm_date(b["raw"])
        seen.add(full)
        out.append({
            "title": title,
            "source_url": full,
            "publish_date": pub,
            "source": source,
        })
        if len(out) >= limit:
            break
    return out


def _parse_anchors_regex(html: str, base: str, source: str, limit: int) -> list[dict]:
    """无 li/tr 包裹时的兜底：按 <a> 标签提取，日期取链接附近文本。"""
    out: list[dict] = []
    seen = set()
    for m in _A_TAG_RE.finditer(html):
        href, inner = m.group(1), m.group(2)
        title = re.sub(r"\s+", " ", _TAG_STRIP_RE.sub("", inner)).strip()
        if len(title) < 4 or not href:
            continue
        tail = _TAG_STRIP_RE.sub(" ", html[m.end():m.end() + 120])
        head = _TAG_STRIP_RE.sub(" ", html[max(0, m.start() - 80):m.start()])
        pub = _norm_date(tail) or _norm_date(head)
        full = urllib.parse.urljoin(base, href)
        if full in seen:
            continue
        seen.add(full)
        out.append({
            "title": title,
            "source_url": full,
            "publish_date": pub,
            "source": source,
        })
        if len(out) >= limit:
            break
    return out


def _parse_gov_cn(html: str, limit: int = 40) -> list[dict]:
    return _parse_blocks(html, GOV_CN_URL, "gov.cn", limit) or \
        _parse_anchors_regex(html, GOV_CN_URL, limit, "gov.cn")


def _parse_ndrc(html: str, limit: int = 20) -> list[dict]:
    items = _parse_blocks(html, NDRC_URL, "ndrc", limit) or \
        _parse_anchors_regex(html, NDRC_URL, limit, "ndrc")
    for it in items:
        m = _DOC_NO_RE.search(it["title"])
        it["doc_number"] = m.group(0).strip() if m else None
        it["issuing_body"] = "国家发展和改革委员会"
    return items


def fetch_gov_cn(limit: int = 40) -> list[dict]:
    try:
        html = _http_get(GOV_CN_URL)
    except Exception as e:  # noqa: BLE001 - 网络异常记日志，返回空让上层降级
        logger.warning(f"[policy_fetch] gov.cn 抓取失败: {e}")
        return []
    return _parse_gov_cn(html, limit)


def fetch_ndrc(limit: int = 20) -> list[dict]:
    try:
        html = _http_get(NDRC_URL)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[policy_fetch] ndrc 抓取失败: {e}")
        return []
    return _parse_ndrc(html, limit)


# ── 详情页 ───────────────────────────────────────────────────────────────────

class _BodyParser(HTMLParser):
    """提取正文纯文本，跳过 script/style。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            s = data.strip()
            if s:
                self.parts.append(s)


def fetch_policy_detail(source_url: str) -> dict:
    """抓详情页正文。附件（PDF/OFD）场景不假装抓到全文。"""
    try:
        html = _http_get(source_url)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[policy_fetch] 详情页抓取失败 url={source_url}: {e}")
        return {"body_text": None, "body_source": "none"}
    if _ATTACH_RE.search(html):
        return {"body_text": None, "body_source": "attachment"}
    parser = _BodyParser()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[policy_fetch] 详情页解析失败 url={source_url}: {e}")
        return {"body_text": None, "body_source": "none"}
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(parser.parts)).strip()
    if text:
        return {"body_text": text, "body_source": "html"}
    return {"body_text": None, "body_source": "none"}


# ── 编排 ─────────────────────────────────────────────────────────────────────

def fetch_available(limit: int = 40) -> tuple[list[dict], str | None, str]:
    """按优先级取源：gov.cn 主源，空则降级 ndrc。返回 (items, source, basis)。"""
    items = fetch_gov_cn(limit)
    if items:
        return items, "gov.cn", "primary:gov.cn"
    items = fetch_ndrc(limit)
    if items:
        return items, "ndrc", "fallback:ndrc"
    return [], None, "both-empty"


def refresh_policies(include_detail: bool = False, limit: int = 40) -> dict:
    """抓取并入库。两源都空 → 不动库、返回 failed，绝不写假数据。"""
    items, source, basis = fetch_available(limit)
    result = {
        "written": 0, "skipped": 0, "failed": 0,
        "source": source, "basis": basis,
    }
    if not items:
        logger.warning("[policy_fetch] 两源均无政策条目，未写库（拒绝假数据）")
        result["failed"] = 1
        return result
    for it in items:
        try:
            doc = dict(it)
            if include_detail:
                detail = fetch_policy_detail(doc["source_url"])
                doc["body_text"] = detail["body_text"]
                doc["body_source"] = detail["body_source"]
            if _store.upsert_policy(doc):
                result["written"] += 1
            else:
                result["skipped"] += 1
        except Exception as e:  # noqa: BLE001 - 单条失败不影响其余
            logger.warning(f"[policy_fetch] 条目处理失败 url={it.get('source_url')}: {e}")
            result["failed"] += 1
    return result
