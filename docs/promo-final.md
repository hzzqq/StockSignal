# StockSignal v0.1.0 发帖素材（含截图 + 真实链接）

> **发布前确认**：所有链接已就绪，截图已落地。
> - 仓库：https://github.com/hzzqq/StockSignal
> - Release：https://github.com/hzzqq/StockSignal/releases/tag/v0.1.0
> - 欢迎 issue：https://github.com/hzzqq/StockSignal/issues/1
> - 截图：`screenshots/00-05*.png`（6 张真实图表）

---

## 🏆 掘金（技术帖，偏开发者）—— 已可发

# 我开源了一个 A 股事件驱动分析平台：4 大免费数据源自动降级 + 38 个页面 + 1767 个测试

> 一句话：不依赖任何券商接口，聚合 AKShare / BaoStock / 新浪 / 东方财富四个免费源，每个页面都有测试兜底，双击 bat 就能跑起来。

**先看几张图**（截图均来自真实运行数据）：

![K线](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/01-kline-light.png)
![板块热力](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/03-sector-heatmap.png)
![多股对比](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/04-multi-stock-compare.png)

**为什么做这个**
软件工程实训课程设计。从想看「事件怎么影响股价」开始，慢慢堆出了 38 个功能页面。

**核心能力**
- 4 级数据源降级链（AKShare → BaoStock → 新浪 → 东财 → 本地缓存）：单点故障不崩
- 38 个页面：行情看板 / 个股分析 / 多股对比 / 事件追踪 / 策略回测 / 资金流向 / 市场情绪 / 模拟交易 / 智能条件单 / 星辰AI 投研
- 1767 个自动化测试（数据正确性断言 + 离线冒烟 + 后端安全回归）
- 暗夜/白天双主题，A 股红涨绿跌，K 线支持日/周/月切换 + 十字光标 + 双击弹分时

**快速开始**（5 行命令）
```bash
git clone https://github.com/hzzqq/StockSignal.git
cd StockSignal
pip install -r requirements.txt -r backend/requirements.txt
python -m backend.scripts.init_db && python -m flask --app backend.app:app run --port 5050 &
streamlit run app.py
```
Windows 用户直接双击 `启动StockSignal.bat` 一键全起。

**求反馈**：⭐ + Issue，每条反馈都会进下一个迭代
- 仓库：https://github.com/hzzqq/StockSignal
- 首个 Release：https://github.com/hzzqq/StockSignal/releases/tag/v0.1.0
- 欢迎 issue（置顶）：https://github.com/hzzqq/StockSignal/issues/1

---

## 💬 知乎（偏经验分享）

# 一个人全栈做 A 股分析工具：我踩过的坑和拿到的东西

（叙事向：从需求到架构到测试，重点讲"为什么这样设计"）

**三个值得讲的设计决策**

1. **数据源必须多路降级**——AKShare 一个挂了，整个项目就瘫了；所以我做了 4 级降级 + 本地缓存。这次还接入了 westock-mcp 腾讯自选股作为补充（见 `docs/westock-integration.md`）
2. **测试要验"数据对不对"而不是"页面崩没崩"**——OHLC 自洽、日期单调这些断言比 100 个冒烟有用
3. **A 股 UI 的细节**：红涨绿跌、利空事件标在 K 线下方，都是真实用户习惯

![K线暗夜](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/02-kline-dark.png)
![回测曲线](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/05-backtest-curve.png)

链接：https://github.com/hzzqq/StockSignal

---

## ⚡ V2EX（简短 + 链接）

# [开源] 我做的 A 股事件驱动分析平台，4 数据源降级 + 38 页面 + 1767 测试

- 4 大免费数据源自动降级，断网也能看历史
- 事件追踪 / 策略回测 / 模拟交易 / AI 投研
- 1767 个自动化测试
- Windows 双击 bat 一键启动

预览截图：
- 行情看板 K 线：https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/01-kline-light.png
- 多股对比：https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/04-multi-stock-compare.png

仓库：https://github.com/hzzqq/StockSignal
v0.1.0 Release：https://github.com/hzzqq/StockSignal/releases/tag/v0.1.0

新手学生项目，求 star 求 issue，任何反馈都欢迎 🙏

---

## 📱 群聊 / 朋友圈短文案

🔥 自己写的 A 股分析工具开源 v0.1.0！免费数据源×4 自动降级、38 个功能页、1767 个测试兜底，双击 bat 就能跑。

🔗 https://github.com/hzzqq/StockSignal
📦 https://github.com/hzzqq/StockSignal/releases/tag/v0.1.0

求 star 求 issue，每条反馈都会进下一个版本 🙏

---

## 🎯 配套动作（按顺序）

1. **先发掘金**（流量最大，技术受众）
2. **再发知乎**（沉淀长尾搜索）
3. **同时发 V2EX**（开发者圈）
4. **朋友圈/群聊**（个人圈层）
5. **持续 1 周**：每天扫一遍 issue 列表，新反馈及时回复（这是把路人转粉的关键）
6. **2 周后**：根据反馈发 v0.1.1 patch + 写一篇「收到 50 条反馈后我做的 5 个改进」复盘贴

---

## 💡 如果没流量（兜底心态）

- 99% 的开源项目都是这样：发出去没人看 ≠ 项目不行
- 关注「有人用了 + 提了反馈」 > 关注 star 数
- 把每一份 issue 截图进简历 = 面试素材 > 100 个 star
- 半年后回头看，你会庆幸当初把 README 写好了（仓库门面是长期资产）
