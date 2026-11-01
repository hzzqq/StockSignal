# UI 设计系统 · PR 审查清单（P2-4 迁移冻结条款）

> 2026-11-01 落地（Phase3 §2.4 裁定）。用途：凡 PR/commit diff 触及设计系统三层
> （**令牌层 `ui_theme.py` / 原语层 `ui_kit.py` / 页面层 `pages/*.py`**）时，
> 提交前逐项自查。**三类 diff 各有冻结规则，越界改动必须同 commit 带守卫同步或书面豁免说明。**

## 一、三类 diff 冻结规则

### ① 令牌层 diff（`modules/ui_theme.py`、`ui_kit.py` 的 `_TOKEN_CSS`）
- [ ] 新增令牌只能**追加**进 `_TOKEN_CSS`（三条注入通道自动全带），禁止在页面/原语层重复定义同类色值；
- [ ] 改令牌值必须说明视觉影响面（哪些组件/风格受影响），涉及对比度须过 `test_a11y_contrast`；
- [ ] 禁止删除 `deprecated` 标记的旧 CSS 规则（守卫 test_ui_kit_tokens 锁存在性，删除=守卫同步 commit）。

### ② 原语层 diff（`modules/ui_kit.py` 组件、`_KIT_CSS`）
- [ ] 升级原语签名只增不删（新增参数带默认值，旧调用零改动）；
- [ ] 硬编码色值**禁止回潮**——一律走令牌（`--ss-*`），紫 rgba/裸 hex 出现即打回；
- [ ] 原 CSS class 改名/新增必须同步 `tests/test_bento_standards.py` 的 `_KNOWN_PAGE_CLASSES`（G5 登记制）。

### ③ 页面层 diff（`pages/*.py`）
- [ ] **禁 `use_container_width=`**（用 `width="stretch"/"content"`）——守卫 `test_streamlit_api_hygiene` hard fail；
- [ ] **禁任何接收者 `.metric(`**——守卫 `test_no_st_metric_in_pages`（G6）hard fail，KPI 用 `xc_kpi_grid`（窄列 `stat_tile`）；
- [ ] Bento `template=` 只能用 G4 白名单预设（新增预设须人审后登记，写明来源页与卡数）；
- [ ] KPI 带 delta 方向语义：**A股涨红跌绿**（tone/delta_dir，up=红）；无方向量级（胜率/夏普/回撤）不着色；
- [ ] 新页必须 `render_standard_page` 门禁 + 五段式骨架（header→KPI带→主视区→辅助区→方法学注脚）。

## 二、守卫同步义务（改动即同步，防红灯积压）

| 本 diff 触及 | 必须同 commit 做 |
|---|---|
| 迁掉某页的 st.metric | `test_metric_delta_color.py` COMPLETED_FILES 移出该页（assert calls 非空会红） |
| 页面手写 class | G5 `_KNOWN_PAGE_CLASSES` 登记（或改走 ui_kit 工厂） |
| xc_bento template 传参 | G4 `BENTO_TEMPLATE_WHITELIST` 人审登记（注明来源页/卡数/日期） |
| widgets.py | `test_sidebar_nav` 必跑（同文件含 _NAV_GROUPS 锁） |
| 令牌值变更 | `test_a11y_contrast` + `test_ui_theme_styles`（字段集合锁）必跑 |

**例行必跑**（改上述三层任意一层）：`test_bento_standards` / `test_no_st_metric_in_pages` /
`test_streamlit_api_hygiene` / `test_ui_design_system` / `test_metric_delta_color` /
`test_ui_kit_tokens` + 目标页定向冒烟；触及 ui_theme 再加全量冒烟。

## 三、多 AI 共区红线（2026-11-01 清树事故固化）

- **worker/协作者交付即由收口方提交，永不攒批**——未提交改动在共区随时可能被清；
- 禁止任何一方 discard-all / 清工作树 / `git checkout .`（会抹他人未提交产出）；
- commit 只 `git add` 本任务文件清单，**禁 `git add -A`**；推前 fetch+FF 校验。

## 四、豁免

任何越界项若确需豁免，须在 commit message 写明「豁免项 + 理由 + 复核人」，无说明即打回。
