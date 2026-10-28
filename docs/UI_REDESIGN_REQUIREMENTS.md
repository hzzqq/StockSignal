# StockSignal 前端重新设计需求文档（UI/UX Redesign Requirements）

> 文档状态：V2 草案 —— **现状审计优先**，设计方向待老板基于审计拍板（不早下定论）
> 触发：老板反馈「之前只换排版、没改设计语言，远达不到参考图水准」+「先重新查看项目页面，方案别早提，不够详细」
> 参考图：QUBE 行情（浅色极简）/ QuantDinger（深色量化终端）/ PandaAI（黑白注册页）/ StockSignal 现状（图4 错误条溢出，Phase 0 已修）
> 约束：技术栈 **Streamlit**（`app.py` + `pages/` + `modules/ui_kit`）；涨跌色 **A股 涨红跌绿**（不可改）；
> `ui_kit._KIT_CSS` 为样式单一真理源；守卫 `test_ui_design_system.py` / `test_ui_kit_hero.py` 锁视觉基线；双 AI 同机红线（不碰 Trae 领地）。

---

## 1. 背景与目标

### 1.1 现状问题（老板原话）
> 「我想你模仿这些图片的前端，但是你只是保留原来的组件和 ui，然后换了排版，这远远达不到我的需求」

根因：上一轮只动了**排布（layout）**，没重建**设计语言**（配色体系、圆角/间距/阴影刻度、组件视觉质感、信息密度、字体层级）。用户要的是「换皮换骨」，不是「挪位置」。

### 1.2 本轮定位（先审计、后定方向、再分阶段）
1. **先审计**：把 StockSignal 现有 86 个页面 + 既有设计系统的真实状态摸清楚，而不是凭参考图空想方案。
2. **再定方向**：基于审计结果，由老板在「深/浅/双主题」中选主方向。
3. **后分阶段**：先在 `ui_kit` 单点收敛，再逐页标准化，不回退守卫。

### 1.3 非目标（红线）
- 不换技术栈（不把 Streamlit 换成 React/Vue）。
- 不改 A股涨跌色语义（涨红跌绿）。
- 不破坏 `test_ui_design_system.py` / `test_ui_kit_hero.py` / `test_streamlit_api_hygiene.py`。

---

## 2. 参考设计解析（3 张图）

| 参考 | 风格 | 布局 | 配色 | 标志性组件 |
|------|------|------|------|-----------|
| **QUBE 行情** | 浅色极简、数据密集 | 三栏（导航190/列表200/详情） | 浅灰白底、白卡、**黑胶囊选中态**、红涨绿跌 | 白卡 1px 边+12–16px 圆角、黑胶囊贯穿全局、线性细图标、分时红渐变填充 |
| **QuantDinger** | 深色专业量化终端 | 顶栏+图标侧栏+双栏详情 | 近黑底、**琥珀橙强调**、红绿橙语义色 | 双排 KPI 卡、策略卡带状态色竖条、密集红绿表格、橙实心按钮、蓝色提示条 |
| **PandaAI** | 黑白单色注册页 | 左右分栏（白表单+黑像素插画） | 纯白+纯黑、无彩色 | 细边输入框、黑胶囊按钮、像素艺术插画 |

> 关键判断：QUBE 与 QuantDinger 是**功能页**参考（行情/决策/回测），PandaAI 是**落地/注册页**参考。三者风格差异大，最终需老板选主方向。

---

## 3. 现状审计（StockSignal 真实页面，已实地查看）

