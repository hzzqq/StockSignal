# frontend-v2 设计规范 · 轻量卡片流

> 本文件是 `src/styles/tokens.css`（令牌单一真理源）与各组件的**设计说明**。
> 代码注释中引用的 `DESIGN.md §2 / §4 / §5` 即指本文件；此前文件缺失（文档漂移），2026-11-07 补齐。
> 守卫：`tests/unit/design-language.test.tsx`（真扫源码 + 渲染 DOM 双重验证，防回退）。

---

## §1 视觉方向：轻量卡片流（暗色）

老板 2026-11-07 拍板方向。frontend-v2 是**暗色主题**（`sf-bg #0f0f23`），
「轻量」不是改成亮色，而是：

| 原则 | 做法 | 反例（已清除） |
|---|---|---|
| **扁平** | 实色表面 + 1px hairline 边框 + **零阴影** | 半透明叠色 `bg-sf-bg/40` |
| **低色差** | 卡片 `#16162c` 仅比底色略亮，几乎融为底 | 层层套色块、重渐变 |
| **留白** | 卡片 `p-5`(20px)、流间距 16px、标题与内容 `mb-4` | 塞满、靠边框切分 |
| **克制强调** | 只在激活指示条 / 焦点环 / 数据涨跌系列上用高饱和色 | 整卡高亮、绿底错误框 |
| **顺流** | `.flow`（flex column, gap 16px）统一节奏 | 各页散落 `space-y-4` |

卡片像「纸张顺流而下」，层级靠**留白 + 文字三级 + 细线**，不靠装饰。

---

## §2 设计令牌

### §2.1 色彩语义（三条互不混淆的线）

| 语义线 | 令牌 | 值 | 用途 | 禁止 |
|---|---|---|---|---|
| **A股交易屏** | `ss-up` / `ss-down` | `#ff4d4f` / `#00d486` | 价格涨跌、涨跌家数系列 | 表达错误/新鲜度/强弱 |
| **报告体价格域** | `doc-up` / `doc-down` | `#009e60` / `#ff4d4f` | 报告页/个股页（绿涨红跌） | 与交易屏混用 |
| **数据状态** | `sf-ok` / `sf-warn` / `sf-danger` | `#5bb98c` / `#e5a54b` / `#e06c75` | 新鲜度、告警、错误 | 被当成涨跌色 |

**历史缺陷（已纠正）**：`FreshnessBadge` 曾用 `ss-up`(红)=「数据新鲜」、
`ss-down`(绿)=「数据陈旧」，方向与 A 股价格语义恰好拧反；`ErrorState` 曾用
`ss-down`(绿) 表示错误。现全部改用状态色 + `role=status/alert`，且带形状点，
**不依赖单一色彩通道**传达信息。

> 注：全站 `--ss-up/--ss-down` 红涨绿跌、`--doc-up` 绿涨红跌 是项目硬红线
> （`test_colors.py` / `test_ui_design_system.py` 锁），本规范不改动其值。

### §2.2 文字三级（WCAG 对比度已量化，不拍脑袋）

底色 `sf-surface #16162c`。旧实现用 `text-sf-txt/30~80` 透明度混合，
实际颜色随底漂移、无法量化；现改**实色**三级：

| 令牌 | hex | 对比度 (on surface) | 级别 | 用途 |
|---|---|---|---|---|
| `sf-ink` | `#e2e8f0` | **14.37:1** | AAA | 主文、KPI 数值 |
| `sf-ink-2` | `#a8b2cc` | **8.36:1** | AAA | 次文、卡片标题、正文 |
| `sf-ink-3` | `#7c86a3` | **4.89:1** | **AA 达标** | 弱文、标签、脚注 |

WCAG AA 正文要求 ≥4.5，三级全部达标（最弱的 `sf-ink-3` 在内嵌块
`surface-2` 上仍有 4.51:1）。`sf-warn` 8.28:1、`sf-ok`/`sf-danger` 亦远高于 3:1。

### §2.3 表面 / 结构

