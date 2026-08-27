"""modules/errors.report_error 的单元测试：纯工具，不依赖业务/网络。"""
import logging

import pytest

from modules.errors import report_error


def test_report_error_logs_and_returns_summary(caplog):
    caplog.set_level(logging.WARNING, logger="fetch_parallel")
    out = report_error("fetch_parallel", ValueError("boom"), context="single task")
    # 返回单行安全摘要，含模块名 + 上下文 + 异常信息
    assert "fetch_parallel" in out
    assert "single task" in out
    assert "boom" in out
    # 且仅以 warning 级别记录一条，不含 traceback
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert "boom" in caplog.records[0].message


def test_report_error_without_context(caplog):
    caplog.set_level(logging.WARNING, logger="mod_x")
    out = report_error("mod_x", KeyError("k"))
    assert "mod_x" in out
    assert "k" in out
    assert "处理异常: " in out


def test_report_error_does_not_leak_traceback(caplog):
    """上报内容不应包含完整堆栈文本（安全基线：不向日志外泄堆栈无关信息）。"""
    caplog.set_level(logging.WARNING, logger="mod_y")
    report_error("mod_y", RuntimeError("oops"))
    # 单行摘要，不应出现换行（traceback 必然多行）
    assert "\n" not in caplog.records[0].message
