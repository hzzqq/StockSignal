---
name: split-large-streamlit-page
description: 安全地把超大类文件（Streamlit 页面 / 大模块）中的纯函数簇抽到独立 helper 模块，做零改动风险拆分。当用户说"文件太大/拆一下/抽公共函数/降低圈复杂度"，或审计发现单文件 >800 行、函数职责混杂时使用。
---

# 超大文件安全拆分（Streamlit 项目）

把巨型文件（如 1200+ 行的 `pages/E_基本面分析.py`）中的**纯函数簇**抽到独立 `modules/xxx_helpers.py`，
页面只保留渲染 + 依赖 `st`/`fetcher`/`session_state` 的 impure 函数。目标：降低单文件圈复杂度、便于单测、消灭重复。

## 核心铁律
1. **只抽纯函数**：不依赖 `st` / `fetcher` / `session_state` / 模块级单例的函数/常量才能抽。
   带 `@st.cache_data` / `@st.cache_resource`、调用 `fetcher.xxx()`、读 `st.session_state` 的函数**必须留在原文件**。
2. **零改动风险**：用 Python 脚本按**精确行号**切割，逐字节复制，**绝不用 Write 工具重写大段内容**
   （Write 对超长 content 会偶发 `Parameter 'content' expected string, but received undefined`，已踩坑）。
3. **行号漂移防护**：脚本里对每个抽取范围的**首行做 `startswith(预期)` 断言**，任何行号偏移立即中止，绝不污染文件。
4. **不要破坏共享模块**：抽出的源若被 Flask 后端复用（如 `modules/fetcher.py`），不要下沉 UI 框架装饰器
   （`@st.cache_data` 会让后端 import 崩溃）。只在其数据层内部统一缓存策略（TTL 集中到 CONFIG）。

## 步骤
1. **定位边界**：`grep -n "^def \|^@st\|^class \|^常量名 =\|^require_auth" 大文件.py` 列出所有函数/装饰器/常量。
2. **判纯/impure**：逐个 `Read` 函数体，确认是否引用 `st.` / `fetcher` / `session_state` / 全局可变状态。
3. **写抽取脚本**（Python，非 Bash heredoc 也行）：
   - 读取原文件 `lines`，定义 1-based 闭区间范围列表 `[(s,e),...]`（升序不重叠）。
   - 对每个范围首行做 `lines[ln-1].startswith(预期头)` 断言。
   - 把每个范围内容 + 块间空行写入 `modules/xxx_helpers.py`，头部加：
     `from __future__ import annotations` + `import pandas as pd` + `import numpy as np`（按需）。
   - 构建新页面：跳过被删行，在第一个删除块前插入 `from modules.xxx_helpers import (...)`（按字母/逻辑排序，含所有被抽符号）。
4. **校验**：
   - `python -m py_compile modules/xxx_helpers.py 大文件.py`
   - `grep "^def 抽走的函数"` 确认页面无残留 def
   - 写一段 import 冒烟（调用几个纯函数验证行为不变）
5. **回归**：跑相关 pytest，必要时跑全量白盒 `pytest tests/`。
6. **提交**：`git add` 新模块 + 改后的页面，commit 说明含「X 行 → Y 行」与抽取清单。

## 反模式
- ❌ 用 Write 工具把 1000+ 行文件整体重写（传输易失败，且易引入无意改动）。
- ❌ 把依赖 `st.rerun` / `fetcher` 的函数抽走，导致页面 import 即崩。
- ❌ 抽取时手动复制粘贴大段代码（行号/缩进极易错）。

## 本项目已落地案例
- `pages/2_个股分析.py` 1571→1015 行 → 抽 `modules/stock_analysis_helpers.py`（16 函数 + 常量）
- `pages/E_基本面分析.py` 1276→791 行 → 抽 `modules/fundamental_helpers.py`（20 函数/常量）
- `modules/fetcher.py` 进程缓存统一 TTL（`_proc_cache_get/_set`，不改 backend 耦合）
