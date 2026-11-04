# 递延 UI 项下一轮规划（#35 收口）

> 生成：2026-11-04 · 本地基线 `3081776` · 远端 `0703387`
> 产出方式：UI 设计全栈专家团三阶段串行交付（视觉 → 体验 → 前端工程），主理人汇编与裁定
> **状态：已随 `85e1168` FF 推送（2026-11-04）；§8 的同步阻塞由并发方 `32dd1c3` / `1ceaabc` 自行解除**。
> ⚠️ **M1 开工前实证勘误见 §10（v3）：§1 的「20 页 docstring 改红涨绿跌」是误判，已撤回；执行以 §10 为准。**
> 诚实边界：本轮**零改码**，三阶段成员均零文件改动；本文是「下一轮」执行方案，不是已实施结论。三阶段完整论证原文见 2026-11-04 会话交付，本文为汇编精简版。

## 0. 结论先行

| 项 | 结论 |
|---|---|
| #35 真实性质 | 「下一轮规划 + Trae 协调闸」，**不是本轮改页面**；任务台账带 `cancelled=true` 且 status 滞后 |
| 台账描述 | **已过时**，4 条实证勘误见 §1；照原描述执行会做无用功并踩守卫 |
| 优先级 | P0 报告卡（高）→ P1 `sf-*` 收敛（高，与 P0 同批次）→ P2 导航（中，后置）→ P3 登录页（低，搭车） |
| 执行序 | A 语义不变量 → B 报告卡 → C `sf-*` 收敛 → D 深链 → E 断言；**P0+P1 单一原子 commit** |
| 最大风险 | 语义反转被当「配色小问题」漏改；现有守卫只锁色值层，改完色值测试仍绿但「🟢 强势」依旧反 |
| 本轮交付 | 本文 + Trae 协调闸（§6，含当日真实触发案例）；**未推送** |

**大白话**：4 个递延项里 2 个描述是错的（`20 页已注销`、`al-* 待迁移`），另 2 个其实是同一个文件；真正该先修的是 A 股涨跌语义写反了，这是会误导下单的正确性缺陷，不是美化。

## 1. 实证勘误（主理人逐条真扫核验）

| 台账 #35 描述 | 真实情况 | 影响 |
|---|---|---|
| 「20_个股分析 sf-* 迁移」 | `pages/20_个股分析.py` 是 12 行 shim；`pages/24_个股研究.py:39` 仍引用；`tests/test_sidebar_nav.py:139-140` **反向强制**两字符串必须存在；唯一真违规是 `pages/22_基本面分析.py:870` 的 `st.page_link` | 不能清字符串、不能恢复独立页；只能改 CSS 与 22 页出边 |
| 「11 Block2-3 报告卡」 | `pages/11_股票选取.py` 是 shim；报告卡 HTML 全在 `modules/stock_research.py` 185–799（30+ `sf-*` 片段） | 项 1 与项 2 **落点同一文件**，必须合批 |
| 「登录页 al-* → PandaAI 黑白」 | `al-*` 已全仓清零；现用 `lg-*` 27 个 class（`tests/test_bento_standards.py:122-128` 白名单）；待办实为「去紫渐变 + 中性化」 | 按字面迁移会找不到对象 |
| 「导航重构」 | `widgets.py::_NAV_GROUPS` 锁 6 类目/顺序/emoji 唯一/子簇≤8；主导航其实是**顶栏 mega**（`widgets.py:1057-1063` 的 `render_sidebar_nav` 已退役），窄屏无折叠 | 改造空间只在渲染层，不能动数据层 |

**主理人补充核验（成员未覆盖，改变改动面）**：

- `tests/test_no_st_metric_in_pages.py` 的 G6 终态封禁**只扫 `pages/*.py`**（第 27/38 行），文件头第 18 行明确 `modules/` 下被 shim 委托的实现体不在封禁范围。
- `tests/test_metric_delta_color.py:20-23` 的 `_RELOCATED` 把 `20_个股分析.py → stock_research.py::render_stock_analysis`、`11_股票选取.py → render_stock_picker` 列为守卫清单；第 41/47 行 `COMPLETED_FILES` 仍锁这两页。
- `modules/stock_research.py` 的 `st.metric` 实际 **8 处**：2084/2094 `delta_color="inverse"`（A 股正值红，正确）；1295/1297/1299/1301/1305/1307 `delta_color="off"`（每股收益 / 营业总收入 / 净利润 / ROE% / 毛利率 / 净利率）。成员规划只报了 2 处。

⇒ **裁定（Phase 3 工程师 v2，主理人采纳）**：**4a 全迁** —— 8 处 `st.metric` 全部迁到 `xc_kpi_grid`，同步升级 `tests/test_metric_delta_color.py` 的 `_RELOCATED` / `COMPLETED_FILES`（混合态分支），该守卫文件留在单一原子 commit 的显式 add 清单；`tests/test_no_st_metric_in_pages.py`（G6）**零改动、不扩权、不缩权**，从 staged 清单移出但仍进 pytest 回归清单。
- 理由：Phase 1/2 已把「KPI 用 `xc_kpi_grid` + 显式 `delta_dir`」定为**设计终态**；G6 与 `_RELOCATED` 描述的只是「本批次前的合法现状快照」，不是终态豁免。把守卫边界读成设计许可会让实现体被旧守卫冻结。8 处同文件同批次正好消除「只迁 2 处、6 处 `off` 未迁」的半迁移中间态。
- **不扩权 G6 到 `modules/` 是正确性必需**：否则会连带把 `40_仓位管理.py` 委托的 `portfolio_views` 实现体（本批次零改动、仍合法用 `st.metric`）误判为违规。
- `delta_dir` 映射（8 处全部**显式传**，禁默认 flat）：2084/2094 `inverse` → `up`(delta>0) / `down`(delta<0) / `flat`(=0 或 None)；1295/1297/1299/1301/1305/1307 `off` → `flat`。`flat` 分支渲染「— + 中性文字 + 零 `--ss-up/down` + delta 固定右侧」，**6 个财务指标不得被染红/染绿**（否则制造新的语义污染）。
- `_RELOCATED` 三条按混合态分支处理：11/20 两条谓词切到 `xc_kpi_grid(delta_dir=...)`；`40_仓位管理.py → portfolio_views` 分支**保持 `st.metric` 断言原样**。`COMPLETED_FILES` 的 11/20 条目**保留不删**（删条目 = 弱化守卫），仅更新完成态语义。不同步时该守卫会红 —— 这是「守卫与实现体脱节」的可观测信号，**禁止用 skip/xfail/删条目让它变绿**。
- 措辞纪律：`pages/` 零 `st.metric` 是 **G6 红线**；`modules/stock_research.py` 零 `st.metric` 只能表述为「8 处迁移完成度结果」，不得包装成红线豁免。
- v2 补充范围：`20_个股分析.py:5-6` docstring 里的 `#009e60/#dc2626` 一并清零（不只改「绿涨红跌」措辞）；`90_登录.py:152` 的 ▲/▼ 与「涨/跌」文字是黑白化显式例外，DOM 保留不动。

其余已核验属实：`stock_research.py:2054/2057/2060/2072/2101/2113/2117` 七处 🟢/🔴 反转；`24_个股研究.py:93-105` 只有 setdefault + radio key（深链契约未实现）；`20_个股分析.py:5-6` docstring 仍写「绿涨红跌 #009e60/#dc2626」；`90_登录.py:207-208` 的 `#ee2a2a/#00b96b` 漂移、152 行 ▲/▼ 与「涨/跌」文字同在（黑白化显式例外成立）。

## 2. 视觉基座（Phase 1 成员结论摘要）

