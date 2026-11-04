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
### 13.8 Phase 2 修订版裁定（推翻主理人原裁定一条，2026-11-04）

Phase 2 修订版用**运行时探针实测**推翻了我 §13.2 的 D2 表述，并补出 3 条实施约束。

#### 13.8.1 ⚠️ 推翻：D2 的「当前症状」不成立，但**必须与 D3 同批**（我原裁定的执行顺序错了）

- **当前症状实测不成立**：8 组风格 `--doc-up`/`--doc-down` **全部有定义、值全部正确**
  （`#009e60`/`#dc2626`），来源是 `dashboard_sf_css()`(`ui_theme.py:222-223`) 注入的经典 `:root{root}` 块。
  ⇒ §13.2 表里「6 套风格价格域回落继承色」**是错的**，在此更正。
- **但 D2 是被 D3 掩盖的潜伏缺陷**：模拟「D3 修复后」（移除经典 `:root`，让 preset vars 真正生效）——
  **7 套风格 `--doc-up` 全丢**（`None`），**连 classic 也一起丢**（classic 的定义源就是 `_THEME_ROOT_VARS`，
  正是被移除的那块）。
- ⇒ **D3 一修，D2 立刻显形**；若 D3 单独上线，报告会立刻失色（价格数字掉回继承色）。
- ⇒ **主理人裁定更新**：D2 **仍应独立立项**（判定依据不变：与 sf-* 命名无关），
  **但执行顺序必须与 D3 绑定** ⇒ 合并为 **C0（D3+D2 联动）**，不得后置。
- ⇒ 新增机器可拦截项 **AC-0.4**：断言 8 组矩阵下 `--doc-up/--doc-down` 均有定义且 `== #009e60/#dc2626`。
- ⇒ D3 修法可**复用 `modules/ui_theme.py:200` 的 `_build_theme_root()`**（实测生产零调用，只有
  `_THEME_ROOT_VARS` 在 `:222` 被 `dashboard_sf_css` 使用）⇒ 不必新造机制。

#### 13.8.2 starfield 清理：准则 + 排期约束

Phase 2 逐 token 实测：`starfield_theme.py` 内 16 个 `sf-*` 字面量 = **14 个 CSS token + 2 个 div_id**
（`sf-chart`/`:103`、`sf-kline`/`:109`，**非 class、不在命名空间**）。
外部引用要区分「CSS 规则引用」与「**class 字面量**引用」：
- **9 个有外部 class 字面量引用**：`sf-alert` `sf-brand` `sf-card` `sf-disclaimer` `sf-header`
  `sf-table` `sf-tag` `sf-vs` `sf-vsbox`（引用方 = `modules/stock_research.py` / `modules/ui_theme.py` /
  `pages/13_市场强弱.py`）⇒ **类名不可随文件清理**
- **5 个只有外部 CSS 规则同名、无 class 字面量引用**：`sf-down` `sf-note` `sf-one-line` `sf-up` `sf-verdict`
  ⇒ `sf-verdict` 另被 `tests/test_starfield_theme.py:71,76` 硬锁 ⇒ 一律不动

⇒ **准则：清理「规则」，保留「名字」。** `STARFIELD_CSS` 常量可整体删除
（`inject_theme()` 仅在 `modules/starfield_theme.py:141` 的 `__main__` 块调用 ⇒ 生产不注入），
但类名必须继续存在于 `ui_theme` 的 `dashboard_sf_css`，否则 `stock_research.py` / `pages/13` 失配。
⇒ **排期：starfield 清理必须排在 C2 之后或与 C2 同批。**

#### 13.8.3 #40 续项必须拆开（我原 brief 未拆）

- **`modules/page_utils.py:116,118,124,126`**（交易时段胶囊 4 行硬编码 hex）→ **本轮独立做**，归 C3。
  ⚠️ `:124`「已休市」`#166534` on 合成底 ≈ **2.2:1 ❌**（新增 **D4**）。
- **`modules/ui_kit.py:462`**（页头主图标原样输出 emoji）→ **必须随 #41 入 P2**。
  理由：页头 52 个去重 emoji 中 `_EMOJI_MAP` **仅收录 17 个、35 个未收录** ⇒ 现在改 `render_nav_icon(icon)`
  会让 35 个**安全回退成原 emoji** ⇒ 造出「半 SVG 半 emoji」的页头，视觉更不一致。

#### 13.8.4 一条会静默咬人的隐含守卫（Phase 2 发现，我与 Phase 1 均漏）

`tests/test_ui_theme.py:62` 断言 **`"绿涨红跌" in css`** ⇒
**`dashboard_sf_css` 的 CSS 模板里必须保留「绿涨红跌」这四个字的中文注释**。
C2 大改 `ui_theme.py:223-270` 的 f-string 模板时若顺手删掉它 ⇒ **守卫会红且报错信息完全指不到原因**。

#### 13.8.5 修正后的四批方案（Phase 2 修订版，主理人采纳）

| # | 内容 | 依赖 |
|---|---|---|
| **C0**（最高优先） | **D3 + D2 联动**：`ui_kit.py:88` 的 `--brand-1/--brand-2` 处理 + `dashboard_sf_css` 的 `:root` 按风格取值（可复用 `_build_theme_root()`）+ 6 套 preset vars 补齐 `--doc-up/--doc-down`（**字面量必须仍出现在 `ui_theme.py` 源码里**，否则 `test_no_hardcoded_semantic_hex.py:54-55` 会红）+ `tests/test_a11y_contrast.py` 改级联口径 + 新建 `tests/test_style_token_cascade.py`（含 AC-0.4） | 无 |
| **C1** | B4 死代码清理（10 个真死，含 `ui_theme.py:942`/`:1076` 成对覆写同步删）+ B5 | C0 后 |
| **C2**（原子大头） | 仪表盘族 sf-* → xc-* 全量迁移 383 处 + 6 个守卫同步 + **保留「绿涨红跌」注释** | C0、C1 |
| **C3**（独立） | R3 语义修复 + D4 + D5 + `page_utils.py` 胶囊令牌化 | C2（类名已稳定） |

#### 13.8.6 C0 的最大风险（Phase 2 指出，必须逐风格目检）

D3 修好后，6 套风格会从「`extra` 里大量 `!important` 硬编码色撑起来的**假象**」变成「**真正按 vars 生效**」
⇒ **视觉会明显变化**（可能是这些风格首次真正呈现）⇒ **目检必须逐风格，不能只看 classic**。

#### 13.8.7 数字更正（Phase 2 AST 实测）

`#41`：导航 **63** 条（非 65）、未收录 **47**（非 49）、需新增 **约 43** 个 path、`_ICONS` 空闲恰 4
（`brand`/`chart`/`moon`/`sun`）、**`_EMOJI_MAP` 实际 53 条**（16 是「导航中命中数」）；
`modules/ui_icons.py` 中 `_EMOJI_MAP` 在 **L73**、`_ICONS` L19、`svg_icon` L99；
`modules/top_nav.py` **410** 行；`#40` emoji **67 调用 / 52 个不同**（页头 52 中仅 17 被收录）；
最小回归集 **32 个文件**（原 28）。
### 13.9 Phase 1 更正版 + 缺陷编号统一（2026-11-04，Phase 3 开工前的最后修正）

> Phase 1 收到 ux-designer 的 D3 后做了独立复核（tinycss2 规范解析 + 复刻 `render_standard_page`
> 真实注入序列），**撤回了自己的 D2**、**新增 2 条更底层缺陷**、**给出实测通过的修法 fixE**。
> **两名成员独立收敛到「D2 当前症状不成立」这一结论 ⇒ 置信度高。**

#### 13.9.1 ⚠️ 缺陷编号统一（避免后人踩坑）

Phase 1 与 Phase 2 各自用了 D4/D5，**撞号**。本仓库统一为：

| 编号 | 缺陷 | 提出者 | 级别 |
|---|---|---|---|
| **D3** | `:root` 级联倒挂（`dashboard_sf_css` 的经典 `:root` 注入晚于 preset vars） | Phase 2 | 🔴 |
| **D4** | **`modules/ui_kit.py:86` CSS 注释提前闭合 ⇒ `--brand-1` 声明被浏览器丢弃** | Phase 1 | 🔴 |
| **D5** | 6 套非 classic 风格的 `vars` 全未生效（**D3 + D4 的合并结果**，与 D3 同根因） | Phase 1 | 🔴 |
| **D6** | `modules/page_utils.py:124` 休市胶囊对比度 ≈ 2.2:1 | Phase 2 | 🟡 |
| **D7** | `--doc-up` 在 swiss/ink/classic-light 三组 < 4.5（字面值被 3 守卫硬锁不可改） | Phase 2 | 🟡 |
| ~~D2~~ | ~~6 套风格价格域回落继承色~~ | — | **已撤回**（当前症状不成立；降级为 D3/D4 的潜伏缺陷） |

> ⚠️ §13.8 表格里的「D4」= 现 **D6**、「D5」= 现 **D7**（§13.8 写于 Phase 1 更正版到达之前）。

#### 13.9.2 🔴 D4：`ui_kit.py:86` CSS 注释提前闭合 ⇒ `--brand-1` 声明被浏览器丢弃

```
  /* design_system.md §2 新增语义别名（绑定 --ss-*/--acc* 等价变量或 colors.* 既有值，
     绝不臆造独立色相；供未来 page 迁移复用，对现有 --brand-1/--ss-* 消费者零影响） */
  --brand-1:#4f46e5; --brand-2:#7c3aed;
```
注释体内含 `--ss-*/` ⇒ **CSS 注释在第一个 `*/` 处结束**（提前闭合）⇒ 剩余文本成非法 CSS ⇒
浏览器解析到 `--brand-1:#4f46e5` 时报 *"Expected ':' after declaration name"* 并**丢弃该声明**。

**tinycss2 实测**（`_TOKEN_CSS` 的 `:root` 内部，`parse_declaration_list`）：
```
文本声明数: 64 | 解析成功: 63 | 错误数: 1
★★ 真正丢失的声明: ['--brand-1']      ← 精确 1 条
--brand-1 浏览器生效? 否    --brand-2 生效? 是    --ss-up 生效? 是
```
全仓扫描同一 bug 形态（`--xx-*/` 提前闭合）**只命中这 1 处**。

**三点后果**：
1. 注释自称「对现有 `--brand-1`/`--ss-*` 消费者零影响」——**实际它连 `--brand-1` 自己都吞了**。
2. **伪装成"注释"的静默失效**：任何「只修好注释让 `--brand-1` 复活」的单边修复，
   都会让 `#4f46e5` 硬覆盖全站复活，**比现在更糟**（实测 fixA：8 组 `--brand-1` 全变 `#4f46e5`）。
3. `tests/test_ui_kit_tokens.py:247` 硬断言 `"--brand-1:#4f46e5" in _KIT_CSS`
   —— **它锁的是文本存在，不是浏览器生效** ⇒ 这条守卫一直在给一个**死声明**背书，**所以从没发现 D4**。

#### 13.9.3 🔴 D5 的两层根因（与 D3 同源，Phase 1 独立复现）

| preset | 声明 `--brand-1` | 实测生效 | | preset | 声明 `--brand-2` | 实测生效 |
|---|---|---|---|---|---|---|
| terminal | `#e8a33d` | `#5b53f0` ★ | | terminal | `#b8860b` | `#7c3aed` ★ |
| swiss | `#111111` | `#4f46e5` ★ | | swiss | `#1a56db` | `#7c3aed` ★ |
| aurora | `#6c5ce7` | `#5b53f0` ★ | | aurora | `#5d5fef` | `#7c3aed` ★ |
| ink | `#b03a2e` | `#4f46e5` ★ | | ink | `#1e7762` | `#7c3aed` ★ |
| cyber | `#fcee0a` | `#5b53f0` ★ | | cyber | `#00f0ff` | `#7c3aed` ★ |
| finpro | `#2170ec` | `#5b53f0` ★ | | finpro | `#1f6feb` | `#7c3aed` ★ |