### 3.1 既有设计系统（已存在，不是从零开始）
| 层 | 文件 | 现状 |
|----|------|------|
| 主题 | `modules/ui_theme.py` | **双主题已支持**：默认**暗色终端**（2026-10-28 已翻全局回退 dark；浅色保留为可切换副主题）；深色令牌 `--bg:#0f0f23 / --card:#1a1a2e / --txt:#e2e8f0 / --border:#2d2d44`，强调色为**靛紫 `#4f46e5/#7c3aed`**（≠QuantDinger 琥珀橙）；A股涨红跌绿由 `--ss-up:#ff4d4f / --ss-down:#00d486`（`ui_kit`）管；另有 finpro/terminal/aurora/cyber→dark、swiss/ink→light 命名风格 |
| 组件层 | `modules/ui_kit.py` | 已有 `.xc-*` 新城组件：**渐变 hero（.xc-hero）**、**Bento 卡网格（.xc-card / .xc-grid）**、指标卡、图表卡（.ss-chart）、信息横幅（.xc-info）、错误/空态/成功/警告卡（.xc-error-box 等，**带 `min-width:0` 自动换行**）、响应式表格（.ss-table-wrap）、悬停预览（.ss-hint）、数据来源徽标（.ss-prov）；设计令牌 `.ss-*` 全部走 CSS 变量，首帧兜底已做 |
| 页面脚手架 | `modules/page_utils.py` | `render_standard_page(title, icon, layout, caption)` —— 各页统一入口，但**不是** `ui_kit.page_hero`；含 `get_fetcher` 等 |
| 旧组件 | `modules/ui_theme.py` + `page_widgets` | 仍有旧 `sf_card` / `sf_metric` / `_empty_info` / `_toast` 等，与 `.xc-*` 并存 |
| 专用渲染 | `modules/decision_view.py` | 决策页把渲染委托给它（`render_signal_cards` / `render_position_card` / `render_ladder_table` / `render_freshness_badge` / `render_decision_loop_alarm`） |
| 错误展示 | `90_登录.py` | **图4 错误条**：原为原生 `st.error`+`st.code` 裸塞异常 `{e}` → 长文本溢出；**Phase 0 已修复**：改走 `xc_error_box`+`st.code(language="bash")`，异常只进日志 |

### 3.2 页面采用现状（抽样 3 页，代表三类）
| 页面 | 类型 | 实际用的组件 | 问题 |
|------|------|------------|------|
| `10_行情看板.py` | 行情看板 | `render_standard_page` + 旧 `sf_card` + 板块卡**已收口** `xc_kpi_grid`（T-优化试点）+ `xc_warn_box`/`prov_badge` | 仍混用旧 `sf_card` 与 canonical；下一步清 `sf_card` 走 `chart_card` |
| `54_今日决策面板.py` | 决策（对标 QuantDinger） | `render_standard_page` + `decision_view.*` 委托 + `xc_info/success/warn_box` + `ss_hover_preview` | 渲染在 `decision_view` 内，需单独审计该模块是否统一；密度尚可但视觉未达 QuantDinger 专业感 |
| `90_登录.py` | 登录/落地（对标 PandaAI） | **自定义 `.al-*` 样式**（al-hero/al-brand-card/al-badge）+ `xc-*` 盒子 | 登录页走自己一套 `al-*` CSS，未复用 ui_kit；与 PandaAI 黑白风可对齐，但当前是紫渐变非黑白 |

### 3.3 核心结论：不是「没设计系统」，而是「设计系统未统一落地」
- ✅ 底层令牌、Bento 卡、hero、错误卡、表格等**基元已齐备**（`.xc-*`）。
- ❌ **采用极不统一**：旧 `sf_*`、自定义 inline HTML（板块卡）、`al-*` 登录样式、`decision_view` 委托渲染 四套并存。
- ❌ **信息密度与参考图差距大**：参考图（尤其 QuantDinger）是高频密集终端，当前大量页面用 `st.columns`+`st.metric` 散装，未用自适应 Bento 网格。
- ❌ **深色强调色错配**：现有深色是靛紫，QuantDinger 是琥珀橙；若选深色方向需新增/切换强调色令牌。
- ❌ **导航**：当前是 Streamlit 默认侧栏（`pages/` 编号列表），与 QUBE/QuantDinger 的「分组导航 + 图标侧栏」差距大。
- ⚠️ **A股色一致性**：`ui_theme` 的 `--buy/#009e60(绿)`/`--sell/#dc2626(红)` 与 `ui_kit --ss-up(红)/--ss-down(绿)` 命名/语义需对齐核对（订单侧 vs 涨跌侧）。

---

## 4. 参考图 ↔ 现状 映射与差距

| 参考图 | 最匹配的 StockSignal 页 | 现状差距 |
|--------|----------------------|---------|
| QUBE 行情 | `10_行情看板`、`24_个股研究`、`57_市场全景` | 缺三栏布局、黑胶囊选中态、Bento 板块卡；当前用 sf_card+自定义 HTML |
| QuantDinger 深色终端 | `54_今日决策面板`、`30_策略回测`、`41_组合收益`、`45_持仓中心` | 缺深色琥珀橙强调、双排 KPI、状态色竖条、密集表格；当前深色为靛紫且密度不足 |
| PandaAI 黑白注册 | `90_登录`、`96_新手教程` | 当前登录页是紫渐变 `al-*`，未用黑白单色+像素插画 |