- 令牌单一来源 `--ss-*` / `ui_kit._KIT_CSS`；chip 全 inline、零新增 `.ss-pill`；页面层零语义 hex；字重仅 400/500/600/700；卡片 16px 圆角 / 12px gap / 16px 内边距；结论句 22px/700 ≤2 行；单卡 ≤3 级字号；hover 仅明度 1 级，禁渐变/双阴影/位移。
- 涨红跌绿走 `--ss-up:#ff4d4f` / `--ss-down:#00d486`；`--ss-box-success/info/warn/danger` 与之**语义正交**，`.xc-*-box` 规则内禁出现 `var(--ss-up|down)`。
- 需补的增量令牌：`--ss-surface-2/3`、`--ss-text-tertiary`、`--ss-line-strong`、`--ss-up-soft/down-soft`、`--ss-login-*`（全部写入 `_KIT_CSS` 单点，不新建平行命名空间）。
- 导航不换 emoji 图标集、不改 6 类目与顺序；active = 左 3px accent 竖条 + `--ss-surface-3` + `--txt`（不用涨跌色）。
- 交付 28 条视觉验收项（含「`grep -n "20_个股分析.py" pages/24_个股研究.py` ≥1」这类**反向验收**）。

## 3. 体验规范（Phase 2 成员结论摘要）

- **深链契约是 P0 前置项**：22 页点「去深度分析」不能只改 label —— 24 页注释承诺预选子视图但代码未消费 `hub_gyj_view`，会落到默认「⚡ 快速选取」且 code 丢失。须定义跳转方写 `hub_gyj_view` + `pick_stock` + `safe_switch_page("pages/24_个股研究.py")`，消费方预置分段、回填 code，并补「← 返回基本面分析（code）」可见控件。
- **语义四通道冗余**：文字（方向词前置）+ 形状（▲=涨/多=红、▼=跌/空=绿、—=中性，替换同形圆点）+ 颜色 + 位置；去色后仍可读。红绿色觉缺陷约 8% 男性，🟢/🔴 同形圆点会退化成逐字阅读。
- **两套响应式并存**：`xc_kpi_grid` 容器 auto-fit（`ui_kit.py:921`）vs `sf-grid-4` 视口断点 900/540（`ui_theme.py:419-421`）⇒ 同页窄屏错位，这是 P0+P1 必须合批的体验侧理由。
- 对比度不是「暗/浅两套」：`:root` 基线 + `ui_theme.py:599/695/774/856/954` **5 套风格** × 暗/浅 = 12 组矩阵；正文 ≥4.5:1、22px/700 ≥3:1、登录主文 ≥7:1、非文本 ≥3:1。
- 焦点环统一 `--ss-focus-ring`（现状散落三套且 `ui_theme.py:1104` 的 `input:focus` 无 outline）；`90_登录.py` 8+ 处裸 `st.error` 需换 `xc_error_box`；**▲涨/▼跌 与「涨/跌」文字是黑白化显式例外，永不删除**。
- 执行序 A→E、单一原子 commit、P3 晚于 A 令牌锁定、P2 独占守卫改动；交付 27 条体验验收项。

## 4. 工程落地（Phase 3 成员结论摘要）

**四态口径裁定（主理人）**：按**双义同时覆盖** —— 语义四态（方向词归一到 ▲/▼/— 三形）与交互四态（default/hover/focus/disabled），避免下一轮只取其一。

| 阶段 | 主要落点 | 关键动作 |
|---|---|---|
| A | `ui_kit.py` / `ui_theme.py` / `stock_research.py` / `20_个股分析.py` | 锁定语义不变量、令牌、焦点环、auto-fit 单一响应式；修 7 处反转；20 页 docstring 改「红涨绿跌」 |
| B | `stock_research.py` 185–799 / `90_登录.py` | 11 张报告卡结论句置顶、四通道、四态、错误三重编码 |
| C | `stock_research.py` / `ui_kit.py` / `ui_theme.py` / `tests/test_metric_delta_color.py` | `sf-*`→`xc-*`/令牌；`sf-grid-4` 断点退役；**8 处 `st.metric` 全迁 `xc_kpi_grid`**（显式 `delta_dir`，见 §1）；同步升级该守卫的混合态分支；G6 零改动、移出 staged |
| D | `22_基本面分析.py:870` / `24_个股研究.py:93-105` | 深链契约；**24 页 `_SUBPAGES` 路径字符串零改动**；在 22 页注释登记「尚有同类直连未清理」 |
| E | `tests/*` | 断言落测试；新建 `tests/test_deep_link_contract.py`（深链断言不塞进 `test_sidebar_nav.py`） |

**本批次零改动清单**：`tests/test_sidebar_nav.py`、`tests/test_no_st_metric_in_pages.py`（G6）、`modules/widgets.py::_NAV_GROUPS`、`modules/top_nav.py`、`modules/portfolio_views.py`（`40_仓位管理.py` 委托体，仍合法用 `st.metric`）、`pages/11_股票选取.py`、`10_行情看板.py`、`51_每日晨报.py`、`modules/scroll_nav.py`、24 页 `_SUBPAGES` 字符串、20 页 shim 结构、`al-*` 清零状态。显式 add 清单由 15 收敛为 **14 个文件**（移出 G6、并入 `test_metric_delta_color.py` 后按 v2 口径）。

**验证矩阵**：统一 `python -m pytest -o addopts= -q`（仓库默认 `-q` 会形成双重 `-q` 吞汇总行，无汇总行不得判通过）；独立库 `DATABASE_URL=sqlite:///E:/tmp/ss_probe/app.db`；页面冒烟 `SMOKE_BATCH=i/n` 分批。9 个守卫文件 + V-A~V-D `git grep` 断言 + 12 组对比度/截图人工项。成员 v2 交付 **28 条工程验收项**与 5 档里程碑表（M0 规划 / M1 原子批次（唯一可独立上线）/ M1' 登录搭车 / M2 导航后置 / M3 降级补做）。

## 5. 主理人范围裁定

- **其余 shim 直连归 P2 后置清点，不纳入 P0+P1 原子合批**：`10_行情看板.py:311/343/601/609 → 11 页`、`51_每日晨报.py:184 → 46 页`、`scroll_nav.py:411 → /个股分析?pick_stock=`。理由：原子批次已含 30+ `sf-*`、7 处反转、深链契约，摊到多文件会放大回归面。但 D 阶段改 22:870 时**必须显式登记**这三处，防止把「`test_sidebar_nav.py` 通过」误判为「入口已全部收敛」（该守卫只覆盖导航登记）。
- **P2 折叠判定**：子簇满 8 项时，高频同任务页走「新建子簇」（子簇数量无上限），低频诊断页走渲染层「更多」折叠；**绝不能往 `_NAV_GROUPS` 追加第 9 项**，折叠项仍须留在 `_iter_nav_items()` / 搜索索引中。
- **P0 语义修正必须先于视觉收敛**：先换色值/组件会把「🟢 强势」原样固化进新组件，之后要动两遍。语义是数据，配色是表现。

## 6. Trae 多机协调闸（#35 的另一半，可直接写进项目约定）

统一三段式 **命令 → 判定 → 处置**，始终 FF-only。

**G0 编辑前**：`git fetch origin main`（只刷 FETCH_HEAD，不 pull/merge/checkout/stash/reset）→ 记录 FETCH_HEAD SHA 与 `status --porcelain` 基线 → 用 `git log -n 50 --format='%an <%ae>' | sort -u` 建立作者基线识别 Trae。出现成批 ` M` 即判定「Trae 正在工作树中」。

