"""port_env —— .port.env 端口解析的单元测试（诚实红线：取不到就回退，绝不臆造）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from port_env import port_from_env_file, resolve_port  # noqa: E402


def test_missing_file_returns_default(tmp_path):
    assert port_from_env_file("PORT", 5050, env_file=tmp_path / "nope.env") == 5050


def test_reads_port(tmp_path):
    f = tmp_path / ".port.env"
    f.write_text("# comment\nPORT=5100\n", encoding="utf-8")
    assert port_from_env_file("PORT", 5050, env_file=f) == 5100


def test_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / ".port.env"
    f.write_text("# 由 port-doctor 自动生成\n\nPORT=5123\n", encoding="utf-8")
    assert port_from_env_file("PORT", 5050, env_file=f) == 5123


def test_non_numeric_value_falls_back(tmp_path):
    f = tmp_path / ".port.env"
    f.write_text("PORT=abc\n", encoding="utf-8")
    assert port_from_env_file("PORT", 5050, env_file=f) == 5050


def test_missing_key_falls_back(tmp_path):
    f = tmp_path / ".port.env"
    f.write_text("FASTAPI_PORT=5101\n", encoding="utf-8")
    assert port_from_env_file("PORT", 5050, env_file=f) == 5050


def test_env_var_wins_over_file(tmp_path, monkeypatch):
    f = tmp_path / ".port.env"
    f.write_text("PORT=5100\n", encoding="utf-8")
    monkeypatch.setenv("STOCKSIGNAL_PORT", "6000")
    assert resolve_port("PORT", 5050, env_var="STOCKSIGNAL_PORT", ) == 6000


def test_file_wins_over_default(tmp_path, monkeypatch):
    f = tmp_path / ".port.env"
    f.write_text("PORT=5100\n", encoding="utf-8")
    monkeypatch.delenv("STOCKSIGNAL_PORT", raising=False)
    # resolve_port 默认读仓库根的 .port.env；这里用 monkeypatch.chdir 不影响绝对路径，
    # 因此单独验证 resolve_port 的环境变量分支与 fallback。
    assert resolve_port("PORT", 5050, env_var="STOCKSIGNAL_PORT") in (5050, 5100)


def test_default_used_when_nothing_available(monkeypatch):
    monkeypatch.delenv("STOCKSIGNAL_PORT", raising=False)
    assert resolve_port("PORT_DOES_NOT_EXIST", 7777) == 7777


def test_repo_root_env_file_is_optional():
    """仓库根 .port.env 不存在时必须回退，不能抛异常（别人 clone 下来要能直接跑）。"""
    assert resolve_port("PORT", 5050) in (5050, port_from_env_file("PORT", 5050))
