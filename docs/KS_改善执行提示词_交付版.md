# StockSignal (ks) 架构改善执行提示词・交付版

> 用途：把本提示词整体复制给任一具备代码编辑与本地执行能力的 AI 工作台（Trae / 豆包 / Cursor / CodeBuddy / Qoder 等），由它按下面清单在 StockSignal 仓库内实施改善。
> 版本：v1（2026-10-29）・依据：2026-10-28 对仓库的架构审计（git 历史 + AST 统计 + 守卫实测）。



***

## 一、角色与总目标

你是一名资深全栈工程师，接手一个 **A 股事件驱动投资分析平台**（代码库名 StockSignal，目录 `E:\project\ks\StockSignal`，用户常称 ks）。技术栈：**Streamlit 前端（72 页）+ Flask 后端（5050 端口，约 80 路由）+ FastAPI 试点切片（5052）+ 自研 MCP gateway + SQLite + akshare/baostock/tushare 数据层**，依赖由 uv 管理（`uv.lock`）。

总目标：在不破坏现有功能、不违反红线的前提下，按优先级消除以下 7 类结构性问题，并让每一步都可验证、可回滚、可审计。逐项完成后输出「改动文件清单 + 验证结果 + 未完成项及原因」。

## 二、红线（任何情况下不得违反）



1. **A 股涨跌语义色不可反转**：涨 `#ff4d4f`（红）/ 跌 `#00d486`（绿），由 `modules/ui_kit.py` 的 `--ss-up/--ss-down` 管理；`tests/test_ui_design_system.py::test_st_metric_with_delta_must_set_delta_color` 必须保持绿色。

2. **品牌身份色不动**：`--acc1:#4f46e5 / --acc2:#7c3aed`（`modules/colors.py`、`modules/ui_theme.py` 的 `:root`）保持冻结，不换色。

3. **现有守卫不得回退**：`tests/test_ui_design_system.py`（5 项）、`tests/test_pages_smoke.py`、`tests/test_config_theme_types.py`、`tests/test_ui_kit_hero.py` 必须全绿；新增代码不得删除或弱化既有断言。

4. **诚实语义**：不编造数据、不伪造测试通过；接口取不到数据如实返回，禁止用 mock 结果冒充真实运行结果。

5. **依赖收敛**：除迁移 streamlit-autorefresh 的替换外，不新增重型第三方依赖；确需新增必须说明理由并写入 `pyproject.toml`。

6. **不破坏生产服务**：不 force 推送、不杀端口占用进程；git 提交采用小步提交，每个任务一个 commit，允许 push 前先 `git fetch origin main` 校验。

## 三、任务清单（按优先级）

### P0-1 消除 exec 动态加载页面（高危反模式）



* **背景**：`pages/24_个股研究.py` 第 38 行把 `pages/20_个股分析.py` 映射为子视图，第 72 行用 `exec(compile(src, path, "exec"), g)` 动态执行整个页面源码。该模式使 20 页在 24 页内被字符串执行：不可静态分析、难测试、异常栈混乱。

* **做法**：

1. 将 20 页的渲染主体抽成可调用函数（例如 `modules/stock_research.py` 内 `render_stock_analysis(stock_code)`），保留其原有参数与副作用语义；

2. 24 页改为 `import` 后直接调用该函数，删除 `exec(compile(...))`；

3. 20 页自身保留入口逻辑（作为独立页面仍可单独运行），与 24 页共享同一函数，避免双份实现漂移；

4. 行为必须完全一致：相同输入下渲染内容与数据抓取次数不变。

* **验收**：`24_个股研究.py` 中不再出现 `exec(` 与 `compile(`；`20_个股分析.py` 仍可独立运行；`pytest tests/test_pages_smoke.py -q` 通过。

### P0-2 streamlit-autorefresh 迁移到原生 st.fragment (run\_every=...)



* **背景**：`pages/10_行情看板.py`、`pages/11_股票选取.py`、`pages/12_板块轮动.py` 通过 `modules/autorefresh.py` 的 `st_autorefresh(...)`（包装第三方 `streamlit-autorefresh`，该组件已停止维护）实现定时刷新；而项目部分模块已用 Streamlit 原生 `st.fragment(run_every=...)`（见 `.streamlit/config.toml` 注释），属新旧并存。

* **做法**：