---

## 5. 设计令牌（已有 vs 需补）

### 5.1 已有（`.ss-*` / `--ss-*` 在 `ui_kit`，`--card/--txt/--bg` 在 `ui_theme`）
- 颜色令牌齐全（bg/card/text/border/accent/up/down/ok/warn/danger）。
- 间距栅格 `--ss-space-1..6`（4/8/12/16/20/24）、圆角 `--ss-radius 12px / --ss-radius-card 16px / --ss-radius-pill 999px`、阴影、字体（CJK 栈 + 等宽数字）。
- **缺口**：深色强调色硬编码靛紫，无「琥珀橙」选项（QuantDinger 方向需补 `--ss-accent-amber` 或切主题 accent）；浅色缺「黑胶囊」语义色（QUBE 方向需 `--ss-capsule-bg:#111`）。

### 5.2 需补（按老板选的方向）
- 若选**深色（A）**：新增琥珀橙强调令牌，替换靛紫；强化状态色竖条/橙实心按钮规范。
- 若选**浅色（B）**：新增黑胶囊选中态令牌（黑底白字）；强化白卡 1px 边 + 大圆角 + 近无阴影的克制风。
- 若选**双主题（C）**：以上两者都做 + `apply_theme(dark/light)` 切换。

---

## 6. 组件规范化（基于已有 ui_kit 收敛，不另起炉灶）

| 动作 | 内容 | 红线 |
|------|------|------|
| 统一 KPI | 全站弃用 `st.metric`/`sf_metric`，改 `xc_kpi_grid`（自适应 Bento，A股红涨绿跌语义色） | 改 primitive 不迁调用点 |
| 统一卡片 | 弃用 `sf_card` 与自定义 inline HTML 卡（如板块卡），改 `.xc-card` | 同上 |
| 统一 hero | 弃用 `al-hero`/`render_standard_page` 自定义头，改 `ui_kit.page_hero`（首帧兜底已做） | 同上 |
| 统一表格 | 密集页改 `.ss-table-wrap`（粘性表头/斑马纹/红绿着色） | 同上 |
| 统一错误/提示 | 弃用原生 `st.error`，全走 `xc_error_box`/`xc_handle_error`（异常只进日志） | 诚实语义 |
| 新增（按需） | 状态色竖条（策略/持仓卡）、橙实心按钮、黑胶囊（浅色选中态） | 写入 `_KIT_CSS` 单点 |

---

## 7. 页面重构清单（基于真实 86 页，按类型分组）

| 分组 | 代表页 | 目标方向 | 参考 |
|------|--------|---------|------|
| 落地/登录 | `90_登录`、`96_新手教程`、`83_分析规则库` | 黑白单色 + 像素插画（PandaAI） | PandaAI |
| 行情/看板 | `10_行情看板`、`57_市场全景`、`59_市场温度计`、`56_市场状态机` | 三栏 + Bento 板块卡 + 黑胶囊（浅）/ 深色密度（深） | QUBE/QuantDinger |
| 决策 | `54_今日决策面板`、`24_个股研究`、`98_仓位落地`、`40_仓位管理`、`99_决策问答` | 双排 KPI + 密集表 + 状态徽章 + 深色专业感 | QuantDinger |
| 回测/组合 | `30_策略回测`、`41_组合收益`、`42_模拟交易`、`43_实盘交易`、`45_持仓中心` | 深色指标卡 + 红绿表格 + 状态竖条 | QuantDinger |
| 分析与选股 | `11/21/31/32_选股`、`71_因子分析`、`72_六维评分`、`73_自定义看板`、`22_基本面`、`17_市场魔方` 等 | Bento 卡网格 + 图表卡 + 高密度 | QUBE/QuantDinger |
| 情绪/广度 | `50_市场情绪`、`61_广度分化`、`62_动量广度共振`、`63_温度回测`、`65_周期时钟` 等 | 温度计/时钟可视化 + KPI | QuantDinger |
| 用户/系统 | `91_我的`、`92_用户管理`、`93_系统配置`、`94_消息中心`、`95_数据导出`、`97_决策回放` | 表单/列表现代化 | 三者通用 |

> 改完任一页后须重跑 `scripts/gen_portfolio_page.py` + 同步 `docs/index.html`/README/`docs/promo-*.md`/`docs/publish-kit/*.md`（守卫 `test_public_numbers_consistency.py`）。

---

