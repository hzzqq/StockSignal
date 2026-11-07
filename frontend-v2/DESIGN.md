# frontend-v2 设计规范 · 轻量卡片流

> 本文件是 `src/styles/tokens.css`（令牌单一真理源）与各组件的**设计说明**。
> 代码注释中引用的 `DESIGN.md §2 / §4 / §5` 即指本文件；此前文件缺失（文档漂移），2026-11-07 补齐。
> 守卫：`tests/unit/design-language.test.tsx`（真扫源码 + 渲染 DOM 双重验证，防回退）
> 与 `tests/unit/theme-contrast.test.ts`（**读 CSS 真值 + WCAG 实算**，防「自己写答案自己验」）。
>
> ⚠️ `docs/frontend-v2/DESIGN.md` 是 W0 **规划态**文档，已与落地事实漂移
> （`--doc-down` 值、断点档数、hover 位移、顶栏高度至少 4 处），**以本文件 + 代码为准**；
> 可引用的只有其 `data-theme` 属性 + CSS variables 口径，不是「复制两套组件」。

---

## §1 视觉方向：轻量卡片流（默认暗色）

老板 2026-11-07 拍板方向：**暗色为默认主题**（`sf-bg #0f0f23`），
亮色是**同一套轻量卡片流体系的第二套令牌**，不是另一套组件、也不是把暗色推翻
（依据：`b6516ca` 已落地的暗色基线 + 本文件 §1 原则 + 暗色对比度证据链）。
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
- 侧栏窄屏收为图标栏靠 CSS 隐藏文字，图标为 `aria-hidden`；
  2026-11-07 已给所有导航 `Link` 补 `aria-label={it.label}`，可访问名不再只靠 `title`。
- 图表 `aria-label` 是**静态描述**，不含实时数值（数值在同页 Stat/脚注，非唯一载体）。

---

## §6 诚实红线（不可破）

- 缺失数据 → `status=error` 信封 → `QueryState` 渲染「暂无数据」，**不补零、不编造**。
- Zod 严格校验，解析失败抛错，禁 `?? 0` 默认值兜底。
- MSW Mock 仅演示数值，明确标注非真实行情；生产构建不加载。
- 真实后端 E2E 默认保持 `skipIf(!LIVE)`：2026-11-07 实测 `:5050/` = 200、
  `/api/health` 信封 ok、`VITE_E2E_LIVE=1 vitest` **5/5 passed**——但这只证明
  jsdom/Node `fetch` 能打 health，**不等于**浏览器 CORS 链路或真人视觉 E2E。
  实测 5050 对任意 Origin 都不返回 `ACAO`、未启用 credentials、预检无任何 ACAO，
  浏览器从 5173 **直连** 5050 不可行，`vite.config.ts` 的 `/api` proxy 是唯一正确路径。
  默认跳过是因为 CI 不应依赖外部 Flask 进程，不是「服务返 502」；
  不把 5/5 包装成「E2E 已转正」或「CORS 已验证」。


---

## §7 亮色主题与主题切换（2026-11-07）

### §7.1 交互与持久化

- 三态偏好 `pref: 'dark' | 'light' | 'system'`，存 `localStorage['ss_theme']`；
  **首次默认 dark**（新用户无偏好时）。非法值 / localStorage 不可用一律回落 dark。
- 控件在顶栏右侧，顺序 `[主题控件] [退出登录]`，退出登录保持最右；
  `role="radiogroup"` + 3 个 `role="radio" aria-checked`，用原生 button 保证键盘可达。
- `<html data-theme="dark|light">` 作为**唯一真理源**；`color-scheme` 两态都设。
- **FOUC**：`index.html` 的 `<head>` 内联**同步普通 script**（在 module script 之前）
  读偏好 → 写 `data-theme` + `colorScheme`，React 侧初值直接读该属性、不重复 resolve。
- `system` 模式监听 `matchMedia('(prefers-color-scheme: light)')` change；
  jsdom / 无 matchMedia 环境守卫并回落 dark，不抛错。
- 主题变化时 `applyTheme` 派发 `ss-theme-change` 自定义事件，`EChart` 订阅后
  用重映射过的 option 重新 `setOption(..., {notMerge:true})`，**禁止 dispose / reinit**。

### §7.2 CSS 变量覆盖（不复制组件）

`html[data-theme="light"]` 覆盖**同名** CSS 变量， specificity 0,1,1；
不新建 `--color-*-light` 平行命名空间，组件 class 一行不改。

- 必须**显式覆盖 4 个 W0 兼容令牌** `--color-sf-card / sf-txt / sf-border / sf-grid`：
  它们被尚未迁移的旧页面使用，只覆盖新语义令牌会让这些页残留暗底。
- **绝不覆盖** `--color-ss-up / ss-down / doc-up / doc-down` 4 个 A 股语义变量：
  两主题恒等，是全站硬红线（旧体系 `docs/ui_deferred_next_round.md` D5 已定此口径）。
- 需要 ≥4.5:1 的**细字**时用 4 个增量别名 `--ss-up-ink / --ss-down-ink /
  --doc-up-ink / --doc-down-ink`（`color-mix` 派生，比例 75/55/75/75）。
  ⚠️ 别名**刻意不加 `--color-` 前缀**，避免 Tailwind 生成 `text-ss-up-ink` 类
  被 `design-language.test.tsx` 的 `includes` 子串守卫误判为「涨跌色借作 UI 色」；
  且只允许以 `var(...)` 或 palette 字面 hex 形式出现，绝不进 `FreshnessBadge.tsx`。

### §7.3 WCAG 对比度（实算，三底顺序：白卡 / s2 / 画布）