`--card`/`--bg`/`--txt`/`--txt2`/`--border`/`--hold`/`--hover` 同样退化为 classic 基座，
**只有 `--buy`/`--sell` 幸存**。**两层根因**：
1. `ui_kit.py:88` 的 `--brand-1:#4f46e5` 硬覆盖 —— **当前被 D4 意外屏蔽**；修注释会复活它 ⇒ **必须同时删**。
2. `ui_theme.py:223` `dashboard_sf_css()` 自带 `:root{_THEME_ROOT_VARS}`（classic 基座）
   注入晚于 `ui_theme.py:185` 的 `inject_style_css()` ⇒ **这才是真覆盖者**。

⇒ **D4 + D5 必须一起修，只修一个都无效或更糟。**

#### 13.9.4 修法 fixE（Phase 1 已实测，8 组全绿；**取代三选一**）

```
fixE = fixD + 删 _TOKEN_CSS 的 --ss-up/--ss-down 硬覆盖
fixD = fixB + dashboard_sf_css() 的 :root 改为「基座 ∪ preset vars（preset 优先）」
fixB = 修 D4 注释闭合 + 删 _TOKEN_CSS 的 --brand-1/--brand-2 硬覆盖
```
**四步落点（R7：缺一不可）**：`modules/ui_kit.py:86`（修注释）+ `modules/ui_kit.py:88`（删 brand 硬覆盖）
+ `modules/ui_kit.py:45`（删 ss-up/down 硬覆盖）+ `modules/ui_theme.py:223`（`:root` 合并 preset vars）。

**fixE 实测（8 组）**：
```
preset     --brand-1  --card     --txt      --ss-up   --ss-down  --doc-up  --doc-down
classic    #5b53f0    #1a1a2e   #e2e8f0   #ff4d4f   #00d486    #009e60   #dc2626
terminal   #e8a33d ★  #141414 ★ #d4d4d4 ★ #ff5c5c   #3ddc97    #009e60   #dc2626
swiss      #111111 ★  #ffffff   #111111 ★ #d93025   #0f9d58    #009e60   #dc2626
aurora     #6c5ce7 ★  #181a44 ★ #e9ecff ★ #ff5c7a   #2fe0a8    #009e60   #dc2626
ink        #b03a2e ★  #fbf8f1 ★ #2b2b2b ★ #c0392b   #1e7f6b    #009e60   #dc2626
cyber      #fcee0a ★  #101624 ★ #e8f6ff ★ #ff2a6d   #00ff9f    #009e60   #dc2626
finpro     #2170ec ★  #0f1726 ★ #e6edf3 ★ #ff4d4f   #00d486    #009e60   #dc2626
```
⇒ **8 组「红涨绿跌（--ss-*）」+「绿涨红跌（--doc-*）」双语义全部成立**。
**为什么必须删 `_TOKEN_CSS` 的 `--ss-up/--ss-down`**：只做 fixD 时 `--ss-up` 仍全 8 组 = `#ff4d4f`
（preset 的 `#ff5c5c` 等被盖）—— 语义方向仍对，但**风格色仍不生效**。

**R8（守卫升级，非弱化）**：`tests/test_ui_kit_tokens.py:247` 的 `"--brand-1:#4f46e5"` 文本断言
在 fixE 后理应消失 ⇒ **必须改为断言「浏览器生效值」而非「文本存在」**，否则下次还会漏 D4。

#### 13.9.5 新增可 grep 验收项

```bash
# D4：CSS 注释提前闭合不得回潮
! grep -nE '\-\-[a-z0-9-]+-\*/' modules/ui_kit.py
# D5-a：_TOKEN_CSS 不得硬写主题层令牌
! grep -nE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#' modules/ui_kit.py
# D5-b：dashboard_sf_css 的 :root 必须合并 preset vars
grep -n 'STYLE_PRESETS' modules/ui_theme.py
# 价格域红线（8 组恒成立）
grep -q -- '--doc-up:#009e60' modules/ui_theme.py && grep -q -- '--doc-down:#dc2626' modules/ui_theme.py
```

#### 13.9.6 依赖约束与两条新增诚实边界

- ⚠️ **`tinycss2` 只在 `E:\python\lib\site-packages`，不在项目 `.venv`**
  ⇒ `tests/test_style_token_cascade.py` **本轮只做静态文本断言**（上节 grep 类），
  **探针固化（tinycss2 解析 + 复刻注入序列 + 按序求最终值）推到下一轮**；是否把 tinycss2 加入项目依赖需另行决策。
- ⚠️ **fixE 后 6 套风格视觉外观会变**（terminal 琥珀 → 现在终于是琥珀，此前一直是经典紫）
  ⇒ **可见变更**，需截图基线对比 + **逐风格目检**。
- ⚠️ **fixE 后 terminal/aurora/cyber 的 `--card`/`--txt` 变为 preset 值 ⇒ 对比度必须重算**
  （8 组矩阵对比度项从「未算」升级为「必须算」）。

#### 13.9.7 Phase 1 其余交付项的修订（以本条为准）

| Phase 1 原文 | 修订 |
|---|---|
| 「暗/浅 × 4 套主题 = 12 组矩阵」 | **7 套 `STYLE_PRESETS`**（classic/terminal/swiss/aurora/ink/cyber/**finpro**），**可达 8 组** |
| D2「6 套风格价格域回落继承色」 | **撤回**（8 组实测全部成立） |
| 「`starfield_theme.py` 整文件列 P2 删除候选」 | **收窄** —— 模块不可删（`stock_research.py:1419` + `pages/53:40` 真实引用）；仅 `STARFIELD_CSS` + 11 个渲染函数是死代码 |
| 原验收项 O（「--doc-up 在 6 套风格下有定义」→ 缺失） | **删除**（前提不成立），替换为 §13.9.5 的 D4/D5 验收项 |
| §1c「`.sf-pill.up` 绿底红字」 | **不变**，但影响面收窄：因 `--buy` 在 6 套下被覆盖为 preset 值 ⇒ 串色只在 **classic 暗色**出现；classic 亮色 `--buy` 仍未定义。**结论与修法均不变** |
| 其余 42 个 token 映射表、11 个死代码清单、#40/#41 裁定、风险分级 | **不变** |
### 13.10 C0 批次定稿：fixF（合并路线）+ 🔴 D6 缓存键（Phase 1 最终态）

> Phase 1 收到 Phase 2 修订后做了独立复核（tinycss2 规范解析 + 复刻 `render_standard_page` 真实注入序列）。
> **本条为 C0 的定稿方案。**

#### 13.10.1 ⚠️ 缺陷编号第三次统一（务必以本条为准）

| 现编号 | 缺陷 | 提出者 | 级别 |
|---|---|---|---|
| D3 | `:root` 级联倒挂（`dashboard_sf_css` 的经典 `:root` 注入晚于 preset vars） | Phase 2 | 🔴 |
| **D4** | `modules/ui_kit.py:86` CSS 注释提前闭合 ⇒ `--brand-1` 声明被浏览器丢弃 | Phase 1 | 🔴 |
| **D5** | 6 套非 classic 风格的 `vars` 全未生效（**D3 + D4 的合并结果**，与 D3 同根因） | Phase 1 | 🔴 |
| **D6** | **`dashboard_sf_css()` 缓存键只有 `dark` ⇒ 切风格后仪表盘层静默不更新** | Phase 1 | 🔴 |
| **D7** | `modules/page_utils.py:124` 休市胶囊对比度 ≈ 2.2:1 | Phase 2 | 🟡 |
| **D8** | `--doc-up`/`--doc-down` 小号场景对比度不达标 | Phase 2 | 🟡 |
| ~~D2~~ | ~~6 套风格价格域回落继承色~~ | — | **已撤回** |

> ⚠️ §13.8 的「D4/D5」= 现 **D7/D8**；§13.9 的「D6/D7」= 现 **D7/D8**，且现 **D6** 是缓存键。

#### 13.10.2 🔴 D6（此前无人发现的第 5 阻塞点）：缓存键只有 `dark`

`modules/ui_theme.py:191 / 219 / 502`：
```python
_DASHBOARD_SF_CSS_CACHE: dict = {}
_cached = _DASHBOARD_SF_CSS_CACHE.get(dark)      # ← 键只有 dark 布尔
_DASHBOARD_SF_CSS_CACHE[dark] = _css
```
**实测**：同 mode 下先 classic 再 terminal → `dashboard_sf_css()` **返回同一个对象（`is` 判定 True）**。
⇒ 一旦 `:root` 引入 preset vars，**缓存键必须改成 `(dark, style)`**，否则用户切风格后仪表盘层仍返回
**上一个风格**的 CSS ⇒ **风格切换对仪表盘层无效，且不报错**。
⇒ **与 D4 同类病：「看起来生效、实际没生效」。**

#### 13.10.3 修法 fixF（合并路线）取代 fixE（替换路线）

- **fixE（替换）**：`:root` 只取 preset vars ⇒ 基座的 `--doc-up/--doc-down` 消失 ⇒ 6 套 preset 必须补
  （Phase 2 实测：替换下 7 套全丢）
- **fixF（合并）**：`:root{基座 ∪ preset vars（preset 优先）}` ⇒ **基座永远提供 `--doc-up/--doc-down`**，
  preset 只覆盖自己声明的键 ⇒ **`--doc-up` 8 组全部存活，且 6 套 preset 零改动**

⇒ **Phase 1 修正了 Phase 2 的一个推论**：「D3 修好后 D2 显形」**仅当修法是「替换」才成立**；
合并语义下 8 组全存活。⇒ 「fixF 后 7 套风格价格域全丢」**不成立**；
但 **AC-0.4（8 组都有 `--doc-up/--doc-down`）仍要保留为防回归护栏**。

**fixF 五步（缺一不可；Phase 1 实测三个半成品变体全部证明必须整批）**：
| 步 | 位置 | 动作 | 不做会怎样 |
|---|---|---|---|
| 1 | `ui_kit.py:86` | 修 CSS 注释提前闭合（`--ss-*/` → `--ss-* /`） | **`--brand-1` 继续被浏览器丢弃**（D4 不修，后续都是假修） |
| 2 | `ui_kit.py:88` | 删 `--brand-1:#4f46e5; --brand-2:#7c3aed;` 硬覆盖 | 步 1 会让它复活 ⇒ 8 组统一经典紫，**比现状更糟** |
| 3 | `ui_kit.py:45` | 删 `--ss-up:#ff4d4f; --ss-down:#00d486;` 硬覆盖 | `--ss-up` 仍 8 组统一 `#ff4d4f`（语义方向对但风格色不生效） |
| 4 | `ui_theme.py:223` | `:root` 改为 **`基座 ∪ preset vars`（合并，非替换）** | **preset vars 永不生效**（D5 的真覆盖者） |
| 5 | `ui_theme.py:219/502` | 缓存键 `(dark)` → `(dark, style)` | **切风格后仪表盘层不更新（静默）** |

实测三个半成品变体：只做步 1 ⇒ `--brand-1` 8 组全变 `#4f46e5`（**更糟**）；只做步 1+2 ⇒ `--brand-1`
**完全不变**（覆盖者是步 4）；只做步 4 但用「替换」⇒ `--doc-up` 7 套全丢。

