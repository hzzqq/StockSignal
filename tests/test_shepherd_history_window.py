"""炸板股池「最近 30 个交易日」窗口守卫。

背景（真实缺陷，勿回退）：
    东财炸板股池接口只能取最近 30 个交易日。历史拉取 `_fetch_shepherd_history`
    原先对**每一个**交易日都请求一次，超窗口的日期必然抛
    「炸板股池只能获取最近 30 个交易日的数据」。叠加 `_retry(max_retries=2)`
    等于每个超窗口日白打 2 次请求：拉 90 天历史时约 120 次无效网络往返，
    既把每日快照拖慢数十秒，又加剧 legu 限流（曾连续两天 FAIL）。

修复：按 `_ZBGC_MAX_DAYS` 裁剪，超窗口日期**根本不请求**。

本测试用 monkeypatch 顶掉全部网络函数，直接数 `_fetch_zbgc_pool` 的调用次数，
属于可证伪断言——把窗口裁剪去掉，这里立刻变红。

运行：pytest tests/test_shepherd_history_window.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

import modules.shepherd as S

CALLS = {"zbgc": [], "zt": [], "prev": []}


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    CALLS["zbgc"].clear()
    CALLS["zt"].clear()
    CALLS["prev"].clear()

    n_days = {"v": 70}

    def fake_trading_days(n):
        return [f"D{i:03d}" for i in range(n)]

    def fake_zt_pool(d):
        CALLS["zt"].append(d)
        return {"limit_up": 40}

    def fake_zbgc_pool(d):
        CALLS["zbgc"].append(d)
        return {"zt_fail_count": 10}

    def fake_prev_pool(d):
        CALLS["prev"].append(d)
        return {"zt_prev_ret": 1.0}

    def fake_legu():
        return {"up_count": 100, "down_count": 100}

    def fake_spot():
        return {"median_chg": 0.1}

    monkeypatch.setattr(S, "_trading_days", fake_trading_days)
    monkeypatch.setattr(S, "_fetch_zt_pool", fake_zt_pool)
    monkeypatch.setattr(S, "_fetch_zbgc_pool", fake_zbgc_pool)
    monkeypatch.setattr(S, "_fetch_prev_pool", fake_prev_pool)
    monkeypatch.setattr(S, "_fetch_legu", fake_legu)
    monkeypatch.setattr(S, "_get_spot_cached", fake_spot)
    monkeypatch.setattr(S, "time", type("T", (), {"sleep": staticmethod(lambda *_a: None)}))
    monkeypatch.setattr(S, "_pdate", lambda s: pd.to_datetime(s, errors="coerce"))
    yield n_days


def test_zbgc_only_requests_last_30_trading_days():
    """70 个交易日 → 炸板股池只应请求最后 30 个，而不是 70 个。"""
    S._fetch_shepherd_history(70)
    assert len(CALLS["zbgc"]) == 30, (
        f"炸板股池请求了 {len(CALLS['zbgc'])} 次，期望 30 次（接口只支持最近 30 个交易日）"
    )
    # 且必须是**最近的** 30 个（末尾对齐），不是前 30 个
    assert CALLS["zbgc"] == [f"D{i:03d}" for i in range(40, 70)]


def test_other_pools_still_full_window():
    """裁剪只针对炸板股池；涨停池/昨日涨停池没有该限制，仍应覆盖全窗口。"""
    S._fetch_shepherd_history(70)
    assert len(CALLS["zt"]) == 70
    assert len(CALLS["prev"]) == 70


def test_window_shorter_than_cap_requests_all():
    """窗口本身不足 30 天时，不应少请求（裁剪不能反向砍掉有效日期）。"""
    S._fetch_shepherd_history(12)
    assert len(CALLS["zbgc"]) == 12


def test_cap_constant_matches_interface_limit():
    """常量值就是接口硬限制 30，改动需同步修改本测试。"""
    assert S._ZBGC_MAX_DAYS == 30
