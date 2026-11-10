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


## 增量目检（W4-B 个股域 + 深链，2026-11-07 第三次实跑）

`ROUTES` 扩到 **10 条**（新增 `/stock/research`、`/stock/fundamentals`），新增 `DEEPLINK_CASES` **5 条**专项用例与 `capture_deeplink_case()`；专项走 `Page.navigate` 后轮询 16s 读**最终** `location.search`，逐条断言目标路径、必须 / 禁止出现的 search 字面量、主题令牌与真实截图。单页 `--routes` 冒烟不跑专项，避免误测。

### 结果

**32/32 通过、退出码 0、全部红线 PASS**：10 常规路由 × 2 主题 = 20，sixdim partial × 2 = 2，5 深链专项 × 2 = 10。

| 红线 | 结果 |
|---|---|
| 两主题表面色必须不同（`--color-sf-bg`） | PASS（dark `#0f0f23` / light `#f0f3f9`） |
| A 股 4 个价格变量两主题恒等 | PASS（4/4 相等） |
| W4-A 缺维不补 0 + 真实 ECharts canvas（dark / light） | PASS（canvas `1126×300`） |
| 防伪码 `pick_stock=000001` 透传且 URL 不含 `600519`（dark / light） | PASS |
| 深链直达 `view=deep&code=600519`（dark / light） | PASS |
| 旧链接中文 `hub_gyj_view` 映射 deep + `code=600519`（dark / light） | PASS |
| 只传 `pick_stock` 落 quick + `code=600519`（dark / light） | PASS |
| 非法 code 不进入最终 search（dark / light） | PASS |

### 过程中发现并修复的真缺陷（不掩盖）

第一次 W4-B 全量目检为 **26/30、exit 3**：`legacy_zh_deep` 与 `legacy_pick_only` 暗 / 亮各 FAIL，实际 URL 为 `?view=deep` / `?view=quick`，合法 `code` 丢失；`deeplink_deep` 与 `legacy_bad_code` 反而 PASS。
`view` 全对、`code` 全丢 → 排除纯函数与目标 `validateSearch`；真读 `@tanstack/router-core@1.170.46` 后定位为默认 `parseSearchWith(JSON.parse)` 把纯数字代码解析成 number，被 `typeof === 'string'` 拒收。修复为全站 `URLSearchParams` 字符串序列化（见 `IA-MIGRATION.md` W4-B 豁免 §5），并补 8 例运行时集成测试。修复后重跑即 **32/32**。
**防伪用例的局限（如实标注）**：`000001` 因前导零绕过 `JSON.parse`，本身**并不能抓到该缺陷**；真正抓到的是 `600519` 那两条。故防伪用例只用于堵「硬编码默认代码蒙混」，不能替代纯数字 code 回归。

### 人工逐张看图（不只看脚本 PASS）

- **`/stock/research`（暗 / 亮）**：标题「个股研究」、数据源 `stock-kline`、代码 `600519`、「⚡ 快速选取」选中、权威数据日 `2026-11-06`、OHLC 表 3 行（`date/open/high/low/close/volume`）、note 原文「逐字段独立取数、独立降级；缺失为 null 且不补 0」；暗色深底浅字、亮色白卡浅灰底，均无暗色残留、无白底白字、扁平细边框无阴影。
- **`/stock/fundamentals`（暗 / 亮）**：6 张 KPI（贵州茅台 / 白酒 / 1523.50 / PE 28.10 / 总市值 19138.20 / `priceDomain market`）+ 9 项业绩指标 +「多期财报（三表合并）」2 行；数据日、行情快照日、K 线数据日**分行**展示，无「今日」措辞；营收 / 净利标签为「较上一报告期 %」，未写成「同比」；两条出边链接可见；无补 0 假数值。
- **`legacy_zh_deep`（暗）**：代码 `600519` 保留，主体显示「深度分析子视图待 W4-C 迁移，当前仅完成深链预选」+「已预选 code：600519」，**不造假数据、不画空图**。
- **截图像素级重复是真实状态相同，不是复制充数**：`legacy_pick_only` 与 `research`、`legacy_zh_deep` 与 `deeplink_deep` 分别 md5 相同（同一最终状态同一渲染）；`code=000001` 的 `legacy_pick_custom` md5 独立，反证截图随状态变化。32 张截图 md5 分布已真扫核对。
- 顶部「演示数据（Mock，非真实行情，仅用于前端联调）」是 MSW dev 的诚实标注，保留。
- `artifacts/shots/frontend-v2/_chrome_profile/` 为 **16:55 的历史遗留**（本轮 report 23:30），脚本现用 `tempfile.gettempdir()`，本轮未往仓库写浏览器缓存；该目录 gitignored。

