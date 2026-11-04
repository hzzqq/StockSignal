# StockSignal UI 整体体检报告（68 页）

> 由 UI 全栈专家团产出：视觉设计架构师（视觉审计）+ 体验设计师（UX 审计）+ 前端工程师（落地校验）。
> 范围：StockSignal 全站 68 业务页（Streamlit 应用，Python + 内联 CSS）。**本轮只出报告与规范，不改代码。**
> 诚实红线：所有问题均附真实 `文件:行号` 证据，无臆造。

> ## ⚠️ 勘误（2026-11-03 复核）：原 P0「语义色双轨 = 合规事故」为**误报，已撤回**。
> 经核对 `ui_theme.py:579` 注释与 `stock_research.py`/`pages/13` 实际引用：**交易屏（54/57/58）正确采用 `--ss-up:#ff4d4f`(红涨)/`--ss-down:#00d486`(绿跌)，未用 `.sf-` 类，A 股铁律未被违反**。`ui_theme.py:433` 的 `.sf-doc-up`(绿)/`.sf-doc-down`(红) 仅用于 `stock_research.py` 个股深度分析**报告体**与 `pages/13`，属有意的「报告绿涨红跌」双轨，非 bug。`--buy/--sell` 在 `starfield_theme.py:28`(红涨) 与 `ui_theme.py` docs 域(绿涨) 语义相反，是**命名隐患**（P2），不是反向显示。下文 P0 已降级重分类，落地方案同步修正（改名非删除）。

## 0. 结论先行

StockSignal 在**标准化入口、导航守卫、诚实降级、回到顶部、图标唯一**上已达专业水准，是可信金融终端的合格底座。

**最大扣分项（重分类后）**：**P1 组件词汇分裂 + 错误态泄露**（UX3/UX4）——最影响「可信金融终端」观感且最易修复的真实问题。其次 **P1/P2：页面硬编码 hex（UX2）、语义色命名隐患（A2/A3）**。原 P0「语义色反向」经复核不属实，已撤回。

## 1. 视觉审计（视觉设计架构师）

| # | 问题 | 证据 | 影响 |
|---|---|---|---|
| A1 | 令牌定义散落三处、cascade 脆弱 | `ui_theme._DARK_CSS`(ui_theme.py:54)、`ui_kit._TOKEN_CSS`(ui_kit.py:44)、`dashboard_sf_css`(ui_theme.py:208) 各写一套 `:root` | 改色未必全站生效，易回归 |
| A2 | 语义色命名不一致（非反向显示） | `--buy/--sell` 在 `starfield_theme.py:28`(红涨) 与 `ui_theme.py:209,211` docs 域(绿涨) 语义相反；`.sf-doc-up{color:var(--buy)}`(ui_theme.py:433) 仅用于报告体 | 命名隐患：同 token 不同语义易误用；交易屏未反向，非合规事故 |
| A3 | 品牌色常量漂移 | `colors.py BRAND_ACCENT=#4f46e5`(colors.py:32)、`ui_theme --brand-1=#5b53f0`、`.ss-accent fallback=#667eea` 三处不一致 | 换色需改 3+ 处且易漏 |
| A4 | 页面内联硬编码色（dark/light 双份） | `widgets.py:298` `name_color='#e2e8f0' if dark else '#111827'`；`widgets.py:327` 字面量 `#ff4d4f/#00d486`；`pages/57:24`、`pages/58:29` 各自硬编码 STATE_COLORS/LEADER_BAND_COLOR | 主题切换断色、维护灾难 |
| A5 | 圆角 16/18 并存 | `--ss-radius-card:16`(ui_kit.py:51) vs `.sf-card:18`(ui_theme.py:215)、`.xc-hero:18`(ui_kit.py:209) | 卡片观感不齐，弱 Bento 感 |
| A6 | 间距未落在 4px 阶梯 | 令牌含非标 20px(ui_kit.py:52)；页面大量 10/14/18/22px 散值(`ui_kit.py:229` gap14、`ui_theme.py:215` margin18) | 栅格不齐 |
| A7 | 等宽数字未全量 | 仅 `.ss-stat/.xc-card .value` 挂 Fira Code(ui_kit.py:98)；`pages/57:90`、`pages/58:48`、`widgets.py:327` 数值位未挂 | 列对齐差，终端感打折 |
| A8 | 胶囊/状态点双轨、深浅硬编码 | `_nav_active_css` 写死 `#FFD166/#FF8C00`(widgets.py:1022)、指数卡写死 `#ff4d4f/#00d486`(widgets.py:327) | 主题下硬编码金/橙边违和 |
| A9 | 深色阴影近乎不可见 | `--ss-shadow-card:rgba(15,15,35,.06)`(ui_kit.py:53) 在深底 `#0f0f23` 无存在感；深底卡层级靠 `#2d2d44` 边对比极低 | 卡片易糊成一片 |
| A10 | st.metric 死 CSS 残留 | `ui_theme.py:381` 仍 card-ify `[data-testid="stMetric"]`，与「st.metric 已清零」声明矛盾 | 防御性死规则，易误导 |

## 2. UX 审计（体验设计师）

### 2.1 导航与信息架构

