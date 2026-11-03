# StockSignal 设计系统统一文档（单一真理源）

> UI 全栈专家团交付。目标：对齐 ui-ux-pro-max 67 风格 / Bento Grids，产出全局 design tokens + 组件规范，作为后续 68 页改造的单一真理源。
> 应用形态：**Streamlit（Python + 内联 CSS）**，非 React；组件规范须 Streamlit 化。
> 边界：本文档为规范，落地动作归入后续迭代 PR（见 §5）。

> ## ⚠️ 勘误（2026-11-03 复核）：原 P0「语义色双轨=合规事故、删 `--buy/--sell`」为**误报，已撤回**。
> 交易屏（54/57/58）用 `--ss-up`(红涨)/`--ss-down`(绿跌) 正确，未用 `.sf-` 类，A 股铁律未被违反；`.sf-doc-up`(绿)/`.sf-doc-down`(红) 仅用于 `stock_research.py` 报告体与 `pages/13`，属有意的报告绿涨红跌双轨。因此落地方案 **A 由「删除」改为「改名」**：将 docs 域的 `--buy/--sell` 改名为 `--doc-up/--doc-down`（非语义、限报告体），消除同 token 跨域语义相反的命名隐患，**绝不删除**（删除会破坏报告渲染）。下文的 P0 已重分类为 P1/P2。

## 1. 视觉方向

**Dark Data Terminal（深色数据终端）为骨 + Bento Modular Grid（模块化卡片）为肉 + Minimalist Fintech（克制科技感）为度。**

- 深色为默认底，红涨绿跌为第一视觉语言，Bento 卡片承载高密度行情与信号。
- 强调色只做点睛；微光描边替代重阴影；绝不堆渐变与玻璃拟态。
- 与 ui-ux-pro-max 67 风格最契合原型：① Dark Data Terminal ② Bento Modular Grid ③ Minimalist Fintech。明确**不取** Glassmorphism / Brutalism / Neumorphism（深底易脏 / 与可信感冲突 / 阴影失效）。

## 2. 全局 Design Tokens（单一真理源草案）

### 2.1 色彩
| 分组 | Token | 浅色 | 深色 | 用途 |
|---|---|---|---|---|
| 品牌 | `--brand-1` | `#4f46e5` | `#5b53f0` | 主强调/聚焦环/激活态 |
| 品牌 | `--brand-2` | `#7c3aed` | `#7f3df0` | 渐变止/分区竖条 |
| 背景 | `--bg` | `#F5F7FA` | `#0f0f23` | 页面底 |
| 表面 | `--surface` | `#ffffff` | `#1a1a2e` | 卡片/容器 |
| 表面2 | `--surface-2` | `#f4f6fb` | `#15152a` | 内嵌/表头/斑马纹 |
| 文本 | `--text` | `#1e293b` | `#e2e8f0` | 正文/标题 |
| 文本弱 | `--text-muted` | `#64748b` | `#94a3b8` | 副信息/坐标 |
| 边框 | `--border` | `#e2e8f0` | `#2d2d44` | 分隔/卡边 |
| 边框强 | `--border-strong` | `color-mix(--brand-1 24%,--border)` | 同左 | 卡强调边（替代深阴影） |
| **涨·红** | `--c-up` | `#ff4d4f` | `#ff4d4f` | **A股涨（红），不可反转** |
| **跌·绿** | `--c-down` | `#00d486` | `#00d486` | **A股跌（绿），不可反转** |
| 持有 | `--c-hold` | `#ffa502` | `#ffa502` | 持平/换手 |
| 预警 | `--c-warn` | `#f59e0b` | `#f59e0b` | 预警/黄灯 |
| 危险 | `--c-danger` | `#ef4444` | `#ef4444` | 错误/风控 |
| 信息 | `--c-info` | `#3b82f6` | `#3b82f6` | 信息/链接 |
| 成功 | `--c-ok` | `#16a34a` | `#16a34a` | 成功（**与 `--c-down` 解耦**） |

**表面层级 ≤4**：`--bg` → `--surface` → `--surface-2` → `--overlay`(hero 光晕，仅装饰)。
**注意（命名隐患，非 Bug）**：`--buy/--sell` 在 `starfield_theme.py:28`(红涨) 与 `ui_theme.py:209,211` docs 域(绿涨) 语义相反；`.sf-doc-up/--sf-doc-down` 报告体用绿涨红跌，是**有意双轨**。落地时改名 `--doc-up/--doc-down` 消除歧义，**禁止删除**（会破坏报告渲染）。禁止页面内 `if dark: '#x' else: '#y'` 双份写死 hex。