### 本次增量未覆盖（如实标注）

- 仍**未走 5050 真后端**：3 个新端点由 `backend/tests/test_read_routes.py` 39 例 + OpenAPI / API 契约守卫覆盖，浏览器侧只打 MSW dev fixtures；`CORS_ORIGINS` 默认不含 5173，真后端浏览器联调需走 Vite `/api` proxy 另开一轮。
- 24 deep 完整内容、21 多股对比、ECharts K 线图属 W4-C，本波**未实现**，占位文案已如实标注。
- 截图为 1440×900 单视口、`captureBeyondViewport=false`，口径说明卡片等下半内容裁在视口外；DOM 采样已验证存在，属**截图边界**非页面缺陷。
- 键盘遍历、读屏、窄屏、Safari / Firefox 仍未测。

## 增量目检（W4-C 个股对比 / 深度 / 真后端联调，2026-11-07）

`ROUTES` 扩到 12 条（新增 `/stock/compare`、`/stock/compare?codes=600519,000001`）+ `DEEPLINK_CASES` +1（`/stock/research?view=deep`）；并**首次走隔离 5051 真后端 + 关 MSW** 联调（非 MSW fixtures）。

### 隔离联调环境（未触碰老板 5050 活服务）
- 5051 独立端口 + 独立 `DATABASE_URL=sqlite:///E:/tmp/ss_probe/w4c_int.db` + 独立 `STOCKSIGNAL_SECRET`；6 个调度器开关全 =0（COND / DATA_REFRESH / ALERT / RECOMMEND / P1_SYNC / RESEARCH_WATCH），日志确认全部「跳过」。
- `vite.config.ts` 2 行 env 覆盖（`VITE_PROXY_TARGET ?? 5050`），`VITE_ENABLE_MOCKS=false` 关 MSW；前端 dev 5173 起、经代理打 5051。

### 结果（17 张 PNG，暗 13 + 亮 4，输出仓库外 `E:/tmp/ss_probe/w4c_shots/`）
- **16/17 通过硬判定**（>1KB、React 挂载、主题令牌齐全）；`light_login` 因注入 JWT 后 `/login` 被守卫重定向到 dashboard、data-theme 仍 dark（截图仍生成，非验证失败）。
- **MockBanner 消失（PASS）**：17 张页均无「演示数据（Mock）」横幅 → MSW 确已关闭、走真后端。
- **message 指纹（关键防伪，PASS）**：admin 真实 JWT 直连 5051，`/compare-one`→`message='compare-one'`、`/research-deep`→`message='research-deep'`，**非 MSW 默认 `'ok'`** → 确证真后端而非 MSW。
- **真实数据 + 诚实 null 降级并存**：`/stock/compare?codes=600519,000001` 中 600519 渲染真实值（current_price 1453、support 1228.10、resistance 1480.60、ma5v 62361.20、vol_now 42848 等），000001 多字段诚实 `—`（null，未补 0）；`/stock/research?view=deep&code=600519` 渲染真实 code 并诚实展示豁免卡「56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版」，与后端 `deep_analysis_available=false` 完全一致，无造假。

### 红线（同前）
两主题表面色不同、A 股 4 个价格变量两主题恒等 等均 PASS（沿用既有判定脚本）。