| 令牌 | 值 | 用途 |
|---|---|---|
| `sf-bg` | `#0f0f23` | 页面底 |
| `sf-surface` | `#16162c` | 卡片 |
| `sf-surface-2` | `#1d1d38` | 内嵌块 / Stat / 导航激活 |
| `sf-line` | `#26263f` | hairline 边框（细、低对比但可辨） |
| `radius-card` | `14px` | 卡片 |
| `radius-tile` | `10px` | 内嵌块 / Stat / 徽标 |

### §2.4 字号阶梯

| 令牌 | px | 用途 |
|---|---|---|
| `text-kpi` | 22 | 指标数值（`tabular-nums` 等宽防抖动） |
| `text-page` | 18 | 页标题 |
| `text-title` | 14 | 卡片标题 |
| `text-body` | 13 | 正文 |
| `text-label` | 12 | 标签 / 脚注 |

旧实现散用 `text-xs/sm/lg/xl`，现统一到上表。全站 **48 处** `text-sf-txt/*`
已收敛（12 个页面），零残留由守卫锁定。

---

## §3 布局与导航

- `.flow` = `flex column + gap 1rem`，页面根容器统一节奏。
- 栅格 `grid-cols-2 md:grid-cols-4 gap-3`：窄屏 2 列，不挤压。
- 侧栏：**<768px 收为 56px 图标栏**（CSS 隐藏 `.nav-label`，`title` 属性保留可读性），
  ≥768px 展开 224px。内容区 `p-4 md:p-6`。
- 导航激活态由 TanStack Router 写入 `aria-current="page"`，CSS 用
  `inset 2px 0 0 sf-accent` 画左侧细指示条——**不占布局宽度、不位移**。
- 全局 `:focus-visible` 焦点环 + `prefers-reduced-motion` 降级。

---

## §4 分包与预算

`vite.config.ts` 用 `manualChunks` 把 `echarts(+zrender)` / `@tanstack` 独立成块；
`EChart` 组件动态 `import('echarts')`，仅图表挂载时拉取。
2026-11-07 构建实测：主包 342.86 kB / **gzip 102.06 kB**，
`echarts` 独立 1124 kB / gzip 373 kB（懒加载，不进首屏）。

---

## §5 无障碍

| 项 | 落地 |
|---|---|
| 图表 canvas | `role="img"` + `aria-label`（逐图具体描述）+ `sr-only` 文本替代；关键数值同页 Stat/脚注另给 |
| 卡片 | `role="region"` + `aria-label`（标题为 string 时） |
| 状态 | `Loading`/`EmptyState` `role=status`，`ErrorState` `role=alert` |
| 数值 | `tabular-nums` 等宽数字 |
| 状态色 | 颜色之外带形状点 + 文案，不靠单一色通道 |
| 键盘 | 全局焦点环；深链为真实 `<a href>` |
| 动效 | `prefers-reduced-motion` 降级 |

### 已知取舍（诚实标注）

- 两页互加深链用**原生 `<a href>`** 而非 TanStack `<Link>`：E2E 把
  `BreadthOverview` 无 `RouterProvider` 独立渲染，`Link` 会因缺 router context 抛错。
  代价是整页导航而非 SPA 无刷新跳转；后续若给 E2E 补 Router 上下文可升级为 `Link`。
- 侧栏窄屏收为图标栏靠 CSS 隐藏文字，`aria-label` 未逐项补——图标为 `aria-hidden`，
  链接可访问名依赖 `title`；后续可补 `aria-label={it.label}`。
- 图表 `aria-label` 是**静态描述**，不含实时数值（数值在同页 Stat/脚注，非唯一载体）。

---

## §6 诚实红线（不可破）

- 缺失数据 → `status=error` 信封 → `QueryState` 渲染「暂无数据」，**不补零、不编造**。
- Zod 严格校验，解析失败抛错，禁 `?? 0` 默认值兜底。
- MSW Mock 仅演示数值，明确标注非真实行情；生产构建不加载。
- 真实后端 E2E（5050）未实测时保持 `skipIf(!LIVE)`，不伪造成功。
