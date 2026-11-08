# -*- coding: utf-8 -*-
"""pytest 全局配置（tests/ 目录）。

2026-11-08 宏观入库改造引入的测试隔离约定：
`modules/macro_data.fetch_indicator` 改为**库优先**（TTL 内直接读
`macro_history`，零网络往返）。既有单测用 monkeypatch 替换 akshare 假源，
若库优先生效会读到**真实库**里的值而非假源值 → 断言失真
（实测 20 个既有宏观用例因此变红）。

故在 tests/ 目录级别默认关闭宏观库（``MACRO_STORE_ENABLED=0``）：
既有测试继续验证"取数与解析"逻辑，不受入库改造影响；
需要验证入库行为的用例（如 ``tests/test_macro_store.py``）在自己的
fixture 里**显式打开**开关并用 ``MACRO_DB_PATH`` 指向临时库。

这与「测试不依赖真实数据」的既有纪律一致：单测只测自己声明的契约。
"""
import os

os.environ.setdefault("MACRO_STORE_ENABLED", "0")