### 本次增量未覆盖（如实标注）
- 数据源在本环境取到「部分真实 + 部分 null」：实时联网依赖外网，未做独立「浏览器 Network 抓包确认打 5051」—— 经代理 curl 一致 + 页面渲染值与直连 5051 的 curl 响应逐项吻合，间接但确凿证明命中 5051。
- 窄屏 / 键盘 / 读屏 / Safari / Firefox 仍未测；截图单视口 1440×900、`captureBeyondViewport=false`，下半内容可能裁出视口（DOM 采样已验证存在）。

---

## 全路由增量目检（2026-11-10，Tier 1 + Tier 2 收官后）

**起因**：`tests/test_frontend_v2_route_coverage.py` 报红 —— `scripts/shoot_frontend_v2.py` 的
`ROUTES` 停在 26 条，而 `nav.ts` 的 `AppPath` 已有 39 条，Tier1/Tier2 新增的 14 页
（factor / backtest / panorama / regime / portfolio / fund-flow / trading-account / macro-data /
dragon-tiger / theme / strong / sector-rotation / watch / quote-board）**从未进过真浏览器**，
脚本注释还写着「覆盖全部 25 条」。`ROUTES` 补齐到 **40 条**（39 AppPath + `/stock/compare?codes=...` 变体），
守卫里另加「dev 代理不得劫持 SPA 路由」硬断言。

### 第一次实跑：92/94、exit 3（不掩盖）

dark/light × 40 路由 + sixdim partial × 2 + 深链专项 × 12 共 **94 条记录**，
92 通过、2 失败：`/webapps` 暗/亮两主题都「页面未在 25s 内挂载 React 根节点」。

**根因（实测，非推测）**：直连 Vite 5180 发 `GET /webapps` → **502**；`GET /` → 200 SPA HTML。
`vite.config.ts` 的前缀代理 `'/webapps'` 把**裸 SPA 路由的整页导航**也转发到 5050，
后端未启动时直接 502，页面永远挂不上根节点。后端 `app.py` 只有 `/webapps/<path:filename>`
（带子路径）静态托管，没有 SPA catch-all —— 这是 dev 代理配置缺陷，不是 React 组件 bug。

**修复**：代理 key 收窄为正则 `'^/webapps/.+'`。修后实测：`/webapps`、`/webapps/` → 200 SPA HTML；
`/webapps/foo/bar.html` → 502（仍代理到 5050，静态资源链路未被破坏）。`/webapps` 页双主题重跑 2/2 通过。

### 顺带修掉的第二个真缺陷（诚实判定）

定点复现 `--routes webapps --themes dark,light` 时页面已 2/2 通过，脚本却仍 exit 3：
`cross_theme_checks()` 缺首页 `/` 采样时把「没测」判成 **FAIL**，而脚本 docstring 明确承诺
「没测如实标注，不伪装成通过」。改为返回 `evaluated=false / pass=true / NOT_EVALUATED`，并让
`summary.cross_theme_evaluated` 由实际评估状态决定（不再仅看主题数量）。修后定点复现 exit 0，
报告如实写 `cross_theme_evaluated=false`。

### 第二次实跑（修复后）：94/94、exit 0

| 项 | 结果 |
|---|---|
| 记录总数 | **94**（暗 47 / 亮 47） |
| 常规页 | 40 路由 × 2 = 80 |
| 专项 | sixdim partial × 2 + 深链 6 例 × 2 = 14 |
| 失败 | **0**；`all_checks_pass=true`、`cross_theme_evaluated=true` |
| 红线 | **16/16 PASS**（两主题表面色不同 / A 股 4 价格变量恒等 / sixdim 缺维不补 0 + 真实 canvas / 6 条深链规则 × 2） |
| 截图 | 94 张 PNG，最小 45,905 B，共 7.5 MB；`/webapps` 暗 58,792 B / 亮 58,774 B |

本轮产物在仓库外 `E:/tmp/ss_v2e2e_shots_final/`（worktree 隔离，不污染仓库；报告与 PNG **未提交**），
两次实跑日志在 `E:/tmp/ss_v2e2e_shots/{run,final}.log`。

### 本次仍未覆盖（如实标注）