**G1 逐文件痕迹判定**：对 §4 每个待改文件跑
`git log -n 5 -- <file>` / `git log --author=<Trae> -- <file>` / `git diff -- <file>` / `git diff --cached -- <file>`。
- 仅成批独立 `# noqa: I001` 噪声 ⇒ **不删工作树**，用显式 `git add -- <仅本次文件>` + index 级剥离（`git show :path` → 去 I001 → `git hash-object -w` → `git update-index --cacheinfo`），达成 staged 零夹带、工作树完整保留。
- 实质改动与目标行段重叠 ⇒ **先沟通、暂停该文件编辑**，不覆盖 / 不 checkout / 不 restore / 不 reset --hard / 不 stash。
- `git diff --cached -- <file>` 非空且非本人 staged ⇒ 禁止覆盖。

**G2 编辑中/提交前**：`diff --check`；staged 集合 ⊆ 显式 add 清单；staged 零 I001；278 个 Trae 改动仍为 ` M`（未暂存）；两次采样 status 变化 ⇒ Trae 正实时编辑同文件，停并约定写入窗口。

**G3 推送闸**：`fetch` → `merge-base --is-ancestor FETCH_HEAD HEAD` → `rev-list --count HEAD..FETCH_HEAD = 0` → `push --dry-run` → push → 复校 `HEAD == origin/main`（含 `ls-remote` 实测）。任一失败即停，回 G0。

**禁止清单**：`add -A` / `add .` / `commit -a`；`--force` / `--force-with-lease` / `--no-verify`；`stash`；`checkout --` / `restore` / `reset --hard` / `clean -fd`；`pull` / `merge`；`worktree add`（B 例外，分叉必现）；对 Trae 的 I001 做工作树级删除或整文件 reformat；把 `test_sidebar_nav.py` / `_NAV_GROUPS` / `top_nav.py` / 24 页 `_SUBPAGES` 纳入本批次；把 P0+P1 拆成两个可独立上线的提交。

**必须停下来找老板协调的 10 类触发**：非 FF 或 HEAD 落后 · Trae 在目标行段有实质改动且无法无覆盖合并 · 他人已暂存 · I001 与目标改同一 hunk · 必须改 P2 守卫文件才能过 · 必须拆批才能避冲突 · 密钥/大文件扫描命中或探针库入 staged · pytest 汇总行缺失/冒烟超时 · Trae 实时编辑同文件 · 全仓无 `safe_switch_page` 或 session 不可跨页持久化。

### 6.1 当日真实触发案例（2026-11-04，本轮亲历）

| 步骤 | 事实 |
|---|---|
| G0 | `origin/main` 从 `3081776` 前进到 `0703387`（4 个提交：`fix(quality)` / merge / 质量数字回填 / snownlp 容错），`HEAD..origin/main=4`、`origin/main..HEAD=0`，`merge-base --is-ancestor HEAD origin/main` 为真 |
| G1 | 远端改动 14 文件，其中 `modules/_news_io.py` / `_news_nlp.py` / `news.py` 与本地 278 个未提交批注**重叠**；本地是 import 行 `# noqa: I001/F401`，远端是 45 行后新增 `except Exception:` 兜底，行段不重叠 |
| 处置 | 先备份 3 文件工作树版本到 `E:/project/ks/_bak_*.py`，再 `git merge --ff-only origin/main` |
| 结果 | Git 拒绝：`Your local changes ... would be overwritten by merge`。**按闸停下**：未 stash、未覆盖、未强推。HEAD 仍 `3081776`，工作树 278 M 原样，本地批注（8/1/11 处）与远端兜底各自完好 |
| 结论 | 触发「同文件有 Trae 痕迹 + 本地未提交改动」停止条件 ⇒ 本轮规划文档**不提交、不推送**，等协调（§8） |

## 7. 回退与降级（诚实底线）

- 语义修正覆盖不全 ⇒ 不回退已修部分，逐处 `# TODO(A股口径)` 并**如实列出剩余命中数**；若剩余落在报告卡可见区 ⇒ **整批不提交**，不拆批、不放宽守卫、不加 xfail/skip。宁可显示「中性 / 方向未判定」，不假造方向。
- 深链 session 不支持 ⇒ 按钮改显式提示 + code 明文可复制，**不假造跳转成功**；返回控件可降级为不带 code，但断言「降级分支存在与可见」，验收标「降级，未达标（已如实标注）」。
- 窄屏 mega 折叠不可行 ⇒ 本就 P2，本批次不实施；不得以折叠为名在数据层删导航项。
- aria 受限 ⇒ 用原生 `help`/`disabled` + `xc_error_box` 三重编码或等效 live region，**绝不写不起作用的 aria 字符串骗守卫**。
- 推送后缺陷 ⇒ `git revert <SHA>` 生成反向提交按 FF 推送，不 force、不改写历史；所有降级同时在 commit message / §10 回报 / 验收清单三处登记。
- **v2 补充降级**：若 6 处 `off` 的 `delta_dir='flat'` 实现未就绪，则该 6 处**保留原 `st.metric` 不动**，仅在验收清单标「降级（迁移未达标）」，并如实登记剩余命中数；**不得**把 `flat` 错误渲染成红/绿来假装迁移完成，也不得用 `xc_kpi_grid` 的默认参数蒙混。语义不变量 A 仍须先锁定，原子批次不因该降级拆批。

## 8. 交付状态与解除阻塞

**本轮产物**：本文 `docs/ui_deferred_next_round.md`（仓库内，**untracked、未提交、未推送**）+ §6 协调闸 + 三阶段成员结论（会话内）。本轮零改码；上一交付 `docs/quality_regression_summary.md` 已随 `3081776` FF 推送。

**未推送原因**：本地 `HEAD=3081776` 落后 `origin/main=0703387` 共 4 个提交，`git merge --ff-only` 被 3 个重叠文件的未提交批注挡下（§6.1）。按红线不 stash、不覆盖别人的 278 个改动，也不强推。

**解除阻塞步骤（需老板或 Trae 先协调）**：
1. 由 Trae/老板决定那 278 个 `# noqa: I001` 未提交批注的归属：提交它们，或明确可丢弃后自行处理；备份已在 `E:/project/ks/_bak_*.py`。
2. 工作树干净后再 `git merge --ff-only origin/main`，验证 3 个文件的本地批注与远端 `except Exception:` 兜底都还在。
3. 然后显式 `git add -- docs/ui_deferred_next_round.md` → 密钥/大文件扫描 → staged 清单核对 → commit → `fetch` → FF 校验 → `push --dry-run` → push → 复校 `HEAD == origin/main`。
4. 期间**不得**对这 3 个重叠文件做 `checkout -f` / `restore` / `stash` / `clean`，也不得把并发会话的 278 个改动裹挟进任何提交。

## 9. 验收清单汇总（合计 83 条，来源与汇编口径）

| 来源 | 条数 | 要点 |
|---|---|---|
| Phase 1 视觉 | 28 | 全局红线回归、`sf-` 清零、7 处反转文案、反向验收「24 页字符串 ≥1」、导航 6 类目 diff、登录 `lg-*` 保留率 100% |
| Phase 2 体验 | 27 | IA/入口 7 条、语义与无障碍 8 条、响应式 5 条、交互状态 4 条、批次回归 3 条 |
| Phase 3 工程（v2） | 28 | 方案留痕、G1 判定留痕、staged 集合一致（14 文件）、零 I001、密钥扫描、FF 四闸、pytest 汇总行、SMOKE_BATCH 分批、24 页字符串零改动、**8 处 `delta_dir` 全显式 + 混合态守卫升级 + G6 零改动**、对比度 12 组、单一 commit、§10 回报 |
| 主理人补充 | 1 | `22:870` 出边处显式登记「尚有同类直连未清理」并列出 10/51/scroll_nav 三处；**`test_sidebar_nav.py` 通过不得作为「入口已全部收敛」的判据** |