**fixF 实测 8 组矩阵（全绿）**：
```
preset     --brand-1  --brand-2  --card     --bg      --txt      --ss-up   --ss-down  --doc-up  --doc-down
classic    #5b53f0    #7f3df0    #1a1a2e   #0f0f23   #e2e8f0   #ff4d4f   #00d486    #009e60   #dc2626
terminal   #e8a33d ★  #b8860b ★  #141414 ★ #0a0a0a ★ #d4d4d4 ★ #ff5c5c   #3ddc97    #009e60   #dc2626
swiss      #111111 ★  #1a56db ★  #ffffff   #ffffff   #111111 ★ #d93025   #0f9d58    #009e60   #dc2626
aurora     #6c5ce7 ★  #5d5fef ★  #181a44 ★ #101334 ★ #e9ecff ★ #ff5c7a   #2fe0a8    #009e60   #dc2626
ink        #b03a2e ★  #1e7762 ★  #fbf8f1 ★ #f7f3ea ★ #2b2b2b ★ #c0392b   #1e7f6b    #009e60   #dc2626
cyber      #fcee0a ★  #00f0ff ★  #101624 ★ #0a0e17 ★ #e8f6ff ★ #ff2a6d   #00ff9f    #009e60   #dc2626
finpro     #2170ec ★  #1f6feb ★  #0f1726 ★ #0a1020 ★ #e6edf3 ★ #ff4d4f   #00d486    #009e60   #dc2626
```
⇒ **8 组「红涨绿跌（`--ss-*`）」+「绿涨红跌（`--doc-*`）」双语义全部成立**；
**缓存键实测：换风格返回不同对象 ✓**；**4 条守卫文本实测仍在**（`绿涨红跌` / `--doc-up:#009e60` /
`--doc-down:#dc2626` / `--bg:#0f0f23` 全 True）。

**C0 范围**：`modules/ui_kit.py`（3 处）+ `modules/ui_theme.py`（2 处）+
`tests/test_ui_kit_tokens.py`（守卫升级 1 处）= **5 文件，单一原子 commit**。
**R8 守卫升级**：`test_ui_kit_tokens.py:247` 的 `"--brand-1:#4f46e5"` 文本断言
⇒ 必须改为断言「**浏览器生效值**」而非「文本存在」（**它锁文本不锁生效值，正是它没发现 D4 的原因**）。

#### 13.10.4 D8：对比度（Phase 1 独立复算，比 Phase 2 多报了一半）

| 组 | `--doc-up` 4.5 | `--doc-down` 4.5 | 3:1 |
|---|---|---|---|
| classic/dark | 5.44 ✓ | **3.91 ✗** | 全过 |
| classic/light | **3.47 ✗** | 4.83 ✓ | 全过 |
| terminal/dark | 5.71 ✓ | **4.10 ✗** | 全过 |
| swiss/light | **3.47 ✗** | 4.83 ✓ | 全过 |
| aurora/dark | 5.20 ✓ | **3.73 ✗** | 全过 |
| ink/light | **3.13 ✗** | **4.36 ✗** | 全过 |
| cyber/dark | 5.57 ✓ | **4.00 ✗** | 全过 |
| finpro/dark | 5.47 ✓ | **3.92 ✗** | 全过 |

⇒ **`--doc-up` 3/8 组不达标；`--doc-down` 6/8 组不达标**（Phase 2 只报了 `--doc-up` 3 组，
**`--doc-down` 这一半此前无人报**）。3:1 大字阈值 8 组全过。

**判定关键 = 实际渲染字号（比数值本身更重要）**：
| 使用点 | 实际字号 | WCAG 判定 | 阈值 | 结论 |
|---|---|---|---|---|
| `stock_research.py:529/531/533` `sf-metric-card .value`（`ui_theme.py:412` 22px/700） | 22px/700 | **大字** | 3:1 | ✓ 全过 |
| `:562` `sf-doc-down`「压制」（`sf-perspective-card .body`，`ui_theme.py:416` 14px） | **14px/400** | **正文** | 4.5 | ✗ |
| `:567` `sf-doc-up` MA5/MA10（body 内 `<b>`） | **14px/700** | **正文**（14px < 18.66px，**加粗也救不了**） | 4.5 | ✗ |

⇒ **「大小字二分」不足以解决**（`--doc-down` 6/8 组仍不达标）⇒ **必须新增别名派生令牌**
`--doc-up-text` / `--doc-down-text`（如 `color-mix(in srgb,var(--doc-up) 80%,black)`），
**不得改 `--doc-up:#009e60` 字面值**（3 守卫硬锁：`test_no_hardcoded_semantic_hex.py:54`、
`test_ui_theme.py:60,69`、`test_stock_research_semantics.py:98`）。
⚠️ **`--doc-up-text` 的具体加深比例未测算**（Phase 1 只给派生方向）⇒ 需实测测算。

#### 13.10.5 保留原名的族最终为 4 族 + `sf-chart`/`sf-kline`

| 族 | 位置 | 理由 |
|---|---|---|
| `sf-btn-*` | `button_colors.py` | `test_whitebox_button_colors.py:23-55` 硬锁 |
| `sf-text-*` + `sf-chip*` | `dark_text_fix.py` | `test_dark_text_fix.py:52` 硬锁 |
| `sf-scroll-*` | `scroll_nav.py` | `test_scroll_nav.py:56-130` 硬锁 |
| **`sf-chart` + `sf-kline`** | `starfield_theme.py:103/109` | **是 `div_id` 不是 class** ⇒ 改名会破坏 JS/echarts DOM 定位 |

⇒ 仪表盘族 9 个有外部 class 引用者（alert/brand/card/disclaimer/header/table/tag/vs/vsbox）
随规则一起迁 `xc-*`；`STARFIELD_CSS` 整体可删（生产不注入）。

#### 13.10.6 C0 的可 grep 验收项（定稿版）

```bash
# D4 注释提前闭合不得回潮
! grep -nE '\-\-[a-z0-9-]+-\*/' modules/ui_kit.py
# _TOKEN_CSS 不得硬写主题层令牌
! grep -nE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#' modules/ui_kit.py
# :root 必须合并（基座 + preset vars），不能只用 preset
grep -q '_THEME_ROOT_VARS' modules/ui_theme.py
grep -qE 'STYLE_PRESETS\.get\(.*\)\.get\(.vars.\)' modules/ui_theme.py
# 缓存键必须含 style
grep -qE '_DASHBOARD_SF_CSS_CACHE\.get\(\(dark' modules/ui_theme.py
# 价格域红线（8 组恒成立）
grep -q -- '--doc-up:#009e60' modules/ui_theme.py && grep -q -- '--doc-down:#dc2626' modules/ui_theme.py
grep -q -- '--ss-up:#ff4d4f' modules/colors.py && grep -q -- '--ss-down:#00d486' modules/colors.py
# classic zero-op 守卫不破
grep -q "STYLE_PRESETS\[.classic.\]\[.vars.\] == " tests/test_ui_theme_styles.py
# 绿涨红跌注释仍在
grep -q '绿涨红跌' modules/ui_theme.py
```

#### 13.10.7 诚实边界

- **fixF 会改变 6 套风格的可见外观**（terminal 此前一直是经典紫，修后终于是琥珀）
  ⇒ **必须做截图基线对比 + 逐风格目检**（不能只看 classic）。
- **未做完整 WCAG 全量对比**（只算了 `--doc-up`/`--doc-down` 对 `--bg`，未覆盖 `--txt`/`--border`/`--hold`）
  ⇒ 验证矩阵里的对比度重算**必须覆盖全部令牌对**。
- ⚠️ **`tinycss2` 只在 `E:\python\lib\site-packages`，不在项目 `.venv`**
  ⇒ `tests/test_style_token_cascade.py` 本轮只做静态文本断言 + 8 组矩阵人工验收表；探针固化推下一轮。
- **D4 未在真实浏览器确认**（tinycss2 与浏览器同源实现，CSS 注释终止规则是规范硬定义，风险低，
  但建议 Phase 3 补一次 DevTools 确认）。
### 13.11 C0 最终定稿：fixG（fixF ∪ fixE+ 第④步 = 6 步）+ 编号第四次统一

> Phase 1 与 Phase 2 各自用 tinycss2 独立复现了对方的结论，分歧全部收敛。
> **Phase 2 主动认错**：其上一版探针**用正则提取 `:root{}` 文本、不做 CSS 词法解析**
> ⇒ 把「文本存在但浏览器丢弃」的声明误算成生效 ⇒ 矩阵数值全错（已更正，见 §13.11.4）。
> **主理人综合判定：两位成员的方案互补而非冲突 ⇒ 合并为 fixG（6 步）。**

#### 13.11.1 fixG 六步（缺一不可）

| 步 | 位置 | 动作 | 不做会怎样 | 来源 |
|---|---|---|---|---|
| 1 | `modules/ui_kit.py:86` | 修 CSS 注释提前闭合（`--ss-*/` → `--ss-* /`） | **`--brand-1` 继续被浏览器丢弃**（D4 不修，后续都是假修） | 两人一致 |
| 2 | `modules/ui_kit.py:88` | 删 `--brand-1:#4f46e5; --brand-2:#7c3aed;` 硬覆盖 | 步 1 会让它复活 ⇒ 8 组统一经典紫，**比现状更糟** | 两人一致 |
| 3 | `modules/ui_kit.py:45` | 删 `--ss-up:#ff4d4f; --ss-down:#00d486;` 硬覆盖 | `--ss-up` 仍 8 组统一 `#ff4d4f`（语义方向对但风格色不生效） | 两人一致 |
| 4 | `modules/ui_theme.py:219/502` | 缓存键 `(dark)` → `(dark, style)` | **切风格后仪表盘层静默不更新**（D6） | **Phase 1 独有** |
| 5 | `modules/ui_theme.py:223` | `:root` 改为 **`基座 ∪ preset vars`（合并，非替换）** | **preset vars 永不生效**（D5 的真覆盖者） | 两人一致 |
| 6 | `modules/ui_theme.py:196` `_THEME_ROOT_VARS['light']` | **补 `--buy:#ff4d4f; --sell:#00d486;`** | **classic 亮色 `var(--buy)` 未定义 ⇒ `.sf-pill.up{color:var(--buy)}` 整条声明 invalid at computed-value time ⇒ 回落 inherit ⇒ D1 亮色侧仍红** | **Phase 2 独有（两人原本都漏）** |

⇒ **步 4 与步 6 是两位成员各自的独家发现，缺任一步都留下一个静默失效点。**

#### 13.11.2 一处真冲突 + 主理人裁定

Phase 2 的 AC-0.2.b 注释「`--brand-2:#7c3aed` 允许保留（浏览器里生效，且非风格色）」
vs Phase 1 的步 2「一并删」。

⇒ **主理人裁定：一并删。** 理由：① `#7c3aed` 是**通用紫**，不属于任何风格的品牌色，留着会让
**未声明 `--brand-2` 的风格拿到错色**；② Phase 1 实测删掉后 classic 的 `--brand-2` 反而变成
**`#7f3df0`**（classic 自己的定义）⇒ 删掉更准确。
⇒ 验收项相应改为 **四个 token 全 0 命中**（含 `--brand-2`）。

#### 13.11.3 根因归属（两层，缺一不可）

| 层 | 位置 | 作用 |
|---|---|---|
| 层 1 | `ui_kit.py:86` 注释提前闭合 ⇒ `:88` 的 `--brand-1:#4f46e5` **被解析错误丢弃** | **当前被意外屏蔽**；⚠️ **只修注释会复活它** ⇒ 修注释必须同时删这行 |
| 层 2 | `ui_theme.py:223` `dashboard_sf_css()` 自带 `:root{_THEME_ROOT_VARS}`（classic 基座），注入晚于 `ui_theme.py:185` 的 `inject_style_css()` | **真正的覆盖者** |

⇒ 修法**必须用「合并」语义**（`:root{基座 ∪ preset vars，preset 优先}`），**不得用「替换」**。

#### 13.11.4 矩阵数值更正（Phase 2 认错后）