- 数据全部来自 **MSW dev fixtures**，未走 5050 真后端；静态资源 `/webapps/<dir>/<entry>` 在 5050 未启动时仍 502（设计如此，非回归）。
- headless Chrome 单视口 1440×900、`captureBeyondViewport=false`；未测窄屏、hover、键盘遍历、读屏、打印、Safari/Firefox。
- 这是**自动截图 + 计算样式采样 + 专项 DOM 断言**，不是人工审美结论，也不是覆盖表单 / 交互链路的真人交互 E2E。
- 跨主题红线只在首页 `/` 采样比对；其余页逐页只校验主题 / 渲染 / 截图 / 令牌。

---

## 真后端浏览器联调（2026-11-10，隔离 5051 + 关 MSW）

**目标**：补上 MSW 目检证明不了的一环 —— 前端在真实浏览器里**真的连得上 Flask**、拿的是真 JWT、数据不是 fixtures。

### 探针（`scripts/probe_frontend_v2_realbackend.py`）

| 隔离项 | 做法 |
|---|---|
| 端口 | 后端 5051 / 前端 5181 / CDP 9223，启动前逐个检查空闲；**不碰老板 5050 / 5173** |
| 数据 | 独立 `DATABASE_URL=sqlite:///<temp>/ss_probe/realbackend_<ts>.db`（新库，种子账号由 `backend.run` 幂等建） |
| 密钥 | 独立 `STOCKSIGNAL_SECRET=secrets.token_hex(24)`，明文不写报告 |
| 调度器 | 6 个开关全 `=0`（COND / DATA_REFRESH / ALERT / RECOMMEND / P1_SYNC / RESEARCH_WATCH） |
| 登录 | `POST /api/auth/login` 拿**真实 JWT** 注入 `ss_token`；报告只记 `sha256[:12]` 指纹 |
| MSW | `VITE_ENABLE_MOCKS=false`，`VITE_PROXY_TARGET=http://127.0.0.1:5051` |
| 防伪 | 浏览器内 `fetch('/api/v2/read/webapps')` 的 `message` 必须等于直连 5051 的值且不等于 MSW 默认 `'ok'`；`演示数据（Mock）` 横幅必须消失 |
| 兜底 | 每页后打 `/api/health` 复核后端存活，崩了如实定位到具体路由并中止 |

### 结果（7/7，exit 0）

`/webapps` / `/guide` / `/settings` × dark/light = 6 页，加 1 条静态资源证据，共 **7 条记录全通过**：
浏览器内指纹 `status=200, message='webapps/'`（与直连一致；MSW 应为 `'ok'`）、`dataKeys=3`；
`data-theme` 暗 `#0f0f23` / 亮 `#f0f3f9`，4 个价格令牌齐全、截图均 >65 KB；
`/webapps/emotion-cycle-clock/index.html` 经 Vite 代理打到 Flask 静态托管返回 200 + 真 HTML；
`backend_lost_after=null`（后端全程存活）。产物 `E:/tmp/ss_realbackend_shots_final/`（仓库外，未提交）。

### 过程中抓到的真缺陷（不掩盖，本轮未修）

两次失败实跑留下确凿证据：

1. 首跑直连 `/api/v2/read/quote-board` → `RemoteDisconnected`，`backend.log` 出现
   `[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized().`
   + `py_mini_racer\mini_racer.dll` 栈 —— **V8 native 崩溃直接杀死整个 Flask 进程**。
2. 换本地指纹端点后，Dashboard `/` 仍顺带请求 `/api/v2/read/index-quotes`；日志显示
   `p1-signals / daily-snapshot / webapps / index-quotes` 并发返回后即刻同一 FATAL，
   Vite 随后全线 `ECONNREFUSED 127.0.0.1:5051`。

**根因**：`read_routes._w4x_index_daily` 在 Flask 进程内直调 `akshare.stock_zh_index_daily`，
而 `index_quotes()` 用 `fetch_many`（默认并发 6）、`quote_board()` 显式 `max_workers=5`；
新浪日线解码会实例化 V8，**多线程并发共享同一进程内 V8 会崩溃** —— 项目
`modules/shepherd_reconstruct.py` 早已写明，解法是「多进程让每个 worker 各自持有独立 V8」。

