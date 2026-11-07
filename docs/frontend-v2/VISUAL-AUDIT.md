# frontend-v2 暗/亮主题 · 真实浏览器目检报告

- **日期**：2026-11-07
- **执行**：team-lead，本机 Google Chrome（headless）+ Chrome DevTools Protocol
- **工具**：`scripts/shoot_frontend_v2.py`（本轮新增）、`npm run inspect:visual`
- **产物**：`artifacts/shots/frontend-v2/<dark|light>/*.png` + `report.json`
  （本地目检产物，存 `artifacts/`，**未提交仓库**）
- **本文含两次实跑**：首次 **14/14**（W3 收口，见正文）；第二次 **18/18**（W4-A 六维评分增量，见文末「增量目检」）。
  两次都是已发生的真实目检记录，不是持续守护。

## 结论

**通过。** dark / light 两套主题 × 7 个路由共 **14/14 页**全部成功渲染并截图，退出码 0；
两条设计红线在**真实浏览器计算样式**层面 PASS。此前"仅单测 / vite build / dist CSS 真扫"
证明不了的「主题在浏览器里到底有没有真的生效」，至此闭环。

> ⚠️ 本报告是「headless 自动截图 + 计算样式采样 + 逐张目视核对」，
> **不是**多设备、多分辨率、读屏、键盘遍历或真人可用性测试；页面数据来自 MSW dev fixtures，
> 不是真实行情。见文末「未覆盖」。

## 为什么需要这一步

| 既有证据 | 能证明 | 不能证明 |
|---|---|---|
| `vitest run`（95 passed） | 源码字符串、Zod 契约、WCAG 数值实算 | 浏览器实际渲染 |
| `vite build` + dist CSS 真扫 | 亮色令牌编译进产物 | 运行时是否被正确应用 |
| **本目检** | `getComputedStyle` 实测值、canvas 图表实际配色、页面是否白屏 | — |

## 复现

```bash
cd E:/project/ks/StockSignal
npm --prefix frontend-v2 run inspect:visual
# 等价：python scripts/shoot_frontend_v2.py --start-app
```

脚本自行 headless 启动 Vite（`127.0.0.1:5180`）与 Chrome（CDP `9222`），
注入 `localStorage['ss_theme']` / `['ss_token']`（登录判据见 `src/app/guards.tsx`），
逐页导航 → 采样真实计算样式 → 截图 → 结束自动关闭两个进程。
**零 npm 依赖**（仅需 Python `websocket-client`），无需真后端、无需真账号、**未改动产品代码**。

端口选 5180 而非 5173，原因见下文「发现 1」。

## 自动断言（真实计算样式，非源码字符串匹配）

| 断言 | dark | light | 结果 |
|---|---|---|---|
| `--color-sf-bg` 两主题必须不同 | `#0f0f23` | `#f0f3f9` | **PASS** |
| `--color-ss-up` | `#ff4d4f` | `#ff4d4f` | 恒等 |
| `--color-ss-down` | `#00d486` | `#00d486` | 恒等 |
| `--color-doc-up` | `#009e60` | `#009e60` | 恒等 |
| `--color-doc-down` | `#ff4d4f` | `#ff4d4f` | 恒等 |

→ **A 股 4 个价格变量两主题恒等（light 块绝不覆盖）PASS**。

逐页另校验：`data-theme` / `color-scheme`、React 根节点非空、截图 >1KB、9 个令牌非空。
亮色实采 `--color-sf-ink #20284a`、`--color-sf-surface #ffffff`、
`--color-sf-ok #376f54`、`--color-sf-line-strong #7d8496`，与权威定案值逐项一致。

## 逐页结果（14/14）

| 路由 | dark | light | 截图字节 dark / light |
|---|---|---|---|
| `/login` | ✓ | ✓ | 13,368 / 13,420 |
| `/` 概览 | ✓ | ✓ | 84,677 / 85,193 |
| `/breadth` | ✓ | ✓ | 72,907 / 72,950 |
| `/ladder` | ✓ | ✓ | 74,293 / 74,543 |
| `/events` | ✓ | ✓ | 73,693 / 74,135 |
| `/predictions` | ✓ | ✓ | 83,554 / 83,580 |
| `/ops` | ✓ | ✓ | 100,177 / 99,831 |