> 完整逐条检查方式见三阶段成员交付原文（2026-11-04 会话，Phase 3 以 **v2** 为准）。本文未复制 83 条全文，避免与原文产生第二套口径；执行时以成员原文 + 本文 §1/§5 裁定为准。

## 10. v3 执行复核与勘误（2026-11-04，M1 开工前）

> 本章由主理人在 `85e1168` 之后、动 M1 之前**按当前 HEAD 真扫**得出，优先级高于 §1–§5 的成员结论。
> 诚实边界：专家团三阶段结论基于 `3081776` 基线；并发方 `32dd1c3`（283 文件）后，M1 目标族
> 仅 4 文件被触碰且全是行尾 `# noqa` 批注（+N/-N 全等），v2 的行号与代码快照**逐行仍有效**。

### 10.1 推翻一条 P0 结论（重要）

项目存在**两套并行且被守卫锁定**的配色语义，源码注释明确承认，不是笔误：

| 层 | 变量/常量 | 口径 | 锁定处 |
|---|---|---|---|
| 报告体 / 个股页价格域 | `--doc-up:#009e60`（绿涨）、`--doc-down:#dc2626`（红跌）；`colors.RED=#009e60`、`GREEN=#dc2626` | **绿涨红跌** | `ui_theme.py:195-196,270,592`；`tests/test_colors.py:41-42` 硬断言 |
| 交易屏 / 全站 A 股 | `--ss-up/--ss-down`；`UP_COLOR=#ff4d4f`、`DOWN_COLOR=#00d486` | **红涨绿跌** | `tests/test_colors.py:44-45` 硬断言 |

`ui_theme.py:592` 原文即「报告体 --doc-up/--doc-down 绿涨红跌 · 交易屏 --ss-up/--ss-down 红涨绿跌」；
`financial_report_helpers.py:18`、`stock_analysis_helpers.py:19,453` 亦写明 20 页价格域是例外。

⇒ **撤回 §1/§4 的「`20_个股分析.py:5-6` docstring 改红涨绿跌、清除 `#009e60/#dc2626`」**：
该 docstring 与 `stock_research.py:25` 导读文案在当前代码下是**准确描述**，改了会让文档与真实渲染相反；
反转 `--doc-*` 更会撞 `test_colors.py` 并破坏大面积渲染。7 处 🟢强势/🔴偏弱属**强弱信号灯**语义
（对照 `pages/13_市场强弱.py:8`「强=红/弱=绿」），确实反了，但与价格域例外是两件事，**不得一刀切**。

真未被覆盖的文档矛盾在 `pages/96_新手教程.py:202/240`（宣称全局统一、个股页也遵循），归 P3 补例外注记。

### 10.2 M1 修订版实际改动（单一原子批次）

| 项 | 落点 | 动作 |
|---|---|---|
| A' 方向语义 | `modules/stock_research.py` | 7 处 🟢/🔴/⚪ → `▲/▼/—` 形状 + 方向词；颜色交给 `delta_dir`，不碰 `--doc-*` |
| C' KPI 终态 | 同上 | 6 处财务 `st.metric(off)` → `xc_kpi_grid` 6 卡（显式 `delta_dir="flat"`，`help→meta`）；2 处窄列 `st.metric(inverse)` → `stat_tile`（按符号 up/down/flat）；存量 L1903-1905 三张卡补 `delta_dir`；共 **18 张卡 + 2 瓦片全显式** |
| C'' 组件词汇 | 同上 | 本文件 8 处 `sf_card` → `xc_section_header`；清 `sf_metric` 死导入与重复导入 |
| E' 守卫 | `tests/test_metric_delta_color.py` | 混合态分支：11/20 走「零 metric + 显式 delta_dir」终态，40 保留原 `delta_color` 断言；`COMPLETED_FILES` 条目不删；加 2 例 mutation 自验防空转 |
| E'' 新守卫 | `tests/test_stock_research_semantics.py` | 锁方向形状、零彩色圆点、零 `st.metric`/`sf_card`、18 卡契约，**反向锁 `--doc-*` 绿涨红跌例外不被误改** |
| 🚫 零改动 | `pages/20_个股分析.py`、`modules/colors.py`、`ui_theme.py --doc-*`、`tests/test_colors.py`、`tests/test_no_st_metric_in_pages.py`(G6) | 按 10.1 裁定 |

### 10.3 如实登记的降级与剩余（不得包装成「全仓收敛」）

- `sf-*` **未清零**：本文件仍有 76 处 `sf-*` CSS class 字符串；`ui_theme.py` 有 99 处 `.sf-*` 定义；
  `portfolio_views.py` 另有 9 处 `sf_card` 调用（v2 §4 本就列为零改动，后置）。本批次只清
  `stock_research.py` 内的 `sf_card` 调用点。
- P2 深链契约（22→24 页 `hub_gyj_view`/`pick_stock`）、P3 登录页中性化、`pages/96` 例外注记
  **均未实施**，仍属下一轮。
- 全量页面冒烟按 `SMOKE_BATCH` 分批执行；未跑全量 457 测试文件，不得对外称「全站绿」。
- 并发协作：全程未 stash / restore / checkout -f / force / `add -A`；3 个 untracked（`.trae/`、两份 thesis docx）零触碰。

### 10.4 经验（写给下一轮）

专家团结论必须由主理人在**执行前**按当前 HEAD 真扫复核；「看起来合理的一致性整改」可能改成与真实
渲染相反。「颜色名」不等于「颜色语义」——本仓 `colors.RED` 是绿色。改文案前先读单一真理源与守卫断言。

## 11. v4 实施回执（2026-11-04，M1 之后的下一轮）

> 本章登记**已实际落地**的项与**仍未清零**的项。执行基线 `85e1168` → `1440509` → `bca96ad` → `4c99b26`。

### 11.1 已实施

| 项 | 落点 | 提交 |
|---|---|---|
| **P2 深链契约** | `pages/22_基本面分析.py` 出边改 `safe_switch_page`（跳转前写 `hub_gyj_view='🔬 深度分析'` + `pick_stock`）；`pages/24_个股研究.py` 消费端读 `query_params` 预选分段、回填 `pick_stock_confirmed/pick_stock_query`、补「← 返回基本面分析」控件 | `bca96ad` |
| **P3 配色例外注记** | `pages/96_新手教程.py` FAQ 与误区各补一条：「个股分析页（报告体）价格域为**文档体绿涨红跌例外**（`tests/test_colors.py` 锁 `--doc-up:#009e60`）」 | `bca96ad` |
| **P1 组件词汇补漏** | `modules/portfolio_views.py` 9 处 `sf_card` → `xc_section_header`（位置兼容），3 处 `ui_theme` 导入改 `ui_kit`，清 `sf_metric` 死导入 | `bca96ad` |
| **深链契约守卫** | 新增 `tests/test_deep_link_contract.py`（5 例：跳转方写参 / 消费方读参 / 返回控件 / `_SUBPAGES` 字符串零改动） | `bca96ad` |
| **P1 信号同步自动化缺口** | 新增 `modules/p1_sync.py` + `scripts/refresh_p1_signals.py` + `tests/test_p1_sync.py`（14 例）；既有 automation `aed3ad1a` prompt 升级为调用该工具 | `4c99b26` |

**P1 同步工具口径**（可复现、不臆造）：按**数据日 `latest_date` 降序**选最新，`mtime` 仅并列次键（不用 mtime 当数据新旧）；结构校验**复用** `p1_signal_quality.check_file`（新鲜度不作同步闸，fusion 有设计性滞后）；md5 相同 → 幂等跳过；目标已是更新数据日 → **绝不降级覆盖**；全部候选结构无效 → **拒绝写入**并如实带出缺字段明细；源目录发现走 `p1_signal.discover_source_dirs()`，**零硬编码路径**（AST 守卫锁）。