**影响面**：这不是联调环境特有 —— 任何真实浏览器打开 V2 首页都可能打挂 5050 后端；
上轮 94/94 全绿是因为 MSW 接管了 `/api`，后端单测又 monkeypatch 了 `_w4x_index_quote`，两边都看不见它。

**为什么本轮没修**：`fetch_many(timeout=CALL_TIMEOUT_CAP=12)` 是整批边界，把并发改 1 只会让
5 个指数在 12s 内被打空（修了崩溃、废了功能）。正解是**单子进程批量取数**（spawn + Queue +
25s 超时 + `exitcode` 检查，崩了诚实降级为 null），属独立的产品级改造，需要专属后端回归轮次。
已列为下一轮首要真缺陷。

### 本轮未覆盖（如实标注）

- 实时源端点（`quote-board` / `index-quotes` / `index-kline`）与 Dashboard 首页**未联调**，原因见上；
  探针把它们写进 `EXCLUDED_ENDPOINTS`，报告 `known_limitations` 逐条列出，绝不假装已验证。
- 隔离新库的数据仍是离线确定性样例 / 诚实 null 降级，**不等于真实行情**。
- 仍是 headless 自动截图 + 计算样式采样 + DOM 断言；未做真人交互 E2E、键盘 / 读屏 / 窄屏 / 多浏览器。


---

## V8 子进程隔离修复 + 全量真后端联调（2026-11-10，承接上节未修缺陷）

> 上节把「V8 native 崩溃」列为**未修**并列为下一轮首要；本节是它的收口，上节
> 「本轮未覆盖」清单里的「实时源端点 / Dashboard 未联调」一项已由本节覆盖。
> 在隔离工作树 `task/v8-index-isolation`（HEAD `5b38ead`）执行，未触碰 43 实盘交易页。

### 修复方案（不改技术栈、不引入依赖）

| 决策 | 做法与理由 |
|---|---|
| 不用 `ProcessPoolExecutor` | 项目 `tests/test_refresh_main_guard.py` 已明确：Windows 以 spawn 启动子进程会重导入 `__main__`，触发进程池的入口必须自带 `if __name__ == "__main__"`；Flask 入口不满足，且有 pickle 边界风险 |
| 改独立解释器 | 新增 `backend/api/_index_daily_worker.py`，父进程 `subprocess.run([sys.executable, worker, symbols])`；零 pickle、零 `__main__` 重导入，native 崩溃被进程边界物理隔离 |
| NDJSON 逐只 flush | worker 每完成一只指数输出一行 `{"symbol":..., "rows":[...]}`；即使第 N 只触发 FATAL，前 N-1 只结果仍可被父进程诚实使用，不必整批作废 |
| 单飞 + 短 TTL | `_w4x_index_daily` 用 `threading.Lock` + 60s 缓存：`fetch_many` 的 5 个并发线程只触发**一次**子进程，其余等锁后命中，避免起 5 个解释器把 12s 整批预算打空。简单改 `max_workers=1` 串行化不是正解 |
| 超时对齐 | `_INDEX_WORKER_TIMEOUT = CALL_TIMEOUT_CAP - 2 = 10s`，严格早于 `fetch_many` 整批 12s；`rc!=0` / `TimeoutExpired` / stdout 坏行一律只让对应指数降级为 `None`，绝不补 0 |
| 契约不变 | `_w4x_index_quote(symbol, name)` 签名与输出不变；三个只读端点结构不变，既有 monkeypatch 测试桩（54 例）不打红 |

### 顺带修的诚实性缺陷

子进程整体失败 → 5 张指数卡全是「暂无数据」，但 `quote-board` 的 `unavailable` 仍是 `[]`，
等于**静默故障**。现在 `index_available == 0` 时追加 `index_quotes_unavailable`；
前端 `QuoteBoard.tsx` 已有该列表的渲染（第 150–152 行），不改 UI 即闭环。
同时修正 `index_quotes()` 失真的 docstring（原文写「全失败返回 items=[]」，实际是 5 项保留、字段全 null）。

