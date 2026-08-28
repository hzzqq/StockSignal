# StockSignal 前端 UI 优化 · 10 轮迭代总览

> 角色：前端界面开发专家（在 Streamlit 语境下落地为「组件库 + 主题一致性 + 无障碍 + 视觉记忆点」）
> 方式：纯加法式 UI 改动（注入 CSS / HTML 片段 / 视觉层），**不改业务逻辑、DOM 结构、功能**
> 起点 `da2a6e7`（性能 10 轮终点） → 终点 `9ba5b58`（已 fast-forward 推送 GitHub main）

## 设计原则

1. **复用既有 widget，拒绝重复造轮子** —— 审计发现 `st.metric` 全项目 0 使用、空状态已由 `_empty_info`/`render_empty_state` 覆盖、`_data_card` 已是指标卡。故把原计划里的 metric_card / empty_state 重定向为更高价值的**签名页头**与**统一引导横幅**。
2. **主题一致** —— kit 组件 CSS 不自建暗色媒体查询，全部复用 `ui_theme` 注入的 `--acc1/--acc2/--txt/--txt2/--border/--card/--card2` 变量，随用户「白天/暗夜」开关自适应。
3. **无障碍** —— 按钮焦点环、键盘可达、按压反馈。
4. **XSS 安全** —— 所有数据派生文本走 `html.escape`，组件构建器抽成纯函数便于单测。

## 各轮交付

| 轮次 | Commit | 内容 |
|------|--------|------|
| I1 | `4f52aec` | 新增 `modules/ui_kit.py` 通用组件层：`page_hero` / `info_banner`(info/success/warning/danger) / `stat_tile` / `stat_row` / `chart_card` / `table_wrap`；+ 8 单测 `tests/test_ui_kit.py` |
| I2 | `cec0208` | `render_standard_page` 统一签名页头（hero + 主题模式/交易时段状态胶囊），**36 页一致** |
| I3 | `8a11859` | 按钮无障碍增强：`:focus-visible` 焦点环 + `:active` 按压态 + 主按钮渐变描边 |
| I4 | `dc368dd` | `info_banner` 接入引导页：系统配置 / 数据导出 / 价格预警 |
| I5 | `ce3521b` | ui_kit CSS 改用 `ui_theme` 主题变量（随 theme_mode 自适应）+ `apply_theme()` 全局注入 + `.sf-table` 粘性表头/斑马纹/hover 增强 |
| I6 | `3ddd9c6` | 行情看板行业板块网格包入 `.ss-chart` 卡片 |
| I7 | `3ddd9c6` | 系统配置概览 `st.metric` × 3 → `stat_row` 指标瓦片（股票总数/沪市/深市，红涨绿跌配色） |
| I8 | `7c0b331` | `info_banner` 接入：多股对比 / 新手教程（统一上手引导） |
| I9 | `9ba5b58` | `info_banner` 接入合并 hub 页：个股研究 / 持仓中心（标明子视图切换 + 模拟数据提示） |
| I10 | — | 全量验证 + 安全 fast-forward 推送（无新 commit） |

## 验证结果

- 新建单测 `tests/test_ui_kit.py`：**8/8 通过**（覆盖 XSS 转义、kind 回落、非法方向回落、结构正确性）
- 全量回归：unit（ui_kit 8 + perf_downsample 7 + whitebox_technical 18 = 33）+ 页面冒烟 **39/39** 全绿（EXIT=0）
- 推送：`da2a6e7..9ba5b58 main -> main`，复验 `remote == local == 9ba5b58381a847c18a972afd3371803efe6fad46`，全程无 `--force`

## 关键文件清单

- `modules/ui_kit.py`（**新增**）—— 通用展示组件层 + 主题自适应 CSS
- `modules/page_utils.py` —— 签名页头（hero + 状态胶囊）
- `modules/button_colors.py` —— 按钮无障碍 CSS
- `modules/ui_theme.py` —— `apply_theme()` 末尾全局注入 kit CSS
- `pages/8_系统配置.py` / `pages/J_数据导出.py` / `pages/9_价格预警.py` / `pages/1_行情看板.py` / `pages/2_多股对比.py` / `pages/Z_新手教程.py` / `pages/个股研究.py` / `pages/持仓中心.py` —— 引导横幅 / 卡片化 / 指标瓦片
- `tests/test_ui_kit.py`（**新增**）—— 8 单测
