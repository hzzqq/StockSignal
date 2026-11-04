# -*- coding: utf-8 -*-
"""守卫：snownlp 加载失败不得把整页拖垮（回归 2026-11-04《23_事件追踪》白屏）。

背景：snownlp 的分词数据用 `marshal` 序列化，数据文件损坏或与解释器版本不匹配时，
导入抛的是 `ValueError`（bad marshal data）/`EOFError`，**不是 `ImportError`**。
而 `modules/news.py`（及其拆分出的 `_news_io.py`、`_news_nlp.py`）用
`except ImportError` 做可选依赖降级 —— ValueError 直接穿透模块导入，
`23_事件追踪.py`（`signal → news → snownlp`）整页渲染崩溃，页面冒烟因此判红。
情感分析本身有词典法降级路径，第三方包加载失败只该降级，不该白屏。

实现方式：用**子进程**注入一个 `__getattr__` 抛 ValueError 的假 `snownlp`，
再 import 三个模块，断言导入成功且 `_SNOW_OK`/`SnowNLP` 如实降级。
选子进程而不是 `importlib.reload`：reload 会留下新旧模块对象混用的状态，
污染同进程内其他用例；子进程天然隔离，也复现了「页面在自己的进程里首次导入」的真实路径。
"""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_PROBE = r"""
import sys, types, traceback

broken = types.ModuleType("snownlp")


def _boom(name):
    raise ValueError("bad marshal data (unknown type code)")


broken.__getattr__ = _boom
sys.modules["snownlp"] = broken

import modules.news as news            # noqa: F401
import modules._news_io as io_mod     # noqa: F401
import modules._news_nlp as nlp_mod   # noqa: F401

assert news._SNOW_OK is False, "news._SNOW_OK 必须为 False"
assert io_mod._SNOW_OK is False, "_news_io._SNOW_OK 必须为 False"
assert nlp_mod.SnowNLP is None, "_news_nlp.SnowNLP 必须降级为 None"
print("OK")
"""


def test_news_chain_survives_broken_snownlp():
    """snownlp 抛 ValueError 时，news 三个模块必须都能导入并降级。"""
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    detail = f"stdout={proc.stdout}\nstderr={proc.stderr[-2000:]}"
    assert proc.returncode == 0, f"注入 snownlp ValueError 后导入链不应崩：\n{detail}"
    assert "OK" in proc.stdout, detail


def test_snownlp_flag_is_boolean_in_real_env():
    """真实环境里 `_SNOW_OK` 必须是明确的 True/False（不能是 None 或异常对象）。"""
    import modules._news_io as io_mod

    assert io_mod._SNOW_OK in (True, False)
