# 👋 新来的朋友看这里 · StockSignal 是什么 & 怎么开始

欢迎来到 StockSignal 社区！这是一份「5 分钟上手」指南，看完你就能本地跑起来。

## 它是什么

一个**开源免费、不依赖任何券商接口**的 A 股事件驱动投资分析平台。把「事件 → 主线 → 回测 → 交易」串成一个工作台。

- **38 个功能页面**：行情看板 / 个股分析 / 多股对比 / 事件追踪 / 策略回测 / 资金流向 / 市场情绪 / 模拟交易 / 智能条件单 / 星辰 AI 投研……
- **4 级数据源自动降级**：AKShare → BaoStock → 新浪 → 东方财富 → 本地缓存，单点故障不崩、断网也能看历史。
- **1767 个自动化测试**兜底，每个页面都有测试。
- 暗夜 / 白天双主题，A 股红涨绿跌。

## 3 步跑起来

```bash
git clone https://github.com/hzzqq/StockSignal.git
cd StockSignal
pip install -r requirements.txt -r backend/requirements.txt
python -m backend.scripts.init_db
python -m flask --app backend.app:app run --port 5050   # 终端1
streamlit run app.py                                     # 终端2
```

Windows 直接双击 `启动StockSignal.bat`；也支持 Docker Compose。

默认账号：`demo / Demo@123`（体验全部功能）、`admin / Admin@123`（管理后台）。

## 你想做什么，就去哪一页

- 看盘 → **行情看板**
- 研究一只票 → **个股分析**
- 找当下主线 → **市场驱动力 / 板块轮动**
- 验一个策略 → **策略回测**
- 跟情绪面 → **市场情绪 / 股吧热帖**
- 问 AI → **星辰 AI**（右侧栏常驻）

## 反馈渠道（每条都进 roadmap）

- 🐛 Bug → 提 Issue（附复现步骤 + 报错）
- 💡 功能想法 → Feature Request Issue
- 🤔 不会用 → 使用问题 Issue，我逐条回
- 🛠 想直接改 → Fork + PR
- ⭐ 顺手点 star，让更多人看到

## 社区公约

不荐股、拒绝「圣杯」、实盘风险自负。这里是交流工具与方法的地方，不是喊单群。

> ⚠️ 本项目为软件工程实训课程设计，仅用于学习与研究，不构成任何投资建议。

有问题随时在这个讨论里 @ 我，或者开新讨论。一起把它做得更好 🚀