```
风格/主题            --brand-1  --card   --txt    --ss-up  --ss-down --doc-up  preset 声明
[classic/dark ]      #5b53f0   #1a1a2e  #e2e8f0  #ff4d4f  #00d486  #009e60  (classic 无)
[classic/light]      #4f46e5   #ffffff  #1e293b  #ff4d4f  #00d486  #009e60  (classic 无)
[terminal/dark ]     #5b53f0   #1a1a2e  #e2e8f0  #ff4d4f  #00d486  #009e60  #e8a33d ⚠被覆盖
[swiss/light  ]      #4f46e5   #ffffff  #1e293b  #ff4d4f  #00d486  #009e60  #111111 ⚠
[aurora/dark  ]      #5b53f0   #1a1a2e  #e2e8f0  #ff4d4f  #00d486  #009e60  #6c5ce7 ⚠
[ink/light    ]      #4f46e5   #ffffff  #1e293b  #ff4d4f  #00d486  #009e60  #b03a2e ⚠
[cyber/dark   ]      #5b53f0   #1a1a2e  #e2e8f0  #ff4d4f  #00d486  #009e60  #fcee0a ⚠
[finpro/dark  ]      #5b53f0   #1a1a2e  #e2e8f0  #ff4d4f  #00d486  #009e60  #2170ec ⚠
```
⇒ 暗色 6 组是 `#5b53f0`（classic dark 基座），亮色 3 组是 `#4f46e5`（classic light 基座）。
⇒ fixG 后应全部变成 preset 自己的值。
⚠️ **`finpro` 的 `--ss-up` 修完仍 `#ff4d4f`** —— 因为 **finpro 的 vars 本身就没有 `--ss-up/--ss-down`**
（实测）⇒ 属**既有状态，非 fixG 缺口**，不得写进验收失败项。

#### 13.11.5 D2 的最终口径（两人一致）

- **D2 当前症状实测不成立**（8 组 `--doc-up`/`--doc-down` 全对）
- 在 **fixG 的合并语义下不会显形**（基座 `:root` 仍在）⇒ §13.10 提到的「fixF 后 7 套价格域全丢」**不成立**
- 但「D2 依赖基座存活」这个**结构性脆弱点依然成立** ⇒ **AC-0.4 必须保留**
  （8 组 `--doc-up` 有定义且 `== #009e60`），把「将来有人把基座 `:root` 整个删掉」变成可拦截项。

#### 13.11.6 AC-0.2 定稿（a~f 六条，.b 已按裁定改）

```bash
# .a 注释提前闭合不得回潮
! grep -rnE '\-\-[a-zA-Z0-9_-]+-\*/' --include="*.py" modules/ pages/ app.py
# .b _TOKEN_CSS 不得硬写主题层令牌（★四个 token 全 0 命中，含 --brand-2）
! grep -nE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#' modules/ui_kit.py
# .c 解析层：_TOKEN_CSS 的 :root 不得有解析错误（需 tinycss2，本轮不做）
# .d :root 必须合并 preset vars
grep -q 'STYLE_PRESETS' modules/ui_theme.py
# .e 价格域 + 交易语义红线
grep -q -- '--doc-up:#009e60' modules/ui_theme.py && grep -q -- '--doc-down:#dc2626' modules/ui_theme.py
grep -q -- '--ss-up:#ff4d4f' modules/colors.py && grep -q -- '--ss-down:#00d486' modules/colors.py
# .f ★新增：classic 亮色 --buy/--sell 必须有定义（fixG 步 6）
grep -q -- '--buy:#ff4d4f' modules/ui_theme.py && grep -q -- '--sell:#00d486' modules/ui_theme.py
# 缓存键必须含 style（fixG 步 4）
grep -qE '_DASHBOARD_SF_CSS_CACHE\.get\(\(dark' modules/ui_theme.py
# classic zero-op 守卫不破
grep -q "STYLE_PRESETS\[.classic.\]\[.vars.\] == " tests/test_ui_theme_styles.py
# 绿涨红跌注释仍在
grep -q '绿涨红跌' modules/ui_theme.py
```

#### 13.11.7 守卫升级（R8）

`tests/test_ui_kit_tokens.py:243-256`（`test_token_aliases_bound_to_existing`）断言 `_KIT_CSS` 的
**原始文本**含 `--brand-1:#4f46e5` ⇒ **它一直在「绿」而浏览器丢弃了这条声明** ⇒ 这正是它没拦住
注释 bug 的原因。⇒ fixG 后该断言会红，属**「守卫需同步升级」而非弱化**：应改为断言令牌在
**其生效位置**存在（如 `ui_theme._THEME_ROOT_VARS['light']` 的 `--brand-1:#4f46e5`）。
📌 `modules/ui_kit.py:121-134` 的 `_build_token_css()`（`:130` 也返回 `--brand-1:#4f46e5`）
**生产零调用** ⇒ 不影响运行时，但需标注为「同源死代码，可留可清（清则须同步 `:130`）」。

#### 13.11.8 C0 定稿范围与风险

**C0 = fixG 6 步 + 守卫升级** = `modules/ui_kit.py`(3 处) + `modules/ui_theme.py`(3 处)
+ `tests/test_ui_kit_tokens.py`(1 处) + `tests/test_a11y_contrast.py`（改级联口径）
= **5 文件，单一原子 commit**。

- **最大风险**：fixG 后 6 套风格从「`extra` 硬编码撑起来的假象」变成「**真正按 vars 生效**」
  ⇒ **视觉会明显变化，可能是这 6 套风格第一次真正呈现其设计意图** ⇒ **必须逐风格目检，不能只看 classic**。
- **对比度**：fixG **不解决** D5（`--doc-up` 在 classic-light / swiss-light / ink-light 三组仍 < 4.5）
  ⇒ **D5 独立留在 C3**（需新增 `--doc-up-text` / `--doc-down-text` 别名派生令牌，
  **不得改被 3 守卫锁定的 `--doc-up:#009e60` 字面值**）。
- ⚠️ `tinycss2` 不在项目 `.venv` ⇒ 解析层守卫（AC-0.2.c）本轮不做，探针固化推下一轮。
### 13.12 Phase 1 / Phase 2 定稿：三方共识 + 主理人 3 条修正与 2 处裁定

> Phase 1 与 Phase 2 的 **10 条分歧全部收敛** ⇒ **fixG 六步 + R8 守卫升级是三方共识**。
> 本章记录定稿增量、**3 条修正**（含一条「验收项假红」）与**2 处主理人裁定**。

#### 13.12.1 Phase 1 找到自己探针的盲区（这正是 fixG 第 6 步的来源）

Phase 1 的探针循环写成 `theme = p.get('mode') or 'dark'`，而 **classic 的 `mode` 是 `None`**
⇒ **classic/light 这一格从未被测过** ⇒ 正是这一格命中 `--buy/--sell` UNDEF
⇒ **Phase 1 独立补上了自己漏的那一步**（classic 亮色补 `--buy/--sell`）。

#### 13.12.2 ⚠️ 修正 1：验收项 ⑥ 的原写法是**假红**

`grep -- '--ss-up:#ff4d4f' modules/colors.py` **永远不命中** —— `modules/colors.py` 是
**【常量形态】**（`UP_COLOR = "#ff4d4f"` / `DOWN_COLOR = "#00d486"`），**不是** `--ss-up:` 形态。
⇒ **正确写法**：
```bash
grep -q 'UP_COLOR = "#ff4d4f"' modules/colors.py && grep -q 'DOWN_COLOR = "#00d486"' modules/colors.py
```
⇒ 交易语义真值源在 **`modules/colors.py` 的常量**，不在 `--ss-*` 形态的 CSS 里。

#### 13.12.3 ⚠️ 修正 2：`--brand-2` 必须一起删（理由更新 —— Phase 1 证伪了我的原理由）

我上一条裁定的理由是「`#7c3aed` 是通用紫、非任何风格品牌色」——**Phase 1 实测证伪了这个理由**
（**结论不变，理由要换**）：
- **6 套 preset 全都声明了不同值的 `--brand-2`**：terminal `#b8860b` / swiss `#1a56db` /
  aurora `#5d5fef` / ink `#1e7762` / cyber `#00f0ff` / finpro `#1f6feb`
  ⇒ **它就是风格色**，不是通用紫。
- **机制**（与 D4 的解析错误无关）：
  ```
  page_utils.py:57 → dashboard_sf_css()            → :root{基座 ∪ preset vars}   ← preset 的 --brand-2
  page_utils.py:60 → page_hero() → inject_kit_css() → _KIT_CSS = _TOKEN_CSS + …    (ui_kit.py:137)
  page_utils.py:60 → page_hero() → _HERO_FALLBACK_CSS = _TOKEN_CSS + …            (ui_kit.py:390) ← 最后注入者胜
  ```
  `_TOKEN_CSS` 在 `page_hero` 时**最后注入** ⇒ 它的 `--brand-2:#7c3aed` **覆盖** preset 的值。
- **保留 = 引入「preset 声明了但没生效」的静默缺陷**（与 D4 / D6 同类）。
- **消费者很实**：`modules/session.py:687/696/703/710/717/750`（登录页渐变）、
  `modules/ui_kit.py:47`（`--ss-accent2`）、`modules/ui_theme.py:235/243`（卡片竖条渐变）
  ⇒ **6 套风格的渐变会全部同质化成经典紫**（可见但不报错，最难发现的那类）。

#### 13.12.4 裁定 A：**一并清 `modules/ui_kit.py:130`**（推翻 Phase 1 的「C0 不动」建议）

Phase 1 建议「`_build_token_css()` 生产零调用，C0 不动、留作独立清理项（避免扩大改动面）」。
⇒ **主理人裁定：一并清。** 理由：① **验收项 ② 要求四个 token 全 0 命中** ⇒ 留 `:130`（它同样产
`--brand-1:#4f46e5` / `--brand-2:#7c3aed`）则该验收项**必红**，要么开特例（脆弱）要么违背其目的；
② 它是**同源死代码**（同一常量族、同样被注释 bug 污染的写法），留着会让下一个人再踩；
③ 改动是**删两行死代码**、`_build_token_css` 生产零调用 ⇒ **回归面几乎为零**，不构成「扩大改动面」。

⇒ **C0 范围 = 5 文件**：`modules/ui_kit.py`（`86`/`88`/`45`/`130`）+
`modules/ui_theme.py`（`196`/`223`/`219+502`）+ `tests/test_ui_kit_tokens.py`（1 处）+
`tests/test_a11y_contrast.py`（改级联口径）。

#### 13.12.5 裁定 B：守卫升级写法（采纳 Phase 1，**注意 dark/light 值不同**）

```python
assert "--brand-1:#4f46e5" not in kit._KIT_CSS, "组件层不得硬写主题层 --brand-1"
assert "--brand-2:#7c3aed" not in kit._KIT_CSS, "组件层不得硬写主题层 --brand-2"
assert "--brand-1:#4f46e5" in ut._THEME_ROOT_VARS["light"]   # light 基座
assert "--brand-1:#5b53f0" in ut._THEME_ROOT_VARS["dark"]    # dark 基座
```
⇒ 这是「**锁归属 + 锁不越权**」：组件层不得硬写主题层令牌；主题层基座必须自带。

#### 13.12.6 修正 3：D5 范围要扩到**两组**

`--ss-up` 在 **classic/light 仅 3.27（<4.5）** —— 交易屏涨跌色用于 13px 正文同样不合格。
⇒ **D5 = `--doc-up-text` / `--doc-down-text` ＋ `--ss-up-text` / `--ss-down-text`**，
明确留 **C3**（fixG 不解决对比度）。

#### 13.12.7 fixG 后的 8 组期望值表（定稿，含 `--brand-2` 与 `--buy/--sell`）

