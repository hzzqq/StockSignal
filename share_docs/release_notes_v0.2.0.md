## 🎨 StockSignal v0.2.0 · 全站视觉统一 + 社区化

> 本次更新聚焦「让更多人愿意用、愿意评」：全站 UI 重做、README 社区化、仓库公开上线。

### ✨ 本次亮点
- **全站视觉统一为「新城（xc）」设计语言**：深紫渐变 `#667eea→#764ba2`、16px 大圆角、hover 抬升 + 紫色光晕。
  - 通过单一共享 CSS 注入点（`dashboard_sf_css`）重渲染 19 个 `.sf-*` 子类，**零调用点改动**即全站 80+ 卡片自动继承新风格；
  - 36 个页面头部统一升级为 `page_hero(style='xc')`；
  - 指数卡 / 板块卡 / 内联卡全部套 xc 组件；
  - **修复暗色模式下 11 处硬编码 hex 导致的文字看不清**真 bug。
- **README 社区化**：补全界面截图（6 张真实数据渲染）、一键启动脚本说明、贡献指引、社区公约、免责声明。
- **仓库公开上线**：PUBLIC 可见 + 15 个 Topics（a-share / streamlit / quant / akshare / backtrader …）+ Discussions 已开。

### 🧱 工程基线
- 测试 **57 passed 0 failed**（ui_kit / ui_theme / page_utils / 38 页离线冒烟），业务逻辑 0 改动（additive-only）。
- 数据正确性断言 + 后端安全回归 12/12 持续绿。

### 🚀 升级方式
无需数据库迁移。拉取最新 `main` 后按 README 方式 A/B/C 重启即可：
```bash
git pull
python -m backend.scripts.init_db   # 仅在首次或模型变更时需要
```

### 👋 欢迎来玩
- ⭐ Star 让更多人看到
- 💬 [Discussions](https://github.com/hzzqq/StockSignal/discussions) 聊策略 / 风控 / 需求
- 🐛 任何问题提 Issue，每条反馈都进下个迭代

> ⚠️ 本项目为软件工程实训课程设计，仅用于学习与研究，不构成任何投资建议。
