# 交接文档：StockSignal 自主迭代与知识交接 · 2026-07-26（更新）

> 本文件由 WorkBuddy「小帮手」在自主迭代（self-driving-dev）周期中持续维护，用于跨会话 / 跨环境续跑。
> 新会话在 WorkBuddy 说「继续 StockSignal 的自主迭代」即可接手；本文件所在仓库即 `D:\project\ks\StockSignal`。

## 1. 背景与目标
StockSignal 是 A 股事件驱动投资分析平台（Streamlit 前端 8501 + Flask 后端 5050，SQLite + akshare/BaoStock + 多源竞速 fetcher）。
本次会话围绕 **self-driving-dev 自主迭代循环**推进：自己找活干 → 做 → 验证 → 优化 → 找新需求，循环往复。本轮重点治理 **HTML 注入 / XSS 根因**与**页面 / 后端崩溃根因**，并修复了一处会导致全量测试无法收集的历史测试污染。

## 2. 架构与关键约定（⚠️ 新 AI 必读）
- **UI 改造只动 CSS，绝不改功能/布局**（StockSignal 铁律，SOUL.md 一致）。
- **改动后必回归**：用 venv 跑测试，绝不留红的。
  - venv：`C:/Users/24995/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
  - 四道验证门：`py_compile` → `python -m backend.tests.test_security`（12/12）→ `pytest tests/test_backend_imports.py`（74/74）→ 全量 `pytest tests/`
- **禁止破坏性操作**：`rm -rf` / `git reset --hard` / `git push --force` / 删 workspace 外文件一律不做。
- **后端改动必须真重启** Flask（改 backend/ 或 modules/session.py 后按端口杀 PID 再起）。
- **网络**：本环境 akshare 新浪/东方财富部分接口被墙；fetcher 用 4 源竞速 + 本地缓存兜底，勿串行依赖单源。
- **红涨绿跌**：A 股约定（全局 UP 红 / DOWN 绿）；个股对比等少数语义场景另有说明，勿混淆。
- **测试隔离铁律（本次新立）**：pytest 进程内 `sys.modules` 全局共享，**任何测试不得在模块顶层把真实包（如 `modules`）覆盖为 stub，也不得注入残缺的 `streamlit` 桩**。根目录 `conftest.py` 已在收集前把**真实 streamlit** 常驻 `sys.modules`（venv 已装 1.59.2，API 完整）。需要桩页面的测试（如 `test_msg_title.py`）必须在**临时命名空间**内桩入、导入后恢复，**严禁污染全局**。

## 3. 已完成工作（自主迭代 Round 3 + Round 4，截至 cycle 55）

### Round 3 — cycle 21–40（20 轮，已提交本地，HEAD=144e603）
纯逻辑加固与崩溃根因治理，新增/补全白盒测试约 140 项，全量 pytest 达 **1223 passed / 0 failed**。
覆盖：monitor 延迟校验、session 凭证形态、signal 正则转义、worker 状态解析、response 安全序列化、parse_int_param、safe_int/float、backtest 评分守卫、RSI 序列原语、portfolio 安全计算、stock_service/fundamental/compare/alert 校验、progress_bus 线程安全、widgets/page_widgets 转义、safe_timeutil 等。

### Round 4 — cycle 41–55（15 轮，本次交接前已完成本地）
- **Batch A（41–45）XSS 根因治理**：`dark_text_fix._esc`、`button_colors.btn_html`、个股分析视频 URL 仅安全 http(s) 渲染、消息中心标题转义、QuantAgent 投研日志转义（对应测试 5/4/5/5/4 项）。
- **Batch B（46–50）纯逻辑加固 + 输入校验**：`margin_trading` 除零/NaN/None 守卫；`errors.to_response` 复用 `fail()` 统一信封（修复 security 门禁回归）；`admin_api.build_query`；`market_drivers` 温度评分守卫；`ai_engine` 取数失败记 warning + `_build_stock_jobs` 缺键兜底（测试 11/3/4/42/6 项）。
- **Batch C（51–55）后端路由输入校验**：`config_routes._validate_config_value`（bool/None/超长拒绝，杜绝被 `str()` 静默存成 "None"）、`stock_routes._count_by_key`（None/空 key 安全）、`market_routes._is_valid_adjust`（仅放行 qfq/hfq/''/None）、`task_routes._validate_task_payload`（拒非 dict 顶层）、`chat_routes._ensure_json_safe`（序列化前净化防崩溃）。每路由配套纯函数离线测试（共 34 项）。

### 本次重要修复：测试污染导致全量 collection 9 error → 0
- **根因**：`tests/test_msg_title.py` 在模块顶层 `sys.modules["modules"] = 空 stub` 覆盖真实包，并注入**残缺 streamlit 桩**（缺 `cache_data`/`dialog`/`v1`）。pytest 共享 `sys.modules`，批量收集时该文件（字母序 m）先于 `test_widgets_helpers` 等执行，把真实 `modules` 包与 `streamlit` 污染为残缺桩，导致后续 `import modules.session`（含 `@st.cache_data`/`@st.dialog`/`from streamlit import v1`）在收集阶段批量 `ImportError/AttributeError`。该回归随 Batch A 引入，因此前只跑新增测试 + security + imports 而未发现。
- **修复**：
  1. 根目录新增 `conftest.py`：pytest 启动时预加载**真实 streamlit**（venv 1.59.2）常驻 `sys.modules`，任何残缺桩无法覆盖之。
  2. `test_msg_title.py` 改为**临时命名空间隔离导入**页面（`importlib` 在临时 `sys.modules` 中桩入完整 streamlit + 必要子桩，导入后立即 `clear/update` 恢复），做到零全局污染。
- **验证**：全量 `pytest tests/` 已跑至 100% 无 collection error、无 failed（进度条全绿）；安全门禁 12/12、导入门禁 74/74 均通过。

## 4. 验证状态（推送前口径）
| 门禁 | 结果 |
|---|---|
| `py_compile` 全量 | 通过 |
| `python -m backend.tests.test_security` | 12 / 12 通过 |
| `pytest tests/test_backend_imports.py` | 74 / 74 通过 |
| `pytest tests/`（全量） | 通过（0 collection error，0 failed） |
| Round 4 新增测试 | Batch A/B/C 共约 110+ 项，全部通过 |

## 5. Git 与推送状态
- 仓库根：`D:\project\ks\StockSignal`；默认分支 `main`。
- **尚未推送的本地提交**：Round 3（cycle 21–40，20 commit，HEAD=144e603）→ Round 4（cycle 41–55，含 Batch A/B/C 与测试污染修复，共 15 commit）。
- **推送方式**：GitHub 连接器当前 `connected`，直接用系统 git（`D:\Git\cmd\git.exe`）即可 `fetch`/`push`，无需 PAT。推送前先 `fetch` 并对齐远端分叉（若本地领先则 `git rebase origin/main` 再推）。
- **本次动作**：用户要求「更新交接文档，传到 GitHub」——已将交接文档移入仓库内（本文件），连同 Round 4 全部已完成工作一并推送。

## 6. 待办与下一步
- [ ] **Round 4 还有 cycle 56–60 未做**（用户本次仅要求更新交接 + 推送，未要求继续迭代）。可继续：`self-driving-dev` 再跑 5 轮，候选方向见 `state.json` 的 `coverage` 缺口（如 `auth_persist`/`background_tasks`/`fundflow`/`prefs_persist`/`scroll_nav`/`starfield_theme`/`ui_theme`、后端 `services/alert_service`/`task_service`、`tasks/scheduler`、未覆盖页面如 `P_市场情绪.py` 等）。
- [ ] 登录持久化（刷新保持登录）改动后务必验证。
- [ ] 已知历史待修项：暗夜模式 K 线图左上文字重合、个别页面 HTML 泄露（非本轮引入，已通过 XSS 治理大幅收敛）。

## 7. 如何续跑
在 WorkBuddy 对话框说：
「根据 StockSignal 项目，用 self-driving-dev 继续 Round 4 的剩余 5 轮（cycle 56–60），优先补齐 `coverage` 缺口里的纯函数测试与输入校验，每轮本地 commit、维护 `state.json`、跑四道验证门，全部完成后告诉我再推送。」

关键文件：
- 循环状态：`D:\project\ks\StockSignal\.workbuddy\self-driving\state.json`（`cycle`/`max_cycles`/`round`/`completed`/`log`/`coverage`）
- 测试入口：`tests/`（白盒）、`backend/tests/`（安全/契约）
- venv：`C:/Users/24995/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