```
preset/theme  --brand-1  --brand-2  --card   --bg      --txt      --ss-up   --ss-down  --buy      --sell     --doc-up  --doc-down
classic/dark  #5b53f0   #7f3df0    #1a1a2e  #0f0f23  #e2e8f0   #ff4d4f   #00d486   #ff4d4f   #00d486   #009e60   #dc2626
classic/light #4f46e5   #7c3aed    #ffffff  #ffffff  #1e293b   #ff4d4f   #00d486   #ff4d4f   #00d486   #009e60   #dc2626
terminal/dark #e8a33d   #b8860b    #141414  #0a0a0a  #d4d4d4   #ff5c5c   #3ddc97   #ff5c5c   #3ddc97   #009e60   #dc2626
swiss/light   #111111   #1a56db    #ffffff  #ffffff  #111111   #d93025   #0f9d58   #d93025   #0f9d58   #009e60   #dc2626
aurora/dark   #6c5ce7   #5d5fef    #181a44  #101334  #e9ecff   #ff5c7a   #2fe0a8   #ff5c7a   #2fe0a8   #009e60   #dc2626
ink/light     #b03a2e   #1e7762    #fbf8f1  #f7f3ea  #2b2b2b   #c0392b   #1e7f6b   #c0392b   #1e7f6b   #009e60   #dc2626
cyber/dark    #fcee0a   #00f0ff    #101624  #0a0e17  #e8f6ff   #ff2a6d   #00ff9f   #ff2a6d   #00ff9f   #009e60   #dc2626
finpro/dark   #2170ec   #1f6feb    #0f1726  #0a1020  #e6edf3   #ff4d4f   #00d486   #ff4d4f   #00d486   #009e60   #dc2626
```
⇒ **红涨绿跌（`--ss-up` R>G / `--ss-down` G>R）+ 绿涨红跌（`--doc-*`）双语义 8 组全部成立，
且全部令牌有定义（无 UNDEF）。**

#### 13.12.8 C0 验收项定稿（Phase 1 版 + 主理人修正）

```bash
# ① D4 注释提前闭合不得回潮
! grep -rnE '\-\-[a-z0-9-]+-\*/' --include="*.py" modules/ pages/ app.py
# ② _TOKEN_CSS 不得硬写主题层令牌（--brand-2 也要删）
! grep -nE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#' modules/ui_kit.py
# ③ :root 必须合并 preset vars（★「合并 vs 替换」的唯一静态判据；_THEME_ROOT_VARS 一直存在，不能证明合并）
grep -q 'STYLE_PRESETS' modules/ui_theme.py
# ④ classic 亮色 --buy/--sell 必须有定义
grep -q -- '--buy:#ff4d4f' modules/ui_theme.py && grep -q -- '--sell:#00d486' modules/ui_theme.py
# ⑤ 缓存键必须含 style
grep -qE '_DASHBOARD_SF_CSS_CACHE\.get\(\(dark' modules/ui_theme.py
# ⑥ 交易语义真值源（★ colors.py 是【常量形态】，上一版写法永远红）
grep -q 'UP_COLOR = "#ff4d4f"' modules/colors.py && grep -q 'DOWN_COLOR = "#00d486"' modules/colors.py
# ⑦ 价格域红线
grep -q -- '--doc-up:#009e60' modules/ui_theme.py && grep -q -- '--doc-down:#dc2626' modules/ui_theme.py
# ⑧ classic zero-op + 「绿涨红跌」注释不破
grep -q "STYLE_PRESETS\[.classic.\]\[.vars.\] == " tests/test_ui_theme_styles.py
grep -q '绿涨红跌' modules/ui_theme.py
```

#### 13.12.9 一处数据残留不一致（已统一）

Phase 1 最终态表格里「#41 真实缺口 = `_EMOJI_MAP` 覆盖 **16/65**」是**旧数字**。
ux-designer 的 AST 实测：**导航条目 63 条 / 未收录 47 个 / `_EMOJI_MAP` 实际 53 条 / 需新增约 43 个 path**。
⇒ **以 63 / 47 / 53 / 约 43 为准**。

#### 13.12.10 探针与依赖的处置

- Phase 1 的探针在 `$TEMP/probe*.py`，**未落仓库** ⇒ 整理为**人工验收脚本**给 Phase 3，
  但**不放进仓库**（`tinycss2` 不在项目 `.venv`）。
- ⇒ **「tinycss2 进项目 .venv」列为 C0 的显式前置动作**：否则解析层守卫（AC-0.2.c + 8 组探针）
  永远进不了 CI。
- ⚠️ `sf-chart` / `sf-kline` 实锤（`starfield_theme.py:103-107`）：
  `var el = document.getElementById('{div_id}'); var chart = echarts.init(el);`
  ⇒ **改名会直接打断 ECharts 初始化** ⇒ 确认为第 4 个「保留名字」族。
### 13.13 Phase 2 最终定稿：三方完全一致（Phase 2 撤回自己的两条错误）

> Phase 2 最终版**主动撤回**两条错误：①「`--brand-2` 允许保留」②「`colors.py` 里 grep `--ss-up:` 形态」。
> ⇒ **Phase 1 / Phase 2 / 主理人 三方对 fixG 六步 + 守卫 G + 8 组期望值表 + AC-0.2 ①~⑧ + 32 文件回归集完全一致。**

#### 13.13.1 变体对比实测：证明「一起删」是唯一正确解

| 组 | preset 声明 | A：只删 brand-1 | B：一起删 | 判定 |
|---|---|---|---|---|
| classic/dark | （基座） | `#7c3aed` | `#7f3df0` | A=✓ B=✓ |
| classic/light | （基座） | `#7c3aed` | `#7c3aed` | A=✓ B=✓ |
| terminal/dark | `#b8860b` | `#7c3aed` ★不符 | `#b8860b` | A=✗ B=✓ |
| swiss/light | `#1a56db` | `#7c3aed` ★不符 | `#1a56db` | A=✗ B=✓ |
| aurora/dark | `#5d5fef` | `#7c3aed` ★不符 | `#5d5fef` | A=✗ B=✓ |
| ink/light | `#1e7762` | `#7c3aed` ★不符 | `#1e7762` | A=✗ B=✓ |
| cyber/dark | `#00f0ff` | `#7c3aed` ★不符 | `#00f0ff` | A=✗ B=✓ |
| finpro/dark | `#1f6feb` | `#7c3aed` ★不符 | `#1f6feb` | A=✗ B=✓ |

⇒ **变体 A 会让 6 套风格的次品牌色全部退化成经典紫 `#7c3aed`，preset 声明全部失效** ⇒ **必须一起删**。
**机制确认**：`_KIT_CSS = _TOKEN_CSS + …`（`ui_kit.py:137`）、`_HERO_FALLBACK_CSS = _TOKEN_CSS + …`（`:390`）
⇒ **`page_hero()`（`page_utils.py:60`）会让 `_TOKEN_CSS` 最后注入** ⇒ 其 `--brand-2` 覆盖 preset 值。
⚠️ Phase 2 的注入序模拟**漏了「`page_hero` 重复注入 `_TOKEN_CSS`」这一环** ⇒
**实施时的注入序建模必须包含这一环**，否则会低估 `_TOKEN_CSS` 的覆盖力。

#### 13.13.2 D5 的 `--ss-up/--ss-down` 字号实测（一次覆盖两组）

```
ui_kit.py:199  .ss-stat .delta{font-size:13px;font-weight:600}  → 正文 ✗
ui_kit.py:268  .xc-card .delta{font-size:13px;font-weight:700}   → 正文 ✗（13px<18.66px，加粗救不了）
ui_kit.py:272  .xc-card .value.up                               → 继承 22px/800 → 大字 ✓
ui_kit.py:276  .xc-card .meta .up                               → 继承 11px → 正文 ✗
ui_kit.py:163  .ss-pill.open .dot                              → 非文本圆点 ≥3.0 ✓
```
⇒ **classic/light 的 `--ss-up` = 3.27 不达标** ⇒ **D5 一次性覆盖四组令牌**：
`--doc-up-text` / `--doc-down-text` **＋** `--ss-up-text` / `--ss-down-text`。

⚠️ **实现约束**：`--ss-up-text` 与 `--doc-up-text` **不能共用同一派生规则** ——
`--doc-up` 是**绿**（绿涨）、`--ss-up` 是**红**（红涨），加深方式虽同但**色相不同 ⇒ 目检要分开做**。

#### 13.13.3 守卫 G 的写法（按 dark/light 分别写，**不能用单一字面值断言**）

```python
assert "--brand-1:#4f46e5" not in kit._KIT_CSS, "组件层不得硬写主题层 --brand-1"
assert "--brand-2:#7c3aed" not in kit._KIT_CSS, "组件层不得硬写主题层 --brand-2"
assert "--brand-1:#4f46e5" in ut._THEME_ROOT_VARS["light"], "--brand-1 须由主题层提供(light)"
assert "--brand-1:#5b53f0" in ut._THEME_ROOT_VARS["dark"],  "--brand-1 须由主题层提供(dark)"
```

#### 13.13.4 AC-0.2 ② 的区间问题（裁定 A 已消解）

若 C0 不动 `_build_token_css():130`（生产零调用），② 的断言**必须限定扫描 `_TOKEN_CSS` 区间**
（`ui_kit.py:38-118`），否则误报 `:130`。
⇒ **裁定 A 是「一并清 `:130`」** ⇒ **该断言无需限定区间**（全文件扫描、四个 token 全 0 命中）。

#### 13.13.5 AC-0.2 ③ 两条都要进矩阵（唯一区分合并/替换的判据是第二条）

```bash
grep -q 'STYLE_PRESETS' modules/ui_theme.py
grep -qE 'STYLE_PRESETS\.get\(.*\)\.get\(.vars.\)' modules/ui_theme.py   # ★这条才区分合并/替换
```
⇒ `_THEME_ROOT_VARS` 一直存在，**第一条不能证明用了合并**。

#### 13.13.6 Phase 2 撤回的两条错误（勿再引用旧说法）

1. **「`--brand-2` 允许保留」** ⇒ 已撤回（§13.13.1）。
2. **`grep -q -- '--ss-up:#ff4d4f' modules/colors.py`** ⇒ 已撤回（**目标形态不存在**），
   正确写法：`grep -q 'UP_COLOR = "#ff4d4f"' modules/colors.py && grep -q 'DOWN_COLOR = "#00d486"' modules/colors.py`。

#### 13.13.7 C0 最终范围

**5 文件单一原子 commit**：
| 文件 | 处数 | 内容 |
|---|---|---|
| `modules/ui_kit.py` | 4 | `86` 修注释 / `88` 删 brand 硬覆盖 / `45` 删 ss-up-down 硬覆盖 / `130` 同源死代码一并清 |
| `modules/ui_theme.py` | 3 | `196` 补 classic 亮色 `--buy/--sell` / `223` `:root` 合并 preset vars / `219`+`502` 缓存键加 style |
| `tests/test_ui_kit_tokens.py` | 1 | 守卫 G 升级（§13.13.3） |
| `tests/test_a11y_contrast.py` | — | 改级联口径 |
| （前置） | — | **tinycss2 进项目 .venv**，否则解析层守卫永远进不了 CI |

**C0 完成后 8 组全部令牌有定义（无 UNDEF）、红涨绿跌 + 绿涨红跌双语义成立、preset 声明全部生效。**
### 13.14 Phase 1 最终定稿 + 主理人两条核实（D5 方案已验算通过 / 7 页面缺陷推翻）

#### 13.14.1 三方最终一致

**Phase 1 / Phase 2 / 主理人** 对 **fixG 六步 + 守卫 G + 8 组期望值表 + AC-0.2 ①~⑧ + 32 文件回归集** 完全一致。
D5（对比度）双档派生方案已验算通过并采纳；tinycss2 处置已裁定。

#### 13.14.2 🔴 主理人核实 1：session 风格键名就是 `ui_style`（Phase 1 伪代码正确）

`modules/ui_theme.py:102` `st.session_state.setdefault('ui_style', _p.get('ui_style', 'classic'))`、
`:1159` `return st.session_state.get('ui_style', 'classic')`、`:1186` `st.session_state['ui_style'] = choice`
⇒ **Phase 1 的 `st.session_state.get('ui_style', 'classic')` 正确，可照用**。
（另有 `theme_mode` = 暗/亮模式、`_ui_style_switcher_ts` = 切换节流 0.5s。）

**fixG 步 4/5 的具体形态（Phase 1 给，已核实键名）**：
```python
_style = st.session_state.get('ui_style', 'classic')
_cached = _DASHBOARD_SF_CSS_CACHE.get((dark, _style))
if _cached is not None:
    return _cached
root = (_THEME_ROOT_VARS["dark" if dark else "light"]
        + (STYLE_PRESETS.get(_style, {}).get('vars') or ''))
# ... _DASHBOARD_SF_CSS_CACHE[(dark, _style)] = _css
```