### 2.2 字体
- 中文 `--font-cjk`：`'Microsoft YaHei UI','PingFang SC','Microsoft YaHei',system-ui,sans-serif`
- 数字等宽 `--font-num`：`'Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace`（行情/金额/KPI 必挂）
- UI 拉丁 `--font-ui`：`'Inter',system-ui,sans-serif`
- 字号 7 级(px)：`--fs-caption 11` → `label 12` → `body 14` → `title 16` → `h2 20` → `h1 24` → `display 28`
- 字重：400 / 500 / 600 / 700（800 仅留给 KPI 主数）
- 避免：13.5px 正文（现 ui_kit.py:84）；散用 17/22/24/26px 内联字号

### 2.3 间距（4px 基准 7 档）
`--sp-1 4` `--sp-2 8` `--sp-3 12` `--sp-4 16` `--sp-5 24` `--sp-6 32` `--sp-7 48`

### 2.4 圆角
卡片 `--radius-card 12`｜按钮 `--radius-btn 6`｜输入 `--radius-input 4`｜胶囊 `--radius-pill 999`

### 2.5 阴影 / 描边（深浅双规）
- 浅色：`--shadow-card 0 1px 3px rgba(15,15,35,.08)`；`--shadow-lift 0 6px 20px rgba(79,70,229,.14)`
- **深色：不用阴影，改 `--border-strong` 描边 + 1px 内描边**

### 2.6 栅格（Bento）
- 桌面(≥1280)：KPI `repeat(auto-fill,minmax(200px,1fr))`；Bento 非对称 `1.6fr 1fr 1fr`
- 平板(768–1279)：`minmax(170px,1fr)`
- 手机(<768)：`minmax(140px,1fr)`，单列优先
- **gap 统一 16px**；断点 `--bp-tablet 768px` / `--bp-desktop 1280px`

### 2.7 合并后 `:root` 骨架
```css
:root{
  --brand-1:#4f46e5; --brand-2:#7c3aed;
  --bg:#F5F7FA; --surface:#ffffff; --surface-2:#f4f6fb;
  --text:#1e293b; --text-muted:#64748b; --border:#e2e8f0;
  --c-up:#ff4d4f; --c-down:#00d486; --c-hold:#ffa502;
  --c-warn:#f59e0b; --c-danger:#ef4444; --c-info:#3b82f6; --c-ok:#16a34a;
  --font-cjk:'Microsoft YaHei UI','PingFang SC','Microsoft YaHei',system-ui,sans-serif;
  --font-num:'Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace;
  --fs-caption:11px; --fs-label:12px; --fs-body:14px; --fs-title:16px;
  --fs-h2:20px; --fs-h1:24px; --fs-display:28px;
  --sp-1:4px;--sp-2:8px;--sp-3:12px;--sp-4:16px;--sp-5:24px;--sp-6:32px;--sp-7:48px;
  --radius-card:12px; --radius-btn:6px; --radius-input:4px; --radius-pill:999px;
  --shadow-card:0 1px 3px rgba(15,15,35,.08); --shadow-lift:0 6px 20px rgba(79,70,229,.14);
}
[data-theme="dark"]{
  --bg:#0f0f23; --surface:#1a1a2e; --surface-2:#15152a;
  --text:#e2e8f0; --text-muted:#94a3b8; --border:#2d2d44;
  --brand-1:#5b53f0; --brand-2:#7f3df0;
  --shadow-card:none; --shadow-lift:none;
  --border-strong:color-mix(in srgb,var(--brand-1) 30%,var(--border));
}
```

## 3. 组件使用规范（Streamlit 化，核心交付）

> 仅覆盖 StockSignal **实际已有**组件。所有组件令牌化、深浅自适应。

