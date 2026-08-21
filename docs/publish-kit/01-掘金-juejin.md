# 🏆 掘金发布稿（复制即发）

> **发布入口**：掘金 → 创作中心 → 写文章（https://juejin.cn/editor）
> **预计耗时**：30 秒（粘贴 + 传图 + 选标签 + 发布）
> **配图**：3 张，正文下方依次上传

---

## 标题

我开源了一个 A 股事件驱动分析平台：4 大免费数据源自动降级 + 38 个页面 + 1767 个测试

## 正文（从下一行开始复制）

> 一句话：不依赖任何券商接口，聚合 AKShare / BaoStock / 新浪 / 东方财富四个免费源，每个页面都有测试兜底，双击 bat 就能跑起来。

**先看三张图**（来自真实运行数据）：

![K线](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/01-kline-light.png)

![板块热力](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/03-sector-heatmap.png)

![多股对比](https://raw.githubusercontent.com/hzzqq/StockSignal/main/screenshots/04-multi-stock-compare.png)

**为什么做这个**

软件工程实训课程设计。从想看「事件怎么影响股价」开始，慢慢堆出了 38 个功能页面——行情看板、事件追踪、策略回测、资金流向、市场情绪、模拟交易、智能条件单、AI 投研……把自己能想到的 A 股分析场景都做了进去。

**核心能力**

- 4 级数据源降级链（AKShare → BaoStock → 新浪 → 东财 → 本地缓存）：单点故障不崩，断网也能看历史
- 38 个功能页面，暗夜/白天双主题，A 股红涨绿跌
- 1767 个自动化测试：数据正确性断言（OHLC 自洽、日期单调）+ 38 页离线冒烟 + 后端安全回归
- K 线支持日/周/月切换 + 十字光标 + 双击弹分时

**技术栈**

Python + Streamlit + Flask + AKShare/BaoStock/新浪/东财 + SQLite + Plotly + Backtrader

**快速开始**（5 行命令）

```bash
git clone https://github.com/hzzqq/StockSignal.git
cd StockSignal
pip install -r requirements.txt -r backend/requirements.txt
python -m backend.scripts.init_db && python -m flask --app backend.app:app run --port 5050 &
streamlit run app.py
```

Windows 用户直接双击 `启动StockSignal.bat` 一键全起。

**求反馈**

⭐ + Issue，每条反馈都会进下一个迭代 🙏

- 仓库：https://github.com/hzzqq/StockSignal
- 首个 Release：https://github.com/hzzqq/StockSignal/releases/tag/v0.1.0
- 社区：https://github.com/hzzqq/StockSignal/discussions

## 标签

`开源` `A股` `量化交易` `Streamlit` `Python` `投资分析`

## 发布要点

1. 标题前可加表情符号（如 📈）提升点击率
2. 三张图依次上传，插入位置已用空行标出
3. 分类选「前端/后端」或「开源」；标签直接粘贴上面 6 个