实测：P1 产出 5 个模型信号（baseline/ens/ev/fusion/gru，`latest_date=2026-10-16`）与自托管副本 md5 一致 → 幂等 `unchanged`；`signal_rotation.json` 为**非模型信号 schema**（`as_of/all_ranked/method`，缺 `model/latest_date/horizon/top_short/daily`）→ 按结构闸拒绝写入并报出缺字段。

### 11.2 仍未清零（如实登记，不得包装成「全仓收敛」）

- **CSS 令牌层未重命名**：`modules/stock_research.py` 仍有 76 处 `sf-*` class 字符串，`modules/ui_theme.py` 有 99 处 `.sf-*` 定义。台账 #43「P2 组件词汇统一 sf_card→xc_card」虽已标 completed，但其覆盖的是**组件调用点**；本轮补齐了 `portfolio_views.py` 的漏网 9 处，**CSS 类名层仍是后置深改**（全量重命名需整套视觉回归，超出单批次风险预算）。
- `modules/ui_theme.py::sf_card` / `sf_metric` 函数本体**保留未删**（无调用方亦不删，避免连带破坏）。
- **P3 登录页中性化未实施**（`pages/90_登录.py` 的 `lg-*` 紫渐变 / 裸 `st.error` 仍在；▲/▼ 与「涨/跌」文字是黑白化显式例外，DOM 保留）。
- **shim 直连三处未清**（§5 已登记）：`10_行情看板.py:311/343/601/609 → 11 页`、`51_每日晨报.py:184 → 46 页`、`scroll_nav.py:411 → /个股分析?pick_stock=`。
- **P2 导航折叠未实施**（本就后置；不得以折叠为名在 `_NAV_GROUPS` 数据层删项）。
- 全量 457 测试文件**未跑**；本轮为定向抽样（见 §11.3），**不得对外称「全站绿」**。

### 11.3 验证矩阵（真实汇总行）

| 批次 | 用例 | 结果 |
|---|---|---|
| M1 核心守卫 | 154 | 154 passed |
| M1 设计系统族 | 106 | 106 passed |
| M1 页面冒烟（26×3 分批） | 78 | 78 passed |
| M2 守卫（深链+导航+颜色+metric+语义+设计） | 161 | 161 passed |
| M2 公开数字 + 截图防造假 | 22 | 22 passed |
| M2 页面冒烟（26×3 分批） | 78 | 78 passed |
| M3 P1 族（含新 14 例） | 158 | 158 passed |
| M3 公开数字 + metric 组 | 105 | 105 passed |

合计 **862 例零失败**（跨 M1/M2/M3 三批，含 2 次页面冒烟全量分批）。
## 12. ① sf-* 令牌层收敛 · 实施计划 v1（2026-11-04，专家团 Phase 1 + 主理人复核）

> 本章是 **#35 规划 v4 §11.2 登记的「CSS 令牌层未清零」项**的实施前置。
> 产出方式：UI 设计全栈专家团 Phase 1（视觉方向，`frontend-design-architect`）真扫 +
> 主理人独立复核纠偏。**Phase 2（体验）/ Phase 3（前端工程）尚未完成 ⇒ 本章不含最终分批定案。**
> 诚实边界：本轮**零改码**（只读审计 + 清单生成）。

### 12.1 规模实测（Phase 1 真扫；主理人已抽查复核）

| 范围 | 实测 |
|---|---|
| 全仓 `sf-*` 出现总数 | **495 处 / 13 文件**（主理人清单口径：待改 383 + 保留 94 + 未映射 18） |
| `modules/ui_theme.py` | 231 处（44 个不同选择器） |
| `modules/stock_research.py` | 76 处（25 token） |
| `modules/starfield_theme.py` | 58 处（14 token）—— **CSS 规则为死代码，但同名 token 他处在用**（见 12.3） |
| `modules/button_colors.py` | 39 处（`sf-btn-*` 族，保留） |
| `modules/scroll_nav.py` | 29 处（`sf-scroll-*` 族，保留） |
| `modules/dark_text_fix.py` | 29 处（`sf-text-*`/`sf-chip*` 族，保留） |
| 其余 | `stock_analysis_helpers.py` 6、`ui_kit.py` 4、`pages/13` 6、`pages/43` 5、`pages/44` 7、`pages/47` 3、`_widgets_ai.py` 2（仅注释） |

### 12.2 决定性发现：`sf-` 是 **5 个互不相干 CSS 栈**共用的命名空间（同名不同义）

⇒ **禁止整体重命名 / 禁止全局 sed**。必须按族拆分：

| 族 | 代表 token | 语义归属 | 本轮处置 |
|---|---|---|---|
| **A 仪表盘层** | `sf-card` `sf-card-title` `sf-card-subtitle` `sf-metric-card` `sf-page-link` `sf-section-title` `sf-header` `sf-brand` `sf-tag` `sf-pill` `sf-table` `sf-alert` `sf-vs` `sf-vsbox` `sf-disclaimer` `sf-note` `sf-one-line` `sf-verdict` `sf-grid-4` `sf-cta-*` `sf-perspective-card` `sf-intel-*` `sf-scale*` `sf-risk-iron` `sf-insight-box` `sf-doc-*` `sf-up` `sf-down` `sf-price-big` `sf-triangle` `sf-h1` `sf-h2` `sf-stat` | 个股报告卡 / 决策仪表盘（生产在用，`ui_theme` 每页注入） | **本轮目标** |
| B 按钮层 | `sf-btn` `sf-btn-primary` | 白盒按钮配色（`button_colors.py` 自成体系） | **保留** |
| C 文本层 | `sf-text-*` `sf-chip*` `sf-emph-*` | 暗色文本修正（`dark_text_fix.py`） | **保留** |
| D 滚动层 | `sf-scroll-*` `sf-slide` `sf-chat-end` | 回到顶部 / 浮动按钮（`scroll_nav.py`） | **保留** |
| E 星辰层 | `sf-chart` `sf-kline` + 同名 token | 星辰暗色金融风（`starfield_theme.py`） | **CSS 规则可清**（P2 候选），但**同名 token 他处在用**，不可按文件整块处理 |

### 12.3 主理人复核纠偏（3 条推翻/修正 Phase 1 结论）

1. **`starfield_theme.py` 不是「生产零调用」** —— `modules/stock_research.py:1419`（`KLINE_CHART_CONFIG`）、
   `pages/53_星辰AI.py:40`（`inject_plotly_dark`）都是真实生产引用 ⇒ **该模块不可删**。
   且其内 16 个 sf-* token **逐个查得全部有外部引用**（`ui_theme` 最多，其次 `stock_research` / `pages/13` / `ui_kit`）。
   ⇒ 准确表述：**它自己的 CSS 规则不生效**（生产注入的是 `ui_theme` 的 dashboard_sf_css），
   **但同名 token 在别处被实际使用**。清理判据必须是「该 token 在本文件外零引用」，**不能按文件名整块处理**。
2. **`--doc-up/--doc-down` 的定义位置与字面量写法被守卫硬锁**（Phase 1 未提）：
   `tests/test_no_hardcoded_semantic_hex.py:51-55` 断言 `ui_theme.py` **源码字符串**含
   `--doc-up:#009e60` / `--doc-down:#dc2626`；`tests/test_ui_theme.py:60-61,69` 断言运行时 CSS 同值；
   `tests/test_stock_research_semantics.py:98` 断言两者同在 theme 源码。
   ⇒ 「把 --doc-* 收敛进 --ss-*」「把定义搬到别处」「改字面量格式」三类方案**都会直接红**。
