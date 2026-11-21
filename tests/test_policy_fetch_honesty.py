# -*- coding: utf-8 -*-
"""政策采集确定性缺陷回归守卫（真实抓取探针取证，零联网）。

覆盖主控取证确认的 3 个缺陷：
1. _parse_anchors_regex 调用参数顺序（降级路径 TypeError）；
2. gov.cn 非政策页（/fuwu/jiucuopage.html「网站纠错」）入库；
3. 列表块施行日期（2027-01-01）误当发布日期 + 未来日期写入。
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import policy_fetch as pf  # noqa: E402
from modules import policy_store as ps  # noqa: E402


# 无 li/tr —— 强制走 _parse_anchors_regex 降级路径
FALLBACK_HTML = """
<html><body>
<p>政策列表</p>
<a href="/zhengce/content/202611/t20261110_1001.htm">关于加快Policy建设的若干意见</a><span>2026-11-10</span>
<a href="https://www.gov.cn/zhengce/zhengceku/202611/content_7085743.htm">司法部就基金会管理条例修订答记者问</a><span>2026-11-09</span>
<a href="/fuwu/jiucuopage.html">网站纠错</a><span>2026-11-08</span>
</body></html>
"""

# 有 li/tr —— 走 _parse_blocks 主路径
BLOCK_HTML = """
<html><body><ul>
<li><a href="/zhengce/content/202611/t20261110_1001.htm">关于加快Policy建设的若干意见</a><span>2026-11-10</span></li>
<li><a href="/fuwu/jiucuopage.html">网站纠错</a><span>2026-11-08</span></li>
<li><a href="https://evil.example.com/zhengce/fake.htm">冒充政策页的第三方链接标题</a><span>2026-11-07</span></li>
</ul></body></html>
"""

NDRC_FALLBACK_HTML = """
<html><body>
<a href="/xxgk/zcfb/fzggwl/202611/t20261115_2001.htm">国家发展改革委2026年第50号令</a> 2026-11-15
</body></html>
"""

# 列表块 raw_no_a 里是「施行日期」2027-01-01，详情页正文首部才是真实发布时间
LIST_WITH_FUTURE_DATE = """
<html><body><ul>
<li><a href="/zhengce/202611/content_7085743.htm">司法部、民政部负责人就《基金会管理条例》修订答记者问</a><span>自2027年1月1日起施行</span></li>
</ul></body></html>
"""

DETAIL_HTML = """
<html><body>
<div class="pages-date">2026-11-10 22:09</div>
<h1>司法部、民政部负责人就《基金会管理条例》修订答记者问</h1>
<p>《基金会管理条例》自2027年1月1日起施行。</p>
</body></html>
"""

FUTURE_LIST_HTML = """
<html><body><ul>
<li><a href="/zhengce/content/202611/t20990101_9999.htm">关于Policy建设远期规划的若干意见</a><span>2099-01-01</span></li>
</ul></body></html>
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """每个用例隔离到 tmp 库，绝不污染 data/policy.db。"""
    monkeypatch.setenv("POLICY_DB_PATH", str(tmp_path / "policy.db"))
    return str(tmp_path / "policy.db")


# ── 缺陷 1：_parse_anchors_regex 调用参数顺序 ───────────────────────────────

def test_parse_gov_cn_fallback_no_typeerror():
    """降级路径下 limit 必须是 int；传反会把 limit 变成字符串导致 TypeError。"""
    items = pf._parse_gov_cn(FALLBACK_HTML, limit=10)
    assert isinstance(items, list)
    assert len(items) == 2  # 3 个链接中「网站纠错」被过滤
    # 参数顺序修正后 source 落到正确位置，而非整数 10
    assert all(it["source"] == "gov.cn" for it in items)


def test_parse_ndrc_fallback_no_typeerror():
    """_parse_ndrc 同写法，降级路径同样不得 TypeError。"""
    items = pf._parse_ndrc(NDRC_FALLBACK_HTML, limit=5)
    assert len(items) == 1
    assert items[0]["source"] == "ndrc"
    assert "2026年第50号" in items[0]["doc_number"]


# ── 缺陷 2：过滤非政策页 ────────────────────────────────────────────────────