## 人工目视核对（逐张看图）

- **login（暗/亮）**：登录卡片、两个输入框、按钮齐全；亮色白卡 + 深蓝文字对比清晰，无深色残留。
- **dashboard（暗/亮）**：导航 4 组、顶栏三态主题控件（深色｜浅色｜跟随系统，选中态细边框）、
  Mock 提示条、KPI 卡、仓位建议环形图、情景概率条全部正常。
  **关键发现**：亮色版图表颜色由暗色高饱和值切换为深派生值
  （红 `#ff4d4f` → `#bf3a3b`、绿 `#00d486` → `#00754a`），
  证明 `ss-theme-change` → `remapChartColors` → `setOption(notMerge)` 链路在真实浏览器生效
  ——**这一条单测与构建产物都证明不了**。
- **light/events**：免责口径「统计意义上的超额收益概率排序，非买卖指令」原样展示；
  评分分布条形图在浅底清晰、文字可读。
- **light/ops**：三个独立数据源区块齐全；负收益 `-1.88` / `-4.66` 显绿、正收益 `+4.23` 显红
  （A 股红涨绿跌语义正确）；页脚如实写明「负值与负 Sharpe 未取绝对值、回测不代表未来收益」；
  「绝对路径字段已由后端递归剔除，本页不展示」的脱敏说明也在。

轻微观察（非缺陷，不改）：`/events` 顶部「来源」KPI 卡的长文本 `P1-QuantFactor EV 事件因子`
在 1440px 视口换成两行，卡片等高未错位。

## 过程中发现并修复的问题（不掩盖）

1. **5173 的 502 根因**：本机 `Get-NetTCPConnection -LocalPort 5173` 显示**无任何监听进程**，
   响应 `upstream connect failed ... (os error 10061)` 来自沙箱外层端口代理；
   Vite 压根没启动，不是 Vite 坏了。目检改用 5180 直连绕开代理。
2. **5050 的 `data-theme="dark"` 是巧合**：Flask 自己的「后端管理」页也用了同名属性，
   并非 frontend-v2 页面；`/api/health` 正常返回 `status: ok`。
3. **脚本 `textLen < 20` 误报**：登录页文案天然只有 17 字，被误判「空壳」。
   改为组合判据「文本短 **且** 可交互元素 < 2」才判空壳，真白屏仍会 FAIL；修后 14/14。
4. **Git Bash MSYS 路径转换**：`--routes /login,/` 被转换成
   `E:/WorkBuddy/resources/vendor/PortableGit/login,/`，导致选页失效。
   `--routes` 改收**页面名**（`login,dashboard,events`），从根上避开。
5. **Chrome profile 不进仓库**：改用系统临时目录，避免浏览器缓存写入 `artifacts/`。

## 与旧脚本的分工（勿混用）

| 脚本 | 目标 | 端口 | 主题机制 | 驱动 |
|---|---|---|---|---|
| `scripts/shoot_styles.py` | 旧 Streamlit 六风格 | 8899 | `prefs=` query + `--card` | Playwright |
| `scripts/shoot_frontend_v2.py` | 新 React SPA 两主题 | 5180 | `localStorage.ss_theme` | CDP + 本机 Chrome |

旧前端仍在 8899 运行，故**保留旧脚本不改造**；两者 URL 构造、就绪判据、登录方式、输出结构全不同。

## 未覆盖 / 诚实标注

- 数据来自 MSW dev fixtures，**不经 5050 真后端**（CORS 仍不允许浏览器从 5173 直连 5050，
  `vite.config.ts` 的 `/api` proxy 是唯一正确路径）。
