"""
资金流向模块「卡住」回归测试（离线可跑，无需网络）。

根因：akshare 个股资金流接口底层 requests 不设 timeout，上游/代理挂起时
get_individual_fund_flow / get_individual_fund_flow_series 会无限阻塞，
导致资金流向页 / 盯盘页一直转圈。

本测试通过 monkeypatch 让底层取数「永久挂起」，验证：
  - _run_with_timeout 能按时截断并返回 None；
  - get_individual_fund_flow 在 _real 挂起时按时返回 source='none'；
  - get_individual_fund_flow_series 在 _fetch_individual_real 挂起时按时返回空 DF(source='none')；
  - 全局 requests 默认超时补丁已注入。
"""
import time

import pytest

import modules.fundflow as fundflow
import modules.linear_trends as linear_trends


def test_run_with_timeout_returns_none_on_hang():
    """挂起的 fn 必须在 timeout 内被截断，不能真的等满。"""
    t0 = time.monotonic()
    res = fundflow._run_with_timeout(lambda: time.sleep(30), timeout=0.3)
    elapsed = time.monotonic() - t0
    assert res is None
    assert elapsed < 3.0, f"超时未生效，耗时 {elapsed:.2f}s"


def test_individual_fund_flow_bounded_on_real_hang(monkeypatch):
    """get_individual_fund_flow 在真实接口无限挂起时必须按时降级为 none。"""
    monkeypatch.setattr(fundflow, "_real", lambda code: time.sleep(30))
    # 隔离估算兜底，避免拖长测试
    monkeypatch.setattr(fundflow, "_estimate_individual_fund_flow",
                        lambda code: {"source": "none", "main_net": None,
                                      "main_net_pct": None, "big_net": None,
                                      "super_net": None, "latest_date": None})

    t0 = time.monotonic()
    out = fundflow.get_individual_fund_flow("600519", use_estimate_fallback=True, timeout=1.0)
    elapsed = time.monotonic() - t0

    assert elapsed < 5.0, f"个股资金流未按时降级，耗时 {elapsed:.2f}s"
    assert isinstance(out, dict)
    assert out.get("source") == "none"


def test_individual_fund_flow_series_bounded_on_real_hang(monkeypatch):
    """get_individual_fund_flow_series 在真实接口挂起时必须按时返回空 DF。"""
    monkeypatch.setattr(linear_trends, "_fetch_individual_real", lambda c, m: time.sleep(30))
    # 估算兜底快速返回空，聚焦真实接口挂起路径
    import pandas as pd
    monkeypatch.setattr(linear_trends, "_estimate_individual_series",
                        lambda code, days: pd.DataFrame(
                            columns=["date", "main_net", "super_net", "big_net"]))
    fundflow._CACHE.clear()  # 避免命中 600s 缓存

    t0 = time.monotonic()
    out = linear_trends.get_individual_fund_flow_series("999999", days=60)
    elapsed = time.monotonic() - t0

    assert elapsed < 15.0, f"个股资金序列未按时降级，耗时 {elapsed:.2f}s"
    assert out is not None
    assert out.attrs.get("source") == "none"


def test_global_request_timeout_patched():
    """fundflow 导入即注入 requests 默认超时，防止 akshare 无限挂起。"""
    import requests
    assert getattr(requests.Session.request, "_ss_timeout_patched", False) is True


def test_patch_requests_timeout_is_idempotent():
    """重复调用 _patch_requests_timeout 不叠加多层补丁。"""
    import requests
    before = requests.Session.request
    fundflow._patch_requests_timeout()
    after = requests.Session.request
    assert before is after, "重复 patch 不应产生嵌套包装"