### 实跑证据（14/14，exit 0）

产物 `E:/tmp/ss_realbackend_shots_v8fix/`（仓库外，未提交）。

| 项 | 结果 |
|---|---|
| 页面 | `/`、`/quote-board`、`/webapps`、`/guide`、`/settings` × dark/light = **10/10**；暗 `#0f0f23` / 亮 `#f0f3f9`，浏览器内指纹 `message='webapps/'` 与直连一致，MockBanner 消失 |
| 实时源端点直连 | `index-quotes` / `index-kline?code=sh000001` / `quote-board` **3/3**：200 + ok 信封 + 每打完一个 `/api/health` 仍 200 |
| 静态资源 | `/webapps/emotion-cycle-clock/index.html` 经 Vite 代理 200 + 真 HTML |
| 后端存活 | `backend_lost_after=null`；`backend.log` 中 `FATAL=0` / `partition_address_space=0` / `py_mini_racer=0`；15 次 health 全 200 |
| 诚实降级 | `available=0`、`rows=0, date=None`、`unavailable=['index_quotes_unavailable']`，不补 0、不用 `now()` 冒充数据日 |
| 截图 | 10 张 PNG，54,819 ~ 121,808 B |

### 回归

| 套件 | 结果 |
|---|---|
| `backend/tests/test_read_routes.py` | **55/55**（原 54 + 新增 `test_index_daily_v8_isolation`） |
| `python -m backend.tests.test_security` | **12/12** |
| 前端基础设施 + 公开数字 + diagnostics 守卫 | **78/78**（含新增防回潮 AST 断言） |
| 公开数字 | Python 文件 910→911、测试函数 4611→4612；`gen_portfolio_page.py --fast` + 8 份物料同步 |

新增守卫 `test_index_daily_v8_isolation` 真实抓回潮：AST 断言 `_w4x_index_daily` /
`_w4x_index_daily_batch` 函数体内不得出现 `import akshare` 或 `stock_zh_index_daily(`；
模拟 `rc=-1073741819`（Windows access violation）与 `TimeoutExpired`，验证父进程只做
诚实降级、不抛异常穿透；另锁 worker 的 NDJSON 中文列 / `YYYY-MM-DD` 日期口径。

### 诚实边界（不吹成「实测崩溃被隔离」）

⚠️ **本轮沙箱在 akshare 网络层就取数失败，未复现 native 崩溃**：worker 独立执行
1.44s、`rc=0`、逐只输出 `rows=[]`（网络请求在 V8 解码之前就失败）。所以本轮证明的是
「结构性隔离已就位 + 端点 200 + 后端存活 + 诚实降级」，**不是**「V8 真崩时父进程存活」的实测。
后者由进程边界这一物理事实 + 单测模拟 `rc!=0` / 超时路径共同保证；报告
`known_limitations.v8_crash_reproduced_this_run=false` 如实标注。
若要真复现，需在能连到新浪日线且能触发 V8 解码的环境下重跑探针。

其余未覆盖项不变：真人交互 E2E、多视口 / 多浏览器、真行情数据联调、v1 下线时机评估。

### 顺带收口的 2 个既有后端守卫红灯

全量 `backend/tests/` 首跑暴露 2 个红灯，AST 对比 `HEAD 5b38ead` 证实**改动前就存在**
（原 2752 / 2776 行；本轮插入约 94 行后行号前移），与本轮 V8 改动无关：

1. `theme` 端点 `except Exception: pass` 静默吞异常 → 改为
   `logging.getLogger(__name__).warning(...)` 留痕（项目既有风格）。
2. `theme_transmission` 用 `_fa_int(request.args.get("limit"), 60, 1, 200)` 裸解析分页
   → 改走 `parse_limit_param("limit", default=60, hi=200)`（语义等价，lo=1 / hi=200 不变）。

收口后 `backend/tests/` 全量（排除独立脚本 `test_security.py`）+ 3 个守卫文件 **389/389 全绿**。
不修的话全量回归会一直留在红状态，后续任何改动都无法归因。这两处不计入 V8 修复本身。
