# 回归归因报告（T-247 相关 vs 环境 / 既有失败）

> 生成日期：2026-11-04 · 代码基线：`7883923`（`main`，与 `origin/main` 一致）
> 适用范围：**本轮可复现的定向回归**，不是全量 457 个测试文件的结论。
> 诚实红线：历史两份全量回归日志已不可得，**不反推、不编造其数字与失败用例名**；缺失项在下文显式标注为「不可得」。

## 1. 结论先行

| 项 | 结论 |
|---|---|
| 本轮可复现回归 | **510 passed / 0 failed / 0 error**（4 组有效日志，见 §2） |
| T-247 引入的回归 | **已修复**：`test_search_ui` 的 `NameError`、`fetcher_core_tier11` 的影子名薄壳守卫，本轮对应守卫族全绿（§3） |
| 环境 / 既有失败 | 本轮 **0 例**；历史两份日志里的既有失败清单 **不可得**（§4） |
| 报告边界 | 🟡 未跑全量 457 文件；🟡 历史日志缺失。二者均列为 §6 后续项，不在本报告里假装覆盖 |

**大白话**：能真跑的都跑了、全绿；T-247 当年那两个真 bug 现在确实没了；但当年那两份日志找不到了，所以我只报告「现在」，不假装知道「当时」。

## 2. 数据源与真实计数

数据源 = workspace 根下本轮生成的原始 pytest 输出（均为 `-o addopts= -q` 覆盖仓库默认 `-q` 后带明确汇总行的版本），独立库 `DATABASE_URL=sqlite:///E:/tmp/ss_probe/app.db`。

| # | 日志 | 覆盖 | passed | failed | error | 汇总行 |
|---|---|---|---|---|---|---|
| 1 | `_h_regression_out2.txt` | 事件因子全族 15 文件 | 110 | 0 | 0 | `110 passed in 109.00s` |
| 2 | `_pending_probe_out.txt` | 停更检测 / 拆分回归 / T-367 UI 守卫 33 文件 | 259 | 0 | 0 | `259 passed in 61.69s` |
| 3 | `_probe2_out.txt` | 导航子簇 / 决策新鲜度 / 决策环报警 3 文件 | 63 | 0 | 0 | `63 passed in 10.53s` |
| 4 | `_h_smoke_b0.txt` / `_h_smoke_b1.txt` / `_h_smoke_b2.txt` | 页面冒烟 `SMOKE_BATCH=0/3,1/3,2/3`，覆盖 `ALL_PAGE_FILES=75`（25/25/25，`UNIQUE=75` 无遗漏） | 26 + 26 + 26 = **78** | 0 | 0 | 三份各自 `26 passed` |
| — | **合计** | — | **510** | **0** | **0** | — |

**被排除的不完整日志（不计入统计，如实记录）**：

| 文件 | 现象 | 处置 |
|---|---|---|
| `_h_smoke_out.txt` | 整批后台冒烟停在 67 个点，**无汇总行、无 `SMOKE_EXIT`** | 进程被中断，判定「未正常结束」，不计通过，改用 §2 第 4 项分批重跑 |
| `_final_regression.txt` | 164 个点但无汇总行（早期双重 `-q` 吞掉 summary） | 不据此声明用例数 |
| `_pytest_base.txt` | P0-3 改动前基线，7 例 `exit: 0` | 属历史基线，不计入本轮合计 |

> 复现要点：仓库 `pyproject.toml` 默认 `addopts=["-q"]`，命令行再传 `-q` 会形成双重 `-q` 并吞掉 pytest 汇总行。所有统计均使用 `-o addopts= -q`。

## 3. T-247 引入的回归：归因与当前状态