3. **`--doc-up/--doc-down` 的真实形态** = `_THEME_ROOT_VARS` 的 classic 两块
   （`ui_theme.py:195` dark / `:196` light），**其余 6 套非 classic 风格块确实没有** ⇒
   **D2 缺陷成立**（6 套风格下报告体价格域回落继承色）。

### 12.4 两个 🔴 级既有缺陷（与 sf-* 收敛解耦）

- **D1 跨域串色**：`ui_theme.py:270` 附近 `.sf-pill.up` 底色走**文档域绿**（`rgba(0,158,96,.12)`）
  × 字色走 `var(--buy)`（`#ff4d4f`，**交易域红**）⇒ classic 暗色下渲染「绿底红字」；
  `.sf-pill.down` 反之。**且 `_LIGHT_CSS`（`ui_theme.py:55` 起）全字面不含 `--buy`/`--sell`**
  ⇒ 亮色主题 `var(--buy)` 未定义 → 回退继承色。
  生产影响点：`pages/43:222`、`pages/44:129`、`pages/47:418/421/424`、
  `stock_research.py:578`（情绪面）、`:588`（`sf-tag` 舆情极性）。
  ⚠️ 这三处的 up/down/mid 语义是**订单状态成功/失败、舆情极性、技术强弱**，**都不是价格涨跌**。
- **D2 价格域缺定义**：见 12.3 纠偏 3。**独立立项，不混进 sf-* 收敛批次**（主理人裁定）。

### 12.5 ③ #40 / #41 的真实缺口（Phase 1 裁定 + 主理人复核）

- **#40「页头状态胶囊去 emoji + 令牌化」已在 `9255fc1`（2026-10-31）完成**：
  `page_utils.py:71-130 _build_status_chips()` 已用 `svg_icon("moon"/"sun")` + `--ss-*` 令牌；
  `tests/test_ui_kit_hero.py:86` 硬断言无 `☀️/🌙`。
  **真实残留仅 2 处**：① `page_utils.py:113-127` 交易时段胶囊仍硬编码 hex
  （`#ff4d4f`/`rgba(255,77,79,.10)`/`#dc2626`/`#00d486`/`rgba(0,212,134,.10)`/`#166534`）；
  ② `modules/ui_kit.py:462` 页头主图标 `f'<span class="{icon_cls}">{html.escape(icon)}</span>'`
  仍原样输出 emoji（`render_standard_page(icon=...)` 实测 52 处调用 / 51 个不同 emoji）。
- **#41「顶栏 SVG 替换 emoji」真实缺口 = `_EMOJI_MAP` 覆盖不全**：
  65 个导航条目中 49 个 emoji 未收录 → 回退原始 emoji；`_ICONS`（`modules/ui_icons.py:19`）
  仅约 4 个空闲图标名，需新增约 30~40 个 24×24 SVG path。
  ⚠️ 主理人复核修正：SVG 在 **`modules/ui_icons.py`**（`_EMOJI_MAP` L5、`_ICONS` L19、`svg_icon` L99），
  `modules/top_nav.py` 411 行内 **`<svg>` 标签 0 个**（只是 import 并调用 `svg_icon`）。
  ⇒ **#41 降级 P2 后置，不进本轮**（数据层 `_NAV_GROUPS` 零改动，
  由 `tests/test_sidebar_nav.py:145-159 test_icon_global_uniqueness` 硬锁保护）。

### 12.6 可执行替换清单（已生成，`_n1_replace_plan.json`）

- **待改 383 处**（仪表盘族）｜**保留 94 处**（按钮 39 / 文本 27 / 滚动 26 / 仅注释 2）
  ｜**未映射 18 处**（需补映射：`sf-up`/`sf-down` 价格域、`sf-stat`、`sf-emph-*`、`sf-slide`、`sf-chat-end`、`sf-chart`、`sf-kline`）
- **实施核心陷阱**：替换必须**长 token 优先**（`sf-card-title` 先于 `sf-card`），
  否则前缀包含关系会被破坏（如 `sf-card` 先替换会把 `sf-card-title` 打成 `xc-card-title` 前缀错乱）。
- **必改守卫 12 个**（改名后不同步更新即红）：

| 守卫文件 | 断言内容 |
|---|---|
| `tests/test_bento_standards.py:131-132` | `_KNOWN_PAGE_CLASSES` **未知类登记制白名单**含 `sf-card`/`sf-card-subtitle`/`sf-card-title`/`sf-metric-card`/`sf-page-link` → 改名后**必须登记新名**（白名单是「已人审快照」非禁止项；`_BANNED_CLASS_TOKENS` 实测**不含**任何 `sf-*`） |
| `tests/test_page91_prefs_slim.py:36-43` | `.sf-section-title` 必须存在 + `<div class="sf-card">` 位置比较 + `dashboard_sf_css` 携带该样式（顺序敏感） |
| `tests/test_static_css_cache.py:31` | 断言 `.sf-card` 出现在注入 CSS 中 |
| `tests/test_component_vocabulary.py:46` | 注释提及 `.sf-section-title` |
| `tests/test_ui_kit_tokens.py:172` | docstring 提及 `sf-card-title` |
| `tests/test_no_hardcoded_semantic_hex.py:51-55` | 断言 `ui_theme.py` 源码含 `--doc-up:#009e60` / `--doc-down:#dc2626` |
| `tests/test_ui_theme.py:60-61,69` | 断言运行时 CSS 含 `--doc-up:#009e60` / `--doc-down:#dc2626` |
| `tests/test_stock_research_semantics.py:98` | 断言 `--doc-up:#009e60` 与 `--doc-down:#dc2626` 同在 theme 源码 |
| `tests/test_dark_text_fix.py:52` | `class="sf-text-title"`（保留族，不动则无需改） |
| `tests/test_starfield_theme.py:71,76` | `class="sf-verdict b"` / `"sf-verdict o"`（保留族，不动则无需改） |
| `tests/test_scroll_nav.py`（12 处） | `sf-scroll-top` / `sf-scroll-bottom-float`（保留族，不动则无需改） |
| `tests/test_whitebox_button_colors.py`（6 处） | `sf-btn sf-btn-primary`（保留族，不动则无需改） |

### 12.7 语义红线（不可越）

1. **双套配色**：报告体/个股页价格域 `--doc-up:#009e60`（**绿涨**）/ `--doc-down:#dc2626`（红跌）；
   交易屏/全站 `--ss-up:#ff4d4f` / `--ss-down:#00d486`（**红涨绿跌**）。
   `modules/colors.py` 的 `RED` 实为绿色、`GREEN` 实为红色；`tests/test_colors.py:41-45` 硬断言。
   ⇒ `sf-doc-up`/`sf-doc-down`/`sf-doc-neu` **必须保留 doc 域**，不得并入 `--ss-*`。
2. **强弱信号灯**：`🟢强势/🔴偏弱` 已改 ▲/▼/— 形状；`sf-verdict`（红=多/绿=空）**不得改色**。
3. **暗/浅双风格 × 7 套 `STYLE_PRESETS`**（classic 暗/亮 + 其余 6 套各 1 = 8 组矩阵）：
   改类名须**逐套同步**，不能只改 `:root`。
4. **双响应式并存**：`.sf-grid-4` 视口断点（900/540）与 `xc_kpi_grid` 的 auto-fit 容器
   （`ui_kit.py:921`）冲突 → 收敛时统一到一套。
5. **G6 零扩权**：`tests/test_no_st_metric_in_pages.py` 只扫 `pages/*.py`，**不得**扩到 `modules/`。
6. **零改动清单**：`modules/widgets.py::_NAV_GROUPS`、`modules/top_nav.py`、`tests/test_sidebar_nav.py`、
   `tests/test_colors.py`、24 页 `_SUBPAGES` 字符串。
