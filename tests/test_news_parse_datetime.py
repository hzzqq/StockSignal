r"""
tests/test_news_parse_datetime.py
================================
回归：东方财富要闻 HTML 解析 `_parse_eastmoney_yw` 的时间戳 fidelity。

历史 bug：日期正则的 alternation 把 `\d{4}-\d{2}-\d{2}` 放在最前，
导致 HTML 里出现的完整时间戳「2026-07-30 14:25」被抢先只截到日期，
「时:分」被静默丢弃 —— 新闻时间精度丢失。
修复后：优先匹配「年-月-日 [时:分[:秒]]」完整时间戳，时间得以保留。
"""
from __future__ import annotations

from modules._news_io import NewsFetcher


def _wrap(href, title, date_near):
    # 在 <a> 附近 500 字符内放置日期串，模拟真实页面结构
    return (
        f'<div><a href="{href}">{title}</a>'
        f'<span class="t">{date_near}</span></div>'
    )


def test_full_datetime_time_preserved():
    html = _wrap(
        "https://finance.eastmoney.com/a/202607301425123456.html",
        "今日重大财经要闻发布",
        "2026-07-30 14:25",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert len(items) == 1
    assert items[0]["date"] == "2026-07-30 14:25", items[0]["date"]


def test_full_datetime_with_seconds_preserved():
    html = _wrap(
        "https://finance.eastmoney.com/a/20260730142530123456.html",
        "盘中快讯：指数异动",
        "2026-07-30 14:25:30",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert items[0]["date"] == "2026-07-30 14:25:30", items[0]["date"]


def test_date_only_unchanged():
    html = _wrap(
        "https://finance.eastmoney.com/a/202607300000123456.html",
        "收盘综述：三大指数涨跌互现",
        "2026-07-30",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert items[0]["date"] == "2026-07-30", items[0]["date"]


def test_two_digit_datetime_gets_year_prefix():
    html = _wrap(
        "https://finance.eastmoney.com/a/202607300000123456.html",
        "早间财经摘要",
        "07-30 09:15",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    # 2位年月 + 时分 -> 补全年份
    assert items[0]["date"].endswith("07-30 09:15"), items[0]["date"]
    assert items[0]["date"].count("-") == 2  # 形如 2026-07-30 09:15


def test_two_digit_date_gets_year_prefix():
    html = _wrap(
        "https://finance.eastmoney.com/a/202607300000123456.html",
        "周报：行业资金流向",
        "07-30",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert items[0]["date"] == "2026-07-30", items[0]["date"]


def test_no_date_falls_back_to_today():
    import datetime
    html = _wrap(
        "https://finance.eastmoney.com/a/202607300000123456.html",
        "无日期标记的要闻",
        "无关文本没有日期",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert items[0]["date"] == datetime.datetime.now().strftime("%Y-%m-%d"), items[0]["date"]


def test_short_title_skipped():
    html = _wrap(
        "https://finance.eastmoney.com/a/202607300000123456.html",
        "短",  # 少于 6 字
        "2026-07-30 10:00",
    )
    items = NewsFetcher._parse_eastmoney_yw(html)
    assert items == []


def test_malformed_html_no_crash():
    # 无合法 href 结构 -> 不抛异常，返回空列表
    items = NewsFetcher._parse_eastmoney_yw("<p>没有链接的纯文本</p>")
    assert items == []


def test_source_level_regex_prefers_full_datetime():
    """源码级防回退：日期正则首选项必须含可选的时间部分，防止时间被丢弃。"""
    import pathlib
    src = pathlib.Path("modules/_news_io.py").read_text(encoding="utf-8")
    # 断言首选项包含「完整日期 + 可选时间」的写法
    assert r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}" in src