1. 把上述三页的自动刷新区域改为 `@st.fragment(run_every=<原间隔秒>)` 包裹的独立渲染函数，保证刷新只重算该区域而非整页；

2. 保留原刷新间隔与 `key` 语义；页面加载时首帧立即渲染（fragment 首次仍会执行）；

3. 迁移完成后从 `pyproject.toml`/`requirements.txt` 移除 `streamlit-autorefresh` 依赖，删除或清空 `modules/autorefresh.py` 中不再被引用的封装（保留无引用则删除）。

* **验收**：全仓库 grep 不再出现 `streamlit_autorefresh`；三页刷新行为等价（观察 10 页板块区在 `run_every` 间隔内自动更新）；依赖清单已移除；`pytest tests/ -q` 相关冒烟通过。

### P0-3 统一主题两层默认值（历史遗留不一致）



* **背景**：`.streamlit/config.toml` 原生层 `base = "dark"`（深空黑 `#0f0f23`），而 `modules/ui_theme.py` 的 `theme_mode` 默认 `'light'`（第 78/98/189 行 `get('theme_mode', 'light')`）—— 两层默认互相矛盾；且暗色皮肤存在两套强调色：`_DARK_CSS` 用极光 `#667eea/#764ba2`，`dashboard_sf_css` 的 `:root` 用靛紫 `#4f46e5/#7c3aed`。

* **做法**：以「默认暗色、品牌靛紫统一」为终点（与 config.toml 及 `dashboard_sf_css` 一致，最小改动面）：

1. `theme_mode` 默认值统一为 `'dark'`（`ui_theme.py` 三处 `'light'` 默认同步核对）；

2. `_DARK_CSS` 的 `--acc1/--acc2` 由 `#667eea/#764ba2` 改为品牌令牌 `#4f46e5/#7c3aed`（或改为引用 `var(--acc1)` 单一来源），消除两套暗色强调并存；

3. 保留用户手动切换浅色的能力（`style_switcher` 与主题预设不动）；

4. 浅色退回验证：切换浅色后全站无破版、无 A 股色反转。

* **验收**：`ui_theme.py` 中 `get('theme_mode', 'light')` 不再存在（默认暗）；`_DARK_CSS` 不再硬编码极光色；`tests/test_ui_design_system.py` 与 `tests/test_config_theme_types.py` 全绿；手动浅色切换正常。

### P0-4 UI 审计基线脚本落地（量化口径可复现）



* **背景**：`docs/UI_REFERENCE_ANALYSIS.md` 声称「71% 裸 HTML、10% 旧 sf\_\*、68% 散装 st.metric」，但仓库无审计脚本 / 报告，且实测（AST 级，72 页）为：含 `unsafe_allow_html=True` 62%（45 页）、含旧 `sf_*` 引用 69%（50 页）、含 `st.metric` 24%（17 页）、完全不引 `ui_kit` 的纯旧页 11%（8 页）。口径未固定则验收无基准。

* **做法**：新建 `scripts/ui_audit.py`（AST 级，不要用字符串 grep 误伤注释）：

1. 统计维度：a) 含 `unsafe_allow_html=True` 的页数 / 调用数；b) 引用 `sf_card/sf_metric/sf_table/sf_pill/sf_stat/sf_one_line/sf_alert/sf_tag` 等旧组件的页数 / 调用数；c) 调用 `st.metric` 的页数 / 调用数；d) 完全不 import `modules.ui_kit` 的页数；e) 使用 `xc_kpi_grid/chart_card/table_wrap/page_hero/xc_section_header` 的页数；

2. 输出 `docs/ui_audit_baseline.json`（含口径说明、统计日期、各维度页级与调用级数字）+ 控制台表格；

3. 脚本幂等、可在任意时刻重跑。

* **验收**：`python scripts/ui_audit.py` 能产出与上述实测同口径的数字，`docs/ui_audit_baseline.json` 提交入库；后续 UI 改造以该 baseline 为前后对照。

### P1-1 修正 UI 文档引用错误（避免实现期漏页）



* **背景**：`docs/UI_REFERENCE_ANALYSIS.md` 存在 4 处与代码不符的引用。

* **做法**：核对后修正：

1. 第四 / 六节 `76_强势榜.py` → 实际文件 `pages/76_实时强势榜.py`；

2. `59_温度计.py` → 实际文件 `pages/59_市场温度计.py`；