#### 13.14.3 ⚠️ 主理人核实 2：Phase 1 新登记的「7 个页面亮色基座缺失」**不成立**

Phase 1 说「`_LIGHT_CSS` 无 classic 基座 `:root` ⇒ 这 7 页在 classic 亮色下 `--bg`/`--card`/`--txt` 未定义」。
**前半句成立**（主理人实测：`_LIGHT_CSS` 内确实**找不到 `:root` 块**），**但推论不成立**：

`dashboard_sf_css()` 的**全部调用方只有 2 处**：
```
app.py:29                  st.markdown(dashboard_sf_css(), unsafe_allow_html=True)   ← ★全局注入
modules/page_utils.py:57   st.markdown(dashboard_sf_css(), unsafe_allow_html=True)   （render_standard_page 内）
```
⇒ **`app.py:29` 是全局注入** ⇒ 所有页面（含那 7 页）**都拿得到** `_THEME_ROOT_VARS` 的 `:root`。
且 `11_股票选取.py` / `20_个股分析.py` / `40_仓位管理.py` / `41_组合收益.py` / `46_自选股监控.py`
**既不调 `render_standard_page` 也不调 `apply_page_config`** —— 但它们是 **12 行 shim**
（委托 `modules/stock_research` / `modules/portfolio_views`），**真实渲染体由 24 页（走 `render_standard_page`）调用**
⇒ 内容渲染时同样有基座。

⇒ **该缺陷在本项目实际入口下不成立** ⇒ **不进 C0，也不单独立项**（避免虚假缺陷登记）。
⚠️ **唯一遗留待答项**：`app.py:29` 与 `page_utils.py:57` 两处调用的 `dark` / 风格入参**是否一致**
（若 app.py 那次拿不到 preset vars，则 app 级注入的 `:root` 仍只有基座值 ⇒ 影响「preset vars 在哪一层生效」）。

#### 13.14.4 D5 双档派生方案（已验算通过，32 项全部 ≥4.5，最差 4.80）

**决定性发现：不能只做「亮色加深」**。第一版方案（暗色=原值 / 亮色加深）**验算失败** ——
`--doc-down` 在 **5 个暗色组**（3.91~4.36）也不达标，**需要变亮**。

| 令牌 | 暗色基座 | 亮色基座 |
|---|---|---|
| `--doc-up-text` | `var(--doc-up)`（不变） | `color-mix(in srgb, var(--doc-up) 78%, black)` |
| `--doc-down-text` | `color-mix(in srgb, var(--doc-down) 79%, white)` ← **变亮** | `color-mix(in srgb, var(--doc-down) 94%, black)` |
| `--ss-up-text` | `var(--ss-up)`（不变） | `color-mix(in srgb, var(--ss-up) 80%, black)` |
| `--ss-down-text` | `var(--ss-down)`（不变） | `color-mix(in srgb, var(--ss-down) 62%, black)` |

⇒ **8 组 × 4 令牌 = 32 项全部 ≥ 4.5，最差 4.80**。
⇒ **色相保持已实测**：`--doc-up` 156.5°→156.6°（Δ+0.1）、`--doc-down` 0.0°→0.0°（Δ0.0）
⇒ **绿仍是绿、红仍是红，「绿涨红跌」语义不受影响**（反驳「加深会变褐」的担心）。
⇒ **落点**：4 个新令牌**分暗/亮两套** ⇒ **必须放 `_THEME_ROOT_VARS['dark']` 与 `['light']`**，
**不能放不分主题的 `_TOKEN_CSS`**。
⇒ 用 `color-mix(…, var(--X) P%, …)` 而非写死 hex ⇒ 随 `var(--X)` 自动跟随各风格
（swiss 的 `#d93025`、ink 的 `#c0392b` 各自派生）⇒ 无需逐风格维护。

**D5 不并入 C0 的三条理由**：① 会把 C0 回归面从 6 处扩到 14 处，且改变 3 个亮色组实际文字色
⇒ **截图基线无法区分是 C0 的锅还是 D5 的锅**；② D5 需「哪些场景用 text 令牌」的产品决策
（`sf-tag`/`sf-pill` 迁移后还会新增消费点）；③ D5 验证依赖浏览器截图，而 C0 可纯静态 + tinycss2 验证
⇒ 混批会让「C0 已验证可上线」失效。

#### 13.14.5 裁定：tinycss2 **装进 venv 但不进 C0 commit**

采纳 Phase 1 建议：**环境准备动作**（C0 期间一次性装进项目 venv，**不进 commit**，
避免 `requirements.txt` 变更让 C0 从 5 文件变 6 文件 + 双机并发下 pip 装包不可控）；
**C0 的主要防线 = 零依赖静态断言**（AC-0.2 ①~⑧）⇒ 可进 CI；
**解析层守卫** `tests/test_style_token_cascade.py` 随 C0 或下轮落地。

#### 13.14.6 数据残留已统一（勿引用旧数字）

#41 真实缺口 = **导航条目 63 条 / 未收录 47 个 / `_EMOJI_MAP` 实际 53 条 / 需新增约 43 个 path**
（Phase 1 表格里的「16/65」为旧数字，作废）。
### 13.15 最终定案：C0~C4 五批 + 三条收口修正（Phase 2 收官版）

> **Phase 1 / Phase 2 / 主理人 三方完全一致**：C0 = fixE+ 六步 + 守卫 G（**5 文件原子 commit**）、
> 8 组期望值表、AC-0.2 ①~⑧、32 文件回归集、D5 双档派生表。

#### 13.15.1 ⚠️ 修正：亮色基座缺失的页面是 **2 页**（不是 7 页）

主理人上一条裁定「7 页全不成立」（理由 `app.py:29` 是全局注入）——**Phase 2 逐个追了装配路径，
主理人的推翻过于绝对**。修正后的准确结论：

| 页面 | 实际装配路径 | 结果 |
|---|---|---|
| `pages/11_股票选取.py` | → `stock_research.render_stock_picker`(`:1406`) → 内部 `render_standard_page` | ✅ 间接拿到 |
| `pages/20_个股分析.py` | → `render_stock_analysis`(`:13`) → `:24` `render_standard_page(...)` | ✅ 间接拿到 |
| `pages/40_仓位管理.py` | → `portfolio_views.render_position_manager`(`:520`) → `:531` `render_standard_page(...)` | ✅ 间接拿到 |
| `pages/41_组合收益.py` | → `render_portfolio_returns`(`:996`) → `:1012` `render_standard_page(...)` | ✅ 间接拿到 |
| `pages/46_自选股监控.py` | → `render_watchlist_monitor`(`:10`) → `:28` import `render_standard_page` | ✅ 间接拿到 |
| **`pages/53_星辰AI.py`** | 仅 `apply_page_config`(`:54`) | ❌ **真不拿** |
| **`pages/90_登录.py`** | 仅 `apply_page_config`(`:25`) | ❌ **真不拿** |

⇒ **真正不经 `dashboard_sf_css` 的只有 2 页** ⇒ 缺陷成立 ⇒ **登记为 C4（独立立项，不进 C0~C3）**。
⚠️ **登记表必须写 2 页**，写 7 页会误伤 5 个正常页面。
⚠️ **未验证**：这 2 页在 classic 亮色下的**实际渲染**（静态推导：未定义 ⇒ 回落继承/初始值）
⇒ **需目检确认后再登记**。

#### 13.15.2 ⚠️ 修正：C0 第 6 步的**理由**（主理人此前的表述有错，落点不变）

主理人此前说「基座的 **dark** 块本来就有 `--buy/--sell`」⇒ **错**。实测：
```
_THEME_ROOT_VARS['dark']  含 --buy=False  含 --sell=False  含 --doc-up=True
_THEME_ROOT_VARS['light'] 含 --buy=False  含 --sell=False  含 --doc-up=True
_DARK_CSS   含 --buy:#ff4d4f : True      ← dark 的真实来源是这里
_LIGHT_CSS  含 --buy        : False
_LIGHT_CSS 的 :root 声明数   : 1  → ['--ss-saas-shadow ×2','--ss-up:#ff4d4f','--ss-down:#00d486']
```
⇒ **`_THEME_ROOT_VARS` 两块都没有 `--buy/--sell`**；`_LIGHT_CSS` 完全没有 classic 基座（只有 4 条声明）。
⇒ **但落点结论不变**：classic 亮色下唯一可补处就是 `_THEME_ROOT_VARS['light']`(`:196`)
⇒ **C0 第 6 步位置正确**，理由改为「两块都缺 `--buy/--sell`，而 `_LIGHT_CSS` 不含基座」。
⇒ **连带事实（成立）**：classic 亮色下 `--bg`/`--card`/`--txt` 的**唯一来源**就是
`dashboard_sf_css()` 注入的 `:root{_THEME_ROOT_VARS['light']}`。

#### 13.15.3 C3 验收标准加一条（`color-mix` 插值模型未验证项）

**tinycss2 不计算 `color-mix`**（实测 `parse_component_value_list` 返回
`<FunctionBlock color-mix( … )>`），且**两种插值模型给出不同 hex**
（gamma 编码 `#007b4b` vs 线性光 `#008d55`）。
⇒ **C3 验收标准加一条**：「DevTools 读 `--doc-up-text` 计算值，与期望 hex 偏差 ≤ 1/通道」
⇒ 插值模型若有偏差会被守卫拦住，**而非静默失色**。

#### 13.15.4 最终五批

| # | 内容 | 状态 |
|---|---|---|
| **C0**（最先） | fixE+ 六步 + 守卫 G = **5 文件原子 commit** | ✅ 定稿 |
| **C1** | B4 死代码清理（10 真死）+ B5 | 不变 |
| **C2** | 仪表盘族全量迁移 + 6 守卫同步 + 保留「绿涨红跌」注释 | 不变 |
| **C3** | R3 语义修复 + D4（`page_utils.py:124` ≈2.2:1）+ **D5（4 新令牌 + 32 项验算 + color-mix 插值验收）** | ✅ D5 独立 C3 |
| **C4** | **`pages/53_星辰AI.py` / `pages/90_登录.py` classic 亮色缺基座** | 独立立项，需目检确认 |

#### 13.15.5 唯一遗留待答项（三方都没查的一环）

**`app.py:29` 与 `page_utils.py:57` 两处 `dashboard_sf_css()` 调用的 `dark` / 风格入参是否一致？**
⇒ 若 `app.py` 那次拿不到 preset vars，则 app 级注入的 `:root` 仍只有基座值
⇒ 影响「preset vars 到底在哪一层生效」，也影响 C4 的影响面判断。
### 13.16 验收方式定稿 + 主理人裁定 A 修订（Phase 1 收官版）

> **三方技术分歧已全部清零**；C0 实施所需信息齐备：六步（位置 + 动作 + 后果 + 具体代码形态）、
> 守卫 G 写法、10 条验收项、8 组期望值表、D5 派生表与字号口径、32 文件回归集、C0~C4 分批。

#### 13.16.1 守卫验收以 **Python 断言为主体**（grep 仅作人工核对）

`_TOKEN_CSS` 字面量现为 `modules/ui_kit.py:38..118`（81 行），而 C0 的**步 2、步 3 各删一行**
⇒ `_TOKEN_CSS` 变 79 行、`_build_token_css()` 移到 `:119`
⇒ **写死行号的区间断言实施后会扫错范围**（ux 的「区间扫描」方案有此坑）。

⇒ **定稿：两种形态都用**