| 令牌 | 亮色 hex | 三底对比度 | 门槛 |
|---|---|---|---|
| `sf-ink` | `#20284a` | 14.35 / 13.50 / 12.91 | ≥7 |
| `sf-ink-2` | `#414c6b` | 8.50 / 8.00 / 7.65 | ≥4.5 |
| `sf-ink-3` | `#5f6a87` | 5.39 / 5.07 / **4.85** | ≥4.5（最紧） |
| `sf-ok` | `#376f54` | 5.89 / 5.55 / 5.30 | ≥4.5 |
| `sf-warn` | `#8a5300` | 6.33 / 5.96 / 5.69 | ≥4.5 |
| `sf-danger` | `#b02a3a` | 6.48 / 6.10 / 5.83 | ≥4.5 |
| `sf-accent` | `#4657c8` | 6.07 / 5.72 / 5.46 | ≥3（焦点环） |
| `sf-line-strong` | `#7d8496` | 3.74 / 3.52 / 3.37 | ≥3（非文本控件边界） |
| `sf-line` | `#dbe0ec` | 1.32 / 1.24 / 1.19 | 装饰性 hairline，1.4.11 豁免 |

暗色基线不变：hairline 下限锚点 **1.21:1**；暗 `sf-line-strong #6a7194`
在三暗底 3.71 / 3.43 / 3.96。

**状态色必须双主题分别定义**：亮色深状态色只能写在 light 块内。
把亮色深值放到暗实色底上只有 2.52 / 2.38 / 2.41（全崩），
而暗色原状态色 `#5bb98c / #e5a54b / #e06c75` 在暗实色底上是 6.34 / 7.03 / 4.90（全达标）。
因此暗色侧**只把 `/10` 半透明换成实色等价底 `-soft`（`#1d2636 / #2b242f / #2a1f33`），
状态色文字一字不动**——由 `mixOver()` 的 RGB 距离 ≤2 守卫证明是视觉等价替换。

**撞色矩阵**：`sf-ok #376f54` 与两个价格绿距离 56.2 / 56.7（候选 `#1d704f` 仅 29.8/30.4，作废）；
`sf-danger #b02a3a` 与价格红 `#bf3a3b` 距离 22.0（候选 `#c0363f` 仅 5.7 几乎同色，作废）。
守卫锁 `min RGBdist ≥ 20`、`sf-ok` 与两个价格绿各 ≥50。

### §7.4 canvas 域例外（渲染域差异，**不是**语义差异）

ECharts 是 canvas，吃不到 CSS 变量，故 `palette.ts` 独立维护 `CHART` / `CHART_LIGHT`。
`CHART` 暗表 9 组 hex **一字不动**（`design-language.test.tsx` 逐项锁）。

`CHART_LIGHT.up/down/docUp/docDown` 用**同色相深派生值**
`#bf3a3b / #00754a / #007648 / #bf3a3b`，原因：亮底上 `#00d486` 仅 **1.95:1**，
不满足 WCAG 1.4.11 非文本 ≥3:1；派生后 H 色相不变（|ΔH|≤1°，
8-bit 舍入微漂故判据用 ≤1° 而非 `===`），`LadderResonance` 的
`ariaLabel`「高板位红色、低板位绿色」描述的是**色相族**，不失真。

> ⚠️ 这是 **canvas 渲染域**为达标而做的明度调整；CSS 价格域 4 个变量两主题恒等。
> 两者 hex 不同**不代表语义不同**，不得据此把派生值「修」回原值（反向守卫会拦）。
> `docUp` 写死字面 hex `#007648`，不在运行时算 color-mix：
> Python 银行家舍入与 JS `Math.round` 在 75% 处有 1/255 差异（`#007648` vs `#007748`）。

`CHART_LIGHT.warn/ok/danger` 逐项等于亮色深状态色；
`CHART_LIGHT.docDown === CHART_LIGHT.up`（双语义同源）。
`remapChartColors(option, theme)` 递归把 option 里等于 CHART 暗 hex 的字符串替换为亮值，
涨跌系列因此自动适配，页面组件无需逐个改。

### §7.5 状态色徽标与作用域

- `FreshnessBadge` 从 `bg-sf-ok/10` + `border-sf-ok/30` 收敛到
  `bg-sf-ok-soft` / `bg-sf-warn-soft` / `bg-sf-danger-soft` + `border-sf-line`：
  这是**回归 §1「扁平实色、零半透明叠色」原设计意图**，不是新增风格。
  新令牌名统一含 `sf-ok/sf-warn/sf-danger` 子串（守卫靠 `toContain`）。
- `sf-line-strong` **只用于交互控件边界**（ThemeToggle 选中态）；
  `Card.tsx` / `Stat.tsx` / `.flow` 根 / 卡片根一律 0 次出现，防视觉变重。

### §7.6 已知取舍（诚实标注）

- 图表 `aria-label` 两主题**相同**（描述色相族，不随明度变化），仍是静态描述、
  不含实时数值；数值在同页 Stat / 脚注，非唯一载体。
- 等价 `<table>` 文本替代列为 **P2，本轮不做**，保留 `role=img` + `sr-only` + Stat。
- 未新增第 5 种 `degraded` 状态，继续用 `FreshnessBadge` 表达数据新鲜度。
- `system` 模式在 jsdom 无 `matchMedia` 时回落 dark，这是测试环境守卫，不是产品行为缺失。
- 亮色主题**未做真人浏览器目检**（5173 实测 502、vite dev 未起）；
  WCAG 达标是 CSS 真值实算结论，不等于视觉验收通过。
