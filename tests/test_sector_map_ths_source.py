# -*- coding: utf-8 -*-
"""行业映射切源到同花顺链路的离线确定性测试。

全程 monkeypatch akshare 与 urllib 边界：不真联网、不依赖真实 akshare 数据。
"""
import logging
import re
import sqlite3
import sys
import types

import pandas as pd
import pytest

from modules import sector_map as sm
from modules import sector_map_fetch as fetcher


# ── 受控替身 ──────────────────────────────────────────────────────────────

def _fake_akshare(rows=None, *, boom=None):
    """构造假 akshare；只提供 _ths_board_codes 需要的那个接口。"""
    fake = types.ModuleType("akshare")

    def _name_ths():
        if boom:
            raise boom
        return pd.DataFrame(rows or [], columns=["name", "code"])

    fake.stock_board_industry_name_ths = _name_ths
    return fake


class _Resp:
    def __init__(self, text):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._text.encode("gbk")


def _page_html(members, page, total):
    """构造同花顺详情页 HTML：每行 index=1 是代码、index=2 是名称。"""
    trs = []
    for i, (code, name) in enumerate(members, 1):
        trs.append(
            "<tr><td>%d</td><td><a href='/x'>%s</a></td>"
            "<td><span class='name'>%s</span></td></tr>" % (i, code, name)
        )
    return (
        "<html><body><table><tr><th>序号</th><th>代码</th><th>名称</th></tr>%s"
        "</table><span class=\"page_info\">%d/%d</span></body></html>"
    ) % ("".join(trs), page, total)


def _install_pages(monkeypatch, pages, *, seen_urls=None, fail_pages=None):
    """把 _urlopen 换成按页返回受控 HTML 的替身；fail_pages={'2': 失败次数}。"""
    fail_pages = dict(fail_pages or {})

    def _fake(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if seen_urls is not None:
            seen_urls.append(url)
        m = re.search(r"/page/(\d+)/", url)
        page = int(m.group(1)) if m else 1
        if fail_pages.get(page, 0) > 0:
            fail_pages[page] -= 1
            raise OSError("forced page failure %d" % page)
        return _Resp(pages[page])

    monkeypatch.setattr(fetcher, "_urlopen", _fake)
    return _fake


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "news.db"
    monkeypatch.setenv("SECTOR_MAP_DB_PATH", str(path))
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE sectors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            keywords TEXT NOT NULL,
            stock_codes TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()
    sm.init_table()
    return path


def _patch_refresh(monkeypatch, names, codes, member_fn):
    """把 refresh_sector_map 的三个外部依赖全换成受控替身。"""
    monkeypatch.setattr(
        fetcher, "fetch_industry_names",
        lambda: [{"name": n, "source": "ths"} for n in names],
    )
    monkeypatch.setattr(fetcher, "_ths_board_codes", lambda: dict(codes))
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    em_calls = []
    monkeypatch.setattr(
        fetcher, "_fetch_em_board_index",
        lambda **kw: (em_calls.append(kw) or (_ for _ in ()).throw(
            AssertionError("主流程不得调用东财 _fetch_em_board_index"))),
    )
    calls = []

    def _members(code, **kwargs):
        calls.append(code)
        return member_fn(code)

    monkeypatch.setattr(fetcher, "fetch_members_ths", _members)
    return calls, em_calls


# ── _ths_board_codes ──────────────────────────────────────────────────────

def test_ths_board_codes_maps_names_to_6digit_codes(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", _fake_akshare([
        ("半导体", 881121), ("银行", "881155"), ("保险", "881156"),
        ("证券", "881157"), ("坏代码", "BK0001"),
    ]))
    assert fetcher._ths_board_codes() == {
        "半导体": "881121", "银行": "881155",
        "保险": "881156", "证券": "881157",
    }