3. 第七节「更新 UI\_REDESIGN\_REQUIREMENTS.md 第 57 行风格决策」→ 第 57 行是 `10_行情看板` 表格行，风格决策实际在第 10 节（约 145-149 行），改为指向正确位置；

4. 第四节 `57_市场全景.py` 的「散装 st.metric」→ 该页实际用 `sf_metric`（已委托 `ui_kit._xc_card_html`，视觉已收敛 canonical），改为准确描述；

5. 附注：文档与 `UI_REDESIGN_REQUIREMENTS.md` 的「深色切琥珀橙」方向存在取舍关系，在文档第六节明确「本方案保留靛紫、否决琥珀橙」的决策记录。

* **验收**：修正后文档中所有 `pages/*.py` 文件名均可与 `pages/` 目录一一对应（脚本核对无遗漏）；git diff 干净可审。

### P1-2 双后端过渡态明确终点



* **背景**：Flask（`backend/app.py`，5050）与 FastAPI 试点（`backend_fastapi/main.py`，5052）并存；`backend_fastapi` 已示范「新端点增量 FastAPI + 只读共享 SQLite」。

* **做法**（推荐方案，写入 `docs/` 决策记录）：

1. 明确策略：「存量 Flask 路由维持生产不动；一切新端点走 `backend_fastapi`」；

2. 在 `backend_fastapi/main.py` 或独立 `docs/backend_strategy.md` 记录该决策与迁移触发条件（例如：当某功能需要重写或新增 >3 个端点时优先在 FastAPI 实现）；

3. 不强制全量迁移，不做无收益重写。

* **验收**：`docs/backend_strategy.md` 存在并记录决策；两服务仍可同时启动（5050/5052）；`pytest tests/ -q` 全绿。

### P1-3 测试 skip 率治理（消除黑盒虚高）



* **背景**：`conftest.py` 会在会话结束打印全量 skip 率，>30% 时报警；当前页面级测试存在大量黑盒 skip。

* **做法**：抽查 `tests/test_pages_smoke.py` 与最大 skip 源，把「因缺数据 / 网络而 skip」的用例改为：有本地 fixture 数据时断言渲染关键节点存在；确需真网的保留 `@pytest.mark.live`（默认不收集，`OFFLINE_TEST=0` 显式开启，机制已存在）；目标是全量 skip 率显著下降（目标 <30%）。

* **验收**：运行 `pytest tests/ -q` 后 conftest 打印的 skip 率低于 30%，且无测试被静默删除。

## 四、实施纪律



1. **小步提交**：每个 P 级任务一个 commit，commit message 带编号（如 `refactor: P0-1 消除 exec 动态加载`）；禁止把无关改动混入同一 commit。

2. **每步验证**：每个任务完成后立即跑 `python -m pytest tests/test_ui_design_system.py tests/test_pages_smoke.py tests/test_config_theme_types.py -q`；P0 任务额外跑受影响页面的冒烟。

3. **改动前先读**：任何文件修改前先完整读该文件，理解上下文再改；不确定的语义（如 refresh 间隔、主题默认值）以代码现状为准并记录。

4. **诚实汇报**：无法完成的任务如实说明原因与影响，不标记为完成；全部完成后输出：改动文件清单（含行数统计）、每项验收结果、剩余风险、下一步建议。

5. **禁止**：不要以「教程 / 建议」代替实际代码改动；不要删除守卫测试；不要为了通过测试而放松断言。

## 五、完工验收清单（交付前逐项自检）



* [ ] `grep -rn "exec(compile" pages/` 无结果；24 页可正常进入两个子视图

* [ ] `grep -rn "streamlit_autorefresh\|st_autorefresh" .` 无结果（除清理残留说明）

* [ ] `ui_theme.py` 无 `get('theme_mode', 'light')`；`_DARK_CSS` 无 `#667eea/#764ba2` 硬编码

* [ ] `python scripts/ui_audit.py` 可运行并产出 `docs/ui_audit_baseline.json`

* [ ] `docs/UI_REFERENCE_ANALYSIS.md` 中 `pages/*.py` 文件名全部真实存在

* [ ] `docs/backend_strategy.md` 已提交决策

* [ ] `pytest tests/ -q` 全绿（含设计系统守卫 5/5），skip 率 <30%

* [ ] 全部改动已小步提交，未 force push

> 完成后请把本清单逐项勾选结果与改动摘要回复给用户。