7. **D1 的 up/down 语义 ≠ 价格涨跌**（订单状态 / 舆情极性 / 技术强弱），修 D1 时不得误染涨跌色。

### 12.8 本章状态与下一步

- ✅ **Phase 1（视觉方向）已完成**（映射表 + 5 族分类 + 风险分级 + 分批建议 B1–B6 / R1–R6）
- ✅ **主理人复核纠偏已完成**（12.3 三条 + 12.6 守卫清单 + 12.5 一处数据修正）
- ✅ **可执行替换清单已生成**（383/94/18 + 12 守卫 + 实施陷阱）
- ⏳ **Phase 2（体验规范）进行中** → 产出：8 组风格矩阵的视觉回归验收标准、对比度**可执行**计算方法、
  D1 修复后的期望渲染、风险独立复核、最终分批定案（`ui_theme.py`+`ui_kit.py`+`stock_research.py`
  被多批次共触时是否必须合成单一原子 commit）、改动后最小回归测试集（只列真实存在的文件）
- ⏳ **Phase 3（前端工程）待启动** → 产出：逐批次实施步骤 + 守卫同步点 + 原子 commit 边界 + 验证矩阵
- ⏳ **实施待 Phase 2/3 完成后进行**（本轮零改码；不做半迁移）
## 13. ① sf-* 令牌层收敛 · Phase 2 体验规范 + 主理人裁定（2026-11-04）

> 产出方式：专家团 Phase 2（`ux-ui-designer`，体验方向，零改码）+ 主理人综合裁定。
> **Phase 3（前端工程实施计划）待启动 ⇒ 本章只定「做什么 / 分几批 / 怎么验」，不定最终类名表。**
> 诚实边界：本轮**零改码**；Phase 2 **未跑任何 pytest**、**无浏览器实测**（项目无 Playwright/Selenium）。

### 13.1 🔴 D3（新发现，最高优先级）：`:root` 级联倒挂 ⇒ 6 套非 classic 风格的 vars 被静默覆盖

**Phase 2 用运行时探针实测**（拦截 `st.markdown` 捕获真实注入序列 + 按 CSS「同特异性后到者胜」求最终值），
terminal 风格 `--brand-1` 的级联序列：

```
#01 _DARK_CSS :root              #5b53f0
#02 _TOKEN_CSS :root             (未定义)
#03 inject_kit_css → _TOKEN_CSS  #4f46e5
#04 preset[terminal].vars        #e8a33d   ★预设值在此出现
#06 dashboard_sf_css 前置 _TOKEN_CSS  #4f46e5
#07 dashboard_sf_css 的 :root{root}   #5b53f0
#09 page_hero → _HERO_FALLBACK_CSS    #4f46e5   ★最后注入者
```

⇒ 最终 `--brand-1` = `#4f46e5`（经典紫），**不是** terminal 预设的 `#e8a33d`（琥珀）。
**8 组矩阵中 6 组的 `--brand-1/--brand-2/--card/--card2/--txt/--txt2/--bg/--border/--hold/--hover/--ss-up/--ss-down/--doc-up/--doc-down` 全被经典值覆盖**
⇒ terminal 琥珀 / cyber 霓虹黄青 / aurora 紫 / swiss 纯黑 / ink 朱砂 / finpro 商务蓝
**在 `:root` 令牌层全部失效**；「风格仍能用」是**假象**（全靠 `STYLE_PRESETS[*]['extra']` 里大量
`!important` 硬编码色撑着）。

**三重根因**：
1. `modules/ui_kit.py:88` —— `_TOKEN_CSS` 的 `:root` **硬写** `--brand-1:#4f46e5; --brand-2:#7c3aed;`
   （注释自称「对现有 --brand-1/--ss-* 消费者零影响」，**实为全局覆盖**）。被 `inject_kit_css()`(`ui_kit.py:436`)、
   `dashboard_sf_css()`(`ui_theme.py:223`)、`_HERO_FALLBACK_CSS`(`ui_kit.py:390`) 各注入一次，
   **最后一次在 `page_hero()`(`page_utils.py:60`)**。
2. `modules/ui_theme.py:223` —— `dashboard_sf_css()` 自带 `:root{_THEME_ROOT_VARS}`，
   而 `_THEME_ROOT_VARS`(`:195/:196`) 是**经典基座**（`--card:#1a1a2e` `--txt:#e2e8f0` `--brand-1:#5b53f0`），
   非 classic 风格下覆盖预设值。
3. `modules/ui_theme.py:185` `inject_style_css()` 在 `apply_theme` **尾部**，比
   `dashboard_sf_css()`(`page_utils.py:57`)、`_HERO_FALLBACK_CSS`(`page_utils.py:60`) **更早**。

⇒ **主理人裁定：D3 独立立项，且必须先于 C2 落地**——否则「8 组风格矩阵验收」整批不可信
（Phase 1 的 AC-4 全部建立在错误的前提上）。`docs/ui_audit_report.md:20` 曾记录
「令牌定义散列三处、cascade 脆弱」，D3 是那行记录的**可执行根因**。

### 13.2 五个缺陷汇总（🔴 三个 / 🟡 两个）

| 编号 | 缺陷 | 级别 | 处置 |
|---|---|---|---|
| **D3** | `:root` 级联倒挂，6 套非 classic 风格 vars 被覆盖 | 🔴 | **独立立项 + 前置**（13.1） |
| **D1** | `.sf-pill/.sf-tag` 跨域串色：底色走文档域绿 × 字色走 `var(--buy)` 交易域红 ⇒ classic 暗色「绿底红字」；且 `_LIGHT_CSS`(`ui_theme.py:55` 起) **全字面不含 `--buy`/`--sell`** ⇒ 亮色下 `color:var(--buy)` invalid at computed-value time ⇒ 回落 `inherit` | 🔴 | C3 |
| **D1-b** | classic 亮色 `--buy/--sell` 未定义（影响面不止 pill） | 🔴 | **C1**（先于 C3） |
| **D2** | `--doc-up/--doc-down` 只在 classic 暗/亮定义 ⇒ 6 套风格下报告体价格域回落继承色 | 🔴 | **独立立项**（不改 sf-*） |
| **D4** | `page_utils.py:124` 「已休市」胶囊 `#166534` on 合成底 ≈ **2.2:1 ❌** | 🟡 | C3 |
| **D5** | `--doc-up` 在 classic-light / swiss-light / ink-light 三组对比度 3.13~3.47（< 正文 4.5），但字面值被 3 个守卫硬锁不可改 | 🟡 | C3（提字号/字重 或 新增小号令牌） |

### 13.3 D1 修复的期望渲染（Phase 2 已算对比度）

| 语义 | 底色 | 字色 | 边框/左条 |
|---|---|---|---|
| `up`（订单成功/舆情正面/技术强） | `color-mix(in srgb, var(--ss-box-success) 8%, var(--card2))` | **`var(--ss-text)`** | `3px solid var(--ss-box-success)` |
| `down`（订单失败/舆情负面/技术弱） | `color-mix(in srgb, var(--ss-box-danger) 8%, var(--card2))` | **`var(--ss-text)`** | `3px solid var(--ss-box-danger)` |
| `mid`（中性/等待） | `color-mix(in srgb, var(--ss-box-warn) 8%, var(--card2))` | **`var(--ss-text)`** | `3px solid var(--ss-box-warn)` |
| `neu`（`sf-tag.neu`） | `var(--card2)` | `var(--ss-text-muted)` | `var(--ss-line)` |

