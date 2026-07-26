"""
tests/test_ai_engine_jobs.py

纯离线测试：只验证 `_build_stock_jobs` 这条「任务构造」逻辑。
R5/R6：缺失或空 code 的条目必须跳过而不是抛 KeyError；返回去重后的任务列表。

不依赖网络 / LLM / Streamlit；必要时 stub streamlit 以便导入模块。
"""
import sys
import types

# 导入整个模块可能因环境缺少 streamlit 而失败，提前 stub（不影响被测试纯函数）。
sys.modules.setdefault("streamlit", types.ModuleType("streamlit"))

from modules.ai_engine import _build_stock_jobs


def test_normal_dict_returns_job():
    """(a) 正常 {code, name} 字典应生成对应任务。"""
    resolved = [{"code": "600519", "name": "贵州茅台"}]
    jobs = _build_stock_jobs(resolved)
    assert jobs == [("600519", "贵州茅台")]


def test_missing_code_is_skipped():
    """(b) 缺失 'code' 的条目应被跳过，不抛 KeyError。"""
    resolved = [
        {"name": "无名氏"},
        {"code": "000001", "name": "平安银行"},
    ]
    jobs = _build_stock_jobs(resolved)
    assert jobs == [("000001", "平安银行")]


def test_missing_name_uses_empty_string():
    """(c) 缺失 'name' 仍应保留该任务，name 回退为空串。"""
    resolved = [
        {"code": "300750"},
        {"code": "600519", "name": "贵州茅台"},
    ]
    jobs = _build_stock_jobs(resolved)
    assert ("300750", "") in jobs
    assert ("600519", "贵州茅台") in jobs
    assert len(jobs) == 2


def test_empty_code_is_skipped():
    """空字符串 code 也应被跳过。"""
    resolved = [
        {"code": "", "name": "空代码"},
        {"code": "600519", "name": "贵州茅台"},
    ]
    jobs = _build_stock_jobs(resolved)
    assert jobs == [("600519", "贵州茅台")]


def test_duplicate_codes_deduped():
    """相同 code 不应重复出现。"""
    resolved = [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "600519", "name": "茅台"},
    ]
    jobs = _build_stock_jobs(resolved)
    assert jobs == [("600519", "贵州茅台")]


def test_empty_list_returns_empty():
    """空输入返回空列表，不抛错。"""
    assert _build_stock_jobs([]) == []