| # | 问题 | 证据 |
|---|---|---|
| IA-1 | 「市场广度·温度」过载同质化（5 子簇 22 项，核心恰顶格 8 项） | `widgets.py:691-701` |
| IA-2 | 量化选股混入异质子项（回测/因子/投研本质是研究） | `widgets.py:736-745` |
| IA-3 | 自然语言选股(81) 类目错配 + 语音事件(87) 入口离散 | `widgets.py:768,776` |
| IA-4 | 决策/全景/状态机/情绪四页互相跳成迷宫 | `57:126-128`、`58:200-203` 互嵌 `st.page_link` |
| IA-5 | 社区功能分散 + 星辰AI 双暴露（导航+顶栏弹层） | `widgets.py:771`、`widgets.py:545` |
| IA-6 | 合并页缺面包屑/返回指示 | `widgets.py:727-728,749,917` |
| IA-7 | 命名中英混用（25_QuantAgent投研、55_P1量化信号） | 非阻断 |

### 2.2 跨页 UX 通病

| # | 通病 | 证据 |
|---|---|---|
| UX1 | 语义色命名不一致（交易屏未反向） | `ui_theme.py:209-211,433-434,585,681,760,842,940`（`--buy/--sell` 红绿语义跨域相反）；54/57/58 交易屏改用 `--ss-up/--ss-down` 正确 | 命名隐患，非反向显示；降级 P2 |
| UX2 | 内联硬编码色泛滥（33 页含字面量 hex） | `54:281`、`57:24-27`、`58:29-35` |
| UX3 | 组件词汇双轨（legacy `section_header`/`info_banner`/`.ss-hero` vs `xc_*`） | legacy `section_header` 14 页用；`.ss-hero` deprecated 仍在 |
| UX4 | 错误态不统一 + 裸异常泄露 | 33 页 `st.error/st.stop`；`14:301/408/483/536` 甩异常对象；`32:191`、`25:288` 拼内部错误进文案 |
| UX5 | 圆角 16/18 并存 | `ui_theme.py:215/808`、`ui_kit.py:209/365`、`stock_analysis_helpers.py:485/613` |
| UX6 | 表格无分页（30 页 `st.dataframe`，81 可上千行直渲） | `81:254` |
| UX7 | 固定列布局，移动端未适配（15+ 页 `st.columns(3-6)`） | 12/22/23/30/32/33/44/50/53/54/67/71/84/93/99 |
| UX8 | 加载/空/错三态不闭环 | `st.spinner` 仅 27 页；空态 `_empty_info`/`st.caption("暂无")` 非统一 |
| UX9 | 内联 HTML 卡片/表格无障碍缺口 | `54:401,507`、`57:89`、`58:147` 裸 `<div>/<table>` |
| UX10 | 长提示/口径注脚风格不一 | T-277 `_hint_html` 已引入但非全站 |

## 3. 优先级清单（合并视觉 + UX）

| 级别 | 条目 | 关键证据 |
|---|---|---|
| **P1 高** | 页面内联硬编码色（33 页），深浅断色 | `54:281`(红涨绿跌正确但硬编码)、`57:24-27`、`58:29-35` |
| **P2 中** | 语义色命名隐患：`--buy/--sell` 跨域语义相反 | `starfield_theme.py:28`(红涨) vs `ui_theme.py:209,211`(绿涨)；改名 `--doc-up/--doc-down` 消除歧义，勿删（会破坏报告体渲染） |
| **P1 高** | 组件词汇双轨（legacy vs `xc_*`） | 14 页 legacy `section_header`；`.ss-hero` deprecated |
| **P1 高** | 错误/加载/空态不闭环 + 裸异常泄露 | 33 页 `st.error/st.stop`；`14:301` 等 |
| **P1 高** | 圆角 16/18 并存 + `st.metric` 死 CSS 残留 | `ui_theme.py:215/808`、`ui_kit.py:209/365` |
| **P1 高** | 等宽数字未全量 | `54:509` 仍内联 `font-family:monospace` |
| **P2 中** | 表格无分页（81 可上千行） | `81:254` |
| **P2 中** | 固定列移动端未适配 | 12/22/23/30/32/33/44/50/53/54/67/71/84/93/99 |
| **P2 中** | 内联 HTML 无障碍缺口 | `54:401`、`57:89`、`58:147` |
| **P2 中** | IA 重叠/错配（81 错配+87 离散；四页互跳） | `widgets.py:768,776`；`57:126`、`58:200` |
| **P3 低** | 页脚口径注脚风格不一 | B 类页有、其余无 |
| **P3 低** | 3 页 `if __name__=='__main__'` 包裹(25/81/82) | `81:265`、`25:380`、`82:202` |
| **P3 低** | 社区功能分散；命名中英混用 | `widgets.py:771-776` |

## 4. 落地边界

- **P0 语义色清零**：全局搜 `--buy/--sell` 与页面 hex → 替换为 `--c-up/--c-down` / `colors.*`；扩展 `test_updown_color_semantics` 守卫生效页面层（详见《设计系统统一文档》§2）。
- 所有改造须经对应守卫（st.metric 已禁、涨跌语义、组件词汇、a11y 对比度），每阶段独立 PR。
- 完整落地方案见配套文档 `design_system.md`。