**（a）Python 断言（主体，进 CI；无行号、无漂移）**：
```python
# tests/test_ui_kit_tokens.py —— 读运行时对象
def test_token_css_does_not_hardcode_theme_tokens():
    css = _kit()._KIT_CSS          # = _TOKEN_CSS + …
    for tok in ("--brand-1:#", "--brand-2:#", "--ss-up:#", "--ss-down:#"):
        assert tok not in css, f"_TOKEN_CSS 不得硬写主题层令牌 {tok}（应归 _THEME_ROOT_VARS / preset vars）"

def test_brand_tokens_owned_by_theme_layer():
    assert "--brand-1:#4f46e5" in ut._THEME_ROOT_VARS["light"]
    assert "--brand-1:#5b53f0" in ut._THEME_ROOT_VARS["dark"]   # ★ 值不同，别用单一字面值
```
⇒ `_KIT_CSS` 天然含 `_TOKEN_CSS` 全部内容、且**不含** `_build_token_css()` ⇒ **不会误报 `:130`**。

**（b）awk 内容锚定（人工核对；不受行号漂移影响）**：
```bash
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py \
  | grep -nE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#'
# 当前 2 处（相对行 8/51）⇒ 红；C0 完成后 0 处 ⇒ 绿
```

#### 13.16.2 ⚠️ 主理人裁定 A 修订：`modules/ui_kit.py:130` **保留不动**

主理人此前裁定「一并清 `_build_token_css():130`」，理由是「验收项②要求四 token 全 0 命中，留着必红」
⇒ **该理由已被 13.16.1 消解**（Python 断言查 `_KIT_CSS`，天然不含 `_build_token_css()`）。
⇒ **裁定更新：`:130` 保留不动** —— **不为迁就断言而扩大 C0 改动面**
（`_build_token_css` 生产零调用，留着零风险；删它反而多一处改动点）。
`_build_token_css` 列为**独立清理项**（不进 C0~C4）。
⇒ 验收项②的**整文件 grep 版作废**，改用 13.16.1 的 (a)/(b)。

#### 13.16.3 验收项 ⑨⑩（新增）

```
# ⑨ _DARK_CSS/_LIGHT_CSS 的 --ss-up 不必删（preset 覆盖它们 ⇒ 无害，允许存在）
! grep -qE 'assert.*_DARK_CSS.*--ss-up' tests/ ; echo "（无需断言，允许存在）"
# ⑩ 价格域与交易域不得互串（colors.py 里 RED/GREEN 名实相反，是既定设计，防有人"纠正"）
grep -q 'RED = "#009e60"' modules/colors.py && grep -q 'GREEN = "#dc2626"' modules/colors.py
```
⇒ 完整验收项 = ①~⑧（②按 13.16.1 改写）+ ⑨⑩。

#### 13.16.4 两处残留纠正

- **「7 个页面」清单是旧的，正确是 2 页**（`pages/53_星辰AI.py` 仅 `apply_page_config:54`；
  `pages/90_登录.py` 仅 `apply_page_config:25`）⇒ C4 登记**必须写 2 页**，写 7 页会误伤 5 个正常页面。
- **#41 数字统一为**：63 条导航 / 47 未收录 / `_EMOJI_MAP` 实际 53 条 / 需新增约 43 个 path
  （Phase 1 收官版 §7 的「16/65」为旧数字，作废）。

#### 13.16.5 D5 字号口径（双方逐点核对一致的完整版）

- **大字档（3:1 全过，无需新令牌）**：`sf-price-big`(40px/800)、`sf-metric-card .value`(22px/700)、
  `.ss-stat .value`(24px/800)、`.xc-card .value`(22px/800)
- **正文档（4.5，需新令牌）**：`sf-perspective-card .body` 内 14px/400 与 14px/700、
  `.ss-stat .delta`(13px/600)、`.xc-card .delta`(13px/700)、`.xc-card .meta`(11px)
- **★ 加粗到 700 仍不足 18.66px ⇒ 不能靠加粗豁免**
### 13.17 终局裁决：AC-0.2 ①~⑨ 定稿 + 两层防假绿 + D5 变体 2

> Phase 1 / Phase 2 终版提请的裁决，**主理人全部采纳**并含 2 条实质更正。
> **三方技术分歧全部清零；C0 实施所需信息齐备且无分歧。**

#### 13.17.1 裁决 ①：C0 = **C0-a~C0-g（7 处改动 / 5 文件原子 commit）** —— 认可

**采用位置引用**（Phase 2 提议，消除两位成员表格里步 5/6 编号相反的歧义）：

| 引用 | 位置 | 动作 | 不做的后果 |
|---|---|---|---|
| **C0-a** | `modules/ui_kit.py:86` | 修 CSS 注释提前闭合（`--ss-*/` → `--ss-* /`） | `--brand-1` 继续被浏览器丢弃（D4） |
| **C0-b** | `modules/ui_kit.py:88` | 删 `--brand-1:#4f46e5; --brand-2:#7c3aed;` **整行** | C0-a 会让它复活 ⇒ 8 组统一经典紫（更糟）；留 `--brand-2` ⇒ 6 套 preset 次品牌色全失效 |
| **C0-c** | `modules/ui_kit.py:45` | 删 `--ss-up:#ff4d4f; --ss-down:#00d486;` | `--ss-up` 仍 8 组统一 `#ff4d4f` |
| **C0-d** | `modules/ui_theme.py:223` | `:root` = `基座 ∪ preset vars`（**合并，非替换**） | preset vars 永不生效（D5 的真覆盖者） |
| **C0-e** | `modules/ui_theme.py:196` | `_THEME_ROOT_VARS['light']` 补 `--buy:#ff4d4f; --sell:#00d486;` | classic 亮色 `.sf-pill.up` 字色回落 inherit（语义+对比度双失控） |
| **C0-f** | `modules/ui_theme.py:219/502` | 缓存键 `(dark)` → `(dark, style)` | 切风格后仪表盘层静默不更新（D6） |
| **C0-g** | `tests/test_ui_kit_tokens.py:243-256` | 守卫升级：锁归属 + 锁不越权 | 守卫继续给死声明背书（一直假绿） |

⇒ **C0-a~C0-g 全部必须同批，缺一即失效或更糟**。C0 = **7 处改动 / 5 文件** 单一原子 commit。

#### 13.17.2 🔴 裁决 ② 补充：验收项 ② **必须配「提取自检」**（防假绿）

内容锚定方案（awk）**自身的失效模式是假绿** —— 锚点一旦失配，awk 提取到 0 行 ⇒ grep 无命中
⇒ 断言「通过」⇒ **守卫在失效时反而放行**（最危险的一类）。
```bash
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py | grep -q '\-\-ss-radius-card' \
  || { echo "★_TOKEN_CSS 提取失败（锚点失配）—— 守卫假绿，断言无效"; exit 1; }
```
⇒ **Python 侧需等价自检**（断言 `_kit()._KIT_CSS` 非空且长度合理，否则 `tok not in css`
在空串上恒真 ⇒ 又是假绿）。

#### 13.17.3 裁决 ② 之 ⑨：采用 Phase 2 的**否定断言**（Phase 1 的 OR 版逻辑是反的）

Phase 1 写的 `grep -q -- '--doc-up:#009e60' modules/colors.py || grep -q -- 'RED = "#009e60"' modules/colors.py`
是 **OR** ⇒ 任一命中即通过 ⇒ **若有人把 `--doc-up:#009e60` 误写进 `colors.py`，这条断言仍会通过**
⇒ **测不出它想防的「互串」**。
```bash
# ⑨-a 价格域令牌不得出现在交易域常量模块
! grep -q -- '--doc-up:' modules/colors.py \
  || { echo "★价格域令牌串进交易域常量模块"; exit 1; }
# ⑨-b 交易域令牌不得出现在报告体基座（必须限定 _THEME_ROOT_VARS 块）
awk '/^_THEME_ROOT_VARS = \{/,/^\}/' modules/ui_theme.py \
  | grep -qE '\-\-ss-up:#|\-\-ss-down:#' \
  && { echo "★交易域令牌串进经典基座"; exit 1; }
```
⚠️ **⑨-b 不能扫整个 `ui_theme.py`** —— 实测 `'--ss-up:#'` 在该文件命中 **7 处**
（`_DARK_CSS:54` / `_LIGHT_CSS:55` 的 `:root` 里**合法地**定义了 `--ss-up:#ff4d4f`，
属**全局主题层**，与 C0-c 要删的**组件层** `_TOKEN_CSS:45` **不同层**）。

#### 13.17.4 三层归属表（「互串」守卫能成立的基础）

| 层 | 位置 | `--ss-up:#ff4d4f` | C0 处置 |
|---|---|---|---|
| 全局主题层 | `_DARK_CSS:54` :root#2、`_LIGHT_CSS:55` :root#1 | ✅ 有 | **保留**（classic 真值源） |
| 组件层 | `_TOKEN_CSS:45` | ✅ 有 | **删除**（C0-c，最后注入者会盖住 preset） |
| 经典基座 | `_THEME_ROOT_VARS` 两块 | ❌ 无 | **保持无**（`--doc-up`/`--doc-down` 归此层） |

#### 13.17.5 裁决 ③：C0~C3 + C4 —— 采纳

**C0 额外触碰 6 个测试文件**：`test_ui_kit_tokens.py`（`:243-256` 升级 + 2 新守卫）、
`test_a11y_contrast.py`（改级联口径）、`test_ui_theme.py`（`:58-69`，⚠️ **`:62` 的「绿涨红跌」注释不能删**）、
`test_no_hardcoded_semantic_hex.py`（`:51-55`）、`test_stock_research_semantics.py`（`:98`）、
`test_ui_theme_styles.py`（`:50` classic zero-op 不破）。

#### 13.17.6 🔴 更正：D5 采用**变体 2（双插值模型鲁棒）**，取代变体 1

主理人上一条裁决 ④ 采纳的是**变体 1** ⇒ **实测推翻**：变体 1 在 **linear 插值模型下
会静默失败 5 项**（`classic/light --ss-down` 仅 **2.98**）—— **那正是 D5 要防的失败模式**
（浏览器若用 linear 插值，颜色静默变浅）。

| 令牌 | 暗色基座 | 亮色基座（变体 2） |
|---|---|---|
| `--doc-up-text` | `var(--doc-up)` | `color-mix(in srgb, var(--doc-up) 58%, black)` |
| `--doc-down-text` | `color-mix(in srgb, var(--doc-down) 79%, white)` | `color-mix(in srgb, var(--doc-down) 88%, black)` |
| `--ss-up-text` | `var(--ss-up)` | `color-mix(in srgb, var(--ss-up) 62%, black)` |
| `--ss-down-text` | `var(--ss-down)` | `color-mix(in srgb, var(--ss-down) 34%, black)` |

⇒ **32 项 × 2 模型 = 64 次验算全部 ≥4.5**（srgb 最差 4.86 / linear 最差 4.80）。
⇒ **色相漂移口径统一**（两成员实测差 0.2° vs 1.0°，取保守值）：**≤ 1.0°**
（出现在 linear 模型下 `--ss-down-text` `#008250` vs 基准 `#00d486`）⇒ 仍在同色系可读范围。
⇒ **语义可读性已实测**（Phase 2 补验，Phase 1 未做）：两模型下
`--doc-up-text` 色相 156.5°/156.1°（绿系）｜`--doc-down-text` 0.0°（红系）｜
`--ss-up-text` 359.5°/359.6°（红系）｜`--ss-down-text` 158.3°/156.9°（绿系）⇒ **无撞色**。
⇒ **「新绿 vs 新绿」碰撞登记**（Phase 2 补验）：`--doc-up-text` 与 `--ss-down-text` 同为绿系，
区分度偏低（1.10:1 ~ 1.87:1），但**两者永不同屏出现**（一在报告体、一在交易屏）
⇒ **不构成实际风险**，但 C3 目检时留意。
⇒ **代价**：亮色主题下颜色比变体 1 更深 ⇒ **对比度更高 = 更安全**，且色相不变。

#### 13.17.7 🔴 验收判据升级：C3 **不断言 hex，断言对比度 + 色相族**

