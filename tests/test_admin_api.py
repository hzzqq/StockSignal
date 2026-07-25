"""modules/admin_api 回归测试（无网依赖，mock session api_*）。

覆盖：
- build_query：安全编码查询串（新增能力）+ 跳过空值
- 列表接口：keyword 含 & / 空格 / 中文 时正确编码（修复 f-string 直插的隐性 bug）
- 写接口：post/put/delete 正确调用
"""
from unittest.mock import Mock

import modules.admin_api as A


def _called_url(mock):
    return mock.call_args[0][0]


def test_build_query_basic():
    assert A.build_query(page=1, per_page=50) == "?page=1&per_page=50"


def test_build_query_skips_empty_and_none():
    # 空字符串 / None 不应进入查询串
    assert A.build_query(page=2, keyword="") == "?page=2"
    assert A.build_query(page=2, keyword=None) == "?page=2"
    assert A.build_query() == ""


def test_build_query_encodes_special_chars():
    q = A.build_query(keyword="a b&c")
    assert "keyword=" in q
    assert "%26" in q          # & 被编码
    assert "a+b" in q or "a%20b" in q   # 空格被编码


def test_search_stocks_encodes_keyword(monkeypatch):
    get = Mock(return_value={"ok": True})
    monkeypatch.setattr(A, "api_get", get)
    A.search_stocks("银行 & 保险")
    url = _called_url(get)
    assert url.startswith("/api/stocks/search?")
    assert "%26" in url          # & 已被编码，不会拆出额外参数


def test_get_users_encodes_chinese(monkeypatch):
    get = Mock(return_value={"data": []})
    monkeypatch.setattr(A, "api_get", get)
    A.get_users(page=2, per_page=10, keyword="煤炭")
    url = _called_url(get)
    assert "page=2" in url and "per_page=10" in url
    assert "keyword=" in url      # 中文已被 urlencode，不再是裸字符


def test_get_stock_list_omits_empty_keyword(monkeypatch):
    get = Mock(return_value={})
    monkeypatch.setattr(A, "api_get", get)
    A.get_stock_list(page=1, per_page=50, keyword="")
    url = _called_url(get)
    assert "keyword" not in url


def test_create_user_posts(monkeypatch):
    post = Mock(return_value={"id": 1})
    monkeypatch.setattr(A, "api_post", post)
    A.create_user("alice", "pw", "admin")
    assert post.called
    assert post.call_args[0][0] == "/api/admin/users"
    assert post.call_args[0][1]["role"] == "admin"


def test_update_user_puts(monkeypatch):
    put = Mock(return_value={})
    monkeypatch.setattr(A, "api_put", put)
    A.update_user(7, role="admin")
    assert put.call_args[0][0] == "/api/admin/users/7"
    assert put.call_args[0][1] == {"role": "admin"}


def test_delete_watchlist_deletes(monkeypatch):
    delete = Mock(return_value={})
    monkeypatch.setattr(A, "api_delete", delete)
    A.remove_watchlist(3)
    assert delete.call_args[0][0] == "/api/watchlist/3"