- headless Chrome 单视口 1440×900；未测窄屏图标栏、hover、键盘遍历、读屏、打印、Safari/Firefox。
- 图表 `aria-label` 仍是静态文本描述、不含实时数值（数值在同页指标卡与脚注）。
- 截图与 `report.json` 存 `artifacts/`，未提交；Chrome profile 存系统临时目录。
- 本报告是**已发生的一次真实目检**记录，不是持续守护；主题代码变更后须重跑
  `npm run inspect:visual` 并更新本报告。

---

## 增量目检（W4-A 六维评分，2026-11-07 第二次实跑）

新页 `/stock/six-dim` 加入 `scripts/shoot_frontend_v2.py` 的 `ROUTES`，并新增专项硬红线
`capture_sixdim_partial()`：在真实浏览器里把股票代码输入框由 `600519` 改为 `000001`
（React 受控输入用原型 setter + `input` 事件驱动），MSW 返回缺维 fixture，验收「`null` 不补 0」。

**为什么必须补这一步**：`tests/e2e/w4-six-dim.test.tsx` 把 `EChart` mock 成占位，
只能证明代码把 `null` 放进 `value` 数组，证明不了**真实 ECharts 渲染**下缺失维没被画成 0 分点；
且没有用例真正导航到 `/stock/six-dim`。

### 结果

**18/18 通过，退出码 0，4 条红线全 PASS**（16 张常规页截图 + 2 张缺维专项截图）。

| 红线 | 结果 |
|---|---|
| 两主题表面色必须不同（`--color-sf-bg`） | PASS（dark `#0f0f23` / light `#f0f3f9`） |
| A 股 4 个价格变量两主题恒等 | PASS（4/4 相等） |
| W4-A 缺维不补 0 + 真实 ECharts canvas（dark） | PASS |
| W4-A 缺维不补 0 + 真实 ECharts canvas（light） | PASS |

专项断言两主题均 True：输入框值为 `000001`、`data-theme` 正确、
`资金` / `成长` 明细为「缺失」而非数值、`技术` 维有值、`仅 4/6 维有效` 降权条可见、
`暂无权威数据日` 可见（无兜底日期）、口径 `note` 原文可见、
**真实 canvas 尺寸 `1126×300`**（非 mock 占位）、截图 >1KB。

### 人工逐张看图（不只看脚本 PASS）

- **full（600519，暗 / 亮）**：标题、代码输入、数据日「权威数据日：2026-11-07」、
  4 张 KPI（综合分 60.40 / 有效维度 6/6 / 最新数据日 / 股票代码）、六边形雷达图、六维明细齐全；
  暗色深底浅字、亮色白卡浅灰底，均无暗色残留、无白底白字、扁平细边框可见。
- **partial（000001，暗 / 亮）**：数据日如实用状态色显示「暂无权威数据日」，
  降权条「仅 4/6 维有效，缺失维未取到数据」，综合分 43.90（仅 4 维平均）、最新数据日 `—`；
  **雷达图呈「缺角」不规则多边形，资金 / 成长方向没有塌陷到圆心的 0 分点**
  —— 这是 `null` 不补 0 在真实 ECharts 下的直接视觉证据。
- 截图为 `1440×900` 视口、`captureBeyondViewport=false`，六维明细下半与「口径说明」卡片裁在视口外；
  DOM 采样已验证其内容存在（含 `note` 原文与两个「缺失」明细），属**截图边界**，不是页面缺陷。
- 顶部「演示数据（Mock，非真实行情，仅用于前端联调）」是 MSW dev 的诚实标注，保留。

### 本次增量未覆盖（如实标注）

- 仍**未走 5050 真后端**：six-dim 端点已由后端单测 21 passed 覆盖，但浏览器侧只打 MSW dev fixtures；
  真后端响应（尤其 `raw.state` 为非空字符串时）未在浏览器里联调。
- 雷达图「缺失维不补 0」由「真实 canvas 渲染 + DOM 明细为『缺失』 + 人工看图」共同佐证，
  **未直接读取 ECharts 实例的 `option.series[0].data[0].value` 数组**，不作超出证据的断言。
- 键盘遍历、读屏、窄屏、Safari / Firefox 仍未测。