| 历史失败 | 用例 | 根因（任务台账记载） | 当前代码真源 | 本轮验证 |
|---|---|---|---|---|
| ① `NameError` | `test_search_ui` 3 例 | 拆分脚本 `STOCK_REPL` 把无 `self` 的类方法（`_pinyin_*`）的 `StockFetcher._X` 改写成 `self._X` | `modules/fetcher_search.py`：类方法内 `self._pinyin_*`；模块级走 `import modules.fetcher as _fetcher_mod` | §2 第 2 项含 `test_search_ui.py`，全绿 |
| ② AST 守卫红 | `fetcher_core_tier11` 2 例 | 影子名薄壳 `_get_stock_industry_keywords` / `synth_us_index_intraday` 被搬出 `fetcher.py` | 薄壳保留在 `fetcher.py`；`tests/test_fetcher_core_tier11.py` 与 `test_fetcher_core_no_circular_import.py` 均在本轮 259 例族中 | 全绿 |

**结论**：T-247 的两类真实回归（不是环境问题）已由历史批次修复，本轮以守卫族真跑复核，无残留。

## 4. 环境 / 网络 / 既有失败：诚实归因

- **本轮实测：0 例**。所有 510 例都在离线打桩（`SMOKE_BATCH` 页面冒烟本身 monkeypatch `requests`/`urllib` 立即抛 `ConnectionError`）或本地临时库下完成，不依赖行情源可用性。
- **已知环境噪声（不是测试失败，勿计入）**：
  1. 沙箱 `tmp_path` 清理在 `atexit` 触发 `rmtree`，日志尾部会带 `SystemExit` 回溯噪声；判定标准是 `pytest exit: 0` / 汇总行，不是尾部字符串。
  2. 整批页面冒烟撞「单条命令 10 分钟墙」被中断，必须走 `SMOKE_BATCH=i/n` 拆前台短任务。
  3. 双重 `-q` 吞汇总行，导致「看起来只有点、没有结论」。
- **历史既有失败清单：不可得**。任务台账 #32/#33 记载曾排查并修复「13 个既有失败（7 集群）」，但对应的两份原始全量回归日志在 `E:/project/ks/*.txt` / `*.log` 全盘检索中均未命中（仅命中本轮新生成的 6 个输出文件）。**因此本报告不列历史失败用例名，也不猜测其 passed/failed/error 数字**。

## 5. 风险分级

| 级别 | 项 | 影响 | 处置 |
|---|---|---|---|
| 🟡 中 | 历史两份日志缺失 | 无法给出「当时」的失败用例名与三类归因明细 | 已在 §1/§4 显式标注；若找回日志，补附录即可，不影响现有结论 |
| 🟡 中 | 全量 457 文件未跑 | 报告是定向抽样，不能当「全站绿」对外宣称 | §6 给出分批全量命令；对外文案不得引用本报告当全量结论 |
| 🟢 低 | 本轮 510 例零失败 | 仅代表所覆盖族 | 可复现、有原始日志路径 |

## 6. 下一步（可复现命令）

1. **补全量归因**：把 `tests/test_*.py`（457 个文件）按文件名排序切成 4–6 批，每批单独前台执行并落盘日志，避免单条命令撞 10 分钟墙：
   ```bash
   python -m pytest -o addopts= -q --tb=line <该批文件列表>
   ```
   环境变量固定 `DATABASE_URL=sqlite:///E:/tmp/ss_probe/app.db`，避免与主工作区后端争锁。
2. **门禁建议**：把「`-o addopts=` 拿汇总行 + 分批 + 日志落盘」写进回归脚本，杜绝「只有点没有结论」的伪通过。
3. **若找回历史两份日志**：在本文追加「历史归因附录」，按 §3/§4 的同一张表补数字与用例名，不改动本轮结论。

## 7. 附：本轮复现入口

| 组 | 包装脚本 | 原始日志 |
|---|---|---|
| 事件因子全族 | `_run_h_regression.py` | `_h_regression_out2.txt` |
| 三方向挂起项 | `_run_pending_probe.py` | `_pending_probe_out.txt` |
| 补测 | `_run_probe2.py` | `_probe2_out.txt` |
| 页面冒烟分批 | `_run_h_smoke_batch.py` | `_h_smoke_b{0,1,2}.txt` |

> 上述脚本与日志位于 workspace 根 `E:/project/ks/`，**不在仓库内、未提交**；本报告只引用其真实输出，不依赖它们长期存在。