**为什么字色不用 `--ss-box-*` 本身**：classic 亮色实测 `success #16a34a` vs 合成底 **2.68:1 ❌**、
`danger #ef4444` **2.99:1 ❌**、`warn #f59e0b` **1.82:1 ❌**；
改字色为 `--ss-text #1e293b` vs 合成底 `#e2efed` = **12.40:1 ✅**（正文 ≥4.5）。

⚠️ **语义先裁定再改色**：`pages/47_价格预警.py:421` 把「🔥 已触发」映射为 `down`，
而 `pages/44_智能条件单.py:129` 把 `triggered→up` ⇒ **同一事件异色**。
不先裁定就直接改色，只会把「绿底红字」换成「红底绿字」。
⚠️ 这 6 态的 up/down/mid **都不是价格涨跌**（订单成败 / 舆情极性 / 技术强弱）
⇒ **不得**把 `--doc-up/down` 拉进来；**也不得**连带改 `stock_research.py:551` 的舆情热度条
（那处走 `color:var(--buy)`，属交易域，与 pill 独立）。

### 13.4 Phase 1 ↔ Phase 2 分歧汇总（10 条）+ 主理人裁定

| # | Phase 1 | Phase 2 | 主理人裁定 |
|---|---|---|---|
| 1 | 未覆盖 `:root` 级联 | **D3 新增，最高优先级** | **采纳 Phase 2**，D3 前置独立立项 |
| 2 | R4（价格域 3 类 + `sf-up/sf-down` 零改动）🔴 | 降级 🟡（`sf-up/sf-down` 是死代码属 B4；价格域一行不改） | **采纳 Phase 2**：R4 降级，**价格域一行不动** |
| 3 | #40 残留「仅 2 处」 | **应为 3 处**（`page_utils.py:116,118,124,126` 4 行硬编码 + `ui_kit.py:462`） | **采纳 Phase 2** |
| 4 | #40 emoji「52 调用 / 51 个不同」 | **67 调用 / 52 个不同** | **采纳 Phase 2**（AST 实测） |
| 5 | #41 覆盖 16/65 | **16/63** | 采纳 Phase 2 |
| 6 | #41 需新增 30~40 个 path | **约 43 个**（`_ICONS` 50，空闲仅 brand/chart/moon/sun） | 采纳 Phase 2 |
| 7 | 44 个选择器 | 44 有效 + 1 个正则残渣 = grep 计 45 | 采纳 Phase 2（表述修正） |
| 8 | 未提及 | `pages/47:421` 「已触发」映射为 `down`，与 `pages/44` 同事件异色 | **采纳 Phase 2**，C3 前必须裁定 |
| 9 | 未提及 | `--doc-up` 三组亮色 < 4.5 | 采纳（D5，C3） |
| 10 | 「starfield_theme 生产零调用」 | 模块**不可删**（`stock_research.py:1419` + `pages/53:40` 真实 import），但 `inject_theme()`（唯一注入 `STARFIELD_CSS` 的入口）**仅在 `__main__` 块调用** ⇒ **CSS 确实生产不生效** | **采纳**：准确表述 =「CSS 规则生产不生效，模块不可删」 |

### 13.5 三批原子方案（Phase 2 裁定，主理人采纳方向；Phase 3 定最终类名表）

**结论：不能拆成多个独立上线批次**——`ui_theme.py` / `ui_kit.py` / `stock_research.py`
被多批次共同触碰，且共享**单个 f-string CSS 模板**（`ui_theme.py:223-270`）与**单个全局 `:root` 作用域**；
分开提交的中间态必然出现「新 CSS 已注入、调用点未改」⇒ **无样式卡 / 白屏**。

| 批次 | 内容 | 落点 | 上线独立性 |
|---|---|---|---|
| **C1** | D3 修复 + D1-b（classic 亮色补 `--buy/--sell`）+ B4 死代码清理（10 个真死，含成对覆写同步删）+ 新建 `tests/test_style_token_cascade.py` + `tests/test_a11y_contrast.py` 改级联口径 | `ui_theme.py:195-196` / `ui_kit.py:88` / `ui_theme.py:942,1076` / `ui_theme.py` 死选择器 | ✅ 独立可上线，**必须先行** |
| **C2** | R1+R2+B1+B2+B3+R5+R6 合并：仪表盘族 sf-* → xc-* 全量迁移（383 处） | `ui_theme.py:225-270,419-421,544-572` / `ui_kit.py:224-227` / `stock_research.py`(7处) / `stock_analysis_helpers.py`(6处) / `pages/13`(5处) / `pages/43,44,47`(仅 pill 类名) | ⚠️ 大头但**必须原子** |
| **C3** | R3 语义修复（D1）+ D4 + D5 + `pages/47` triggered 语义裁定 | `ui_theme.py:270` / `pages/47:421` / `page_utils.py:116-126` | ✅ 独立（唯一改变用户认知的批次，须独立目检/回滚） |

### 13.6 改动后最小回归集（28 个文件，Phase 2 实测存在）

- **必跑硬锁 14**：`test_bento_standards.py` `test_page91_prefs_slim.py` `test_static_css_cache.py`
  `test_component_vocabulary.py` `test_ui_kit_tokens.py` `test_a11y_contrast.py` `test_ui_theme_styles.py`
  `test_ui_theme.py` `test_no_hardcoded_semantic_hex.py` `test_stock_research_semantics.py`
  `test_colors.py` `test_style_presets_structure.py` `test_ui_theme_finpro.py` `test_ui_kit.py`
- **必跑不动族 5**：`test_dark_text_fix.py` `test_starfield_theme.py` `test_scroll_nav.py`
  `test_whitebox_button_colors.py` `test_sidebar_nav.py`
- **必跑受影响页面 9+**：`test_ui_kit_hero.py` `test_ui_theme_alerts_css.py` `test_ui_theme_v10.py`
  `test_ui_theme_no_aurora.py` `test_ui_design_system.py` `test_design_tokens_present.py` `test_ui_bento.py`
  `test_ui_highfreq_pages.py` `test_pages_ui_simplification.py` `test_stock_analysis_fin_report.py`
  `test_market_cube_page.py` `test_no_st_metric_in_pages.py` `test_pages_use_standard_setup.py`
- ⚠️ 涉及 `ui_theme`/`ui_kit`/`stock_research` 的测试共 **41** 个，建议 CI 跑全 41。
- ⚠️ **pytest 汇总行纪律**：仓库默认 `addopts=["-q"]`，命令行再传 `-q` 双重 `-q` 会**吞掉汇总行**
  ⇒ 统一 `-o addopts= -q`；**无汇总行不得判通过**。
- ⚠️ 页面冒烟必须 `SMOKE_BATCH=i/n` 分批（整批撞 10 分钟墙，**被中断不计通过**）。

### 13.7 Phase 2 未验证项（诚实登记）

1. **未跑任何 pytest**（本阶段零改码）⇒ 守卫清单是**静态核对存在性 + 行号**，非执行结果。
2. **无浏览器实测**：项目无 Playwright/Selenium（`import playwright` 失败）⇒ 对比度结论基于 WCAG 公式 +
   CSS 规格推算；`color-mix()` 实际合成依赖浏览器色彩空间，**落地前建议抽验 3 组**。
3. **D3 的浏览器侧未确认**：探针按「Streamlit 把多次 `st.markdown` 的 `<style>` 按调用顺序渲染进同一容器」
   模拟级联——**基于行为惯例，未在真实 DOM 验证** ⇒ 建议 Phase 3 用探针固化成交互守卫。
4. `ui_kit.py:368-369` 用了 `:has`，注释自承「Edge155 实证不支持」（既有问题，非本批引入）。
5. 触控目标 ≥44px（AC-6.5）现状**未验证**。