def test_ths_board_codes_exception_returns_empty_and_logs(monkeypatch, caplog):
    monkeypatch.setitem(
        sys.modules, "akshare",
        _fake_akshare(boom=RuntimeError("THS 不可达")),
    )
    with caplog.at_level(logging.WARNING):
        assert fetcher._ths_board_codes() == {}
    assert "板块代码表获取失败" in caplog.text


def test_ths_board_codes_missing_columns_returns_empty(monkeypatch, caplog):
    fake = types.ModuleType("akshare")
    fake.stock_board_industry_name_ths = lambda: pd.DataFrame(
        [("半导体", "881121")], columns=["板块", "代码"])
    monkeypatch.setitem(sys.modules, "akshare", fake)
    with caplog.at_level(logging.WARNING):
        assert fetcher._ths_board_codes() == {}
    assert "缺 name/code 列" in caplog.text


# ── fetch_members_ths ─────────────────────────────────────────────────────

def test_fetch_members_ths_cross_page_dedup_in_order(monkeypatch):
    pages = {
        1: _page_html([("688981", "中芯国际"), ("688256", "寒武纪")], 1, 2),
        2: _page_html([("688981", "中芯国际"), ("688120", "华海清科")], 2, 2),
    }
    seen_urls = []
    sleeps = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: sleeps.append(s))
    _install_pages(monkeypatch, pages, seen_urls=seen_urls)

    out = fetcher.fetch_members_ths("881121", delay=0.8, retries=2)

    assert out == [
        {"code": "688981", "name": "中芯国际"},
        {"code": "688256", "name": "寒武纪"},
        {"code": "688120", "name": "华海清科"},
    ]
    assert seen_urls == [
        "https://q.10jqka.com.cn/thshy/detail/code/881121/",
        "https://q.10jqka.com.cn/thshy/detail/code/881121/page/2/",
    ]
    assert all("/ajax/" not in u for u in seen_urls)
    assert sleeps == [0.8]  # 页间限速，非重试


def test_fetch_members_ths_empty_tail_page_tolerated(monkeypatch):
    pages = {
        1: _page_html([("601398", "工商银行")], 1, 3),
        2: _page_html([], 2, 3),  # 尾页 0 行
        3: _page_html([], 3, 3),
    }
    _install_pages(monkeypatch, pages)
    assert fetcher.fetch_members_ths("881155", delay=0) == [
        {"code": "601398", "name": "工商银行"}
    ]


def test_fetch_members_ths_retries_page_failure_then_succeeds(monkeypatch):
    pages = {1: _page_html([("600519", "贵州茅台")], 1, 1)}
    sleeps = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: sleeps.append(s))
    _install_pages(monkeypatch, pages, fail_pages={1: 2})
    out = fetcher.fetch_members_ths("881999", delay=0.8, retries=3)
    assert out == [{"code": "600519", "name": "贵州茅台"}]
    assert sleeps == [0.8, 1.6]  # 指数退避


def test_fetch_members_ths_all_pages_fail_returns_empty(monkeypatch, caplog):
    pages = {1: _page_html([("600519", "贵州茅台")], 1, 1)}
    sleeps = []
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: sleeps.append(s))
    _install_pages(monkeypatch, pages, fail_pages={1: 99})
    with caplog.at_level(logging.WARNING):
        assert fetcher.fetch_members_ths("881999", delay=0.8, retries=2) == []
    assert sleeps == [0.8]  # retries=2 → 2 次尝试，1 次退避
    assert "未抓到任何成分股" in caplog.text


def test_fetch_members_ths_sets_browser_user_agent(monkeypatch):
    seen = []

    def _fake(req, timeout=15):
        seen.append((req.full_url, req.headers.get("User-agent")))
        return _Resp(_page_html([("688981", "中芯国际")], 1, 1))

    monkeypatch.setattr(fetcher, "_urlopen", _fake)
    fetcher.fetch_members_ths("881121", delay=0)
    assert seen[0][0].endswith("/code/881121/")
    assert "Chrome/124" in seen[0][1]