hex 依赖插值模型（两种模型给出不同 hex 且都「正确」），而 **WCAG 对比度是模型无关的最终目标**。
⇒ **C3 验收 4 条**（模型无关版）：
```
① DevTools 读 4 个新令牌的计算值（3 组亮色 × 4 令牌 = 12 项）
② 计算值 → 转 hex → 对该风格 --bg 算 WCAG 对比度
③ 断言 ≥4.5（目标 ≥4.8 留余量）
④ 断言色相仍属原语义色系
   （--doc-up-text 绿 60~180° / --doc-down-text 红 ≤20 或 ≥340°
    / --ss-up-text 红 / --ss-down-text 绿）
   —— 这条是「语义不串」的机器化，比肉眼目检更可靠
```
⇒ **无论浏览器用哪种插值模型都恒绿**；若某浏览器用第三种模型（CSS Color 5 还有
premultiplied-alpha 等变体）导致对比度不足，**守卫会红**（发现问题）而非静默失色。

#### 13.17.8 Python 守卫的两个坑（Phase 2 实测）

⚠️ **必须用带冒号的精确形态**：`'--ss-up'`（不带冒号）在 `_KIT_CSS` 出现 **8 次**（含 `var(--ss-up)`）⇒ 会误报
⇒ 统一用 `"--ss-up:#"` 这类带冒号形态。
⚠️ **dark/light 必须分写**（`--brand-1:#5b53f0` in dark ≠ `#4f46e5` in light）。

#### 13.17.9 C4 登记口径：**待目检后决定是否立项**

两页（`pages/53_星辰AI.py` 仅 `apply_page_config:54`、`pages/90_登录.py` 仅 `:25`）的
**classic 亮色实际渲染未目检** ⇒ **建议先目检再立项**，避免把未验证的静态推导写成既成事实。
⚠️ **登记表必须写 2 页**，写 7 页会误伤 5 个正常页面。
### 13.18 验收清单冻结（Phase 1 终版）+ 守卫自杀边界警示

> **C0 口径冻结**：Phase 1 / Phase 2 / 主理人三方技术分歧清零；
> **C0 实施内容不变**（6 步 + 守卫 G，5 文件单一原子 commit）。

#### 13.18.1 🔴 边界警示（最重要）：⑩-b 的检查范围**绝不能扩到 `--buy:|--sell:`**

```bash
# ✓ 正确（严格限定 --ss-up:#|--ss-down:#）
awk '/^_THEME_ROOT_VARS = \{/,/^\}/' modules/ui_theme.py \
  | grep -qE '\-\-ss-up:#|\-\-ss-down:#' \
  && { echo "★交易域令牌串进经典基座"; exit 1; }
```
⚠️ **若把范围扩到 `--buy:|--sell:`，守卫会误杀自己的批次** ——
**C0-e 本身就要把 `--buy:#ff4d4f; --sell:#00d486;` 加进 `_THEME_ROOT_VARS['light']`**
⇒ 守卫在 C0 完成后**必然红**，而红的原因正是 C0 自己做对了。
⇒ **范围必须严格限定 `--ss-up:#|--ss-down:#`**（交易域的**涨跌语义色**），
**不得**包含 `--buy:|--sell:`（那是 C0-e 要加的东西，且语义层级不同）。

#### 13.18.2 三条已实测的实现细节（照用）

- `'--ss-up'`（**不带冒号**）在 `_KIT_CSS` 出现 **8 次**（含 `var(--ss-up)` 等用法）
  ⇒ **必须用精确形态 `'--ss-up:#'`**，否则守卫误报。
- `_KIT_CSS` 长度 **21934**；4 个目标 token 各出现 **1 次**；`'_build_token_css'` 出现 **0 次**
  ⇒ `:130` 不会污染 Python 守卫。
- **锚点失配 ⇒ 提取为空 ⇒ 旧断言会【假绿】通过**（实测：原始提取 81 行 / 模拟提取 0 行）
  ⇒ **AC-0.2.b-self 提取自检必须带**，锚点用 `--ss-radius-card`（在 `_TOKEN_CSS` 内出现 3 次，稳定存在）。

#### 13.18.3 新登记观察项（列 C3，不影响 C0）

**classic 的 `--buy/--sell` 来源修完后不对称**：
- classic/dark：仅来自 `_DARK_CSS:54`（`_THEME_ROOT_VARS['dark']` 里**没有**）
- classic/light：仅来自 `_THEME_ROOT_VARS['light']`（`_LIGHT_CSS:55` 里**没有**）

⇒ 两者**值相同**（`#ff4d4f`/`#00d486`）⇒ **视觉无差异**，但**各自是单点依赖**。
彻底修法：`_THEME_ROOT_VARS` 两块都带 `--buy/--sell`，或让 `_LIGHT_CSS` 也带完整 classic 基座。
⇒ **本轮不动**，登记为 C3 项。

#### 13.18.4 8 组期望值表的落点

采纳 Phase 1 建议：**落 `docs/` 的 Markdown 表格**（**不放脚本** ——
tinycss2 不在项目 `.venv`，进 CI 会依赖未声明包）⇒ 已落 §13.17 的人工验收对照表。
### 13.19 C0 验收标准终版（Phase 2 终版）+ 两处补正

> Phase 2 终版确认了 §13.18 的边界警示，并**精确化了 Phase 1 对「awk 假绿」的描述**。
> **C0 口径最终冻结。**

#### 13.19.1 补正 1：真正的假绿触发条件是「**起始锚不再匹配**」，不是收尾锚

Phase 1 模拟的是「收尾锚 `"""` → `x"""`」⇒ **Phase 2 实测该场景并不假绿**：

| 模拟的改动 | awk 提取行数 | 旧断言（无自检） | 带自检 |
|---|---|---|---|
| 收尾 `"""` → `x"""`（Phase 1 的模拟） | 348（范围延伸到下一个 `^"""`） | 红（命中）⇒ **不假绿** | 自检通过（漏报但无害） |
| **起始 `_TOKEN_CSS = r"""` → `_TOKEN_CSS: str = r"""`** | **0** | **★★假绿**：提取为空 ⇒ 判为「已修复」，而实际硬写还在 | **★自检正确报出「提取失败」** |

⇒ **最可能的真实诱因是有人给变量加类型注解**（`_TOKEN_CSS: str = r"""`）——现代 Python 代码里很常见。
⇒ **自检必须带，且用「内容锚点 + 数量下限」双保险**（两者正交，任一锚点失配都能拦下）：
```bash
# 内容锚点（--ss-radius-card 在 _TOKEN_CSS 内出现 3 次，稳定存在）
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py | grep -q '\-\-ss-radius-card' \
  || { echo "★_TOKEN_CSS 提取失败（锚点失配）—— 守卫假绿，断言无效"; exit 1; }
# 数量下限（当前 81 行；C0 删 2 行后 79 行，余量充足）
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py | grep -c . | grep -qE '^[5-9][0-9]$|^[1-9][0-9]{2,}$' \
  || { echo "★_TOKEN_CSS 提取内容异常短—— 守卫假绿，断言无效"; exit 1; }
```

#### 13.19.2 补正 2：⑨-i 的范围边界**必须写成注释**（否则下轮极可能被「顺手扩范围」误杀 C0）

C0-e（`ui_theme.py:196`）**合法地**把 `--buy:#ff4d4f; --sell:#00d486;` 加进 `_THEME_ROOT_VARS['light']`，
而 `--buy/--sell` **也是交易域令牌** ⇒ 若断言含 `--buy:|--sell:`，**C0 完成后必然命中 ⇒ 守卫恒红（自我否定）**。
实测（正确范围，仅 `--ss-up:#|--ss-down:#`）：dark 0 处 ✔ / light 0 处 ✔ ⇒ 绿。
⇒ **本断言只管「`--ss-up/--ss-down` 误入报告体基座」这一个情形**；范围边界必须落成注释。

#### 13.19.3 C3 新增观察项：基座对称性（**可机器判**）

C0-e 完成后，classic 的 `--buy/--sell` 来源**不对称**：
- classic/dark：仅来自 `_DARK_CSS:54`（`_THEME_ROOT_VARS['dark']` 里**没有**）
- classic/light：仅来自 `_THEME_ROOT_VARS['light']`（`_LIGHT_CSS:55` 里**没有**）

⇒ **值相同 ⇒ 视觉无差异**，但**各自是单点依赖**（删了那一侧就静默失色）。
⇒ **可机器判的落地形式**：断言 `_THEME_ROOT_VARS['dark']` 与 `['light']` 的**令牌键集合对称**
（值可不同，dark `#5b53f0` vs light `#4f46e5` 仍允许）。
⇒ **C0 不动它**（彻底修法属 C3，避免混入 C0 回归面）。

#### 13.19.4 C0 终版验收标准（冻结）

```bash
# ① 注释提前闭合不得回潮
! grep -rnE '\-\-[a-zA-Z0-9_-]+-\*/' --include="*.py" modules/ pages/ app.py

# ② _TOKEN_CSS 不得硬写主题层令牌（内容锚定，不受行号漂移）
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py \
  | grep -qE '\-\-brand-1:#|--brand-2:#|--ss-up:#|--ss-down:#' && echo "★组件层仍硬写主题层令牌"
# ②-self 双保险（内容锚点 + 数量下限）—— 缺一即假绿风险
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py | grep -q '\-\-ss-radius-card' \
  || { echo "★_TOKEN_CSS 提取失败（锚点失配）—— 守卫假绿，断言无效"; exit 1; }
awk '/^_TOKEN_CSS = r"""/,/^"""/' modules/ui_kit.py | grep -c . | grep -qE '^[5-9][0-9]$|^[1-9][0-9]{2,}$' \
  || { echo "★_TOKEN_CSS 提取内容异常短—— 守卫假绿，断言无效"; exit 1; }

# ③ :root 必须【合并】preset vars（第二条是唯一区分合并/替换的判据）
grep -q 'STYLE_PRESETS' modules/ui_theme.py
grep -qE 'STYLE_PRESETS\.get\(.*\)\.get\(.vars.\)' modules/ui_theme.py

# ④ classic 亮色 --buy/--sell 必须有定义
grep -q -- '--buy:#ff4d4f' modules/ui_theme.py && grep -q -- '--sell:#00d486' modules/ui_theme.py

# ⑤ 缓存键必须含 style
grep -qE '_DASHBOARD_SF_CSS_CACHE\.get\(\(dark' modules/ui_theme.py

# ⑥ 交易语义真值源（colors.py 是【常量形态】，不是 --ss-up: 形态）
grep -q 'UP_COLOR = "#ff4d4f"' modules/colors.py && grep -q 'DOWN_COLOR = "#00d486"' modules/colors.py

# ⑦ 价格域红线（8 组恒成立）
grep -q -- '--doc-up:#009e60' modules/ui_theme.py && grep -q -- '--doc-down:#dc2626' modules/ui_theme.py

# ⑧ classic zero-op 与「绿涨红跌」注释不破
grep -q "STYLE_PRESETS\[.classic.\]\[.vars.\] == " tests/test_ui_theme_styles.py
grep -q '绿涨红跌' modules/ui_theme.py

# ⑨ 双向互串守卫（★否定断言）
! grep -q -- '--doc-up:' modules/colors.py \
  || { echo "★价格域令牌串进交易域常量模块"; exit 1; }
# ⚠️ 范围必须严格限定 --ss-up:#|--ss-down:#，【不可加入 --buy:|--sell:】
#    （C0-e 合法地把 --buy/--sell 加进 _THEME_ROOT_VARS['light']，扩范围会让守卫恒红）
awk '/^_THEME_ROOT_VARS = \{/,/^\}/' modules/ui_theme.py \
  | grep -qE '\-\-ss-up:#|\-\-ss-down:#' \
  && { echo "★交易域令牌串进经典基座"; exit 1; }
```
⚠️ **⑨-b 必须限定 `_THEME_ROOT_VARS` 块** —— 实测整文件扫命中 **7 处**
（`_DARK_CSS:54` / `_LIGHT_CSS:55` / 6 套 preset vars `:599/695/774/856/954`），那些**合法**（不同层）。