| 用途 | ✅ 用这个 | ❌ 禁止 | 深浅注意 |
|---|---|---|---|
| KPI/指标 | `xc_kpi_grid` / `stat_tile` / `xc_bento_kpi` | `st.metric`（已禁 0 处） | 涨跌走 `delta_dir/tone`(up=红 内置铁律)，勿内联 hex |
| 内容卡 | `xc_content_card(title,body,icon)` | 内联 `<div style>` 信号卡 | body 空自动降级紧凑标题 |
| Hero | `page_hero(...)`(ui_kit.py:597) | 裸 `<div class="ss-hero">`(deprecated) | `.xc-hero` 自带渐变描边 |
| Bento 错落 | `xc_bento_grid(cells,template,gap=16)` | 手写 `st.columns` 不同 radius | gap 统一 16 |
| 警告 | `xc_warn_box(title,hint)` | `st.warning` 直用 | 琥珀色语义 |
| 错误 | `xc_error_box` / `xc_handle_error(title,exc)` | `st.error` / `st.stop` / 拼异常 | 异常只进 logger，绝不进可见文案 |
| 成功 | `xc_success_box`（走 `--ss-ok`） | 用绿表达「跌」 | 成功绿 ≠ 跌绿 |
| 提示 | `xc_info_banner(text,kind)` | legacy `info_banner` | kind: info/success/warning/danger |
| 空态 | `xc_empty_box(title,hint)` | `st.caption("暂无")` | 给引导文案 |
| 状态标签 | `.ss-pill`（令牌色） | 内联 `<span style=color:#xxx>` | `.ss-pill.open/.closed` 绑 `--ss-up/--ss-down` |
| 表格 | `st.dataframe(df, hide_index=True, height=…)` | 无分页直渲全量 | 长表设 `height` 出滚动；列排序原生 |
| 图表 | `st.plotly_chart(fig, width="stretch")` | 裸 `go.Figure` | 深浅 `template="plotly_dark" if dark`；字体绑 `--font-num` |
| 表单 | `st.text_input/selectbox/radio` + `search_ui.st_pills` | 自绘 HTML 输入 | `st.pills` 原生适配深浅 |
| 按钮 | `st.button(label, type="primary"/"secondary", key=…)` | 内联 `<a>/<div onclick>` | 危险操作先确认态 |
| Tabs | `st.tabs`（谨慎） | 用 Tabs 替代分区标题 | 优先 `xc_section_header` |
| 展开块 | `st.expander(title, expanded=…)` | 默认展开长内容占屏 | 长明细 `expanded=False` |
| 回到顶部 | `scroll_nav.inject_scroll_nav`（全局已注入） | 自写 JS 滚顶 | 右下固定圆钮，threshold=120px |

### 3.1 关键代码片段
```python
from modules import ui_kit as kit, colors

# KPI（替代 st.metric，红涨绿跌自动正确）
kit.xc_kpi_grid([
    {"label":"上证","value":"3,210.5","delta":"+1.23%","delta_dir":"up"},
    {"label":"创业板","value":"2,005.1","delta":"-0.45%","delta_dir":"down","tone":"down"},
], min_col=168)

# 错误（诚实红线：失败给错误卡，不谎报；异常不泄露）
try:
    data = load()
except Exception as e:
    kit.xc_handle_error("数据加载失败", exc=e, hint="请稍后重试或检查数据源")  # e 仅进日志
    return
if data is None or data.empty:
    kit.xc_warn_box("⏰ 暂无数据（网络/代理受限），非故障")  # 缺失→None，不臆造

# 状态标签（统一 .ss-pill，禁止内联 hex）
st.markdown('<span class="ss-pill open">● 实盘连接</span> '
            '<span class="ss-pill closed">○ 离线</span>', unsafe_allow_html=True)

# 表格（分页/定高，避免 81 式上千行直渲）
st.dataframe(df, width="stretch", hide_index=True, height=420, key="result_tbl")
```

## 4. 错误/加载/空态闭环

- 加载：`st.spinner`（默认）或 `ui_theme.loading_spinner(text, variant)`(ui_theme.py:514)。
- 空：`kit.xc_empty_box(title, hint)`(ui_kit.py:736)。
- 错：`kit.xc_handle_error(title, exc, hint)`(ui_kit.py:749) → 内部 `logger.warning` 记异常、只渲染友好文案，取代 `st.error(f"...{e}")`。
- **建议新增 `xc_error_boundary` 上下文管理器**（消除散落 try/except）：
```python
from contextlib import contextmanager
@contextmanager
def xc_error_boundary(title, hint="", log=None):
    try:
        yield
    except Exception as exc:
        (log or logger).warning("%s: %s", title, exc)
        xc_handle_error(title, exc=exc, hint=hint)
# 用法：with xc_error_boundary("持仓快照加载失败", hint="检查交易接口连接。"): rows = api_get(...)
```

## 5. 落地路线（分阶段，每阶段可独立提交 + 守卫）