def test_fetch_members_ths_empty_code_returns_empty(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        assert fetcher.fetch_members_ths("", delay=0) == []
    assert "空 board_code" in caplog.text


# ── refresh_sector_map 切源 / resume / 诚实 ────────────────────────────────

def test_refresh_uses_ths_codes_not_em(db, monkeypatch):
    calls, em_calls = _patch_refresh(
        monkeypatch,
        ["半导体", "银行"],
        {"半导体": "881121", "银行": "881155"},
        lambda code: [{"code": "600000", "name": "样本"}],
    )
    out = fetcher.refresh_sector_map(limit=2, resume=False)

    assert calls == ["881121", "881155"]
    assert em_calls == []
    assert out["ok"] == 2 and out["failed"] == 0
    rows = {r["board_name"]: r for r in sm.list_sectors()}
    assert rows["半导体"]["board_code"] == "881121"
    assert rows["银行"]["board_code"] == "881155"
    assert rows["半导体"]["board_type"] == "industry"
    assert rows["半导体"]["stock_codes"] == "600000"
    assert rows["半导体"]["member_count"] == 1


def test_refresh_resume_skips_ok_and_refetches_failed(db, monkeypatch):
    calls, em_calls = _patch_refresh(
        monkeypatch,
        ["半导体", "银行"],
        {"半导体": "881121", "银行": "881155"},
        lambda code: [{"code": "600000", "name": "样本"}],
    )
    fetcher.refresh_sector_map(limit=2, resume=False)  # 两者均 ok

    calls.clear()
    monkeypatch.setattr(
        fetcher, "fetch_members_ths",
        lambda code, **kw: (calls.append(code) or []),  # 这次全抓空
    )
    out = fetcher.refresh_sector_map(limit=2, resume=True)
    assert calls == []  # ok 行业全跳过
    assert out["skipped"] >= 2

    sm.mark_failed("银行")
    calls.clear()
    monkeypatch.setattr(
        fetcher, "fetch_members_ths",
        lambda code, **kw: (calls.append(code) or [{"code": "601398", "name": "工商银行"}]),
    )
    out = fetcher.refresh_sector_map(limit=2, resume=True)
    assert calls == ["881155"]
    assert out["ok"] == 1
    assert em_calls == []
    row = {r["board_name"]: r for r in sm.list_sectors()}["银行"]
    assert row["fetch_status"] == "ok" and row["member_count"] == 1


def test_refresh_empty_members_marks_failed_not_fabricated(db, monkeypatch):
    _patch_refresh(
        monkeypatch,
        ["保险"],
        {"保险": "881156"},
        lambda code: [],
    )
    out = fetcher.refresh_sector_map(limit=1, resume=False)
    assert out["ok"] == 0 and out["failed"] == 1
    row = sm.list_sectors()[0]
    assert row["board_name"] == "保险"
    assert row["fetch_status"] == "failed"
    assert row["stock_codes"] == "" and row["member_count"] == 0
    assert row["board_code"] in (None, "")  # 失败不写入伪代码冒充成功


def test_refresh_missing_ths_code_marks_failed_without_fetch(db, monkeypatch):
    calls, em_calls = _patch_refresh(monkeypatch, ["未知行业"], {}, lambda code: [])
    out = fetcher.refresh_sector_map(limit=1, resume=False)
    assert calls == [] and em_calls == []
    assert out["failed"] == 1
    assert sm.list_sectors()[0]["fetch_status"] == "failed"


def test_refresh_never_writes_ok_with_zero_members(db, monkeypatch):
    _patch_refresh(
        monkeypatch,
        ["甲", "乙"],
        {"甲": "881121", "乙": "881155"},
        lambda code: [] if code == "881155" else [{"code": "600000", "name": "样本"}],
    )
    fetcher.refresh_sector_map(limit=2, resume=False)
    for r in sm.list_sectors():
        assert not (r["fetch_status"] == "ok" and r["member_count"] == 0)