## 8. 已知问题修复

| 项 | 状态 | 说明 |
|----|------|------|
| 图4 错误条长文本溢出 | ✅ **Phase 0 已完成** | `90_登录.py` 改 `xc_error_box`+`st.code(language="bash")`（自带复制），异常只进日志 |
| 错误卡无复制命令 | ✅ 已完成 | `st.code(language="bash")` 原生复制按钮 |
| 组件混用（sf_*/al-*/自定义HTML） | ⬜ 待 Phase 1+ | 见第 6 节统一规范 |
| 深色强调色错配（靛紫 vs 琥珀橙） | ⬜ 待方向拍板 | 见第 5.2 节 |

---

## 9. 实施分阶段（「慢慢改善」）

- **Phase 0（已交付）**：图4 错误条修复（纯 CSS + 复制按钮）。
- **Phase 1（令牌+基件）**：在 `ui_kit._KIT_CSS` 按方向补令牌；新增缺的基元（状态竖条/橙按钮/黑胶囊）；确保守卫不回退。
- **Phase 2（导航+布局骨架）**：按方向改导航（图标侧栏/分组/黑胶囊）；统一页面容器。
- **Phase 3（逐页标准化）**：按第 7 节分组，先落地/行情，再决策/回测；每页改完跑守卫 + 同步规模数字。
- **Phase 4（主题/响应式）**：若选 C 做 `apply_theme` 切换；补窄屏适配。

---

## 10. 待老板拍板（基于审计，不早下结论）
1. **主方向**：A 深色靛紫→切琥珀橙终端（推荐贴合量化定位）/ B 浅色极简+黑胶囊 / C 双主题。
   - 注意：当前深色已是靛紫，**选 A 需把强调色从靛紫换成琥珀橙**才像 QuantDinger；选 B 则强化黑胶囊浅色。
2. **优先级**：先改哪一组页面（落地页/行情页最显眼，建议先动）。
3. **是否接受 Phase 1 先做**：统一令牌+基元是后续所有页的地基，风险低，可先于逐页改造开工。


---

## 5. 老板拍板与实施记录（2026-10-28）

### 5.1 拍板结论
- **默认主题**：暗色终端（原默认浅色已翻 dark；浅色保留为可切换副主题）。
- **身份色**：维持靛紫 `--acc1:#4f46e5 / --acc2:#7c3aed`（零风险，不动令牌）。
- **实施范围**：B 旗舰页优先（10·54·24·36）。

### 5.2 已落地改动
1. **全局暗色默认**：翻转 6 处 `theme_mode` 回退值——`ui_theme.py` 的 `_theme_is_dark`/`get_current_mode`/`apply_page_config` setdefault、`session.py` 的 setdefault/`_current_prefs`、`pages/91_我的.py` 的 setdefault/`_SETTINGS_KEYS`、`modules/visualizer.py` 回退。浅色预设(swiss/ink)与风格切换逻辑不变；用户已存 localStorage 的 light 偏好仍优先生效。
2. **组件收敛（B 旗舰页）**：散装 `st.metric` 收口到 canonical `xc_kpi_grid`（A股红涨绿跌语义一致，消除 `st.metric` 默认涨绿跌红回退）：
   - `36_每日荐股.py`：11 处 → `xc_kpi_grid`。
   - `54_今日决策面板.py`：5 卡（分周期命中率循环 + 回测摘要） → `xc_kpi_grid`。
   - `11_股票选取.py`（"24"快速选取子页）：Block1 价格 KPI + Block4 RSI/MACD/KDJ/BOLL 指标 → `xc_kpi_grid`。
   - `10_行情看板.py`：板块卡试点已落地（前序）。
3. **守卫**：`test_ui_design_system.py` 5/5 通过；`test_pages_smoke.py` 全绿。

### 5.3 待确认 / 递延（非 B 安全范围，需老板另行拍板）
- **20_个股研究（深度分析子页）**：大量自定义 `sf-*` 原始 HTML（评分环/因子清单/新闻情绪条等），已是主题化旧体系；全量迁移为 `xc-*` 需专属重写，超出 B 安全范围。
- **11_股票选取 Block2/3（评分卡/技术报告卡）**：带粗体标题 + 🟢强势/偏弱 caption 的结构化报告卡，非纯 KPI 网格，需布局重排。
- **导航重构（分组图标侧栏）**、**登录页 `al-*` → 黑白 PandaAI 风**：更大范围，不在 B 内。