def test_gov_cn_filters_non_policy_urls_fallback():
    items = pf._parse_gov_cn(FALLBACK_HTML, limit=10)
    urls = [it["source_url"] for it in items]
    assert any("t20261110_1001.htm" in u for u in urls)
    assert not any("jiucuopage" in u for u in urls)
    assert all("/zhengce/" in u and (u.endswith(".htm") or u.endswith(".html")) for u in urls)


def test_gov_cn_filters_non_policy_urls_block_path():
    """主路径 _parse_blocks 也要过滤，且只认 www.gov.cn/gov.cn host。"""
    items = pf._parse_gov_cn(BLOCK_HTML, limit=10)
    urls = [it["source_url"] for it in items]
    assert len(urls) == 1
    assert urls[0].startswith("https://www.gov.cn/zhengce/")
    assert not any("jiucuopage" in u for u in urls)
    assert not any("evil.example.com" in u for u in urls)


def test_non_policy_url_never_written(db, monkeypatch):
    """过滤必须发生在写库前：网站纠错页不得落库。"""
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: FALLBACK_HTML)
    result = pf.refresh_policies(include_detail=False, limit=10)
    assert result["written"] == 2
    rows = ps.read_recent(20)
    assert len(rows) == 2
    assert all("jiucuopage" not in r["source_url"] for r in rows)


def test_gov_cn_all_non_policy_returns_empty(monkeypatch):
    """过滤后为空则诚实返回空，让上层降级，不保留脏条目。"""
    html = '<html><body><a href="/fuwu/jiucuopage.html">网站纠错入口</a></body></html>'
    assert pf._parse_gov_cn(html, limit=10) == []


# ── 缺陷 3：详情页日期 + 未来日期守卫 ───────────────────────────────────────

def test_fetch_policy_detail_extracts_publish_time(monkeypatch):
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: DETAIL_HTML)
    detail = pf.fetch_policy_detail("https://www.gov.cn/zhengce/202611/content_7085743.htm")
    assert detail["publish_date"] == "2026-11-10"
    assert detail["body_source"] == "html"


def test_fetch_policy_detail_ignores_naked_date(monkeypatch):
    """正文里的裸日期/施行日期不得冒充发布时间。"""
    html = "<div>自2027年1月1日起施行</div><div>2026-11-09</div>"
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: html)
    detail = pf.fetch_policy_detail("https://www.gov.cn/zhengce/x.htm")
    assert detail["publish_date"] is None


def test_fetch_policy_detail_only_scans_first_30_parts(monkeypatch):
    """发布时间出现在第 31 段时不得被采信（只扫前 30 段）。"""
    parts = [f"占位{i}" for i in range(30)] + ["2026-11-10 22:09"]
    html = "".join(f"<p>{p}</p>" for p in parts)
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: html)
    detail = pf.fetch_policy_detail("https://www.gov.cn/zhengce/x.htm")
    assert detail["publish_date"] is None


def test_detail_date_overrides_future_list_date(db, monkeypatch):
    """详情页真实发布时间覆盖列表块的施行日期 2027-01-01。"""
    def fake_get(url, timeout=None):
        if url == pf.GOV_CN_URL:
            return LIST_WITH_FUTURE_DATE
        return DETAIL_HTML

    monkeypatch.setattr(pf, "_http_get", fake_get)
    result = pf.refresh_policies(include_detail=True, limit=10)
    assert result["written"] == 1
    stats = ps.policy_store_stats()
    assert stats["latest_publish_date"] == "2026-11-10"
    row = ps.read_recent(1)[0]
    assert row["publish_date"] == "2026-11-10"
    assert row["body_source"] == "html"
    assert "2026-11-10 22:09" in row["body_text"]


def test_future_publish_date_guarded_before_write(db, monkeypatch):
    """未来日期 2099-01-01 写入前必须被置 None（mutation 目标用例）。"""
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: FUTURE_LIST_HTML)
    result = pf.refresh_policies(include_detail=False, limit=10)
    assert result["written"] == 1
    assert ps.policy_store_stats()["latest_publish_date"] is None
    row = ps.read_recent(1)[0]
    assert row["publish_date"] is None


def test_guard_publish_date_helper():
    assert pf._guard_publish_date("2099-01-01") is None
    assert pf._guard_publish_date("2026-11-10") == "2026-11-10"
    assert pf._guard_publish_date(None) is None
    assert pf._guard_publish_date("bad-date") is None
