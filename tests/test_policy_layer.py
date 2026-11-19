# -*- coding: utf-8 -*-
"""政策抓取层离线单测。

全部使用 monkeypatch 假 HTML / 假 fetch —— 零真实网络、确定性。
真实抓取验证是另一回事，由 scripts/refresh_policies --check 手动执行。
"""
import ast
import os
import re
import sys
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import policy_fetch as pf  # noqa: E402
from modules import policy_store as ps  # noqa: E402


GOV_HTML = """
<html><body><ul>
  <li><a href="/zhengce/content/202611/t20261110_1001.htm">关于加快Policy建设的若干意见</a><span>2026-11-10</span></li>
  <li><a href="https://www.gov.cn/zhengce/content/202611/t20261109_1002.htm">促进Policy高质量发展的实施方案</a><span class="date">2026-11-09</span></li>
  <li><a href="/zhengce/content/202611/t20261108_1003.htm">无日期政策标题示例文本</a></li>
</ul></body></html>
"""

NDRC_HTML = """
<html><body><ul>
  <li><a href="/xxgk/zcfb/fzggwl/202611/t20261115_2001.htm">国家发展改革委2026年第50号令</a><span>2026-11-15</span></li>
</ul></body></html>
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    """每个用例隔离到 tmp 库，绝不污染 data/policy.db。"""
    monkeypatch.setenv("POLICY_DB_PATH", str(tmp_path / "policy.db"))
    return str(tmp_path / "policy.db")


def _doc(url="https://www.gov.cn/a", title="政策甲", date="2026-11-10", body=None, source="gov.cn"):
    return {
        "title": title,
        "source_url": url,
        "publish_date": date,
        "source": source,
        "body_text": body,
        "body_source": "html" if body else "none",
    }


# ── 列表解析 ─────────────────────────────────────────────────────────────────

def test_parse_gov_cn_extracts_fields():
    items = pf._parse_gov_cn(GOV_HTML, limit=10)
    assert len(items) >= 2
    first = items[0]
    assert first["title"] == "关于加快Policy建设的若干意见"
    assert first["publish_date"] == "2026-11-10"
    assert first["source"] == "gov.cn"
    assert first["source_url"].startswith("https://www.gov.cn/")


def test_parse_gov_cn_missing_date_is_none():
    items = pf._parse_gov_cn(GOV_HTML, limit=10)
    nodate = [i for i in items if "无日期" in i["title"]]
    assert len(nodate) == 1
    assert nodate[0]["publish_date"] is None  # 缺失 → None，不兜底 now


def test_parse_gov_cn_url_normalized():
    items = pf._parse_gov_cn(GOV_HTML, limit=10)
    urls = [i["source_url"] for i in items]
    assert any("t20261110_1001.htm" in u for u in urls)
    assert all(u.startswith("https://www.gov.cn/") for u in urls)


def test_parse_ndrc_doc_number_and_body():
    items = pf._parse_ndrc(NDRC_HTML, limit=10)
    assert len(items) == 1
    it = items[0]
    assert it["doc_number"] and "2026年第50号" in it["doc_number"]
    assert it["issuing_body"] == "国家发展和改革委员会"
    assert it["source"] == "ndrc"
    assert it["publish_date"] == "2026-11-15"


def test_fetch_gov_cn_http_error_returns_empty(monkeypatch):
    def boom(url, timeout=None):
        raise RuntimeError("network down")
    monkeypatch.setattr(pf, "_http_get", boom)
    assert pf.fetch_gov_cn(5) == []


# ── 详情页 ───────────────────────────────────────────────────────────────────

def test_fetch_policy_detail_attachment(monkeypatch):
    html = '<a href="2026年第50号令.pdf">PDF 附件</a><p>这里只有令的说明</p>'
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: html)
    d = pf.fetch_policy_detail("https://x/detail.htm")
    assert d["body_text"] is None
    assert d["body_source"] == "attachment"


def test_fetch_policy_detail_html_body(monkeypatch):
    html = "<html><body><script>x()</script><div>正文第一段</div><p>正文第二段</p></body></html>"
    monkeypatch.setattr(pf, "_http_get", lambda url, timeout=None: html)
    d = pf.fetch_policy_detail("https://x/detail2.htm")
    assert d["body_source"] == "html"
    assert "正文第一段" in d["body_text"]
    assert "x()" not in d["body_text"]


# ── 存储：upsert 幂等 ────────────────────────────────────────────────────────

def test_upsert_new_then_same_hash_skipped(db):
    assert ps.upsert_policy(_doc()) is True
    assert ps.upsert_policy(_doc()) is False  # content_hash 相同 → skipped
    assert ps.policy_store_stats()["total"] == 1


def test_upsert_changed_hash_updates(db):
    ps.upsert_policy(_doc(body="旧正文"))
    assert ps.upsert_policy(_doc(body="新正文")) is True
    rows = ps.read_recent(5)
    assert rows[0]["body_text"] == "新正文"
    assert ps.policy_store_stats()["total"] == 1


def test_upsert_keeps_none_publish_date(db):
    ps.upsert_policy(_doc(date=None))
    row = ps.read_recent(1)[0]
    assert row["publish_date"] is None
    assert row["crawled_at"]  # 抓取时间在，但不冒充数据日期


# ── 存储：读 / 统计 / TTL ────────────────────────────────────────────────────

def test_read_recent_empty_returns_list(db):
    assert ps.read_recent(10) == []


def test_read_recent_ordered_by_date(db):
    ps.upsert_policy(_doc(url="https://x/1", title="旧", date="2026-01-01"))
    ps.upsert_policy(_doc(url="https://x/2", title="新", date="2026-11-10"))
    ps.upsert_policy(_doc(url="https://x/3", title="中", date="2026-06-01"))
    rows = ps.read_recent(10)
    assert [r["title"] for r in rows] == ["新", "中", "旧"]


def test_stats_by_source(db):
    ps.upsert_policy(_doc(url="https://g/1", source="gov.cn"))
    ps.upsert_policy(_doc(url="https://n/1", source="ndrc"))
    st = ps.policy_store_stats()
    assert st["total"] == 2
    assert st["by_source"] == {"gov.cn": 1, "ndrc": 1}


def test_is_fresh_ttl():
    today = datetime.now().strftime("%Y-%m-%d")
    old = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    assert ps.is_fresh(today) is True
    assert ps.is_fresh(old) is False
    assert ps.is_fresh(None) is False
    assert ps.is_fresh("bad-date") is False


# ── 编排：降级 / 去重 / 两源空 ───────────────────────────────────────────────

def test_both_sources_empty_no_write(db, monkeypatch):
    monkeypatch.setattr(pf, "fetch_gov_cn", lambda limit=40: [])
    monkeypatch.setattr(pf, "fetch_ndrc", lambda limit=20: [])
    called = []
    monkeypatch.setattr(pf._store, "upsert_policy", lambda d: called.append(d) or True)
    res = pf.refresh_policies(limit=5)
    assert res["written"] == 0
    assert res["failed"] >= 1
    assert res["source"] is None
    assert called == []
    assert ps.policy_store_stats()["total"] == 0


def test_refresh_uses_fallback_and_dedup(db, monkeypatch):
    monkeypatch.setattr(pf, "fetch_gov_cn", lambda limit=40: [])
    monkeypatch.setattr(pf, "fetch_ndrc", lambda limit=20: [
        {"title": "N1", "source_url": "https://ndrc/1", "publish_date": "2026-11-15", "source": "ndrc"},
        {"title": "N2", "source_url": "https://ndrc/2", "publish_date": "2026-11-14", "source": "ndrc"},
    ])
    r1 = pf.refresh_policies(limit=5)
    assert r1["source"] == "ndrc"
    assert r1["written"] == 2
    r2 = pf.refresh_policies(limit=5)
    assert r2["written"] == 0
    assert r2["skipped"] == 2
    assert ps.policy_store_stats()["total"] == 2


# ── 诚实红线 / 不变量守卫 ────────────────────────────────────────────────────

def test_honesty_no_now_as_publish_date_no_zero_fallback():
    now_pat = re.compile(r"publish_date\s*=\s*[^\n]*now\(|[\"']publish_date[\"']\s*:\s*[^\n]*now\(")
    for mod in (ps, pf):
        with open(mod.__file__, encoding="utf-8") as f:
            src = f.read()
        for line in src.splitlines():
            code = line.split("#", 1)[0]  # 去注释，避免诚实声明文本误伤
            assert not now_pat.search(code), f"{mod.__name__}: now() 充当 publish_date: {line}"
            assert not re.search(r"\bor\s+0\b", code), f"{mod.__name__}: 存在 or 0 补零: {line}"
            assert "??" not in code, f"{mod.__name__}: 存在 ?? 补零: {line}"


def test_no_conn_leak_in_policy_modules():
    def is_conn_call(node):
        if not isinstance(node, ast.Call):
            return False
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        return name in ("_get_conn", "get_conn")

    for mod in (ps, pf):
        with open(mod.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name in {"_get_conn", "get_conn"}:
                continue  # 工厂函数把连接 return 给调用方关闭
            assigned = set()
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign) and is_conn_call(node.value):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            assigned.add(t.id)
            if not assigned:
                continue
            closed = set()
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "close" and isinstance(node.func.value, ast.Name)):
                    closed.add(node.func.value.id)
            assert assigned <= closed, f"{mod.__name__}:{fn.name} 连接未关闭: {assigned - closed}"