| 阶段 | 目标 / 涉及文件 | 守卫 | 验证 | 风险 |
|---|---|---|---|---|
| **A · P1 页面 hex→colors.* + P2 命名隐患** | `ui_theme.py` docs 域 `--buy/--sell` **改名** `--doc-up/--doc-down`（非删除，防报告体失色）；`pages/*` 交易屏 hex(`#ff4d4f|#00d486`)→`colors.*` | 新增 `test_no_hardcoded_semantic_hex`（仅扫交易屏 hex，排除 `#009e60/#dc2626` 报告体）；维持 `test_updown_color_semantics` | pytest + 目检 53/54/57/58 配色与 K线方向；确认 `.sf-*` 报告体未失色 | 低（改名）/中（pages） |
| **B · P1 词汇统一** | `ui_theme.py:495/531`、`ui_kit.py:806`(标 deprecated)；`pages/*` 的 `info_banner(`→`xc_info_banner(`；删 `pages/53` 内嵌 `:root` | `test_component_vocabulary` 加 `section_header`/`info_banner` 禁令 | grep `info_banner(` 仅剩 `xc_` 前缀；目检横幅一致 | 中(20+ 页迁移) |
| **C · P2 令牌单一源 + 三态闭环** | `ui_kit.py`(`_build_token_css()` 由 `colors` 生成+`--c-*` 别名)；`ui_theme.py`(`_build_theme_root(dark)`) | `test_ui_kit_tokens` 加别名同值断言；扩 `test_sterror_leak_guard` 禁 `st.stop`/异常进 `st.error` | `test_ui_kit_tokens` 全绿；切暗/亮配色不变 | 中 |
| **D · P3 圆角/字体/对比度收口** | 圆角 16/18 统一；等宽数字全量化；`--c-*` 替换残留 `--acc1` | `test_a11y_contrast` 强化；圆角/等宽用量断言 | `test_a11y_contrast`；目检对比度与等宽对齐 | 低-中 |

### 5.1 P1 页面 hex→colors.* + P2 语义色改名（核实自源码，禁止误删）

**P1 — 页面硬编码 hex（仅交易屏语义色，不改报告体）**：
```bash
# 列出 pages/ 下交易屏语义 hex 裸字面量（红涨 #ff4d4f / 绿跌 #00d486）
grep -rEn '#(ff4d4f|00d486)' pages/
# 改前（54:281）: _UP, _DOWN = "#ff4d4f", "#00d486"
# 改后: from modules import colors ；_UP, _DOWN = colors.UP_COLOR, colors.DOWN_COLOR
```
- ⚠️ **禁止**把 `#009e60`/`#dc2626`（报告体绿涨红跌）列入扫描——它们在 `.sf-doc-*` 中是**有意**使用，误改会破坏报告渲染。
- 守卫 `test_no_hardcoded_semantic_hex` 仅扫 `pages/` 的 `#ff4d4f|#00d486`，排除 `colors.py`/`_TOKEN_CSS` 定义，近零误报。

**P2 — 语义色命名隐患（改名非删除）**：
- `ui_theme.py` docs 域(:209,:211) 与 `starfield_theme.py:28` 的 `--buy/--sell` 语义相反；将 docs 域相关键改名为 `--doc-up`/`--doc-down`，并把 `.sf-doc-up{color:var(--buy)}`(ui_theme.py:433) 等引用同步改为 `var(--doc-up)`。
- preset 键(:585/681/760/842/940) 的 `--buy/--sell` 为红涨绿跌（正确），保留但统一改名为 `--doc-up/--doc-down` 以消歧义；`.sf-*` 引用(:423/:427/:433/:259)、stAlert(:334/:336) 同步。
- **绝不删除** `--buy/--sell` 相关规则——删除会令报告体 `.sf-*` 失色。

## 6. 已知事实校正（避免规范建立在错误假设上）
- `apply_theme` **定义在 `modules/ui_theme.py:153`**（非 widgets.py）；widgets.py 仅调用。
- **无 `xc_hero` 函数**，新城 hero 入口是 `page_hero(...)`(ui_kit.py:597)，`.ss-hero` 仅 `style='sf'` 兜底。
- 现有令牌命名是 `--ss-*`/`--acc1`，与本文 draft 的 `--c-*`/`--brand-1` 不一致——§2 草案中的 `--c-*` 是**新增别名**，须 `var(--ss-*)` 等价绑定，不得臆造独立值。
- 令牌真相源以 `modules/ui_kit.py::_TOKEN_CSS` 为准（已由 `test_ui_kit_tokens.py` 锁定义/接线/语义）。
